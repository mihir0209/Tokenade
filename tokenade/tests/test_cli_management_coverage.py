"""Tests targeting uncovered lines in cli/management.py.

Uncovered lines:
  22        - filter_sessions with site/browser in cmd_sessions list
  61-62     - file not found during rotate in cmd_sessions
  75-76     - file not found during stats in cmd_sessions
  132       - unhealthy session counter in cmd_health
  160       - site_config list case in cmd_refresh
  181-183   - exception during refresh in cmd_refresh
  213       - max_uses display in cmd_share
  215       - password protected display in cmd_share
  222-226   - html format share in cmd_share
  317       - error in sync status in cmd_sync
  320-336   - sync once and start commands
"""

import json
from unittest.mock import patch, MagicMock
from argparse import Namespace

from tokenade.cli.management import (
    cmd_sessions,
    cmd_health,
    cmd_refresh,
    cmd_share,
    cmd_sync,
)


def _make_session_file(tmp_path, name="test", cookies=None):
    if cookies is None:
        cookies = [{"name": "sid", "value": "abc", "domain": ".github.com"}]
    f = tmp_path / f"{name}.tokenade"
    f.write_text(json.dumps({
        "cookies": cookies,
        "site_name": name,
        "auth_status": "logged_in",
    }))
    return f


# ---------------------------------------------------------------------------
# cmd_sessions list with site/browser filter (line 22)
# ---------------------------------------------------------------------------

class TestCmdSessionsFilter:
    @patch("tokenade.core.importer.session_manager.SessionManager")
    def test_list_filter_by_site(self, mock_mgr_cls, tmp_path, capsys):
        """Line 22: sessions filtered by site name."""
        mock_mgr = MagicMock()
        mock_session = MagicMock()
        mock_session.site_name = "github"
        mock_session.cookie_count = 5
        mock_session.source_browser = "firefox"
        mock_session.file_size = 1024
        mock_session.path = "/tmp/test.tokenade"
        mock_mgr.list_sessions.return_value = [mock_session]
        mock_mgr.filter_sessions.return_value = [mock_session]
        mock_mgr_cls.return_value = mock_mgr

        args = Namespace(
            sessions_command="list",
            dir=str(tmp_path),
            pattern="*.tokenade",
            recursive=False,
            site="github",
            browser=None,
        )
        cmd_sessions(args)
        mock_mgr.filter_sessions.assert_called_once()
        assert "github" in capsys.readouterr().out

    @patch("tokenade.core.importer.session_manager.SessionManager")
    def test_list_filter_by_browser(self, mock_mgr_cls, tmp_path, capsys):
        """Line 22: sessions filtered by browser."""
        mock_mgr = MagicMock()
        mock_session = MagicMock()
        mock_session.site_name = "github"
        mock_session.cookie_count = 5
        mock_session.source_browser = "chrome"
        mock_session.file_size = 1024
        mock_session.path = "/tmp/test.tokenade"
        mock_mgr.list_sessions.return_value = [mock_session]
        mock_mgr.filter_sessions.return_value = [mock_session]
        mock_mgr_cls.return_value = mock_mgr

        args = Namespace(
            sessions_command="list",
            dir=str(tmp_path),
            pattern="*.tokenade",
            recursive=False,
            site=None,
            browser="chrome",
        )
        cmd_sessions(args)
        mock_mgr.filter_sessions.assert_called_once()

    @patch("tokenade.core.importer.session_manager.SessionManager")
    def test_list_large_file_size_display(self, mock_mgr_cls, tmp_path, capsys):
        """Line 37: file size display for large files (>1MB)."""
        mock_mgr = MagicMock()
        mock_session = MagicMock()
        mock_session.site_name = "big"
        mock_session.cookie_count = 100
        mock_session.source_browser = "firefox"
        mock_session.file_size = 2 * 1024 * 1024  # 2MB
        mock_session.path = "/tmp/big.tokenade"
        mock_mgr.list_sessions.return_value = [mock_session]
        mock_mgr_cls.return_value = mock_mgr

        args = Namespace(
            sessions_command="list",
            dir=str(tmp_path),
            pattern="*.tokenade",
            recursive=False,
            site=None,
            browser=None,
        )
        cmd_sessions(args)
        assert "M" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# cmd_sessions rotate missing file (lines 61-62)
# ---------------------------------------------------------------------------

class TestCmdSessionsRotate:
    @patch("tokenade.core.importer.session_manager.SessionManager")
    def test_rotate_missing_file(self, mock_mgr_cls, capsys):
        """Lines 61-62: file not found during rotate."""
        mock_mgr_cls.return_value = MagicMock()
        args = Namespace(
            sessions_command="rotate",
            files=["/nonexistent/file.tokenade"],
            strategy="round_robin",
            state_file=None,
            dir=".",
        )
        cmd_sessions(args)
        assert "not found" in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# cmd_sessions stats missing file (lines 75-76)
