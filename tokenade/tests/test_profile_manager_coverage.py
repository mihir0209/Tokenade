"""
Comprehensive tests for profile_manager.py — InjectionResult, ProfileManager,
inject_cookies, resolve_database_path, backup, inject_chromium/firefox, etc.
"""
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from tokenade.core.injector.profile_manager import (
    InjectionResult,
    ProfileManager,
    inject_session_to_profile,
)


class TestInjectionResult(unittest.TestCase):
    def test_defaults(self):
        r = InjectionResult(success=False, cookies_injected=0, cookies_total=5, profile_path="/tmp")
        self.assertFalse(r.success)
        self.assertEqual(r.cookies_total, 5)
        self.assertIsNone(r.backup_path)
        self.assertIsNone(r.error)

    def test_full(self):
        r = InjectionResult(success=True, cookies_injected=10, cookies_total=10, profile_path="/tmp",
                            backup_path="/tmp.bak", error="none")
        self.assertTrue(r.success)


class TestProfileManagerInit(unittest.TestCase):
    def test_init(self):
        m = ProfileManager()
        self.assertEqual(m.CHROME_EPOCH_OFFSET, 11644473600)


class TestProfileManagerResolveDatabasePath(unittest.TestCase):
    def test_file_path(self):
        m = ProfileManager()
        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            result = m._resolve_database_path(f.name, "chrome")
            self.assertEqual(result, f.name)

    def test_dir_chromium(self):
        m = ProfileManager()
        with tempfile.TemporaryDirectory() as tmpdir:
            cookies_path = os.path.join(tmpdir, "Default", "Cookies")
            os.makedirs(os.path.dirname(cookies_path))
            open(cookies_path, "w").close()
            result = m._resolve_database_path(tmpdir, "chrome")
            self.assertEqual(result, cookies_path)

    def test_dir_firefox(self):
        m = ProfileManager()
        with tempfile.TemporaryDirectory() as tmpdir:
            cookies_path = os.path.join(tmpdir, "cookies.sqlite")
            open(cookies_path, "w").close()
            result = m._resolve_database_path(tmpdir, "firefox")
            self.assertEqual(result, cookies_path)

    def test_dir_no_cookies(self):
        m = ProfileManager()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = m._resolve_database_path(tmpdir, "chrome")
            self.assertIsNone(result)

    def test_nonexistent_path(self):
        m = ProfileManager()
        result = m._resolve_database_path("/nonexistent", "chrome")
        self.assertIsNone(result)


class TestProfileManagerCreateBackup(unittest.TestCase):
    def test_backup(self):
        m = ProfileManager()
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            f.write(b"test data")
            db_path = f.name
        try:
            backup = m._create_backup(db_path)
            self.assertTrue(os.path.exists(backup))
            os.unlink(backup)
        finally:
            os.unlink(db_path)


