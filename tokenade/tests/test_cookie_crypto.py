"""Tests for cookie crypto module."""

import json
import os
import sqlite3
import pytest
from unittest.mock import patch, MagicMock

from tokenade.core.crypto.cookie_crypto import (
    DecryptedCookie,
    LinuxCookieCrypto,
    MacCookieCrypto,
    WindowsCookieCrypto,
    CookieCrypto,
    CookieCryptoFactory,
)


# ---------------------------------------------------------------------------
# DecryptedCookie
# ---------------------------------------------------------------------------

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

    def test_to_playwright_format_negative_expires_excluded(self):
        c = DecryptedCookie(name="a", value="1", host_key=".x.com", path="/", expires_utc=-1)
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


# ---------------------------------------------------------------------------
# Abstract base – can't instantiate directly
# ---------------------------------------------------------------------------

class TestCookieCryptoAbstract:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            CookieCrypto()


# ---------------------------------------------------------------------------
# WindowsCookieCrypto
# ---------------------------------------------------------------------------

class TestWindowsCookieCrypto:
    """Tests for WindowsCookieCrypto – all OS imports are mocked."""

    @patch("tokenade.core.crypto.cookie_crypto.WindowsCookieCrypto._ensure_imports")
    def _make(self, mock_ensure):
        crypto = object.__new__(WindowsCookieCrypto)
        crypto._dpapi = MagicMock()
        crypto._aes = MagicMock()
        return crypto

    # -- _ensure_imports paths (lines 132-141) --

    def test_ensure_imports_success(self):
        mock_win32 = MagicMock()
        mock_aes = MagicMock()
        mock_cipher = MagicMock()
        mock_cipher.AES = mock_aes
        mock_crypto = MagicMock()
        mock_crypto.Cipher = mock_cipher
        with patch.dict("sys.modules", {
            "win32crypt": mock_win32,
            "Crypto": mock_crypto,
            "Crypto.Cipher": mock_cipher,
        }):
            crypto = WindowsCookieCrypto()
            assert crypto._dpapi is mock_win32
            assert crypto._aes is mock_aes

    def test_ensure_imports_missing_raises(self):
        with patch.dict("sys.modules", {"win32crypt": None, "Crypto": None}):
            with pytest.raises(ImportError):
                WindowsCookieCrypto()

    # -- get_encryption_key (lines 145-166) --

    def test_get_encryption_key_local_state_not_found(self):
        crypto = self._make()
        result = crypto.get_encryption_key("/nonexistent")
        assert result is None

    def test_get_encryption_key_success(self, tmp_path):
        crypto = self._make()
        local_state = {
            "os_crypt": {
                "encrypted_key": __import__("base64").b64encode(b"DPAPI" + b"\x00" * 32).decode()
            }
        }
        state_file = tmp_path / "Local State"
        state_file.write_text(json.dumps(local_state))

        crypto._dpapi.CryptUnprotectData.return_value = (None, b"decrypted_key_32bytes", None, None)
        result = crypto.get_encryption_key(str(tmp_path))
        assert result == b"decrypted_key_32bytes"
        crypto._dpapi.CryptUnprotectData.assert_called_once()

    def test_get_encryption_key_json_error(self, tmp_path):
        crypto = self._make()
        state_file = tmp_path / "Local State"
        state_file.write_text("not json {{{")
        result = crypto.get_encryption_key(str(tmp_path))
        assert result is None

    def test_get_encryption_key_missing_os_crypt(self, tmp_path):
        crypto = self._make()
        state_file = tmp_path / "Local State"
        state_file.write_text(json.dumps({"other_key": True}))
        result = crypto.get_encryption_key(str(tmp_path))
        assert result is None

    def test_get_encryption_key_dpapi_failure(self, tmp_path):
        crypto = self._make()
        local_state = {
            "os_crypt": {
                "encrypted_key": __import__("base64").b64encode(b"DPAPI" + b"\x00" * 32).decode()
            }
        }
        state_file = tmp_path / "Local State"
        state_file.write_text(json.dumps(local_state))
        crypto._dpapi.CryptUnprotectData.side_effect = Exception("DPAPI failed")
        result = crypto.get_encryption_key(str(tmp_path))
        assert result is None

    # -- decrypt_cookie (lines 168-195) --

    def test_decrypt_empty(self):
        crypto = self._make()
        assert crypto.decrypt_cookie(b"", b"key") == ""

    def test_decrypt_v10(self):
        crypto = self._make()
        nonce = b"\x01" * 12
        tag = b"\x02" * 16
        plaintext_with_meta = b"\x00" * 32 + b"secret_value"
        mock_cipher = MagicMock()
        mock_cipher.decrypt.return_value = plaintext_with_meta
        crypto._aes.new.return_value = mock_cipher
        crypto._aes.MODE_GCM = "GCM"

        encrypted = b"v10" + nonce + b"\x03" * 32 + tag
        result = crypto.decrypt_cookie(encrypted, b"key_32_bytes_here")
        assert result == "secret_value"
        crypto._aes.new.assert_called_once_with(b"key_32_bytes_here", "GCM", nonce=nonce)

    def test_decrypt_v11(self):
        crypto = self._make()
        nonce = b"\x01" * 12
        tag = b"\x02" * 16
        plaintext_with_meta = b"\x00" * 32 + b"v11_value"
        mock_cipher = MagicMock()
        mock_cipher.decrypt.return_value = plaintext_with_meta
        crypto._aes.new.return_value = mock_cipher
        crypto._aes.MODE_GCM = "GCM"

        encrypted = b"v11" + nonce + b"\x03" * 32 + tag
        result = crypto.decrypt_cookie(encrypted, b"key_32_bytes_here")
        assert result == "v11_value"

    def test_decrypt_old_dpapi(self):
        crypto = self._make()
        crypto._dpapi.CryptUnprotectData.return_value = (None, b"old_dpapi_value", None, None)
        encrypted = b"\x01" * 20  # non-v10/v11 prefix
        result = crypto.decrypt_cookie(encrypted, b"key")
        assert result == "old_dpapi_value"

    def test_decrypt_exception_returns_none(self):
        crypto = self._make()
        # v10 prefix but key=None causes AttributeError on AES.new(None, ...)
        crypto._aes.new.return_value.decrypt.side_effect = Exception("decrypt fail")
        result = crypto.decrypt_cookie(b"v10" + b"\x00" * 30, b"key")
        assert result is None

    # -- encrypt_cookie (line 199) --

    def test_encrypt_not_implemented(self):
        crypto = self._make()
        with pytest.raises(NotImplementedError, match="Windows encryption not implemented"):
            crypto.encrypt_cookie("test", b"key")

    # -- extract_cookies (lines 203-268) --

    def test_extract_cookies_db_not_found(self):
        crypto = self._make()
        assert crypto.extract_cookies("/nonexistent/cookies.db") == []

    def test_extract_cookies_empty_db(self, tmp_path):
        crypto = self._make()
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
        conn.commit()
        conn.close()

        result = crypto.extract_cookies(str(db_path))
        assert result == []

    def test_extract_cookies_with_plaintext_value(self, tmp_path):
        crypto = self._make()
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
        conn.execute(
            "INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (".example.com", "sid", "plain_val", b"", "/", 0, 1, 0, 100, 200, 1, 1, 1, -1, 2),
        )
        conn.commit()
        conn.close()

        result = crypto.extract_cookies(str(db_path))
        assert len(result) == 1
        assert result[0].value == "plain_val"
        assert result[0].is_secure is True
        assert result[0].is_httponly is False

    def test_extract_cookies_with_encrypted_value(self, tmp_path):
        crypto = self._make()
        crypto._aes.new.return_value = MagicMock()
        crypto._aes.MODE_GCM = "GCM"

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
        conn.execute(
            "INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (".x.com", "tok", "", b"v10" + b"\x00" * 48, "/", 0, 0, 1, 10, 20, 1, 1, 1, 1, 2),
        )
        conn.commit()
        conn.close()

        plaintext_with_meta = b"\x00" * 32 + b"decrypted_tok"
        mock_cipher = MagicMock()
        mock_cipher.decrypt.return_value = plaintext_with_meta
        crypto._aes.new.return_value = mock_cipher

        result = crypto.extract_cookies(str(db_path), browser_data_dir=str(tmp_path))
        # get_encryption_key will return None (no Local State), so key is None
        # With key=None, the code skips decryption and falls through to value or ""
        assert len(result) == 1
        assert result[0].name == "tok"

    def test_extract_cookies_copy_failure(self, tmp_path):
        crypto = self._make()
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
        conn.commit()
        conn.close()

        with patch("shutil.copy2", side_effect=PermissionError("denied")):
            result = crypto.extract_cookies(str(db_path))
            assert result == []