# ---------------------------------------------------------------------------

class TestCmdSessionsStats:
    @patch("tokenade.core.importer.session_manager.SessionManager")
    def test_stats_missing_file(self, mock_mgr_cls, capsys):
        """Lines 75-76: file not found during stats."""
        mock_mgr_cls.return_value = MagicMock()
        args = Namespace(
            sessions_command="stats",
            files=["/nonexistent/file.tokenade"],
            dir=".",
        )
        cmd_sessions(args)
        assert "not found" in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# cmd_health unhealthy counter (line 132)
# ---------------------------------------------------------------------------

class TestCmdHealthUnhealthy:
    @patch("tokenade.core.refresh.health_checker.SessionHealthChecker")
    @patch("tokenade.core.refresh.health_checker.generate_health_report")
    def test_unhealthy_session_counter(self, mock_report, mock_checker_cls, tmp_path, capsys):
        """Line 132: unhealthy session counter incremented."""
        f = _make_session_file(tmp_path, "bad")
        mock_checker = MagicMock()
        mock_health = MagicMock()
        mock_health.healthy = False
        mock_checker.check_session.return_value = mock_health
        mock_checker_cls.return_value = mock_checker
        mock_report.return_value = "UNHEALTHY session"

        args = Namespace(session=str(f), sessions_dir=None)
        cmd_health(args)
        output = capsys.readouterr().out
        assert "1 unhealthy" in output


# ---------------------------------------------------------------------------
# cmd_refresh site_config list case (line 160) and exception (lines 181-183)
# ---------------------------------------------------------------------------

class TestCmdRefreshSiteConfig:
    @patch("tokenade.core.refresh.health_checker.SessionRefresher")
    def test_site_config_list_case(self, mock_refresher_cls, tmp_path, capsys):
        """Line 160: site_config loaded as list, first element used."""
        f = _make_session_file(tmp_path, "session")
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps([
            {"domains": ["github.com"]},
            {"domains": ["other.com"]},
        ]))
        mock_refresher = MagicMock()
        mock_result = MagicMock(success=True, cookies_refreshed=3, cookies_total=5)
        mock_refresher.refresh.return_value = mock_result
        mock_refresher_cls.return_value = mock_refresher

        args = Namespace(
            session=str(f),
            source_browser="chrome",
            source_browser_path=None,
            source_profile=None,
            site_config=str(config_file),
        )
        cmd_refresh(args)
        assert "successful" in capsys.readouterr().out.lower()

    @patch("tokenade.core.refresh.health_checker.SessionRefresher")
    def test_site_config_empty_list(self, mock_refresher_cls, tmp_path, capsys):
        """Line 160: empty list → site_config becomes None."""
        f = _make_session_file(tmp_path, "session")
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps([]))
        mock_refresher = MagicMock()
        mock_result = MagicMock(success=True, cookies_refreshed=0, cookies_total=0)
        mock_refresher.refresh.return_value = mock_result
        mock_refresher_cls.return_value = mock_refresher

        args = Namespace(
            session=str(f),
            source_browser="chrome",
            source_browser_path=None,
            source_profile=None,
            site_config=str(config_file),
        )
        cmd_refresh(args)
        call_kwargs = mock_refresher.refresh.call_args[1]
        assert call_kwargs["site_config"] is None

    @patch("tokenade.core.refresh.health_checker.SessionRefresher")
    def test_refresh_exception(self, mock_refresher_cls, tmp_path, capsys):
        """Lines 181-183: exception during refresh."""
        f = _make_session_file(tmp_path, "session")
        mock_refresher = MagicMock()
        mock_refresher.refresh.side_effect = RuntimeError("refresh broke")
        mock_refresher_cls.return_value = mock_refresher

        args = Namespace(
            session=str(f),
            source_browser="chrome",
            source_browser_path=None,
            source_profile=None,
            site_config=None,
        )
        cmd_refresh(args)
        assert "failed" in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# cmd_share with max_uses (line 213), password (line 215), html format (222-226)
# ---------------------------------------------------------------------------

