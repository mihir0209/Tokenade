"""Tests for cookie crypto module."""

import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from tokenade.core.crypto.cookie_crypto import (
    DecryptedCookie,
    LinuxCookieCrypto,
    MacCookieCrypto,
    CookieCryptoFactory,
)


class TestDecryptedCookie:
    def test_defaults(self):
        c = DecryptedCookie(name="a", value="1", host_key=".x.com", path="/")
        assert c.name == "a"
        assert c.is_secure is False
        assert c.samesite == -1

    def test_to_playwright_format_basic(self):
        c = DecryptedCookie(name="sid", value="abc", host_key=".test.com", path="/")
        pw = c.to_playwright_format()
        assert pw["name"] == "sid"
        assert pw["value"] == "abc"
        assert pw["domain"] == ".test.com"
        assert "expires" not in pw

    def test_to_playwright_format_secure(self):
        c = DecryptedCookie(name="a", value="1", host_key=".x.com", path="/", is_secure=True)
        pw = c.to_playwright_format()
        assert pw["secure"] is True
        assert pw["sameSite"] == "None"

    def test_to_playwright_format_httponly(self):
        c = DecryptedCookie(name="a", value="1", host_key=".x.com", path="/", is_httponly=True)
        pw = c.to_playwright_format()
        assert pw["httpOnly"] is True

    def test_to_playwright_format_samesite_lax(self):
        c = DecryptedCookie(name="a", value="1", host_key=".x.com", path="/", samesite=1)
        pw = c.to_playwright_format()
        assert pw["sameSite"] == "Lax"

    def test_to_playwright_format_samesite_strict(self):
        c = DecryptedCookie(name="a", value="1", host_key=".x.com", path="/", samesite=2)
        pw = c.to_playwright_format()
        assert pw["sameSite"] == "Strict"

    def test_to_playwright_format_expires(self):
        chrome_epoch_offset = 11644473600
        unix_ts = 1893456000
        chrome_utc = int((unix_ts + chrome_epoch_offset) * 1000000)
        c = DecryptedCookie(name="a", value="1", host_key=".x.com", path="/", expires_utc=chrome_utc)
        pw = c.to_playwright_format()
        assert pw["expires"] == unix_ts

    def test_to_playwright_format_zero_expires(self):
        c = DecryptedCookie(name="a", value="1", host_key=".x.com", path="/", expires_utc=0)
        pw = c.to_playwright_format()
        assert "expires" not in pw

    def test_to_chrome_db_format(self):
        c = DecryptedCookie(name="a", value="1", host_key=".x.com", path="/",
                            is_secure=True, is_httponly=True, creation_utc=100)
        row, extra = c.to_chrome_db_format()
        assert row[0] == 100  # creation_utc
        assert row[3] == "a"  # name
        assert row[4] == "1"  # value
        assert row[8] == 1    # is_secure
        assert row[9] == 1    # is_httponly


class TestLinuxCookieCrypto:
    def test_encrypt_decrypt_roundtrip(self):
        crypto = LinuxCookieCrypto()
        plaintext = "hello_world_cookie_value"
        key = b"peanuts"

        encrypted = crypto.encrypt_cookie(plaintext, key)
        assert encrypted.startswith(b"v10")

        decrypted = crypto.decrypt_cookie(encrypted, key)
        assert decrypted == plaintext

    def test_decrypt_empty(self):
        crypto = LinuxCookieCrypto()
        result = crypto.decrypt_cookie(b"", b"peanuts")
        assert result == ""

    def test_get_encryption_key_fallback(self):
        crypto = LinuxCookieCrypto()
        key = crypto.get_encryption_key("/nonexistent")
        assert key == b"peanuts"

    def test_extract_cookies_nonexistent_db(self):
        crypto = LinuxCookieCrypto()
        cookies = crypto.extract_cookies("/nonexistent/cookies.db")
        assert cookies == []

    def test_extract_cookies_empty_db(self, tmp_path):
        db_path = tmp_path / "Cookies"
        conn = sqlite3.connect(str(db_path))
        conn.execute('''
            CREATE TABLE cookies (
                host_key TEXT, name TEXT, value TEXT, encrypted_value BLOB,
                path TEXT, expires_utc INTEGER, is_secure INTEGER, is_httponly INTEGER,
                creation_utc INTEGER, last_access_utc INTEGER, has_expires INTEGER,
                is_persistent INTEGER, priority INTEGER, samesite INTEGER, source_scheme INTEGER
            )
        ''')
        conn.execute("INSERT INTO cookies VALUES ('.x.com', 'a', 'val1', X'', '/', 0, 0, 0, 100, 100, 0, 0, 1, -1, 2)")
        conn.commit()
        conn.close()

        crypto = LinuxCookieCrypto()
        cookies = crypto.extract_cookies(str(db_path))
        assert len(cookies) == 1
        assert cookies[0].name == "a"
        assert cookies[0].value == "val1"


class TestMacCookieCrypto:
    def test_encrypt_decrypt_roundtrip(self):
        crypto = MacCookieCrypto()
        plaintext = "mac_cookie_test"
        key = b"peanuts"

        encrypted = crypto.encrypt_cookie(plaintext, key)
        assert encrypted.startswith(b"v10")

        decrypted = crypto.decrypt_cookie(encrypted, key)
        assert decrypted == plaintext

    def test_decrypt_empty(self):
        crypto = MacCookieCrypto()
        result = crypto.decrypt_cookie(b"", b"peanuts")
        assert result == ""

    def test_extract_cookies_nonexistent_db(self):
        crypto = MacCookieCrypto()
        cookies = crypto.extract_cookies("/nonexistent/cookies.db")
        assert cookies == []


class TestCookieCryptoFactory:
    def test_get_platform_linux(self):
        with patch("sys.platform", "linux"):
            platform = CookieCryptoFactory.get_platform()
            assert platform in ("posix", "linux")

    def test_create_linux(self):
        crypto = CookieCryptoFactory.create("linux")
        assert isinstance(crypto, LinuxCookieCrypto)

    def test_create_darwin(self):
        crypto = CookieCryptoFactory.create("darwin")
        assert isinstance(crypto, MacCookieCrypto)

    def test_create_windows(self):
        with pytest.raises(ImportError):
            CookieCryptoFactory.create("windows")

    def test_create_unsupported(self):
        with pytest.raises(ValueError, match="Unsupported platform"):
            CookieCryptoFactory.create("android")
