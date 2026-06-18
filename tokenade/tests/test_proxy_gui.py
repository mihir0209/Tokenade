"""Tests for proxy GUI and page generation."""

import pytest
from tokenade.core.proxy.cdp_proxy import CDPProxy, CDPProxyConfig


class TestCDPProxyGUI:
    @pytest.fixture
    def session(self):
        return {
            "version": "2.0",
            "site_name": "test-site",
            "auth_status": "logged_in",
            "cookies": [
                {"name": "session", "value": "abc", "domain": ".example.com", "path": "/",
                 "secure": True, "httpOnly": True, "expires": 9999999999},
                {"name": "lang", "value": "en", "domain": ".example.com", "path": "/"},
            ],
            "fingerprint": {
                "user_agent": "Mozilla/5.0 Test",
                "platform": "Linux",
            },
            "tls_profile": {"browser": "chrome", "version": "120"},
            "source_device": {
                "browser": "firefox",
                "platform": "Linux",
                "hostname": "test-pc",
            },
        }

    def test_get_site_url_with_cookies(self, session):
        proxy = CDPProxy(session)
        url = proxy._get_site_url()
        assert "example.com" in url

    def test_get_site_url_no_cookies(self):
        session = {"site_name": "mysite", "cookies": [], "fingerprint": {}}
        proxy = CDPProxy(session)
        url = proxy._get_site_url()
        assert url == "https://www.mysite.com"

    def test_get_site_url_unknown(self):
        session = {"site_name": "unknown", "cookies": [], "fingerprint": {}}
        proxy = CDPProxy(session)
        url = proxy._get_site_url()
        assert url == "https://example.com"

    def test_cleanup_expired_pages(self, session):
        proxy = CDPProxy(session)
        # No pages to clean
        proxy._cleanup_expired_pages()
        assert len(proxy._pages) == 0

    def test_max_pages_limit(self, session):
        proxy = CDPProxy(session)
        assert proxy._max_pages == 20

    def test_page_ttl(self, session):
        proxy = CDPProxy(session)
        assert proxy._page_ttl == 3600

    def test_stats_default(self, session):
        proxy = CDPProxy(session)
        assert proxy.stats["requests"] == 0
        assert proxy.stats["bytes_sent"] == 0
        assert proxy.stats["bytes_received"] == 0

    def test_config_defaults(self):
        config = CDPProxyConfig()
        assert config.port == 9222
        assert config.headless is True
        assert config.timeout == 30
        assert config.use_fingerprint is False

    def test_config_custom(self):
        config = CDPProxyConfig(port=3000, headless=False, timeout=60, use_fingerprint=True)
        assert config.port == 3000
        assert config.headless is False
        assert config.timeout == 60
        assert config.use_fingerprint is True
