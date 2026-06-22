"""Tests for auto-refresh daemon (Phase 33)."""
import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch

from tokenade.core.daemon.session_daemon import (
    SessionDaemon, DaemonConfig, DaemonState, SessionEntry, RefreshResult,
)


def _make_daemon(tmp_path, sessions=None, **kwargs):
    """Create an isolated SessionDaemon with tmp config."""
    config = DaemonConfig(sessions=sessions or [], **kwargs)
    config_path = tmp_path / "daemon.json"
    config.save(config_path)
    with patch("tokenade.core.daemon.session_daemon.DAEMON_CONFIG_FILE", config_path):
        daemon = SessionDaemon(config)
        return daemon


# -- DaemonConfig Tests --

class TestDaemonConfig:

    def test_default_config(self):
        config = DaemonConfig()
        assert config.sessions == []
        assert config.check_interval_minutes == 30.0
        assert config.webhook_url is None
        assert config.headless is True
        assert config.enabled is True

    def test_to_dict(self):
        config = DaemonConfig(sessions=[SessionEntry(path="/test.tokenade", site_name="test")])
        data = config.to_dict()
        assert "sessions" in data
        assert data["sessions"][0]["path"] == "/test.tokenade"

    def test_from_dict(self):
        data = {
            "sessions": [{"path": "/test.tokenade", "site_name": "test"}],
            "check_interval_minutes": 15.0,
            "webhook_url": "https://hooks.example.com",
        }
        config = DaemonConfig.from_dict(data)
        assert len(config.sessions) == 1
        assert config.sessions[0].path == "/test.tokenade"
        assert config.check_interval_minutes == 15.0
        assert config.webhook_url == "https://hooks.example.com"

    def test_save_and_load(self, tmp_path):
        config_path = tmp_path / "daemon.json"
        config = DaemonConfig(
            sessions=[SessionEntry(path="/test.tokenade", site_name="test")],
            check_interval_minutes=10.0,
        )
        config.save(config_path)
        loaded = DaemonConfig.load(config_path)
        assert len(loaded.sessions) == 1
        assert loaded.sessions[0].path == "/test.tokenade"
        assert loaded.check_interval_minutes == 10.0

    def test_load_missing_file(self, tmp_path):
        config = DaemonConfig.load(tmp_path / "nonexistent.json")
        assert config.sessions == []

    def test_load_corrupt_file(self, tmp_path):
        config_path = tmp_path / "corrupt.json"
        config_path.write_text("not json {{{")
        config = DaemonConfig.load(config_path)
        assert config.sessions == []

    def test_roundtrip_complex(self, tmp_path):
        config_path = tmp_path / "daemon.json"
        config = DaemonConfig(
            sessions=[
                SessionEntry(path="/a.tokenade", site_name="a", browser="chrome", enabled=True),
                SessionEntry(path="/b.tokenade", site_name="b", browser="firefox", enabled=False),
            ],
            check_interval_minutes=5.0,
            max_concurrent_refreshes=3,
            webhook_url="https://hooks.example.com/test",
            headless=False,
            refresh_wait_seconds=15,
        )
        config.save(config_path)
        loaded = DaemonConfig.load(config_path)
        assert len(loaded.sessions) == 2
        assert loaded.sessions[0].browser == "chrome"
        assert loaded.sessions[1].enabled is False
        assert loaded.headless is False


# -- SessionEntry Tests --

class TestSessionEntry:

    def test_default_values(self):
        entry = SessionEntry(path="/test.tokenade")
        assert entry.path == "/test.tokenade"
        assert entry.browser == "chrome"
        assert entry.enabled is True
        assert entry.refresh_count == 0
        assert entry.added_at is not None

    def test_custom_values(self):
        entry = SessionEntry(
            path="/test.tokenade", site_name="github", browser="firefox",
            refresh_before_hours=4.0, target_url="https://github.com", enabled=False,
        )
        assert entry.site_name == "github"
        assert entry.browser == "firefox"
        assert entry.refresh_before_hours == 4.0
        assert entry.enabled is False


# -- RefreshResult Tests --

class TestRefreshResult:

    def test_success_result(self):
        result = RefreshResult(
            session_path="/test.tokenade", site_name="github",
            success=True, cookies_before=10, cookies_after=12, duration_seconds=5.3,
        )
        assert result.success is True
        assert result.cookies_before == 10
        assert result.cookies_after == 12
        assert result.timestamp is not None

    def test_failure_result(self):
        result = RefreshResult(
            session_path="/test.tokenade", site_name="github",
            success=False, error="Session file not found",
        )
        assert result.success is False
        assert result.error == "Session file not found"


# -- SessionDaemon Tests --

