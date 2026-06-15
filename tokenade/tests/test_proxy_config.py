"""Tests for proxy configuration."""

import pytest
from tokenade.core.proxy.cdp_proxy import CDPProxyConfig, CDPProxy


class TestCDPProxyConfig:
    def test_default_config(self):
        config = CDPProxyConfig()
        assert config.port == 9222
        assert config.host == "127.0.0.1"
        assert config.headless is True
        assert config.verbose is False
        assert config.timeout == 30
        assert config.use_fingerprint is False

    def test_custom_config(self):
        config = CDPProxyConfig(port=8080, host="0.0.0.0", headless=False, timeout=60)
        assert config.port == 8080
        assert config.host == "0.0.0.0"
        assert config.headless is False
        assert config.timeout == 60

    def test_fingerprint_config(self):
        config = CDPProxyConfig(use_fingerprint=True)
        assert config.use_fingerprint is True


class TestCDPProxyCreation:
    @pytest.fixture
    def session(self):
        return {
            "version": "2.0",
            "site_name": "test",
            "auth_status": "logged_in",
            "cookies": [
                {"name": "session", "value": "abc", "domain": ".example.com", "path": "/",
                 "secure": True, "httpOnly": True, "expires": 9999999999},
            ],
            "fingerprint": {
                "user_agent": "Mozilla/5.0 Test",
                "platform": "Linux",
            },
            "tls_profile": {"browser": "chrome", "version": "120"},
        }

    def test_creation(self, session):
        proxy = CDPProxy(session)
        assert proxy.session == session
        assert proxy.config.port == 9222

    def test_cookie_jar_loaded(self, session):
        proxy = CDPProxy(session)
        assert len(proxy.cookie_jar.to_list()) == 1

    def test_stats_initialized(self, session):
        proxy = CDPProxy(session)
        assert proxy.stats["requests"] == 0
        assert proxy.stats["bytes_sent"] == 0
        assert proxy.stats["bytes_received"] == 0
        assert proxy.stats["errors"] == 0
        assert proxy.stats["start_time"] is None

    def test_pages_empty(self, session):
        proxy = CDPProxy(session)
        assert len(proxy._pages) == 0

    def test_max_pages(self, session):
        proxy = CDPProxy(session)
        assert proxy._max_pages == 20

    def test_page_ttl(self, session):
        proxy = CDPProxy(session)
        assert proxy._page_ttl == 3600

    def test_get_site_url(self, session):
        proxy = CDPProxy(session)
        url = proxy._get_site_url()
        assert url.startswith("https://")
        assert "example.com" in url

    def test_get_site_url_unknown(self):
        session = {"site_name": "unknown", "cookies": [], "fingerprint": {}}
        proxy = CDPProxy(session)
        url = proxy._get_site_url()
        assert url == "https://example.com"
