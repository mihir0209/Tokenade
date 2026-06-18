"""Comprehensive tests for cdp_routing module — targeting 50%+ coverage."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web

from tokenade.core.proxy.cdp_routing import (
    SKIP_HEADERS,
    handle_route,
    forward_via_curl_cffi,
    forward_via_aiohttp,
    handle_proxy,
    handle_api,
    handle_page_html,
    handle_page_screenshot,
    build_target_url,
)


def _make_proxy(**overrides):
    """Create a mock CDPProxy with sensible defaults."""
    proxy = MagicMock()
    proxy.config = MagicMock()
    proxy.config.host = "127.0.0.1"
    proxy.config.port = 9222
    proxy.config.timeout = 30
    proxy.session = {"tls_profile": {"impersonate": "chrome120"}}
    proxy.stats = {
        "requests": 0, "bytes_sent": 0, "bytes_received": 0, "errors": 0
    }
    proxy.cookie_jar = MagicMock()
    proxy.cookie_jar.get_for_request.return_value = ""
    proxy.cookie_jar.add_cookie = MagicMock()
    proxy.fingerprint = MagicMock()
    proxy.fingerprint.get_headers.return_value = {"accept": "text/html"}
    proxy._pages = {}
    proxy._page_meta = {}
    proxy._max_pages = 20
    proxy._shared_http_session = None
    proxy._http_session = None
    proxy._session_lock = asyncio.Lock()
    proxy._cleanup_expired_pages = MagicMock()
    proxy._close_page = AsyncMock()
    proxy._navigate_page = AsyncMock()
    proxy._handle_status = AsyncMock(return_value=web.Response(text="ok"))
    proxy._handle_stats = AsyncMock(return_value=web.Response(text="{}"))
    for k, v in overrides.items():
        setattr(proxy, k, v)
    return proxy


def _make_route(url="https://example.com", method="GET", headers=None, post_data=None, post_data_buffer=None):
    """Create a mock route object."""
    route = AsyncMock()
    route.request = MagicMock()
    route.request.url = url
    route.request.method = method
    route.request.headers = headers or {}
    if post_data is not None:
        route.request.post_data = post_data
    else:
        route.request.post_data = MagicMock(side_effect=UnicodeDecodeError("", b"", 0, 1, ""))
    if post_data_buffer is not None:
        route.request.post_data_buffer = post_data_buffer
    else:
        route.request.post_data_buffer = MagicMock(side_effect=Exception("no buffer"))
    route.continue_ = AsyncMock()
    route.abort = AsyncMock()
    route.fulfill = AsyncMock()
    return route


# ---------------------------------------------------------------------------
# SKIP_HEADERS
# ---------------------------------------------------------------------------

def test_skip_headers():
    assert "content-security-policy" in SKIP_HEADERS
    assert "x-frame-options" in SKIP_HEADERS
    assert "strict-transport-security" in SKIP_HEADERS
    assert "content-encoding" in SKIP_HEADERS
    assert "transfer-encoding" in SKIP_HEADERS
    assert len(SKIP_HEADERS) == 5


# ---------------------------------------------------------------------------
# build_target_url
# ---------------------------------------------------------------------------

def test_build_target_url_full_http():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "https://example.com/page"
    request.headers = {}
    result = build_target_url(proxy, request)
    assert result == "https://example.com/page"


def test_build_target_url_full_https():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "https://secure.com/x"
    request.headers = {}
    result = build_target_url(proxy, request)
    assert result == "https://secure.com/x"


def test_build_target_url_with_host_header():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "/api/data"
    request.headers = {"Host": "cdn.example.com"}
    result = build_target_url(proxy, request)
    assert result == "http://cdn.example.com/api/data"


def test_build_target_url_with_authority_header():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "/data"
    request.headers = {":authority": "api.service.io"}
    result = build_target_url(proxy, request)
    assert result == "http://api.service.io/data"


def test_build_target_url_with_authority_https():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "/data"
    request.headers = {":authority": "api.service.io:443"}
    result = build_target_url(proxy, request)
    assert result == "https://api.service.io:443/data"


def test_build_target_url_with_scheme_https():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "/data"
    request.headers = {":authority": "api.service.io", ":scheme": "https"}
    result = build_target_url(proxy, request)
    assert result == "https://api.service.io/data"


def test_build_target_url_host_is_proxy_host():
    proxy = _make_proxy()
    proxy.config.host = "127.0.0.1"
    proxy.config.port = 9222
    request = MagicMock()
    request.path = "/data"
    request.headers = {"Host": "127.0.0.1"}
    result = build_target_url(proxy, request)
    assert result is None


def test_build_target_url_host_is_proxy_host_with_port():
    proxy = _make_proxy()
    proxy.config.host = "127.0.0.1"
    proxy.config.port = 9222
    request = MagicMock()
    request.path = "/data"
    request.headers = {"Host": "127.0.0.1:9222"}
    result = build_target_url(proxy, request)
    assert result is None


def test_build_target_url_with_referer():
    proxy = _make_proxy()
    page = MagicMock()
    page.url = "https://www.google.com/search?q=test"
    proxy._pages = {"abc123": page}
    request = MagicMock()
    request.path = "/results"
    request.headers = {"Referer": "http://127.0.0.1:9222/page/abc123"}
    result = build_target_url(proxy, request)
    assert result == "https://www.google.com/results"


def test_build_target_url_no_host_no_referer():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "/data"
    request.headers = {}
    result = build_target_url(proxy, request)
    assert result is None


def test_build_target_url_referer_no_matching_page():
    proxy = _make_proxy()
    proxy._pages = {}
    request = MagicMock()
    request.path = "/data"
    request.headers = {"Referer": "http://127.0.0.1:9222/page/nonexistent"}
    result = build_target_url(proxy, request)
    assert result is None


# ---------------------------------------------------------------------------
# handle_route — data: and about: URLs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_route_data_url():
    proxy = _make_proxy()
    route = _make_route(url="data:text/html,<h1>Hello</h1>")
    await handle_route(proxy, route)
    route.continue_.assert_awaited_once()
    route.abort.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_route_about_url():
    proxy = _make_proxy()
    route = _make_route(url="about:blank")
    await handle_route(proxy, route)
    route.continue_.assert_awaited_once()


# ---------------------------------------------------------------------------
# handle_route — normal request flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_route_forwards_request():
    proxy = _make_proxy()
    route = _make_route(url="https://example.com/", method="GET")
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"content-type": "text/html"}
    mock_response.body = b"<html></html>"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_response):
        await handle_route(proxy, route)
    route.fulfill.assert_awaited_once()
    assert proxy.stats["requests"] == 1
    assert proxy.stats["bytes_received"] == len(b"<html></html>")


@pytest.mark.asyncio
async def test_handle_route_response_none_aborts():
    proxy = _make_proxy()
    route = _make_route(url="https://example.com/")
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=None):
        await handle_route(proxy, route)
    route.abort.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_route_stats_error_on_exception():
    proxy = _make_proxy()
    route = _make_route(url="https://example.com/")
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, side_effect=Exception("boom")):
        await handle_route(proxy, route)
    assert proxy.stats["errors"] == 1
    route.abort.assert_awaited()


# ---------------------------------------------------------------------------
# handle_route — post_data with UnicodeDecodeError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_route_post_data_buffer_fallback():
    proxy = _make_proxy()
    route = _make_route(url="https://example.com/post", method="POST")
    route.request.post_data = MagicMock(side_effect=UnicodeDecodeError("", b"", 0, 1, ""))
    route.request.post_data_buffer = b"raw binary data"
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {}
    mock_response.body = b"ok"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_response):
        await handle_route(proxy, route)
    route.fulfill.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_route_post_data_both_fail():
    proxy = _make_proxy()
    route = _make_route(url="https://example.com/post", method="POST")
    route.request.post_data = MagicMock(side_effect=UnicodeDecodeError("", b"", 0, 1, ""))
    route.request.post_data_buffer = MagicMock(side_effect=Exception("no buffer"))
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {}
    mock_response.body = b"ok"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_response):
        await handle_route(proxy, route)
    route.fulfill.assert_awaited_once()


# ---------------------------------------------------------------------------
# handle_route — set-cookie parsing from dict headers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_route_set_cookie_from_dict():
    proxy = _make_proxy()
    route = _make_route(url="https://example.com/")
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"set-cookie": "session=abc123; Path=/; Secure"}
    mock_response.body = b"ok"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_response):
        await handle_route(proxy, route)
    proxy.cookie_jar.add_cookie.assert_called_once()
    cookie = proxy.cookie_jar.add_cookie.call_args[0][0]
    assert cookie["name"] == "session"
    assert cookie["value"] == "abc123"
    assert cookie["domain"] == "example.com"


@pytest.mark.asyncio
async def test_handle_route_set_cookie_list_of_tuples():
    proxy = _make_proxy()
    route = _make_route(url="https://example.com/")
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = [("set-cookie", "tok=xyz; Path=/")]
    mock_response.body = b"ok"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_response):
        await handle_route(proxy, route)
    proxy.cookie_jar.add_cookie.assert_called_once()
    cookie = proxy.cookie_jar.add_cookie.call_args[0][0]
    assert cookie["name"] == "tok"
    assert cookie["value"] == "xyz"


@pytest.mark.asyncio
async def test_handle_route_set_cookie_list_of_dicts():
    proxy = _make_proxy()
    route = _make_route(url="https://example.com/")
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = [{"name": "set-cookie", "value": "a=1; Path=/"}]
    mock_response.body = b"ok"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_response):
        await handle_route(proxy, route)
    proxy.cookie_jar.add_cookie.assert_called_once()
    cookie = proxy.cookie_jar.add_cookie.call_args[0][0]
    assert cookie["name"] == "a"
    assert cookie["value"] == "1"


@pytest.mark.asyncio
async def test_handle_route_set_cookie_invalid_format():
    proxy = _make_proxy()
    route = _make_route(url="https://example.com/")
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"set-cookie": "bad_cookie_no_equals"}
    mock_response.body = b"ok"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_response):
        await handle_route(proxy, route)
    proxy.cookie_jar.add_cookie.assert_not_called()


@pytest.mark.asyncio
async def test_handle_route_set_cookie_none_header():
    proxy = _make_proxy()
    route = _make_route(url="https://example.com/")
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Set-Cookie": None}
    mock_response.body = b"ok"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_response):
        await handle_route(proxy, route)
    proxy.cookie_jar.add_cookie.assert_not_called()


# ---------------------------------------------------------------------------
# handle_route — header filtering (SKIP_HEADERS)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_route_skips_csp_header():
    proxy = _make_proxy()
    route = _make_route(url="https://example.com/")
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {
        "content-security-policy": "default-src 'self'",
        "content-type": "text/html",
    }
    mock_response.body = b"ok"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_response):
        await handle_route(proxy, route)
    fulfilled_headers = route.fulfill.call_args[1]["headers"]
    assert "content-security-policy" not in fulfilled_headers
    assert "content-type" in fulfilled_headers


@pytest.mark.asyncio
async def test_handle_route_skips_xframe():
    proxy = _make_proxy()
    route = _make_route(url="https://example.com/")
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"x-frame-options": "DENY", "x-custom": "val"}
    mock_response.body = b"ok"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_response):
        await handle_route(proxy, route)
    fulfilled_headers = route.fulfill.call_args[1]["headers"]
    assert "x-frame-options" not in fulfilled_headers
    assert "x-custom" in fulfilled_headers


@pytest.mark.asyncio
async def test_handle_route_headers_as_list_of_tuples():
    proxy = _make_proxy()
    route = _make_route(url="https://example.com/")
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = [("content-type", "text/html"), ("x-extra", "yes")]
    mock_response.body = b"ok"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_response):
        await handle_route(proxy, route)
    fulfilled_headers = route.fulfill.call_args[1]["headers"]
    assert fulfilled_headers["content-type"] == "text/html"
    assert fulfilled_headers["x-extra"] == "yes"


@pytest.mark.asyncio
async def test_handle_route_headers_as_list_of_dicts():
    proxy = _make_proxy()
    route = _make_route(url="https://example.com/")
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = [{"name": "content-type", "value": "text/html"}]
    mock_response.body = b"ok"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_response):
        await handle_route(proxy, route)
    fulfilled_headers = route.fulfill.call_args[1]["headers"]
    assert fulfilled_headers["content-type"] == "text/html"


@pytest.mark.asyncio
async def test_handle_route_headers_empty_list():
    proxy = _make_proxy()
    route = _make_route(url="https://example.com/")
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = []
    mock_response.body = b"ok"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_response):
        await handle_route(proxy, route)
    fulfilled_headers = route.fulfill.call_args[1]["headers"]
    assert fulfilled_headers == {}


@pytest.mark.asyncio
async def test_handle_route_headers_none():
    proxy = _make_proxy()
    route = _make_route(url="https://example.com/")
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = None
    mock_response.body = b"ok"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_response):
        await handle_route(proxy, route)
    fulfilled_headers = route.fulfill.call_args[1]["headers"]
    assert fulfilled_headers == {}


@pytest.mark.asyncio
async def test_handle_route_headers_dict_skips_hsts():
    proxy = _make_proxy()
    route = _make_route(url="https://example.com/")
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {
        "strict-transport-security": "max-age=31536000",
        "content-encoding": "gzip",
        "transfer-encoding": "chunked",
    }
    mock_response.body = b"ok"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_response):
        await handle_route(proxy, route)
    fulfilled_headers = route.fulfill.call_args[1]["headers"]
    assert fulfilled_headers == {}


# ---------------------------------------------------------------------------
# handle_route — set-cookie with https scheme
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_route_set_cookie_https_secure():
    proxy = _make_proxy()
    route = _make_route(url="https://secure.com/login")
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"set-cookie": "token=abc; Path=/; Secure"}
    mock_response.body = b"ok"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_response):
        await handle_route(proxy, route)
    cookie = proxy.cookie_jar.add_cookie.call_args[0][0]
    assert cookie["secure"] is True


# ---------------------------------------------------------------------------
# forward_via_curl_cffi — happy path (with curl_cffi in sys.modules)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forward_via_curl_cffi_happy_path():
    proxy = _make_proxy()
    proxy.fingerprint.get_headers.return_value = {"accept": "text/html"}
    proxy.cookie_jar.get_for_request.return_value = "session=abc"

    mock_curl_mod = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/html"}
    mock_resp.content = b"response body"
    mock_curl_mod.request.return_value = mock_resp

    fake_curl = MagicMock()
    fake_curl.requests = mock_curl_mod

    with patch.dict("sys.modules", {"curl_cffi": fake_curl, "curl_cffi.requests": mock_curl_mod}):
        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=mock_resp):
            result = await forward_via_curl_cffi(
                proxy, method="GET", url="https://example.com/",
                headers={"Accept": "text/html"}, body=None
            )

    assert result.status == 200
    assert result.body == b"response body"
    assert result.headers["content-type"] == "text/html"


@pytest.mark.asyncio
async def test_forward_via_curl_cffi_with_body():
    proxy = _make_proxy()
    proxy.fingerprint.get_headers.return_value = {}
    proxy.cookie_jar.get_for_request.return_value = ""

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.headers = {}
    mock_resp.content = b""

    fake_curl = MagicMock()
    fake_curl_mod = MagicMock()
    fake_curl.requests = fake_curl_mod

    with patch.dict("sys.modules", {"curl_cffi": fake_curl, "curl_cffi.requests": fake_curl_mod}):
        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=mock_resp):
            result = await forward_via_curl_cffi(
                proxy, method="POST", url="https://example.com/api",
                headers={}, body="data"
            )
    assert result.status == 201
    assert proxy.stats["bytes_sent"] == 4


@pytest.mark.asyncio
async def test_forward_via_curl_cffi_skips_host_connection():
    proxy = _make_proxy()
    proxy.fingerprint.get_headers.return_value = {}
    proxy.cookie_jar.get_for_request.return_value = ""

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {}
    mock_resp.content = b""

    fake_curl = MagicMock()
    fake_curl_mod = MagicMock()
    fake_curl.requests = fake_curl_mod

    with patch.dict("sys.modules", {"curl_cffi": fake_curl, "curl_cffi.requests": fake_curl_mod}):
        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=mock_resp) as mock_thread:
            await forward_via_curl_cffi(
                proxy, method="GET", url="https://example.com/",
                headers={"Host": "evil.com", "Connection": "keep-alive", "Proxy-Connection": "no"},
                body=None
            )
            # Verify that the header filtering happened before calling to_thread
            call_args = mock_thread.call_args
            headers_arg = call_args[1]["headers"] if "headers" in call_args[1] else call_args[0][4]
            assert "Host" not in headers_arg
            assert "Connection" not in headers_arg
            assert "Proxy-Connection" not in headers_arg


@pytest.mark.asyncio
async def test_forward_via_curl_cffi_headers_list():
    proxy = _make_proxy()
    proxy.fingerprint.get_headers.return_value = {}
    proxy.cookie_jar.get_for_request.return_value = ""

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = [("content-type", "text/html"), ("x-custom", "val")]
    mock_resp.content = b""

    fake_curl = MagicMock()
    fake_curl_mod = MagicMock()
    fake_curl.requests = fake_curl_mod

    with patch.dict("sys.modules", {"curl_cffi": fake_curl, "curl_cffi.requests": fake_curl_mod}):
        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=mock_resp):
            result = await forward_via_curl_cffi(
                proxy, method="GET", url="https://example.com/",
                headers={}, body=None
            )
    assert result.headers["content-type"] == "text/html"
    assert result.headers["x-custom"] == "val"


@pytest.mark.asyncio
async def test_forward_via_curl_cffi_headers_none():
    proxy = _make_proxy()
    proxy.fingerprint.get_headers.return_value = {}
    proxy.cookie_jar.get_for_request.return_value = ""

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = None
    mock_resp.content = b""

    fake_curl = MagicMock()
    fake_curl_mod = MagicMock()
    fake_curl.requests = fake_curl_mod

    with patch.dict("sys.modules", {"curl_cffi": fake_curl, "curl_cffi.requests": fake_curl_mod}):
        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=mock_resp):
            result = await forward_via_curl_cffi(
                proxy, method="GET", url="https://example.com/",
                headers={}, body=None
            )
    assert result.headers == {}


@pytest.mark.asyncio
async def test_forward_via_curl_cffi_chatgpt_cookie_log():
    proxy = _make_proxy()
    proxy.fingerprint.get_headers.return_value = {}
    proxy.cookie_jar.get_for_request.return_value = "session=abc"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {}
    mock_resp.content = b""

    fake_curl = MagicMock()
    fake_curl_mod = MagicMock()
    fake_curl.requests = fake_curl_mod

    with patch.dict("sys.modules", {"curl_cffi": fake_curl, "curl_cffi.requests": fake_curl_mod}):
        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=mock_resp):
            await forward_via_curl_cffi(
                proxy, method="GET", url="https://chatgpt.com/api",
                headers={}, body=None
            )


@pytest.mark.asyncio
async def test_forward_via_curl_cffi_chatgpt_no_cookies_log():
    proxy = _make_proxy()
    proxy.fingerprint.get_headers.return_value = {}
    proxy.cookie_jar.get_for_request.return_value = ""

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {}
    mock_resp.content = b""

    fake_curl = MagicMock()
    fake_curl_mod = MagicMock()
    fake_curl.requests = fake_curl_mod

    with patch.dict("sys.modules", {"curl_cffi": fake_curl, "curl_cffi.requests": fake_curl_mod}):
        with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=mock_resp):
            await forward_via_curl_cffi(
                proxy, method="GET", url="https://chatgpt.com/api",
                headers={}, body=None
            )


@pytest.mark.asyncio
async def test_forward_via_curl_cffi_falls_back_to_aiohttp():
    proxy = _make_proxy()
    proxy.fingerprint.get_headers.return_value = {}
    proxy.cookie_jar.get_for_request.return_value = ""

    fake_curl = MagicMock()
    fake_curl_mod = MagicMock()
    fake_curl.requests = fake_curl_mod

    with patch.dict("sys.modules", {"curl_cffi": fake_curl, "curl_cffi.requests": fake_curl_mod}):
        with patch("asyncio.to_thread", new_callable=AsyncMock, side_effect=Exception("curl failed")):
            with patch("tokenade.core.proxy.cdp_routing.forward_via_aiohttp", new_callable=AsyncMock) as mock_aio:
                mock_aio.return_value = MagicMock(status=500, headers={}, body=b"fallback")
                await forward_via_curl_cffi(
                    proxy, method="GET", url="https://example.com/",
                    headers={}, body=None
                )
    mock_aio.assert_awaited_once()


# ---------------------------------------------------------------------------
# forward_via_aiohttp
# ---------------------------------------------------------------------------

def _mock_aiohttp_response(status=200, headers=None, body=b"ok"):
    """Create a proper async context manager mock for aiohttp responses."""
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.headers = headers or {}
    mock_resp.read = AsyncMock(return_value=body)
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


def _make_mock_session(status=200, headers=None, body=b"ok"):
    """Create a mock aiohttp session where request() returns an async context manager."""
    mock_session = AsyncMock()
    mock_session.closed = False
    # request() must NOT be async — it's called as `async with session.request(...)`
    # so request() itself is sync, returning an async context manager
    mock_session.request = MagicMock(return_value=_mock_aiohttp_response(status, headers, body))
    return mock_session


@pytest.mark.asyncio
async def test_forward_via_aiohttp_creates_session():
    proxy = _make_proxy()
    proxy._shared_http_session = None
    proxy._http_session = None
    proxy._session_lock = asyncio.Lock()
    proxy.fingerprint.get_headers.return_value = {}
    proxy.cookie_jar.get_for_request.return_value = ""

    mock_session = _make_mock_session(200, {"content-type": "text/html"}, b"ok")

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await forward_via_aiohttp(
            proxy, method="GET", url="https://example.com/",
            headers={}, body=None
        )
    assert result.status == 200
    assert result.body == b"ok"


@pytest.mark.asyncio
async def test_forward_via_aiohttp_uses_shared_session():
    proxy = _make_proxy()
    mock_shared = _make_mock_session(200, {}, b"data")
    proxy._shared_http_session = mock_shared
    proxy.fingerprint.get_headers.return_value = {}
    proxy.cookie_jar.get_for_request.return_value = ""

    result = await forward_via_aiohttp(
        proxy, method="GET", url="https://example.com/",
        headers={}, body=None
    )
    assert result.status == 200
    mock_shared.request.assert_called_once()


@pytest.mark.asyncio
async def test_forward_via_aiohttp_shared_session_closed_creates_new():
    proxy = _make_proxy()
    mock_shared = MagicMock()
    mock_shared.closed = True
    proxy._shared_http_session = mock_shared
    proxy._http_session = None
    proxy._session_lock = asyncio.Lock()
    proxy.fingerprint.get_headers.return_value = {}
    proxy.cookie_jar.get_for_request.return_value = ""

    mock_session = _make_mock_session(200, {}, b"data")

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await forward_via_aiohttp(
            proxy, method="GET", url="https://example.com/",
            headers={}, body=None
        )
    assert result.status == 200


@pytest.mark.asyncio
async def test_forward_via_aiohttp_skips_host_connection():
    proxy = _make_proxy()
    proxy._shared_http_session = None
    proxy._http_session = None
    proxy._session_lock = asyncio.Lock()
    proxy.fingerprint.get_headers.return_value = {}
    proxy.cookie_jar.get_for_request.return_value = ""

    mock_session = _make_mock_session(200, {}, b"ok")

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await forward_via_aiohttp(
            proxy, method="GET", url="https://example.com/",
            headers={"Host": "evil.com", "Connection": "keep-alive"},
            body=None
        )
    call_kwargs = mock_session.request.call_args[1]
    assert "Host" not in call_kwargs["headers"]
    assert "Connection" not in call_kwargs["headers"]


@pytest.mark.asyncio
async def test_forward_via_aiohttp_with_cookies():
    proxy = _make_proxy()
    proxy._shared_http_session = None
    proxy._http_session = None
    proxy._session_lock = asyncio.Lock()
    proxy.fingerprint.get_headers.return_value = {}
    proxy.cookie_jar.get_for_request.return_value = "session=abc"

    mock_session = _make_mock_session(200, {}, b"ok")

    with patch("aiohttp.ClientSession", return_value=mock_session):
        await forward_via_aiohttp(
            proxy, method="GET", url="https://example.com/",
            headers={}, body=None
        )
    call_kwargs = mock_session.request.call_args[1]
    assert call_kwargs["headers"]["cookie"] == "session=abc"


@pytest.mark.asyncio
async def test_forward_via_aiohttp_failure_returns_none():
    proxy = _make_proxy()
    proxy._shared_http_session = None
    proxy._http_session = None
    proxy._session_lock = asyncio.Lock()
    proxy.fingerprint.get_headers.return_value = {}
    proxy.cookie_jar.get_for_request.return_value = ""

    mock_session = AsyncMock()
    mock_session.closed = False
    mock_session.request = MagicMock(side_effect=Exception("conn refused"))

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await forward_via_aiohttp(
            proxy, method="GET", url="https://example.com/",
            headers={}, body=None
        )
    assert result is None


@pytest.mark.asyncio
async def test_forward_via_aiohttp_existing_session_reused():
    proxy = _make_proxy()
    proxy._shared_http_session = None
    existing = _make_mock_session(200, {}, b"data")
    proxy._http_session = existing
    proxy.fingerprint.get_headers.return_value = {}
    proxy.cookie_jar.get_for_request.return_value = ""

    result = await forward_via_aiohttp(
        proxy, method="GET", url="https://example.com/",
        headers={}, body=None
    )
    assert result.status == 200
    existing.request.assert_called_once()


# ---------------------------------------------------------------------------
# handle_proxy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_proxy_api_routes():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "/api/status"
    request.method = "GET"
    request.headers = {}
    await handle_proxy(proxy, request)
    proxy._handle_status.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_handle_proxy_redirects_proxy_path():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "/proxy"
    request.headers = {}
    with pytest.raises(web.HTTPFound):
        await handle_proxy(proxy, request)


@pytest.mark.asyncio
async def test_handle_proxy_no_target_url():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "/data"
    request.headers = {}
    result = await handle_proxy(proxy, request)
    assert result.status == 400


@pytest.mark.asyncio
async def test_handle_proxy_unsafe_url():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "http://192.168.1.1/admin"
    request.headers = {}
    result = await handle_proxy(proxy, request)
    assert result.status == 403


@pytest.mark.asyncio
async def test_handle_proxy_forward_failure():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "https://example.com/"
    request.method = "GET"
    request.headers = {}
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=None):
        result = await handle_proxy(proxy, request)
    assert result.status == 502


@pytest.mark.asyncio
async def test_handle_proxy_happy_path():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "https://example.com/"
    request.method = "GET"
    request.headers = {}
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.headers = {"content-type": "text/html"}
    mock_resp.body = b"<html></html>"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_resp):
        result = await handle_proxy(proxy, request)
    assert result.status == 200
    assert proxy.stats["requests"] == 1


@pytest.mark.asyncio
async def test_handle_proxy_skips_csp():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "https://example.com/"
    request.method = "GET"
    request.headers = {}
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.headers = {"content-security-policy": "default-src 'self'", "x-custom": "val"}
    mock_resp.body = b"ok"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_resp):
        result = await handle_proxy(proxy, request)
    assert "content-security-policy" not in result.headers
    assert "x-custom" in result.headers


@pytest.mark.asyncio
async def test_handle_proxy_post_method():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "https://example.com/api"
    request.method = "POST"
    request.headers = {}
    request.read = AsyncMock(return_value=b"body")
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.headers = {}
    mock_resp.body = b"ok"
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, return_value=mock_resp):
        result = await handle_proxy(proxy, request)
    assert result.status == 200


@pytest.mark.asyncio
async def test_handle_proxy_exception():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "https://example.com/"
    request.method = "GET"
    request.headers = {}
    with patch("tokenade.core.proxy.cdp_routing.forward_via_curl_cffi", new_callable=AsyncMock, side_effect=Exception("boom")):
        result = await handle_proxy(proxy, request)
    assert result.status == 502
    assert proxy.stats["errors"] == 1


# ---------------------------------------------------------------------------
# handle_api
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_api_stats():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "/api/stats"
    await handle_api(proxy, request)
    proxy._handle_stats.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_handle_api_page_html():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "/api/page/abc123/html"
    result = await handle_api(proxy, request)
    assert isinstance(result, web.Response)


@pytest.mark.asyncio
async def test_handle_api_page_screenshot():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "/api/page/abc123/screenshot"
    result = await handle_api(proxy, request)
    assert isinstance(result, web.Response)


@pytest.mark.asyncio
async def test_handle_api_not_found():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "/api/unknown"
    result = await handle_api(proxy, request)
    assert result.status == 404


# ---------------------------------------------------------------------------
# handle_page_html
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_page_html_invalid_path():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "/api/page"
    result = await handle_page_html(proxy, request)
    assert result.status == 400


@pytest.mark.asyncio
async def test_handle_page_html_not_found():
    proxy = _make_proxy()
    proxy._pages = {}
    request = MagicMock()
    request.path = "/api/page/nonexistent/html"
    result = await handle_page_html(proxy, request)
    assert result.status == 404


@pytest.mark.asyncio
async def test_handle_page_html_success():
    proxy = _make_proxy()
    page = AsyncMock()
    page.content = AsyncMock(return_value="<html><head></head><body></body></html>")
    page.url = "https://example.com/page1"
    proxy._pages = {"abc": page}
    request = MagicMock()
    request.path = "/api/page/abc/html"
    result = await handle_page_html(proxy, request)
    assert result.status == 200
    assert b"<base href" in result.body


@pytest.mark.asyncio
async def test_handle_page_html_head_uppercase():
    proxy = _make_proxy()
    page = AsyncMock()
    page.content = AsyncMock(return_value="<HTML><HEAD></HEAD><BODY></BODY></HTML>")
    page.url = "https://example.com/page1"
    proxy._pages = {"abc": page}
    request = MagicMock()
    request.path = "/api/page/abc/html"
    result = await handle_page_html(proxy, request)
    assert b"<base href" in result.body


@pytest.mark.asyncio
async def test_handle_page_html_about_url_no_base():
    proxy = _make_proxy()
    page = AsyncMock()
    page.content = AsyncMock(return_value="<html><head></head></html>")
    page.url = "about:blank"
    proxy._pages = {"abc": page}
    request = MagicMock()
    request.path = "/api/page/abc/html"
    result = await handle_page_html(proxy, request)
    assert b"<base href" not in result.body


@pytest.mark.asyncio
async def test_handle_page_html_no_url():
    proxy = _make_proxy()
    page = AsyncMock()
    page.content = AsyncMock(return_value="<html><head></head></html>")
    page.url = None
    proxy._pages = {"abc": page}
    request = MagicMock()
    request.path = "/api/page/abc/html"
    result = await handle_page_html(proxy, request)
    assert b"<base href" not in result.body


@pytest.mark.asyncio
async def test_handle_page_html_content_exception():
    proxy = _make_proxy()
    page = AsyncMock()
    page.content = AsyncMock(side_effect=Exception("page crash"))
    proxy._pages = {"abc": page}
    request = MagicMock()
    request.path = "/api/page/abc/html"
    result = await handle_page_html(proxy, request)
    assert result.status == 500


# ---------------------------------------------------------------------------
# handle_page_screenshot
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_page_screenshot_invalid_path():
    proxy = _make_proxy()
    request = MagicMock()
    request.path = "/api/page"
    result = await handle_page_screenshot(proxy, request)
    assert result.status == 400


@pytest.mark.asyncio
async def test_handle_page_screenshot_not_found():
    proxy = _make_proxy()
    proxy._pages = {}
    request = MagicMock()
    request.path = "/api/page/nonexistent/screenshot"
    result = await handle_page_screenshot(proxy, request)
    assert result.status == 404


@pytest.mark.asyncio
async def test_handle_page_screenshot_success():
    proxy = _make_proxy()
    page = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"\x89PNG...")
    proxy._pages = {"abc": page}
    request = MagicMock()
    request.path = "/api/page/abc/screenshot"
    result = await handle_page_screenshot(proxy, request)
    assert result.status == 200
    assert result.body == b"\x89PNG..."
    assert result.content_type == "image/png"


@pytest.mark.asyncio
async def test_handle_page_screenshot_exception():
    proxy = _make_proxy()
    page = AsyncMock()
    page.screenshot = AsyncMock(side_effect=Exception("screenshot fail"))
    proxy._pages = {"abc": page}
    request = MagicMock()
    request.path = "/api/page/abc/screenshot"
    result = await handle_page_screenshot(proxy, request)
    assert result.status == 500
