"""
Tokenade CDP Proxy - Playwright-based reverse proxy with TLS fingerprint matching.

Architecture:
  1. Launch Playwright Chromium with donor cookies injected
  2. page.route("**/*") intercepts ALL browser requests
  3. Handler forwards via curl-cffi (TLS matched) with donor headers/cookies
  4. Browser renders everything natively — no URL rewriting, no service worker
  5. aiohttp serves GUI + reverse proxy for the client browser

Key insight: The browser makes the requests, not the proxy.
The proxy just ensures each request goes through curl-cffi with the
donor's TLS fingerprint and cookies.
"""

import asyncio
import base64
import html
import ipaddress
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from urllib.parse import urlparse

import aiohttp
from aiohttp import web


def _strip_duplicate_headers(raw_data: bytes) -> bytes:
    """Strip duplicate HTTP headers from raw request data to handle stale service workers."""
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
    """Wraps aiohttp's protocol to tolerate duplicate headers from stale service workers."""
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
    """Protocol factory that wraps aiohttp's protocol with duplicate-header tolerance."""
    def __init__(self, aiohttp_server):
        self._server = aiohttp_server
    def __call__(self):
        return _LenientProtocol(self._server())

try:
    from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from tokenade.core.errors import ProxyError, ConfigurationError
from tokenade.core.runtime.engine import CookieJar, FingerprintMatcher
from tokenade.core.runtime.tls_matcher import TLSMatcher, create_tls_matcher
from tokenade.core.importer.session_refresher import SessionRefresher, RefreshConfig

