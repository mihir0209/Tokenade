"""
CDP Proxy — Request routing, forwarding via curl-cffi/aiohttp, and reverse proxy.
"""

import asyncio
import logging
from typing import Optional, Dict, TYPE_CHECKING
from urllib.parse import urlparse

import aiohttp
from aiohttp import web

from tokenade.core.proxy.cdp_stealth import is_safe_url

if TYPE_CHECKING:
    from tokenade.core.proxy.cdp_proxy import CDPProxy

logger = logging.getLogger(__name__)

SKIP_HEADERS = {
    "content-security-policy",
    "x-frame-options",
    "strict-transport-security",
    "content-encoding",
    "transfer-encoding",
}


async def handle_route(proxy: "CDPProxy", route):
    """
    Intercept ALL requests from the browser and forward via curl-cffi.
    """
    request = route.request
    url = request.url
    method = request.method
    headers = dict(request.headers)

    if url.startswith("data:") or url.startswith("about:"):
        await route.continue_()
        return

    proxy.stats["requests"] += 1

    try:
        logger.debug(f"Route: {method} {url}")

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

        response = await forward_via_curl_cffi(proxy, method=method, url=url, headers=headers, body=body)

        if response is None:
            await route.abort()
            return

        proxy.stats["bytes_received"] += len(response.body)

        raw_headers = response.headers

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
                        proxy.cookie_jar.add_cookie(new_cookie)
                except Exception:
                    pass

        resp_headers = {}
        if isinstance(raw_headers, dict):
            header_items = raw_headers.items()
        elif isinstance(raw_headers, list):
            header_items = raw_headers
        else:
            header_items = []

        for item in header_items:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                key, value = item
            elif isinstance(item, dict):
                key = item.get("name", "")
                value = item.get("value", "")
            else:
                continue

            if key.lower() in SKIP_HEADERS:
                continue
            resp_headers[str(key)] = str(value)

        await route.fulfill(
            status=response.status,
            headers=resp_headers,
            body=response.body
        )

    except Exception as e:
        from tokenade.core.errors import DependencyError, ProxyError
        if isinstance(e, DependencyError):
            raise
        logger.error("Route error for %s: %s", url[:120], e)
        proxy.stats["errors"] += 1
        try:
            await route.abort()
        except Exception as abort_err:
            logger.debug("route.abort failed: %s", abort_err)
            raise ProxyError(
                f"Request route failed and abort failed: {e}",
                operation="cdp_route",
                cause=abort_err,
            ) from e


async def forward_via_curl_cffi(
    proxy: "CDPProxy",
    method: str,
    url: str,
    headers: Dict[str, str],
    body: Optional[str] = None,
):
    """Forward request via curl-cffi with donor TLS fingerprint.

    Missing curl-cffi is a hard failure (DependencyError). Transient request
    errors still fall back to aiohttp so pages can load without TLS match.
    """
    try:
        from curl_cffi import requests as curl_requests
    except ImportError as e:
        from tokenade.core.errors import DependencyError
        raise DependencyError(
            "curl-cffi is required for TLS-matched proxy forwarding. "
            "Install with: pip install curl-cffi",
            operation="cdp_route",
            cause=e,
        ) from e

    try:
        donor_headers = proxy.fingerprint.get_headers(url, None, method)

        for key, value in headers.items():
            key_lower = key.lower()
            if key_lower in ("host", "connection", "proxy-connection"):
                continue
            donor_headers[key] = value

        cookies = proxy.cookie_jar.get_for_request(url)
        if cookies:
            donor_headers["cookie"] = cookies
            if "chatgpt" in url:
                logger.info(f"[COOKIE] {url[:80]} -> {len(cookies)} chars")
        else:
            if "chatgpt" in url:
                logger.warning(f"[COOKIE] NO cookies for {url[:80]}")

        donor_headers.pop("accept-encoding", None)

        proxy.stats["bytes_sent"] += len(body) if body else 0

        response = await asyncio.to_thread(
            curl_requests.request,
            method=method,
            url=url,
            headers=donor_headers,
            data=body,
            impersonate=proxy.session.get("tls_profile", {}).get("impersonate", "chrome120"),
            timeout=proxy.config.timeout,
            allow_redirects=True,
        )

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
        from tokenade.core.errors import DependencyError
        if isinstance(e, DependencyError):
            raise
        logger.warning("curl-cffi request failed for %s: %s — falling back to aiohttp", url[:80], e)
        return await forward_via_aiohttp(proxy, method, url, headers, body)


