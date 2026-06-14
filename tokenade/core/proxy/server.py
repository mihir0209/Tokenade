"""
Tokenade Proxy Server - Local fingerprint-matched HTTP/HTTPS proxy.

Intercepts requests from a client browser and forwards them through
a TLS-matched connection with the donor's fingerprint and cookies.

Modes:
- HTTP_PROXY mode: Set HTTP_PROXY=http://127.0.0.1:9222
- GUI mode: Open http://127.0.0.1:9222 in browser to browse as donor

Architecture:
  Client Browser -> Local Proxy (127.0.0.1:9222) -> curl-cffi (JA3 matched) -> Remote Server
"""

import asyncio
import html as html_module
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Tuple
from urllib.parse import urlparse, quote

import aiohttp
from aiohttp import web

from tokenade.core.runtime.engine import CookieJar, FingerprintMatcher
from tokenade.core.runtime.tls_matcher import TLSMatcher, create_tls_matcher
from tokenade.core.proxy.cdp_proxy import _is_safe_url

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    """Configuration for the proxy server."""
    port: int = 9222
    host: str = "127.0.0.1"
    gui_mode: bool = True
    auto_refresh: bool = False
    verbose: bool = False


@dataclass
class ProxyResponse:
    """Simple response container from forwarded request."""
    status: int
    headers: Dict[str, str]
    body: bytes
    url: str


class TokenadeProxy:
    """
    Local fingerprint-matched proxy server.
    
    Loads a .tokenade file and serves requests with the donor's
    fingerprint, cookies, and TLS profile.
    
    Usage:
        proxy = TokenadeProxy.from_session("chatgpt.tokenade")
        proxy.start()  # Opens browser to localhost:9222
    """
    
    def __init__(self, session_package: Dict, config: Optional[ProxyConfig] = None):
        """
        Initialize proxy from session package.
        
        Args:
            session_package: .tokenade session dictionary
            config: Proxy configuration
        """
        self.config = config or ProxyConfig()
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
        
        # Request statistics
        self.stats = {
            "requests": 0,
            "bytes_sent": 0,
            "bytes_received": 0,
            "errors": 0,
            "start_time": None
        }
        
        self._app = None
        self._runner = None
        self._site = None
        self._target_url = None  # Current browse target
        self._proxy_active = False  # True when acting as reverse proxy for a site
        self._http_session = None  # Persistent aiohttp session with connection pooling
    
    @classmethod
    def from_session_file(cls, session_file: str, config: Optional[ProxyConfig] = None) -> 'TokenadeProxy':
        """
        Create proxy from .tokenade file.
        
        Args:
            session_file: Path to .tokenade file
            config: Proxy configuration
            
        Returns:
            Configured TokenadeProxy
        """
        from tokenade.core.importer.session_packager import SessionPackager
        
        packager = SessionPackager()
        session = packager.load(session_file)
        
        return cls(session, config)
    
    @classmethod
    def from_session_data(cls, session_data: Dict, config: Optional[ProxyConfig] = None) -> 'TokenadeProxy':
        """
        Create proxy from session data dictionary.
        
        Args:
            session_data: Session dictionary
            config: Proxy configuration
            
        Returns:
            Configured TokenadeProxy
        """
        return cls(session_data, config)
    
    def _create_app(self) -> web.Application:
        """Create aiohttp application with routes."""
        app = web.Application()
        
        # GUI routes
        if self.config.gui_mode:
            app.router.add_get("/", self._handle_gui)
            app.router.add_get("/status", self._handle_status)
            app.router.add_get("/stats", self._handle_stats)
            app.router.add_get("/proxy", self._handle_site_proxy_entry)
            app.router.add_post("/browse", self._handle_browse_post)
            app.router.add_get("/browse", self._handle_browse)
        
        # Service worker for intercepting browser requests
        app.router.add_get("/_tokenade_sw.js", self._handle_service_worker)
        
        # Proxy catch-all (must be last)
        app.router.add_route("*", "/{path:.*}", self._handle_proxy)
        
        return app
    
    async def _handle_gui(self, request: web.Request) -> web.Response:
        """Serve the GUI landing page."""
        site_name = html_module.escape(self.session.get("site_name", "unknown"))
        source_device = self.session.get("source_device", {})
        browser = html_module.escape(source_device.get("browser", "unknown"))
        platform = html_module.escape(source_device.get("platform", "unknown"))
        
        # Determine default URL
        default_url = html_module.escape(self._get_site_url())
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Tokenade Proxy - {site_name}</title>
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
    </style>