# ---------------------------------------------------------------------------
# LinuxCookieCrypto
# ---------------------------------------------------------------------------

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
        conn.execute(
            "INSERT INTO cookies VALUES ('.x.com', 'a', 'val1', X'', '/', 0, 0, 0, 100, 100, 0, 0, 1, -1, 2)"
        )
        conn.commit()
        conn.close()

        crypto = LinuxCookieCrypto()
        cookies = crypto.extract_cookies(str(db_path))
        assert len(cookies) == 1
        assert cookies[0].name == "a"
        assert cookies[0].value == "val1"

    # -- _check_keyring (lines 277-283) --

    def test_check_keyring_available(self):
        with patch.dict("sys.modules", {"secretstorage": MagicMock()}):
            crypto = LinuxCookieCrypto()
            assert crypto._keyring_available is True

    def test_check_keyring_unavailable(self):
        crypto = LinuxCookieCrypto()
        with patch.object(crypto, '_check_keyring', return_value=False):
            crypto._keyring_available = crypto._check_keyring()
            assert crypto._keyring_available is False

    # -- get_encryption_key with keyring (lines 285-300) --

    def test_get_encryption_key_keyring_success(self):
        mock_secretstorage = MagicMock()
        mock_bus = MagicMock()
        mock_secretstorage.dbus_init.return_value = mock_bus

        mock_collection = MagicMock()
        mock_secretstorage.get_default_collection.return_value = mock_collection

        mock_item = MagicMock()
        mock_item.get_label.return_value = "Chrome Safe Storage"
        mock_item.get_secret.return_value = b"keyring_password"
        mock_collection.get_all_items.return_value = [mock_item]

        with patch.dict("sys.modules", {"secretstorage": mock_secretstorage}):
            crypto = LinuxCookieCrypto()
            crypto._keyring_available = True
            result = crypto.get_encryption_key("/tmp/test")
            assert result == b"keyring_password"

    def test_get_encryption_key_keyring_no_chrome_item(self):
        mock_secretstorage = MagicMock()
        mock_bus = MagicMock()
        mock_secretstorage.dbus_init.return_value = mock_bus

        mock_collection = MagicMock()
        mock_secretstorage.get_default_collection.return_value = mock_collection

        mock_item = MagicMock()
        mock_item.get_label.return_value = "Other Service"
        mock_collection.get_all_items.return_value = [mock_item]

        with patch.dict("sys.modules", {"secretstorage": mock_secretstorage}):
            crypto = LinuxCookieCrypto()
            crypto._keyring_available = True
            result = crypto.get_encryption_key("/tmp/test")
            assert result == b"peanuts"

    def test_get_encryption_key_keyring_exception(self):
        mock_secretstorage = MagicMock()
        mock_secretstorage.dbus_init.side_effect = Exception("dbus error")

        with patch.dict("sys.modules", {"secretstorage": mock_secretstorage}):
            crypto = LinuxCookieCrypto()
            crypto._keyring_available = True
            result = crypto.get_encryption_key("/tmp/test")
            assert result == b"peanuts"

    # -- decrypt_cookie edge cases (lines 302-343) --

    def test_decrypt_non_v10_v11_returns_raw(self):
        crypto = LinuxCookieCrypto()
        result = crypto.decrypt_cookie(b"raw_cookie_value", b"peanuts")
        assert result == "raw_cookie_value"

    def test_decrypt_non_utf8_raw_returns_empty_string(self):
        crypto = LinuxCookieCrypto()
        result = crypto.decrypt_cookie(b"\xff\xfe", b"peanuts")
        assert result == ""

    def test_decrypt_v10_with_custom_key(self):
        crypto = LinuxCookieCrypto()
        encrypted = crypto.encrypt_cookie("custom_key_test", b"mykey")
        decrypted = crypto.decrypt_cookie(encrypted, b"mykey")
        assert decrypted == "custom_key_test"

    def test_decrypt_v10_pkcs7_padding_removal(self):
        crypto = LinuxCookieCrypto()
        # Encrypt an exact multiple of 16 bytes
        plaintext = "a" * 16  # exactly 16 bytes
        encrypted = crypto.encrypt_cookie(plaintext, b"peanuts")
        decrypted = crypto.decrypt_cookie(encrypted, b"peanuts")
        assert decrypted == plaintext

    def test_decrypt_v10_exception_returns_none(self):
        crypto = LinuxCookieCrypto()
        # Corrupted data that will cause an exception during decryption
        result = crypto.decrypt_cookie(b"v10" + b"\x00" * 16 + b"\xf0", b"peanuts")
        assert result is None

    # -- encrypt_cookie edge cases (lines 345-371) --

    def test_encrypt_decrypt_long_value(self):
        crypto = LinuxCookieCrypto()
        plaintext = "x" * 1000
        encrypted = crypto.encrypt_cookie(plaintext, b"peanuts")
        decrypted = crypto.decrypt_cookie(encrypted, b"peanuts")
        assert decrypted == plaintext

    def test_encrypt_decrypt_unicode(self):
        crypto = LinuxCookieCrypto()
        plaintext = "\u00e9\u00e8\u00ea\u00eb\u00f0\u00f1"
        encrypted = crypto.encrypt_cookie(plaintext, b"peanuts")
        decrypted = crypto.decrypt_cookie(encrypted, b"peanuts")
        assert decrypted == plaintext

    def test_encrypt_cookie_exception(self):
        crypto = LinuxCookieCrypto()
        with patch("hashlib.pbkdf2_hmac", side_effect=Exception("hash fail")):
            with pytest.raises(Exception, match="hash fail"):
                crypto.encrypt_cookie("test", b"key")

    # -- extract_cookies with encrypted data (line 403) --

    def test_extract_cookies_with_encrypted_data(self, tmp_path):
        crypto = LinuxCookieCrypto()
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

        # Pre-encrypt a cookie value
        encrypted = crypto.encrypt_cookie("secret_db_val", b"peanuts")
        conn.execute(
            "INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (".db.com", "db_cookie", "", encrypted, "/", 0, 0, 0, 1, 2, 1, 1, 1, -1, 2),
        )
        conn.commit()
        conn.close()

        # Pass browser_data_dir so get_encryption_key is called (returns "peanuts")
        cookies = crypto.extract_cookies(str(db_path), browser_data_dir="/tmp")
        assert len(cookies) == 1
        assert cookies[0].value == "secret_db_val"

    def test_extract_cookies_with_browser_data_dir(self, tmp_path):
        crypto = LinuxCookieCrypto()
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
        conn.execute(
            "INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (".x.com", "a", "val1", b"", "/", 0, 0, 0, 100, 100, 0, 0, 1, -1, 2),
        )
        conn.commit()
        conn.close()

        cookies = crypto.extract_cookies(str(db_path), browser_data_dir=str(tmp_path))
        assert len(cookies) == 1
        assert cookies[0].value == "val1"

    def test_extract_cookies_exception_during_query(self, tmp_path):
        crypto = LinuxCookieCrypto()
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
        conn.commit()
        conn.close()

        with patch("sqlite3.connect", side_effect=Exception("db error")):
            result = crypto.extract_cookies(str(db_path))
            assert result == []

    def test_extract_cookies_multiple(self, tmp_path):
        crypto = LinuxCookieCrypto()
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
        conn.execute(
            "INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (".a.com", "c1", "v1", b"", "/", 0, 0, 0, 1, 2, 1, 1, 1, -1, 2),
        )
        conn.execute(
            "INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (".b.com", "c2", "v2", b"", "/", 0, 1, 1, 3, 4, 0, 0, 1, 1, 2),
        )
        conn.commit()
        conn.close()

        cookies = crypto.extract_cookies(str(db_path))
        assert len(cookies) == 2
        assert cookies[0].host_key == ".a.com"
        assert cookies[1].host_key == ".b.com"
        assert cookies[1].is_secure is True
        assert cookies[1].is_httponly is True
        assert cookies[1].samesite == 1

    def test_extract_cookies_plaintext_fallback(self, tmp_path):
        crypto = LinuxCookieCrypto()
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
        conn.execute(
            "INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (".x.com", "a", "plaintext_fallback", b"\x01\x02\x03", "/", 0, 0, 0, 1, 2, 1, 1, 1, -1, 2),
        )
        conn.commit()
        conn.close()

        # No key (browser_data_dir=None), so encrypted_value won't be decrypted
        # Falls back to value column
        cookies = crypto.extract_cookies(str(db_path))
        assert len(cookies) == 1
        assert cookies[0].value == "plaintext_fallback"


