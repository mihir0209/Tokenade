"""Tests for session monitoring."""

import time
import pytest
from tokenade.core.monitoring.session_monitor import (
    SessionMonitor,
    MonitorConfig,
    SessionStatus,
    CookieStatus,
)


class TestSessionMonitor:
    def test_register_session(self):
        monitor = SessionMonitor()
        session = {
            "cookies": [
                {"name": "sid", "domain": ".example.com", "expires": time.time() + 3600, "secure": True, "httpOnly": True},
                {"name": "track", "domain": ".example.com", "expires": time.time() + 86400, "secure": False, "httpOnly": False},
            ]
        }
        monitor.register_session("s1", session, "example.com")
        status = monitor.get_status("s1")
        assert status is not None
        assert status.site_name == "example.com"
        assert status.cookie_count == 2
        assert status.healthy_cookies + status.warning_cookies + status.expired_cookies == 2

    def test_unregister_session(self):
        monitor = SessionMonitor()
        monitor.register_session("s1", {"cookies": []})
        monitor.unregister_session("s1")
        assert monitor.get_status("s1") is None

    def test_get_all_statuses(self):
        monitor = SessionMonitor()
        monitor.register_session("s1", {"cookies": []}, "site1")
        monitor.register_session("s2", {"cookies": []}, "site2")
        statuses = monitor.get_all_statuses()
        assert len(statuses) == 2

    def test_health_score_expired_cookie(self):
        monitor = SessionMonitor()
        session = {
            "cookies": [
                {"name": "expired", "domain": ".example.com", "expires": time.time() - 100, "secure": True, "httpOnly": True},
            ]
        }
        monitor.register_session("s1", session)
        status = monitor.get_status("s1")
        assert status.expired_cookies == 1
        assert status.health_score < 100.0

    def test_health_score_missing_flags(self):
        monitor = SessionMonitor()
        session = {
            "cookies": [
                {"name": "insecure", "domain": ".example.com", "expires": time.time() + 3600, "secure": False, "httpOnly": False, "sameSite": "None"},
            ]
        }
        monitor.register_session("s1", session)
        status = monitor.get_status("s1")
        assert len(status.issues) > 0
        assert len(status.recommendations) > 0

    def test_summary(self):
        monitor = SessionMonitor()
        monitor.register_session("s1", {"cookies": [{"name": "a", "domain": ".x.com", "expires": time.time() + 3600, "secure": True, "httpOnly": True}]})
        summary = monitor.get_summary()
        assert summary["total_sessions"] == 1
        assert summary["total_cookies"] == 1

    def test_summary_empty(self):
        monitor = SessionMonitor()
        summary = monitor.get_summary()
        assert summary["total_sessions"] == 0

    def test_health_callback(self):
        monitor = SessionMonitor()
        changes = []
        monitor.on_health_change(lambda sid, status: changes.append((sid, status.health_score)))
        # Callbacks are called during _check_all_sessions, just verify registration works
        assert len(monitor._callbacks) == 1

    def test_config_defaults(self):
        config = MonitorConfig()
        assert config.check_interval == 60.0
        assert config.auto_refresh is False

    def test_start_stop(self):
        monitor = SessionMonitor(MonitorConfig(check_interval=0.1))
        monitor.start()
        assert monitor._running is True
        monitor.stop()
        assert monitor._running is False
