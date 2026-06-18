"""Comprehensive tests for engine.py to boost coverage from 39% to 75%+."""

import json
import time
import tempfile
import os
import pytest
from collections import OrderedDict
from unittest.mock import MagicMock, patch

from tokenade.core.runtime.engine import (
    FingerprintMatcher,
    CookieJar,
    RuntimeConfig,
    RuntimeEngine,
    SessionValidator,
    create_engine_from_session,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def chrome_ua():
    return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


@pytest.fixture
def firefox_ua():
    return "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"


@pytest.fixture
def edge_ua():
    return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"


@pytest.fixture
def opera_ua():
    return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0"


@pytest.fixture
def sample_cookies():
    return [
        {"name": "session", "value": "abc123", "domain": ".example.com", "path": "/"},
        {"name": "pre", "value": "dark", "domain": ".example.com", "path": "/"},
    ]


@pytest.fixture
def jar():
    return CookieJar()


# ─── FingerprintMatcher ──────────────────────────────────────────────────────

class TestFingerprintMatcher:
    def test_init_no_fingerprint(self):
        fm = FingerprintMatcher()
        assert fm.fingerprint == {}
        assert fm.platform == "Win32"
        assert fm.language == "en-US"

    def test_init_with_fingerprint(self, chrome_ua):
        fm = FingerprintMatcher({"user_agent": chrome_ua, "platform": "MacIntel"})
        assert fm.ua == chrome_ua
        assert fm.platform == "MacIntel"

    def test_detect_browser_chrome(self, chrome_ua):
        fm = FingerprintMatcher({"user_agent": chrome_ua})
        assert fm._detect_browser() == "chrome"

    def test_detect_browser_firefox(self, firefox_ua):
        fm = FingerprintMatcher({"user_agent": firefox_ua})
        assert fm._detect_browser() == "firefox"

    def test_detect_browser_edge(self, edge_ua):
        fm = FingerprintMatcher({"user_agent": edge_ua})
        assert fm._detect_browser() == "edge"

    def test_detect_browser_opera(self, opera_ua):
        fm = FingerprintMatcher({"user_agent": opera_ua})
        assert fm._detect_browser() == "opera"

    def test_get_chrome_version(self, chrome_ua):
        fm = FingerprintMatcher({"user_agent": chrome_ua})
        assert fm._get_chrome_version() == "120"

    def test_get_chrome_version_no_match(self):
        fm = FingerprintMatcher({"user_agent": "RandomUA"})
        assert fm._get_chrome_version() == "120"

    def test_default_ua(self):
        fm = FingerprintMatcher()
        ua = fm._default_ua()
        assert "Chrome/120" in ua

    def test_get_headers_chrome(self, chrome_ua):
        fm = FingerprintMatcher({"user_agent": chrome_ua})
        headers = fm.get_headers("https://example.com/page")
        assert isinstance(headers, OrderedDict)
        assert "user-agent" in headers
        assert "sec-ch-ua" in headers
        assert "sec-ch-ua-mobile" in headers
        assert "sec-ch-ua-platform" in headers
        assert headers["upgrade-insecure-requests"] == "1"

    def test_get_headers_firefox(self, firefox_ua):
        fm = FingerprintMatcher({"user_agent": firefox_ua})
        headers = fm.get_headers("https://example.com/page")
        assert isinstance(headers, OrderedDict)
        assert "user-agent" in headers
        # Firefox doesn't have sec-ch-ua
        assert "sec-ch-ua" not in headers

    def test_get_headers_edge(self, edge_ua):
        fm = FingerprintMatcher({"user_agent": edge_ua})
        headers = fm.get_headers("https://example.com/page")
        assert isinstance(headers, OrderedDict)
        # Edge is detected as 'edge', not 'chrome', so no sec-ch-ua headers
        assert "accept" in headers
        assert "user-agent" in headers

    def test_get_headers_api_request(self, chrome_ua):
        fm = FingerprintMatcher({"user_agent": chrome_ua})
        headers = fm.get_headers("https://api.example.com/data", is_api=True)
        assert headers["accept"] == "application/json"
        assert headers["sec-fetch-mode"] == "cors"

    def test_get_headers_with_referer(self, chrome_ua):
        fm = FingerprintMatcher({"user_agent": chrome_ua})
        headers = fm.get_headers(
            "https://example.com/page",
            referer="https://example.com/home",
        )
        assert "referer" in headers
        assert headers["referer"] == "https://example.com/home"

    def test_get_headers_js_resource(self, chrome_ua):
        fm = FingerprintMatcher({"user_agent": chrome_ua})
        headers = fm.get_headers("https://example.com/app.js")
        assert headers["accept"] == "*/*"

    def test_get_headers_image_resource(self, chrome_ua):
        fm = FingerprintMatcher({"user_agent": chrome_ua})
        headers = fm.get_headers("https://example.com/logo.png")
        assert "image/" in headers["accept"]

    def test_get_headers_no_cache_control_with_referer(self, chrome_ua):
        fm = FingerprintMatcher({"user_agent": chrome_ua})
        headers = fm.get_headers(
            "https://example.com/page",
            referer="https://example.com/home",
        )
        assert "cache-control" not in headers

    def test_get_headers_cache_control_without_referer(self, chrome_ua):
        fm = FingerprintMatcher({"user_agent": chrome_ua})
        headers = fm.get_headers("https://example.com/page")
        assert headers.get("cache-control") == "max-age=0"

    def test_order_headers_custom_header(self, chrome_ua):
        fm = FingerprintMatcher({"user_agent": chrome_ua})
        headers = fm.get_headers("https://example.com/page")
        # connection is always added
        assert headers["connection"] == "keep-alive"

    def test_tls_config(self):
        fm = FingerprintMatcher()
        tls = fm.get_tls_config()
        assert "ssl_version" in tls
        assert "cipher_suite" in tls
        assert "extensions" in tls

    def test_chrome_ua_brands_fallback(self):
        fm = FingerprintMatcher({"user_agent": "Chrome/999.0.0.0"})
        headers = fm.get_headers("https://example.com")
        # Should fall back to known brands
        assert "sec-ch-ua" in headers


# ─── CookieJar ───────────────────────────────────────────────────────────────

class TestCookieJar:
    def test_add_cookie(self, jar):
        jar.add_cookie({"name": "a", "value": "1", "domain": ".example.com"})
        assert len(jar.to_list()) == 1

    def test_add_multiple_cookies(self, jar):
        jar.add_cookies([
            {"name": "a", "value": "1", "domain": ".example.com"},
            {"name": "b", "value": "2", "domain": ".example.com"},
        ])
        assert len(jar.to_list()) == 2

    def test_add_cookie_replaces_same_name(self, jar):
        jar.add_cookie({"name": "a", "value": "1", "domain": ".example.com"})
        jar.add_cookie({"name": "a", "value": "2", "domain": ".example.com"})
        assert len(jar.to_list()) == 1
        assert jar.to_list()[0]["value"] == "2"

    def test_get_for_request_match(self, jar):
        jar.add_cookie({"name": "sid", "value": "abc", "domain": ".example.com", "path": "/"})
        cookie_str = jar.get_for_request("https://example.com/page")
        assert "sid=abc" in cookie_str

    def test_get_for_request_subdomain(self, jar):
        jar.add_cookie({"name": "sid", "value": "abc", "domain": ".example.com", "path": "/"})
        cookie_str = jar.get_for_request("https://sub.example.com/page")
        assert "sid=abc" in cookie_str

    def test_get_for_request_no_match(self, jar):
        jar.add_cookie({"name": "sid", "value": "abc", "domain": ".other.com", "path": "/"})
        cookie_str = jar.get_for_request("https://example.com/page")
        assert cookie_str == ""

    def test_get_for_request_path_mismatch(self, jar):
        jar.add_cookie({"name": "sid", "value": "abc", "domain": ".example.com", "path": "/api"})
        cookie_str = jar.get_for_request("https://example.com/page")
        assert "sid=abc" not in cookie_str

    def test_get_for_request_expired_cookie_excluded(self, jar):
        jar.add_cookie({
            "name": "old", "value": "x", "domain": ".example.com",
            "path": "/", "expires": 1500000000000,
        })
        cookie_str = jar.get_for_request("https://example.com/page")
        assert "old=x" not in cookie_str

    def test_get_for_request_secure_cookie_on_http(self, jar):
        jar.add_cookie({
            "name": "sec", "value": "abc", "domain": ".example.com",
            "path": "/", "secure": True,
        })
        cookie_str = jar.get_for_request("http://example.com/page")
        assert "sec=abc" not in cookie_str

    def test_get_for_request_secure_cookie_on_https(self, jar):
        jar.add_cookie({
            "name": "sec", "value": "abc", "domain": ".example.com",
            "path": "/", "secure": True,
        })
        cookie_str = jar.get_for_request("https://example.com/page")
        assert "sec=abc" in cookie_str

    def test_empty_domain_matches_exact_host(self, jar):
        jar.add_cookie({"name": "sid", "value": "abc", "domain": "", "path": "/"})
        cookie_str = jar.get_for_request("https://example.com/page")
        assert "sid=abc" in cookie_str

    def test_host_cookie_with_domain_skipped(self, jar):
        jar.add_cookie({
            "name": "__Host-sid", "value": "abc", "domain": ".example.com",
            "path": "/",
        })
        cookie_str = jar.get_for_request("https://example.com/page")
        assert "__Host-sid" not in cookie_str

    def test_clear(self, jar):
        jar.add_cookie({"name": "a", "value": "1", "domain": ".x.com"})
        jar.clear()
        assert jar.to_list() == []

    def test_get_valid_cookies(self, jar):
        jar.add_cookie({"name": "a", "value": "1", "domain": ".example.com", "path": "/"})
        valid = jar.get_valid_cookies("https://example.com/page")
        assert len(valid) == 1
        assert valid[0]["name"] == "a"

    def test_get_valid_cookies_no_match(self, jar):
        jar.add_cookie({"name": "a", "value": "1", "domain": ".other.com", "path": "/"})
        valid = jar.get_valid_cookies("https://example.com/page")
        assert len(valid) == 0

    def test_get_expired_cookies(self, jar):
        jar.add_cookie({
            "name": "old", "value": "x", "domain": ".example.com",
            "path": "/", "expires": 1000000000,
        })
        expired = jar.get_expired_cookies()
        assert len(expired) == 1

    def test_get_expired_cookies_none_expired(self, jar):
        jar.add_cookie({
            "name": "fresh", "value": "x", "domain": ".example.com",
            "path": "/", "expires": int(time.time()) + 3600,
        })
        expired = jar.get_expired_cookies()
        assert len(expired) == 0

    def test_prune_expired(self, jar):
        jar.add_cookie({
            "name": "old", "value": "x", "domain": ".example.com",
            "path": "/", "expires": 1000000000,
        })
        jar.add_cookie({
            "name": "fresh", "value": "y", "domain": ".example.com",
            "path": "/", "expires": int(time.time()) + 3600,
        })
        removed = jar.prune_expired()
        assert removed == 1
        assert len(jar.to_list()) == 1

    def test_prune_expired_removes_empty_domain(self, jar):
        jar.add_cookie({
            "name": "old", "value": "x", "domain": ".example.com",
            "path": "/", "expires": 1000000000,
        })
        jar.prune_expired()
        assert ".example.com" not in jar.cookies

    def test_cookie_expired_milliseconds(self, jar):
        # Value > 1262304000000 triggers ms→s conversion, resulting in a past timestamp
        jar.add_cookie({
            "name": "old_ms", "value": "x", "domain": ".example.com",
            "path": "/", "expires": 1500000000000,
        })
        assert jar._is_cookie_expired(jar.cookies["example.com"][0]) is True

    def test_cookie_not_expired_session(self, jar):
        jar.add_cookie({
            "name": "session", "value": "x", "domain": ".example.com",
            "path": "/",
        })
        assert jar._is_cookie_expired(jar.cookies["example.com"][0]) is False

    def test_cookie_expires_zero(self, jar):
        jar.add_cookie({
            "name": "sess", "value": "x", "domain": ".example.com",
            "path": "/", "expires": 0,
        })
        assert jar._is_cookie_expired(jar.cookies["example.com"][0]) is False


# ─── RuntimeEngine ───────────────────────────────────────────────────────────

class TestRuntimeEngine:
    def _make_engine(self, **overrides):
        config = RuntimeConfig(use_tls_match=False, **overrides)
        with patch("requests.Session") as mock_cls:
            mock_session = MagicMock()
            mock_cls.return_value = mock_session
            engine = RuntimeEngine(config)
            engine._session = mock_session
        return engine, mock_session

    def test_init(self):
        engine, _ = self._make_engine()
        assert engine.cookie_jar is not None
        assert engine.tokens == {}
        engine.close()

    def test_init_with_cookies(self):
        engine, _ = self._make_engine(cookies=[
            {"name": "sid", "value": "abc", "domain": ".example.com"},
        ])
        assert len(engine.cookie_jar.to_list()) == 1
        engine.close()

    def test_init_with_tokens(self):
        engine, _ = self._make_engine(tokens=[
            {"token_type": "oauth", "value": "tok123"},
        ])
        assert engine.tokens["oauth"]["value"] == "tok123"
        engine.close()

    def test_get_request(self):
        engine, mock = self._make_engine()
        mock.request.return_value = MagicMock(status_code=200, content=b"ok", cookies=[])
        resp = engine.get("https://example.com")
        assert resp.status_code == 200
        assert mock.request.call_args[1]["method"] == "GET"
        engine.close()

    def test_post_request(self):
        engine, mock = self._make_engine()
        mock.request.return_value = MagicMock(status_code=201, content=b"created", cookies=[])
        resp = engine.post("https://example.com/api", json_data={"key": "val"})
        assert resp.status_code == 201
        assert mock.request.call_args[1]["method"] == "POST"
        engine.close()

    def test_put_request(self):
        engine, mock = self._make_engine()
        mock.request.return_value = MagicMock(status_code=200, content=b"ok", cookies=[])
        engine.put("https://example.com/api/1", data="body")
        assert mock.request.call_args[1]["method"] == "PUT"
        engine.close()

    def test_delete_request(self):
        engine, mock = self._make_engine()
        mock.request.return_value = MagicMock(status_code=204, content=b"", cookies=[])
        engine.delete("https://example.com/api/1")
        assert mock.request.call_args[1]["method"] == "DELETE"
        engine.close()

    def test_prepare_request_with_cookies(self):
        engine, _ = self._make_engine()
        engine.cookie_jar.add_cookie({
            "name": "sid", "value": "abc", "domain": ".example.com", "path": "/",
        })
        headers = engine._prepare_request("GET", "https://example.com/page")
        assert "cookie" in headers
        assert "sid=abc" in headers["cookie"]
        engine.close()

    def test_prepare_request_with_custom_headers(self):
        engine, _ = self._make_engine()
        headers = engine._prepare_request(
            "GET", "https://example.com/page",
            headers={"X-Custom": "val"},
        )
        assert headers["X-Custom"] == "val"
        engine.close()

    def test_prepare_request_custom_config_headers(self):
        engine, _ = self._make_engine(custom_headers={"X-From-Config": "yes"})
        headers = engine._prepare_request("GET", "https://example.com/page")
        assert headers["X-From-Config"] == "yes"
        engine.close()

    def test_update_cookies_from_response(self):
        engine, mock = self._make_engine()
        mock_resp = MagicMock(status_code=200, content=b"ok")
        mock_cookie = MagicMock()
        mock_cookie.name = "resp_cookie"
        mock_cookie.value = "resp_val"
        mock_cookie.domain = ".example.com"
        mock_cookie.path = "/"
        mock_cookie.secure = False
        mock_resp.cookies = [mock_cookie]
        mock.request.return_value = mock_resp

        engine.get("https://example.com")
        cookies = engine.cookie_jar.to_list()
        assert any(c["name"] == "resp_cookie" for c in cookies)
        engine.close()

    def test_update_cookies_from_response_none_domain(self):
        engine, mock = self._make_engine()
        mock_resp = MagicMock(status_code=200, content=b"ok")
        mock_cookie = MagicMock()
        mock_cookie.name = "nd_cookie"
        mock_cookie.value = "val"
        mock_cookie.domain = None
        mock_cookie.path = None
        mock_cookie.secure = False
        mock_resp.cookies = [mock_cookie]
        mock.request.return_value = mock_resp

        engine.get("https://example.com")
        cookies = engine.cookie_jar.to_list()
        assert any(c["name"] == "nd_cookie" for c in cookies)
        engine.close()

    def test_request_with_referer(self):
        engine, mock = self._make_engine()
        mock.request.return_value = MagicMock(status_code=200, content=b"ok", cookies=[])
        engine.get("https://example.com/page", referer="https://example.com/home")
        headers = mock.request.call_args[1]["headers"]
        assert "referer" in headers
        engine.close()

    def test_context_manager(self):
        with patch("requests.Session") as mock_cls:
            mock_session = MagicMock()
            mock_cls.return_value = mock_session
            with RuntimeEngine(RuntimeConfig(use_tls_match=False)) as engine:
                engine._session = mock_session
            mock_session.close.assert_called_once()

    def test_has_tls_matching_false(self):
        engine, _ = self._make_engine()
        assert engine.has_tls_matching is False
        engine.close()

    def test_rate_limiting(self):
        engine, _ = self._make_engine(rate_limit=0.1)
        mock_resp = MagicMock(status_code=200, content=b"ok", cookies=[])
        engine._session.request.return_value = mock_resp

        start = time.time()
        engine.get("https://example.com/1")
        engine.get("https://example.com/2")
        elapsed = time.time() - start
        assert elapsed >= 0.09
        engine.close()

    def test_rate_limit_zero(self):
        engine, _ = self._make_engine(rate_limit=0)
        mock_resp = MagicMock(status_code=200, content=b"ok", cookies=[])
        engine._session.request.return_value = mock_resp
        start = time.time()
        engine.get("https://example.com")
        elapsed = time.time() - start
        assert elapsed < 0.1
        engine.close()

    def test_proxy_config(self):
        engine, _ = self._make_engine(proxy="http://proxy:8080")
        assert engine._session.proxies["http"] == "http://proxy:8080"
        assert engine._session.proxies["https"] == "http://proxy:8080"
        engine.close()

    def test_no_proxy(self):
        engine, _ = self._make_engine()
        # With proxy=None, the proxy setup block is skipped
        # Just verify engine works normally without proxy
        mock_resp = MagicMock(status_code=200, content=b"ok", cookies=[])
        engine._session.request.return_value = mock_resp
        resp = engine.get("https://example.com")
        assert resp.status_code == 200
        engine.close()

    def test_ssl_verify_true(self):
        engine, _ = self._make_engine(verify_ssl=True)
        assert engine._session.verify is True
        engine.close()

    def test_ssl_verify_false(self):
        engine, _ = self._make_engine(verify_ssl=False)
        assert engine._session.verify is False
        engine.close()

    def test_request_with_tls_matcher(self):
        engine, mock = self._make_engine()
        mock_matcher = MagicMock()
        mock_matcher.request.return_value = MagicMock(status_code=200, content=b"tls", cookies=[])
        engine._tls_matcher = mock_matcher

        resp = engine.request("GET", "https://example.com", use_tls=True)
        assert resp.status_code == 200
        mock_matcher.request.assert_called_once()
        engine.close()

    def test_request_tls_auto_when_available(self):
        engine, mock = self._make_engine()
        mock_matcher = MagicMock()
        mock_matcher.request.return_value = MagicMock(status_code=200, content=b"", cookies=[])
        engine._tls_matcher = mock_matcher

        engine.request("GET", "https://example.com")
        mock_matcher.request.assert_called_once()
        engine.close()

    def test_request_tls_disabled(self):
        engine, mock = self._make_engine()
        mock_matcher = MagicMock()
        engine._tls_matcher = mock_matcher

        engine.request("GET", "https://example.com", use_tls=False)
        mock.request.return_value = MagicMock(status_code=200, content=b"", cookies=[])
        mock.request.assert_called_once()
        engine.close()

    def test_fingerprint_headers_in_request(self):
        engine, mock = self._make_engine()
        mock.request.return_value = MagicMock(status_code=200, content=b"", cookies=[])
        engine.get("https://example.com")
        headers = mock.request.call_args[1]["headers"]
        assert "user-agent" in headers
        engine.close()


# ─── SessionValidator ────────────────────────────────────────────────────────

class TestSessionValidator:
    def _make_validator(self):
        mock_engine = MagicMock()
        return SessionValidator(mock_engine), mock_engine

    def test_validate_google_valid(self):
        val, engine = self._make_validator()
        engine.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"result": {"data": [1, 2, 3]}},
        )
        result = val.validate_google_session()
        assert result["valid"] is True
        assert result["projects"] == 3

    def test_validate_google_403(self):
        val, engine = self._make_validator()
        engine.get.return_value = MagicMock(status_code=403)
        result = val.validate_google_session()
        assert result["valid"] is False
        assert result["status_code"] == 403

    def test_validate_google_unexpected_status(self):
        val, engine = self._make_validator()
        engine.get.return_value = MagicMock(status_code=503)
        result = val.validate_google_session()
        assert result["valid"] is False
        assert "Unexpected status" in result["error"]

    def test_validate_google_exception(self):
        val, engine = self._make_validator()
        engine.get.side_effect = Exception("timeout")
        result = val.validate_google_session()
        assert result["valid"] is False
        assert "timeout" in result["error"]

    def test_validate_github_valid(self):
        val, engine = self._make_validator()
        engine.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"login": "testuser", "name": "Test"},
        )
        engine.tokens = {"oauth_access": {"value": "tok123"}}
        result = val.validate_github_session()
        assert result["valid"] is True
        assert result["login"] == "testuser"

    def test_validate_github_no_token(self):
        val, engine = self._make_validator()
        engine.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"login": "user"},
        )
        engine.tokens = {}
        result = val.validate_github_session()
        assert result["valid"] is True

    def test_validate_github_401(self):
        val, engine = self._make_validator()
        engine.get.return_value = MagicMock(status_code=401)
        engine.tokens = {}
        result = val.validate_github_session()
        assert result["valid"] is False
        assert "Token expired" in result["error"]

    def test_validate_github_unexpected_status(self):
        val, engine = self._make_validator()
        engine.get.return_value = MagicMock(status_code=500)
        engine.tokens = {}
        result = val.validate_github_session()
        assert result["valid"] is False
        assert result["status_code"] == 500

    def test_validate_github_exception(self):
        val, engine = self._make_validator()
        engine.get.side_effect = Exception("conn error")
        engine.tokens = {}
        result = val.validate_github_session()
        assert result["valid"] is False
        assert "conn error" in result["error"]

    def test_validate_generic_success(self):
        val, engine = self._make_validator()
        engine.get.return_value = MagicMock(status_code=200, content=b"OK")
        result = val.validate_generic("https://example.com")
        assert result["valid"] is True
        assert result["status_code"] == 200

    def test_validate_generic_custom_codes(self):
        val, engine = self._make_validator()
        engine.get.return_value = MagicMock(status_code=201, content=b"created")
        result = val.validate_generic("https://example.com", success_codes=[201])
        assert result["valid"] is True

    def test_validate_generic_failure(self):
        val, engine = self._make_validator()
        engine.get.return_value = MagicMock(status_code=500, content=b"err")
        result = val.validate_generic("https://example.com")
        assert result["valid"] is False

    def test_validate_generic_exception(self):
        val, engine = self._make_validator()
        engine.get.side_effect = Exception("network")
        result = val.validate_generic("https://example.com")
        assert result["valid"] is False
        assert "network" in result["error"]


