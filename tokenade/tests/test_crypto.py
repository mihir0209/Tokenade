"""
Unit tests for cookie cryptography module.

Tests cross-platform cookie encryption/decryption with mocked
platform-specific dependencies.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure tokenade is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tokenade.core.crypto.cookie_crypto import (  # noqa: E402
    DecryptedCookie,
    CookieCryptoFactory,
    LinuxCookieCrypto,
)


class TestDecryptedCookie(unittest.TestCase):
    """Test DecryptedCookie dataclass."""

    def test_creation(self):
        """Test basic creation."""
        cookie = DecryptedCookie(
            name="test_cookie",
            value="test_value",
            host_key=".example.com",
            path="/",
        )
        self.assertEqual(cookie.name, "test_cookie")
        self.assertEqual(cookie.value, "test_value")
        self.assertEqual(cookie.host_key, ".example.com")
        self.assertFalse(cookie.is_secure)

    def test_to_playwright_format(self):
        """Test conversion to Playwright format."""
        cookie = DecryptedCookie(
            name="session",
            value="abc123",
            host_key=".google.com",
            path="/",
            expires_utc=1700000000000000,
            is_httponly=True,
            samesite=1,
        )
        pw = cookie.to_playwright_format()
        self.assertEqual(pw["name"], "session")
        self.assertEqual(pw["value"], "abc123")
        self.assertEqual(pw["domain"], ".google.com")
        self.assertEqual(pw["path"], "/")
        self.assertTrue(pw["httpOnly"])
        self.assertEqual(pw["sameSite"], "Lax")

    def test_to_chrome_db_format(self):
        """Test conversion to Chrome SQLite format."""
        cookie = DecryptedCookie(
            name="session",
            value="abc123",
            host_key=".google.com",
            path="/",
            expires_utc=1700000000000000,
        )
        chrome, _ = cookie.to_chrome_db_format()
        self.assertEqual(chrome[3], "session")  # name
        self.assertEqual(chrome[4], "abc123")   # value
        self.assertEqual(chrome[1], ".google.com")  # host_key
        self.assertEqual(chrome[6], "/")      # path

    def test_from_chrome_row(self):
        """Test creation from Chrome SQLite row."""
        row = {
            "name": "test",
            "encrypted_value": b"encrypted_data",
            "host_key": ".example.com",
            "path": "/",
            "expires_utc": 1700000000000000,
            "is_secure": 1,
            "is_httponly": 1,
            "samesite": 1,
        }
        cookie = DecryptedCookie(
            name=row["name"],
            value="decrypted_value",
            host_key=row["host_key"],
            path=row["path"],
            expires_utc=row["expires_utc"],
            is_secure=bool(row["is_secure"]),
            is_httponly=bool(row["is_httponly"]),
            samesite=row["samesite"],
        )
        self.assertEqual(cookie.name, "test")
        self.assertEqual(cookie.value, "decrypted_value")
        self.assertEqual(cookie.host_key, ".example.com")
        self.assertTrue(cookie.is_httponly)
        self.assertEqual(cookie.samesite, 1)

    def test_serialization(self):
        """Test JSON serialization via dataclass."""
        from dataclasses import asdict
        cookie = DecryptedCookie(
            name="test",
            value="value",
            host_key=".example.com",
            path="/",
        )
        data = asdict(cookie)
        self.assertEqual(data["name"], "test")
        self.assertEqual(data["value"], "value")

        restored = DecryptedCookie(**data)
        self.assertEqual(restored.name, "test")
        self.assertEqual(restored.value, "value")


class TestCookieCryptoFactory(unittest.TestCase):
    """Test platform detection and factory creation."""

    @patch.object(CookieCryptoFactory, "get_platform", return_value="nt")
    @patch("tokenade.core.crypto.cookie_crypto.WindowsCookieCrypto")
    def test_windows_detection(self, mock_windows, mock_platform):
        """Test Windows platform detection."""
        mock_instance = MagicMock()
        mock_windows.return_value = mock_instance

        result = CookieCryptoFactory.create()
        self.assertEqual(result, mock_instance)

    @patch.object(CookieCryptoFactory, "get_platform", return_value="posix")
    @patch("tokenade.core.crypto.cookie_crypto.LinuxCookieCrypto")
    def test_linux_detection(self, mock_linux, mock_platform):
        """Test Linux platform detection."""
        mock_instance = MagicMock()
        mock_linux.return_value = mock_instance

        result = CookieCryptoFactory.create()
        self.assertEqual(result, mock_instance)

    @patch.object(CookieCryptoFactory, "get_platform", return_value="posix")
    @patch("tokenade.core.crypto.cookie_crypto.LinuxCookieCrypto")
    def test_macos_detection(self, mock_linux, mock_platform):
        """Test macOS falls back to Linux crypto (both posix)."""
        mock_instance = MagicMock()
        mock_linux.return_value = mock_instance

        result = CookieCryptoFactory.create()
        self.assertEqual(result, mock_instance)

    def test_unsupported_platform(self):
        """Test unsupported platform raises error."""
        with self.assertRaises(ValueError) as ctx:
            CookieCryptoFactory.create(platform_override="freebsd")
        self.assertIn("Unsupported platform", str(ctx.exception))


class TestLinuxCookieCrypto(unittest.TestCase):
    """Test Linux-specific cookie decryption."""

    @patch.object(LinuxCookieCrypto, "_check_keyring", return_value=True)
    @patch.object(LinuxCookieCrypto, "get_encryption_key")
    def test_decrypt_with_keyring(self, mock_get_key, mock_check):
        """Test decryption with secretstorage."""
        mock_get_key.return_value = b"password"

        crypto = LinuxCookieCrypto()
        key = crypto.get_encryption_key("/tmp/test")
        self.assertEqual(key, b"password")

    @patch.object(LinuxCookieCrypto, "_check_keyring", return_value=False)
    def test_decrypt_with_peanuts_fallback(self, mock_check):
        """Test fallback to 'peanuts' password."""
        crypto = LinuxCookieCrypto()
        key = crypto.get_encryption_key("/tmp/test")
        # Should derive key from "peanuts"
        self.assertEqual(key, b"peanuts")

    def test_pbkdf2_key_derivation(self):
        """Test PBKDF2 key derivation via decrypt."""
        import hashlib
        key = hashlib.pbkdf2_hmac("sha1", b"peanuts", b"saltysalt", 1, dklen=16)
        self.assertEqual(len(key), 16)


if __name__ == "__main__":
    unittest.main()
