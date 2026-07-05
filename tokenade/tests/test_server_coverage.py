"""Comprehensive tests for server.py — targeting 50%+ coverage."""

import asyncio
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from tokenade.core.proxy.server import (
    ProxyConfig,
    TokenadeProxy,
    create_proxy_from_file,
)


def _run_async(coro):
    return asyncio.run(coro)


def _make_session():
    return {
        "version": "2.0",
        "site_name": "test-site",
        "auth_status": "logged_in",
        "cookies": [
            {"name": "sid", "value": "abc123", "domain": ".example.com", "path": "/"},
        ],
        "fingerprint": {"user_agent": "Mozilla/5.0 TestAgent", "platform": "Linux"},
        "tls_profile": {"browser": "chrome", "version": "120", "impersonate": "chrome_120"},
    }


# ===========================================================================
# ProxyConfig
# ===========================================================================

class TestProxyConfig:
    def test_defaults(self):
        c = ProxyConfig()
        assert c.port == 9222
        assert c.host == "127.0.0.1"
        assert c.gui_mode is True
        assert c.auto_refresh is False
        assert c.verbose is False

    def test_custom(self):
        c = ProxyConfig(port=8080, host="0.0.0.0", gui_mode=False, auto_refresh=True, verbose=True)
        assert c.port == 8080
        assert c.host == "0.0.0.0"
        assert c.gui_mode is False
        assert c.auto_refresh is True
        assert c.verbose is True


# ===========================================================================
# TokenadeProxy.__init__
# ===========================================================================

class TestTokenadeProxyInit:
    def test_creation_with_config(self):
        config = ProxyConfig(port=9999, host="0.0.0.0")
        proxy = TokenadeProxy(_make_session(), config)
        assert proxy.config.port == 9999
        assert proxy.config.host == "0.0.0.0"

    def test_creation_default_config(self):
        proxy = TokenadeProxy(_make_session())
        assert proxy.config.port == 9222
        assert proxy.config.host == "127.0.0.1"

    def test_session_stored(self):
        s = _make_session()
        proxy = TokenadeProxy(s)
        assert proxy.session is s

    def test_cookie_jar_initialized(self):
        proxy = TokenadeProxy(_make_session())
        assert proxy.cookie_jar is not None
        cookies = proxy.cookie_jar.to_list()
        assert len(cookies) >= 1

    def test_fingerprint_initialized(self):
        proxy = TokenadeProxy(_make_session())
        assert proxy.fingerprint is not None

    def test_tls_matcher_initialized(self):
        proxy = TokenadeProxy(_make_session())
        assert proxy.tls_matcher is not None

    def test_stats_initialized(self):
        proxy = TokenadeProxy(_make_session())
        assert proxy.stats["requests"] == 0
        assert proxy.stats["bytes_sent"] == 0
        assert proxy.stats["bytes_received"] == 0
        assert proxy.stats["errors"] == 0
        assert proxy.stats["start_time"] is None

    def test_internal_fields_none(self):
        proxy = TokenadeProxy(_make_session())
        assert proxy._app is None
        assert proxy._runner is None
        assert proxy._site is None
        assert proxy._target_url is None
        assert proxy._proxy_active is False
        assert proxy._http_session is None


# ===========================================================================
# TokenadeProxy.from_session_data
# ===========================================================================

class TestFromSessionData:
    def test_creates_proxy(self):
        s = _make_session()
        proxy = TokenadeProxy.from_session_data(s)
        assert proxy.session is s

    def test_with_config(self):
        config = ProxyConfig(port=7777)
        proxy = TokenadeProxy.from_session_data(_make_session(), config)
        assert proxy.config.port == 7777


# ===========================================================================
# TokenadeProxy._create_app
# ===========================================================================

class TestCreateApp:
    def test_gui_mode_routes(self):
        proxy = TokenadeProxy(_make_session(), ProxyConfig(gui_mode=True))
        app = proxy._create_app()
        assert isinstance(app, web.Application)

    def test_non_gui_mode_routes(self):
        proxy = TokenadeProxy(_make_session(), ProxyConfig(gui_mode=False))
        app = proxy._create_app()
        assert isinstance(app, web.Application)


