"""
Comprehensive tests for server_gui.py — handle_gui and handle_browse_page.
"""
import asyncio
import concurrent.futures
import unittest
from unittest.mock import MagicMock

from tokenade.core.proxy.server_gui import handle_gui, handle_browse_page


def _run_async(coro):
    """Run async coroutine in a new event loop via ThreadPoolExecutor."""
    with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result(timeout=10)


class TestHandleGui(unittest.TestCase):
    def _make_proxy(self):
        proxy = MagicMock()
        proxy.session = {
            "site_name": "github",
            "source_device": {"browser": "chrome", "platform": "linux"},
        }
        proxy.cookie_jar.to_list.return_value = [
            {"name": "sid", "value": "v", "domain": ".github.com", "path": "/"}
        ]
        proxy._target_url = None
        proxy.config.port = 9222
        return proxy

    def test_handle_gui_returns_html(self):
        import asyncio
        proxy = self._make_proxy()
        request = MagicMock()
        result = _run_async(handle_gui(proxy, request))
        self.assertEqual(result.status, 200)
        self.assertIn(b"Tokenade Proxy", result.body)

    def test_handle_gui_shows_site_name(self):
        import asyncio
        proxy = self._make_proxy()
        request = MagicMock()
        result = _run_async(handle_gui(proxy, request))
        self.assertIn(b"github", result.body)

    def test_handle_gui_shows_cookie_count(self):
        import asyncio
        proxy = self._make_proxy()
        request = MagicMock()
        result = _run_async(handle_gui(proxy, request))
        self.assertIn(b"1", result.body)

    def test_handle_gui_with_target_url(self):
        import asyncio
        proxy = self._make_proxy()
        proxy._target_url = "https://custom.example.com"
        request = MagicMock()
        result = _run_async(handle_gui(proxy, request))
        self.assertEqual(result.status, 200)

    def test_handle_gui_shows_port(self):
        import asyncio
        proxy = self._make_proxy()
        proxy.config.port = 8080
        request = MagicMock()
        result = _run_async(handle_gui(proxy, request))
        self.assertIn(b"8080", result.body)


class TestHandleBrowsePage(unittest.TestCase):
    def _make_proxy(self):
        proxy = MagicMock()
        proxy.session = {"site_name": "github"}
        proxy._target_url = None
        return proxy

    def test_handle_browse_page(self):
        import asyncio
        proxy = self._make_proxy()
        request = MagicMock()
        result = _run_async(handle_browse_page(proxy, request))
        self.assertEqual(result.status, 200)
        self.assertIn(b"Browse", result.body)

    def test_handle_browse_page_with_target(self):
        import asyncio
        proxy = self._make_proxy()
        proxy._target_url = "https://example.com"
        request = MagicMock()
        result = _run_async(handle_browse_page(proxy, request))
        self.assertEqual(result.status, 200)


if __name__ == "__main__":
    unittest.main()
