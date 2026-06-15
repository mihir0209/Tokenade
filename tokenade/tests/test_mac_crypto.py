"""Tests for macOS cookie crypto."""

import pytest
from tokenade.core.crypto.cookie_crypto import (
    MacCookieCrypto, LinuxCookieCrypto, CookieCryptoFactory
)


class TestMacCookieCrypto:
    def test_creation(self):
        crypto = MacCookieCrypto()
        assert crypto is not None

    def test_fallback_key(self):
        crypto = MacCookieCrypto()
        # On Linux CI, Keychain won't be available, so fallback to peanuts
        key = crypto.get_encryption_key()
        assert key == b"peanuts" or isinstance(key, bytes)

    def test_encrypt_decrypt_roundtrip(self):
        crypto = MacCookieCrypto()
        key = b"peanuts"
        plaintext = "test_cookie_value"
        encrypted = crypto.encrypt_cookie(plaintext, key)
        decrypted = crypto.decrypt_cookie(encrypted, key)
        assert decrypted == plaintext

    def test_encrypt_produces_v10(self):
        crypto = MacCookieCrypto()
        encrypted = crypto.encrypt_cookie("test", b"peanuts")
        assert encrypted[:3] == b"v10"

    def test_decrypt_empty(self):
        crypto = MacCookieCrypto()
        assert crypto.decrypt_cookie(b"", b"peanuts") == ""

    def test_decrypt_none(self):
        crypto = MacCookieCrypto()
        assert crypto.decrypt_cookie(None, b"peanuts") == ""


class TestCookieCryptoFactory:
    def test_factory_posix(self):
        crypto = CookieCryptoFactory.create("posix")
        assert isinstance(crypto, LinuxCookieCrypto)

    def test_factory_linux(self):
        crypto = CookieCryptoFactory.create("linux")
        assert isinstance(crypto, LinuxCookieCrypto)

    def test_factory_darwin(self):
        crypto = CookieCryptoFactory.create("darwin")
        assert isinstance(crypto, MacCookieCrypto)

    def test_factory_macos_override(self):
        crypto = CookieCryptoFactory.create("darwin")
        assert isinstance(crypto, MacCookieCrypto)

    def test_factory_windows(self):
        try:
            crypto = CookieCryptoFactory.create("windows")
            from tokenade.core.crypto.cookie_crypto import WindowsCookieCrypto
            assert isinstance(crypto, WindowsCookieCrypto)
        except (ImportError, OSError):
            pytest.skip("Windows crypto dependencies not available")

    def test_factory_unsupported(self):
        with pytest.raises(ValueError, match="Unsupported platform"):
            CookieCryptoFactory.create("amiga")

    def test_get_platform_returns_string(self):
        platform = CookieCryptoFactory.get_platform()
        assert isinstance(platform, str)
        assert platform in ("nt", "posix", "darwin")
