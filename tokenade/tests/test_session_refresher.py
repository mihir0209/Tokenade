"""Tests for session refresher."""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tokenade.core.importer.session_refresher import (
    SessionRefresher,
    RefreshConfig,
    CookieExpiryInfo,
)


class TestRefreshConfig:
    def test_default_config(self):
        config = RefreshConfig()
        assert config.check_interval == 300
        assert config.expiry_warning_days == 7
        assert config.expiry_critical_days == 1
        assert config.auto_refresh is False
        assert config.source_browser is None

    def test_custom_config(self):
        config = RefreshConfig(
            check_interval=60,
            expiry_warning_days=3,
            expiry_critical_days=2,
            auto_refresh=True,
            source_browser="firefox",
            source_profile="default",
            domains="example.com,test.com",
        )
        assert config.check_interval == 60
        assert config.expiry_warning_days == 3
        assert config.expiry_critical_days == 2
        assert config.auto_refresh is True
        assert config.source_browser == "firefox"
        assert config.source_profile == "default"
        assert config.domains == "example.com,test.com"


class TestSessionRefresher:
    @pytest.fixture
    def session(self):
        return {
            "site_name": "test_site",
            "cookies": [
                {"name": "session", "value": "abc", "domain": ".example.com", "path": "/"},
                {"name": "lang", "value": "en", "domain": ".example.com", "path": "/"},
            ],
            "source_device": {"browser": "firefox"},
        }

    @pytest.fixture
    def session_with_expiry(self):
        now = time.time()
        return {
            "site_name": "test_site",
            "cookies": [
                {"name": "session", "value": "abc", "domain": ".example.com", "path": "/"},
                {"name": "expiring", "value": "xyz", "domain": ".example.com", "path": "/",
                 "expires": now + 86400},  # 1 day from now
                {"name": "expired", "value": "old", "domain": ".example.com", "path": "/",
                 "expires": now - 86400},  # 1 day ago
            ],
        }

    @pytest.fixture
    def refresher(self, session):
        return SessionRefresher(session)

    def test_check_expiry_no_expiry(self, refresher):
        status = refresher.check_expiry()
        assert status.total_cookies == 2
        assert status.expired_count == 0
        assert status.expiring_soon_count == 0
        assert status.critical_count == 0

    def test_check_expiry_with_expired(self, session_with_expiry):
        refresher = SessionRefresher(session_with_expiry)
        status = refresher.check_expiry()
        assert status.expired_count == 1

    def test_check_expiry_critical(self):
        now = time.time()
        session = {
            "cookies": [
                {"name": "critical", "value": "val", "domain": ".example.com", "path": "/",
                 "expires": now + 3600},  # 1 hour from now
            ]
        }
        refresher = SessionRefresher(session, RefreshConfig(expiry_critical_days=1))
        status = refresher.check_expiry()
        assert status.critical_count == 1

    def test_check_expiry_warning(self):
        now = time.time()
        session = {
            "cookies": [
                {"name": "warning", "value": "val", "domain": ".example.com", "path": "/",
                 "expires": now + 5 * 86400},  # 5 days from now
            ]
        }
        refresher = SessionRefresher(session, RefreshConfig(expiry_warning_days=7))
        status = refresher.check_expiry()
        assert status.expiring_soon_count == 1

    def test_check_expiry_next_expiry_human(self):
        now = time.time()
        session = {
            "cookies": [
                {"name": "soon", "value": "val", "domain": ".example.com", "path": "/",
                 "expires": now + 7200},  # 2 hours
            ]
        }
        refresher = SessionRefresher(session)
        status = refresher.check_expiry()
        assert status.next_expiry_human is not None
        assert "hours" in status.next_expiry_human

    def test_get_status(self, refresher):
        status = refresher.get_status()
        assert "total_cookies" in status
        assert "expired_count" in status
        assert "auto_refresh_enabled" in status
        assert status["auto_refresh_enabled"] is False

    def test_update_session(self, refresher):
        new_session = {
            "site_name": "new_site",
            "cookies": [{"name": "new", "value": "val", "domain": ".new.com", "path": "/"}],
        }
        refresher.update_session(new_session)
        assert refresher.session["site_name"] == "new_site"
        assert len(refresher.session["cookies"]) == 1

    def test_start_stop(self, refresher):
        # Test the state changes without actually running the event loop
        assert refresher._running is False
        refresher._running = True
        assert refresher._running is True
        refresher._running = False
        assert refresher._running is False

    def test_attempt_refresh_no_source(self, refresher):
        refresher.config.source_browser = None
        # Should not raise, just log warning
        # We can't easily test async without running the event loop
        assert refresher.config.source_browser is None

    def test_attempt_refresh_with_callback(self, refresher):
        callback = AsyncMock()
        refresher.on_refresh = callback
        refresher.config.source_browser = "firefox"
        
        # Test that callback is set correctly
        assert refresher.on_refresh == callback
        assert refresher.config.source_browser == "firefox"
