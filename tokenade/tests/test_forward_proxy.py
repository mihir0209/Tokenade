"""Tests for forward proxy."""

import pytest
from tokenade.core.proxy.forward_proxy import ForwardProxy


class TestForwardProxy:
    @pytest.fixture
    def session(self):
        return {
            "version": "2.0",
            "site_name": "test",
            "auth_status": "logged_in",
            "cookies": [
                {"name": "session", "value": "abc", "domain": ".example.com", "path": "/"},
            ],
            "fingerprint": {
                "user_agent": "Mozilla/5.0 TestAgent",
                "platform": "Linux",
            },
            "tls_profile": {"browser": "chrome", "version": "120"},
        }

    def test_creation(self, session):
        proxy = ForwardProxy(session, port=9999, host="127.0.0.1")
        assert proxy.port == 9999
        assert proxy.host == "127.0.0.1"
        assert proxy.session == session

    def test_stats_initialized(self, session):
        proxy = ForwardProxy(session)
        assert proxy.stats["requests"] == 0
        assert proxy.stats["bytes_sent"] == 0
        assert proxy.stats["bytes_received"] == 0
        assert proxy.stats["errors"] == 0

    def test_default_port(self, session):
        proxy = ForwardProxy(session)
        assert proxy.port == 9223

    def test_default_host(self, session):
        proxy = ForwardProxy(session)
        assert proxy.host == "127.0.0.1"

    def test_cookie_jar_loaded(self, session):
        proxy = ForwardProxy(session)
        assert proxy._cookie_jar is None  # Not initialized until start()

    def test_session_stored(self, session):
        proxy = ForwardProxy(session)
        assert proxy.session["site_name"] == "test"
        assert len(proxy.session["cookies"]) == 1
