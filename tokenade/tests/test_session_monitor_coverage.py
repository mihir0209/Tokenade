"""Tests for session monitor - coverage boost."""

import time
from unittest.mock import MagicMock

from tokenade.core.monitoring.session_monitor import (
    SessionMonitor,
    MonitorConfig,
    SessionStatus,
    CookieStatus,
)


class TestSessionMonitorCoverage:
    def test_set_refresh_callback(self):
        monitor = SessionMonitor()

        def cb(sid):
            return True

        monitor.set_refresh_callback(cb)
        assert monitor._refresh_callback is cb

    def test_start_already_running(self):
        monitor = SessionMonitor(MonitorConfig(check_interval=0.1))
        monitor.start()
        assert monitor._running is True
        monitor.start()  # Should not create a second thread
        assert monitor._running is True
        monitor.stop()

    def test_stop_without_thread(self):
        monitor = SessionMonitor()
        monitor._running = True
        monitor.stop()
        assert monitor._running is False

    def test_monitor_loop_exception(self):
        monitor = SessionMonitor(MonitorConfig(check_interval=0.01))
        call_count = [0]
        monitor._check_all_sessions

        def failing_check():
            call_count[0] += 1
            if call_count[0] >= 2:
                monitor._running = False
            raise RuntimeError("check failed")

        monitor._check_all_sessions = failing_check
        monitor._running = True
        monitor._monitor_loop()
        assert call_count[0] >= 2

    def test_check_all_sessions_callback(self):
        monitor = SessionMonitor()
        changes = []
        monitor.on_health_change(lambda sid, status: changes.append(sid))

        session = {
            "cookies": [
                {"name": "c1", "domain": ".x.com", "expires": time.time() + 3600, "secure": True, "httpOnly": True},
            ]
        }
        monitor.register_session("s1", session)
        # Force health score change by manually updating
        monitor.get_status("s1").health_score
        monitor.get_status("s1").health_score = 0.0
        monitor._check_all_sessions()
        assert "s1" in changes

    def test_check_all_sessions_auto_refresh(self):
        monitor = SessionMonitor(MonitorConfig(auto_refresh=True, auto_refresh_threshold=100))
        refresh_called = [False]

        def refresh_cb(sid):
            refresh_called[0] = True
            return True

        monitor.set_refresh_callback(refresh_cb)

        session = {
            "cookies": [
                {"name": "expired", "domain": ".x.com", "expires": time.time() - 100, "secure": True, "httpOnly": True},
            ]
        }
        monitor.register_session("s1", session)
        status = monitor.get_status("s1")
        status.health_score = 0.0
        monitor._check_all_sessions()
        assert refresh_called[0] is True

    def test_check_all_sessions_auto_refresh_failure(self):
        monitor = SessionMonitor(MonitorConfig(auto_refresh=True, auto_refresh_threshold=100))

        def fail_cb(sid):
            return False

        monitor.set_refresh_callback(fail_cb)

        session = {
            "cookies": [
                {"name": "expired", "domain": ".x.com", "expires": time.time() - 100, "secure": True, "httpOnly": True},
            ]
        }
        monitor.register_session("s1", session)
        status = monitor.get_status("s1")
        status.health_score = 0.0
        monitor._check_all_sessions()

    def test_check_all_sessions_refresh_exception(self):
        monitor = SessionMonitor(MonitorConfig(auto_refresh=True, auto_refresh_threshold=100))

        def exception_cb(sid):
            raise RuntimeError("refresh error")

        monitor.set_refresh_callback(exception_cb)

        session = {
            "cookies": [
                {"name": "expired", "domain": ".x.com", "expires": time.time() - 100, "secure": True, "httpOnly": True},
            ]
        }
        monitor.register_session("s1", session)
        status = monitor.get_status("s1")
        status.health_score = 0.0
        monitor._check_all_sessions()

    def test_check_all_sessions_callback_exception(self):
        monitor = SessionMonitor()

        def bad_callback(sid, status):
            raise RuntimeError("callback error")

        monitor.on_health_change(bad_callback)

        session = {
            "cookies": [
                {"name": "c1", "domain": ".x.com", "expires": time.time() + 3600, "secure": True, "httpOnly": True},
            ]
        }
        monitor.register_session("s1", session)
        status = monitor.get_status("s1")
        status.health_score = 0.0
        monitor._check_all_sessions()

    def test_analyze_cookies_session_cookie(self):
        monitor = SessionMonitor()
        session = {
            "cookies": [
                {"name": "session_only", "domain": ".x.com", "secure": True, "httpOnly": True},
            ]
        }
        monitor.register_session("s1", session)
        status = monitor.get_status("s1")
        assert status.healthy_cookies == 1

    def test_analyze_cookies_with_creation_time(self):
        monitor = SessionMonitor()
        now = time.time()
        session = {
            "cookies": [
                {"name": "c", "domain": ".x.com", "expires": now + 1800, "creation_time": now - 3600, "secure": True, "httpOnly": True},
            ]
        }
        monitor.register_session("s1", session)
        status = monitor.get_status("s1")
        assert status.cookie_count == 1

    def test_analyze_cookies_warning(self):
        monitor = SessionMonitor(MonitorConfig(warning_threshold=0.5))
        now = time.time()
        session = {
            "cookies": [
                {"name": "c", "domain": ".x.com", "expires": now + 100, "creation_time": now - 3600, "secure": True, "httpOnly": True},
            ]
        }
        monitor.register_session("s1", session)
        status = monitor.get_status("s1")
        assert status.warning_cookies == 1

    def test_recalculate_health_empty(self):
        monitor = SessionMonitor()
        status = SessionStatus(session_id="s1", site_name="test")
        monitor._recalculate_health(status)
        assert status.health_score == 0.0

    def test_recalculate_health_mixed(self):
        monitor = SessionMonitor()
        status = SessionStatus(
            session_id="s1", site_name="test",
            healthy_cookies=2, warning_cookies=1, expired_cookies=1,
        )
        status.cookies = [MagicMock()] * 4
        monitor._recalculate_health(status)
        # (2*1.0 + 1*0.5 + 1*0.0) / 4 * 100 = 62.5
        assert status.health_score == 62.5

    def test_update_status(self):
        monitor = SessionMonitor()
        status = SessionStatus(session_id="s1", site_name="test")
        status.cookies = [MagicMock()]
        status.healthy_cookies = 1
        status.warning_cookies = 0
        status.expired_cookies = 0
        old_check = status.last_check
        time.sleep(0.01)
        monitor._update_status(status)
        assert status.last_check > old_check

    def test_trigger_refresh_no_callback(self):
        monitor = SessionMonitor()
        status = SessionStatus(session_id="s1", site_name="test")
        monitor._trigger_refresh("s1", status)
        assert status.last_refresh is None

    def test_trigger_refresh_success(self):
        monitor = SessionMonitor()
        monitor.set_refresh_callback(lambda sid: True)
        status = SessionStatus(session_id="s1", site_name="test")
        monitor._trigger_refresh("s1", status)
        assert status.last_refresh is not None
        assert status.refresh_count == 1

    def test_trigger_refresh_failure(self):
        monitor = SessionMonitor()
        monitor.set_refresh_callback(lambda sid: False)
        status = SessionStatus(session_id="s1", site_name="test")
        monitor._trigger_refresh("s1", status)
        assert status.last_refresh is None
        assert status.refresh_count == 0

    def test_get_summary_with_sessions(self):
        monitor = SessionMonitor()
        session1 = {
            "cookies": [
                {"name": "c1", "domain": ".x.com", "expires": time.time() + 172800, "secure": True, "httpOnly": True},
            ]
        }
        session2 = {
            "cookies": [
                {"name": "c2", "domain": ".y.com", "expires": time.time() - 100, "secure": True, "httpOnly": True},
            ]
        }
        monitor.register_session("s1", session1, "site1")
        monitor.register_session("s2", session2, "site2")
        summary = monitor.get_summary()
        assert summary["total_sessions"] == 2
        assert summary["total_cookies"] == 2
        assert summary["healthy_cookies"] + summary["warning_cookies"] + summary["expired_cookies"] == 2
        assert len(summary["sessions"]) == 2
        assert summary["sessions"][0]["id"] in ("s1", "s2")


