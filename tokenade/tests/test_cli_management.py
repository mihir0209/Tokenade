"""Tests for CLI management commands."""

import json
from unittest.mock import patch, MagicMock
from argparse import Namespace

from tokenade.cli.management import cmd_sessions, cmd_health, cmd_refresh, cmd_share, cmd_unshare


def _make_session_file(tmp_path, name="test", cookies=None, auth_status="logged_in"):
    if cookies is None:
        cookies = [{"name": "sid", "value": "abc", "domain": ".github.com"}]
    f = tmp_path / f"{name}.tokenade"
    f.write_text(json.dumps({
        "cookies": cookies, "site_name": name, "auth_status": auth_status,
    }))
    return f


class TestCmdSessions:
    def test_list_no_sessions(self, tmp_path, capsys):
        args = Namespace(sessions_command="list", dir=str(tmp_path), pattern="*.tokenade",
                         recursive=False, site=None, browser=None)
        cmd_sessions(args)
        assert "No sessions found" in capsys.readouterr().out

    def test_list_with_sessions(self, tmp_path, capsys):
        _make_session_file(tmp_path, "github")
        args = Namespace(sessions_command="list", dir=str(tmp_path), pattern="*.tokenade",
                         recursive=False, site=None, browser=None)
        cmd_sessions(args)
        assert "github" in capsys.readouterr().out

    def test_list_unknown_command(self, capsys):
        args = Namespace(sessions_command="unknown")
        cmd_sessions(args)
        output = capsys.readouterr().out
        assert "subcommand" in output.lower() or "unknown" in output.lower()

    @patch("tokenade.core.importer.session_manager.SessionManager")
    def test_merge(self, mock_mgr_cls, tmp_path, capsys):
        f1 = _make_session_file(tmp_path, "a")
        f2 = _make_session_file(tmp_path, "b")
        mock_mgr = MagicMock()
        mock_mgr.merge_sessions.return_value = str(tmp_path / "merged.tokenade")
        mock_mgr_cls.return_value = mock_mgr
        args = Namespace(sessions_command="merge", files=[str(f1), str(f2)],
                         output=str(tmp_path / "merged"), site_name="test", dir=str(tmp_path))
        cmd_sessions(args)
        assert "Merged" in capsys.readouterr().out

    @patch("tokenade.core.importer.session_manager.SessionManager")
    def test_merge_missing_file(self, mock_mgr_cls, tmp_path, capsys):
        mock_mgr_cls.return_value = MagicMock()
        args = Namespace(sessions_command="merge", files=["/nonexistent/file"],
                         output=str(tmp_path / "merged"), site_name="test", dir=str(tmp_path))
        cmd_sessions(args)
        assert "not found" in capsys.readouterr().out.lower()

    @patch("tokenade.core.importer.session_manager.SessionManager")
    def test_rotate(self, mock_mgr_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "a")
        mock_mgr = MagicMock()
        mock_mgr.rotate_session.return_value = str(f)
        mock_mgr_cls.return_value = mock_mgr
        args = Namespace(sessions_command="rotate", files=[str(f)], strategy="round_robin",
                         state_file=None, dir=str(tmp_path))
        cmd_sessions(args)
        assert "Selected" in capsys.readouterr().out

    @patch("tokenade.core.importer.session_manager.SessionManager")
    def test_stats(self, mock_mgr_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "a")
        mock_mgr = MagicMock()
        mock_mgr.get_session_stats.return_value = {
            "session_count": 1, "total_cookies": 5, "total_size_bytes": 1024,
            "unique_sites": ["github"], "unique_browsers": ["chrome"],
        }
        mock_mgr_cls.return_value = mock_mgr
        args = Namespace(sessions_command="stats", files=[str(f)], dir=str(tmp_path))
        cmd_sessions(args)
        assert "Statistics" in capsys.readouterr().out


class TestCmdHealth:
    def test_health_no_sessions_dir(self, capsys):
        args = Namespace(session=None, sessions_dir="/nonexistent/dir")
        cmd_health(args)
        assert "Directory not found" in capsys.readouterr().out

    def test_health_no_files(self, tmp_path, capsys):
        args = Namespace(session=None, sessions_dir=str(tmp_path))
        cmd_health(args)
        assert "No session files found" in capsys.readouterr().out

    def test_health_single_file(self, tmp_path, capsys):
        f = _make_session_file(tmp_path, "healthy")
        args = Namespace(session=str(f), sessions_dir=None)
        cmd_health(args)
        output = capsys.readouterr().out
        assert "HEALTHY" in output or "health" in output.lower()

    def test_health_from_dir(self, tmp_path, capsys):
        _make_session_file(tmp_path, "s1")
        args = Namespace(session=None, sessions_dir=str(tmp_path))
        cmd_health(args)
        assert "SUMMARY" in capsys.readouterr().out


