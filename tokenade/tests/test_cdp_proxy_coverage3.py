"""
Comprehensive tests for cdp_proxy.py — covering uncovered lines:
21-22, 81-83, 232, 450-451, 455-462, 464, 477-542, 545, 548, 551, 554, 557, 560, 563, 566,
569, 572, 575, 580-591, 616, 629-631, 649-764, 774-775, 777, 779, 781, 786.
"""

import asyncio
import concurrent.futures
import time
import unittest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

from aiohttp import web


def _run_async(coro):
    """Run async coroutine in a new event loop via ThreadPoolExecutor."""
    with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result(timeout=10)


def _make_proxy():
    from tokenade.core.proxy.cdp_proxy import CDPProxy
    session = {
        "cookies": [],
        "site_name": "test",
        "fingerprint": {},
        "tls_profile": {},
        "source_device": {},
    }
    return CDPProxy(session)


class TestCDPProxyCoverage3(unittest.TestCase):
    def setUp(self):
        self.proxy = _make_proxy()

    # ── Lines 21-22: HAS_PLAYWRIGHT = False branch ────────────────

    @patch("tokenade.core.proxy.cdp_proxy.HAS_PLAYWRIGHT", False)
    def test_start_no_playwright(self):
        async def _run():
            proxy = _make_proxy()
            with self.assertRaises(RuntimeError) as ctx:
                await proxy.start()
            self.assertIn("Playwright is required", str(ctx.exception))

        _run_async(_run())

    # ── Lines 81-83: _strip_duplicate_headers error handling ───────

    def test_strip_duplicate_headers_error(self):
        """Lines 81-83: Trigger the except clause by passing an object whose find() raises ValueError."""
        from tokenade.core.proxy.cdp_proxy import _strip_duplicate_headers

        class _BytesFindError:
            """Bytes-like object whose find() raises ValueError."""
            def find(self, sub, start=0, end=None):
                raise ValueError("simulated find error")

            def __getitem__(self, key):
                return b""[key]

            def __len__(self):
                return 0

        raw = _BytesFindError()
        result = _strip_duplicate_headers(raw)
        self.assertIs(result, raw)

    def test_strip_duplicate_headers_returns_raw_on_key_error(self):
        from tokenade.core.proxy.cdp_proxy import _strip_duplicate_headers

        class _BytesKeyError:
            """Bytes-like object whose find() raises KeyError."""
            def find(self, sub, start=0, end=None):
                raise KeyError("simulated key error")

            def __getitem__(self, key):
                return b""[key]

            def __len__(self):
                return 0

        raw = _BytesKeyError()
        result = _strip_duplicate_headers(raw)
        self.assertIs(result, raw)

    # ── Line 232: _handle_legacy_redirect delegates ────────────────

    def test_handle_legacy_redirect(self):
        async def _run():
            proxy = _make_proxy()
            request = MagicMock()
            with self.assertRaises(web.HTTPFound):
                await proxy._handle_legacy_redirect(request)

        _run_async(_run())

    # ── Lines 450-451: _handle_browse_post when max_pages reached ──

    def test_handle_browse_post_max_pages(self):
        async def _run():
            proxy = _make_proxy()
            proxy._max_pages = 2
            # Create two existing pages with old timestamps
            old_page1 = AsyncMock()
            old_page2 = AsyncMock()
            proxy._pages = {"old1": old_page1, "old2": old_page2}
            proxy._page_meta = {
                "old1": {"created": time.time() - 100},
                "old2": {"created": time.time() - 200},
            }

            new_page = AsyncMock()
            new_page.url = "https://example.com"
            proxy._context = AsyncMock()
            proxy._context.new_page.return_value = new_page

            # Mock request
            request = MagicMock()

            async def fake_post():
                return {"url": "https://example.com"}

            request.post = fake_post

            # Patch is_safe_url to allow the URL, and _navigate_page to avoid actual navigation
            with patch("tokenade.core.proxy.cdp_proxy.is_safe_url", return_value=True):
                with patch.object(proxy, "_navigate_page", new_callable=AsyncMock):
                    with patch.object(proxy, "_close_page", new_callable=AsyncMock) as mock_close:
                        # The oldest page should be closed (old2 has earlier created time)
                        try:
                            await proxy._handle_browse_post(request)
                        except web.HTTPFound as e:
                            # Expected redirect
                            self.assertIn("/page/", str(e.location))

                        # Verify the oldest page was evicted
                        mock_close.assert_called_once_with("old2")

        _run_async(_run())

    # ── Lines 453-462: _handle_browse_post creates page + redirect ─

    def test_handle_browse_post_creates_page(self):
        async def _run():
            proxy = _make_proxy()
            new_page = AsyncMock()
            new_page.url = "https://example.com"
            proxy._context = AsyncMock()
            proxy._context.new_page.return_value = new_page

            request = MagicMock()

            async def fake_post():
                return {"url": "https://example.com"}

            request.post = fake_post

            with patch("tokenade.core.proxy.cdp_proxy.is_safe_url", return_value=True):
                with patch.object(proxy, "_navigate_page", new_callable=AsyncMock):
                    try:
                        await proxy._handle_browse_post(request)
                    except web.HTTPFound as e:
                        self.assertIn("/page/", str(e.location))

            # Verify page was created
            proxy._context.new_page.assert_called_once()
            self.assertEqual(len(proxy._pages), 1)
            page_id = list(proxy._pages.keys())[0]
            self.assertIs(proxy._pages[page_id], new_page)

        _run_async(_run())

    def test_handle_browse_post_no_url(self):
        async def _run():
            proxy = _make_proxy()
            request = MagicMock()

            async def fake_post():
                return {}

            request.post = fake_post
            result = await proxy._handle_browse_post(request)
            self.assertEqual(result.status, 400)

        _run_async(_run())

    def test_handle_browse_post_invalid_url(self):
        async def _run():
            proxy = _make_proxy()
            request = MagicMock()

            async def fake_post():
                return {"url": "not-a-url"}

            request.post = fake_post
            with patch("tokenade.core.proxy.cdp_proxy.is_safe_url", return_value=True):
                # Should prepend https:// and try to parse
                proxy._context = AsyncMock()
                new_page = AsyncMock()
                new_page.url = "https://not-a-url"
                proxy._context.new_page.return_value = new_page
                with patch.object(proxy, "_navigate_page", new_callable=AsyncMock):
                    try:
                        await proxy._handle_browse_post(request)
                    except web.HTTPFound:
                        pass  # redirect means it accepted the URL

        _run_async(_run())

    def test_handle_browse_post_blocked_url(self):
        async def _run():
            proxy = _make_proxy()
            request = MagicMock()

            async def fake_post():
                return {"url": "http://localhost/admin"}

            request.post = fake_post
            with patch("tokenade.core.proxy.cdp_proxy.is_safe_url", return_value=False):
                result = await proxy._handle_browse_post(request)
                self.assertEqual(result.status, 403)

        _run_async(_run())

    # ── Lines 472-476: _handle_page not found ─────────────────────

    def test_handle_page_not_found(self):
        async def _run():
            proxy = _make_proxy()
            proxy._pages = {}
            request = MagicMock()
            request.match_info = {"page_id": "nonexistent"}
            result = await proxy._handle_page(request)
            self.assertEqual(result.status, 404)
            self.assertIn("Page not found", result.text)

        _run_async(_run())

    # ── Lines 477-542: _handle_page found + HTML rendering ─────────

    def test_handle_page_found(self):
        async def _run():
            proxy = _make_proxy()
            mock_page = AsyncMock()
            mock_page.url = "https://example.com/test?q=1"
            proxy._pages = {"page1": mock_page}
            request = MagicMock()
            request.match_info = {"page_id": "page1"}
            result = await proxy._handle_page(request)
            self.assertEqual(result.status, 200)
            self.assertIn("Tokenade", result.text)
            self.assertIn("example.com", result.text)

        _run_async(_run())

    def test_handle_page_found_empty_url(self):
        async def _run():
            proxy = _make_proxy()
            mock_page = AsyncMock()
            mock_page.url = ""
            proxy._pages = {"page1": mock_page}
            request = MagicMock()
            request.match_info = {"page_id": "page1"}
            result = await proxy._handle_page(request)
            self.assertEqual(result.status, 200)
            self.assertIn("Tokenade", result.text)

        _run_async(_run())

    def test_handle_page_exception(self):
        async def _run():
            proxy = _make_proxy()
            mock_page = MagicMock()
            # Make .url raise an exception
            type(mock_page).url = PropertyMock(side_effect=RuntimeError("page error"))
            proxy._pages = {"page1": mock_page}
            request = MagicMock()
            request.match_info = {"page_id": "page1"}
            result = await proxy._handle_page(request)
            self.assertEqual(result.status, 500)
            self.assertIn("Error loading page", result.text)

        _run_async(_run())

    # ── Lines 544-591: Delegation handlers ─────────────────────────

    def test_handle_status_delegates(self):
        async def _run():
            proxy = _make_proxy()
            request = MagicMock()
            with patch("tokenade.core.proxy.cdp_proxy.handle_status", new_callable=AsyncMock) as mock_fn:
                mock_fn.return_value = web.Response(text="ok")
                result = await proxy._handle_status(request)
                self.assertEqual(result.status, 200)
                mock_fn.assert_called_once_with(proxy, request)

        _run_async(_run())

    def test_handle_stats_delegates(self):
        async def _run():
            proxy = _make_proxy()
            request = MagicMock()
            with patch("tokenade.core.proxy.cdp_proxy.handle_stats", new_callable=AsyncMock) as mock_fn:
                mock_fn.return_value = web.Response(text="ok")
                result = await proxy._handle_stats(request)
                self.assertEqual(result.status, 200)
                mock_fn.assert_called_once_with(proxy, request)

        _run_async(_run())

    def test_handle_session_status_delegates(self):
        async def _run():
            proxy = _make_proxy()
            request = MagicMock()
            with patch("tokenade.core.proxy.cdp_proxy.handle_session_status", new_callable=AsyncMock) as mock_fn:
                mock_fn.return_value = web.Response(text="ok")
                result = await proxy._handle_session_status(request)
                self.assertEqual(result.status, 200)
                mock_fn.assert_called_once_with(proxy, request)

        _run_async(_run())

    def test_handle_session_refresh_delegates(self):
        async def _run():
            proxy = _make_proxy()
            request = MagicMock()
            with patch("tokenade.core.proxy.cdp_proxy.handle_session_refresh", new_callable=AsyncMock) as mock_fn:
                mock_fn.return_value = web.Response(text="ok")
                result = await proxy._handle_session_refresh(request)
                self.assertEqual(result.status, 200)
                mock_fn.assert_called_once_with(proxy, request)

        _run_async(_run())

    def test_handle_cdp_version_delegates(self):
        async def _run():
            proxy = _make_proxy()
            request = MagicMock()
            with patch("tokenade.core.proxy.cdp_proxy.handle_cdp_version", new_callable=AsyncMock) as mock_fn:
                mock_fn.return_value = web.Response(text="ok")
                result = await proxy._handle_cdp_version(request)
                self.assertEqual(result.status, 200)
                mock_fn.assert_called_once_with(proxy, request)

        _run_async(_run())

    def test_handle_cdp_list_delegates(self):
        async def _run():
            proxy = _make_proxy()
            request = MagicMock()
            with patch("tokenade.core.proxy.cdp_proxy.handle_cdp_list", new_callable=AsyncMock) as mock_fn:
                mock_fn.return_value = web.Response(text="ok")
                result = await proxy._handle_cdp_list(request)
                self.assertEqual(result.status, 200)
                mock_fn.assert_called_once_with(proxy, request)

        _run_async(_run())

    def test_handle_stealth_js_delegates(self):
        async def _run():
            proxy = _make_proxy()
            request = MagicMock()
            with patch("tokenade.core.proxy.cdp_proxy.handle_stealth_js", new_callable=AsyncMock) as mock_fn:
                mock_fn.return_value = web.Response(text="ok")
                result = await proxy._handle_stealth_js(request)
                self.assertEqual(result.status, 200)
                mock_fn.assert_called_once_with(proxy, request)

        _run_async(_run())

    def test_handle_route_delegates(self):
        async def _run():
            proxy = _make_proxy()
            route = MagicMock()
            with patch("tokenade.core.proxy.cdp_proxy.handle_route", new_callable=AsyncMock) as mock_fn:
                mock_fn.return_value = None
                await proxy._handle_route(route)
                mock_fn.assert_called_once_with(proxy, route)

        _run_async(_run())

    def test_handle_proxy_delegates(self):
        async def _run():
            proxy = _make_proxy()
            request = MagicMock()
            with patch("tokenade.core.proxy.cdp_proxy.handle_proxy", new_callable=AsyncMock) as mock_fn:
                mock_fn.return_value = web.Response(text="ok")
                result = await proxy._handle_proxy(request)
                self.assertEqual(result.status, 200)
                mock_fn.assert_called_once_with(proxy, request)

        _run_async(_run())

    def test_handle_page_html_delegates(self):
        async def _run():
            proxy = _make_proxy()
            request = MagicMock()
            with patch("tokenade.core.proxy.cdp_proxy.handle_page_html", new_callable=AsyncMock) as mock_fn:
                mock_fn.return_value = web.Response(text="ok")
                result = await proxy._handle_page_html(request)
                self.assertEqual(result.status, 200)
                mock_fn.assert_called_once_with(proxy, request)

        _run_async(_run())

    def test_handle_page_screenshot_delegates(self):
        async def _run():
            proxy = _make_proxy()
            request = MagicMock()
            with patch("tokenade.core.proxy.cdp_proxy.handle_page_screenshot", new_callable=AsyncMock) as mock_fn:
                mock_fn.return_value = web.Response(text="ok")
                result = await proxy._handle_page_screenshot(request)
                self.assertEqual(result.status, 200)
                mock_fn.assert_called_once_with(proxy, request)

        _run_async(_run())

    # ── Lines 580-591: _navigate_page ─────────────────────────────

    def test_navigate_page_success(self):
        async def _run():
            proxy = _make_proxy()
            mock_page = AsyncMock()
            proxy._pages = {"p1": mock_page}
            proxy.session["local_storage"] = {}
            await proxy._navigate_page("p1", "https://example.com")
            mock_page.goto.assert_called_once()

        _run_async(_run())

    def test_navigate_page_no_page(self):
        async def _run():
            proxy = _make_proxy()
            proxy._pages = {}
            # Should return early, no error
            await proxy._navigate_page("nonexistent", "https://example.com")

        _run_async(_run())

    def test_navigate_page_with_local_storage(self):
        async def _run():
            proxy = _make_proxy()
            mock_page = AsyncMock()
            proxy._pages = {"p1": mock_page}
            proxy.session["local_storage"] = {"key": "value"}
            with patch("tokenade.core.proxy.cdp_proxy.inject_local_storage", new_callable=AsyncMock):
                await proxy._navigate_page("p1", "https://example.com")
                mock_page.goto.assert_called_once()
                mock_page.reload.assert_called_once()

        _run_async(_run())

    def test_navigate_page_exception(self):
        async def _run():
            proxy = _make_proxy()
            mock_page = AsyncMock()
            mock_page.goto.side_effect = RuntimeError("nav error")
            proxy._pages = {"p1": mock_page}
            proxy.session["local_storage"] = {}
            # Should not raise, just log
            await proxy._navigate_page("p1", "https://example.com")

        _run_async(_run())

    # ── Lines 629-631: start_extension_bridge cookie_update ────────

    def test_extension_bridge_cookie_update(self):
        async def _run():
            proxy = _make_proxy()
            bridge_mock = MagicMock()
            callback_captured = {}

            def fake_on_message(event, cb):
                callback_captured[event] = cb

            bridge_mock.on_message = fake_on_message
            bridge_mock.start = AsyncMock()

            mock_ext_module = MagicMock()
            mock_ext_module.ExtensionBridge.return_value = bridge_mock

            with patch.dict("sys.modules", {
                "tokenade.core.proxy.extension_bridge": mock_ext_module,
            }):
                proxy.start_extension_bridge(bridge_port=9224)

            # Simulate a cookie_update message
            self.assertIn("cookie_update", callback_captured)
            cb = callback_captured["cookie_update"]
            cb({"cookies": [{"name": "c1", "value": "v1"}]})
            # Verify cookies were added
            self.assertTrue(len(proxy.cookie_jar.to_list()) > 0)

        _run_async(_run())

    def test_extension_bridge_import_error(self):
        proxy = _make_proxy()
        with patch.dict("sys.modules", {"tokenade.core.proxy.extension_bridge": None}):
            with self.assertLogs(level="WARNING"):
                proxy.start_extension_bridge()

    # ── Lines 616: _on_session_refresh with context ────────────────

    def test_on_session_refresh_with_context(self):
        async def _run():
            proxy = _make_proxy()
            proxy._context = AsyncMock()
            with patch("tokenade.core.proxy.cdp_proxy.inject_cookies", new_callable=AsyncMock) as mock_inject:
                await proxy._on_session_refresh({"cookies": [{"name": "x", "value": "y"}]})
                mock_inject.assert_called_once_with(proxy)

        _run_async(_run())

    def test_on_session_refresh_without_context(self):
        async def _run():
            proxy = _make_proxy()
            proxy._context = None
            with patch("tokenade.core.proxy.cdp_proxy.inject_cookies", new_callable=AsyncMock) as mock_inject:
                await proxy._on_session_refresh({"cookies": []})
                mock_inject.assert_not_called()

        _run_async(_run())

    def test_on_session_refresh_exception(self):
        async def _run():
            proxy = _make_proxy()
            proxy._context = AsyncMock()
            with patch("tokenade.core.proxy.cdp_proxy.inject_cookies", side_effect=RuntimeError("inject fail")):
                # Should not raise, just log
                await proxy._on_session_refresh({"cookies": []})

        _run_async(_run())

    # ── Lines 766-783: stop() with various components ──────────────

    def test_stop_with_all_components(self):
        async def _run():
            proxy = _make_proxy()
            proxy._refresher = AsyncMock()
            proxy._refresher.stop = AsyncMock()
            proxy._extension_bridge = MagicMock()
            proxy._extension_bridge.stop = MagicMock()
            proxy._http_session = AsyncMock()
            proxy._http_session.closed = False
            proxy._http_session.close = AsyncMock()
            proxy._raw_server = AsyncMock()
            proxy._raw_server.close = MagicMock()
            proxy._raw_server.wait_closed = AsyncMock()
            proxy._context = AsyncMock()
            proxy._context.close = AsyncMock()
            proxy._browser = AsyncMock()
            proxy._browser.close = AsyncMock()
            proxy._playwright = AsyncMock()
            proxy._playwright.stop = AsyncMock()
            proxy.tls_matcher = MagicMock()
            proxy.tls_matcher.close = MagicMock()

            await proxy.stop()

            proxy._refresher.stop.assert_called_once()
            proxy._extension_bridge.stop.assert_called_once()
            proxy._http_session.close.assert_called_once()
            proxy._raw_server.close.assert_called_once()
            proxy._raw_server.wait_closed.assert_called_once()
            proxy._context.close.assert_called_once()
            proxy._browser.close.assert_called_once()
            proxy._playwright.stop.assert_called_once()
            proxy.tls_matcher.close.assert_called_once()

        _run_async(_run())

    def test_stop_all_none(self):
        async def _run():
            proxy = _make_proxy()
            proxy._refresher = None
            proxy._extension_bridge = None
            proxy._http_session = None
            proxy._raw_server = None
            proxy._context = None
            proxy._browser = None
            proxy._playwright = None
            proxy.tls_matcher = None
            # Should not crash
            await proxy.stop()

        _run_async(_run())

    def test_stop_http_session_already_closed(self):
        async def _run():
            proxy = _make_proxy()
            proxy._http_session = AsyncMock()
            proxy._http_session.closed = True
            proxy._http_session.close = AsyncMock()
            proxy._refresher = None
            proxy._extension_bridge = None
            proxy._raw_server = None
            proxy._context = None
            proxy._browser = None
            proxy._playwright = None
            proxy.tls_matcher = None
            await proxy.stop()
            proxy._http_session.close.assert_not_called()

        _run_async(_run())

    # ── Lines 785-786: run() ──────────────────────────────────────

    def test_run(self):
        proxy = _make_proxy()
        with patch("tokenade.core.proxy.cdp_proxy.asyncio") as mock_asyncio:
            mock_asyncio.run = MagicMock()
            proxy.run()
            mock_asyncio.run.assert_called_once()

    # ── _handle_old_sw (line 232) ─────────────────────────────────

    def test_handle_old_sw(self):
        async def _run():
            proxy = _make_proxy()
            request = MagicMock()
            result = await proxy._handle_old_sw(request)
            self.assertEqual(result.status, 200)
            self.assertIn("application/javascript", result.content_type)

        _run_async(_run())

    # ── _cleanup_expired_pages ─────────────────────────────────────

    def test_cleanup_expired_pages(self):
        async def _run():
            proxy = _make_proxy()
            # Add an expired page
            mock_page = AsyncMock()
            proxy._pages = {"old": mock_page}
            proxy._page_meta = {"old": {"created": time.time() - 100000}}
            proxy._page_ttl = 1
            # Must be in an async context for asyncio.create_task
            proxy._cleanup_expired_pages()
            # Let the create_task coroutine run
            await asyncio.sleep(0.1)
            # After cleanup, the expired page should have been closed and removed
            self.assertNotIn("old", proxy._pages)

        _run_async(_run())

    def test_cleanup_expired_pages_no_expired(self):
        proxy = _make_proxy()
        mock_page = AsyncMock()
        proxy._pages = {"new": mock_page}
        proxy._page_meta = {"new": {"created": time.time()}}
        proxy._page_ttl = 3600
        proxy._cleanup_expired_pages()
        # No pages should be scheduled for closure

    # ── _close_page ────────────────────────────────────────────────

    def test_close_page(self):
        async def _run():
            proxy = _make_proxy()
            mock_page = AsyncMock()
            proxy._pages = {"p1": mock_page}
            proxy._page_meta = {"p1": {"created": time.time()}}
            await proxy._close_page("p1")
            self.assertNotIn("p1", proxy._pages)
            self.assertNotIn("p1", proxy._page_meta)
            mock_page.close.assert_called_once()

        _run_async(_run())

    def test_close_page_not_found(self):
        async def _run():
            proxy = _make_proxy()
            proxy._pages = {}
            proxy._page_meta = {}
            # Should not crash
            await proxy._close_page("nonexistent")

        _run_async(_run())

    def test_close_page_exception_on_close(self):
        async def _run():
            proxy = _make_proxy()
            mock_page = AsyncMock()
            mock_page.close.side_effect = RuntimeError("close error")
            proxy._pages = {"p1": mock_page}
            proxy._page_meta = {"p1": {"created": time.time()}}
            # Should not raise
            await proxy._close_page("p1")
            self.assertNotIn("p1", proxy._pages)

        _run_async(_run())

    # ── _get_site_url ──────────────────────────────────────────────

    def test_get_site_url(self):
        proxy = _make_proxy()
        url = proxy._get_site_url()
        self.assertIsInstance(url, str)


if __name__ == "__main__":
    unittest.main()