class TestSessionDaemon:

    def test_init_default(self):
        daemon = SessionDaemon(DaemonConfig())
        assert daemon.state == DaemonState.STOPPED
        assert daemon.config is not None

    def test_init_custom_config(self):
        config = DaemonConfig(sessions=[SessionEntry(path="/x.tokenade", site_name="x")])
        daemon = SessionDaemon(config)
        assert len(daemon.config.sessions) == 1

    def test_status_when_stopped(self):
        daemon = SessionDaemon(DaemonConfig())
        status = daemon.status()
        assert status["running"] is False
        assert status["pid"] is None

    def test_add_session(self, tmp_path):
        session_path = tmp_path / "test.tokenade"
        session_path.write_text("{}")
        daemon = _make_daemon(tmp_path)
        result = daemon.add_session(str(session_path), browser="chrome")
        assert result is True
        assert len(daemon.config.sessions) == 1
        assert daemon.config.sessions[0].site_name == "test"

    def test_add_session_not_found(self, tmp_path):
        daemon = _make_daemon(tmp_path)
        result = daemon.add_session(str(tmp_path / "missing.tokenade"))
        assert result is False

    def test_add_session_duplicate(self, tmp_path):
        session_path = tmp_path / "test.tokenade"
        session_path.write_text("{}")
        daemon = _make_daemon(tmp_path)
        daemon.add_session(str(session_path))
        result = daemon.add_session(str(session_path))
        assert result is False
        assert len(daemon.config.sessions) == 1

    def test_remove_session(self, tmp_path):
        session_path = tmp_path / "test.tokenade"
        session_path.write_text("{}")
        daemon = _make_daemon(tmp_path)
        daemon.add_session(str(session_path))
        result = daemon.remove_session(str(session_path))
        assert result is True
        assert len(daemon.config.sessions) == 0

    def test_remove_session_not_found(self, tmp_path):
        daemon = _make_daemon(tmp_path)
        result = daemon.remove_session(str(tmp_path / "missing.tokenade"))
        assert result is False

    def test_list_sessions_empty(self, tmp_path):
        daemon = _make_daemon(tmp_path)
        sessions = daemon.list_sessions()
        assert sessions == []

    def test_list_sessions(self, tmp_path):
        session_path = tmp_path / "test.tokenade"
        session_path.write_text("{}")
        daemon = _make_daemon(tmp_path)
        daemon.add_session(str(session_path), browser="firefox")
        sessions = daemon.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["site_name"] == "test"
        assert sessions[0]["browser"] == "firefox"
        assert sessions[0]["file_exists"] is True

    def test_run_once_no_sessions(self, tmp_path):
        daemon = _make_daemon(tmp_path)
        results = daemon.run_once()
        assert results == []

    def test_run_once_file_not_found(self, tmp_path):
        config = DaemonConfig(
            sessions=[SessionEntry(path=str(tmp_path / "missing.tokenade"), site_name="missing")]
        )
        daemon = SessionDaemon(config)
        results = daemon.run_once()
        assert len(results) == 1
        assert results[0].success is False
        assert "not found" in results[0].error.lower()

    def test_run_once_no_cookies(self, tmp_path):
        session_path = tmp_path / "empty.tokenade"
        session_path.write_text(json.dumps({"cookies": []}))
        config = DaemonConfig(
            sessions=[SessionEntry(path=str(session_path), site_name="empty")]
        )
        daemon = SessionDaemon(config)
        results = daemon.run_once()
        assert len(results) == 1
        assert results[0].success is False
        assert "no cookies" in results[0].error.lower()

    def test_stop_not_running(self):
        daemon = SessionDaemon(DaemonConfig())
        result = daemon.stop()
        assert result is True

    def test_stop_stale_pid(self, tmp_path):
        pid_file = tmp_path / "daemon.pid"
        pid_file.write_text("99999999")
        with patch("tokenade.core.daemon.session_daemon.DAEMON_PID_FILE", pid_file):
            daemon = SessionDaemon(DaemonConfig())
            result = daemon.stop()
            assert result is True

    def test_is_alive(self):
        assert SessionDaemon._is_alive(str(os.getpid())) is True
        assert SessionDaemon._is_alive("99999999") is False
        assert SessionDaemon._is_alive("not_a_number") is False

    def test_history_tracking(self, tmp_path):
        session_path = tmp_path / "test.tokenade"
        session_path.write_text(json.dumps({"cookies": []}))
        config = DaemonConfig(
            sessions=[SessionEntry(path=str(session_path), site_name="test")]
        )
        daemon = SessionDaemon(config)
        daemon.run_once()
        assert len(daemon._history) == 1

    def test_detect_url_from_cookies(self):
        daemon = SessionDaemon(DaemonConfig())
        cookies = [
            {"domain": ".github.com", "path": "/"},
            {"domain": "github.com", "path": "/"},
        ]
        url = daemon._detect_url_from_cookies(cookies)
        assert "github.com" in url

    def test_config_save_creates_dir(self, tmp_path):
        config_path = tmp_path / "subdir" / "daemon.json"
        config = DaemonConfig()
        config.save(config_path)
        assert config_path.exists()

    def test_get_history_empty(self):
        daemon = SessionDaemon(DaemonConfig())
        history = daemon.get_history()
        assert isinstance(history, list)

    def test_status_fields(self):
        daemon = SessionDaemon(DaemonConfig())
        status = daemon.status()
        required = ["running", "pid", "state", "config_file", "pid_file",
                     "sessions_watched", "sessions_enabled", "check_interval_minutes",
                     "webhook_configured", "history_count"]
        for key in required:
            assert key in status

    def test_add_session_with_url(self, tmp_path):
        session_path = tmp_path / "gh.tokenade"
        session_path.write_text("{}")
        daemon = _make_daemon(tmp_path)
        daemon.add_session(str(session_path), target_url="https://github.com")
        assert daemon.config.sessions[0].target_url == "https://github.com"

    def test_add_session_custom_refresh_before(self, tmp_path):
        session_path = tmp_path / "gh.tokenade"
        session_path.write_text("{}")
        daemon = _make_daemon(tmp_path)
        daemon.add_session(str(session_path), refresh_before_hours=6.0)
        assert daemon.config.sessions[0].refresh_before_hours == 6.0

    def test_disabled_session_skipped(self, tmp_path):
        session_path = tmp_path / "test.tokenade"
        session_path.write_text("{}")
        daemon = _make_daemon(tmp_path)
        daemon.add_session(str(session_path))
        daemon.config.sessions[0].enabled = False
        results = daemon.run_once()
        assert results == []

    def test_daemon_state_default(self):
        daemon = SessionDaemon(DaemonConfig())
        assert daemon.state == DaemonState.STOPPED

    def test_daemon_stop_event(self):
        daemon = SessionDaemon(DaemonConfig())
        assert not daemon._stop_event.is_set()

    def test_daemon_reload_event(self):
        daemon = SessionDaemon(DaemonConfig())
        assert not daemon._reload_event.is_set()

    def test_webhook_notification_no_url(self):
        config = DaemonConfig(webhook_url=None)
        daemon = SessionDaemon(config)
        result = RefreshResult(
            session_path="/test.tokenade", site_name="test",
            success=True, cookies_before=5, cookies_after=5,
        )
        daemon._send_webhook(result)

    def test_webhook_notification_with_url(self):
        config = DaemonConfig(webhook_url="https://hooks.example.com/test")
        daemon = SessionDaemon(config)
        result = RefreshResult(
            session_path="/test.tokenade", site_name="test",
            success=True, cookies_before=5, cookies_after=5,
        )
        with patch("urllib.request.urlopen") as mock_open:
            daemon._send_webhook(result)
            mock_open.assert_called_once()

    def test_list_sessions_file_missing(self, tmp_path):
        daemon = _make_daemon(tmp_path)
        daemon.config.sessions.append(
            SessionEntry(path=str(tmp_path / "missing.tokenade"), site_name="missing")
        )
        sessions = daemon.list_sessions()
        assert sessions[0]["file_exists"] is False

    def test_webhook_filter_success(self):
        config = DaemonConfig(
            webhook_url="https://hooks.example.com/test",
            webhook_on_success=False,
        )
        daemon = SessionDaemon(config)
        result = RefreshResult(
            session_path="/test.tokenade", site_name="test",
            success=True, cookies_before=5, cookies_after=5,
        )
        with patch.object(daemon, "_send_webhook") as mock_webhook:
            daemon._send_webhook_notifications([result])
            mock_webhook.assert_not_called()

    def test_webhook_filter_failure(self):
        config = DaemonConfig(
            webhook_url="https://hooks.example.com/test",
            webhook_on_failure=False,
        )
        daemon = SessionDaemon(config)
        result = RefreshResult(
            session_path="/test.tokenade", site_name="test",
            success=False, error="fail",
        )
        with patch.object(daemon, "_send_webhook") as mock_webhook:
            daemon._send_webhook_notifications([result])
            mock_webhook.assert_not_called()

    def test_daemon_state_refreshing(self):
        daemon = SessionDaemon(DaemonConfig())
        daemon.state = DaemonState.REFRESHING
        assert daemon.state == DaemonState.REFRESHING

    def test_daemon_state_error(self):
        daemon = SessionDaemon(DaemonConfig())
        daemon.state = DaemonState.ERROR
        assert daemon.state == DaemonState.ERROR

    def test_daemon_state_starting(self):
        daemon = SessionDaemon(DaemonConfig())
        daemon.state = DaemonState.STARTING
        assert daemon.state == DaemonState.STARTING

    def test_daemon_state_stopping(self):
        daemon = SessionDaemon(DaemonConfig())
        daemon.state = DaemonState.STOPPING
        assert daemon.state == DaemonState.STOPPING

    def test_daemon_state_running(self):
        daemon = SessionDaemon(DaemonConfig())
        daemon.state = DaemonState.RUNNING
        assert daemon.state == DaemonState.RUNNING

    def test_save_history(self, tmp_path):
        session_path = tmp_path / "test.tokenade"
        session_path.write_text(json.dumps({"cookies": []}))
        config = DaemonConfig(
            sessions=[SessionEntry(path=str(session_path), site_name="test")]
        )
        daemon = SessionDaemon(config)
        daemon.run_once()
        history_file = tmp_path / "history.json"
        with patch("tokenade.core.daemon.session_daemon.DAEMON_HISTORY_FILE", history_file):
            daemon._save_history()
            assert history_file.exists()
            data = json.loads(history_file.read_text())
            assert len(data) == 1
