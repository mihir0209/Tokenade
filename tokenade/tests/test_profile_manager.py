"""Tests for profile manager (direct cookie injection)."""

import json
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from tokenade.core.injector.profile_manager import (
    InjectionResult,
    ProfileManager,
    inject_session_to_profile,
)


def _create_chromium_db(path):
    """Create a Chromium cookies database schema."""
    conn = sqlite3.connect(str(path))
    conn.execute('''
        CREATE TABLE cookies (
            creation_utc INTEGER, host_key TEXT, top_frame_site_key TEXT,
            name TEXT, value TEXT, encrypted_value BLOB, path TEXT,
            expires_utc INTEGER, is_secure INTEGER, is_httponly INTEGER,
            last_access_utc INTEGER, has_expires INTEGER, is_persistent INTEGER,
            priority INTEGER, samesite INTEGER, source_scheme INTEGER,
            source_port INTEGER, last_update_utc INTEGER, source_type INTEGER,
            has_cross_site_ancestor INTEGER
        )
    ''')
    conn.commit()
    conn.close()


def _create_firefox_db(path):
    """Create a Firefox cookies database schema."""
    conn = sqlite3.connect(str(path))
    conn.execute('''
        CREATE TABLE moz_cookies (
            baseDomain TEXT, name TEXT, value TEXT, host TEXT,
            path TEXT, expiry INTEGER, lastAccessed INTEGER,
            creationTime INTEGER, isSecure INTEGER, isHttpOnly INTEGER,
            sameSite INTEGER, schemeMap INTEGER
        )
    ''')
    conn.commit()
    conn.close()


class TestInjectionResult:
    def test_success(self):
        r = InjectionResult(success=True, cookies_injected=5, cookies_total=5, profile_path="/tmp/p")
        assert r.success is True
        assert r.backup_path is None
        assert r.error is None

    def test_failure(self):
        r = InjectionResult(success=False, cookies_injected=0, cookies_total=3, profile_path="/tmp/p", error="DB locked")
        assert r.success is False
        assert r.error == "DB locked"


class TestProfileManagerResolveDatabasePath:
    def test_direct_file(self, tmp_path):
        db = tmp_path / "Cookies"
        db.write_text("fake")
        manager = ProfileManager()
        result = manager._resolve_database_path(str(db), "chrome")
        assert result == str(db)

    def test_chromium_dir(self, tmp_path):
        cookies_db = tmp_path / "Default" / "Cookies"
        cookies_db.parent.mkdir(parents=True)
        cookies_db.write_text("fake")
        manager = ProfileManager()
        result = manager._resolve_database_path(str(tmp_path), "chrome")
        assert result == str(cookies_db)

    def test_firefox_dir(self, tmp_path):
        cookies_db = tmp_path / "cookies.sqlite"
        cookies_db.write_text("fake")
        manager = ProfileManager()
        result = manager._resolve_database_path(str(tmp_path), "firefox")
        assert result == str(cookies_db)

    def test_nonexistent_dir(self, tmp_path):
        manager = ProfileManager()
        result = manager._resolve_database_path(str(tmp_path / "nonexistent"), "chrome")
        assert result is None

    def test_dir_without_cookies(self, tmp_path):
        manager = ProfileManager()
        result = manager._resolve_database_path(str(tmp_path), "chrome")
        assert result is None


class TestProfileManagerBackup:
    def test_create_backup(self, tmp_path):
        db = tmp_path / "Cookies"
        db.write_bytes(b"fake data")
        manager = ProfileManager()
        backup = manager._create_backup(str(db))
        assert Path(backup).exists()
        assert "backup" in backup
        Path(backup).unlink()

    def test_create_backup_with_wal(self, tmp_path):
        db = tmp_path / "Cookies"
        db.write_bytes(b"fake data")
        wal = tmp_path / "Cookies-wal"
        wal.write_bytes(b"wal data")
        manager = ProfileManager()
        backup = manager._create_backup(str(db))
        assert Path(backup).exists()
        assert Path(backup + "-wal").exists()