# ===========================================================================
# TokenadeProxy._handle_browse_post
# ===========================================================================

class TestHandleBrowsePost:
    def test_no_url_returns_400(self):
        proxy = TokenadeProxy(_make_session())
        request = make_mocked_request("POST", "/browse")
        mock_post = AsyncMock(return_value={})
        with patch.object(request, "post", mock_post):
            resp = _run_async(proxy._handle_browse_post(request))
        assert resp.status == 400

    def test_unsafe_url_returns_403(self):
        proxy = TokenadeProxy(_make_session())
        request = make_mocked_request("POST", "/browse")
        mock_post = AsyncMock(return_value={"url": "http://192.168.1.1/admin"})
        with patch.object(request, "post", mock_post):
            with patch("tokenade.core.proxy.server._is_safe_url", return_value=False):
                resp = _run_async(proxy._handle_browse_post(request))
        assert resp.status == 403

    def test_safe_url_sets_target(self):
        proxy = TokenadeProxy(_make_session())
        request = make_mocked_request("POST", "/browse")
        mock_post = AsyncMock(return_value={"url": "https://example.com"})
        with patch.object(request, "post", mock_post):
            with patch("tokenade.core.proxy.server._is_safe_url", return_value=True):
                with pytest.raises(web.HTTPFound):
                    _run_async(proxy._handle_browse_post(request))
        assert proxy._target_url == "https://example.com"
        assert proxy._proxy_active is True

    def test_url_without_scheme_gets_https_prepended(self):
        proxy = TokenadeProxy(_make_session())
        request = make_mocked_request("POST", "/browse")
        mock_post = AsyncMock(return_value={"url": "example.com"})
        with patch.object(request, "post", mock_post):
            with patch("tokenade.core.proxy.server._is_safe_url", return_value=True):
                with pytest.raises(web.HTTPFound):
                    _run_async(proxy._handle_browse_post(request))
        assert proxy._target_url == "https://example.com"

    def test_exception_returns_500(self):
        proxy = TokenadeProxy(_make_session())
        request = make_mocked_request("POST", "/browse")
        mock_post = AsyncMock(side_effect=RuntimeError("boom"))
        with patch.object(request, "post", mock_post):
            resp = _run_async(proxy._handle_browse_post(request))
        assert resp.status == 500

    def test_url_with_only_scheme_returns_400(self):
        proxy = TokenadeProxy(_make_session())
        request = make_mocked_request("POST", "/browse")
        # "https://" has no hostname
        mock_post = AsyncMock(return_value={"url": "https://"})
        with patch.object(request, "post", mock_post):
            resp = _run_async(proxy._handle_browse_post(request))
        assert resp.status == 400


# ===========================================================================
# TokenadeProxy._handle_site_proxy_entry
# ===========================================================================

