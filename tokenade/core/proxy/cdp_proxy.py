"""
Tokenade CDP Proxy — Slim orchestrator.

Imports helper logic from cdp_stealth, cdp_injection, cdp_routing, cdp_api.
Defines CDPProxyConfig, CDPProxy, and re-exports needed items.
"""

import asyncio
import html
import logging
import time
from dataclasses import dataclass
from typing import Optional, Dict
from urllib.parse import urlparse

from aiohttp import web

try:
    from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from tokenade.core.runtime.engine import CookieJar, FingerprintMatcher
from tokenade.core.runtime.tls_matcher import create_tls_matcher
from tokenade.core.refresh.session_refresher import SessionRefresher, RefreshConfig

from tokenade.core.proxy.cdp_stealth import (
    is_safe_url,
    get_site_url,
)
_is_safe_url = is_safe_url
from tokenade.core.proxy.cdp_injection import (  # noqa: E402
    inject_via_cdp,
    inject_via_raw_cdp,
    inject_stealth_script,
    inject_cookies,
    inject_local_storage,
)
from tokenade.core.proxy.cdp_routing import (  # noqa: E402
    handle_route,
    handle_proxy,
    handle_page_html,
    handle_page_screenshot,
)
from tokenade.core.proxy.cdp_api import (  # noqa: E402
    handle_cdp_version,
    handle_cdp_list,
    handle_stealth_js,
    handle_status,
    handle_stats,
    handle_session_status,
    handle_session_refresh,
    handle_old_sw,
)

logger = logging.getLogger(__name__)


# ── Duplicate-header tolerance (stale service workers) ────────────

def _strip_duplicate_headers(raw_data: bytes) -> bytes:
    """Strip duplicate HTTP headers from raw request data."""
    try:
        header_end = raw_data.find(b'\r\n\r\n')
        if header_end == -1:
            return raw_data
        header_block = raw_data[:header_end]
        rest = raw_data[header_end:]
        lines = header_block.split(b'\r\n')
        seen = set()
        fixed = []
        for line in lines:
            if b':' in line:
                key = line.split(b':', 1)[0].strip().lower()
                if key in seen:
                    continue
                seen.add(key)
            fixed.append(line)
        return b'\r\n'.join(fixed) + rest
    except (ValueError, UnicodeDecodeError, KeyError) as e:
        logger.debug("Failed to strip duplicate headers, returning raw data: %s", e)
        return raw_data


class _LenientProtocol(asyncio.Protocol):
    """Wraps aiohttp's protocol to tolerate duplicate headers."""

    def __init__(self, inner):
        self._inner = inner
        self._transport = None

    def connection_made(self, transport):
        self._transport = transport
        self._inner.connection_made(transport)

    def connection_lost(self, exc):
        self._inner.connection_lost(exc)

    def data_received(self, data):
        self._inner.data_received(_strip_duplicate_headers(data))

    def eof_received(self):
        return self._inner.eof_received()


class _LenientServerFactory:
    """Protocol factory with duplicate-header tolerance."""

    def __init__(self, aiohttp_server):
        self._server = aiohttp_server

    def __call__(self):
        return _LenientProtocol(self._server())


# ── Configuration ─────────────────────────────────────────────────

@dataclass
class CDPProxyConfig:
    """Configuration for the CDP proxy server."""
    port: int = 9222
    host: str = "127.0.0.1"
    headless: bool = True
    verbose: bool = False
    timeout: int = 30
    use_fingerprint: bool = False


# ── Main proxy class ──────────────────────────────────────────────

