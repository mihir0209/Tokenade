"""Tests for encryptor round-trip and backward compatibility."""

from pathlib import Path

import pytest
from tokenade.core.crypto.encryptor import (
    TokenadeEncryptor,
    EncryptionConfig,
    MAGIC,
    VERSION,
    SALT_SIZE,
    NONCE_SIZE,
    HMAC_SIZE,
    KEY_SIZE,
    PBKDF2_ITERATIONS,
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
        with pytest.raises(ValueError, match=r"^Wrong password or corrupted data$") as ei:
            enc.decrypt(encrypted, "wrong_password")
        # exact message — mutmut wraps with XX...XX otherwise survives
        assert str(ei.value) == "Wrong password or corrupted data"

    def test_format_header(self):
        enc = TokenadeEncryptor()
        encrypted = enc.encrypt(b"test", "pass")
        assert encrypted[:len(MAGIC)] == MAGIC
        import struct
        version = struct.unpack('>I', encrypted[len(MAGIC):len(MAGIC) + 4])[0]
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

    def test_v1_wrong_hmac_exact_message(self):
        """Kill exact-string mutants on the v1 HMAC failure path."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        import hmac as hmac_mod
        import hashlib
        import secrets
        import struct

        enc = TokenadeEncryptor()
        data = b"hmac-path"
        password = "pw"
        salt = secrets.token_bytes(SALT_SIZE)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITERATIONS)
        key = kdf.derive(password.encode("utf-8"))
        nonce = secrets.token_bytes(NONCE_SIZE)
        payload = nonce + AESGCM(key).encrypt(nonce, data, None)
        bad_hmac = b"\x00" * HMAC_SIZE
        v1_data = MAGIC + struct.pack(">I", 1) + salt + payload + bad_hmac
        with pytest.raises(ValueError, match=r"^Wrong password or corrupted data$") as ei:
            enc.decrypt(v1_data, password)
        assert str(ei.value) == "Wrong password or corrupted data"

    def test_v1_respects_config_iterations(self):
        """Kill hasattr(self, 'config') on the v1 decrypt branch."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        import hmac as hmac_mod
        import hashlib
        import secrets
        import struct

        iterations = 1500
        data = b"v1-config"
        password = "pw"
        salt = secrets.token_bytes(SALT_SIZE)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
        key = kdf.derive(password.encode("utf-8"))
        nonce = secrets.token_bytes(NONCE_SIZE)
        payload = nonce + AESGCM(key).encrypt(nonce, data, None)
        good_hmac = hmac_mod.new(key, payload, hashlib.sha256).digest()
        v1_data = MAGIC + struct.pack(">I", 1) + salt + payload + good_hmac

        enc = TokenadeEncryptor()
        enc.config = EncryptionConfig(password="unused", iterations=iterations)
        assert enc.decrypt(v1_data, password) == data

        bare = TokenadeEncryptor()
        with pytest.raises(ValueError):
            bare.decrypt(v1_data, password)

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
        with pytest.raises(ValueError, match=r"^Invalid file format$") as ei:
            enc.decrypt(b"WRONGMAGIC" + b"\x00" * 50, "pass")
        assert str(ei.value) == "Invalid file format"

    def test_unsupported_version(self):
        enc = TokenadeEncryptor()
        import struct
        with pytest.raises(ValueError, match=r"^Unsupported version: 99$") as ei:
            enc.decrypt(MAGIC + struct.pack('>I', 99) + b"\x00" * 50, "pass")
        assert str(ei.value) == "Unsupported version: 99"

    def test_format_constants_exact(self):
        assert MAGIC == b"TOKENADE_ENCRYPTED"
        assert VERSION == 2
        assert SALT_SIZE == 16
        assert NONCE_SIZE == 12
        assert HMAC_SIZE == 32
        assert KEY_SIZE == 32
        assert PBKDF2_ITERATIONS == 600_000

    def test_encrypted_blob_layout_uses_salt_and_nonce_sizes(self):
        enc = TokenadeEncryptor()
        blob = enc.encrypt(b"layout", "pw")
        # MAGIC + version(4) + salt + nonce + ciphertext+tag
        header = len(MAGIC) + 4 + SALT_SIZE + NONCE_SIZE
        assert len(blob) > header
        # GCM tag is 16 bytes minimum beyond nonce
        assert len(blob) >= header + 16

    def test_encryption_config_dataclass_defaults(self):
        cfg = EncryptionConfig(password="secret")
        assert cfg.password == "secret"
        assert cfg.iterations == PBKDF2_ITERATIONS
        assert cfg.iterations == 600_000
        assert cfg.key_file is None

    def test_encryptor_respects_config_iterations(self):
        """Kill hasattr(self, 'config') → 'XXconfigXX' mutants."""
        enc = TokenadeEncryptor()
        # low iterations for speed; still must derive differently than default
        enc.config = EncryptionConfig(password="unused", iterations=1000)
        data = b"iter-sensitive"
        password = "pw"
        encrypted = enc.encrypt(data, password)
        # decrypt with same config still works
        assert enc.decrypt(encrypted, password) == data
        # decrypt without config (default 600k iterations) must fail
        bare = TokenadeEncryptor()
        with pytest.raises(ValueError):
            bare.decrypt(encrypted, password)

    def test_rekey_round_trip(self):
        enc = TokenadeEncryptor()
        data = b"rekey-me"
        encrypted = enc.encrypt(data, "old-pass")
        rekeyed = enc.rekey(encrypted, "old-pass", "new-pass")
        assert enc.decrypt(rekeyed, "new-pass") == data
        with pytest.raises(ValueError):
            enc.decrypt(rekeyed, "old-pass")

    def test_encrypt_decrypt_file_and_session_helpers(self, tmp_path):
        from tokenade.core.crypto.encryptor import (
            encrypt_session,
            decrypt_session,
            load_key_from_file,
        )

        plain = tmp_path / "sess.json"
        plain.write_bytes(b'{"cookies":[]}')
        key_file = tmp_path / "key.txt"
        key_file.write_text("file-password\n")
        password = load_key_from_file(str(key_file))
        assert password == "file-password"

        enc_path = encrypt_session(str(plain), password)
        assert enc_path.endswith(".encrypted")
        out = decrypt_session(enc_path, password)
        assert Path(out).read_bytes() == b'{"cookies":[]}'

    def test_decrypt_error_operation_exact(self):
        from tokenade.core.errors import DecryptionError

        enc = TokenadeEncryptor()
        encrypted = enc.encrypt(b"secret", "right")
        with pytest.raises(DecryptionError) as ei:
            enc.decrypt(encrypted, "wrong")
        assert ei.value.operation == "decrypt"

    def test_encrypt_file_permissions_and_log(self, tmp_path, caplog):
        import logging
        import stat

        enc = TokenadeEncryptor()
        src = tmp_path / "in.bin"
        dst = tmp_path / "out.enc"
        src.write_bytes(b"data")
        with caplog.at_level(logging.INFO, logger="tokenade.core.crypto.encryptor"):
            enc.encrypt_file(str(src), str(dst), "pw")
        mode = stat.S_IMODE(dst.stat().st_mode)
        assert mode == 0o600
        assert any(
            r.getMessage() == f"File encrypted: {src} -> {dst}" for r in caplog.records
        )

    def test_decrypt_file_log_message_and_permissions(self, tmp_path, caplog):
        import logging
        import stat

        enc = TokenadeEncryptor()
        src = tmp_path / "in.bin"
        enc_path = tmp_path / "out.enc"
        plain_out = tmp_path / "plain.bin"
        src.write_bytes(b"payload")
        enc.encrypt_file(str(src), str(enc_path), "pw")
        with caplog.at_level(logging.INFO, logger="tokenade.core.crypto.encryptor"):
            enc.decrypt_file(str(enc_path), str(plain_out), "pw")
        assert plain_out.read_bytes() == b"payload"
        assert stat.S_IMODE(plain_out.stat().st_mode) == 0o600
        assert any(
            r.getMessage() == f"File decrypted: {enc_path} -> {plain_out}"
            for r in caplog.records
        )

    def test_decrypt_session_default_output_paths(self, tmp_path):
        from tokenade.core.crypto.encryptor import encrypt_session, decrypt_session

        plain = tmp_path / "session.json"
        plain.write_bytes(b"abc")
        enc_path = encrypt_session(str(plain), "pw")
        assert enc_path == str(plain) + ".encrypted"
        # strips .encrypted suffix
        out = decrypt_session(enc_path, "pw")
        assert out == str(plain)
        assert Path(out).read_bytes() == b"abc"

        # no .encrypted in name → appends .decrypted
        odd = tmp_path / "blob.bin"
        TokenadeEncryptor().encrypt_file(str(plain), str(odd), "pw")
        out2 = decrypt_session(str(odd), "pw")
        assert out2 == str(odd) + ".decrypted"
        assert Path(out2).read_bytes() == b"abc"