class TestMonitorConfig:
    def test_custom_config(self):
        config = MonitorConfig(
            check_interval=30.0,
            warning_threshold=0.3,
            auto_refresh=True,
            auto_refresh_threshold=0.1,
            source_browser="firefox",
        )
        assert config.check_interval == 30.0
        assert config.warning_threshold == 0.3
        assert config.auto_refresh is True
        assert config.auto_refresh_threshold == 0.1
        assert config.source_browser == "firefox"


class TestCookieStatus:
    def test_defaults(self):
        cs = CookieStatus(name="test", domain=".example.com")
        assert cs.health == "healthy"
        assert cs.is_secure is False
        assert cs.is_http_only is False
        assert cs.same_site == "None"

    def test_custom_values(self):
        cs = CookieStatus(
            name="sid", domain=".x.com", expires=1000.0,
            remaining_seconds=500.0, is_secure=True, is_http_only=True,
            same_site="Strict", health="warning",
        )
        assert cs.health == "warning"
        assert cs.is_secure is True


class TestSessionStatus:
    def test_defaults(self):
        ss = SessionStatus(session_id="s1", site_name="test")
        assert ss.cookie_count == 0
        assert ss.health_score == 0.0
        assert ss.refresh_count == 0
        assert ss.last_refresh is None
        assert ss.cookies == []
        assert ss.issues == []
        assert ss.recommendations == []
