"""Comprehensive tests for cdp_gui module — targeting 50%+ coverage."""

from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
from aiohttp import web

from tokenade.core.proxy.cdp_gui import (
    handle_gui,
    handle_browse_post,
    handle_page,
)


def _make_proxy(**overrides):
    """Create a mock CDPProxy with sensible defaults."""
    proxy = MagicMock()
    proxy.config = MagicMock()
    proxy.config.host = "127.0.0.1"
    proxy.config.port = 9222
    proxy.config.timeout = 30
    proxy.config.use_fingerprint = False
    proxy.session = {
        "site_name": "test-site",
        "source_device": {"browser": "firefox", "platform": "Linux"},
        "tls_profile": {"impersonate": "chrome120"},
    }
    proxy.cookie_jar = MagicMock()
    proxy.cookie_jar.to_list.return_value = [{"name": "c1"}, {"name": "c2"}]
    proxy._pages = {}
    proxy._page_meta = {}
    proxy._max_pages = 20
    proxy._context = AsyncMock()
    proxy._cleanup_expired_pages = MagicMock()
    proxy._close_page = AsyncMock()
    proxy._navigate_page = AsyncMock()
    for k, v in overrides.items():
        setattr(proxy, k, v)
    return proxy


def _make_request(method="GET", path="/", post_data=None, post=None, match_info=None):
    """Create a mock aiohttp request."""
    request = MagicMock()
    request.method = method
    request.path = path
    request.headers = {}
    request.match_info = match_info or {}
    if post_data is not None:
        request.post = AsyncMock(return_value=post_data)
    else:
        request.post = AsyncMock(return_value={})
    request.read = AsyncMock(return_value=b"")
    return request


# ---------------------------------------------------------------------------
# handle_gui
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_gui_returns_html():
    proxy = _make_proxy()
    request = _make_request()
    result = await handle_gui(proxy, request)
    assert result.status == 200
    assert result.content_type == "text/html"


@pytest.mark.asyncio
async def test_handle_gui_contains_site_name():
    proxy = _make_proxy()
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert "test-site" in body


@pytest.mark.asyncio
async def test_handle_gui_contains_browser():
    proxy = _make_proxy()
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert "firefox" in body


@pytest.mark.asyncio
async def test_handle_gui_contains_platform():
    proxy = _make_proxy()
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert "Linux" in body


@pytest.mark.asyncio
async def test_handle_gui_contains_cookie_count():
    proxy = _make_proxy()
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert "2" in body


@pytest.mark.asyncio
async def test_handle_gui_contains_tls_profile():
    proxy = _make_proxy()
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert "chrome120" in body


@pytest.mark.asyncio
async def test_handle_gui_contains_port():
    proxy = _make_proxy()
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert "9222" in body


@pytest.mark.asyncio
async def test_handle_gui_xss_protection_site_name():
    """The site_name is escaped — <script> should become &lt;script&gt; in the output."""
    proxy = _make_proxy()
    proxy.session["site_name"] = '<script>alert("xss")</script>'
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert "&lt;script&gt;" in body
    # The title element should contain the escaped version
    assert 'Tokenade CDP Proxy - &lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;' in body


@pytest.mark.asyncio
async def test_handle_gui_xss_in_browser():
    """The browser name is escaped."""
    proxy = _make_proxy()
    proxy.session["source_device"]["browser"] = '<img onerror="alert(1)">'
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert "&lt;img" in body


@pytest.mark.asyncio
async def test_handle_gui_xss_in_platform():
    """The platform is escaped."""
    proxy = _make_proxy()
    proxy.session["source_device"]["platform"] = '"><script>alert(1)</script>'
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert "&lt;script&gt;" in body


@pytest.mark.asyncio
async def test_handle_gui_default_site_name():
    proxy = _make_proxy()
    proxy.session["site_name"] = "unknown"
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert "unknown" in body


@pytest.mark.asyncio
async def test_handle_gui_empty_source_device():
    proxy = _make_proxy()
    proxy.session["source_device"] = {}
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert "unknown" in body


@pytest.mark.asyncio
async def test_handle_gui_contains_browse_form():
    proxy = _make_proxy()
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert '/browse' in body
    assert 'POST' in body


