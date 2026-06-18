"""
Comprehensive tests for session_sync.py — SyncTarget, SyncStatus,
SessionSyncDaemon, target management, status, config save/load.
"""

import tempfile
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from tokenade.core.importer.session_sync import (
    SyncTarget,
    SyncStatus,
    SessionSyncDaemon,
)


class TestSyncTarget(unittest.TestCase):
    def test_defaults(self):
        t = SyncTarget(name="gmail", domains=["google.com"])
        self.assertEqual(t.name, "gmail")
        self.assertEqual(t.domains, ["google.com"])
        self.assertEqual(t.browser, "firefox")
        self.assertIsNone(t.browser_profile)

    def test_full(self):
        t = SyncTarget(
            name="github",
            domains=["github.com"],
            browser="chrome",
            browser_profile="Profile 1",
            output_dir="/tmp/out",
            output_filename="gh.tokenade",
        )
        self.assertEqual(t.browser, "chrome")
        self.assertEqual(t.output_filename, "gh.tokenade")


class TestSyncStatus(unittest.TestCase):
    def test_defaults(self):
        s = SyncStatus(target="gmail")
        self.assertEqual(s.target, "gmail")
        self.assertIsNone(s.last_sync)
        self.assertEqual(s.last_cookie_count, 0)
        self.assertEqual(s.sync_count, 0)


class TestSessionSyncDaemonInit(unittest.TestCase):
    def test_default_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            self.assertTrue(daemon.storage_dir.exists())
            self.assertEqual(daemon._targets, [])

    def test_custom_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            self.assertEqual(len(daemon._targets), 0)