</head>
<body>
    <div class="container">
        <h1>Tokenade Proxy</h1>
        <p class="subtitle">Fingerprint-matched session proxy</p>
        
        <div class="card">
            <h3>Session Info</h3>
            <div class="info-row">
                <span class="info-label">Site</span>
                <span class="info-value">{site_name}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Source Browser</span>
                <span class="info-value">{browser}</span>
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
                <span class="info-label">Status</span>
                <span class="info-value"><span class="status status-ok">● Running</span></span>
            </div>
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
            <h3>Proxy Configuration</h3>
            <div class="info-row">
                <span class="info-label">HTTP Proxy</span>
                <span class="info-value" style="font-family: monospace;">http://127.0.0.1:{self.config.port}</span>
            </div>
            <div class="info-row">
                <span class="info-label">HTTPS Proxy</span>
                <span class="info-value" style="font-family: monospace;">http://127.0.0.1:{self.config.port}</span>
            </div>
        </div>
        
        <div class="card">
            <h3>Usage</h3>
            <div class="instructions">
                <p><strong>GUI Mode:</strong> Enter a URL above and click Browse</p>
                <p><strong>Proxy Mode:</strong> Configure your browser or terminal:</p>
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
        async function updateStats() {{
            try {{
                const resp = await fetch('/stats');
                const data = await resp.json();
                document.getElementById('requests').textContent = data.requests || 0;
                document.getElementById('bytes-in').textContent = formatBytes(data.bytes_received || 0);
                document.getElementById('bytes-out').textContent = formatBytes(data.bytes_sent || 0);
            }} catch(e) {{}}
        }}
        function formatBytes(bytes) {{
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
            return (bytes/(1024*1024)).toFixed(1) + ' MB';
        }}
        setInterval(updateStats, 2000);
        updateStats();
    </script>
</body>
</html>"""
        return web.Response(text=html, content_type='text/html')
    
    async def _handle_browse_post(self, request: web.Request) -> web.Response:
        """Handle POST to /browse - set target URL and redirect."""
        try:
            data = await request.post()
            url = data.get("url", "")
            
            if not url:
                return web.Response(text="No URL provided", status=400)
            
            # Ensure URL has scheme
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            
            # Validate URL
            parsed = urlparse(url)
            if not parsed.hostname:
                return web.Response(text="Invalid URL", status=400)
            
            if not _is_safe_url(url):
                return web.Response(text="URL blocked: internal/private network target", status=403)
            
            # Store target URL and activate proxy mode
            self._target_url = url
            self._proxy_active = True
            
            # Redirect to /proxy which serves the site through the proxy
            raise web.HTTPFound("/proxy")
            
        except web.HTTPFound:
            raise
        except Exception:
            return web.Response(text="Failed to process request", status=500)
    
    async def _handle_site_proxy_entry(self, request: web.Request) -> web.StreamResponse:
        """
        Handle /proxy - serve the target site as a reverse proxy.
        
        All paths are mapped to the target site. URLs are rewritten
        to route back through the proxy.
        """
        if not self._target_url:
            return web.Response(
                text="No target URL set. Use the browse page to set one.",
                status=400
            )
        
        # Redirect root to /proxy/ (with trailing slash for relative URL resolution)
        if request.path == "/proxy":
            raise web.HTTPFound("/proxy/")
        
        # Build target URL from request path
        parsed_target = urlparse(self._target_url)
        request_path = request.path[len("/proxy"):] or "/"
        
        # Preserve query string
        target_url = f"{parsed_target.scheme}://{parsed_target.hostname}"
        if parsed_target.port and parsed_target.port != (443 if parsed_target.scheme == "https" else 80):
            target_url += f":{parsed_target.port}"
        target_url += request_path
        if request.query_string:
            target_url += f"?{request.query_string}"
        
        self.stats["requests"] += 1
        
        try:
            logger.debug(f"Site proxy: {request.method} {target_url}")
            
            # Forward with donor fingerprint
            response = await self._forward_request(
                method=request.method,
                url=target_url,
                headers=dict(request.headers),
                body=await request.read() if request.method in ("POST", "PUT", "PATCH") else None,
                referer=self._extract_referer(request),
                follow_redirects=True
            )
            
            self.stats["bytes_received"] += len(response.body)
            
            # Build response headers
            resp_headers = self._filter_response_headers(response.headers)
            
            # Rewrite HTML content
            content_type = resp_headers.get("content-type", "")
            body = response.body
            
            if "text/html" in content_type:
                body = self._rewrite_html_for_proxy(body, target_url)
            elif "javascript" in content_type or "text/javascript" in content_type:
                body = self._rewrite_js_for_proxy(body, target_url)
            elif "text/css" in content_type:
                body = self._rewrite_css_for_proxy(body, target_url)
            
            return web.Response(
                status=response.status,
                headers=resp_headers,
                body=body
            )
            
        except Exception as e:
            logger.error(f"Site proxy error: {e}")
            self.stats["errors"] += 1
            return web.Response(
                text=f"<html><body><h1>Proxy Error</h1><p>{e}</p></body></html>",
                content_type="text/html",
                status=502
            )
    
    async def _handle_service_worker(self, request: web.Request) -> web.Response:
        """
        Serve a service worker that intercepts all fetch requests
        and routes them through the proxy.
        
        URL scheme:
        - /proxy/<path> → forward to target domain (chatgpt.com)
        - /proxy/<hostname>/<path> → forward to that specific hostname
        """
        sw_code = """
