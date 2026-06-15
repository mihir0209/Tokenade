"""Tests for encryptor round-trip and backward compatibility."""

import pytest
from tokenade.core.crypto.encryptor import (
    TokenadeEncryptor, MAGIC, VERSION, SALT_SIZE, NONCE_SIZE, HMAC_SIZE
)


class TestEncryptorRoundTrip:
    def test_basic_round_trip(self):
        enc = TokenadeEncryptor()
        data = b"Hello, World!"
        password = "test_password"
        encrypted = enc.encrypt(data, password)
        decrypted = enc.decrypt(encrypted, password)
        assert decrypted == data

    def test_empty_data(self):
        enc = TokenadeEncryptor()
        data = b""
        password = "test123"
        encrypted = enc.encrypt(data, password)
        decrypted = enc.decrypt(encrypted, password)
        assert decrypted == data

    def test_binary_data(self):
        enc = TokenadeEncryptor()
        data = bytes(range(256))
        password = "binary_test"
        encrypted = enc.encrypt(data, password)
        decrypted = enc.decrypt(encrypted, password)
        assert decrypted == data

    def test_large_data(self):
        enc = TokenadeEncryptor()
        data = b"x" * 100000
        password = "large_test"
        encrypted = enc.encrypt(data, password)
        decrypted = enc.decrypt(encrypted, password)
        assert decrypted == data

    def test_unicode_data(self):
        enc = TokenadeEncryptor()
        data = "Hello, World! 🌍".encode("utf-8")
        password = "unicode_test"
        encrypted = enc.encrypt(data, password)
        decrypted = enc.decrypt(encrypted, password)
        assert decrypted == data

    def test_wrong_password_fails(self):
        enc = TokenadeEncryptor()
        data = b"secret"
        encrypted = enc.encrypt(data, "correct_password")
        with pytest.raises(ValueError, match="Wrong password"):
            enc.decrypt(encrypted, "wrong_password")

    def test_format_header(self):
        enc = TokenadeEncryptor()
        encrypted = enc.encrypt(b"test", "pass")
        assert encrypted[:len(MAGIC)] == MAGIC
        import struct
        version = struct.unpack('>I', encrypted[len(MAGIC):len(MAGIC)+4])[0]
        assert version == VERSION

    def test_different_nonces(self):
        enc = TokenadeEncryptor()
        data = b"same data"
        password = "same_password"
        e1 = enc.encrypt(data, password)
        e2 = enc.encrypt(data, password)
        # Nonces should be different (random)
        assert e1 != e2
        # But both should decrypt
        assert enc.decrypt(e1, password) == data
        assert enc.decrypt(e2, password) == data

    def test_v1_backward_compatibility(self):
        """Test that v1 format (with HMAC) can still be decrypted."""
        from tokenade.core.crypto.encryptor import PBKDF2_ITERATIONS
        enc = TokenadeEncryptor()
        data = b"backward compat test"
        password = "compat_pass"

        # Manually create a v1 format file
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        import hmac as hmac_mod
        import hashlib
        import secrets
        import struct

        salt = secrets.token_bytes(SALT_SIZE)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITERATIONS)
        key = kdf.derive(password.encode('utf-8'))
        nonce = secrets.token_bytes(NONCE_SIZE)
        aesgcm = AESGCM(key)
        encrypted_data = aesgcm.encrypt(nonce, data, None)
        payload = nonce + encrypted_data
        h = hmac_mod.new(key, payload, hashlib.sha256)
        hmac_digest = h.digest()
        # v1 format: MAGIC + version(1) + salt + payload + HMAC
        v1_data = MAGIC + struct.pack('>I', 1) + salt + payload + hmac_digest

        decrypted = enc.decrypt(v1_data, password)
        assert decrypted == data

    def test_corrupted_data(self):
        enc = TokenadeEncryptor()
        encrypted = enc.encrypt(b"test", "pass")
        # Corrupt a byte in the middle
        corrupted = bytearray(encrypted)
        corrupted[len(MAGIC) + 10] ^= 0xFF
        with pytest.raises(ValueError, match="Wrong password|corrupted"):
            enc.decrypt(bytes(corrupted), "pass")

    def test_invalid_magic(self):
        enc = TokenadeEncryptor()
        with pytest.raises(ValueError, match="Invalid file format"):
            enc.decrypt(b"WRONGMAGIC" + b"\x00" * 50, "pass")

    def test_unsupported_version(self):
        enc = TokenadeEncryptor()
        import struct
        with pytest.raises(ValueError, match="Unsupported version"):
            enc.decrypt(MAGIC + struct.pack('>I', 99) + b"\x00" * 50, "pass")