class TestSessionSyncDaemonTargetManagement(unittest.TestCase):
    def test_add_target(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            target = SyncTarget(name="gmail", domains=["google.com"])
            daemon.add_target(target)
            self.assertEqual(len(daemon._targets), 1)
            self.assertIn("gmail", daemon._statuses)

    def test_add_target_no_duplicate_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            daemon.add_target(SyncTarget(name="gmail", domains=["google.com"]))
            daemon.add_target(SyncTarget(name="gmail", domains=["google.com"]))
            self.assertEqual(len(daemon._targets), 2)
            self.assertEqual(len(daemon._statuses), 1)

    def test_remove_target(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            daemon.add_target(SyncTarget(name="gmail", domains=["google.com"]))
            daemon.remove_target("gmail")
            self.assertEqual(len(daemon._targets), 0)
            self.assertNotIn("gmail", daemon._statuses)

    def test_remove_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            daemon.remove_target("nonexistent")


class TestSessionSyncDaemonOnSync(unittest.TestCase):
    def test_on_sync_callback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            cb = MagicMock()
            daemon.on_sync(cb)
            self.assertEqual(len(daemon._on_sync_callbacks), 1)


class TestSessionSyncDaemonGetDbPath(unittest.TestCase):
    def test_firefox(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            target = SyncTarget(
                name="gmail", domains=["google.com"], browser="firefox"
            )
            mock_profile = MagicMock()
            mock_profile.path = "/fake/firefox/profile"
            mock_profile.browser = "firefox"
            mock_profile.name = "default"
            with patch(
                "tokenade.core.importer.browser_discovery.BrowserProfileDiscovery"
            ) as MockDiscovery:
                MockDiscovery.return_value.discover_all.return_value = {
                    "firefox": [mock_profile]
                }
                result = daemon._get_db_path(target)
                self.assertIn("cookies.sqlite", str(result))

    def test_chrome(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            target = SyncTarget(
                name="github", domains=["github.com"], browser="chrome"
            )
            mock_profile = MagicMock()
            mock_profile.path = "/fake/chrome/profile"
            mock_profile.browser = "chrome"
            mock_profile.name = "Default"
            with patch(
                "tokenade.core.importer.browser_discovery.BrowserProfileDiscovery"
            ) as MockDiscovery:
                MockDiscovery.return_value.discover_all.return_value = {
                    "chrome": [mock_profile]
                }
                result = daemon._get_db_path(target)
                self.assertIn("Cookies", str(result))

    def test_no_profiles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            target = SyncTarget(
                name="test", domains=["test.com"], browser="opera"
            )
            with patch(
                "tokenade.core.importer.browser_discovery.BrowserProfileDiscovery"
            ) as MockDiscovery:
                MockDiscovery.return_value.discover_all.return_value = {}
                result = daemon._get_db_path(target)
                self.assertIsNone(result)


class TestSessionSyncDaemonGetDbMtime(unittest.TestCase):
    def test_mtime_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            target = SyncTarget(name="test", domains=["test.com"])
            with patch.object(
                daemon, "_get_db_path", return_value=Path("/nonexistent")
            ):
                result = daemon._get_db_mtime(target)
                self.assertEqual(result, 0.0)

    def test_mtime_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            target = SyncTarget(name="test", domains=["test.com"])
            with tempfile.NamedTemporaryFile() as f:
                with patch.object(
                    daemon, "_get_db_path", return_value=Path(f.name)
                ):
                    result = daemon._get_db_mtime(target)
                    self.assertGreater(result, 0.0)


class TestSessionSyncDaemonCheckOnce(unittest.TestCase):
    def test_check_once_first_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            target = SyncTarget(
                name="gmail", domains=["google.com"], browser="firefox"
            )
            daemon.add_target(target)
            with (
                patch.object(daemon, "_get_db_mtime", return_value=100.0),
                patch.object(daemon, "_extract_and_save", return_value=5),
            ):
                results = daemon.check_once()
                self.assertTrue(results["gmail"])

    def test_check_once_no_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            target = SyncTarget(name="gmail", domains=["google.com"])
            daemon.add_target(target)
            daemon._statuses["gmail"].last_db_mtime = 100.0
            with patch.object(daemon, "_get_db_mtime", return_value=100.0):
                results = daemon.check_once()
                self.assertFalse(results["gmail"])

    def test_check_once_extraction_failed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            target = SyncTarget(name="gmail", domains=["google.com"])
            daemon.add_target(target)
            with (
                patch.object(daemon, "_get_db_mtime", return_value=200.0),
                patch.object(daemon, "_extract_and_save", return_value=None),
            ):
                results = daemon.check_once()
                self.assertFalse(results["gmail"])

    def test_check_once_callback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            target = SyncTarget(name="gmail", domains=["google.com"])
            daemon.add_target(target)
            cb = MagicMock()
            daemon.on_sync(cb)
            with (
                patch.object(daemon, "_get_db_mtime", return_value=200.0),
                patch.object(daemon, "_extract_and_save", return_value=10),
            ):
                daemon.check_once()
                cb.assert_called_once_with("gmail", 10)

    def test_check_once_zero_cookies(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            target = SyncTarget(name="gmail", domains=["google.com"])
            daemon.add_target(target)
            with (
                patch.object(daemon, "_get_db_mtime", return_value=200.0),
                patch.object(daemon, "_extract_and_save", return_value=0),
            ):
                results = daemon.check_once()
                self.assertTrue(results["gmail"])


class TestSessionSyncDaemonGetStatus(unittest.TestCase):
    def test_get_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            daemon.add_target(
                SyncTarget(
                    name="gmail",
                    domains=["google.com"],
                    browser="firefox",
                    output_dir="/tmp/out",
                )
            )
            statuses = daemon.get_status()
            self.assertEqual(len(statuses), 1)
            self.assertEqual(statuses[0]["name"], "gmail")


class TestSessionSyncDaemonSaveLoadConfig(unittest.TestCase):
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            daemon.add_target(
                SyncTarget(
                    name="gmail", domains=["google.com"], browser="firefox"
                )
            )
            daemon.save_config()

            loaded = SessionSyncDaemon.load_config(tmpdir)
            self.assertEqual(len(loaded._targets), 1)
            self.assertEqual(loaded._targets[0].name, "gmail")

    def test_load_no_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            loaded = SessionSyncDaemon.load_config(tmpdir)
            self.assertEqual(len(loaded._targets), 0)


class TestSessionSyncDaemonStartStop(unittest.TestCase):
    def test_stop(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            daemon._running = True
            daemon.stop()
            self.assertFalse(daemon._running)

    def test_start_runs_check_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = SessionSyncDaemon(storage_dir=tmpdir)
            with patch.object(
                daemon, "check_once", return_value={}
            ) as mock_check:
                with patch("time.sleep", side_effect=KeyboardInterrupt):
                    try:
                        daemon.start(interval=1)
                    except KeyboardInterrupt:
                        pass
                mock_check.assert_called()


if __name__ == "__main__":
    unittest.main()
