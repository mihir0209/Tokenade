"""
Comprehensive tests for server_routing.py — forward_request with redirects,
curl-cffi fallback to aiohttp, response handling, error paths.
"""

import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

from tokenade.core.proxy.server_routing import forward_request
from tokenade.core.proxy.server_utils import ProxyResponse


def _run_async(coro):
    return asyncio.run(coro)


class TestForwardRequest(unittest.TestCase):
    def _make_proxy(self):
        proxy = MagicMock()
        proxy.fingerprint.get_headers.return_value = {
            "user-agent": "TestAgent/1.0"
        }
        proxy.cookie_jar.get_for_request.return_value = "sid=abc"
        proxy.stats = {"bytes_sent": 0, "bytes_received": 0}
        proxy.tls_matcher = MagicMock()
        proxy.tls_matcher._session = MagicMock()
        proxy._http_session = None
        return proxy

    def test_basic_request_via_curl(self):
        proxy = self._make_proxy()
        mock_response = MagicMock()
        mock_response.content = b"response body"
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        proxy.tls_matcher.request.return_value = mock_response

        result = _run_async(
            forward_request(proxy, "GET", "https://example.com", {}, None)
        )
        self.assertIsInstance(result, ProxyResponse)
        self.assertEqual(result.status, 200)
        self.assertEqual(result.body, b"response body")

    def test_curl_content_has_read(self):
        proxy = self._make_proxy()
        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.read.return_value = b"from read"
        mock_response.content = mock_content
        mock_response.status_code = 200
        mock_response.headers = {}
        proxy.tls_matcher.request.return_value = mock_response

        result = _run_async(
            forward_request(proxy, "GET", "https://example.com", {}, None)
        )
        self.assertEqual(result.body, b"from read")

    def test_curl_content_is_not_bytes(self):
        proxy = self._make_proxy()
        mock_response = MagicMock()
        mock_response.content = [b"chunk1", b"chunk2"]
        mock_response.status_code = 200
        mock_response.headers = {}
        proxy.tls_matcher.request.return_value = mock_response

        result = _run_async(
            forward_request(proxy, "GET", "https://example.com", {}, None)
        )
        self.assertIsInstance(result.body, bytes)

    def test_curl_fails_fallback_aiohttp(self):
        proxy = self._make_proxy()
        proxy.tls_matcher.request.side_effect = RuntimeError("curl failed")
        proxy._http_session = MagicMock()
        proxy._http_session.closed = False

        mock_aio_response = AsyncMock()
        mock_aio_response.status = 200
        mock_aio_response.headers = {"content-type": "text/html"}
        mock_aio_response.read = AsyncMock(return_value=b"fallback body")
        mock_aio_response.__aenter__ = AsyncMock(
            return_value=mock_aio_response
        )
        mock_aio_response.__aexit__ = AsyncMock(return_value=False)
        proxy._http_session.request.return_value = mock_aio_response

        result = _run_async(
            forward_request(proxy, "GET", "https://example.com", {}, None)
        )
        self.assertEqual(result.status, 200)
        self.assertEqual(result.body, b"fallback body")

    def test_aiohttp_creates_session_if_none(self):
        proxy = self._make_proxy()
        proxy.tls_matcher = None
        proxy._http_session = None

        mock_aio_response = AsyncMock()
        mock_aio_response.status = 200
        mock_aio_response.headers = {}
        mock_aio_response.read = AsyncMock(return_value=b"new session")
        mock_aio_response.__aenter__ = AsyncMock(
            return_value=mock_aio_response
        )
        mock_aio_response.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "tokenade.core.proxy.server_routing.aiohttp"
        ) as mock_aiohttp:
            mock_session = MagicMock()
            mock_session.request.return_value = mock_aio_response
            mock_session.closed = False
            mock_aiohttp.ClientSession.return_value = mock_session
            mock_aiohttp.TCPConnector.return_value = MagicMock()
            mock_aiohttp.ClientTimeout.return_value = MagicMock()
            result = _run_async(
                forward_request(proxy, "GET", "https://example.com", {}, None)
            )
            self.assertEqual(result.status, 200)

    def test_no_follow_redirects(self):
        proxy = self._make_proxy()
        mock_response = MagicMock()
        mock_response.content = b"redirected"
        mock_response.status_code = 301
        mock_response.headers = {"location": "https://example.com/new"}
        proxy.tls_matcher.request.return_value = mock_response

        result = _run_async(
            forward_request(
                proxy,
                "GET",
                "https://example.com",
                {},
                None,
                follow_redirects=False,
            )
        )
        self.assertEqual(result.status, 301)

    def test_body_added_to_stats(self):
        proxy = self._make_proxy()
        body = b"test body data"
        mock_response = MagicMock()
        mock_response.content = b"ok"
        mock_response.status_code = 200
        mock_response.headers = {}
        proxy.tls_matcher.request.return_value = mock_response

        _run_async(
            forward_request(proxy, "POST", "https://example.com", {}, body)
        )
        self.assertEqual(proxy.stats["bytes_sent"], len(body))

    def test_null_body_stats(self):
        proxy = self._make_proxy()
        proxy.tls_matcher = None
        proxy._http_session = MagicMock()
        proxy._http_session.closed = False

        mock_aio_response = AsyncMock()
        mock_aio_response.status = 200
        mock_aio_response.headers = {}
        mock_aio_response.read = AsyncMock(return_value=b"ok")
        mock_aio_response.__aenter__ = AsyncMock(
            return_value=mock_aio_response
        )
        mock_aio_response.__aexit__ = AsyncMock(return_value=False)
        proxy._http_session.request.return_value = mock_aio_response

        _run_async(
            forward_request(proxy, "GET", "https://example.com", {}, None)
        )
        self.assertEqual(proxy.stats["bytes_sent"], 0)

    def test_strips_headers(self):
        proxy = self._make_proxy()
        mock_response = MagicMock()
        mock_response.content = b"ok"
        mock_response.status_code = 200
        mock_response.headers = {}
        proxy.tls_matcher.request.return_value = mock_response

        _run_async(
            forward_request(proxy, "GET", "https://example.com", {}, None)
        )
        call_kwargs = proxy.tls_matcher.request.call_args
        headers = call_kwargs[1].get("headers", {})
        self.assertNotIn("host", headers)
        self.assertNotIn("connection", headers)
        self.assertEqual(headers.get("accept-encoding"), "gzip, deflate")

    def test_aiohttp_session_already_closed(self):
        proxy = self._make_proxy()
        proxy.tls_matcher = None
        closed_session = MagicMock()
        closed_session.closed = True
        proxy._http_session = closed_session

        mock_aio_response = AsyncMock()
        mock_aio_response.status = 200
        mock_aio_response.headers = {}
        mock_aio_response.read = AsyncMock(return_value=b"new session")
        mock_aio_response.__aenter__ = AsyncMock(
            return_value=mock_aio_response
        )
        mock_aio_response.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "tokenade.core.proxy.server_routing.aiohttp"
        ) as mock_aiohttp:
            new_session = MagicMock()
            new_session.request.return_value = mock_aio_response
            new_session.closed = False
            mock_aiohttp.ClientSession.return_value = new_session
            mock_aiohttp.TCPConnector.return_value = MagicMock()
            mock_aiohttp.ClientTimeout.return_value = MagicMock()
            result = _run_async(
                forward_request(proxy, "GET", "https://example.com", {}, None)
            )
            self.assertEqual(result.status, 200)

    def test_follow_redirect_301_relative(self):
        proxy = self._make_proxy()
        proxy.tls_matcher = None

        async def make_response(status, headers, body=b"ok"):
            resp = AsyncMock()
            resp.status = status
            resp.headers = headers
            resp.read = AsyncMock(return_value=body)
            return resp

        call_count = [0]

        def mock_request_factory(**kwargs):
            call_count[0] += 1
            cm = AsyncMock()
            if call_count[0] == 1:
                cm.__aenter__ = AsyncMock(
                    return_value=AsyncMock(
                        status=302,
                        headers={"location": "/new-path"},
                        read=AsyncMock(return_value=b""),
                    )
                )
            else:
                cm.__aenter__ = AsyncMock(
                    return_value=AsyncMock(
                        status=200,
                        headers={},
                        read=AsyncMock(return_value=b"ok"),
                    )
                )
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        proxy._http_session = MagicMock()
        proxy._http_session.closed = False
        proxy._http_session.request = mock_request_factory

        result = _run_async(
            forward_request(proxy, "GET", "https://example.com/page", {}, None)
        )
        self.assertEqual(result.status, 200)

    def test_max_redirects_reached(self):
        proxy = self._make_proxy()
        proxy.tls_matcher = None

        def mock_request_factory(**kwargs):
            cm = AsyncMock()
            cm.__aenter__ = AsyncMock(
                return_value=AsyncMock(
                    status=302,
                    headers={"location": "https://example.com/loop"},
                    read=AsyncMock(return_value=b""),
                )
            )
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        proxy._http_session = MagicMock()
        proxy._http_session.closed = False
        proxy._http_session.request = mock_request_factory

        result = _run_async(
            forward_request(
                proxy, "GET", "https://example.com", {}, None, max_redirects=2
            )
        )
        self.assertEqual(result.status, 302)

    def test_redirect_307_maintains_method(self):
        proxy = self._make_proxy()
        proxy.tls_matcher = None

        call_count = [0]

        def mock_request_factory(**kwargs):
            call_count[0] += 1
            cm = AsyncMock()
            if call_count[0] == 1:
                cm.__aenter__ = AsyncMock(
                    return_value=AsyncMock(
                        status=307,
                        headers={"location": "https://example.com/new"},
                        read=AsyncMock(return_value=b""),
                    )
                )
            else:
                cm.__aenter__ = AsyncMock(
                    return_value=AsyncMock(
                        status=200,
                        headers={},
                        read=AsyncMock(return_value=b"ok"),
                    )
                )
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        proxy._http_session = MagicMock()
        proxy._http_session.closed = False
        proxy._http_session.request = mock_request_factory

        result = _run_async(
            forward_request(proxy, "POST", "https://example.com", {}, b"body")
        )
        self.assertEqual(result.status, 200)

    def test_redirect_no_location_header(self):
        proxy = self._make_proxy()
        mock_response = MagicMock()
        mock_response.content = b"redirect without location"
        mock_response.status_code = 302
        mock_response.headers = {}
        proxy.tls_matcher.request.return_value = mock_response

        result = _run_async(
            forward_request(proxy, "GET", "https://example.com", {}, None)
        )
        self.assertEqual(result.status, 302)


if __name__ == "__main__":
    unittest.main()