@pytest.mark.asyncio
async def test_handle_gui_contains_architecture():
    proxy = _make_proxy()
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert 'curl-cffi' in body
    assert 'Playwright' in body


@pytest.mark.asyncio
async def test_handle_gui_contains_stats_js():
    proxy = _make_proxy()
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert 'updateStats' in body
    assert 'formatBytes' in body


@pytest.mark.asyncio
async def test_handle_gui_empty_cookies():
    proxy = _make_proxy()
    proxy.cookie_jar.to_list.return_value = []
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert "0" in body


# ---------------------------------------------------------------------------
# handle_browse_post
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_browse_post_no_url():
    proxy = _make_proxy()
    request = _make_request(method="POST", post_data={})
    result = await handle_browse_post(proxy, request)
    assert result.status == 400
    body = result.body.decode()
    assert "No URL provided" in body


@pytest.mark.asyncio
async def test_browse_post_prepends_https():
    proxy = _make_proxy()
    request = _make_request(method="POST", post_data={"url": "example.com"})
    with patch("tokenade.core.proxy.cdp_gui.is_safe_url", return_value=True):
        with pytest.raises(web.HTTPFound) as exc_info:
            await handle_browse_post(proxy, request)
    assert "/page/" in exc_info.value.location


@pytest.mark.asyncio
async def test_browse_post_invalid_url_no_hostname():
    proxy = _make_proxy()
    request = _make_request(method="POST", post_data={"url": "://invalid"})
    result = await handle_browse_post(proxy, request)
    assert result.status == 400
    body = result.body.decode()
    assert "Invalid URL" in body


@pytest.mark.asyncio
async def test_browse_post_unsafe_url():
    proxy = _make_proxy()
    request = _make_request(method="POST", post_data={"url": "http://192.168.1.1/"})
    with patch("tokenade.core.proxy.cdp_gui.is_safe_url", return_value=False):
        result = await handle_browse_post(proxy, request)
    assert result.status == 403
    body = result.body.decode()
    assert "blocked" in body.lower()


@pytest.mark.asyncio
async def test_browse_post_max_pages_evicts_oldest():
    proxy = _make_proxy()
    proxy._max_pages = 2
    proxy._pages = {"old1": MagicMock(), "old2": MagicMock()}
    proxy._page_meta = {
        "old1": {"created": 100},
        "old2": {"created": 200},
    }
    mock_page = AsyncMock()
    proxy._context.new_page = AsyncMock(return_value=mock_page)
    request = _make_request(method="POST", post_data={"url": "https://example.com"})
    with patch("tokenade.core.proxy.cdp_gui.is_safe_url", return_value=True):
        with pytest.raises(web.HTTPFound):
            await handle_browse_post(proxy, request)
    proxy._close_page.assert_awaited_once_with("old1")


@pytest.mark.asyncio
async def test_browse_post_creates_page():
    proxy = _make_proxy()
    proxy._pages = {}
    proxy._page_meta = {}
    mock_page = AsyncMock()
    proxy._context.new_page = AsyncMock(return_value=mock_page)
    request = _make_request(method="POST", post_data={"url": "https://example.com"})
    with patch("tokenade.core.proxy.cdp_gui.is_safe_url", return_value=True):
        with pytest.raises(web.HTTPFound) as exc_info:
            await handle_browse_post(proxy, request)
    assert "/page/" in exc_info.value.location


@pytest.mark.asyncio
async def test_browse_post_cleanup_expired_called():
    proxy = _make_proxy()
    proxy._pages = {}
    proxy._page_meta = {}
    mock_page = AsyncMock()
    proxy._context.new_page = AsyncMock(return_value=mock_page)
    request = _make_request(method="POST", post_data={"url": "https://example.com"})
    with patch("tokenade.core.proxy.cdp_gui.is_safe_url", return_value=True):
        with pytest.raises(web.HTTPFound):
            await handle_browse_post(proxy, request)
    proxy._cleanup_expired_pages.assert_called_once()


