"""
Tokenade Proxy Server — Slim orchestrator.

Imports helper logic from server_utils, server_routing, server_gui.
Defines ProxyConfig, TokenadeProxy, and re-exports ProxyResponse.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional, Dict
from urllib.parse import urlparse

from aiohttp import web

from tokenade.core.runtime.engine import CookieJar, FingerprintMatcher
from tokenade.core.runtime.tls_matcher import create_tls_matcher

from tokenade.core.proxy.server_utils import (
    ProxyResponse,
    build_target_url,
    filter_response_headers,
    rewrite_urls,
    rewrite_html_for_proxy,
    rewrite_js_for_proxy,
    rewrite_css_for_proxy,
)
from tokenade.core.proxy.server_routing import forward_request
from tokenade.core.proxy.server_gui import handle_gui, handle_browse_page
from tokenade.core.proxy.cdp_stealth import is_safe_url

_is_safe_url = is_safe_url  # alias for test-patching compatibility

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    """Configuration for the proxy server."""
    port: int = 9222
    host: str = "127.0.0.1"
    gui_mode: bool = True
    auto_refresh: bool = False
    verbose: bool = False


class TokenadeProxy:
    """
    Local fingerprint-matched proxy server.

    Loads a .tokenade file and serves requests with the donor's
    fingerprint, cookies, and TLS profile.

    Usage:
        proxy = TokenadeProxy.from_session_file("chatgpt.tokenade")
        proxy.start()
    """

    def __init__(self, session_package: Dict, config: Optional[ProxyConfig] = None):
        self.config = config or ProxyConfig()
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

        self.stats = {
            "requests": 0,
            "bytes_sent": 0,
            "bytes_received": 0,
            "errors": 0,
            "start_time": None,
        }

        self._app = None
        self._runner = None
        self._site = None
        self._target_url = None
        self._proxy_active = False
        self._http_session = None

    @classmethod
    def from_session_file(cls, session_file: str, config: Optional[ProxyConfig] = None) -> "TokenadeProxy":
        from tokenade.core.importer.session_packager import SessionPackager
        packager = SessionPackager()
        session = packager.load(session_file)
        return cls(session, config)

    @classmethod
    def from_session_data(cls, session_data: Dict, config: Optional[ProxyConfig] = None) -> "TokenadeProxy":
        return cls(session_data, config)

    # ── App creation ──────────────────────────────────────────────

    def _create_app(self) -> web.Application:
        app = web.Application()

        if self.config.gui_mode:
            app.router.add_get("/", self._handle_gui)
            app.router.add_get("/status", self._handle_status)
            app.router.add_get("/stats", self._handle_stats)
            app.router.add_get("/proxy", self._handle_site_proxy_entry)
            app.router.add_post("/browse", self._handle_browse_post)
            app.router.add_get("/browse", self._handle_browse)

        app.router.add_get("/_tokenade_sw.js", self._handle_service_worker)
        app.router.add_route("*", "/{path:.*}", self._handle_proxy)

        return app

    # ── GUI handlers (delegate to helpers) ────────────────────────

    async def _handle_gui(self, request: web.Request) -> web.Response:
        return await handle_gui(self, request)

    async def _handle_browse(self, request: web.Request) -> web.StreamResponse:
        url = request.query.get("url")
        if not url:
            return await handle_browse_page(self, request)

        self.stats["requests"] += 1
        try:
            logger.debug(f"Browsing: {url}")
            response = await forward_request(
                self, method="GET", url=url, headers={}, body=None,
                referer=None, follow_redirects=True,
            )
            body = response.body
            if body and b"<html" in body[:1000].lower():
                body = rewrite_urls(body, response.url)
            resp_headers = filter_response_headers(response.headers)
            return web.Response(status=response.status, headers=resp_headers, body=body)
        except Exception as e:
            logger.error(f"Browse error: {e}")
            self.stats["errors"] += 1
            import html as html_module
            safe_msg = html_module.escape(str(e))
            return web.Response(
                text=f"<html><body><h1>Proxy Error</h1><p>{safe_msg}</p>"
                     f"<p><a href='/'>Back to Proxy</a></p></body></html>",
                content_type="text/html", status=502,
            )

    # ── Browse POST ───────────────────────────────────────────────

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
            self._target_url = url
            self._proxy_active = True
            raise web.HTTPFound("/proxy")
        except web.HTTPFound:
            raise
        except Exception:
            return web.Response(text="Failed to process request", status=500)

    # ── Site proxy entry ──────────────────────────────────────────

    async def _handle_site_proxy_entry(self, request: web.Request) -> web.StreamResponse:
        if not self._target_url:
            return web.Response(text="No target URL set. Use the browse page to set one.", status=400)
        if request.path == "/proxy":
            raise web.HTTPFound("/proxy/")

        parsed_target = urlparse(self._target_url)
        request_path = request.path[len("/proxy"):] or "/"
        target_url = f"{parsed_target.scheme}://{parsed_target.hostname}"
        if parsed_target.port and parsed_target.port != (443 if parsed_target.scheme == "https" else 80):
            target_url += f":{parsed_target.port}"
        target_url += request_path
        if request.query_string:
            target_url += f"?{request.query_string}"

        self.stats["requests"] += 1
        try:
            logger.debug(f"Site proxy: {request.method} {target_url}")
            response = await forward_request(
                self, method=request.method, url=target_url,
                headers=dict(request.headers),
                body=await request.read() if request.method in ("POST", "PUT", "PATCH") else None,
                referer=self._extract_referer(request), follow_redirects=True,
            )
            self.stats["bytes_received"] += len(response.body)
            resp_headers = filter_response_headers(response.headers)
            content_type = resp_headers.get("content-type", "")
            body = response.body
            if "text/html" in content_type:
                body = rewrite_html_for_proxy(body, target_url)
            elif "javascript" in content_type or "text/javascript" in content_type:
                body = rewrite_js_for_proxy(body, target_url)
            elif "text/css" in content_type:
                body = rewrite_css_for_proxy(body, target_url)
            return web.Response(status=response.status, headers=resp_headers, body=body)
        except Exception as e:
            logger.error(f"Site proxy error: {e}")
            self.stats["errors"] += 1
            return web.Response(
                text=f"<html><body><h1>Proxy Error</h1><p>{e}</p></body></html>",
                content_type="text/html", status=502,
            )

    # ── Service worker ────────────────────────────────────────────

    async def _handle_service_worker(self, request: web.Request) -> web.Response:
        sw_code = """