class TestCmdShareOptions:
    @patch("tokenade.core.importer.session_sharer.SessionSharer")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_max_uses_display(self, mock_packager_cls, mock_sharer_cls, tmp_path, capsys):
        """Line 213: max_uses displayed when set."""
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": []}
        mock_packager_cls.return_value = mock_packager
        mock_sharer = MagicMock()
        mock_sharer.create_share_link.return_value = ("http://link", "id1")
        mock_sharer_cls.return_value = mock_sharer

        args = Namespace(
            session=str(f),
            expiry=24,
            max_uses=10,
            password=None,
            format="url",
            output=None,
        )
        cmd_share(args)
        assert "10" in capsys.readouterr().out

    @patch("tokenade.core.importer.session_sharer.SessionSharer")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_password_protected_display(self, mock_packager_cls, mock_sharer_cls, tmp_path, capsys):
        """Line 215: password protected displayed when set."""
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": []}
        mock_packager_cls.return_value = mock_packager
        mock_sharer = MagicMock()
        mock_sharer.create_share_link.return_value = ("http://link", "id1")
        mock_sharer_cls.return_value = mock_sharer

        args = Namespace(
            session=str(f),
            expiry=24,
            max_uses=None,
            password="secret",
            format="url",
            output=None,
        )
        cmd_share(args)
        assert "password" in capsys.readouterr().out.lower()

    @patch("tokenade.core.importer.session_sharer.generate_share_html")
    @patch("tokenade.core.importer.session_sharer.SessionSharer")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_html_format(self, mock_packager_cls, mock_sharer_cls, mock_html, tmp_path, capsys):
        """Lines 222-226: html format share."""
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": []}
        mock_packager_cls.return_value = mock_packager
        mock_sharer = MagicMock()
        mock_sharer.create_share_link.return_value = ("http://link", "session123")
        mock_sharer_cls.return_value = mock_sharer

        args = Namespace(
            session=str(f),
            expiry=24,
            max_uses=None,
            password=None,
            format="html",
            output=None,
        )
        cmd_share(args)
        output = capsys.readouterr().out
        assert "session123" in output
        mock_html.assert_called_once()


# ---------------------------------------------------------------------------
# cmd_sync (lines 317, 320-336)
# ---------------------------------------------------------------------------

class TestCmdSync:
    @patch("tokenade.core.importer.session_sync.SessionSyncDaemon")
    def test_list_with_error(self, mock_daemon_cls, capsys):
        """Line 317: error displayed in sync status."""
        mock_daemon = MagicMock()
        mock_daemon.get_status.return_value = [{
            "name": "target1",
            "browser": "firefox",
            "domains": ["a.com"],
            "last_sync": None,
            "last_cookie_count": 0,
            "sync_count": 0,
            "error": "Connection failed",
        }]
        mock_daemon_cls.load_config.return_value = mock_daemon
        mock_daemon_cls.return_value = mock_daemon

        args = Namespace(
            sync_command="list",
            name=None, domains=None, browser=None,
            profile=None, output_dir=None,
            interval=None,
        )
        cmd_sync(args)
        assert "Connection failed" in capsys.readouterr().out

    @patch("tokenade.core.importer.session_sync.SessionSyncDaemon")
    def test_once(self, mock_daemon_cls, capsys):
        """Lines 320-325: sync once command."""
        mock_daemon = MagicMock()
        mock_daemon.check_once.return_value = {
            "target1": True,
            "target2": False,
        }
        mock_daemon_cls.load_config.return_value = mock_daemon
        mock_daemon_cls.return_value = mock_daemon

        args = Namespace(
            sync_command="once",
            name=None, domains=None, browser=None,
            profile=None, output_dir=None,
            interval=None,
        )
        cmd_sync(args)
        output = capsys.readouterr().out
        assert "synced" in output.lower() or "unchanged" in output.lower()

    @patch("tokenade.core.importer.session_sync.SessionSyncDaemon")
    def test_start_and_stop(self, mock_daemon_cls, capsys):
        """Lines 327-336: start daemon then stop via KeyboardInterrupt."""
        mock_daemon = MagicMock()
        mock_daemon._targets = ["t1"]
        mock_daemon.start.side_effect = KeyboardInterrupt()
        mock_daemon_cls.load_config.return_value = mock_daemon
        mock_daemon_cls.return_value = mock_daemon

        args = Namespace(
            sync_command="start",
            name=None, domains=None, browser=None,
            profile=None, output_dir=None,
            interval=30,
        )
        cmd_sync(args)
        mock_daemon.start.assert_called_once_with(interval=30)
        mock_daemon.stop.assert_called_once()
        assert "stopped" in capsys.readouterr().out.lower()

    @patch("tokenade.core.importer.session_sync.SessionSyncDaemon")
    def test_start_default_interval(self, mock_daemon_cls, capsys):
        """Lines 328-329: default interval when not specified."""
        mock_daemon = MagicMock()
        mock_daemon._targets = []
        mock_daemon.start.side_effect = KeyboardInterrupt()
        mock_daemon_cls.load_config.return_value = mock_daemon
        mock_daemon_cls.return_value = mock_daemon

        args = Namespace(
            sync_command="start",
            name=None, domains=None, browser=None,
            profile=None, output_dir=None,
            interval=None,
        )
        cmd_sync(args)
        mock_daemon.start.assert_called_once_with(interval=60)
