import asyncio
import concurrent.futures
import unittest
from unittest.mock import AsyncMock, patch


def _run_async(coro):
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(asyncio.run, coro).result(timeout=10)


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


class TestCDPProxyStartErrors(unittest.TestCase):
    @patch("tokenade.core.proxy.cdp_proxy.async_playwright")
    def test_start_error_executable_not_found(self, mock_pw):
        proxy = _make_proxy()
        mock_pw.return_value.start = AsyncMock()
        mock_pw.return_value.start.return_value.chromium.launch = AsyncMock(
            side_effect=Exception("executable not found")
        )
        with self.assertRaises(RuntimeError) as ctx:
            _run_async(proxy.start())
        self.assertIn("Chromium browser not found", str(ctx.exception))

    @patch("tokenade.core.proxy.cdp_proxy.async_playwright")
    def test_start_error_timeout(self, mock_pw):
        proxy = _make_proxy()
        mock_pw.return_value.start = AsyncMock()
        mock_pw.return_value.start.return_value.chromium.launch = AsyncMock(
            side_effect=Exception("launch timeout")
        )
        with self.assertRaises(RuntimeError) as ctx:
            _run_async(proxy.start())
        self.assertIn("timed out", str(ctx.exception))

    @patch("tokenade.core.proxy.cdp_proxy.async_playwright")
    def test_start_error_generic(self, mock_pw):
        proxy = _make_proxy()
        mock_pw.return_value.start = AsyncMock()
        mock_pw.return_value.start.return_value.chromium.launch = AsyncMock(
            side_effect=Exception("some other error")
        )
        with self.assertRaises(RuntimeError) as ctx:
            _run_async(proxy.start())
        msg = str(ctx.exception)
        self.assertIn("Failed to launch Chromium", msg)
        self.assertIn("Troubleshooting", msg)
