"""Tests for encryption and decryption edge cases."""

import pytest
from tokenade.core.crypto.encryptor import TokenadeEncryptor


class TestEncryptorEdgeCases:
    def test_many_encryptions_same_data(self):
        enc = TokenadeEncryptor()
        data = b"same"
        pw = "pass"
        results = [enc.encrypt(data, pw) for _ in range(5)]
        # All should decrypt correctly
        for r in results:
            assert enc.decrypt(r, pw) == data
        # All should be different (random nonces)
        assert len(set(results)) == 5

    def test_long_password(self):
        enc = TokenadeEncryptor()
        data = b"test"
        pw = "x" * 10000
        encrypted = enc.encrypt(data, pw)
        assert enc.decrypt(encrypted, pw) == data

    def test_special_chars_password(self):
        enc = TokenadeEncryptor()
        data = b"test"
        pw = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        encrypted = enc.encrypt(data, pw)
        assert enc.decrypt(encrypted, pw) == data

    def test_unicode_password(self):
        enc = TokenadeEncryptor()
        data = b"test"
        pw = "contraseña密码パスワード"
        encrypted = enc.encrypt(data, pw)
        assert enc.decrypt(encrypted, pw) == data

    def test_zero_length_data(self):
        enc = TokenadeEncryptor()
        encrypted = enc.encrypt(b"", "pass")
        assert enc.decrypt(encrypted, "pass") == b""

    def test_single_byte(self):
        enc = TokenadeEncryptor()
        encrypted = enc.encrypt(b"\x00", "pass")
        assert enc.decrypt(encrypted, "pass") == b"\x00"

    def test_max_size_data(self):
        enc = TokenadeEncryptor()
        data = b"\xff" * 1000000
        encrypted = enc.encrypt(data, "pass")
        assert enc.decrypt(encrypted, "pass") == data

    def test_truncated_ciphertext(self):
        enc = TokenadeEncryptor()
        encrypted = enc.encrypt(b"test", "pass")
        truncated = encrypted[:len(encrypted) // 2]
        with pytest.raises(ValueError):
            enc.decrypt(truncated, "pass")

    def test_empty_encrypted(self):
        enc = TokenadeEncryptor()
        with pytest.raises(ValueError):
            enc.decrypt(b"", "pass")
