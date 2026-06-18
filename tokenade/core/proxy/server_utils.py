"""
Tokenade Legacy Proxy — URL rewriting, response filtering, and content rewriting.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional, Dict
from urllib.parse import urlparse, quote

from aiohttp import web

logger = logging.getLogger(__name__)


@dataclass
class ProxyResponse:
    """Simple response container from forwarded request."""
    status: int
    headers: Dict[str, str]
    body: bytes
    url: str


SKIP_RESPONSE_HEADERS = {
    "transfer-encoding", "connection", "keep-alive", "proxy-connection",
    "content-encoding", "content-length",
    "content-security-policy", "x-frame-options", "strict-transport-security",
}


def build_target_url(request: web.Request) -> Optional[str]:
    """Build target URL from request."""
    path = request.path
    if path.startswith(("http://", "https://")):
        return path

    authority = request.headers.get(":authority")
    if authority:
        scheme = request.headers.get(":scheme", "https")
        return f"{scheme}://{authority}{path}"

    host = request.headers.get("Host")
    if host:
        scheme = "https" if ":443" in host or request.headers.get(":scheme") == "https" else "http"
        return f"{scheme}://{host}{path}"

    path_stripped = path.lstrip("/")
    if path_stripped.startswith(("http://", "https://")):
        return path_stripped

    if "." in path_stripped and " " not in path_stripped:
        parts = path_stripped.split("/", 1)
        if len(parts) > 1:
            return f"https://{parts[0]}/{parts[1]}"
        else:
            return f"https://{path_stripped}"

    return None


def filter_response_headers(headers: Dict) -> Dict:
    """Filter response headers to remove proxy-sensitive ones."""
    filtered = {}
    for key, value in headers.items():
        if key.lower() in SKIP_RESPONSE_HEADERS:
            continue
        if key.lower() == "set-cookie":
            if value.strip().startswith("__Host-"):
                continue
            if "domain=" in value.lower():
                continue
        filtered[key] = value
    return filtered


def rewrite_urls(content: bytes, base_url: str) -> bytes:
    """Rewrite URLs in HTML content to go through the proxy."""
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
            if url.startswith(("data:", "javascript:", "#", "mailto:", "tel:")):
                return match.group(0)
            if "/browse?url=" in url or "/proxy/" in url:
                return match.group(0)
            if url.startswith("/"):
                full_url = f"{parsed_base.scheme}://{parsed_base.hostname}"
                if parsed_base.port:
                    full_url += f":{parsed_base.port}"
                full_url += url
            elif not url.startswith(("http://", "https://")):
                full_url = f"{base_origin}/{url}"
            else:
                full_url = url
            encoded = quote(full_url, safe="")
            if 'href=' in match.group(0):
                return f'href="/browse?url={encoded}"'
            else:
                return f'src="/browse?url={encoded}"'

        result = re.sub(r'href="([^"]+)"|src="([^"]+)"', rewrite_url, text)
        return result.encode("utf-8")
    except Exception as e:
        logger.debug(f"URL rewrite error: {e}")
        return content


def rewrite_html_for_proxy(content: bytes, base_url: str) -> bytes:
    """Rewrite HTML for reverse proxy mode."""
    try:
        text = content.decode("utf-8", errors="ignore")
        parsed_base = urlparse(base_url)
        target_host = parsed_base.hostname

        sw_injection = """
