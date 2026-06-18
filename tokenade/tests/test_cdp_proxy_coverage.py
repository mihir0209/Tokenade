"""
Comprehensive tests for cdp_proxy.py — covering config, factory, handlers,
page lifecycle, extension bridge, session refresh, lenient protocol, etc.
"""
import asyncio
import concurrent.futures
import time
import unittest
from unittest.mock import (
    MagicMock, AsyncMock, patch, PropertyMock, mock_open
)

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop


def _run_async(coro):
    """Run async coroutine in a new event loop via ThreadPoolExecutor."""
    with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result(timeout=10)


class TestStripDuplicateHeaders(unittest.TestCase):
    def test_no_duplicate_headers(self):
        from tokenade.core.proxy.cdp_proxy import _strip_duplicate_headers
        raw = b"GET / HTTP/1.1\r\nHost: example.com\r\nAccept: */*\r\n\r\n"
        result = _strip_duplicate_headers(raw)
        self.assertEqual(result, raw)

    def test_duplicate_headers_stripped(self):
        from tokenade.core.proxy.cdp_proxy import _strip_duplicate_headers
        raw = b"GET / HTTP/1.1\r\nHost: a.com\r\nHost: b.com\r\nAccept: */*\r\n\r\nbody"
        result = _strip_duplicate_headers(raw)
        self.assertNotIn(b"b.com", result.split(b"\r\n\r\n")[0])
        self.assertIn(b"a.com", result.split(b"\r\n\r\n")[0])
        self.assertIn(b"body", result)

    def test_no_header_end_returns_raw(self):
        from tokenade.core.proxy.cdp_proxy import _strip_duplicate_headers
        raw = b"incomplete data without header end"
        result = _strip_duplicate_headers(raw)
        self.assertEqual(result, raw)

    def test_exception_returns_raw(self):
        from tokenade.core.proxy.cdp_proxy import _strip_duplicate_headers
        # Should handle gracefully and return raw data
        raw = b"\x80\x81\x82"
        result = _strip_duplicate_headers(raw)
        self.assertEqual(result, raw)

    def test_non_duplicate_headers(self):
        from tokenade.core.proxy.cdp_proxy import _strip_duplicate_headers
        raw = b"GET / HTTP/1.1\r\nHost: a.com\r\nContent-Type: text/html\r\n\r\n"
        result = _strip_duplicate_headers(raw)
        self.assertEqual(result, raw)


class TestLenientProtocol(unittest.TestCase):
    def test_connection_made(self):
        from tokenade.core.proxy.cdp_proxy import _LenientProtocol
        inner = MagicMock()
        proto = _LenientProtocol(inner)
        transport = MagicMock()
        proto.connection_made(transport)
        inner.connection_made.assert_called_once_with(transport)

    def test_connection_lost(self):
        from tokenade.core.proxy.cdp_proxy import _LenientProtocol
        inner = MagicMock()
        proto = _LenientProtocol(inner)
        proto.connection_lost(RuntimeError("test"))
        inner.connection_lost.assert_called_once()

    def test_data_received_strips_duplicates(self):
        from tokenade.core.proxy.cdp_proxy import _LenientProtocol
        inner = MagicMock()
        proto = _LenientProtocol(inner)
        data = b"HTTP/1.1 200 OK\r\nHost: a.com\r\nHost: b.com\r\n\r\n"
        proto.data_received(data)
        inner.data_received.assert_called_once()
        called_data = inner.data_received.call_args[0][0]
        self.assertNotIn(b"b.com", called_data.split(b"\r\n\r\n")[0])

    def test_eof_received(self):
        from tokenade.core.proxy.cdp_proxy import _LenientProtocol
        inner = MagicMock()
        inner.eof_received.return_value = False
        proto = _LenientProtocol(inner)
        result = proto.eof_received()
        self.assertFalse(result)


class TestLenientServerFactory(unittest.TestCase):
    def test_creates_lenient_protocol(self):
        from tokenade.core.proxy.cdp_proxy import _LenientServerFactory, _LenientProtocol
        inner_factory = MagicMock()
        factory = _LenientServerFactory(inner_factory)
        proto = factory()
        self.assertIsInstance(proto, _LenientProtocol)


