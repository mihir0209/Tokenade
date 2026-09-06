"""Tests for session_sync module — Session Sync Daemon."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import asdict
from argparse import Namespace

from tokenade.core.importer.session_sync import (
    SyncTarget,
    SyncStatus,
    SessionSyncDaemon,
)


# ─── SyncTarget ───────────────────────────────────────────────────────────────

class TestSyncTarget:
    def test_create_defaults(self):
        t = SyncTarget(name="gmail", domains=["google.com"])
        assert t.name == "gmail"
        assert t.domains == ["google.com"]
        assert t.browser == "firefox"
        assert t.browser_profile is None
        assert t.output_dir == "~/.tokenade/synced"
        assert t.output_filename is None

    def test_create_custom(self):
        t = SyncTarget(
            name="github",
            domains=["github.com"],
            browser="brave",
            browser_profile="Profile 1",
            output_dir="/tmp/sync",
            output_filename="gh.tokenade",
        )
        assert t.browser == "brave"
        assert t.browser_profile == "Profile 1"
        assert t.output_filename == "gh.tokenade"

    def test_to_dict(self):
        t = SyncTarget(name="x", domains=["x.com"])
        d = asdict(t)
        assert d["name"] == "x"
        assert "domains" in d


# ─── SyncStatus ───────────────────────────────────────────────────────────────

class TestSyncStatus:
    def test_create_defaults(self):
        s = SyncStatus(target="gmail")
        assert s.target == "gmail"
        assert s.last_sync is None
        assert s.last_cookie_count == 0
        assert s.last_file_hash is None
        assert s.last_db_mtime == 0.0
        assert s.sync_count == 0
        assert s.error is None

    def test_create_with_values(self):
        s = SyncStatus(
            target="github",
            last_sync="2026-01-01T00:00:00",
            last_cookie_count=15,
            sync_count=3,
        )
        assert s.last_cookie_count == 15
        assert s.sync_count == 3


# ─── SessionSyncDaemon ────────────────────────────────────────────────────────

class TestSessionSyncDaemon:
    def test_init_creates_storage_dir(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path / "sync"))
        assert d.storage_dir.exists()
        assert d._targets == []
        assert d._statuses == {}
        assert d._running is False

    def test_add_target(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        t = SyncTarget(name="gmail", domains=["google.com"])
        d.add_target(t)
        assert len(d._targets) == 1
        assert d._targets[0].name == "gmail"
        assert "gmail" in d._statuses

    def test_add_target_no_duplicate_status(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        t = SyncTarget(name="gmail", domains=["google.com"])
        d.add_target(t)
        d.add_target(t)  # second add appends but doesn't reset status
        assert len(d._targets) == 2  # both added to list
        assert d._statuses["gmail"].sync_count == 0  # status preserved

    def test_remove_target(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        d.add_target(SyncTarget(name="a", domains=["a.com"]))
        d.add_target(SyncTarget(name="b", domains=["b.com"]))
        d.remove_target("a")
        assert len(d._targets) == 1
        assert d._targets[0].name == "b"
        assert "a" not in d._statuses

    def test_remove_nonexistent_noop(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        d.remove_target("nonexistent")  # should not raise

    def test_on_sync_callback(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        calls = []
        d.on_sync(lambda name, count: calls.append((name, count)))
        assert len(d._on_sync_callbacks) == 1

    def test_get_status_empty(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        assert d.get_status() == []

    def test_get_status_with_targets(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        d.add_target(SyncTarget(name="gmail", domains=["google.com"]))
        d.add_target(SyncTarget(name="github", domains=["github.com"], browser="brave"))
        statuses = d.get_status()
        assert len(statuses) == 2
        names = {s["name"] for s in statuses}
        assert names == {"gmail", "github"}
        assert all("browser" in s for s in statuses)
        assert all("domains" in s for s in statuses)
        assert all("last_sync" in s for s in statuses)
        assert all("sync_count" in s for s in statuses)

    def test_get_status_with_error(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        d.add_target(SyncTarget(name="x", domains=["x.com"]))
        d._statuses["x"].error = "Extraction failed"
        statuses = d.get_status()
        assert statuses[0]["error"] == "Extraction failed"


# ─── Config persistence ───────────────────────────────────────────────────────

class TestConfigPersistence:
    def test_save_and_load_config(self, tmp_path):
        d1 = SessionSyncDaemon(storage_dir=str(tmp_path))
        d1.add_target(SyncTarget(
            name="gmail",
            domains=["google.com", "accounts.google.com"],
            browser="firefox",
        ))
        d1.add_target(SyncTarget(
            name="github",
            domains=["github.com"],
            browser="brave",
            browser_profile="Profile 1",
            output_dir="/tmp/gh",
            output_filename="gh.tokenade",
        ))
        d1.save_config()

        # Verify config file exists
        config_path = tmp_path / "sync_config.json"
        assert config_path.exists()

        # Load into new daemon
        d2 = SessionSyncDaemon.load_config(storage_dir=str(tmp_path))
        assert len(d2._targets) == 2
        names = {t.name for t in d2._targets}
        assert names == {"gmail", "github"}

        # Verify all fields round-trip
        github = [t for t in d2._targets if t.name == "github"][0]
        assert github.browser == "brave"
        assert github.browser_profile == "Profile 1"
        assert github.output_dir == "/tmp/gh"
        assert github.output_filename == "gh.tokenade"

    def test_load_config_no_file(self, tmp_path):
        d = SessionSyncDaemon.load_config(storage_dir=str(tmp_path))
        assert len(d._targets) == 0

    def test_load_config_empty_file(self, tmp_path):
        config_path = tmp_path / "sync_config.json"
        config_path.write_text("{}")
        d = SessionSyncDaemon.load_config(storage_dir=str(tmp_path))
        assert len(d._targets) == 0

    def test_save_config_empty(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        d.save_config()
        config_path = tmp_path / "sync_config.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert data["targets"] == []


# ─── Extract and save ─────────────────────────────────────────────────────────

class TestExtractAndSave:
    @patch("tokenade.core.importer.session_sync.SessionSyncDaemon._get_db_path")
    def test_get_db_mtime_returns_stat(self, mock_get_db, tmp_path):
        # Create a dummy file to stat
        dummy = tmp_path / "cookies.sqlite"
        dummy.write_text("dummy")
        mock_get_db.return_value = dummy

        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        target = SyncTarget(name="x", domains=["x.com"])
        mtime = d._get_db_mtime(target)
        assert mtime > 0

    def test_get_db_mtime_missing_db(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        target = SyncTarget(name="x", domains=["x.com"])
        with patch.object(d, "_get_db_path", return_value=None):
            assert d._get_db_mtime(target) == 0.0

    def test_get_db_mtime_nonexistent(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        target = SyncTarget(name="x", domains=["x.com"])
        with patch.object(d, "_get_db_path", return_value=Path("/nonexistent/file.sqlite")):
            assert d._get_db_mtime(target) == 0.0


# ─── Check once ───────────────────────────────────────────────────────────────

class TestCheckOnce:
    def test_check_once_first_run_triggers_extraction(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        target = SyncTarget(name="gmail", domains=["google.com"])
        d.add_target(target)

        # Mock _get_db_mtime to return 0 (no database)
        with patch.object(d, "_get_db_mtime", return_value=0.0), \
                patch.object(d, "_extract_and_save", return_value=10):
            results = d.check_once()
            # First run with mtime=0 should extract
            assert results["gmail"] is True
            assert d._statuses["gmail"].sync_count == 1
            assert d._statuses["gmail"].last_cookie_count == 10

    def test_check_once_no_change_skips(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        target = SyncTarget(name="gmail", domains=["google.com"])
        d.add_target(target)

        # Set initial mtime
        d._statuses["gmail"].last_db_mtime = 100.0

        with patch.object(d, "_get_db_mtime", return_value=100.0), \
                patch.object(d, "_extract_and_save") as mock_extract:
            results = d.check_once()
            assert results["gmail"] is False
            mock_extract.assert_not_called()

    def test_check_once_change_detected(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        target = SyncTarget(name="gmail", domains=["google.com"])
        d.add_target(target)

        d._statuses["gmail"].last_db_mtime = 100.0

        with patch.object(d, "_get_db_mtime", return_value=200.0), \
                patch.object(d, "_extract_and_save", return_value=25):
            results = d.check_once()
            assert results["gmail"] is True
            assert d._statuses["gmail"].last_cookie_count == 25
            assert d._statuses["gmail"].last_db_mtime == 200.0

    def test_check_once_extraction_failure(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        d.add_target(SyncTarget(name="x", domains=["x.com"]))

        with patch.object(d, "_get_db_mtime", return_value=0.0), \
                patch.object(d, "_extract_and_save", return_value=None):
            results = d.check_once()
            assert results["x"] is False
            assert d._statuses["x"].error == "Extraction failed"

    def test_check_once_multiple_targets(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        d.add_target(SyncTarget(name="a", domains=["a.com"]))
        d.add_target(SyncTarget(name="b", domains=["b.com"]))

        with patch.object(d, "_get_db_mtime", return_value=0.0), \
                patch.object(d, "_extract_and_save", side_effect=[5, 10]):
            results = d.check_once()
            assert results["a"] is True
            assert results["b"] is True

    def test_check_once_callback_fires(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        calls = []
        d.on_sync(lambda name, count: calls.append((name, count)))

        d.add_target(SyncTarget(name="gmail", domains=["google.com"]))

        with patch.object(d, "_get_db_mtime", return_value=0.0), \
                patch.object(d, "_extract_and_save", return_value=15):
            d.check_once()
            assert calls == [("gmail", 15)]

    def test_check_once_callback_error_ignored(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        d.on_sync(lambda name, count: 1 / 0)  # will raise

        d.add_target(SyncTarget(name="gmail", domains=["google.com"]))

        with patch.object(d, "_get_db_mtime", return_value=0.0), \
                patch.object(d, "_extract_and_save", return_value=15):
            results = d.check_once()  # should not raise
            assert results["gmail"] is True

    def test_check_once_skips_none_targets(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        with patch.object(d, "_get_db_mtime", return_value=0.0), \
                patch.object(d, "_extract_and_save", return_value=0):
            results = d.check_once()
            assert results == {}


# ─── Start / stop lifecycle ───────────────────────────────────────────────────

class TestDaemonLifecycle:
    def test_stop_sets_flag(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        d._running = True
        d.stop()
        assert d._running is False

    def test_start_sets_running(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        d.add_target(SyncTarget(name="x", domains=["x.com"]))

        with patch.object(d, "_get_db_mtime", return_value=0.0), \
                patch.object(d, "_extract_and_save", return_value=0), \
                patch("time.sleep", side_effect=Exception("stop")):
            with pytest.raises(Exception, match="stop"):
                d.start(interval=1)

    def test_start_initial_sync(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        d.add_target(SyncTarget(name="x", domains=["x.com"]))

        with patch.object(d, "_get_db_mtime", return_value=0.0), \
                patch.object(d, "_extract_and_save", return_value=5), \
                patch("time.sleep", side_effect=Exception("stop")):
            with pytest.raises(Exception, match="stop"):
                d.start(interval=1)
            assert d._statuses["x"].sync_count == 1


# ─── Domain filtering ─────────────────────────────────────────────────────────

class TestDomainFiltering:
    def test_extract_filters_by_domain(self, tmp_path):
        """Test that _extract_and_save correctly filters cookies by domain."""
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        target = SyncTarget(name="gmail", domains=["google.com", "accounts.google.com"])

        # Mock the entire chain
        mock_discovery = MagicMock()
        mock_profile = MagicMock()
        mock_profile.path = tmp_path / "firefox_profile"
        mock_profile.browser = "firefox"
        mock_discovery.discover_all.return_value = {"firefox": [mock_profile]}
        (tmp_path / "firefox_profile").mkdir()

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = [
            {"domain": "google.com", "name": "sid", "value": "123"},
            {"domain": "accounts.google.com", "name": "auth", "value": "456"},
            {"domain": "youtube.com", "name": "vid", "value": "789"},  # should be filtered out
            {"domain": ".google.com", "name": "pre", "value": "000"},  # should be included
        ]

        mock_packager = MagicMock()
        mock_packager.package.return_value = {
            "cookies": [],
            "metadata": {},
        }

        with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery", return_value=mock_discovery), \
                patch("tokenade.core.importer.cookie_extractor.CookieExtractor", return_value=mock_extractor), \
                patch("tokenade.core.importer.session_packager.SessionPackager", return_value=mock_packager):
            count = d._extract_and_save(target)
            # google.com, accounts.google.com, .google.com = 3 cookies
            # youtube.com should be filtered out
            assert count == 3

    def test_extract_no_matching_cookies(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        target = SyncTarget(name="x", domains=["x.com"])

        mock_discovery = MagicMock()
        mock_profile = MagicMock()
        mock_profile.path = tmp_path / "fp"
        mock_profile.browser = "firefox"
        mock_discovery.discover_all.return_value = {"firefox": [mock_profile]}

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = [
            {"domain": "other.com", "name": "a", "value": "b"},
        ]

        with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery", return_value=mock_discovery), \
                patch("tokenade.core.importer.cookie_extractor.CookieExtractor", return_value=mock_extractor):
            count = d._extract_and_save(target)
            assert count == 0

    def test_extract_with_dot_prefix_domains(self, tmp_path):
        """Test filtering with .-prefixed domains (e.g., .google.com matches mail.google.com)."""
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        target = SyncTarget(name="google", domains=[".google.com"])

        mock_discovery = MagicMock()
        mock_profile = MagicMock()
        mock_profile.path = tmp_path / "fp"
        mock_profile.browser = "firefox"
        mock_discovery.discover_all.return_value = {"firefox": [mock_profile]}

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = [
            {"domain": "mail.google.com", "name": "a", "value": "b"},
            {"domain": "google.com", "name": "c", "value": "d"},
            {"domain": "other.com", "name": "e", "value": "f"},
        ]

        mock_packager = MagicMock()
        mock_packager.package.return_value = {"cookies": [], "metadata": {}}

        with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery", return_value=mock_discovery), \
                patch("tokenade.core.importer.cookie_extractor.CookieExtractor", return_value=mock_extractor), \
                patch("tokenade.core.importer.session_packager.SessionPackager", return_value=mock_packager):
            count = d._extract_and_save(target)
            assert count == 2

    def test_extract_no_profiles_returns_none(self, tmp_path):
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        target = SyncTarget(name="x", domains=["x.com"])

        mock_discovery = MagicMock()
        mock_discovery.discover_all.return_value = {}

        with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery", return_value=mock_discovery):
            count = d._extract_and_save(target)
            assert count is None


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_extract_and_save_output_path(self, tmp_path):
        """Verify output file is created in the right place."""
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        target = SyncTarget(
            name="test",
            domains=["test.com"],
            output_dir=str(tmp_path / "output"),
            output_filename="test.session",
        )

        mock_discovery = MagicMock()
        mock_profile = MagicMock()
        mock_profile.path = tmp_path / "fp"
        mock_profile.name = "default"
        mock_profile.browser = "firefox"
        mock_discovery.discover_all.return_value = {"firefox": [mock_profile]}

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = [
            {"domain": "test.com", "name": "sid", "value": "abc"},
        ]

        mock_packager = MagicMock()
        mock_packager.package.return_value = {
            "cookies": [],
            "metadata": {},
        }
        mock_packager.save.return_value = None

        with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery", return_value=mock_discovery), \
                patch("tokenade.core.importer.cookie_extractor.CookieExtractor", return_value=mock_extractor), \
                patch("tokenade.core.importer.session_packager.SessionPackager", return_value=mock_packager):
            d._extract_and_save(target)
            # Verify packager.save was called with correct path. Compare the
            # recorded path argument directly: str(call_args) escapes
            # backslashes in its repr on Windows, breaking substring checks.
            call_args = mock_packager.save.call_args
            assert call_args is not None
            saved_path = call_args[0][1]
            assert saved_path == str(tmp_path / "output" / "test.session")

    def test_extract_and_save_default_filename(self, tmp_path):
        """Verify default filename uses target name."""
        d = SessionSyncDaemon(storage_dir=str(tmp_path))
        target = SyncTarget(name="gmail", domains=["google.com"])

        mock_discovery = MagicMock()
        mock_profile = MagicMock()
        mock_profile.path = tmp_path / "fp"
        mock_profile.name = "default"
        mock_profile.browser = "firefox"
        mock_discovery.discover_all.return_value = {"firefox": [mock_profile]}

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = [
            {"domain": "google.com", "name": "sid", "value": "abc"},
        ]

        mock_packager = MagicMock()
        mock_packager.package.return_value = {
            "cookies": [],
            "metadata": {},
        }

        with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery", return_value=mock_discovery), \
                patch("tokenade.core.importer.cookie_extractor.CookieExtractor", return_value=mock_extractor), \
                patch("tokenade.core.importer.session_packager.SessionPackager", return_value=mock_packager):
            d._extract_and_save(target)
            call_args = mock_packager.save.call_args
            assert "gmail.tokenade" in str(call_args)


# ─── CLI integration ──────────────────────────────────────────────────────────

class TestCLISyncCommands:
    """Test CLI sync subcommands via management module."""

    @patch("tokenade.core.importer.session_sync.SessionSyncDaemon.load_config")
    def test_cmd_sync_list(self, mock_load_config, tmp_path, capsys):
        from tokenade.cli.management import cmd_sync
        mock_daemon = MagicMock()
        mock_daemon.get_status.return_value = [
            {"name": "gmail", "browser": "firefox", "sync_count": 3, "domains": ["google.com"],
             "output_dir": "~/.tokenade/synced", "last_sync": None, "last_cookie_count": 0, "error": None},
        ]
        mock_load_config.return_value = mock_daemon
        args = Namespace(sync_command="list")
        cmd_sync(args)
        output = capsys.readouterr().out
        assert "gmail" in output

    @patch("tokenade.core.importer.session_sync.SessionSyncDaemon.load_config")
    def test_cmd_sync_add(self, mock_load_config, tmp_path, capsys):
        from tokenade.cli.management import cmd_sync
        mock_daemon = MagicMock()
        mock_load_config.return_value = mock_daemon
        args = Namespace(
            sync_command="add",
            name="github",
            domains="github.com",
            browser="brave",
            profile=None,
            output_dir=None,
        )
        cmd_sync(args)
        mock_daemon.add_target.assert_called_once()
        mock_daemon.save_config.assert_called_once()

    @patch("tokenade.core.importer.session_sync.SessionSyncDaemon.load_config")
    def test_cmd_sync_remove(self, mock_load_config, tmp_path, capsys):
        from tokenade.cli.management import cmd_sync
        mock_daemon = MagicMock()
        mock_load_config.return_value = mock_daemon
        args = Namespace(sync_command="remove", name="gmail")
        cmd_sync(args)
        mock_daemon.remove_target.assert_called_once_with("gmail")
        mock_daemon.save_config.assert_called_once()

    def test_cmd_sync_add_missing_name(self, capsys):
        from tokenade.cli.management import cmd_sync
        args = Namespace(sync_command="add", name=None, domains="x.com",
                         browser="firefox", profile=None, output_dir=None)
        cmd_sync(args)
        assert "required" in capsys.readouterr().out.lower()

    def test_cmd_sync_add_missing_domains(self, capsys):
        from tokenade.cli.management import cmd_sync
        args = Namespace(sync_command="add", name="x", domains=None,
                         browser="firefox", profile=None, output_dir=None)
        cmd_sync(args)
        assert "required" in capsys.readouterr().out.lower()

    def test_cmd_sync_remove_missing_name(self, capsys):
        from tokenade.cli.management import cmd_sync
        args = Namespace(sync_command="remove", name=None)
        cmd_sync(args)
        assert "required" in capsys.readouterr().out.lower()

    @patch("tokenade.core.importer.session_sync.SessionSyncDaemon.load_config")
    def test_cmd_sync_list_empty(self, mock_load_config, capsys):
        from tokenade.cli.management import cmd_sync
        mock_daemon = MagicMock()
        mock_daemon.get_status.return_value = []
        mock_load_config.return_value = mock_daemon
        args = Namespace(sync_command="list")
        cmd_sync(args)
        output = capsys.readouterr().out
        assert "no sync targets" in output.lower()