# ─── create_engine_from_session ──────────────────────────────────────────────

class TestCreateEngineFromSession:
    def test_create_from_file(self):
        session_data = {
            "fingerprint": {"user_agent": "TestUA/1.0"},
            "cookies": [{"name": "sid", "value": "abc"}],
            "tokens": [{"token_type": "oauth", "value": "tok"}],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(session_data, f)
            path = f.name

        try:
            with patch("requests.Session") as mock_cls:
                mock_session = MagicMock()
                mock_cls.return_value = mock_session
                engine = create_engine_from_session(path)
                assert engine.config.user_agent == "TestUA/1.0"
                assert len(engine.cookie_jar.to_list()) == 1
                engine.close()
        finally:
            os.unlink(path)

    def test_create_from_file_defaults(self):
        session_data = {}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(session_data, f)
            path = f.name

        try:
            with patch("requests.Session") as mock_cls:
                mock_session = MagicMock()
                mock_cls.return_value = mock_session
                engine = create_engine_from_session(path)
                assert engine.config.user_agent == ""
                engine.close()
        finally:
            os.unlink(path)

    def test_create_from_missing_file(self):
        with pytest.raises(FileNotFoundError):
            create_engine_from_session("/nonexistent/path.json")


# ─── TLS matcher setup ──────────────────────────────────────────────────────

class TestTlsMatcherSetup:
    def test_setup_tls_matcher_disabled(self):
        with patch("requests.Session"):
            engine = RuntimeEngine(RuntimeConfig(use_tls_match=False))
            assert engine._tls_matcher is None
            engine.close()

    def test_setup_tls_matcher_exception(self):
        with patch("requests.Session"):
            with patch("tokenade.core.runtime.engine.create_tls_matcher", side_effect=Exception("no curl")):
                engine = RuntimeEngine(RuntimeConfig(use_tls_match=True))
                assert engine._tls_matcher is None
                engine.close()

    def test_setup_tls_matcher_success(self):
        mock_matcher = MagicMock()
        with patch("requests.Session"):
            with patch("tokenade.core.runtime.engine.create_tls_matcher", return_value=mock_matcher):
                engine = RuntimeEngine(RuntimeConfig(
                    use_tls_match=True,
                    tls_browser="chrome",
                    tls_version="120",
                    tls_impersonate="chrome120",
                ))
                assert engine._tls_matcher is mock_matcher
                engine.close()