@pytest.mark.asyncio
async def test_browse_post_with_route_setup():
    proxy = _make_proxy()
    proxy.config.use_fingerprint = True
    proxy._pages = {}
    proxy._page_meta = {}
    mock_page = AsyncMock()
    proxy._context.new_page = AsyncMock(return_value=mock_page)
    request = _make_request(method="POST", post_data={"url": "https://example.com"})
    with patch("tokenade.core.proxy.cdp_gui.is_safe_url", return_value=True):
        with pytest.raises(web.HTTPFound):
            await handle_browse_post(proxy, request)
    mock_page.route.assert_awaited_once()


@pytest.mark.asyncio
async def test_browse_post_navigates_page():
    proxy = _make_proxy()
    proxy._pages = {}
    proxy._page_meta = {}
    mock_page = AsyncMock()
    proxy._context.new_page = AsyncMock(return_value=mock_page)
    request = _make_request(method="POST", post_data={"url": "https://example.com"})
    with patch("tokenade.core.proxy.cdp_gui.is_safe_url", return_value=True):
        with pytest.raises(web.HTTPFound):
            await handle_browse_post(proxy, request)
    # create_task is called but not awaited immediately; use called() not awaited()
    assert proxy._navigate_page.called


@pytest.mark.asyncio
async def test_browse_post_general_exception():
    proxy = _make_proxy()
    proxy._pages = {}
    proxy._page_meta = {}
    proxy._context.new_page = AsyncMock(side_effect=Exception("browser crash"))
    request = _make_request(method="POST", post_data={"url": "https://example.com"})
    with patch("tokenade.core.proxy.cdp_gui.is_safe_url", return_value=True):
        result = await handle_browse_post(proxy, request)
    assert result.status == 500
    body = result.body.decode()
    assert "Failed" in body


@pytest.mark.asyncio
async def test_browse_post_existing_http_prefix():
    proxy = _make_proxy()
    proxy._pages = {}
    proxy._page_meta = {}
    mock_page = AsyncMock()
    proxy._context.new_page = AsyncMock(return_value=mock_page)
    request = _make_request(method="POST", post_data={"url": "http://example.com"})
    with patch("tokenade.core.proxy.cdp_gui.is_safe_url", return_value=True):
        with pytest.raises(web.HTTPFound):
            await handle_browse_post(proxy, request)


@pytest.mark.asyncio
async def test_browse_post_existing_https_prefix():
    proxy = _make_proxy()
    proxy._pages = {}
    proxy._page_meta = {}
    mock_page = AsyncMock()
    proxy._context.new_page = AsyncMock(return_value=mock_page)
    request = _make_request(method="POST", post_data={"url": "https://example.com"})
    with patch("tokenade.core.proxy.cdp_gui.is_safe_url", return_value=True):
        with pytest.raises(web.HTTPFound):
            await handle_browse_post(proxy, request)


# ---------------------------------------------------------------------------
# handle_page
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_page_not_found():
    proxy = _make_proxy()
    proxy._pages = {}
    request = _make_request(match_info={"page_id": "nonexistent"})
    result = await handle_page(proxy, request)
    assert result.status == 404
    body = result.body.decode()
    assert "Page not found" in body


@pytest.mark.asyncio
async def test_handle_page_found():
    proxy = _make_proxy()
    page = MagicMock()
    page.url = "https://example.com/page1"
    proxy._pages = {"abc123": page}
    request = _make_request(match_info={"page_id": "abc123"})
    result = await handle_page(proxy, request)
    assert result.status == 200
    assert result.content_type == "text/html"
    body = result.body.decode()
    assert "https://example.com/page1" in body


@pytest.mark.asyncio
async def test_handle_page_escapes_url():
    """The URL in the toolbar should be escaped to prevent XSS."""
    proxy = _make_proxy()
    page = MagicMock()
    page.url = '"><script>alert("xss")</script>'
    proxy._pages = {"abc": page}
    request = _make_request(match_info={"page_id": "abc"})
    result = await handle_page(proxy, request)
    body = result.body.decode()
    # The escaped URL should appear in the toolbar span, not raw script
    assert "&quot;" in body or "&lt;" in body
    # The escaped value in the span
    assert "&gt;&lt;script&gt;" in body or "&lt;script&gt;" in body