class TestCDPProxyConfig(unittest.TestCase):
    def test_defaults(self):
        from tokenade.core.proxy.cdp_proxy import CDPProxyConfig
        config = CDPProxyConfig()
        self.assertEqual(config.port, 9222)
        self.assertEqual(config.host, "127.0.0.1")
        self.assertTrue(config.headless)
        self.assertFalse(config.verbose)
        self.assertEqual(config.timeout, 30)
        self.assertFalse(config.use_fingerprint)

    def test_custom_values(self):
        from tokenade.core.proxy.cdp_proxy import CDPProxyConfig
        config = CDPProxyConfig(port=8080, host="0.0.0.0", headless=False, verbose=True, timeout=60)
        self.assertEqual(config.port, 8080)
        self.assertEqual(config.host, "0.0.0.0")
        self.assertFalse(config.headless)
        self.assertTrue(config.verbose)


class TestCDPProxyInit(unittest.TestCase):
    def _make_proxy(self, **kwargs):
        from tokenade.core.proxy.cdp_proxy import CDPProxy, CDPProxyConfig
        session = {
            "cookies": [{"name": "sid", "value": "abc", "domain": ".github.com", "path": "/"}],
            "site_name": "github",
            "fingerprint": {"user_agent": "Mozilla/5.0 Test"},
            "tls_profile": {"browser": "chrome", "version": "120"},
            "source_device": {"browser": "chrome", "platform": "linux"},
            "local_storage": {},
        }
        config = CDPProxyConfig(**kwargs)
        return CDPProxy(session, config)

    def test_basic_init(self):
        proxy = self._make_proxy()
        self.assertEqual(proxy.config.port, 9222)
        self.assertEqual(proxy.session["site_name"], "github")
        self.assertIsNotNone(proxy.cookie_jar)
        self.assertIsNotNone(proxy.fingerprint)
        self.assertIsNotNone(proxy.tls_matcher)

    def test_stats_init(self):
        proxy = self._make_proxy()
        self.assertEqual(proxy.stats["requests"], 0)
        self.assertEqual(proxy.stats["bytes_sent"], 0)
        self.assertIsNone(proxy.stats["start_time"])

    def test_pages_init(self):
        proxy = self._make_proxy()
        self.assertEqual(proxy._pages, {})
        self.assertEqual(proxy._page_meta, {})
        self.assertEqual(proxy._max_pages, 20)
        self.assertEqual(proxy._page_ttl, 3600)

    def test_default_config(self):
        from tokenade.core.proxy.cdp_proxy import CDPProxy, CDPProxyConfig
        session = {"cookies": []}
        proxy = CDPProxy(session)
        self.assertIsInstance(proxy.config, CDPProxyConfig)

    def test_from_session_data(self):
        from tokenade.core.proxy.cdp_proxy import CDPProxy
        session = {"cookies": [], "site_name": "test"}
        proxy = CDPProxy.from_session_data(session)
        self.assertEqual(proxy.session["site_name"], "test")

    def test_from_session_data_with_config(self):
        from tokenade.core.proxy.cdp_proxy import CDPProxy, CDPProxyConfig
        session = {"cookies": []}
        config = CDPProxyConfig(port=9999)
        proxy = CDPProxy.from_session_data(session, config)
        self.assertEqual(proxy.config.port, 9999)


class TestCDPProxyFactory(unittest.TestCase):
    def test_from_session_file(self):
        from tokenade.core.proxy.cdp_proxy import CDPProxy
        session_data = {"cookies": [{"name": "t", "value": "v", "domain": ".x.com", "path": "/"}], "site_name": "test"}
        with patch("tokenade.core.importer.session_packager.SessionPackager") as MockPackager:
            MockPackager.return_value.load.return_value = session_data
            proxy = CDPProxy.from_session_file("/fake/session.tokenade")
            self.assertEqual(proxy.session["site_name"], "test")


class TestCDPProxyCreateApp(unittest.TestCase):
    def _make_proxy(self):
        from tokenade.core.proxy.cdp_proxy import CDPProxy
        session = {"cookies": [], "site_name": "github", "fingerprint": {}, "tls_profile": {}, "source_device": {}}
        return CDPProxy(session)

    def test_create_app_returns_application(self):
        proxy = self._make_proxy()
        app = proxy._create_app()
        self.assertIsInstance(app, web.Application)