class TestProfileManagerInjectCookies(unittest.TestCase):
    def test_inject_no_database(self):
        m = ProfileManager()
        result = m.inject_cookies("/nonexistent", [{"name": "t"}], "chrome")
        self.assertFalse(result.success)
        self.assertIn("Could not locate", result.error)

    def test_inject_chromium(self):
        m = ProfileManager()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "Default", "Cookies")
            os.makedirs(os.path.dirname(db_path))
            conn = sqlite3.connect(db_path)
            conn.execute("""CREATE TABLE cookies (
                creation_utc INTEGER, host_key TEXT, top_frame_site_key TEXT,
                name TEXT, value TEXT, encrypted_value BLOB, path TEXT,
                expires_utc INTEGER, is_secure INTEGER, is_httponly INTEGER,
                last_access_utc INTEGER, has_expires INTEGER, is_persistent INTEGER,
                priority INTEGER, samesite INTEGER, source_scheme INTEGER,
                source_port INTEGER, last_update_utc INTEGER, source_type INTEGER,
                has_cross_site_ancestor INTEGER
            )""")
            conn.commit()
            conn.close()

            cookies = [{"name": "sid", "value": "abc", "domain": ".github.com", "path": "/"}]
            result = m.inject_cookies(tmpdir, cookies, "chrome", backup=False, verify=False)
            self.assertTrue(result.success)
            self.assertEqual(result.cookies_injected, 1)

    def test_inject_firefox(self):
        m = ProfileManager()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "cookies.sqlite")
            conn = sqlite3.connect(db_path)
            conn.execute("""CREATE TABLE moz_cookies (
                baseDomain TEXT, name TEXT, value TEXT, host TEXT, path TEXT,
                expiry INTEGER, lastAccessed INTEGER, creationTime INTEGER,
                isSecure INTEGER, isHttpOnly INTEGER, sameSite INTEGER, schemeMap INTEGER
            )""")
            conn.commit()
            conn.close()

            cookies = [{"name": "sid", "value": "abc", "domain": ".github.com", "path": "/"}]
            result = m.inject_cookies(tmpdir, cookies, "firefox", backup=False, verify=False)
            self.assertTrue(result.success)
            self.assertEqual(result.cookies_injected, 1)

    def test_inject_unsupported_browser(self):
        m = ProfileManager()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "Default", "Cookies")
            os.makedirs(os.path.dirname(db_path))
            open(db_path, "w").close()
            result = m.inject_cookies(tmpdir, [{"name": "t"}], "safari", backup=False)
            self.assertFalse(result.success)

    def test_inject_with_expiry(self):
        m = ProfileManager()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "Default", "Cookies")
            os.makedirs(os.path.dirname(db_path))
            conn = sqlite3.connect(db_path)
            conn.execute("""CREATE TABLE cookies (
                creation_utc INTEGER, host_key TEXT, top_frame_site_key TEXT,
                name TEXT, value TEXT, encrypted_value BLOB, path TEXT,
                expires_utc INTEGER, is_secure INTEGER, is_httponly INTEGER,
                last_access_utc INTEGER, has_expires INTEGER, is_persistent INTEGER,
                priority INTEGER, samesite INTEGER, source_scheme INTEGER,
                source_port INTEGER, last_update_utc INTEGER, source_type INTEGER,
                has_cross_site_ancestor INTEGER
            )""")
            conn.commit()
            conn.close()

            cookies = [{"name": "sid", "value": "abc", "domain": ".x.com", "path": "/",
                        "expires": 1700000000, "secure": True, "httpOnly": True, "sameSite": "Strict"}]
            result = m.inject_cookies(tmpdir, cookies, "chrome", backup=False, verify=False)
            self.assertTrue(result.success)

    def test_inject_with_large_expiry(self):
        m = ProfileManager()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "Default", "Cookies")
            os.makedirs(os.path.dirname(db_path))
            conn = sqlite3.connect(db_path)
            conn.execute("""CREATE TABLE cookies (
                creation_utc INTEGER, host_key TEXT, top_frame_site_key TEXT,
                name TEXT, value TEXT, encrypted_value BLOB, path TEXT,
                expires_utc INTEGER, is_secure INTEGER, is_httponly INTEGER,
                last_access_utc INTEGER, has_expires INTEGER, is_persistent INTEGER,
                priority INTEGER, samesite INTEGER, source_scheme INTEGER,
                source_port INTEGER, last_update_utc INTEGER, source_type INTEGER,
                has_cross_site_ancestor INTEGER
            )""")
            conn.commit()
            conn.close()

            cookies = [{"name": "sid", "value": "abc", "domain": ".x.com", "path": "/",
                        "expires": 1700000000000, "sameSite": "None"}]
            result = m.inject_cookies(tmpdir, cookies, "chrome", backup=False, verify=False)
            self.assertTrue(result.success)