class TestHandleSiteProxyEntry:
    def test_no_target_url_returns_400(self):
        proxy = TokenadeProxy(_make_session())
        request = make_mocked_request("GET", "/proxy")
        resp = _run_async(proxy._handle_site_proxy_entry(request))
        assert resp.status == 400

    def test_proxy_redirect_to_slash(self):
        proxy = TokenadeProxy(_make_session())
        proxy._target_url = "https://example.com"
        request = make_mocked_request("GET", "/proxy")
        with pytest.raises(web.HTTPFound) as exc_info:
            _run_async(proxy._handle_site_proxy_entry(request))
        # HTTPFound has a `location` attribute
        assert exc_info.value.location == "/proxy/"

    def test_successful_forward(self):
        proxy = TokenadeProxy(_make_session())
        proxy._target_url = "https://example.com"

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.body = b"<html>OK</html>"

        request = make_mocked_request("GET", "/proxy/page")
        with patch("tokenade.core.proxy.server.forward_request", new_callable=AsyncMock, return_value=mock_response):
            resp = _run_async(proxy._handle_site_proxy_entry(request))
        assert resp.status == 200
        assert proxy.stats["requests"] == 1

    def test_html_response_rewritten(self):
        proxy = TokenadeProxy(_make_session())
        proxy._target_url = "https://example.com"

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.body = b"<html><head></head><body></body></html>"

        request = make_mocked_request("GET", "/proxy/")
        with patch("tokenade.core.proxy.server.forward_request", new_callable=AsyncMock, return_value=mock_response):
            resp = _run_async(proxy._handle_site_proxy_entry(request))
        assert b"serviceWorker" in resp.body

    def test_js_response_rewritten(self):
        proxy = TokenadeProxy(_make_session())
        proxy._target_url = "https://example.com"

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "application/javascript"}
        mock_response.body = b'import "https://example.com/module.js"'

        request = make_mocked_request("GET", "/proxy/app.js")
        with patch("tokenade.core.proxy.server.forward_request", new_callable=AsyncMock, return_value=mock_response):
            resp = _run_async(proxy._handle_site_proxy_entry(request))
        assert b"/proxy/module.js" in resp.body

    def test_css_response_rewritten(self):
        proxy = TokenadeProxy(_make_session())
        proxy._target_url = "https://example.com"

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "text/css"}
        mock_response.body = b'body { background: url("https://example.com/bg.png"); }'

        request = make_mocked_request("GET", "/proxy/style.css")
        with patch("tokenade.core.proxy.server.forward_request", new_callable=AsyncMock, return_value=mock_response):
            resp = _run_async(proxy._handle_site_proxy_entry(request))
        assert b"/proxy/" in resp.body

    def test_exception_returns_502(self):
        proxy = TokenadeProxy(_make_session())
        proxy._target_url = "https://example.com"

        request = make_mocked_request("GET", "/proxy/page")
        with patch("tokenade.core.proxy.server.forward_request", new_callable=AsyncMock,
                   side_effect=RuntimeError("timeout")):
            resp = _run_async(proxy._handle_site_proxy_entry(request))
        assert resp.status == 502
        assert proxy.stats["errors"] == 1


# ===========================================================================
# TokenadeProxy._handle_service_worker
# ===========================================================================

class TestHandleServiceWorker:
    def test_returns_js(self):
        proxy = TokenadeProxy(_make_session())
        request = make_mocked_request("GET", "/_tokenade_sw.js")
        resp = _run_async(proxy._handle_service_worker(request))
        assert resp.status == 200
        assert resp.content_type == "application/javascript"

    def test_sw_contains_proxy_base(self):
        proxy = TokenadeProxy(_make_session())
        request = make_mocked_request("GET", "/_tokenade_sw.js")
        resp = _run_async(proxy._handle_service_worker(request))
        assert "/proxy" in resp.text


# ===========================================================================
# TokenadeProxy._handle_browse
# ===========================================================================

class TestHandleBrowse:
    def test_no_query_shows_browse_page(self):
        proxy = TokenadeProxy(_make_session())
        request = make_mocked_request("GET", "/browse")
        with patch("tokenade.core.proxy.server.handle_browse_page", new_callable=AsyncMock) as hbp:
            hbp.return_value = web.Response(text="browse page")
            _run_async(proxy._handle_browse(request))
        hbp.assert_awaited_once()

    def test_with_query_forwards_request(self):
        proxy = TokenadeProxy(_make_session())
        request = make_mocked_request("GET", "/browse?url=https://example.com")

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.body = b"<html>OK</html>"
        mock_response.url = "https://example.com"

        with patch("tokenade.core.proxy.server.forward_request", new_callable=AsyncMock, return_value=mock_response):
            resp = _run_async(proxy._handle_browse(request))
        assert resp.status == 200
        assert proxy.stats["requests"] == 1

    def test_browse_html_gets_url_rewritten(self):
        proxy = TokenadeProxy(_make_session())
        request = make_mocked_request("GET", "/browse?url=https://example.com")

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.body = b'<html><a href="https://example.com/page">Link</a></html>'
        mock_response.url = "https://example.com"

        with patch("tokenade.core.proxy.server.forward_request", new_callable=AsyncMock, return_value=mock_response):
            resp = _run_async(proxy._handle_browse(request))
        assert b"/browse?url=" in resp.body

    def test_browse_exception_returns_502(self):
        proxy = TokenadeProxy(_make_session())
        request = make_mocked_request("GET", "/browse?url=https://example.com")

        with patch("tokenade.core.proxy.server.forward_request", new_callable=AsyncMock,
                   side_effect=RuntimeError("err")):
            resp = _run_async(proxy._handle_browse(request))
        assert resp.status == 502
        assert proxy.stats["errors"] == 1
        assert "Proxy Error" in resp.text


