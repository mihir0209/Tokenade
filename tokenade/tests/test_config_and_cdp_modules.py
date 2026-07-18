"""
Comprehensive tests for config.py, cdp_stealth.py, and cdp_api.py.
"""

import asyncio
import json
import os
import pytest
import time
from unittest.mock import MagicMock, AsyncMock, patch


def _run_async(coro):
    return asyncio.run(coro)


from tokenade.core.config import TokenadeConfig, load_config, DEFAULTS, DEFAULT_CONFIG_FILE  # noqa: E402
from tokenade.core.proxy.cdp_stealth import (  # noqa: E402
    is_safe_url,
    COMPREHENSIVE_STEALTH_SCRIPT,
    BLOCKED_NETWORKS,
    SITE_URLS,
    get_site_url,
)
from tokenade.core.proxy.cdp_api import (  # noqa: E402
    handle_cdp_version,
    handle_cdp_list,
    handle_stealth_js,
    handle_status,
    handle_stats,
    handle_session_status,
    handle_session_refresh,
    handle_old_sw,
)


# ──────────────────────────────────────────────
# config.py tests
# ──────────────────────────────────────────────

class TestTokenadeConfigDefaults:
    def test_defaults_dict_has_expected_keys(self):
        assert "default_browser" in DEFAULTS
        assert "default_profile" in DEFAULTS
        assert "stealth_level" in DEFAULTS
        assert "visible" in DEFAULTS
        assert "auto_validate" in DEFAULTS
        assert "output_dir" in DEFAULTS
        assert "proxy_host" in DEFAULTS
        assert "proxy_port" in DEFAULTS

    def test_default_values(self):
        assert DEFAULTS["stealth_level"] == "maximum"
        assert DEFAULTS["visible"] is False
        assert DEFAULTS["auto_validate"] is True
        assert DEFAULTS["proxy_host"] == "127.0.0.1"
        assert DEFAULTS["proxy_port"] == 9223