class TestProfileManagerCountCookies(unittest.TestCase):
    def test_count_chromium(self):
        m = ProfileManager()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "Default", "Cookies")
            os.makedirs(os.path.dirname(db_path))
            conn = sqlite3.connect(db_path)
            conn.execute("""CREATE TABLE cookies (
                creation_utc INTEGER, host_key TEXT, top_frame_site_key TEXT,
                name TEXT, value TEXT, encrypted_value BLOB, path TEXT,
                expires_utc INTEGER, is_secure INTEGER, is_httponly INTEGER,
                last_access_utc INTEGER, has_expires INTEGER, is_persistent INTEGER,
                priority INTEGER, samesite INTEGER, source_scheme INTEGER,
                source_port INTEGER, last_update_utc INTEGER, source_type INTEGER,
                has_cross_site_ancestor INTEGER
            )""")
            conn.execute("INSERT INTO cookies VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (0, ".x.com", "", "t", "v", b"", "/", 0, 0, 0, 0, 0, 0, 1, 1, 1, 443, 0, 0, 0))
            conn.commit()
            conn.close()
            count = m._count_cookies(db_path, "chrome")
            self.assertEqual(count, 1)

    def test_count_firefox(self):
        m = ProfileManager()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "cookies.sqlite")
            conn = sqlite3.connect(db_path)
            conn.execute("""CREATE TABLE moz_cookies (
                baseDomain TEXT, name TEXT, value TEXT, host TEXT, path TEXT,
                expiry INTEGER, lastAccessed INTEGER, creationTime INTEGER,
                isSecure INTEGER, isHttpOnly INTEGER, sameSite INTEGER, schemeMap INTEGER
            )""")
            conn.execute("INSERT INTO moz_cookies VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         ("x.com", "t", "v", ".x.com", "/", 0, 0, 0, 0, 0, 1, 1))
            conn.commit()
            conn.close()
            count = m._count_cookies(db_path, "firefox")
            self.assertEqual(count, 1)

    def test_count_unknown_browser(self):
        m = ProfileManager()
        count = m._count_cookies("/nonexistent", "safari")
        self.assertEqual(count, 0)

    def test_count_exception(self):
        m = ProfileManager()
        count = m._count_cookies("/nonexistent", "chrome")
        self.assertEqual(count, 0)


class TestProfileManagerRestoreProfile(unittest.TestCase):
    def test_restore(self):
        m = ProfileManager()
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as orig:
            orig.write(b"original")
            orig_path = orig.name
        backup_path = orig_path + ".backup.12345"
        with open(backup_path, "wb") as f:
            f.write(b"restored")
        try:
            result = m.restore_profile(backup_path)
            self.assertTrue(result)
            with open(orig_path, "rb") as f:
                self.assertEqual(f.read(), b"restored")
        finally:
            os.unlink(orig_path)
            os.unlink(backup_path)

    def test_restore_no_backup_marker(self):
        m = ProfileManager()
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as orig:
            orig.write(b"original")
            orig_path = orig.name
        backup_path = orig_path + ".backup.nobackup"
        with open(backup_path, "wb") as f:
            f.write(b"restored data")
        try:
            result = m.restore_profile(backup_path)
            self.assertTrue(result)
        finally:
            os.unlink(orig_path)
            if os.path.exists(backup_path):
                os.unlink(backup_path)


class TestInjectSessionToProfile(unittest.TestCase):
    def test_inject(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = os.path.join(tmpdir, "test.tokenade")
            with open(session_file, "w") as f:
                import json
                json.dump({"cookies": [{"name": "t", "value": "v", "domain": ".x.com", "path": "/"}]}, f)

            profile_dir = os.path.join(tmpdir, "profile")
            os.makedirs(os.path.join(profile_dir, "Default"))
            db_path = os.path.join(profile_dir, "Default", "Cookies")
            conn = sqlite3.connect(db_path)
            conn.execute("""CREATE TABLE cookies (
                creation_utc INTEGER, host_key TEXT, top_frame_site_key TEXT,
                name TEXT, value TEXT, encrypted_value BLOB, path TEXT,
                expires_utc INTEGER, is_secure INTEGER, is_httponly INTEGER,
                last_access_utc INTEGER, has_expires INTEGER, is_persistent INTEGER,
                priority INTEGER, samesite INTEGER, source_scheme INTEGER,
                source_port INTEGER, last_update_utc INTEGER, source_type INTEGER,
                has_cross_site_ancestor INTEGER
            )""")
            conn.commit()
            conn.close()

            result = inject_session_to_profile(session_file, profile_dir, "chrome", backup=False)
            self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