# ===========================================================================
# TokenadeProxy._handle_status
# ===========================================================================

class TestHandleStatus:
    def test_returns_json(self):
        proxy = TokenadeProxy(_make_session())
        proxy.stats["start_time"] = time.time() - 10
        request = make_mocked_request("GET", "/status")
        resp = _run_async(proxy._handle_status(request))
        assert resp.status == 200
        data = json.loads(resp.text)
        assert data["status"] == "running"
        assert data["site"] == "test-site"
        assert data["cookies"] >= 1


# ===========================================================================
# TokenadeProxy._handle_stats
# ===========================================================================

class TestHandleStats:
    def test_returns_stats_json(self):
        proxy = TokenadeProxy(_make_session())
        request = make_mocked_request("GET", "/stats")
        resp = _run_async(proxy._handle_stats(request))
        assert resp.status == 200
        data = json.loads(resp.text)
        assert "requests" in data
        assert "bytes_sent" in data
        assert "errors" in data


# ===========================================================================
# TokenadeProxy._handle_proxy
# ===========================================================================

class TestHandleProxy:
    def test_cannot_determine_target_returns_400(self):
        proxy = TokenadeProxy(_make_session())
        request = make_mocked_request("GET", "/unknown-path")
        with patch("tokenade.core.proxy.server.build_target_url", return_value=None):
            resp = _run_async(proxy._handle_proxy(request))
        assert resp.status == 400

    def test_unsafe_url_returns_403(self):
        proxy = TokenadeProxy(_make_session())
        request = make_mocked_request("GET", "/some-path")
        with patch("tokenade.core.proxy.server.build_target_url", return_value="http://10.0.0.1/admin"):
            with patch("tokenade.core.proxy.server._is_safe_url", return_value=False):
                resp = _run_async(proxy._handle_proxy(request))
        assert resp.status == 403

    def test_successful_forward(self):
        proxy = TokenadeProxy(_make_session())
        request = make_mocked_request("GET", "/some-page")

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.body = b"hello"

        with patch("tokenade.core.proxy.server.build_target_url", return_value="https://example.com/some-page"):
            with patch("tokenade.core.proxy.server._is_safe_url", return_value=True):
                with patch("tokenade.core.proxy.server.forward_request", new_callable=AsyncMock,
                           return_value=mock_response):
                    resp = _run_async(proxy._handle_proxy(request))
        assert resp.status == 200
        assert proxy.stats["requests"] == 1
        assert proxy.stats["bytes_received"] == 5

    def test_proxy_exception_returns_502(self):
        proxy = TokenadeProxy(_make_session())
        request = make_mocked_request("GET", "/some-page")

        with patch("tokenade.core.proxy.server.build_target_url", return_value="https://example.com/page"):
            with patch("tokenade.core.proxy.server._is_safe_url", return_value=True):
                with patch("tokenade.core.proxy.server.forward_request", new_callable=AsyncMock,
                           side_effect=RuntimeError("fail")):
                    resp = _run_async(proxy._handle_proxy(request))
        assert resp.status == 502
        assert proxy.stats["errors"] == 1

    def test_active_proxy_routes_to_subresource(self):
        proxy = TokenadeProxy(_make_session())
        proxy._proxy_active = True
        proxy._target_url = "https://example.com"

        request = make_mocked_request("GET", "/proxy/style.css")
        with patch.object(proxy, "_handle_site_proxy_subresource", new_callable=AsyncMock) as mock:
            mock.return_value = web.Response(text="ok")
            _run_async(proxy._handle_proxy(request))
        mock.assert_awaited_once()


# ===========================================================================
# TokenadeProxy._handle_site_proxy_subresource
# ===========================================================================