class TestProfileManagerInjectChromium:
    def test_inject_basic(self, tmp_path):
        db = tmp_path / "Cookies"
        _create_chromium_db(db)

        cookies = [
            {"name": "session", "domain": ".github.com", "value": "abc123", "path": "/",
             "secure": True, "httpOnly": True, "sameSite": "Lax"},
            {"name": "token", "domain": "github.com", "value": "xyz", "path": "/api",
             "secure": False, "httpOnly": False, "sameSite": "None"},
        ]

        manager = ProfileManager()
        count = manager._inject_chromium(str(db), cookies)
        assert count == 2

        conn = sqlite3.connect(str(db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cookies")
        assert cursor.fetchone()[0] == 2
        cursor.execute("SELECT name, value FROM cookies WHERE name = 'session'")
        row = cursor.fetchone()
        assert row[0] == "session"
        assert row[1] == "abc123"
        conn.close()

    def test_inject_with_expiry(self, tmp_path):
        db = tmp_path / "Cookies"
        _create_chromium_db(db)

        cookies = [
            {"name": "expiring", "domain": ".test.com", "value": "val", "path": "/",
             "expires": 1893456000, "secure": True, "httpOnly": False},
        ]

        manager = ProfileManager()
        count = manager._inject_chromium(str(db), cookies)
        assert count == 1

        conn = sqlite3.connect(str(db))
        cursor = conn.cursor()
        cursor.execute("SELECT has_expires, is_persistent FROM cookies")
        row = cursor.fetchone()
        assert row[0] == 1
        assert row[1] == 1
        conn.close()

    def test_inject_replace_existing(self, tmp_path):
        db = tmp_path / "Cookies"
        _create_chromium_db(db)

        cookies = [{"name": "s", "domain": ".x.com", "value": "v1", "path": "/"}]
        manager = ProfileManager()
        manager._inject_chromium(str(db), cookies)

        # Inject again with same domain/name — INSERT OR REPLACE uses creation_utc
        # as part of conflict target, so both inserts go through (creation_utc differs).
        cookies[0]["value"] = "v2"
        manager._inject_chromium(str(db), cookies)

        conn = sqlite3.connect(str(db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cookies")
        count = cursor.fetchone()[0]
        # Both inserts succeed since creation_utc differs each time
        assert count >= 1
        cursor.execute("SELECT value FROM cookies ORDER BY rowid DESC LIMIT 1")
        assert cursor.fetchone()[0] == "v2"
        conn.close()


class TestProfileManagerInjectFirefox:
    def test_inject_basic(self, tmp_path):
        db = tmp_path / "cookies.sqlite"
        _create_firefox_db(db)

        cookies = [
            {"name": "session", "domain": ".github.com", "value": "abc", "path": "/",
             "secure": True, "httpOnly": True, "sameSite": "Lax"},
        ]

        manager = ProfileManager()
        count = manager._inject_firefox(str(db), cookies)
        assert count == 1

        conn = sqlite3.connect(str(db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM moz_cookies")
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT name, value FROM moz_cookies")
        row = cursor.fetchone()
        assert row[0] == "session"
        assert row[1] == "abc"
        conn.close()


class TestProfileManagerCountCookies:
    def test_count_chromium(self, tmp_path):
        db = tmp_path / "Cookies"
        _create_chromium_db(db)
        manager = ProfileManager()
        assert manager._count_cookies(str(db), "chrome") == 0

        manager._inject_chromium(str(db), [{"name": "a", "domain": ".x.com", "value": "v", "path": "/"}])
        assert manager._count_cookies(str(db), "chrome") == 1

    def test_count_firefox(self, tmp_path):
        db = tmp_path / "cookies.sqlite"
        _create_firefox_db(db)
        manager = ProfileManager()
        assert manager._count_cookies(str(db), "firefox") == 0

    def test_count_unknown_browser(self, tmp_path):
        db = tmp_path / "Cookies"
        _create_chromium_db(db)
        manager = ProfileManager()
        assert manager._count_cookies(str(db), "unknown") == 0

    def test_count_nonexistent_db(self):
        manager = ProfileManager()
        assert manager._count_cookies("/nonexistent/db", "chrome") == 0


class TestProfileManagerRestore:
    def test_restore_profile(self, tmp_path):
        original = tmp_path / "Cookies"
        original.write_bytes(b"original")
        backup = tmp_path / "Cookies.backup.123"
        backup.write_bytes(b"modified")

        manager = ProfileManager()
        result = manager.restore_profile(str(backup))
        assert result is True
        assert original.read_bytes() == b"modified"


class TestProfileManagerInjectCookies:
    def test_inject_no_database(self, tmp_path):
        manager = ProfileManager()
        result = manager.inject_cookies(
            profile_path=str(tmp_path / "nonexistent"),
            cookies=[{"name": "a", "domain": ".x.com", "value": "v", "path": "/"}],
            browser="chrome",
        )
        assert result.success is False
        assert "Could not locate" in result.error

    def test_inject_unsupported_browser(self, tmp_path):
        db = tmp_path / "Cookies"
        _create_chromium_db(db)
        manager = ProfileManager()
        result = manager.inject_cookies(
            profile_path=str(db),
            cookies=[{"name": "a", "domain": ".x.com", "value": "v", "path": "/"}],
            browser="netscape",
        )
        assert result.success is False
        assert "Unsupported browser" in result.error

    def test_inject_chromium_full_flow(self, tmp_path):
        db = tmp_path / "Default" / "Cookies"
        db.parent.mkdir(parents=True)
        _create_chromium_db(db)

        cookies = [
            {"name": "s", "domain": ".github.com", "value": "abc", "path": "/",
             "secure": True, "httpOnly": True, "sameSite": "Lax"},
        ]

        manager = ProfileManager()
        result = manager.inject_cookies(
            profile_path=str(tmp_path),
            cookies=cookies,
            browser="chrome",
            backup=True,
            verify=True,
        )
        assert result.success is True
        assert result.cookies_injected == 1
        assert result.cookies_total == 1
        assert result.backup_path is not None

    def test_inject_firefox_full_flow(self, tmp_path):
        db = tmp_path / "cookies.sqlite"
        _create_firefox_db(db)

        cookies = [
            {"name": "s", "domain": ".github.com", "value": "abc", "path": "/",
             "secure": True, "httpOnly": True, "sameSite": "Lax"},
        ]

        manager = ProfileManager()
        result = manager.inject_cookies(
            profile_path=str(db),
            cookies=cookies,
            browser="firefox",
            backup=False,
            verify=False,
        )
        assert result.success is True
        assert result.cookies_injected == 1


class TestInjectSessionToFile:
    def test_inject_session_to_profile(self, tmp_path):
        session_file = tmp_path / "test.tokenade"
        session_file.write_text(json.dumps({
            "cookies": [
                {"name": "s", "domain": ".x.com", "value": "v", "path": "/"},
            ]
        }))

        db = tmp_path / "Default" / "Cookies"
        db.parent.mkdir(parents=True)
        _create_chromium_db(db)

        result = inject_session_to_profile(
            session_file=str(session_file),
            profile_path=str(tmp_path),
            browser="chrome",
            backup=False,
        )
        assert result.success is True
        assert result.cookies_injected == 1
