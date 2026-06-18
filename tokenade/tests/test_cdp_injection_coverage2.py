"""
Comprehensive tests for cdp_injection.py — inject_via_cdp, inject_via_raw_cdp,
inject_stealth_script, inject_cookies, inject_local_storage.
"""

import asyncio
import concurrent.futures
import unittest
from unittest.mock import MagicMock, AsyncMock, patch


def _run_async(coro):
    """Run async coroutine in a new event loop via ThreadPoolExecutor."""
    with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result(timeout=10)


class TestInjectViaCdp(unittest.TestCase):
    def _make_proxy(self):
        proxy = MagicMock()
        proxy._cdp_session = AsyncMock()
        proxy.session = {
            "cookies": [
                {
                    "name": "sid",
                    "value": "abc",
                    "domain": ".github.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                    "sameSite": "strict",
                },
                {
                    "name": "token",
                    "value": "xyz",
                    "domain": ".github.com",
                    "path": "/",
                    "sameSite": "lax",
                    "expires": 1700000000,
                },
                {
                    "name": "sess",
                    "value": "123",
                    "domain": ".github.com",
                    "path": "/",
                    "sameSite": "none",
                },
                {
                    "name": "old",
                    "value": "v",
                    "domain": ".x.com",
                    "path": "/",
                    "expires": 1700000000000,
                },
                {
                    "name": "plain",
                    "value": "p",
                    "domain": ".x.com",
                    "path": "/",
                },
            ],
        }
        return proxy

    def test_inject_via_cdp(self):
        from tokenade.core.proxy.cdp_injection import inject_via_cdp

        proxy = self._make_proxy()
        _run_async(inject_via_cdp(proxy))
        self.assertTrue(proxy._cdp_session.send.called)

    def test_inject_via_cdp_no_session(self):
        from tokenade.core.proxy.cdp_injection import inject_via_cdp

        proxy = MagicMock()
        proxy._cdp_session = None
        _run_async(inject_via_cdp(proxy))

    def test_inject_via_cdp_send_error(self):
        from tokenade.core.proxy.cdp_injection import inject_via_cdp

        proxy = MagicMock()
        proxy._cdp_session = AsyncMock()
        proxy._cdp_session.send.side_effect = [
            RuntimeError("fail"),
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ]
        proxy.session = {
            "cookies": [
                {"name": "t", "value": "v", "domain": ".x.com", "path": "/"}
            ]
        }
        _run_async(inject_via_cdp(proxy))


class TestInjectViaRawCdp(unittest.TestCase):
    def test_no_websockets(self):
        from tokenade.core.proxy.cdp_injection import inject_via_raw_cdp

        proxy = MagicMock()
        proxy._cdp_port = 9223
        proxy.session = {"cookies": [], "fingerprint": {}}
        with patch.dict("sys.modules", {"websockets": None}):
            _run_async(inject_via_raw_cdp(proxy))

    def test_no_ws_url(self):
        from tokenade.core.proxy.cdp_injection import inject_via_raw_cdp

        proxy = MagicMock()
        proxy._cdp_port = 9223
        proxy.session = {"cookies": [], "fingerprint": {}}
        mock_ws = MagicMock()
        with patch.dict("sys.modules", {"websockets": mock_ws}):
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = b'{"webSocketDebuggerUrl": ""}'
                mock_urlopen.return_value = mock_resp
                _run_async(inject_via_raw_cdp(proxy))

    def test_connection_error(self):
        from tokenade.core.proxy.cdp_injection import inject_via_raw_cdp

        proxy = MagicMock()
        proxy._cdp_port = 9223
        proxy.session = {"cookies": [], "fingerprint": {}}
        mock_ws = MagicMock()
        with patch.dict("sys.modules", {"websockets": mock_ws}):
            with patch(
                "urllib.request.urlopen",
                side_effect=RuntimeError("conn refused"),
            ):
                _run_async(inject_via_raw_cdp(proxy))

    def test_bad_version_json(self):
        from tokenade.core.proxy.cdp_injection import inject_via_raw_cdp

        proxy = MagicMock()
        proxy._cdp_port = 9223
        proxy.session = {"cookies": [], "fingerprint": {}}
        mock_ws = MagicMock()
        with patch.dict("sys.modules", {"websockets": mock_ws}):
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = b"not json"
                mock_urlopen.return_value = mock_resp
                _run_async(inject_via_raw_cdp(proxy))