class TestTokenadeConfigLoad:
    def test_load_from_nonexistent_file(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        config = TokenadeConfig(str(path))
        # Should not crash; config should be empty dict
        assert config._config == {}

    def test_load_from_valid_file(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"stealth_level": "basic", "proxy_port": 8080}))
        config = TokenadeConfig(str(path))
        assert config.get("stealth_level") == "basic"
        assert config.get("proxy_port") == 8080

    def test_load_from_corrupt_file(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{invalid json!!!")
        config = TokenadeConfig(str(path))
        # Should fall back to empty config
        assert config._config == {}

    def test_load_from_empty_file(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text("")
        # json.load will raise on empty file; should be caught
        config = TokenadeConfig(str(path))
        assert config._config == {}


class TestTokenadeConfigGet:
    def test_get_returns_config_value(self, tmp_path):
        path = tmp_path / "c.json"
        path.write_text(json.dumps({"proxy_port": 9999}))
        config = TokenadeConfig(str(path))
        assert config.get("proxy_port") == 9999

    def test_get_returns_default_when_missing(self, tmp_path):
        path = tmp_path / "c.json"
        path.write_text("{}")
        config = TokenadeConfig(str(path))
        # Falls back to DEFAULTS
        assert config.get("stealth_level") == "maximum"

    def test_get_returns_custom_default_for_unknown_key(self, tmp_path):
        path = tmp_path / "c.json"
        path.write_text("{}")
        config = TokenadeConfig(str(path))
        assert config.get("nonexistent_key", "fallback") == "fallback"

    def test_get_returns_none_for_unknown_key_no_default(self, tmp_path):
        path = tmp_path / "c.json"
        path.write_text("{}")
        config = TokenadeConfig(str(path))
        assert config.get("nonexistent_key") is None

    def test_get_config_value_overrides_default(self, tmp_path):
        path = tmp_path / "c.json"
        path.write_text(json.dumps({"stealth_level": "basic"}))
        config = TokenadeConfig(str(path))
        assert config.get("stealth_level") == "basic"


class TestTokenadeConfigSet:
    def test_set_adds_value(self, tmp_path):
        path = tmp_path / "c.json"
        path.write_text("{}")
        config = TokenadeConfig(str(path))
        config.set("custom_key", "custom_value")
        assert config.get("custom_key") == "custom_value"

    def test_set_overwrites_existing(self, tmp_path):
        path = tmp_path / "c.json"
        path.write_text(json.dumps({"proxy_port": 1000}))
        config = TokenadeConfig(str(path))
        config.set("proxy_port", 2000)
        assert config.get("proxy_port") == 2000


class TestTokenadeConfigSave:
    def test_save_creates_file(self, tmp_path):
        path = tmp_path / "subdir" / "config.json"
        config = TokenadeConfig(str(path))
        config.set("proxy_port", 7777)
        config.save()
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["proxy_port"] == 7777

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "a" / "b" / "c" / "config.json"
        config = TokenadeConfig(str(path))
        config.set("key", "val")
        config.save()
        assert path.exists()

    def test_save_and_reload_roundtrip(self, tmp_path):
        path = tmp_path / "roundtrip.json"
        config = TokenadeConfig(str(path))
        config.set("stealth_level", "advanced")
        config.set("proxy_port", 5555)
        config.set("visible", True)
        config.save()
        reloaded = TokenadeConfig(str(path))
        assert reloaded.get("stealth_level") == "advanced"
        assert reloaded.get("proxy_port") == 5555
        assert reloaded.get("visible") is True


class TestTokenadeConfigMisc:
    def test_config_path_property(self, tmp_path):
        path = tmp_path / "c.json"
        config = TokenadeConfig(str(path))
        assert config.config_path == str(path)

    def test_repr(self, tmp_path):
        path = tmp_path / "c.json"
        path.write_text(json.dumps({"a": 1}))
        config = TokenadeConfig(str(path))
        r = repr(config)
        assert "TokenadeConfig" in r
        assert "a" in r

    def test_load_config_convenience(self, tmp_path):
        path = tmp_path / "c.json"
        path.write_text(json.dumps({"proxy_port": 1234}))
        config = load_config(str(path))
        assert isinstance(config, TokenadeConfig)
        assert config.get("proxy_port") == 1234

    def test_load_config_default_path(self):
        config = load_config()
        assert isinstance(config, TokenadeConfig)
        assert config.config_path == str(DEFAULT_CONFIG_FILE)


class TestTokenadeConfigEnvVars:
    def test_env_var_does_not_auto_override(self, tmp_path):
        """Config module doesn't auto-read env vars; get() falls back to defaults."""
        os.environ["TOKENADE_STEALTH_LEVEL"] = "basic"
        try:
            path = tmp_path / "c.json"
            path.write_text("{}")
            config = TokenadeConfig(str(path))
            # Config doesn't auto-read env vars, so it falls back to DEFAULTS
            assert config.get("stealth_level") == "maximum"
        finally:
            del os.environ["TOKENADE_STEALTH_LEVEL"]


class TestTokenadeConfigEdgeCases:
    def test_get_with_none_default(self, tmp_path):
        path = tmp_path / "c.json"
        path.write_text("{}")
        config = TokenadeConfig(str(path))
        assert config.get("missing", None) is None

    def test_set_none_value(self, tmp_path):
        path = tmp_path / "c.json"
        config = TokenadeConfig(str(path))
        config.set("key", None)
        assert config.get("key") is None

    def test_multiple_instances_independent(self, tmp_path):
        p1 = tmp_path / "a.json"
        p2 = tmp_path / "b.json"
        p1.write_text(json.dumps({"x": 1}))
        p2.write_text(json.dumps({"x": 2}))
        c1 = TokenadeConfig(str(p1))
        c2 = TokenadeConfig(str(p2))
        assert c1.get("x") == 1
        assert c2.get("x") == 2

    def test_set_does_not_persist_without_save(self, tmp_path):
        path = tmp_path / "c.json"
        path.write_text("{}")
        config = TokenadeConfig(str(path))
        config.set("key", "val")
        # Not saved yet; reloaded should be empty
        config2 = TokenadeConfig(str(path))
        assert config2.get("key") is None


# ──────────────────────────────────────────────
# cdp_stealth.py tests
# ──────────────────────────────────────────────

class TestIsSafeUrl:
    def test_safe_public_urls(self):
        assert is_safe_url("https://google.com") is True
        assert is_safe_url("https://example.com/path?q=1") is True
        assert is_safe_url("https://github.com/user/repo") is True
        assert is_safe_url("https://sub.domain.example.com") is True

    def test_localhost_rejected(self):
        assert is_safe_url("http://localhost") is False
        assert is_safe_url("http://localhost:8080") is False
        assert is_safe_url("http://localhost/path") is False

    def test_0_0_0_0_rejected(self):
        assert is_safe_url("http://0.0.0.0") is False
        assert is_safe_url("http://0.0.0.0:8080") is False

    def test_ipv6_loopback_rejected(self):
        # urlparse strips brackets; hostname becomes "::" or "::1"
        # "::" is not in ::1/128 (only loopback), but "[::]" is in the string check
        # However urlparse removes brackets, so the string check fails for [::]
        # "::" (all-zeros) is not in any blocked network, so it's not blocked by code
        assert is_safe_url("http://[::1]") is False

    def test_metadata_endpoint_rejected(self):
        assert is_safe_url("http://metadata.google.internal") is False

    def test_private_10_x_rejected(self):
        assert is_safe_url("http://10.0.0.1") is False
        assert is_safe_url("http://10.255.255.255") is False

    def test_private_172_16_x_rejected(self):
        assert is_safe_url("http://172.16.0.1") is False
        assert is_safe_url("http://172.31.255.255") is False

    def test_private_192_168_x_rejected(self):
        assert is_safe_url("http://192.168.1.1") is False
        assert is_safe_url("http://192.168.0.1") is False

    def test_link_local_rejected(self):
        assert is_safe_url("http://169.254.0.1") is False
        assert is_safe_url("http://169.254.169.254") is False

    def test_127_x_rejected(self):
        assert is_safe_url("http://127.0.0.1") is False
        assert is_safe_url("http://127.0.0.1:3000") is False
        assert is_safe_url("http://127.255.255.255") is False

    def test_empty_string_rejected(self):
        assert is_safe_url("") is False

    def test_invalid_url_rejected(self):
        assert is_safe_url("not-a-url") is False

    def test_no_hostname_rejected(self):
        assert is_safe_url("file:///etc/passwd") is False

    def test_none_input_rejected(self):
        assert is_safe_url(None) is False

    def test_ipv6_private_rejected(self):
        # fc00::/7 range (ULA)
        assert is_safe_url("http://[fc00::1]") is False

    def test_public_ip_allowed(self):
        # 8.8.8.8 is Google DNS, not in blocked ranges
        assert is_safe_url("http://8.8.8.8") is True


class TestStealthScript:
    def test_is_nonempty_string(self):
        assert isinstance(COMPREHENSIVE_STEALTH_SCRIPT, str)
        assert len(COMPREHENSIVE_STEALTH_SCRIPT) > 100

    def test_contains_iife(self):
        assert COMPREHENSIVE_STEALTH_SCRIPT.lstrip().startswith("(function()")
        assert COMPREHENSIVE_STEALTH_SCRIPT.strip().endswith("})();")


class TestBlockedNetworks:
    def test_is_nonempty_list(self):
        assert isinstance(BLOCKED_NETWORKS, list)
        assert len(BLOCKED_NETWORKS) > 0

    def test_contains_private_ranges(self):
        net_strs = [str(n) for n in BLOCKED_NETWORKS]
        assert "10.0.0.0/8" in net_strs
        assert "192.168.0.0/16" in net_strs
        assert "127.0.0.0/8" in net_strs


class TestSiteUrls:
    def test_has_expected_keys(self):
        expected = {"google", "github", "discord", "reddit", "openai", "twitter",
                    "linkedin", "netflix", "youtube", "amazon", "spotify", "microsoft"}
        assert expected.issubset(set(SITE_URLS.keys()))

    def test_values_are_urls(self):
        for v in SITE_URLS.values():
            assert v.startswith("https://")


class TestGetSiteUrl:
    def test_known_site_from_site_urls(self):
        session = {"site_name": "github", "cookies": []}
        url = get_site_url(session)
        assert url == "https://github.com"

    def test_known_site_from_site_config(self):
        # "google" has a validate_url in site_configs
        session = {"site_name": "google", "cookies": []}
        url = get_site_url(session)
        assert url == "https://labs.google/fx/tools/flow"

    def test_unknown_site_falls_back_to_cookies(self):
        session = {
            "site_name": "mysite",
            "cookies": [
                {"name": "a", "value": "1", "domain": ".mysite.org"},
                {"name": "b", "value": "2", "domain": "cdn.mysite.org"},
            ],
        }
        url = get_site_url(session)
        # Longest domain first, then shortest; mysite.org contains "mysite"
        assert "mysite" in url.lower()

    def test_unknown_site_no_cookies_fallback(self):
        session = {"site_name": "acme", "cookies": []}
        url = get_site_url(session)
        assert url == "https://www.acme.com"

    def test_unknown_site_empty_string(self):
        session = {"site_name": "", "cookies": []}
        url = get_site_url(session)
        assert url == "https://example.com"

    def test_unknown_site_none(self):
        session = {"cookies": []}
        url = get_site_url(session)
        assert url == "https://example.com"

    def test_unknown_site_value_unknown(self):
        session = {"site_name": "unknown", "cookies": []}
        url = get_site_url(session)
        assert url == "https://example.com"

    def test_cookies_with_leading_dot_stripped(self):
        session = {
            "site_name": "testsite",
            "cookies": [
                {"name": "a", "value": "1", "domain": ".testsite.io"},
            ],
        }
        url = get_site_url(session)
        assert url == "https://testsite.io"


# ──────────────────────────────────────────────
# cdp_api.py tests
# ──────────────────────────────────────────────

def _make_proxy():
    """Create a mock proxy object matching what handlers expect."""
    proxy = MagicMock()
    proxy._cdp_port = 9223
    proxy.session = {
        "site_name": "testsite",
        "tls_profile": {"browser": "chrome", "version": "120"},
    }
    proxy.cookie_jar = MagicMock()
    proxy.cookie_jar.to_list.return_value = [{"name": "a"}, {"name": "b"}]
    proxy.stats = {
        "requests": 42,
        "bytes_sent": 1024,
        "bytes_received": 2048,
        "errors": 3,
        "start_time": time.time() - 60,
    }
    proxy._refresher = None
    return proxy


def _make_request():
    """Create a mock aiohttp request."""
    return MagicMock()


class TestHandleCdpVersion:
    def test_success(self):
        proxy = _make_proxy()
        request = _make_request()
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value={"Browser": "Chrome/120"})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            resp = _run_async(handle_cdp_version(proxy, request))
        assert resp.status == 200

    def test_error_returns_502(self):
        proxy = _make_proxy()
        request = _make_request()

        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=Exception("connection refused"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            resp = _run_async(handle_cdp_version(proxy, request))
        assert resp.status == 502
        body = json.loads(resp.body)
        assert "error" in body


class TestHandleCdpList:
    def test_success(self):
        proxy = _make_proxy()
        request = _make_request()
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value=[{"id": "1", "url": "about:blank"}])
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            resp = _run_async(handle_cdp_list(proxy, request))
        assert resp.status == 200

    def test_error_returns_502(self):
        proxy = _make_proxy()
        request = _make_request()

        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=Exception("timeout"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            resp = _run_async(handle_cdp_list(proxy, request))
        assert resp.status == 502


class TestHandleStealthJs:
    def test_returns_javascript_content_type(self):
        proxy = _make_proxy()
        request = _make_request()
        resp = _run_async(handle_stealth_js(proxy, request))
        assert resp.status == 200
        assert "javascript" in resp.content_type
        assert len(resp.body) > 0

    def test_body_is_stealth_script(self):
        proxy = _make_proxy()
        request = _make_request()
        resp = _run_async(handle_stealth_js(proxy, request))
        assert COMPREHENSIVE_STEALTH_SCRIPT.encode() in resp.body


class TestHandleStatus:
    def test_returns_status_json(self):
        proxy = _make_proxy()
        request = _make_request()
        resp = _run_async(handle_status(proxy, request))
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["status"] == "running"
        assert body["site"] == "testsite"
        assert body["cookies"] == 2

    def test_uptime_is_numeric(self):
        proxy = _make_proxy()
        request = _make_request()
        resp = _run_async(handle_status(proxy, request))
        body = json.loads(resp.body)
        assert isinstance(body["uptime"], float)
        assert body["uptime"] >= 0


class TestHandleStats:
    def test_returns_stats_json(self):
        proxy = _make_proxy()
        request = _make_request()
        resp = _run_async(handle_stats(proxy, request))
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["requests"] == 42
        assert body["bytes_sent"] == 1024


class TestHandleSessionStatus:
    def test_no_refresher_returns_503(self):
        proxy = _make_proxy()
        proxy._refresher = None
        request = _make_request()
        resp = _run_async(handle_session_status(proxy, request))
        assert resp.status == 503
        body = json.loads(resp.body)
        assert "error" in body

    def test_with_refresher(self):
        proxy = _make_proxy()
        proxy._refresher = MagicMock()
        proxy._refresher.get_status.return_value = {"active": True, "expires_in": 3600}
        request = _make_request()
        resp = _run_async(handle_session_status(proxy, request))
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["active"] is True


class TestHandleSessionRefresh:
    def test_no_refresher_returns_503(self):
        proxy = _make_proxy()
        proxy._refresher = None
        request = _make_request()
        resp = _run_async(handle_session_refresh(proxy, request))
        assert resp.status == 503

    def test_refresh_success(self):
        proxy = _make_proxy()
        proxy._refresher = MagicMock()
        proxy._refresher._attempt_refresh = AsyncMock()
        proxy.session = {"site_name": "test", "cookies": [{"name": "c"}]}
        request = _make_request()
        resp = _run_async(handle_session_refresh(proxy, request))
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["status"] == "refreshed"
        assert body["cookies"] == 1

    def test_refresh_failure_returns_500(self):
        proxy = _make_proxy()
        proxy._refresher = MagicMock()
        proxy._refresher._attempt_refresh = AsyncMock(side_effect=Exception("browser closed"))
        request = _make_request()
        resp = _run_async(handle_session_refresh(proxy, request))
        assert resp.status == 500
        body = json.loads(resp.body)
        assert "error" in body


class TestHandleOldSw:
    def test_returns_service_worker(self):
        proxy = _make_proxy()
        request = _make_request()
        resp = _run_async(handle_old_sw(proxy, request))
        assert resp.status == 200
        assert "javascript" in resp.content_type
        body = resp.body.decode()
        assert "skipWaiting" in body
        assert "unregister" in body


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