const PROXY_BASE = '/proxy';
const BYPASS_PATHS = ['/_tokenade_sw.js', '/browse', '/status', '/stats'];

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    if (!url.protocol.startsWith('http')) return;
    if (BYPASS_PATHS.some(p => url.pathname === p || url.pathname.startsWith(p + '?'))) return;
    if (url.pathname.startsWith(PROXY_BASE + '/')) return;

    let proxyPath;
    if (url.hostname === self.location.hostname) {
        proxyPath = PROXY_BASE + url.pathname + url.search + url.hash;
    } else {
        proxyPath = PROXY_BASE + '/' + url.hostname + url.pathname + url.search + url.hash;
    }

    const proxyUrl = new URL(proxyPath, self.location.origin);

    event.respondWith(
        fetch(new Request(proxyUrl.toString(), {
            method: event.request.method,
            headers: event.request.headers,
            body: event.request.body,
            mode: 'cors',
            credentials: 'include'
        })).catch(err => {
            console.warn('[Tokenade] Proxy fetch failed:', err.message);
            return new Response('Proxy error: ' + err.message, { status: 502 });
        })
    );
});

self.addEventListener('install', (event) => { self.skipWaiting(); });
self.addEventListener('activate', (event) => { event.waitUntil(clients.claim()); });
"""
        return web.Response(text=sw_code, content_type='application/javascript')

    # ── Site proxy sub-resource ───────────────────────────────────

    async def _handle_site_proxy_subresource(self, request: web.Request) -> web.StreamResponse:
        parsed_target = urlparse(self._target_url)
        request_path = request.path[len("/proxy"):] or "/"
        target_url = f"{parsed_target.scheme}://{parsed_target.hostname}"
        if parsed_target.port and parsed_target.port != (443 if parsed_target.scheme == "https" else 80):
            target_url += f":{parsed_target.port}"
        target_url += request_path
        if request.query_string:
            target_url += f"?{request.query_string}"

        logger.debug(f"Site subresource: {request.method} {target_url}")

        target_origin = f"{parsed_target.scheme}://{parsed_target.hostname}"
        if parsed_target.port:
            target_origin += f":{parsed_target.port}"

        target_headers = {}
        for key, value in request.headers.items():
            if key.lower() in ("host", "origin", "referer", "x-forwarded-for", "x-real-ip"):
                continue
            target_headers[key] = value
        target_headers["Host"] = parsed_target.hostname
        if parsed_target.port and parsed_target.port != (443 if parsed_target.scheme == "https" else 80):
            target_headers["Host"] += f":{parsed_target.port}"
        target_headers["Origin"] = target_origin
        target_headers["Referer"] = f"{target_origin}/"

        try:
            response = await forward_request(
                self, method=request.method, url=target_url,
                headers=target_headers,
                body=await request.read() if request.method in ("POST", "PUT", "PATCH") else None,
                referer=f"{target_origin}/", follow_redirects=True,
            )
            self.stats["bytes_received"] += len(response.body)
            resp_headers = filter_response_headers(response.headers)
            content_type = resp_headers.get("content-type", "")
            body = response.body
            if "text/html" in content_type:
                body = rewrite_html_for_proxy(body, target_url)
            elif "javascript" in content_type or "text/javascript" in content_type:
                body = rewrite_js_for_proxy(body, target_url)
            elif "text/css" in content_type:
                body = rewrite_css_for_proxy(body, target_url)
            return web.Response(status=response.status, headers=resp_headers, body=body)
        except Exception as e:
            logger.error(f"Site subresource error: {e}")
            self.stats["errors"] += 1
            return web.Response(text="Failed to fetch resource", status=502)

    # ── Catch-all proxy handler ───────────────────────────────────

    async def _handle_proxy(self, request: web.Request) -> web.StreamResponse:
        self.stats["requests"] += 1
        path = request.path
        if self._proxy_active and self._target_url and path.startswith("/proxy/"):
            return await self._handle_site_proxy_subresource(request)

        target_url = build_target_url(request)
        if not target_url:
            return web.Response(text="Could not determine target URL", status=400)
        if not is_safe_url(target_url):
            return web.Response(text="URL blocked: internal/private network target", status=403)

        logger.debug(f"Proxy: {request.method} {target_url}")
        try:
            body = await request.read()
            response = await forward_request(
                self, method=request.method, url=target_url,
                headers=dict(request.headers), body=body,
                referer=self._extract_referer(request),
            )
            self.stats["bytes_received"] += len(response.body)
            resp_headers = filter_response_headers(response.headers)
            return web.Response(status=response.status, headers=resp_headers, body=response.body)
        except Exception as e:
            logger.error(f"Proxy error: {e}")
            self.stats["errors"] += 1
            return web.Response(text=f"Proxy error: {e}", status=502)

    # ── Status / stats ────────────────────────────────────────────

    async def _handle_status(self, request: web.Request) -> web.Response:
        return web.json_response({
            "status": "running",
            "site": self.session.get("site_name", "unknown"),
            "cookies": len(self.cookie_jar.to_list()),
            "tls_profile": self.session.get("tls_profile", {}),
            "uptime": time.time() - (self.stats["start_time"] or time.time()),
        })

    async def _handle_stats(self, request: web.Request) -> web.Response:
        return web.json_response(self.stats)

    # ── Helpers ───────────────────────────────────────────────────

    def _extract_referer(self, request: web.Request) -> Optional[str]:
        return request.headers.get("Referer") or request.headers.get("referer")

    # ── Forward request (delegates to helper) ─────────────────────

    async def _forward_request(self, method, url, headers, body, referer=None,
                               follow_redirects=True, max_redirects=10) -> ProxyResponse:
        return await forward_request(
            self, method=method, url=url, headers=headers, body=body,
            referer=referer, follow_redirects=follow_redirects, max_redirects=max_redirects,
        )

    # ── Lifecycle ─────────────────────────────────────────────────

    async def start(self):
        self._app = self._create_app()
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.config.host, self.config.port)
        await self._site.start()
        self.stats["start_time"] = time.time()

        logger.info(f"Tokenade Proxy started on {self.config.host}:{self.config.port}")
        print(f"\n{'=' * 60}")
        print("Tokenade Proxy Server")
        print(f"{'=' * 60}")
        print(f"Site: {self.session.get('site_name', 'unknown')}")
        print(f"Cookies: {len(self.cookie_jar.to_list())}")
        print(f"TLS Profile: {self.session.get('tls_profile', {}).get('impersonate', 'unknown')}")
        print(f"\nGUI: http://127.0.0.1:{self.config.port}")
        print(f"Proxy: http://127.0.0.1:{self.config.port}")
        print("\nTo use as HTTP proxy:")
        print(f"  export HTTP_PROXY=http://127.0.0.1:{self.config.port}")
        print(f"  export HTTPS_PROXY=http://127.0.0.1:{self.config.port}")
        print(f"{'=' * 60}\n")

    async def stop(self):
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
        if self._runner:
            await self._runner.cleanup()
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
            print("\nShutting down proxy...")
        finally:
            await self.stop()


def create_proxy_from_file(session_file: str, port: int = 9222, gui: bool = True) -> TokenadeProxy:
    """Convenience function to create and configure a proxy."""
    config = ProxyConfig(port=port, gui_mode=gui)
    return TokenadeProxy.from_session_file(session_file, config)