class TestCmdRefresh:
    def test_refresh_session_not_found(self, capsys):
        args = Namespace(session="/nonexistent/tokenade", source_browser="chrome",
                         source_browser_path=None, source_profile=None, site_config=None)
        cmd_refresh(args)
        assert "not found" in capsys.readouterr().out.lower()

    @patch("tokenade.core.refresh.health_checker.SessionRefresher")
    def test_refresh_success(self, mock_refresher_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_refresher = MagicMock()
        mock_result = MagicMock(success=True, cookies_refreshed=5, cookies_total=10)
        mock_refresher.refresh.return_value = mock_result
        mock_refresher_cls.return_value = mock_refresher
        args = Namespace(session=str(f), source_browser="chrome",
                         source_browser_path=None, source_profile=None, site_config=None)
        cmd_refresh(args)
        assert "successful" in capsys.readouterr().out.lower()

    @patch("tokenade.core.refresh.health_checker.SessionRefresher")
    def test_refresh_failure(self, mock_refresher_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_refresher = MagicMock()
        mock_result = MagicMock(success=False, error="No profile found")
        mock_refresher.refresh.return_value = mock_result
        mock_refresher_cls.return_value = mock_refresher
        args = Namespace(session=str(f), source_browser="chrome",
                         source_browser_path=None, source_profile=None, site_config=None)
        cmd_refresh(args)
        assert "failed" in capsys.readouterr().out.lower()

    @patch("tokenade.core.refresh.health_checker.SessionRefresher")
    def test_refresh_with_site_config(self, mock_refresher_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"domains": ["github.com"]}))
        mock_refresher = MagicMock()
        mock_result = MagicMock(success=True, cookies_refreshed=3, cookies_total=5)
        mock_refresher.refresh.return_value = mock_result
        mock_refresher_cls.return_value = mock_refresher
        args = Namespace(session=str(f), source_browser="chrome",
                         source_browser_path=None, source_profile=None, site_config=str(config_file))
        cmd_refresh(args)
        assert "successful" in capsys.readouterr().out.lower()


class TestCmdShare:
    def test_share_session_not_found(self, capsys):
        args = Namespace(session="/nonexistent/tokenade", expiry=24, max_uses=None,
                         password=None, format="url", output=None)
        cmd_share(args)
        assert "not found" in capsys.readouterr().out.lower()

    @patch("tokenade.core.importer.session_sharer.SessionSharer")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_share_url_format(self, mock_packager_cls, mock_sharer_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": []}
        mock_packager_cls.return_value = mock_packager
        mock_sharer = MagicMock()
        mock_sharer.create_share_link.return_value = ("http://share.link/abc", "abc123")
        mock_sharer_cls.return_value = mock_sharer
        args = Namespace(session=str(f), expiry=24, max_uses=None,
                         password=None, format="url", output=None)
        cmd_share(args)
        output = capsys.readouterr().out
        assert "share" in output.lower() or "🔗" in output

    @patch("tokenade.core.importer.session_sharer.SessionSharer")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_share_qr_format(self, mock_packager_cls, mock_sharer_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": []}
        mock_packager_cls.return_value = mock_packager
        mock_sharer_cls.return_value = MagicMock()
        args = Namespace(session=str(f), expiry=24, max_uses=None,
                         password=None, format="qr", output=None)
        cmd_share(args)


class TestCmdUnshare:
    @patch("tokenade.core.importer.session_sharer.SessionSharer")
    def test_list_no_shares(self, mock_sharer_cls, capsys):
        mock_sharer = MagicMock()
        mock_sharer.list_shared.return_value = []
        mock_sharer_cls.return_value = mock_sharer
        args = Namespace(list=True, session_id=None)
        cmd_unshare(args)
        assert "No active" in capsys.readouterr().out

    @patch("tokenade.core.importer.session_sharer.SessionSharer")
    def test_list_with_shares(self, mock_sharer_cls, capsys):
        mock_sharer = MagicMock()
        mock_sharer.list_shared.return_value = [{
            "session_id": "abc", "created_at": 1700000000,
            "expires_at": 1700086400, "use_count": 3,
            "max_uses": 10, "has_password": True,
        }]
        mock_sharer_cls.return_value = mock_sharer
        args = Namespace(list=True, session_id=None)
        cmd_unshare(args)
        assert "abc" in capsys.readouterr().out

    @patch("tokenade.core.importer.session_sharer.SessionSharer")
    def test_revoke_success(self, mock_sharer_cls, capsys):
        mock_sharer = MagicMock()
        mock_sharer.revoke_share.return_value = True
        mock_sharer_cls.return_value = mock_sharer
        args = Namespace(list=False, session_id="abc")
        cmd_unshare(args)
        assert "Revoked" in capsys.readouterr().out

    @patch("tokenade.core.importer.session_sharer.SessionSharer")
    def test_revoke_failure(self, mock_sharer_cls, capsys):
        mock_sharer = MagicMock()
        mock_sharer.revoke_share.return_value = False
        mock_sharer_cls.return_value = mock_sharer
        args = Namespace(list=False, session_id="abc")
        cmd_unshare(args)
        assert "Failed" in capsys.readouterr().out