class CDPProxy:
    """
    Playwright-based reverse proxy with TLS fingerprint matching.

    Uses a real Chromium browser to render pages.  All requests are
    intercepted via page.route() and forwarded through curl-cffi
    with the donor's TLS fingerprint and cookies.
    """

    def __init__(self, session_package: Dict, config: Optional[CDPProxyConfig] = None):
        from tokenade.core.artifacts import ProfileArtifactManager
        ProfileArtifactManager.preflight(session_package, purpose="proxy")
        self.config = config or CDPProxyConfig()
        self.session = session_package

        self.cookie_jar = CookieJar()
        self.cookie_jar.add_cookies(session_package.get("cookies", []))

        self.fingerprint = FingerprintMatcher(session_package.get("fingerprint"))

        tls_profile = session_package.get("tls_profile", {})
        self.tls_matcher = create_tls_matcher(
            browser=tls_profile.get("browser", "chrome"),
            version=tls_profile.get("version", "120"),
            impersonate=tls_profile.get("impersonate"),
        )

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._cdp_session = None
        self._pages: Dict[str, Page] = {}
        self._page_meta: Dict[str, Dict] = {}
        self._max_pages = 20
        self._page_ttl = 3600

        self._http_session = None
        self._shared_http_session = None
        self._session_lock = asyncio.Lock()

        self._refresher: Optional[SessionRefresher] = None
        self._auto_refresh_config: Dict = {}

        self._cdp_port = (self.config.port or 9222) + 1
        self._extension_bridge = None

        self.stats = {
            "requests": 0,
            "bytes_sent": 0,
            "bytes_received": 0,
            "errors": 0,
            "start_time": None,
        }

        self._app = None
        self._raw_server = None

    # ── Factory class methods ─────────────────────────────────────

    @classmethod
    def from_session_file(cls, session_file: str, config: Optional[CDPProxyConfig] = None) -> "CDPProxy":
        from tokenade.core.importer.session_packager import SessionPackager
        packager = SessionPackager()
        session = packager.load(session_file)
        from tokenade.core.artifacts import ProfileArtifactManager
        ProfileArtifactManager.preflight(session, purpose="proxy")
        return cls(session, config)

    @classmethod
    def from_session_data(cls, session_data: Dict, config: Optional[CDPProxyConfig] = None) -> "CDPProxy":
        from tokenade.core.artifacts import ProfileArtifactManager
        ProfileArtifactManager.preflight(session_data, purpose="proxy")
        return cls(session_data, config)

    # ── App creation ──────────────────────────────────────────────

    def _create_app(self) -> web.Application:
        app = web.Application()

        app.router.add_get("/_tokenade_sw.js", self._handle_old_sw)
        app.router.add_get("/proxy", self._handle_legacy_redirect)
        app.router.add_get("/proxy/", self._handle_legacy_redirect)

        app.router.add_get("/", self._handle_gui)
        app.router.add_get("/status", self._handle_status)
        app.router.add_get("/stats", self._handle_stats)
        app.router.add_get("/session/status", self._handle_session_status)
        app.router.add_post("/session/refresh", self._handle_session_refresh)
        app.router.add_post("/browse", self._handle_browse_post)
        app.router.add_get("/page/{page_id}", self._handle_page)

        app.router.add_get("/json/version", self._handle_cdp_version)
        app.router.add_get("/json/version/", self._handle_cdp_version)
        app.router.add_get("/json/list", self._handle_cdp_list)
        app.router.add_get("/json/list/", self._handle_cdp_list)

        app.router.add_get("/stealth.js", self._handle_stealth_js)
        app.router.add_get("/stealth.js/", self._handle_stealth_js)

        app.router.add_route("*", "/{path:.*}", self._handle_proxy)

        return app

    # ── Handlers delegating to helper modules ─────────────────────

    async def _handle_old_sw(self, request: web.Request) -> web.Response:
        return await handle_old_sw(self, request)

    async def _handle_legacy_redirect(self, request: web.Request) -> web.Response:
        raise web.HTTPFound("/")

    async def _handle_gui(self, request: web.Request) -> web.Response:
        site_name = html.escape(self.session.get("site_name", "unknown"))
        source_device = self.session.get("source_device", {})
        browser_name = html.escape(source_device.get("browser", "unknown"))
        platform = html.escape(source_device.get("platform", "unknown"))
        default_url = html.escape(self._get_site_url())

        gui_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Tokenade CDP Proxy - {site_name}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0a0a; color: #fff; min-height: 100vh;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
        }}
        .container {{ max-width: 800px; padding: 40px; width: 100%; }}
        h1 {{ font-size: 2.5em; margin-bottom: 10px; }}
        .subtitle {{ color: #888; font-size: 1.2em; margin-bottom: 40px; }}
        .card {{
            background: #1a1a1a; border-radius: 12px; padding: 24px;
            margin-bottom: 20px; border: 1px solid #333;
        }}
        .card h3 {{ color: #00ff88; margin-bottom: 12px; }}
        .info-row {{ display: flex; justify-content: space-between; margin: 8px 0; }}
        .info-label {{ color: #888; }}
        .info-value {{ color: #fff; font-weight: 500; }}
        .browse-form {{ display: flex; gap: 10px; margin: 20px 0; }}
        .browse-input {{
            flex: 1; padding: 16px; border-radius: 8px; border: 1px solid #333;
            background: #0a0a0a; color: #fff; font-size: 1em; font-family: monospace;
        }}
        .browse-input:focus {{ outline: none; border-color: #00ff88; }}
        .browse-btn {{
            background: #00ff88; color: #000; padding: 16px 24px;
            border-radius: 8px; border: none; font-size: 1em; font-weight: 600;
            cursor: pointer; transition: transform 0.2s;
        }}
        .browse-btn:hover {{ transform: scale(1.05); }}
        .instructions {{ color: #888; line-height: 1.6; }}
        .instructions code {{
            background: #333; padding: 2px 6px; border-radius: 4px;
            font-family: monospace; color: #00ff88;
        }}
        .stats {{ display: flex; gap: 20px; margin-top: 20px; }}
        .stat {{ text-align: center; }}
        .stat-value {{ font-size: 2em; font-weight: bold; color: #00ff88; }}
        .stat-label {{ color: #888; font-size: 0.9em; }}
        .status {{
            padding: 8px 16px; border-radius: 20px;
            display: inline-block; margin: 10px 0;
        }}
        .status-ok {{ background: #00ff8822; color: #00ff88; border: 1px solid #00ff88; }}
        .architecture {{ color: #888; line-height: 1.8; margin-top: 10px; }}
        .architecture strong {{ color: #00ff88; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Tokenade CDP Proxy</h1>
        <p class="subtitle">Playwright-based session proxy with TLS fingerprint matching</p>

        <div class="card">
            <h3>Session Info</h3>
            <div class="info-row">
                <span class="info-label">Site</span>
                <span class="info-value">{site_name}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Source Browser</span>
                <span class="info-value">{browser_name}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Platform</span>
                <span class="info-value">{platform}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Cookies</span>
                <span class="info-value">{len(self.cookie_jar.to_list())}</span>
            </div>
            <div class="info-row">
                <span class="info-label">TLS Profile</span>
                <span class="info-value">{self.session.get("tls_profile", {}).get("impersonate", "unknown")}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Status</span>
                <span class="info-value"><span class="status status-ok">● Running</span></span>
            </div>
            <div id="expiry-info" style="margin-top: 10px; padding: 10px; border-radius: 8px; background: #1a1a1a;"></div>
        </div>

        <div class="card">
            <h3>Browse as Donor Device</h3>
            <p style="color: #888; margin-bottom: 15px;">Enter a URL to browse with the donor's fingerprint and cookies:</p>
            <form class="browse-form" action="/browse" method="POST">
                <input type="text" name="url" class="browse-input" value="{default_url}" placeholder="https://example.com">
                <button type="submit" class="browse-btn">Browse →</button>
            </form>
        </div>

        <div class="card">
            <h3>Architecture</h3>
            <div class="architecture">
                <p><strong>How it works:</strong></p>
                <p>1. Playwright Chromium renders the target page</p>
                <p>2. <code>page.route()</code> intercepts ALL browser requests</p>
                <p>3. Each request is forwarded via <strong>curl-cffi</strong> with the donor's TLS fingerprint</p>
                <p>4. Donor cookies are injected into the browser context</p>
                <p>5. Browser renders everything natively — no URL rewriting needed</p>
            </div>
        </div>

        <div class="card">
            <h3>Usage</h3>
            <div class="instructions">
                <p><strong>GUI Mode:</strong> Enter a URL above and click Browse</p>
                <p><strong>Proxy Mode:</strong> Configure your browser:</p>
                <p>Linux/Mac: <code>export HTTP_PROXY=http://127.0.0.1:{self.config.port}</code></p>
                <p>Windows: <code>set HTTP_PROXY=http://127.0.0.1:{self.config.port}</code></p>
                <p><strong>curl:</strong> <code>curl --proxy http://127.0.0.1:{self.config.port} https://example.com</code></p>
            </div>
        </div>

        <div class="stats" id="stats">
            <div class="stat">
                <div class="stat-value" id="requests">0</div>
                <div class="stat-label">Requests</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="bytes-in">0</div>
                <div class="stat-label">Received</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="bytes-out">0</div>
                <div class="stat-label">Sent</div>
            </div>
        </div>
    </div>

    <script>
        if ('serviceWorker' in navigator) {{{{
            navigator.serviceWorker.getRegistrations().then(regs => {{{{
                regs.forEach(r => {{{{ r.unregister(); }}}});
            }}}});
        }}}}
        async function updateStats() {{{{
            try {{{{
                const resp = await fetch('/stats');
                const data = await resp.json();
                document.getElementById('requests').textContent = data.requests || 0;
                document.getElementById('bytes-in').textContent = formatBytes(data.bytes_received || 0);
                document.getElementById('bytes-out').textContent = formatBytes(data.bytes_sent || 0);
            }}}} catch(e) {{{{}}}}
        }}}}
        async function updateSessionStatus() {{{{
            try {{{{
                const resp = await fetch('/session/status');
                const data = await resp.json();
                const el = document.getElementById('expiry-info');
                if (data.expired_count > 0) {{{{
                    el.innerHTML = '<span style="color: #ff6b6b;">⚠️ ' + data.expired_count + ' expired cookies</span>' +
                        '<button onclick="refreshSession()" style="margin-left: 10px; padding: 4px 8px; background: #ff6b6b; color: #fff; border: none; border-radius: 4px; cursor: pointer;">Refresh</button>';
                }}}} else if (data.critical_count > 0) {{{{
                    el.innerHTML = '<span style="color: #ffa500;">⏰ ' + data.critical_count + ' cookies expiring soon (' + (data.next_expiry_human || 'unknown') + ')</span>' +
                        '<button onclick="refreshSession()" style="margin-left: 10px; padding: 4px 8px; background: #ffa500; color: #000; border: none; border-radius: 4px; cursor: pointer;">Refresh</button>';
                }}}} else if (data.expiring_soon_count > 0) {{{{
                    el.innerHTML = '<span style="color: #888;">📅 ' + data.expiring_soon_count + ' cookies expiring in ' + data.next_expiry_human + '</span>';
                }}}} else {{{{
                    el.innerHTML = '<span style="color: #00ff88;">✓ All cookies valid</span>';
                }}}}
            }}}} catch(e) {{{{}}}}
        }}}}
        async function refreshSession() {{{{
            try {{{{
                const resp = await fetch('/session/refresh', {{{{ method: 'POST' }}}});
                const data = await resp.json();
                if (data.status === 'refreshed') {{{{
                    updateSessionStatus();
                }}}}
            }}}} catch(e) {{{{}}}}
        }}}}
        function formatBytes(bytes) {{{{
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
            return (bytes/(1024*1024)).toFixed(1) + ' MB';
        }}}}
        setInterval(updateStats, 2000);
        setInterval(updateSessionStatus, 60000);
        updateStats();
        updateSessionStatus();
    </script>
</body>
</html>"""
        return web.Response(text=gui_html, content_type='text/html')

    async def _handle_browse_post(self, request: web.Request) -> web.Response:
        try:
            data = await request.post()
            url = data.get("url", "")
            if not url:
                return web.Response(text="No URL provided", status=400)
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            parsed = urlparse(url)
            if not parsed.hostname:
                return web.Response(text="Invalid URL", status=400)
            if not is_safe_url(url):
                return web.Response(text="URL blocked: internal/private network target", status=403)

            self._cleanup_expired_pages()
            if len(self._pages) >= self._max_pages:
                oldest_id = min(self._page_meta, key=lambda k: self._page_meta[k]["created"])
                await self._close_page(oldest_id)

            page_id = str(int(time.time() * 1000))
            page = await self._context.new_page()
            self._pages[page_id] = page
            self._page_meta[page_id] = {"created": time.time()}

            if self.config.use_fingerprint:
                await page.route("**/*", lambda route: self._handle_route(route))

            asyncio.create_task(self._navigate_page(page_id, url))
            raise web.HTTPFound(f"/page/{page_id}")
        except web.HTTPFound:
            raise
        except Exception:
            logger.exception("Failed to process browse request")
            return web.Response(text="Failed to process request", status=500)

    async def _handle_page(self, request: web.Request) -> web.Response:
        page_id = request.match_info["page_id"]
        page = self._pages.get(page_id)
        if not page:
            return web.Response(
                text="<html><body><h1>Page not found</h1><p>The page may still be loading.</p></body></html>",
                content_type="text/html", status=404,
            )
        try:
            current_url = html.escape(page.url or "")
            page_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Tokenade - Browsing</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: monospace; background: #1a1a1a; color: #fff; }}
        .toolbar {{
            background: #0a0a0a; padding: 10px 20px; border-bottom: 1px solid #333;
            display: flex; align-items: center; gap: 10px;
        }}
        .toolbar .url {{
            flex: 1; padding: 8px 12px; border-radius: 4px; border: 1px solid #333;
            background: #1a1a1a; color: #00ff88; font-family: monospace; font-size: 14px;
        }}
        .toolbar a {{ color: #00ff88; text-decoration: none; padding: 8px 16px; }}
        .toolbar a:hover {{ background: #00ff8822; border-radius: 4px; }}
        .screenshot-container {{
            display: flex; justify-content: center; align-items: flex-start;
            padding: 10px; overflow: auto; height: calc(100vh - 50px);
        }}
        .screenshot-container img {{
            max-width: 100%; height: auto; border: 1px solid #333; border-radius: 4px;
        }}
        .loading {{
            display: flex; align-items: center; justify-content: center;
            height: calc(100vh - 50px); color: #888; font-size: 1.2em;
        }}
    </style>
</head>
<body>
    <div class="toolbar">
        <span class="url">{current_url}</span>
        <a href="/">← Back</a>
    </div>
    <div id="content">
        <div class="loading">Loading screenshot...</div>
    </div>
    <script>
        async function refreshScreenshot() {{{{
            try {{{{
                const resp = await fetch('/api/page/{page_id}/screenshot');
                if (resp.ok) {{{{
                    const blob = await resp.blob();
                    const url = URL.createObjectURL(blob);
                    document.getElementById('content').innerHTML = '';
                    const img = document.createElement('img');
                    img.src = url;
                    img.className = 'screenshot-container';
                    document.getElementById('content').appendChild(img);
                }}}}
            }}}} catch(e) {{{{
                console.error('Screenshot refresh failed:', e);
            }}}}
        }}}}

        setTimeout(refreshScreenshot, 2000);
        setInterval(refreshScreenshot, 5000);
    </script>
</body>
</html>"""
            return web.Response(text=page_html, content_type='text/html')
        except Exception:
            return web.Response(text="Error loading page", status=500)

    async def _handle_status(self, request: web.Request) -> web.Response:
        return await handle_status(self, request)

    async def _handle_stats(self, request: web.Request) -> web.Response:
        return await handle_stats(self, request)

    async def _handle_session_status(self, request: web.Request) -> web.Response:
        return await handle_session_status(self, request)

    async def _handle_session_refresh(self, request: web.Request) -> web.Response:
        return await handle_session_refresh(self, request)

    async def _handle_cdp_version(self, request: web.Request) -> web.Response:
        return await handle_cdp_version(self, request)

    async def _handle_cdp_list(self, request: web.Request) -> web.Response:
        return await handle_cdp_list(self, request)

    async def _handle_stealth_js(self, request: web.Request) -> web.Response:
        return await handle_stealth_js(self, request)

    async def _handle_route(self, route):
        return await handle_route(self, route)

    async def _handle_proxy(self, request: web.Request) -> web.Response:
        return await handle_proxy(self, request)

    async def _handle_page_html(self, request: web.Request) -> web.Response:
        return await handle_page_html(self, request)

    async def _handle_page_screenshot(self, request: web.Request) -> web.Response:
        return await handle_page_screenshot(self, request)

    # ── Navigation / page lifecycle ───────────────────────────────

    async def _navigate_page(self, page_id: str, url: str):
        try:
            page = self._pages.get(page_id)
            if not page:
                return
            await page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout * 1000)
            local_storage = self.session.get("local_storage", {})
            if local_storage:
                await inject_local_storage(self, page)
                await page.reload(wait_until="domcontentloaded", timeout=self.config.timeout * 1000)
            logger.info(f"Page {page_id} loaded: {url}")
        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {e}")

    def _cleanup_expired_pages(self):
        now = time.time()
        expired = [pid for pid, meta in self._page_meta.items()
                   if now - meta["created"] > self._page_ttl]
        for pid in expired:
            asyncio.create_task(self._close_page(pid))

    async def _close_page(self, page_id: str):
        page = self._pages.pop(page_id, None)
        self._page_meta.pop(page_id, None)
        if page:
            try:
                await page.close()
            except Exception:
                pass

    # ── Session refresh callback ──────────────────────────────────

    async def _on_session_refresh(self, new_session: Dict):
        try:
            self.cookie_jar = CookieJar()
            self.cookie_jar.add_cookies(new_session.get("cookies", []))
            if self._context:
                await inject_cookies(self)
            logger.info("Session hot-reloaded successfully")
        except Exception as e:
            logger.error(f"Failed to hot-reload session: {e}")

    # ── Extension bridge ──────────────────────────────────────────

    def start_extension_bridge(self, bridge_port: int = 9224):
        try:
            from tokenade.core.proxy.extension_bridge import ExtensionBridge
            self._extension_bridge = ExtensionBridge(host=self.config.host, port=bridge_port)

            def on_cookie_update(data):
                if "cookies" in data:
                    self.cookie_jar.add_cookies(data["cookies"])
                    logger.info(f"Received {len(data['cookies'])} cookies from extension")

            self._extension_bridge.on_message("cookie_update", on_cookie_update)
            asyncio.ensure_future(self._extension_bridge.start())
            logger.info(f"Extension bridge started on ws://{self.config.host}:{bridge_port}")
        except ImportError:
            logger.warning("websockets not installed. Install with: pip install websockets")
        except Exception as e:
            logger.error(f"Failed to start extension bridge: {e}")

    # ── Site URL helper ───────────────────────────────────────────

    def _get_site_url(self) -> str:
        return get_site_url(self.session)

    # ── Lifecycle ─────────────────────────────────────────────────

    async def start(self):
        if not HAS_PLAYWRIGHT:
            raise RuntimeError(
                "Playwright is required for CDP proxy. "
                "Install with: pip install playwright && playwright install chromium"
            )

        if self.config.use_fingerprint:
            from tokenade.core.runtime.tls_matcher import require_curl_cffi
            require_curl_cffi()

        self._playwright = await async_playwright().start()
        launch_args = [
            "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1920,1080", "--window-position=0,0",
            f"--remote-debugging-port={self._cdp_port}",
        ]
        if self.config.headless:
            launch_args.append("--headless=new")
        try:
            self._browser = await self._playwright.chromium.launch(
                headless=self.config.headless, args=launch_args,
            )
        except Exception as e:
            error_str = str(e).lower()
            if "executable" in error_str or "not found" in error_str or "no such" in error_str:
                raise RuntimeError(
                    "Chromium browser not found. Install it with:\n"
                    "  playwright install chromium\n\n"
                    f"Original error: {e}"
                ) from e
            elif "timeout" in error_str:
                raise RuntimeError(
                    "Chromium launch timed out. The system may be under heavy load.\n"
                    "Try: tokenade proxy -s <session> --visible\n\n"
                    f"Original error: {e}"
                ) from e
            else:
                raise RuntimeError(
                    f"Failed to launch Chromium: {e}\n\n"
                    "Troubleshooting:\n"
                    "  1. Run: playwright install chromium\n"
                    "  2. Check disk space and memory\n"
                    "  3. Try: tokenade proxy -s <session> --visible"
                ) from e

        self._context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context(
            viewport={"width": 1920, "height": 960},
            user_agent=(self.session.get("fingerprint") or {}).get(
                "user_agent",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ),
        )

        try:
            self._cdp_session = await self._browser.new_browser_cdp_session()
            await inject_via_cdp(self)
        except Exception as e:
            logger.warning(f"CDP-level injection failed, falling back to context injection: {e}")

        await inject_stealth_script(self)
        await inject_cookies(self)
        asyncio.ensure_future(inject_via_raw_cdp(self))

        self._app = self._create_app()
        self._app.freeze()
        server = web.Server(self._app._handle, request_factory=self._app._make_request)
        loop = asyncio.get_event_loop()
        self._raw_server = await loop.create_server(
            _LenientServerFactory(server), self.config.host, self.config.port
        )

        self.stats["start_time"] = time.time()

        refresh_config = RefreshConfig(
            auto_refresh=self._auto_refresh_config.get("auto_refresh", False),
            source_browser=self._auto_refresh_config.get(
                "source_browser",
                (self.session.get("source_device") or {}).get("browser"),
            ),
        )
        if self._auto_refresh_config.get("source_profile"):
            refresh_config.source_profile = self._auto_refresh_config["source_profile"]
        self._refresher = SessionRefresher(
            session=self.session, config=refresh_config,
            on_refresh=self._on_session_refresh,
        )
        await self._refresher.start()

        site_name = self.session.get("site_name", "unknown")
        cookies = self.session.get("cookies", [])
        tls_profile = self.session.get("tls_profile", {})

        from tokenade.core.importer.site_configs import get_site_config
        site_config = get_site_config(site_name)
        if site_config:
            logger.info(f"Auto-loaded site config for '{site_name}'")

        expiry_info = self._refresher.check_expiry()

        logger.info(f"CDP Proxy started on {self.config.host}:{self.config.port}")
        print(f"\n{'=' * 60}")
        print("Tokenade CDP Proxy Server")
        print(f"{'=' * 60}")
        print(f"Site: {site_name}" + (f" ({site_config['name']})" if site_config else ""))
        print(f"Cookies: {len(cookies)}")
        if expiry_info.expired_count:
            print(f"⚠️  Expired cookies: {expiry_info.expired_count} — re-export recommended")
        if expiry_info.expiring_soon_count:
            print(f"⏰ Expiring soon: {expiry_info.expiring_soon_count} — refresh recommended")
        if expiry_info.critical_count:
            print(f"🔴 Critical: {expiry_info.critical_count} cookies expiring very soon")
        if expiry_info.next_expiry_human:
            print(f"⏳ Next expiry: {expiry_info.next_expiry_human}")
        print(f"TLS Profile: {tls_profile.get('impersonate', 'unknown')}")
        print("Browser: Chromium (Playwright)")
        print(f"Headless: {self.config.headless}")
        print(f"Default URL: {self._get_site_url()}")
        print(f"\nGUI: http://127.0.0.1:{self.config.port}")
        print(f"{'=' * 60}\n")

    async def stop(self):
        if self._refresher:
            await self._refresher.stop()
        if self._extension_bridge:
            self._extension_bridge.stop()
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
        if self._raw_server:
            self._raw_server.close()
            await self._raw_server.wait_closed()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        if self.tls_matcher:
            self.tls_matcher.close()

    def run(self):
        asyncio.run(self._run_async())

    async def _run_async(self):
        await self.start()
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down CDP proxy...")
        finally:
            await self.stop()


# ── Convenience factory ───────────────────────────────────────────

def create_cdp_proxy_from_file(session_file: str, port: int = 9222, headless: bool = True) -> CDPProxy:
    """Convenience function to create a CDP proxy from a session file."""
    config = CDPProxyConfig(port=port, headless=headless)
    return CDPProxy.from_session_file(session_file, config)