logger = logging.getLogger(__name__)

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_safe_url(url: str) -> bool:
    """Check if a URL is safe to proxy (not targeting internal networks)."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False
        if hostname in ("localhost", "0.0.0.0", "[::]", "metadata.google.internal"):
            return False
        try:
            addr = ipaddress.ip_address(hostname)
            for net in _BLOCKED_NETWORKS:
                if addr in net:
                    return False
        except ValueError:
            pass
        return True
    except (ValueError, TypeError) as e:
        logger.debug("URL safety check failed: %s", e)
        return False


@dataclass
class CDPProxyConfig:
    """Configuration for the CDP proxy server."""
    port: int = 9222
    host: str = "127.0.0.1"
    headless: bool = True
    verbose: bool = False
    timeout: int = 30
    use_fingerprint: bool = False


class CDPProxy:
    """
    Playwright-based reverse proxy with TLS fingerprint matching.
    
    Uses a real Chromium browser to render pages. All requests are
    intercepted via page.route() and forwarded through curl-cffi
    with the donor's TLS fingerprint and cookies.
    
    Benefits over the old SW-based approach:
    - No URL rewriting needed
    - No service worker injection
    - No <base> tag injection
    - Browser handles all JS/CSS/fonts natively
    - Perfect rendering of SPAs (React, Next.js, etc.)
    - Sub-resource requests (fonts, analytics, etc.) work correctly
    """
    
    def __init__(self, session_package: Dict, config: Optional[CDPProxyConfig] = None):
        self.config = config or CDPProxyConfig()
        self.session = session_package
        
        # Initialize components from session
        self.cookie_jar = CookieJar()
        self.cookie_jar.add_cookies(session_package.get("cookies", []))
        
        self.fingerprint = FingerprintMatcher(session_package.get("fingerprint"))
        
        # Initialize TLS matcher
        tls_profile = session_package.get("tls_profile", {})
        self.tls_matcher = create_tls_matcher(
            browser=tls_profile.get("browser", "chrome"),
            version=tls_profile.get("version", "120"),
            impersonate=tls_profile.get("impersonate")
        )
        
        # Playwright state
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._pages: Dict[str, Page] = {}  # url -> page
        self._page_meta: Dict[str, Dict] = {}  # url -> {"created": timestamp}
        self._max_pages = 20
        self._page_ttl = 3600  # 1 hour
        
        # HTTP session for curl-cffi fallback
        self._http_session = None
        self._shared_http_session = None  # Set by MultiSiteProxy for connection pooling
        self._session_lock = asyncio.Lock()
        
        # Session auto-refresh
        self._refresher: Optional[SessionRefresher] = None
        self._auto_refresh_config: Dict = {}
        
        # Extension bridge (optional)
        self._extension_bridge = None
        
        # Statistics
        self.stats = {
            "requests": 0,
            "bytes_sent": 0,
            "bytes_received": 0,
            "errors": 0,
            "start_time": None
        }
        
        self._app = None
        self._raw_server = None
    
    @classmethod
    def from_session_file(cls, session_file: str, config: Optional[CDPProxyConfig] = None) -> 'CDPProxy':
        """Create proxy from .tokenade file."""
        from tokenade.core.importer.session_packager import SessionPackager
        packager = SessionPackager()
        session = packager.load(session_file)
        return cls(session, config)
    
    @classmethod
    def from_session_data(cls, session_data: Dict, config: Optional[CDPProxyConfig] = None) -> 'CDPProxy':
        """Create proxy from session data dictionary."""
        return cls(session_data, config)
    
    async def start(self):
        """Start the proxy server and Playwright browser."""
        if not HAS_PLAYWRIGHT:
            raise RuntimeError(
                "Playwright is required for CDP proxy. "
                "Install with: pip install playwright && playwright install chromium"
            )
        
        # Start Playwright browser
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.config.headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1920,1080",
                "--window-position=0,0",
            ]
        )
        
        # Create browser context with donor cookies
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 960},
            user_agent=(self.session.get("fingerprint") or {}).get(
                "user_agent",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        
        # Inject donor cookies
        await self._inject_cookies()
        
        # Start aiohttp server with duplicate-header tolerance
        self._app = self._create_app()
        self._app.freeze()
        server = web.Server(self._app._handle, request_factory=self._app._make_request)
        loop = asyncio.get_event_loop()
        self._raw_server = await loop.create_server(
            _LenientServerFactory(server), self.config.host, self.config.port
        )
        
        self.stats["start_time"] = time.time()
        
        # Start session auto-refresh monitor
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
            session=self.session,
            config=refresh_config,
            on_refresh=self._on_session_refresh,
        )
        await self._refresher.start()
        
        site_name = self.session.get("site_name", "unknown")
        cookies = self.session.get("cookies", [])
        tls_profile = self.session.get("tls_profile", {})
        
        # Check session health
        expiry_info = self._refresher.check_expiry()
        
        logger.info(f"CDP Proxy started on {self.config.host}:{self.config.port}")
        print(f"\n{'='*60}")
        print(f"Tokenade CDP Proxy Server")
        print(f"{'='*60}")
        print(f"Site: {site_name}")
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
        print(f"Browser: Chromium (Playwright)")
        print(f"Headless: {self.config.headless}")
        print(f"\nGUI: http://127.0.0.1:{self.config.port}")
        print(f"{'='*60}\n")
    
    async def stop(self):
        """Stop the proxy server and Playwright browser."""
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
    
    def start_extension_bridge(self, bridge_port: int = 9224):
        """Start the WebSocket bridge for browser extension communication.
        
        The bridge allows the browser extension to push cookie updates
        to the proxy without requiring a restart.
        
        Args:
            bridge_port: Port for the WebSocket bridge (default: 9224)
        """
        try:
            from tokenade.core.proxy.extension_bridge import ExtensionBridge
            
            self._extension_bridge = ExtensionBridge(
                host=self.config.host,
                port=bridge_port,
            )
            
            # Register handler for cookie updates from extension
            def on_cookie_update(data):
                if "cookies" in data:
                    self.cookie_jar.add_cookies(data["cookies"])
                    logger.info(f"Received {len(data['cookies'])} cookies from extension")
            
            self._extension_bridge.on_message("cookie_update", on_cookie_update)
            
            # Start bridge in background
            asyncio.ensure_future(self._extension_bridge.start())
            logger.info(f"Extension bridge started on ws://{self.config.host}:{bridge_port}")
            
        except ImportError:
            logger.warning("websockets not installed. Install with: pip install websockets")
        except Exception as e:
            logger.error(f"Failed to start extension bridge: {e}")
    
    async def _on_session_refresh(self, new_session: Dict):
        """Callback when session is refreshed — hot-reload cookies."""
        try:
            # Update cookie jar
            self.cookie_jar = CookieJar()
            self.cookie_jar.add_cookies(new_session.get("cookies", []))
            
            # Re-inject cookies into browser context
            if self._context:
                await self._inject_cookies()
            
            logger.info("Session hot-reloaded successfully")
        except Exception as e:
            logger.error(f"Failed to hot-reload session: {e}")
    
    async def _inject_cookies(self):
        """Inject donor cookies into the Playwright browser context."""
        cookies = self.session.get("cookies", [])
        if not cookies:
            return
        
        pw_cookies = []
        for cookie in cookies:
            pw_cookie = {
                "name": cookie.get("name", ""),
                "value": cookie.get("value", ""),
                "domain": cookie.get("domain", ""),
                "path": cookie.get("path", "/"),
            }
            
            # Map sameSite values
            same_site = cookie.get("sameSite", "").lower()
            if same_site in ("strict", "lax", "none"):
                pw_cookie["sameSite"] = same_site.capitalize()
            else:
                pw_cookie["sameSite"] = "Lax"
            
            # Set secure flag
            if cookie.get("secure"):
                pw_cookie["secure"] = True
            
            # Set httpOnly flag
            if cookie.get("httpOnly"):
                pw_cookie["httpOnly"] = True
            
            # Convert expiry (handle Firefox ms → s)
            expires = cookie.get("expires")
            if expires:
                if isinstance(expires, (int, float)) and expires > 1262304000000:
                    expires = expires / 1000
                pw_cookie["expires"] = expires
            
            # Skip __Host- cookies with domain set (invalid per spec)
            if pw_cookie["name"].startswith("__Host-") and cookie.get("domain"):
                continue
            
            pw_cookies.append(pw_cookie)
        
        if pw_cookies:
            try:
                await self._context.add_cookies(pw_cookies)
                logger.info(f"Injected {len(pw_cookies)} cookies into browser")
            except Exception as e:
                logger.warning(f"Failed to inject some cookies: {e}")
    
    async def _inject_local_storage(self, page):
        """Inject donor localStorage into a page before navigation."""
        local_storage = self.session.get("local_storage", {})
        if not local_storage:
            return
        
        try:
            # Build JS to set all localStorage items
            items = []
            for key, value in local_storage.items():
                escaped_key = key.replace("\\", "\\\\").replace("'", "\\'")
                escaped_val = value.replace("\\", "\\\\").replace("'", "\\'")
                items.append(f"localStorage.setItem('{escaped_key}', '{escaped_val}')")
            
            js = "(() => { " + "; ".join(items) + " })()"
            await page.evaluate(js)
            logger.info(f"Injected {len(items)} localStorage entries")
        except Exception as e:
            logger.warning(f"Failed to inject localStorage: {e}")
    
    def _create_app(self) -> web.Application:
        """Create aiohttp application with routes."""
        app = web.Application()
        
        # Service worker cleanup — unregisters any cached old SW
        app.router.add_get("/_tokenade_sw.js", self._handle_old_sw)
        
        # Legacy proxy routes — redirect to GUI
        app.router.add_get("/proxy", self._handle_legacy_redirect)
        app.router.add_get("/proxy/", self._handle_legacy_redirect)
        
        # GUI routes
        app.router.add_get("/", self._handle_gui)
        app.router.add_get("/status", self._handle_status)
        app.router.add_get("/stats", self._handle_stats)
        app.router.add_get("/session/status", self._handle_session_status)
        app.router.add_post("/session/refresh", self._handle_session_refresh)
        app.router.add_post("/browse", self._handle_browse_post)
        app.router.add_get("/page/{page_id}", self._handle_page)
        
        # Reverse proxy catch-all (must be last)
        app.router.add_route("*", "/{path:.*}", self._handle_proxy)
        
        return app
    
    async def _handle_old_sw(self, request: web.Request) -> web.Response:
        """Return a service worker that unregisters itself (clears old cached SW)."""
        sw_code = """
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', () => {
    self.registration.unregister();
    clients.matchAll().then(clients => clients.forEach(c => c.navigate(c.url)));
});
"""
        return web.Response(text=sw_code, content_type='application/javascript')
    
    async def _handle_legacy_redirect(self, request: web.Request) -> web.Response:
        """Redirect /proxy to / (clears old cached proxy URLs)."""
        raise web.HTTPFound("/")
    
    async def _handle_gui(self, request: web.Request) -> web.Response:
        """Serve the GUI landing page."""
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
        .browse-form {{
            display: flex; gap: 10px; margin: 20px 0;
        }}
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
        if ('serviceWorker' in navigator) {{
            navigator.serviceWorker.getRegistrations().then(regs => {{
                regs.forEach(r => {{ r.unregister(); }});
            }});
        }}
        async function updateStats() {{
            try {{
                const resp = await fetch('/stats');
                const data = await resp.json();
                document.getElementById('requests').textContent = data.requests || 0;
                document.getElementById('bytes-in').textContent = formatBytes(data.bytes_received || 0);
                document.getElementById('bytes-out').textContent = formatBytes(data.bytes_sent || 0);
            }} catch(e) {{}}
        }}
        async function updateSessionStatus() {{
            try {{
                const resp = await fetch('/session/status');
                const data = await resp.json();
                const el = document.getElementById('expiry-info');
                if (data.expired_count > 0) {{
                    el.innerHTML = '<span style="color: #ff6b6b;">⚠️ ' + data.expired_count + ' expired cookies</span>' +
                        '<button onclick="refreshSession()" style="margin-left: 10px; padding: 4px 8px; background: #ff6b6b; color: #fff; border: none; border-radius: 4px; cursor: pointer;">Refresh</button>';
                }} else if (data.critical_count > 0) {{
                    el.innerHTML = '<span style="color: #ffa500;">⏰ ' + data.critical_count + ' cookies expiring soon (' + (data.next_expiry_human || 'unknown') + ')</span>' +
                        '<button onclick="refreshSession()" style="margin-left: 10px; padding: 4px 8px; background: #ffa500; color: #000; border: none; border-radius: 4px; cursor: pointer;">Refresh</button>';
                }} else if (data.expiring_soon_count > 0) {{
                    el.innerHTML = '<span style="color: #888;">📅 ' + data.expiring_soon_count + ' cookies expiring in ' + data.next_expiry_human + '</span>';
                }} else {{
                    el.innerHTML = '<span style="color: #00ff88;">✓ All cookies valid</span>';
                }}
            }} catch(e) {{}}
        }}
        async function refreshSession() {{
            try {{
                const resp = await fetch('/session/refresh', {{ method: 'POST' }});
                const data = await resp.json();
                if (data.status === 'refreshed') {{
                    updateSessionStatus();
                }}
            }} catch(e) {{}}
        }}
        function formatBytes(bytes) {{
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
            return (bytes/(1024*1024)).toFixed(1) + ' MB';
        }}
        setInterval(updateStats, 2000);
        setInterval(updateSessionStatus, 60000);
        updateStats();
        updateSessionStatus();
    </script>
</body>
</html>"""
        return web.Response(text=gui_html, content_type='text/html')
    
    async def _handle_browse_post(self, request: web.Request) -> web.Response:
        """Handle POST to /browse - create a new page and navigate."""
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
            
            if not _is_safe_url(url):
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
        except Exception as e:
            logger.exception("Failed to process browse request")
            return web.Response(text="Failed to process request", status=500)
    
    async def _navigate_page(self, page_id: str, url: str):
        """Navigate an already-created page to the target URL."""
        try:
            page = self._pages.get(page_id)
            if not page:
                return
            
            await page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout * 1000)
            
            # Inject localStorage after navigation (needs correct origin)
            local_storage = self.session.get("local_storage", {})
            if local_storage:
                await self._inject_local_storage(page)
                await page.reload(wait_until="domcontentloaded", timeout=self.config.timeout * 1000)
            
            logger.info(f"Page {page_id} loaded: {url}")
            
        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {e}")
    
    def _cleanup_expired_pages(self):
        """Remove pages older than TTL."""
        now = time.time()
        expired = [pid for pid, meta in self._page_meta.items()
                   if now - meta["created"] > self._page_ttl]
        for pid in expired:
            asyncio.create_task(self._close_page(pid))
    
    async def _close_page(self, page_id: str):
        """Safely close a page and remove from tracking."""
        page = self._pages.pop(page_id, None)
        self._page_meta.pop(page_id, None)
        if page:
            try:
                await page.close()
            except Exception:
                pass
    
    async def _handle_route(self, route):
        """
        Intercept ALL requests from the browser and forward via curl-cffi.
        
        This is the core of the CDP proxy. Every request the browser makes
        (navigation, CSS, JS, fonts, images, API calls, analytics, etc.)
        is intercepted and forwarded through curl-cffi with the donor's
        TLS fingerprint and cookies.
        """
        request = route.request
        url = request.url
        method = request.method
        headers = dict(request.headers)
        
        # Skip internal requests
        if url.startswith("data:") or url.startswith("about:"):
            await route.continue_()
            return
        
        self.stats["requests"] += 1
        
        try:
            logger.debug(f"Route: {method} {url}")
            
            # Safely extract POST body (may be binary/compressed)
            body = None
            try:
                body = request.post_data
            except (UnicodeDecodeError, ValueError):
                try:
                    post_data_buffer = request.post_data_buffer
                    if post_data_buffer:
                        import base64 as b64
                        body = b64.b64encode(post_data_buffer).decode("ascii")
                except Exception:
                    pass
            
            # Forward via curl-cffi with donor TLS fingerprint
            response = await self._forward_via_curl_cffi(
                method=method,
                url=url,
                headers=headers,
                body=body
            )
            
            if response is None:
                await route.abort()
                return
            
            self.stats["bytes_received"] += len(response.body)
            
            # Extract raw headers from response
            raw_headers = response.headers
            
            # Extract Set-Cookie from response and update our cookie jar
            set_cookie_headers = []
            if isinstance(raw_headers, dict):
                sc = raw_headers.get("set-cookie", raw_headers.get("Set-Cookie"))
                if sc:
                    set_cookie_headers = [sc] if isinstance(sc, str) else sc
            elif isinstance(raw_headers, list):
                for item in raw_headers:
                    if isinstance(item, (list, tuple)) and len(item) == 2:
                        if item[0].lower() == "set-cookie":
                            set_cookie_headers.append(item[1])
                    elif isinstance(item, dict):
                        if item.get("name", "").lower() == "set-cookie":
                            set_cookie_headers.append(item.get("value", ""))
            
            if set_cookie_headers:
                parsed_url = urlparse(url)
                for sc in set_cookie_headers:
                    try:
                        cookie_parts = sc.split(";")[0].strip()
                        if "=" in cookie_parts:
                            cname, cvalue = cookie_parts.split("=", 1)
                            new_cookie = {
                                "name": cname.strip(),
                                "value": cvalue.strip(),
                                "domain": parsed_url.hostname or "",
                                "path": "/",
                                "secure": parsed_url.scheme == "https",
                            }
                            self.cookie_jar.add_cookie(new_cookie)
                    except Exception:
                        pass
            
            # Fulfill the route with the response
            resp_headers = {}
            # curl-cffi may return headers as list of tuples or dict
            if isinstance(raw_headers, dict):
                header_items = raw_headers.items()
            elif isinstance(raw_headers, list):
                header_items = raw_headers
            else:
                header_items = []
            
            skip = {
                "content-security-policy",
                "x-frame-options",
                "strict-transport-security",
                "content-encoding",
                "transfer-encoding",
            }
            
            for item in header_items:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    key, value = item
                elif isinstance(item, dict):
                    key = item.get("name", "")
                    value = item.get("value", "")
                else:
                    continue
                
                if key.lower() in skip:
                    continue
                resp_headers[str(key)] = str(value)
            
            await route.fulfill(
                status=response.status,
                headers=resp_headers,
                body=response.body
            )
            
        except Exception as e:
            logger.error(f"Route error for {url}: {e}")
            self.stats["errors"] += 1
            try:
                await route.abort()
            except Exception:
                pass
    
    async def _forward_via_curl_cffi(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        body: Optional[str] = None,
    ):
        """
        Forward request via curl-cffi with donor TLS fingerprint.
        
        Falls back to aiohttp if curl-cffi fails.
        """
        try:
            from curl_cffi import requests as curl_requests
            
            # Build donor-matched headers
            donor_headers = self.fingerprint.get_headers(url, None, method)
            
            # Override with request headers (browser's headers take priority for content negotiation)
            for key, value in headers.items():
                key_lower = key.lower()
                # Skip headers that curl-cffi manages
                if key_lower in ("host", "connection", "proxy-connection"):
                    continue
                donor_headers[key] = value
            
            # Inject donor cookies
            cookies = self.cookie_jar.get_for_request(url)
            if cookies:
                donor_headers["cookie"] = cookies
                if "chatgpt" in url:
                    logger.info(f"[COOKIE] {url[:80]} -> {len(cookies)} chars")
            else:
                if "chatgpt" in url:
                    logger.warning(f"[COOKIE] NO cookies for {url[:80]}")
            
            # Remove accept-encoding (curl-cffi handles decompression)
            donor_headers.pop("accept-encoding", None)
            
            self.stats["bytes_sent"] += len(body) if body else 0
            
            # Make the request with TLS fingerprint matching
            response = await asyncio.to_thread(
                curl_requests.request,
                method=method,
                url=url,
                headers=donor_headers,
                data=body,
                impersonate=self.session.get("tls_profile", {}).get("impersonate", "chrome120"),
                timeout=self.config.timeout,
                allow_redirects=True,
            )
            
            # Normalize headers to dict
            raw_headers = response.headers
            if isinstance(raw_headers, dict):
                headers_dict = raw_headers
            elif isinstance(raw_headers, list):
                headers_dict = {}
                for item in raw_headers:
                    if isinstance(item, (list, tuple)) and len(item) == 2:
                        headers_dict[item[0]] = item[1]
            else:
                headers_dict = dict(raw_headers) if raw_headers else {}
            
            return type('Response', (), {
                'status': response.status_code,
                'headers': headers_dict,
                'body': response.content,
            })()
            
        except Exception as e:
            logger.debug(f"curl-cffi failed for {url}: {e}")
            
            # Fallback to aiohttp
            return await self._forward_via_aiohttp(method, url, headers, body)
    
    async def _forward_via_aiohttp(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        body: Optional[str] = None,
    ):
        """Fallback: forward via aiohttp. Uses shared pool if available."""
        try:
            # Use shared session from MultiSiteProxy if available
            if self._shared_http_session and not self._shared_http_session.closed:
                http_session = self._shared_http_session
            else:
                async with self._session_lock:
                    if self._http_session is None or self._http_session.closed:
                        connector = aiohttp.TCPConnector(
                            ssl=False,
                            limit=100,
                            limit_per_host=30,
                            enable_cleanup_closed=True
                        )
                        timeout = aiohttp.ClientTimeout(total=self.config.timeout, connect=10)
                        self._http_session = aiohttp.ClientSession(
                            connector=connector,
                            timeout=timeout,
                            auto_decompress=False
                        )
                http_session = self._http_session
            
            # Build donor-matched headers
            donor_headers = self.fingerprint.get_headers(url, None, method)
            for key, value in headers.items():
                key_lower = key.lower()
                if key_lower in ("host", "connection", "proxy-connection"):
                    continue
                donor_headers[key] = value
            
            cookies = self.cookie_jar.get_for_request(url)
            if cookies:
                donor_headers["cookie"] = cookies
            
            donor_headers.pop("accept-encoding", None)
            
            async with http_session.request(
                method=method,
                url=url,
                headers=donor_headers,
                data=body,
                allow_redirects=True,
                ssl=False
            ) as resp:
                resp_body = await resp.read()
                return type('Response', (), {
                    'status': resp.status,
                    'headers': dict(resp.headers),
                    'body': resp_body,
                })()
                
        except Exception as e:
            logger.error(f"aiohttp fallback also failed for {url}: {e}")
            return None
    
    async def _handle_session_status(self, request: web.Request) -> web.Response:
        """Return session expiry status as JSON."""
        if not self._refresher:
            return web.json_response({"error": "Refresh monitor not active"}, status=503)
        
        status = self._refresher.get_status()
        return web.json_response(status)
    
    async def _handle_session_refresh(self, request: web.Request) -> web.Response:
        """Trigger a manual session refresh from source browser."""
        if not self._refresher:
            return web.json_response({"error": "Refresh monitor not active"}, status=503)
        
        try:
            await self._refresher._attempt_refresh()
            return web.json_response({
                "status": "refreshed",
                "cookies": len(self.session.get("cookies", [])),
            })
        except Exception as e:
            return web.json_response({"error": "Refresh failed"}, status=500)
    
    async def _handle_page(self, request: web.Request) -> web.Response:
        """Serve a page that displays the browser content via iframe."""
        page_id = request.match_info["page_id"]
        
        page = self._pages.get(page_id)
        if not page:
            return web.Response(
                text="<html><body><h1>Page not found</h1><p>The page may still be loading.</p></body></html>",
                content_type="text/html",
                status=404
            )
        
        try:
            # Get the current URL of the page
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
        .info {{
            padding: 20px; color: #888;
        }}
        .info p {{ margin: 5px 0; }}
        .info a {{ color: #00ff88; }}
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
        async function refreshScreenshot() {{
            try {{
                const resp = await fetch('/api/page/{page_id}/screenshot');
                if (resp.ok) {{
                    const blob = await resp.blob();
                    const url = URL.createObjectURL(blob);
                    document.getElementById('content').innerHTML = '';
                    const img = document.createElement('img');
                    img.src = url;
                    img.className = 'screenshot-container';
                    document.getElementById('content').appendChild(img);
                }}
            }} catch(e) {{
                console.error('Screenshot refresh failed:', e);
            }}
        }}
        
        setTimeout(refreshScreenshot, 2000);
        setInterval(refreshScreenshot, 5000);
    </script>
</body>
</html>"""
            return web.Response(text=page_html, content_type='text/html')
            
        except Exception:
            return web.Response(text="Error loading page", status=500)
    
    async def _handle_proxy(self, request: web.Request) -> web.Response:
        """Handle reverse proxy requests."""
        self.stats["requests"] += 1
        
        path = request.path
        if path.startswith("/api/"):
            return await self._handle_api(request)
        
        # Redirect old /proxy/* routes to root
        if path.startswith("/proxy"):
            raise web.HTTPFound("/")
        
        # Build target URL from request
        target_url = self._build_target_url(request)
        if not target_url:
            return web.Response(text="Could not determine target URL", status=400)
        
        if not _is_safe_url(target_url):
            return web.Response(text="URL blocked: internal/private network target", status=403)
        
        try:
            body = await request.read() if request.method in ("POST", "PUT", "PATCH") else None
            
            response = await self._forward_via_curl_cffi(
                method=request.method,
                url=target_url,
                headers=dict(request.headers),
                body=body
            )
            
            if response is None:
                return web.Response(text="Proxy error", status=502)
            
            self.stats["bytes_received"] += len(response.body)
            
            # Filter response headers
            resp_headers = {}
            for key, value in response.headers.items():
                if key.lower() in (
                    "content-security-policy",
                    "x-frame-options",
                    "strict-transport-security",
                    "content-encoding",
                    "transfer-encoding",
                ):
                    continue
                resp_headers[key] = value
            
            return web.Response(
                status=response.status,
                headers=resp_headers,
                body=response.body
            )
            
        except Exception as e:
            logger.error(f"Proxy error: {e}")
            self.stats["errors"] += 1
            return web.Response(text=f"Proxy error: {e}", status=502)
    
    async def _handle_api(self, request: web.Request) -> web.Response:
        """Handle API requests."""
        path = request.path
        
        if path == "/api/status":
            return await self._handle_status(request)
        elif path == "/api/stats":
            return await self._handle_stats(request)
        elif path.startswith("/api/page/") and path.endswith("/html"):
            return await self._handle_page_html(request)
        elif path.startswith("/api/page/") and path.endswith("/screenshot"):
            return await self._handle_page_screenshot(request)
        
        return web.Response(text="Not found", status=404)
    
    async def _handle_page_html(self, request: web.Request) -> web.Response:
        """Return the rendered HTML of a page."""
        parts = request.path.split("/")
        if len(parts) >= 4:
            page_id = parts[3]
        else:
            return web.Response(text="Invalid page ID", status=400)
        
        page = self._pages.get(page_id)
        if not page:
            return web.Response(text="Page not found", status=404)
        
        try:
            html = await page.content()
            if page.url and not page.url.startswith("about:"):
                parsed = urlparse(page.url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                if "<head>" in html:
                    html = html.replace("<head>", f"<head><base href=\"{base_url}/\">", 1)
                elif "<HEAD>" in html:
                    html = html.replace("<HEAD>", f"<HEAD><base href=\"{base_url}/\">", 1)
            return web.Response(text=html, content_type='text/html')
        except Exception as e:
            return web.Response(text=f"Error getting page content: {e}", status=500)
    
    async def _handle_page_screenshot(self, request: web.Request) -> web.Response:
        """Return a screenshot of a page as PNG."""
        parts = request.path.split("/")
        if len(parts) >= 4:
            page_id = parts[3]
        else:
            return web.Response(text="Invalid page ID", status=400)
        
        page = self._pages.get(page_id)
        if not page:
            return web.Response(text="Page not found", status=404)
        
        try:
            screenshot = await page.screenshot(type="png")
            return web.Response(body=screenshot, content_type='image/png')
        except Exception as e:
            return web.Response(text=f"Error taking screenshot: {e}", status=500)
    
    async def _handle_status(self, request: web.Request) -> web.Response:
        """Return proxy status as JSON."""
        return web.json_response({
            "status": "running",
            "site": self.session.get("site_name", "unknown"),
            "cookies": len(self.cookie_jar.to_list()),
            "tls_profile": self.session.get("tls_profile", {}),
            "uptime": time.time() - (self.stats["start_time"] or time.time())
        })
    
    async def _handle_stats(self, request: web.Request) -> web.Response:
        """Return proxy statistics as JSON."""
        return web.json_response(self.stats)
    
    def _build_target_url(self, request: web.Request) -> Optional[str]:
        """Build target URL from request."""
        path = request.path
        
        if path.startswith(("http://", "https://")):
            return path
        
        host = request.headers.get("Host") or request.headers.get(":authority")
        
        if host and host not in (self.config.host, f"{self.config.host}:{self.config.port}"):
            scheme = "https" if ":443" in host or request.headers.get(":scheme") == "https" else "http"
            return f"{scheme}://{host}{path}"
        
        referer = request.headers.get("Referer", "")
        for page_id, page in self._pages.items():
            if f"/page/{page_id}" in referer and page.url:
                parsed = urlparse(page.url)
                return f"{parsed.scheme}://{parsed.netloc}{path}"
        
        return None
    
    def _get_site_url(self) -> str:
        """Get the default URL for the session's site."""
        site_name = self.session.get("site_name", "unknown")
        if site_name and site_name != "unknown":
            # Try to infer from cookie domains
            cookies = self.session.get("cookies", [])
            domains = set()
            for c in cookies:
                d = c.get("domain", "")
                if d:
                    domains.add(d.lstrip("."))
            # Find most specific domain matching site_name
            for d in sorted(domains, key=len):
                if site_name.lower() in d.lower():
                    return f"https://{d}"
            # Fallback: use first non-empty domain
            if domains:
                return f"https://{min(domains, key=len)}"
            return f"https://www.{site_name}.com"
        return "https://example.com"
    
    def run(self):
        """Run the proxy server (blocking)."""
        asyncio.run(self._run_async())
    
    async def _run_async(self):
        """Run the proxy server asynchronously."""
        await self.start()
        
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down CDP proxy...")
        finally:
            await self.stop()


def create_cdp_proxy_from_file(session_file: str, port: int = 9222, headless: bool = True) -> CDPProxy:
    """
    Convenience function to create a CDP proxy from a session file.
    
    Args:
        session_file: Path to .tokenade file
        port: Port to listen on
        headless: Run browser in headless mode
        
    Returns:
        Configured CDPProxy
    """
    config = CDPProxyConfig(port=port, headless=headless)
    return CDPProxy.from_session_file(session_file, config)