class TestInjectStealthScript(unittest.TestCase):
    def test_no_context(self):
        from tokenade.core.proxy.cdp_injection import inject_stealth_script

        proxy = MagicMock()
        proxy._context = None
        _run_async(inject_stealth_script(proxy))

    def test_inject_into_pages(self):
        from tokenade.core.proxy.cdp_injection import inject_stealth_script

        proxy = MagicMock()
        proxy._context = AsyncMock()
        page1 = AsyncMock()
        page2 = AsyncMock()
        proxy._pages = {"p1": page1, "p2": page2}
        _run_async(inject_stealth_script(proxy))
        page1.evaluate.assert_called_once()
        page2.evaluate.assert_called_once()
        proxy._context.add_init_script.assert_called_once()

    def test_page_evaluate_error(self):
        from tokenade.core.proxy.cdp_injection import inject_stealth_script

        proxy = MagicMock()
        proxy._context = AsyncMock()
        page = AsyncMock()
        page.evaluate.side_effect = RuntimeError("fail")
        proxy._pages = {"p1": page}
        _run_async(inject_stealth_script(proxy))

    def test_add_init_script_error(self):
        from tokenade.core.proxy.cdp_injection import inject_stealth_script

        proxy = MagicMock()
        proxy._context = AsyncMock()
        proxy._context.add_init_script.side_effect = RuntimeError("fail")
        proxy._pages = {}
        _run_async(inject_stealth_script(proxy))

    def test_context_error(self):
        from tokenade.core.proxy.cdp_injection import inject_stealth_script

        proxy = MagicMock()
        proxy._context = AsyncMock()
        proxy._pages = {}
        proxy._context.add_init_script.side_effect = RuntimeError(
            "context error"
        )
        _run_async(inject_stealth_script(proxy))


class TestInjectCookies(unittest.TestCase):
    def test_no_context(self):
        from tokenade.core.proxy.cdp_injection import inject_cookies

        proxy = MagicMock()
        proxy._context = None
        _run_async(inject_cookies(proxy))

    def test_inject_cookies(self):
        from tokenade.core.proxy.cdp_injection import inject_cookies

        proxy = MagicMock()
        proxy._context = AsyncMock()
        proxy.session = {
            "cookies": [
                {
                    "name": "sid",
                    "value": "abc",
                    "domain": ".github.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                    "sameSite": "strict",
                },
                {
                    "name": "token",
                    "value": "xyz",
                    "domain": ".github.com",
                    "path": "/",
                    "sameSite": "lax",
                    "expires": 1700000000,
                },
                {
                    "name": "old",
                    "value": "v",
                    "domain": ".x.com",
                    "path": "/",
                    "expires": 1700000000000,
                },
            ],
        }
        _run_async(inject_cookies(proxy))
        proxy._context.add_cookies.assert_called_once()

    def test_inject_no_cookies(self):
        from tokenade.core.proxy.cdp_injection import inject_cookies

        proxy = MagicMock()
        proxy._context = AsyncMock()
        proxy.session = {"cookies": []}
        _run_async(inject_cookies(proxy))

    def test_add_cookies_error(self):
        from tokenade.core.proxy.cdp_injection import inject_cookies

        proxy = MagicMock()
        proxy._context = AsyncMock()
        proxy._context.add_cookies.side_effect = RuntimeError("fail")
        proxy.session = {
            "cookies": [
                {"name": "t", "value": "v", "domain": ".x.com", "path": "/"}
            ]
        }
        _run_async(inject_cookies(proxy))


class TestInjectLocalStorage(unittest.TestCase):
    def test_no_local_storage(self):
        from tokenade.core.proxy.cdp_injection import inject_local_storage

        proxy = MagicMock()
        proxy.session = {}
        page = AsyncMock()
        _run_async(inject_local_storage(proxy, page))

    def test_inject_flat(self):
        from tokenade.core.proxy.cdp_injection import inject_local_storage

        proxy = MagicMock()
        proxy.session = {"local_storage": {"token": "abc", "user": "john"}}
        page = AsyncMock()
        _run_async(inject_local_storage(proxy, page))
        page.evaluate.assert_called_once()

    def test_inject_nested(self):
        from tokenade.core.proxy.cdp_injection import inject_local_storage

        proxy = MagicMock()
        proxy.session = {"local_storage": {"github.com": {"token": "abc"}}}
        page = AsyncMock()
        _run_async(inject_local_storage(proxy, page))
        page.evaluate.assert_called_once()

    def test_inject_empty_after_nested(self):
        from tokenade.core.proxy.cdp_injection import inject_local_storage

        proxy = MagicMock()
        proxy.session = {"local_storage": {}}
        page = AsyncMock()
        _run_async(inject_local_storage(proxy, page))
        page.evaluate.assert_not_called()

    def test_evaluate_error(self):
        from tokenade.core.proxy.cdp_injection import inject_local_storage

        proxy = MagicMock()
        proxy.session = {"local_storage": {"token": "abc"}}
        page = AsyncMock()
        page.evaluate.side_effect = RuntimeError("fail")
        _run_async(inject_local_storage(proxy, page))


if __name__ == "__main__":
    unittest.main()