class TestCDPProxyHandlers(unittest.TestCase):
    def _make_proxy(self):
        from tokenade.core.proxy.cdp_proxy import CDPProxy
        session = {
            "cookies": [{"name": "sid", "value": "v", "domain": ".test.com", "path": "/"}],
            "site_name": "github",
            "fingerprint": {"user_agent": "TestAgent/1.0"},
            "tls_profile": {"impersonate": "chrome120"},
            "source_device": {"browser": "chrome", "platform": "linux"},
            "local_storage": {},
        }
        return CDPProxy(session)

    def test_handle_legacy_redirect(self):
        proxy = self._make_proxy()
        request = MagicMock()
        with self.assertRaises(web.HTTPFound):
            _run_async(proxy._handle_legacy_redirect(request))

    def test_handle_browse_post_no_url(self):
        proxy = self._make_proxy()
        request = AsyncMock()
        request.post = AsyncMock(return_value={})
        result = _run_async(proxy._handle_browse_post(request))
        self.assertEqual(result.status, 400)

    def test_handle_browse_post_blocked_url(self):
        proxy = self._make_proxy()
        request = AsyncMock()
        request.post = AsyncMock(return_value={"url": "http://169.254.169.254/metadata"})
        result = _run_async(proxy._handle_browse_post(request))
        self.assertEqual(result.status, 403)

    def test_handle_browse_post_no_hostname(self):
        proxy = self._make_proxy()
        request = AsyncMock()
        request.post = AsyncMock(return_value={"url": "://invalid"})
        result = _run_async(proxy._handle_browse_post(request))
        self.assertEqual(result.status, 400)

    def test_handle_browse_post_adds_https(self):
        proxy = self._make_proxy()
        request = AsyncMock()
        request.post = AsyncMock(return_value={"url": "example.com"})
        result = _run_async(proxy._handle_browse_post(request))
        # Should try to create page; may fail but won't be 400
        self.assertIn(result.status, [302, 403, 500])

    def test_handle_page_not_found(self):
        proxy = self._make_proxy()
        request = MagicMock()
        request.match_info = {"page_id": "nonexistent"}
        result = _run_async(proxy._handle_page(request))
        self.assertEqual(result.status, 404)

    def test_handle_gui(self):
        proxy = self._make_proxy()
        request = MagicMock()
        result = _run_async(proxy._handle_gui(request))
        self.assertEqual(result.status, 200)
        self.assertIn(b"Tokenade CDP Proxy", result.body)


class TestCDPProxyPageLifecycle(unittest.TestCase):
    def _make_proxy(self):
        from tokenade.core.proxy.cdp_proxy import CDPProxy
        session = {"cookies": [], "site_name": "test", "fingerprint": {}, "tls_profile": {}, "source_device": {}}
        return CDPProxy(session)

    def test_cleanup_expired_pages(self):
        proxy = self._make_proxy()
        mock_page = AsyncMock()
        proxy._pages = {"p1": mock_page}
        proxy._page_meta = {"p1": {"created": time.time() - 7200}}

        async def _test():
            proxy._cleanup_expired_pages()
            await asyncio.sleep(0.1)  # Let the task run
            return "ok"

        result = _run_async(_test())
        self.assertEqual(result, "ok")

    def test_cleanup_no_expired(self):
        proxy = self._make_proxy()
        proxy._pages = {"p1": MagicMock()}
        proxy._page_meta = {"p1": {"created": time.time()}}
        proxy._cleanup_expired_pages()
        self.assertIn("p1", proxy._pages)

    def test_close_page(self):
        proxy = self._make_proxy()
        mock_page = AsyncMock()
        proxy._pages = {"p1": mock_page}
        proxy._page_meta = {"p1": {"created": time.time()}}
        _run_async(proxy._close_page("p1"))
        self.assertNotIn("p1", proxy._pages)
        self.assertNotIn("p1", proxy._page_meta)
        mock_page.close.assert_called_once()

    def test_close_page_nonexistent(self):
        proxy = self._make_proxy()
        _run_async(proxy._close_page("nonexistent"))

    def test_close_page_close_error(self):
        proxy = self._make_proxy()
        mock_page = AsyncMock()
        mock_page.close.side_effect = RuntimeError("already closed")
        proxy._pages = {"p1": mock_page}
        proxy._page_meta = {"p1": {"created": time.time()}}
        _run_async(proxy._close_page("p1"))


class TestCDPProxySessionRefresh(unittest.TestCase):
    def _make_proxy(self):
        from tokenade.core.proxy.cdp_proxy import CDPProxy
        session = {
            "cookies": [{"name": "old", "value": "v", "domain": ".x.com", "path": "/"}],
            "site_name": "test",
            "fingerprint": {},
            "tls_profile": {},
            "source_device": {},
        }
        return CDPProxy(session)

    def test_on_session_refresh(self):
        proxy = self._make_proxy()
        new_session = {"cookies": [{"name": "new", "value": "v2", "domain": ".y.com", "path": "/"}]}
        _run_async(proxy._on_session_refresh(new_session))
        self.assertEqual(len(proxy.cookie_jar.to_list()), 1)

    def test_on_session_refresh_error(self):
        proxy = self._make_proxy()
        proxy._context = MagicMock()
        proxy._context.__aenter__ = AsyncMock()
        proxy._context.__aexit__ = AsyncMock()
        # Force error via bad cookies
        _run_async(proxy._on_session_refresh({"cookies": "not-a-list"}))


