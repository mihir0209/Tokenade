"""
Tokenade Legacy Proxy — Request forwarding via curl-cffi/aiohttp.
"""

import logging
from typing import Optional, Dict, TYPE_CHECKING

import aiohttp

from tokenade.core.proxy.server_utils import ProxyResponse

if TYPE_CHECKING:
    from tokenade.core.proxy.server import TokenadeProxy

logger = logging.getLogger(__name__)


async def forward_request(
    proxy: "TokenadeProxy",
    method: str,
    url: str,
    headers: Dict,
    body: Optional[bytes],
    referer: Optional[str] = None,
    follow_redirects: bool = True,
    max_redirects: int = 10,
) -> ProxyResponse:
    """Forward request with donor fingerprint."""
    from urllib.parse import urlparse

    current_url = url
    current_method = method
    current_body = body
    current_referer = referer
    status = 502
    resp_headers = {}
    response_body = b""

    for redirect_count in range(max_redirects):
        donor_headers = proxy.fingerprint.get_headers(current_url, current_referer, current_method)

        cookies = proxy.cookie_jar.get_for_request(current_url)
        if cookies:
            donor_headers["cookie"] = cookies

        for h in ["host", "connection", "proxy-connection", "accept-encoding"]:
            donor_headers.pop(h, None)
        donor_headers["accept-encoding"] = "gzip, deflate"

        proxy.stats["bytes_sent"] += len(current_body) if current_body else 0

        response = None

        if proxy.tls_matcher and proxy.tls_matcher._session:
            try:
                response = proxy.tls_matcher.request(
                    method=current_method,
                    url=current_url,
                    headers=dict(donor_headers),
                    data=current_body,
                    timeout=30
                )
                content = response.content
                if hasattr(content, 'read'):
                    response_body = content.read()
                elif isinstance(content, bytes):
                    response_body = content
                else:
                    response_body = bytes(content)
                resp_headers = dict(response.headers) if hasattr(response, 'headers') else {}
                status = response.status_code
            except Exception as e:
                logger.debug(f"curl-cffi failed: {e}")
                response = None

        if response is None:
            if proxy._http_session is None or proxy._http_session.closed:
                connector = aiohttp.TCPConnector(
                    ssl=None,
                    limit=100,
                    limit_per_host=30,
                    enable_cleanup_closed=True
                )
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                proxy._http_session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout,
                    auto_decompress=False
                )

            async with proxy._http_session.request(
                method=current_method,
                url=current_url,
                headers=dict(donor_headers),
                data=current_body,
                allow_redirects=False,
                ssl=None
            ) as aio_response:
                response_body = await aio_response.read()
                resp_headers = dict(aio_response.headers)
                status = aio_response.status

        if follow_redirects and status in (301, 302, 303, 307, 308):
            location = resp_headers.get("location", "")
            if location:
                if location.startswith("/"):
                    parsed_current = urlparse(current_url)
                    location = f"{parsed_current.scheme}://{parsed_current.hostname}{location}"
                logger.debug(f"Following redirect {status}: {location}")
                current_url = location
                current_method = "GET" if status in (301, 302, 303) else method
                current_body = None
                current_referer = current_url
                continue

        return ProxyResponse(
            status=status,
            headers=resp_headers,
            body=response_body,
            url=current_url
        )

    return ProxyResponse(
        status=status,
        headers=resp_headers,
        body=response_body,
        url=current_url
    )