<script nonce="_tokenade_">
if ('serviceWorker' in navigator) {{
    navigator.serviceWorker.register('/_tokenade_sw.js')
        .then(reg => console.log('[Tokenade] SW registered, scope:', reg.scope))
        .catch(err => console.warn('[Tokenade] SW registration failed:', err));
}}
</script>
{base_tag}
"""
        if "<head>" in text.lower():
            text = re.sub(r'<head>', '<head>\n' + sw_injection, text, count=1, flags=re.IGNORECASE)
        elif "<html>" in text.lower():
            text = re.sub(r'<html>', '<html>\n<head>\n' + sw_injection + '</head>', text, count=1, flags=re.IGNORECASE)
        else:
            text = sw_injection + text

        if target_host:
            def rewrite_all_urls(match):
                attr = match.group(1)
                url = match.group(2)
                if url.startswith(("data:", "javascript:", "#", "mailto:", "tel:")):
                    return match.group(0)
                if url.startswith("/proxy/"):
                    return match.group(0)
                if target_host in url:
                    parsed_url = urlparse(url)
                    path = parsed_url.path or "/"
                    query = f"?{parsed_url.query}" if parsed_url.query else ""
                    fragment = f"#{parsed_url.fragment}" if parsed_url.fragment else ""
                    return f'{attr}/proxy/{path}{query}{fragment}'
                if url.startswith("/"):
                    return f'{attr}/proxy{url}'
                return match.group(0)

            text = re.sub(r'(href="|src=")([^"]+)"', rewrite_all_urls, text)

            def rewrite_import(match):
                keyword = match.group(1)
                q = match.group(2)
                url = match.group(3)
                if url.startswith(("data:", "javascript:", "#")):
                    return match.group(0)
                if url.startswith("/proxy/"):
                    return match.group(0)
                if target_host in url:
                    parsed_url = urlparse(url)
                    path = parsed_url.path or "/"
                    return f'{keyword} {q}/proxy{path}{q}'
                if url.startswith("/"):
                    return f'{keyword} {q}/proxy{url}{q}'
                return match.group(0)

            text = re.sub(r'(import)\s+(["\'])([^"\']+)\2', rewrite_import, text)
            text = re.sub(r'(from)\s+(["\'])([^"\']+)\2', rewrite_import, text)

            def rewrite_css_url(match):
                url = match.group(2)
                if url.startswith("/"):
                    return f'url(/proxy/{url})'
                if target_host in url:
                    return f'url(/proxy/{urlparse(url).path})'
                return match.group(0)

            text = re.sub(r'url\((["\']?)([^)]+)\1\)', rewrite_css_url, text)

        return text.encode("utf-8")
    except Exception as e:
        logger.debug(f"HTML proxy rewrite error: {e}")
        return content


def rewrite_js_for_proxy(content: bytes, base_url: str) -> bytes:
    """Rewrite JavaScript imports to route through proxy."""
    try:
        text = content.decode("utf-8", errors="ignore")
        parsed_base = urlparse(base_url)
        target_host = parsed_base.hostname

        if target_host:
            def rewrite_import(match):
                prefix = match.group(1)
                url = match.group(2)
                if target_host in url:
                    parsed_url = urlparse(url)
                    path = parsed_url.path or "/"
                    query = f"?{parsed_url.query}" if parsed_url.query else ""
                    proxy_path = f"/proxy{path}" if path.startswith("/") else f"/proxy/{path}"
                    return f'{prefix}{proxy_path}{query}'
                return match.group(0)

            def rewrite_bare_path(match):
                prefix = match.group(1)
                path = match.group(2)
                proxy_path = f"/proxy{path}" if path.startswith("/") else f"/proxy/{path}"
                return f'{prefix}{proxy_path}'

            text = re.sub(r'(import\s+(?:["\']))(https?://[^"\']+)(["\'])', rewrite_import, text)
            text = re.sub(r'(from\s+["\'])(https?://[^"\']+)(["\'])', rewrite_import, text)
            text = re.sub(r'(from\s+["\'])(/[^"\']+)(["\'])', rewrite_bare_path, text)
            text = re.sub(r'(fetch\s*\(\s*["\'])(https?://[^"\']+)(["\'])', rewrite_import, text)
            text = re.sub(r'(fetch\s*\(\s*["\'])(/[^"\']+)(["\'])', rewrite_bare_path, text)

        return text.encode("utf-8")
    except Exception as e:
        logger.debug(f"JS proxy rewrite error: {e}")
        return content


def rewrite_css_for_proxy(content: bytes, base_url: str) -> bytes:
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

            text = re.sub(r'url\((["\']?)(https?://[^)]+)\1\)', rewrite_css_url, text)

        return text.encode("utf-8")
    except Exception as e:
        logger.debug(f"CSS proxy rewrite error: {e}")
        return content