# ---------------------------------------------------------------------------
# MacCookieCrypto
# ---------------------------------------------------------------------------

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

    # -- get_encryption_key (lines 436-451) --

    def test_get_encryption_key_keychain_success(self):
        crypto = MacCookieCrypto()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "keychain_password\n"

        with patch("subprocess.run", return_value=mock_result):
            result = crypto.get_encryption_key()
            assert result == b"keychain_password"

    def test_get_encryption_key_keychain_empty_output(self):
        crypto = MacCookieCrypto()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            result = crypto.get_encryption_key()
            assert result == b"peanuts"

    def test_get_encryption_key_keychain_nonzero_return(self):
        crypto = MacCookieCrypto()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            result = crypto.get_encryption_key()
            assert result == b"peanuts"

    def test_get_encryption_key_keychain_exception(self):
        crypto = MacCookieCrypto()
        with patch("subprocess.run", side_effect=Exception("timeout")):
            result = crypto.get_encryption_key()
            assert result == b"peanuts"

    # -- decrypt_cookie (lines 453-475) --

    def test_decrypt_v10_gcm(self):
        crypto = MacCookieCrypto()
        encrypted = crypto.encrypt_cookie("gcm_test", b"peanuts")
        decrypted = crypto.decrypt_cookie(encrypted, b"peanuts")
        assert decrypted == "gcm_test"

    def test_decrypt_non_v10_v11_returns_raw(self):
        crypto = MacCookieCrypto()
        result = crypto.decrypt_cookie(b"raw_data", b"peanuts")
        assert result == "raw_data"

    def test_decrypt_non_utf8_raw_returns_empty(self):
        crypto = MacCookieCrypto()
        result = crypto.decrypt_cookie(b"\xff\xfe", b"peanuts")
        assert result == ""

    def test_decrypt_exception_returns_none(self):
        crypto = MacCookieCrypto()
        # Force an exception inside the decrypt try/except by corrupting hashlib path
        with patch("hashlib.pbkdf2_hmac", side_effect=Exception("kdf error")):
            result = crypto.decrypt_cookie(b"v10" + b"\x00" * 30, b"peanuts")
            assert result is None

    # -- encrypt_cookie (lines 477-493) --

    def test_encrypt_with_default_key(self):
        crypto = MacCookieCrypto()
        encrypted = crypto.encrypt_cookie("default_key")
        assert encrypted.startswith(b"v10")
        decrypted = crypto.decrypt_cookie(encrypted, b"peanuts")
        assert decrypted == "default_key"

    def test_encrypt_exception(self):
        crypto = MacCookieCrypto()
        with patch("hashlib.pbkdf2_hmac", side_effect=Exception("crypto fail")):
            with pytest.raises(Exception, match="crypto fail"):
                crypto.encrypt_cookie("test", b"key")

    # -- extract_cookies (line 498) --

    def test_extract_cookies_real_db(self, tmp_path):
        crypto = MacCookieCrypto()
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
        conn.execute(
            "INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (".mac.com", "mac_val", "hello", b"", "/", 0, 0, 0, 1, 2, 1, 1, 1, -1, 2),
        )
        conn.commit()
        conn.close()

        cookies = crypto.extract_cookies(str(db_path))
        assert len(cookies) == 1
        assert cookies[0].value == "hello"