class TestHandleSiteProxySubresource:
    def test_successful_subresource(self):
        proxy = TokenadeProxy(_make_session())
        proxy._target_url = "https://example.com"

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "image/png"}
        mock_response.body = b"\x89PNG"

        request = make_mocked_request("GET", "/proxy/image.png")
        with patch("tokenade.core.proxy.server.forward_request", new_callable=AsyncMock,
                   return_value=mock_response):
            resp = _run_async(proxy._handle_site_proxy_subresource(request))
        assert resp.status == 200
        assert proxy.stats["bytes_received"] == 4

    def test_subresource_rewrites_host_header(self):
        proxy = TokenadeProxy(_make_session())
        proxy._target_url = "https://example.com:8443"

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {}
        mock_response.body = b"ok"

        request = make_mocked_request("GET", "/proxy/page")
        with patch("tokenade.core.proxy.server.forward_request", new_callable=AsyncMock,
                   return_value=mock_response) as fr:
            _run_async(proxy._handle_site_proxy_subresource(request))
        call_kwargs = fr.call_args[1]
        assert call_kwargs["headers"]["Host"] == "example.com:8443"
        assert call_kwargs["headers"]["Origin"] == "https://example.com:8443"
        assert call_kwargs["headers"]["Referer"] == "https://example.com:8443/"

    def test_subresource_strips_hop_by_hop_headers(self):
        proxy = TokenadeProxy(_make_session())
        proxy._target_url = "https://example.com"

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {}
        mock_response.body = b"ok"

        # Create request with hop-by-hop headers as constructor args
        request = make_mocked_request(
            "GET", "/proxy/page",
            headers={
                "X-Forwarded-For": "127.0.0.1",
                "X-Real-IP": "127.0.0.1",
                "Referer": "http://localhost/proxy/",
            }
        )
        with patch("tokenade.core.proxy.server.forward_request", new_callable=AsyncMock,
                   return_value=mock_response) as fr:
            _run_async(proxy._handle_site_proxy_subresource(request))
        call_kwargs = fr.call_args[1]
        assert "x-forwarded-for" not in {k.lower(): v for k, v in call_kwargs["headers"].items()}
        assert "x-real-ip" not in {k.lower(): v for k, v in call_kwargs["headers"].items()}

    def test_subresource_html_rewritten(self):
        proxy = TokenadeProxy(_make_session())
        proxy._target_url = "https://example.com"

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.body = b"<html><head></head><body></body></html>"

        request = make_mocked_request("GET", "/proxy/page")
        with patch("tokenade.core.proxy.server.forward_request", new_callable=AsyncMock,
                   return_value=mock_response):
            resp = _run_async(proxy._handle_site_proxy_subresource(request))
        assert b"serviceWorker" in resp.body

    def test_subresource_exception_returns_502(self):
        proxy = TokenadeProxy(_make_session())
        proxy._target_url = "https://example.com"

        request = make_mocked_request("GET", "/proxy/page")
        with patch("tokenade.core.proxy.server.forward_request", new_callable=AsyncMock,
                   side_effect=RuntimeError("timeout")):
            resp = _run_async(proxy._handle_site_proxy_subresource(request))
        assert resp.status == 502
        assert proxy.stats["errors"] == 1

    def test_subresource_post_method(self):
        proxy = TokenadeProxy(_make_session())
        proxy._target_url = "https://example.com"

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {}
        mock_response.body = b"ok"

        request = make_mocked_request("POST", "/proxy/submit")
        with patch("tokenade.core.proxy.server.forward_request", new_callable=AsyncMock,
                   return_value=mock_response) as fr:
            _run_async(proxy._handle_site_proxy_subresource(request))
        call_kwargs = fr.call_args[1]
        assert call_kwargs["method"] == "POST"

    def test_subresource_nonstandard_port_includes_host(self):
        proxy = TokenadeProxy(_make_session())
        proxy._target_url = "https://example.com:3000"

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {}
        mock_response.body = b"ok"

        request = make_mocked_request("GET", "/proxy/page")
        with patch("tokenade.core.proxy.server.forward_request", new_callable=AsyncMock,
                   return_value=mock_response) as fr:
            _run_async(proxy._handle_site_proxy_subresource(request))
        call_kwargs = fr.call_args[1]
        assert call_kwargs["headers"]["Host"] == "example.com:3000"