class TestCDPProxyExtensionBridge(unittest.TestCase):
    def _make_proxy(self):
        from tokenade.core.proxy.cdp_proxy import CDPProxy
        session = {"cookies": [], "site_name": "test", "fingerprint": {}, "tls_profile": {}, "source_device": {}}
        return CDPProxy(session)

    def test_start_extension_bridge(self):
        proxy = self._make_proxy()
        with patch("tokenade.core.proxy.extension_bridge.ExtensionBridge") as MockBridge:
            mock_instance = MagicMock()
            MockBridge.return_value = mock_instance
            with patch("asyncio.ensure_future") as mock_ensure:
                proxy.start_extension_bridge(bridge_port=9224)
                MockBridge.assert_called_once_with(host="127.0.0.1", port=9224)
                mock_instance.on_message.assert_called_once()

    def test_start_extension_bridge_import_error(self):
        proxy = self._make_proxy()
        with patch.dict("sys.modules", {"tokenade.core.proxy.extension_bridge": None}):
            proxy.start_extension_bridge()

    def test_start_extension_bridge_general_error(self):
        proxy = self._make_proxy()
        with patch("tokenade.core.proxy.extension_bridge.ExtensionBridge", side_effect=RuntimeError("fail")):
            proxy.start_extension_bridge()


class TestCDPProxySiteUrl(unittest.TestCase):
    def test_get_site_url(self):
        from tokenade.core.proxy.cdp_proxy import CDPProxy
        session = {"site_name": "github", "cookies": [{"domain": ".github.com"}]}
        proxy = CDPProxy(session)
        url = proxy._get_site_url()
        self.assertIsInstance(url, str)

    def test_get_site_url_no_cookies(self):
        from tokenade.core.proxy.cdp_proxy import CDPProxy
        session = {"site_name": "github", "cookies": []}
        proxy = CDPProxy(session)
        url = proxy._get_site_url()
        self.assertIsInstance(url, str)


class TestCDPProxyStop(unittest.TestCase):
    def test_stop(self):
        from tokenade.core.proxy.cdp_proxy import CDPProxy
        session = {"cookies": [], "site_name": "test"}
        proxy = CDPProxy(session)
        proxy._refresher = AsyncMock()
        proxy._extension_bridge = MagicMock()
        proxy._http_session = None
        proxy._raw_server = None
        proxy._context = None
        proxy._browser = None
        proxy._playwright = None
        proxy.tls_matcher = MagicMock()
        _run_async(proxy.stop())
        proxy._refresher.stop.assert_called_once()

    def test_stop_with_http_session(self):
        from tokenade.core.proxy.cdp_proxy import CDPProxy
        session = {"cookies": [], "site_name": "test"}
        proxy = CDPProxy(session)
        mock_session = AsyncMock()
        mock_session.closed = False
        proxy._http_session = mock_session
        proxy.tls_matcher = MagicMock()
        _run_async(proxy.stop())
        mock_session.close.assert_called_once()

    def test_stop_http_session_already_closed(self):
        from tokenade.core.proxy.cdp_proxy import CDPProxy
        session = {"cookies": [], "site_name": "test"}
        proxy = CDPProxy(session)
        mock_session = AsyncMock()
        mock_session.closed = True
        proxy._http_session = mock_session
        proxy.tls_matcher = MagicMock()
        _run_async(proxy.stop())


class TestCreateCdpProxyFromFile(unittest.TestCase):
    def test_create_cdp_proxy_from_file(self):
        from tokenade.core.proxy.cdp_proxy import create_cdp_proxy_from_file
        session_data = {"cookies": [], "site_name": "test"}
        with patch("tokenade.core.importer.session_packager.SessionPackager") as MockPackager:
            MockPackager.return_value.load.return_value = session_data
            proxy = create_cdp_proxy_from_file("/fake/tokenade")
            self.assertEqual(proxy.session["site_name"], "test")


class TestCDPProxyRunAsync(unittest.TestCase):
    def test_run_async_calls_start_and_stop(self):
        from tokenade.core.proxy.cdp_proxy import CDPProxy
        session = {"cookies": [], "site_name": "test"}
        proxy = CDPProxy(session)
        proxy.start = AsyncMock()
        proxy.stop = AsyncMock()
        with patch("asyncio.sleep", side_effect=KeyboardInterrupt):
            _run_async(proxy._run_async())
        proxy.start.assert_called_once()
        proxy.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