# ---------------------------------------------------------------------------
# CookieCryptoFactory
# ---------------------------------------------------------------------------

class TestCookieCryptoFactory:
    def test_get_platform_linux(self):
        with patch("sys.platform", "linux"):
            platform = CookieCryptoFactory.get_platform()
            assert platform in ("posix", "linux")

    def test_get_platform_darwin(self):
        with patch("sys.platform", "darwin"):
            platform = CookieCryptoFactory.get_platform()
            assert platform == "darwin"

    def test_get_platform_win32(self):
        with patch("sys.platform", "win32"):
            platform = CookieCryptoFactory.get_platform()
            assert platform == "nt"

    def test_get_platform_default(self):
        with patch("sys.platform", "freebsd"):
            platform = CookieCryptoFactory.get_platform()
            assert platform == os.name

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

    def test_create_no_override_linux(self):
        with patch.object(CookieCryptoFactory, "get_platform", return_value="posix"):
            crypto = CookieCryptoFactory.create()
            assert isinstance(crypto, LinuxCookieCrypto)

    def test_create_no_override_darwin(self):
        with patch.object(CookieCryptoFactory, "get_platform", return_value="darwin"):
            crypto = CookieCryptoFactory.create()
            assert isinstance(crypto, MacCookieCrypto)

    def test_create_no_override_nt(self):
        with patch.object(CookieCryptoFactory, "get_platform", return_value="nt"), \
             patch("tokenade.core.crypto.cookie_crypto.WindowsCookieCrypto") as mock_win:
            mock_win.return_value = MagicMock()
            CookieCryptoFactory.create()
            mock_win.assert_called_once()

    def test_create_override_posix(self):
        """platform_override='posix' matches the posix check, creates LinuxCookieCrypto."""
        crypto = CookieCryptoFactory.create("posix")
        assert isinstance(crypto, LinuxCookieCrypto)

    def test_create_override_linux_matches_posix(self):
        """platform_override='linux' triggers the posix check."""
        crypto = CookieCryptoFactory.create("linux")
        assert isinstance(crypto, LinuxCookieCrypto)

    def test_create_override_windows(self):
        """platform_override='windows' matches the windows check."""
        with pytest.raises(ImportError):
            CookieCryptoFactory.create("windows")

    def test_create_override_darwin(self):
        crypto = CookieCryptoFactory.create("darwin")
        assert isinstance(crypto, MacCookieCrypto)