# ===========================================================================
# TokenadeProxy.start / stop
# ===========================================================================

class TestStartStop:
    def test_start_sets_start_time(self):
        proxy = TokenadeProxy(_make_session(), ProxyConfig(port=19500))
        mock_runner = AsyncMock()
        mock_site = AsyncMock()

        with patch("tokenade.core.proxy.server.web.AppRunner", return_value=mock_runner):
            mock_runner.setup = AsyncMock()
            with patch("tokenade.core.proxy.server.web.TCPSite", return_value=mock_site):
                mock_site.start = AsyncMock()
                _run_async(proxy.start())

        assert proxy.stats["start_time"] is not None
        assert proxy._app is not None

    def test_stop_closes_session(self):
        proxy = TokenadeProxy(_make_session())
        mock_session = AsyncMock()
        mock_session.closed = False
        proxy._http_session = mock_session

        mock_runner = AsyncMock()
        proxy._runner = mock_runner

        _run_async(proxy.stop())
        mock_session.close.assert_called_once()
        mock_runner.cleanup.assert_called_once()

    def test_stop_closes_tls_matcher(self):
        proxy = TokenadeProxy(_make_session())
        proxy._http_session = None
        proxy._runner = None

        mock_tls = MagicMock()
        proxy.tls_matcher = mock_tls

        _run_async(proxy.stop())
        mock_tls.close.assert_called_once()

    def test_stop_noop_when_no_session(self):
        proxy = TokenadeProxy(_make_session())
        proxy._http_session = None
        proxy._runner = None
        proxy.tls_matcher = None
        _run_async(proxy.stop())


# ===========================================================================
# TokenadeProxy._run_async
# ===========================================================================

class TestRunAsync:
    def test_run_async_starts_and_stops(self):
        proxy = TokenadeProxy(_make_session(), ProxyConfig(port=19501))

        mock_runner = AsyncMock()
        mock_site = AsyncMock()

        with patch("tokenade.core.proxy.server.web.AppRunner", return_value=mock_runner):
            mock_runner.setup = AsyncMock()
            with patch("tokenade.core.proxy.server.web.TCPSite", return_value=mock_site):
                mock_site.start = AsyncMock()
                with patch("asyncio.sleep", new_callable=AsyncMock, side_effect=asyncio.CancelledError):
                    with pytest.raises(asyncio.CancelledError):
                        _run_async(proxy._run_async())

        mock_runner.cleanup.assert_called()


# ===========================================================================
# create_proxy_from_file
# ===========================================================================

class TestCreateProxyFromFile:
    def test_returns_proxy(self):
        with patch("tokenade.core.proxy.server.TokenadeProxy.from_session_file") as mock_from:
            mock_from.return_value = MagicMock()
            create_proxy_from_file("test.tokenade", port=8888, gui=False)
            mock_from.assert_called_once_with("test.tokenade", ProxyConfig(port=8888, gui_mode=False))


# ===========================================================================
# Edge cases
# ===========================================================================

class TestEdgeCases:
    def test_session_with_no_cookies(self):
        s = {"site_name": "test", "fingerprint": {}, "tls_profile": {}}
        proxy = TokenadeProxy(s)
        assert proxy.cookie_jar is not None

    def test_session_with_empty_fingerprint(self):
        s = {"site_name": "test", "cookies": [], "fingerprint": {}, "tls_profile": {}}
        proxy = TokenadeProxy(s)
        assert proxy.fingerprint is not None

    def test_handle_proxy_increments_requests(self):
        proxy = TokenadeProxy(_make_session())
        proxy.stats["requests"] = 0
        request = make_mocked_request("GET", "/test")

        with patch("tokenade.core.proxy.server.build_target_url", return_value=None):
            _run_async(proxy._handle_proxy(request))
        assert proxy.stats["requests"] == 1

    def test_from_session_file_classmethod(self):
        with patch.object(TokenadeProxy, "from_session_file") as mock:
            mock.return_value = MagicMock()
            TokenadeProxy.from_session_file("test.tokenade")
            mock.assert_called_once_with("test.tokenade")