@pytest.mark.asyncio
async def test_handle_page_none_url():
    proxy = _make_proxy()
    page = MagicMock()
    page.url = None
    proxy._pages = {"abc": page}
    request = _make_request(match_info={"page_id": "abc"})
    result = await handle_page(proxy, request)
    assert result.status == 200


@pytest.mark.asyncio
async def test_handle_page_empty_url():
    proxy = _make_proxy()
    page = MagicMock()
    page.url = ""
    proxy._pages = {"abc": page}
    request = _make_request(match_info={"page_id": "abc"})
    result = await handle_page(proxy, request)
    assert result.status == 200


@pytest.mark.asyncio
async def test_handle_page_contains_toolbar():
    proxy = _make_proxy()
    page = MagicMock()
    page.url = "https://example.com/"
    proxy._pages = {"abc": page}
    request = _make_request(match_info={"page_id": "abc"})
    result = await handle_page(proxy, request)
    body = result.body.decode()
    assert "toolbar" in body
    assert 'Back' in body


@pytest.mark.asyncio
async def test_handle_page_contains_screenshot_script():
    proxy = _make_proxy()
    page = MagicMock()
    page.url = "https://example.com/"
    proxy._pages = {"abc": page}
    request = _make_request(match_info={"page_id": "abc"})
    result = await handle_page(proxy, request)
    body = result.body.decode()
    assert "refreshScreenshot" in body
    assert "/api/page/abc/screenshot" in body


@pytest.mark.asyncio
async def test_handle_page_contains_loading_div():
    proxy = _make_proxy()
    page = MagicMock()
    page.url = "https://example.com/"
    proxy._pages = {"abc": page}
    request = _make_request(match_info={"page_id": "abc"})
    result = await handle_page(proxy, request)
    body = result.body.decode()
    assert "Loading screenshot" in body


@pytest.mark.asyncio
async def test_handle_page_contains_title():
    proxy = _make_proxy()
    page = MagicMock()
    page.url = "https://example.com/"
    proxy._pages = {"abc": page}
    request = _make_request(match_info={"page_id": "abc"})
    result = await handle_page(proxy, request)
    body = result.body.decode()
    assert "Tokenade - Browsing" in body


@pytest.mark.asyncio
async def test_handle_page_exception():
    proxy = _make_proxy()
    page = MagicMock()
    type(page).url = PropertyMock(side_effect=Exception("prop fail"))
    proxy._pages = {"abc": page}
    request = _make_request(match_info={"page_id": "abc"})
    result = await handle_page(proxy, request)
    assert result.status == 500
    body = result.body.decode()
    assert "Error loading page" in body


@pytest.mark.asyncio
async def test_handle_page_page_id_in_screenshot_url():
    proxy = _make_proxy()
    page = MagicMock()
    page.url = "https://example.com/"
    proxy._pages = {"my_unique_id": page}
    request = _make_request(match_info={"page_id": "my_unique_id"})
    result = await handle_page(proxy, request)
    body = result.body.decode()
    assert "/api/page/my_unique_id/screenshot" in body


# ---------------------------------------------------------------------------
# handle_gui — edge cases for missing session fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_gui_no_tls_profile():
    proxy = _make_proxy()
    proxy.session["tls_profile"] = {}
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert "unknown" in body


@pytest.mark.asyncio
async def test_handle_gui_no_source_device():
    proxy = _make_proxy()
    proxy.session.pop("source_device", None)
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert "unknown" in body


@pytest.mark.asyncio
async def test_handle_gui_empty_session():
    proxy = _make_proxy()
    proxy.session = {}
    proxy.cookie_jar.to_list.return_value = []
    request = _make_request()
    result = await handle_gui(proxy, request)
    assert result.status == 200


@pytest.mark.asyncio
async def test_handle_gui_contains_service_worker_removal():
    proxy = _make_proxy()
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert "serviceWorker" in body
    assert "unregister" in body


@pytest.mark.asyncio
async def test_handle_gui_contains_session_status_js():
    proxy = _make_proxy()
    request = _make_request()
    result = await handle_gui(proxy, request)
    body = result.body.decode()
    assert "updateSessionStatus" in body
    assert "refreshSession" in body