async def forward_via_aiohttp(
    proxy: "CDPProxy",
    method: str,
    url: str,
    headers: Dict[str, str],
    body: Optional[str] = None,
):
    """Fallback: forward via aiohttp."""
    try:
        if proxy._shared_http_session and not proxy._shared_http_session.closed:
            http_session = proxy._shared_http_session
        else:
            async with proxy._session_lock:
                if proxy._http_session is None or proxy._http_session.closed:
                    connector = aiohttp.TCPConnector(
                        ssl=None,
                        limit=100,
                        limit_per_host=30,
                        enable_cleanup_closed=True
                    )
                    timeout = aiohttp.ClientTimeout(total=proxy.config.timeout, connect=10)
                    proxy._http_session = aiohttp.ClientSession(
                        connector=connector,
                        timeout=timeout,
                        auto_decompress=False
                    )
            http_session = proxy._http_session

        donor_headers = proxy.fingerprint.get_headers(url, None, method)
        for key, value in headers.items():
            key_lower = key.lower()
            if key_lower in ("host", "connection", "proxy-connection"):
                continue
            donor_headers[key] = value

        cookies = proxy.cookie_jar.get_for_request(url)
        if cookies:
            donor_headers["cookie"] = cookies

        donor_headers.pop("accept-encoding", None)

        async with http_session.request(
            method=method,
            url=url,
            headers=donor_headers,
            data=body,
            allow_redirects=True,
            ssl=None
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


async def handle_proxy(proxy: "CDPProxy", request: web.Request) -> web.Response:
    """Handle reverse proxy requests."""
    proxy.stats["requests"] += 1

    path = request.path
    if path.startswith("/api/"):
        return await handle_api(proxy, request)

    if path.startswith("/proxy"):
        raise web.HTTPFound("/")

    target_url = build_target_url(proxy, request)
    if not target_url:
        return web.Response(text="Could not determine target URL", status=400)

    if not is_safe_url(target_url):
        return web.Response(text="URL blocked: internal/private network target", status=403)

    try:
        body = await request.read() if request.method in ("POST", "PUT", "PATCH") else None

        response = await forward_via_curl_cffi(
            proxy,
            method=request.method,
            url=target_url,
            headers=dict(request.headers),
            body=body
        )

        if response is None:
            return web.Response(text="Proxy error", status=502)

        proxy.stats["bytes_received"] += len(response.body)

        resp_headers = {}
        for key, value in response.headers.items():
            if key.lower() in SKIP_HEADERS:
                continue
            resp_headers[key] = value

        return web.Response(
            status=response.status,
            headers=resp_headers,
            body=response.body
        )

    except Exception as e:
        logger.error(f"Proxy error: {e}")
        proxy.stats["errors"] += 1
        return web.Response(text=f"Proxy error: {e}", status=502)


async def handle_api(proxy: "CDPProxy", request: web.Request) -> web.Response:
    """Handle API requests under /api/."""
    path = request.path

    if path == "/api/status":
        return await proxy._handle_status(request)
    elif path == "/api/stats":
        return await proxy._handle_stats(request)
    elif path.startswith("/api/page/") and path.endswith("/html"):
        return await handle_page_html(proxy, request)
    elif path.startswith("/api/page/") and path.endswith("/screenshot"):
        return await handle_page_screenshot(proxy, request)

    return web.Response(text="Not found", status=404)


async def handle_page_html(proxy: "CDPProxy", request: web.Request) -> web.Response:
    """Return the rendered HTML of a page."""
    parts = request.path.split("/")
    if len(parts) >= 4:
        page_id = parts[3]
    else:
        return web.Response(text="Invalid page ID", status=400)

    page = proxy._pages.get(page_id)
    if not page:
        return web.Response(text="Page not found", status=404)

    try:
        page_html = await page.content()
        if page.url and not page.url.startswith("about:"):
            parsed = urlparse(page.url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"  # noqa: F841 used in replace
            if "<head>" in page_html:
                page_html = page_html.replace("<head>", "<head><base href=\"{base_url}/\">", 1)
            elif "<HEAD>" in page_html:
                page_html = page_html.replace("<HEAD>", "<HEAD><base href=\"{base_url}/\">", 1)
        return web.Response(text=page_html, content_type='text/html')
    except Exception as e:
        return web.Response(text=f"Error getting page content: {e}", status=500)


async def handle_page_screenshot(proxy: "CDPProxy", request: web.Request) -> web.Response:
    """Return a screenshot of a page as PNG."""
    parts = request.path.split("/")
    if len(parts) >= 4:
        page_id = parts[3]
    else:
        return web.Response(text="Invalid page ID", status=400)

    page = proxy._pages.get(page_id)
    if not page:
        return web.Response(text="Page not found", status=404)

    try:
        screenshot = await page.screenshot(type="png")
        return web.Response(body=screenshot, content_type='image/png')
    except Exception as e:
        return web.Response(text=f"Error taking screenshot: {e}", status=500)


def build_target_url(proxy: "CDPProxy", request: web.Request) -> Optional[str]:
    """Build target URL from request."""
    path = request.path

    if path.startswith(("http://", "https://")):
        return path

    host = request.headers.get("Host") or request.headers.get(":authority")

    if host and host not in (proxy.config.host, f"{proxy.config.host}:{proxy.config.port}"):
        scheme = "https" if ":443" in host or request.headers.get(":scheme") == "https" else "http"
        return f"{scheme}://{host}{path}"

    referer = request.headers.get("Referer", "")
    for page_id, page in proxy._pages.items():
        if f"/page/{page_id}" in referer and page.url:
            parsed = urlparse(page.url)
            return f"{parsed.scheme}://{parsed.netloc}{path}"

    return None