const PROXY_BASE = '/proxy';
const BYPASS_PATHS = ['/_tokenade_sw.js', '/browse', '/status', '/stats'];

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    
    if (!url.protocol.startsWith('http')) return;
    if (BYPASS_PATHS.some(p => url.pathname === p || url.pathname.startsWith(p + '?'))) return;
    if (url.pathname.startsWith(PROXY_BASE + '/')) return;
    
    // Determine target path
    let proxyPath;
    if (url.hostname === self.location.hostname) {
        // Localhost request (import "/cdn/...", <link href="/cdn/...">)
        // Route to target domain
        proxyPath = PROXY_BASE + url.pathname + url.search + url.hash;
    } else {
        // External domain request (cdn.openai.com, etc.)
        // Include hostname in path so proxy knows which domain to forward to
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
    
    async def _handle_browse(self, request: web.Request) -> web.StreamResponse:
        """Handle GET /browse - fetch and display the target page."""
        url = request.query.get("url")
        
        if not url:
            # Show browse page with URL input
            return await self._handle_browse_page(request)
        
        # Fetch the target page through the proxy
        self.stats["requests"] += 1
        
        try:
            logger.debug(f"Browsing: {url}")
            
            # Forward request with donor fingerprint - follow redirects server-side
            response = await self._forward_request(
                method="GET",
                url=url,
                headers={},
                body=None,
                referer=None,
                follow_redirects=True
            )
            
            # Rewrite URLs in HTML to go through proxy
            body = response.body
            if body and b"<html" in body[:1000].lower():
                body = self._rewrite_urls(body, response.url)
            
            # Build response headers (keep content-type in headers)
            resp_headers = self._filter_response_headers(response.headers)
            
            # Return the proxied content
            return web.Response(
                status=response.status,
                headers=resp_headers,
                body=body
            )
            
        except Exception as e:
            logger.error(f"Browse error: {e}")
            self.stats["errors"] += 1
            safe_msg = html_module.escape(str(e))
            return web.Response(
                text=f"<html><body><h1>Proxy Error</h1><p>{safe_msg}</p><p><a href='/'>Back to Proxy</a></p></body></html>",
                content_type="text/html",
                status=502
            )
    
    async def _handle_browse_page(self, request: web.Request) -> web.Response:
        """Show the browse page with URL input."""
        site_name = html_module.escape(self.session.get("site_name", "unknown"))
        default_url = html_module.escape(self._target_url or self._get_site_url())
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Browse - Tokenade Proxy</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: monospace; background: #1a1a1a; color: #fff; }}
        .toolbar {{
            background: #0a0a0a; padding: 10px 20px; border-bottom: 1px solid #333;
            display: flex; align-items: center; gap: 10px;
        }}
        .toolbar input {{
            flex: 1; padding: 8px 12px; border-radius: 4px; border: 1px solid #333;
            background: #1a1a1a; color: #fff; font-family: monospace;
        }}
        .toolbar button {{
            background: #00ff88; color: #000; padding: 8px 16px; 
            border: none; border-radius: 4px; cursor: pointer; font-weight: bold;
        }}
        .toolbar a {{ color: #00ff88; text-decoration: none; margin-left: 10px; }}
        .frame {{ width: 100%; height: calc(100vh - 50px); border: none; }}
    </style>
</head>
<body>
    <div class="toolbar">
        <form action="/browse" method="GET" style="display: flex; gap: 10px; flex: 1;">
            <input type="text" name="url" value="{default_url}" placeholder="Enter URL">
            <button type="submit">Go</button>
        </form>
        <a href="/">← Back to Proxy</a>
    </div>
    <iframe class="frame" src="/proxy-frame?url={quote(default_url)}"></iframe>
</body>
</html>"""
        return web.Response(text=html, content_type='text/html')
    
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
    
    async def _handle_proxy(self, request: web.Request) -> web.StreamResponse:
        """
        Handle proxied requests.
        
        This is the core of the proxy - intercepts requests, applies
        donor fingerprint, and forwards via TLS-matched connection.
        """
        self.stats["requests"] += 1
        
        # Check if this is a proxy-mode sub-resource request
        path = request.path
        if self._proxy_active and self._target_url and path.startswith("/proxy/"):
            # Route to site proxy handler
            return await self._handle_site_proxy_subresource(request)
        
        # Build target URL from request
        target_url = self._build_target_url(request)
        
        if not target_url:
            return web.Response(text="Could not determine target URL", status=400)
        
        if not _is_safe_url(target_url):
            return web.Response(text="URL blocked: internal/private network target", status=403)
        
        logger.debug(f"Proxy: {request.method} {target_url}")
        
        try:
            # Read request body
            body = await request.read()
            
            # Forward request with donor fingerprint
            response = await self._forward_request(
                method=request.method,
                url=target_url,
                headers=dict(request.headers),
                body=body,
                referer=self._extract_referer(request)
            )
            
            # Update stats
            self.stats["bytes_received"] += len(response.body)
            
            # Build response headers
            resp_headers = self._filter_response_headers(response.headers)
            
            # Return response
            return web.Response(
                status=response.status,
                headers=resp_headers,
                body=response.body
            )
            
        except Exception as e:
            logger.error(f"Proxy error: {e}")
            self.stats["errors"] += 1
            return web.Response(text=f"Proxy error: {e}", status=502)
    
    async def _handle_site_proxy_subresource(self, request: web.Request) -> web.StreamResponse:
        """
        Handle sub-resource requests in site proxy mode.
        
        Maps /proxy/<path> to <target_site>/<path>.
        Fixes headers to match the target site (Host, Referer, Origin).
        """
        parsed_target = urlparse(self._target_url)
        request_path = request.path[len("/proxy"):] or "/"
        
        target_url = f"{parsed_target.scheme}://{parsed_target.hostname}"
        if parsed_target.port and parsed_target.port != (443 if parsed_target.scheme == "https" else 80):
            target_url += f":{parsed_target.port}"
        target_url += request_path
        if request.query_string:
            target_url += f"?{request.query_string}"
        
        logger.debug(f"Site subresource: {request.method} {target_url}")
        
        # Build correct headers for the target site
        target_headers = {}
        target_origin = f"{parsed_target.scheme}://{parsed_target.hostname}"
        if parsed_target.port:
            target_origin += f":{parsed_target.port}"
        
        for key, value in request.headers.items():
            key_lower = key.lower()
            # Skip proxy-specific headers
            if key_lower in ("host", "origin", "referer", "x-forwarded-for", "x-real-ip"):
                continue
            target_headers[key] = value
        
        # Set correct Host header for target
        target_headers["Host"] = parsed_target.hostname
        if parsed_target.port and parsed_target.port != (443 if parsed_target.scheme == "https" else 80):
            target_headers["Host"] += f":{parsed_target.port}"
        
        # Set correct Origin and Referer
        target_headers["Origin"] = target_origin
        target_headers["Referer"] = f"{target_origin}/"
        
        try:
            response = await self._forward_request(
                method=request.method,
                url=target_url,
                headers=target_headers,
                body=await request.read() if request.method in ("POST", "PUT", "PATCH") else None,
                referer=f"{target_origin}/",
                follow_redirects=True
            )
            
            self.stats["bytes_received"] += len(response.body)
            
            resp_headers = self._filter_response_headers(response.headers)
            content_type = resp_headers.get("content-type", "")
            body = response.body
            
            # Rewrite HTML/JS/CSS
            if "text/html" in content_type:
                body = self._rewrite_html_for_proxy(body, target_url)
            elif "javascript" in content_type or "text/javascript" in content_type:
                body = self._rewrite_js_for_proxy(body, target_url)
            elif "text/css" in content_type:
                body = self._rewrite_css_for_proxy(body, target_url)
            
            return web.Response(
                status=response.status,
                headers=resp_headers,
                body=body
            )
            
        except Exception as e:
            logger.error(f"Site subresource error: {e}")
            self.stats["errors"] += 1
            return web.Response(text="Failed to fetch resource", status=502)
    
    def _build_target_url(self, request: web.Request) -> Optional[str]:
        """Build target URL from request."""
        # For HTTP proxy requests, the full URL is in the path
        # e.g., GET http://httpbin.org/get HTTP/1.1
        path = request.path
        
        # Check if path contains a full URL (proxy mode)
        if path.startswith(("http://", "https://")):
            return path
        
        # Check :authority header (HTTP/2 proxy)
        authority = request.headers.get(":authority")
        if authority:
            scheme = request.headers.get(":scheme", "https")
            return f"{scheme}://{authority}{path}"
        
        # Check Host header
        host = request.headers.get("Host")
        if host:
            # Determine scheme from port or other hints
            scheme = "https" if ":443" in host or request.headers.get(":scheme") == "https" else "http"
            return f"{scheme}://{host}{path}"
        
        # Fallback: treat path as URL if it looks like one
        path_stripped = path.lstrip("/")
        if path_stripped.startswith(("http://", "https://")):
            return path_stripped
        
        # If path looks like a domain (contains dot and no space)
        if "." in path_stripped and " " not in path_stripped:
            # Check if it has a path after the domain
            parts = path_stripped.split("/", 1)
            if len(parts) > 1:
                return f"https://{parts[0]}/{parts[1]}"
            else:
                return f"https://{path_stripped}"
        
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
            for d in sorted(domains, key=len):
                if site_name.lower() in d.lower():
                    return f"https://{d}"
            if domains:
                return f"https://{min(domains, key=len)}"
            return f"https://www.{site_name}.com"
        return "https://example.com"
    
    def _extract_referer(self, request: web.Request) -> Optional[str]:
        """Extract referer from request headers."""
        return request.headers.get("Referer") or request.headers.get("referer")
    
    def _filter_response_headers(self, headers: Dict) -> Dict:
        """
        Filter response headers to remove proxy-sensitive ones.
        
        Also removes Content-Encoding/Content-Length because the HTTP client
        (aiohttp/curl-cffi) auto-decompresses the body, so the browser must
        not try to decompress it again.
        
        Filters Set-Cookie headers:
        - __Host- cookies: invalid through proxy (domain changes)
        - Domain-specific cookies: domain won't match proxy origin
        """
        filtered = {}
        # Headers to skip entirely
        skip = {
            "transfer-encoding", "connection", "keep-alive", "proxy-connection",
            "content-encoding", "content-length",  # body is already decompressed by HTTP client
            "content-security-policy",  # would block proxy-injected resources
            "x-frame-options",  # allow embedding through proxy
            "strict-transport-security",  # don't force HSTS on proxy
        }
        
        for key, value in headers.items():
            if key.lower() in skip:
                continue
            
            # Filter Set-Cookie headers
            if key.lower() == "set-cookie":
                # Strip __Host- cookies (invalid through proxy, domain changes)
                if value.strip().startswith("__Host-"):
                    continue
                # Strip cookies with Domain= attribute (won't match proxy origin)
                cookie_lower = value.lower()
                if "domain=" in cookie_lower:
                    continue
            
            filtered[key] = value
        
        return filtered
    
    def _rewrite_urls(self, content: bytes, base_url: str) -> bytes:
        """
        Rewrite URLs in HTML content to go through the proxy.
        
        This ensures links, scripts, and resources load through the proxy.
        """
        try:
            text = content.decode("utf-8", errors="ignore")
            parsed_base = urlparse(base_url)
            base_origin = f"{parsed_base.scheme}://{parsed_base.hostname}"
            if parsed_base.port:
                base_origin += f":{parsed_base.port}"
            
            def rewrite_url(match):
                url = match.group(1) or match.group(2)
                if not url:
                    return match.group(0)
                
                # Skip data URLs, javascript, anchors, etc.
                if url.startswith(("data:", "javascript:", "#", "mailto:", "tel:")):
                    return match.group(0)
                
                # Already proxied
                if "/browse?url=" in url or "/proxy/" in url:
                    return match.group(0)
                
                # Handle relative URLs
                if url.startswith("/"):
                    full_url = f"{parsed_base.scheme}://{parsed_base.hostname}"
                    if parsed_base.port:
                        full_url += f":{parsed_base.port}"
                    full_url += url
                elif not url.startswith(("http://", "https://")):
                    # Relative path
                    full_url = f"{base_origin}/{url}"
                else:
                    full_url = url
                
                # URL encode the target URL
                encoded = quote(full_url, safe="")
                if 'href=' in match.group(0):
                    return f'href="/browse?url={encoded}"'
                else:
                    return f'src="/browse?url={encoded}"'
            
            # Rewrite href="..." and src="..."
            result = re.sub(r'href="([^"]+)"|src="([^"]+)"', rewrite_url, text)
            
            return result.encode("utf-8")
            
        except Exception as e:
            logger.debug(f"URL rewrite error: {e}")
            return content
    
    def _rewrite_html_for_proxy(self, content: bytes, base_url: str) -> bytes:
        """
        Rewrite HTML for reverse proxy mode.
        
        1. Inject <base> tag for relative URLs
        2. Rewrite ALL href/src URLs to /proxy/ paths (absolute AND relative)
        3. Inject service worker for JavaScript fetch interception
        """
        try:
            text = content.decode("utf-8", errors="ignore")
            parsed_base = urlparse(base_url)
            target_host = parsed_base.hostname
            
            # Build <base> tag to make relative URLs resolve to proxy
            base_tag = '<base href="/proxy/">'
            
            # Inject service worker registration + base tag in <head>
            sw_injection = f"""
<script nonce="_tokenade_">
if ('serviceWorker' in navigator) {{
    navigator.serviceWorker.register('/_tokenade_sw.js')
        .then(reg => console.log('[Tokenade] SW registered, scope:', reg.scope))
        .catch(err => console.warn('[Tokenade] SW registration failed:', err));
}}
</script>
{base_tag}
"""
            
            # Inject after <head> or at start
            if "<head>" in text.lower():
                text = re.sub(r'<head>', '<head>\n' + sw_injection, text, count=1, flags=re.IGNORECASE)
            elif "<html>" in text.lower():
                text = re.sub(r'<html>', '<html>\n<head>\n' + sw_injection + '</head>', text, count=1, flags=re.IGNORECASE)
            else:
                text = sw_injection + text
            
            if target_host:
                # Rewrite ALL href="..." and src="..." to /proxy/ paths
                def rewrite_all_urls(match):
                    attr = match.group(1)  # href= or src=
                    url = match.group(2)
                    
                    # Skip data URLs, javascript, anchors, mailto, tel
                    if url.startswith(("data:", "javascript:", "#", "mailto:", "tel:")):
                        return match.group(0)
                    
                    # Already proxied
                    if url.startswith("/proxy/"):
                        return match.group(0)
                    
                    # Absolute URL to target host -> /proxy/path
                    if target_host in url:
                        parsed_url = urlparse(url)
                        path = parsed_url.path or "/"
                        query = f"?{parsed_url.query}" if parsed_url.query else ""
                        fragment = f"#{parsed_url.fragment}" if parsed_url.fragment else ""
                        return f'{attr}/proxy/{path}{query}{fragment}'
                    
                    # Relative URL starting with / -> /proxy/path
                    if url.startswith("/"):
                        # Avoid double slashes
                        return f'{attr}/proxy{url}'
                    
                    # Relative URL without / -> /proxy/path
                    # (handled by <base> tag, but also rewrite explicitly)
                    return match.group(0)
                
                # Rewrite href="..." and src="..."
                text = re.sub(
                    r'(href="|src=")([^"]+)"',
                    rewrite_all_urls,
                    text
                )
                
                # Rewrite import "..." and from "..." in inline <script type="module">
                def rewrite_import(match):
                    keyword = match.group(1)  # import or from
                    quote = match.group(2)    # ' or "
                    url = match.group(3)
                    
                    if url.startswith(("data:", "javascript:", "#")):
                        return match.group(0)
                    if url.startswith("/proxy/"):
                        return match.group(0)
                    if target_host in url:
                        parsed_url = urlparse(url)
                        path = parsed_url.path or "/"
                        return f'{keyword} {quote}/proxy{path}{quote}'
                    if url.startswith("/"):
                        return f'{keyword} {quote}/proxy{url}{quote}'
                    return match.group(0)
                
                # import "..." or import '...'
                text = re.sub(
                    r'(import)\s+(["\'])([^"\']+)\2',
                    rewrite_import,
                    text
                )
                # from "..." or from '...'
                text = re.sub(
                    r'(from)\s+(["\'])([^"\']+)\2',
                    rewrite_import,
                    text
                )
                
                # Rewrite url(...) in inline styles
                def rewrite_css_url(match):
                    url = match.group(2)
                    if url.startswith("/"):
                        return f'url(/proxy/{url})'
                    if target_host in url:
                        return f'url(/proxy/{urlparse(url).path})'
                    return match.group(0)
                
                text = re.sub(
                    r'url\((["\']?)([^)]+)\1\)',
                    rewrite_css_url,
                    text
                )
            
            return text.encode("utf-8")
            
        except Exception as e:
            logger.debug(f"HTML proxy rewrite error: {e}")
            return content
    
    def _rewrite_js_for_proxy(self, content: bytes, base_url: str) -> bytes:
        """Rewrite JavaScript imports to route through proxy."""
        try:
            text = content.decode("utf-8", errors="ignore")
            parsed_base = urlparse(base_url)
            target_host = parsed_base.hostname
            
            if target_host:
                # Rewrite import "https://chatgpt.com/cdn/..." -> import "/proxy/cdn/..."
                def rewrite_import(match):
                    prefix = match.group(1)
                    url = match.group(2)
                    if target_host in url:
                        parsed_url = urlparse(url)
                        path = parsed_url.path or "/"
                        query = f"?{parsed_url.query}" if parsed_url.query else ""
                        # Avoid double slashes
                        proxy_path = f"/proxy{path}" if path.startswith("/") else f"/proxy/{path}"
                        return f'{prefix}{proxy_path}{query}'
                    return match.group(0)
                
                # Also rewrite bare paths: from "/cdn/..." -> from "/proxy/cdn/..."
                def rewrite_bare_path(match):
                    prefix = match.group(1)
                    path = match.group(2)
                    # Avoid double slashes
                    proxy_path = f"/proxy{path}" if path.startswith("/") else f"/proxy/{path}"
                    return f'{prefix}{proxy_path}'
                
                # import "..." or import '...'
                text = re.sub(
                    r'(import\s+(?:["\']))(https?://[^"\']+)(["\'])',
                    rewrite_import,
                    text
                )
                
                # from "..." or from '...'
                text = re.sub(
                    r'(from\s+["\'])(https?://[^"\']+)(["\'])',
                    rewrite_import,
                    text
                )
                
                # from "/path..." or from 'path...' (bare paths)
                text = re.sub(
                    r'(from\s+["\'])(/[^"\']+)(["\'])',
                    rewrite_bare_path,
                    text
                )
                
                # fetch("...") or fetch('...')
                text = re.sub(
                    r'(fetch\s*\(\s*["\'])(https?://[^"\']+)(["\'])',
                    rewrite_import,
                    text
                )
                
                # fetch("/path...") (bare paths in fetch)
                text = re.sub(
                    r'(fetch\s*\(\s*["\'])(/[^"\']+)(["\'])',
                    rewrite_bare_path,
                    text
                )
            
            return text.encode("utf-8")
            
        except Exception as e:
            logger.debug(f"JS proxy rewrite error: {e}")
            return content
    
    def _rewrite_css_for_proxy(self, content: bytes, base_url: str) -> bytes:
        """Rewrite CSS urls to route through proxy."""
        try:
            text = content.decode("utf-8", errors="ignore")
            parsed_base = urlparse(base_url)
            target_host = parsed_base.hostname
            
            if target_host:
                def rewrite_css_url(match):
                    url = match.group(2)
                    if target_host in url:
                        parsed_url = urlparse(url)
                        path = parsed_url.path or "/"
                        return f'url(/proxy/{path})'
                    return match.group(0)
                
                text = re.sub(
                    r'url\((["\']?)(https?://[^)]+)\1\)',
                    rewrite_css_url,
                    text
                )
            
            return text.encode("utf-8")
            
        except Exception as e:
            logger.debug(f"CSS proxy rewrite error: {e}")
            return content
    
    async def _forward_request(
        self,
        method: str,
        url: str,
        headers: Dict,
        body: Optional[bytes],
        referer: Optional[str] = None,
        follow_redirects: bool = True,
        max_redirects: int = 10
    ) -> ProxyResponse:
        """
        Forward request with donor fingerprint.
        
        Applies donor's headers, cookies, and TLS profile.
        Follows redirects server-side to get final content.
        """
        current_url = url
        current_method = method
        current_body = body
        current_referer = referer
        
        for redirect_count in range(max_redirects):
            # Get donor-matched headers
            donor_headers = self.fingerprint.get_headers(current_url, current_referer, current_method)
            
            # Inject donor cookies
            cookies = self.cookie_jar.get_for_request(current_url)
            if cookies:
                donor_headers["cookie"] = cookies
            
            # Remove problematic headers
            for h in ["host", "connection", "proxy-connection", "accept-encoding"]:
                donor_headers.pop(h, None)
            
            # Set accept-encoding to what we can handle
            donor_headers["accept-encoding"] = "gzip, deflate"
            
            # Update stats
            self.stats["bytes_sent"] += len(current_body) if current_body else 0
            
            response = None
            
            # Use TLS matcher for the actual request
            if self.tls_matcher and self.tls_matcher._session:
                try:
                    # Use curl-cffi for TLS fingerprint matching
                    response = self.tls_matcher.request(
                        method=current_method,
                        url=current_url,
                        headers=dict(donor_headers),
                        data=current_body,
                        timeout=30
                    )
                    
                    # Read content
                    content = response.content
                    if hasattr(content, 'read'):
                        response_body = content.read()
                    elif isinstance(content, bytes):
                        response_body = content
                    else:
                        response_body = bytes(content)
                    
                    # Get headers
                    resp_headers = dict(response.headers) if hasattr(response, 'headers') else {}
                    status = response.status_code
                    
                except Exception as e:
                    logger.debug(f"curl-cffi failed: {e}")
                    response = None
            
            # Fallback to aiohttp (persistent session with connection pooling)
            if response is None:
                if self._http_session is None or self._http_session.closed:
                    connector = aiohttp.TCPConnector(
                        ssl=False,
                        limit=100,  # Max connections
                        limit_per_host=30,  # Max per host
                        enable_cleanup_closed=True
                    )
                    timeout = aiohttp.ClientTimeout(total=30, connect=10)
                    self._http_session = aiohttp.ClientSession(
                        connector=connector,
                        timeout=timeout,
                        auto_decompress=False  # We handle decompression ourselves
                    )
                
                async with self._http_session.request(
                    method=current_method,
                    url=current_url,
                    headers=dict(donor_headers),
                    data=current_body,
                    allow_redirects=False,
                    ssl=False
                ) as aio_response:
                    response_body = await aio_response.read()
                    resp_headers = dict(aio_response.headers)
                    status = aio_response.status
            
            # Check if we should follow redirect
            if follow_redirects and status in (301, 302, 303, 307, 308):
                location = resp_headers.get("location", "")
                if location:
                    # Handle relative redirects
                    if location.startswith("/"):
                        parsed_current = urlparse(current_url)
                        location = f"{parsed_current.scheme}://{parsed_current.hostname}{location}"
                    
                    logger.debug(f"Following redirect {status}: {location}")
                    current_url = location
                    current_method = "GET" if status in (301, 302, 303) else method
                    current_body = None
                    current_referer = current_url
                    continue
            
            # Return final response
            return ProxyResponse(
                status=status,
                headers=resp_headers,
                body=response_body,
                url=current_url
            )
        
        # If we exhausted redirects, return last response
        return ProxyResponse(
            status=status,
            headers=resp_headers,
            body=response_body,
            url=current_url
        )
    
    async def start(self):
        """Start the proxy server."""
        self._app = self._create_app()
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.config.host, self.config.port)
        await self._site.start()
        
        self.stats["start_time"] = time.time()
        
        logger.info(f"Tokenade Proxy started on {self.config.host}:{self.config.port}")
        print(f"\n{'='*60}")
        print(f"Tokenade Proxy Server")
        print(f"{'='*60}")
        print(f"Site: {self.session.get('site_name', 'unknown')}")
        print(f"Cookies: {len(self.cookie_jar.to_list())}")
        print(f"TLS Profile: {self.session.get('tls_profile', {}).get('impersonate', 'unknown')}")
        print(f"\nGUI: http://127.0.0.1:{self.config.port}")
        print(f"Proxy: http://127.0.0.1:{self.config.port}")
        print(f"\nTo use as HTTP proxy:")
        print(f"  export HTTP_PROXY=http://127.0.0.1:{self.config.port}")
        print(f"  export HTTPS_PROXY=http://127.0.0.1:{self.config.port}")
        print(f"{'='*60}\n")
    
    async def stop(self):
        """Stop the proxy server."""
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
        if self._runner:
            await self._runner.cleanup()
        if self.tls_matcher:
            self.tls_matcher.close()
    
    def run(self):
        """Run the proxy server (blocking)."""
        asyncio.run(self._run_async())
    
    async def _run_async(self):
        """Run the proxy server asynchronously."""
        await self.start()
        
        try:
            # Keep running until interrupted
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down proxy...")
        finally:
            await self.stop()


def create_proxy_from_file(session_file: str, port: int = 9222, gui: bool = True) -> TokenadeProxy:
    """
    Convenience function to create and configure a proxy.
    
    Args:
        session_file: Path to .tokenade file
        port: Port to listen on
        gui: Enable GUI mode
        
    Returns:
        Configured TokenadeProxy
    """
    config = ProxyConfig(port=port, gui_mode=gui)
    return TokenadeProxy.from_session_file(session_file, config)
