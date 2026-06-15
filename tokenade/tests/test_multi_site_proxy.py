"""Tests for multi-site proxy."""

import pytest
from tokenade.core.proxy.multi_site_proxy import MultiSiteProxy


class TestMultiSiteProxy:
    @pytest.fixture
    def sessions(self):
        return [
            {
                "version": "2.0",
                "site_name": "github",
                "auth_status": "logged_in",
                "cookies": [{"name": "session", "value": "abc", "domain": ".github.com", "path": "/"}],
                "fingerprint": {"user_agent": "Mozilla/5.0", "platform": "Linux"},
                "tls_profile": {"browser": "chrome", "version": "120"},
            },
            {
                "version": "2.0",
                "site_name": "gmail",
                "auth_status": "logged_in",
                "cookies": [{"name": "SID", "value": "xyz", "domain": ".google.com", "path": "/"}],
                "fingerprint": {"user_agent": "Mozilla/5.0", "platform": "Linux"},
                "tls_profile": {"browser": "chrome", "version": "120"},
            },
        ]

    def test_creation(self, sessions):
        proxy = MultiSiteProxy(sessions, base_port=9222, host="127.0.0.1")
        assert len(proxy.sessions) == 2
        assert proxy.base_port == 9222

    def test_default_values(self, sessions):
        proxy = MultiSiteProxy(sessions)
        assert proxy.base_port == 9222
        assert proxy.host == "127.0.0.1"

    def test_empty_sessions(self):
        proxy = MultiSiteProxy([])
        assert len(proxy.sessions) == 0

    def test_session_data_preserved(self, sessions):
        proxy = MultiSiteProxy(sessions)
        assert proxy.sessions[0]["site_name"] == "github"
        assert proxy.sessions[1]["site_name"] == "gmail"

    def test_app_not_created_until_start(self, sessions):
        proxy = MultiSiteProxy(sessions)
        assert proxy._app is None
        assert proxy._proxies == []
