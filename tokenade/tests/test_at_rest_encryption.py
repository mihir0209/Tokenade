"""Tests for Phase 40: Transparent Encryption at Rest."""
import json
import tempfile
import shutil
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_session():
    return {
        "site_name": "gmail",
        "cookies": [
            {"name": "SID", "value": "abc123", "domain": ".google.com"},
            {"name": "HSID", "value": "xyz789", "domain": ".google.com"},
        ],
        "local_storage": {"key1": "value1"},
        "session_storage": {},
        "metadata": {"cookie_count": 2},
    }


class TestIsEncryptedFile:
    """Test encrypted file detection."""

    def test_detects_encrypted_file(self, tmp_dir):
        from tokenade.core.crypto.encryptor import TokenadeEncryptor

        encryptor = TokenadeEncryptor()
        encrypted = encryptor.encrypt(b"test data", "password123")
        fpath = tmp_dir / "test.tokenade"
        fpath.write_bytes(encrypted)

        from tokenade.core.crypto.at_rest import is_encrypted_file
        assert is_encrypted_file(str(fpath))

    def test_detects_plaintext_file(self, tmp_dir):
        fpath = tmp_dir / "test.tokenade"
        fpath.write_text('{"site_name": "test"}')

        from tokenade.core.crypto.at_rest import is_encrypted_file
        assert not is_encrypted_file(str(fpath))

    def test_nonexistent_file(self, tmp_dir):
        from tokenade.core.crypto.at_rest import is_encrypted_file
        assert not is_encrypted_file(str(tmp_dir / "nonexistent.tokenade"))

    def test_empty_file(self, tmp_dir):
        fpath = tmp_dir / "empty.tokenade"
        fpath.write_bytes(b"")

        from tokenade.core.crypto.at_rest import is_encrypted_file
        assert not is_encrypted_file(str(fpath))


class TestEncryptDecryptRoundTrip:
    """Test encrypt/decrypt round trip for session data."""

    def test_round_trip(self, sample_session):
        from tokenade.core.crypto.at_rest import encrypt_session_data, decrypt_session_data

        encrypted = encrypt_session_data(sample_session, "my_password")
        decrypted = decrypt_session_data(encrypted, "my_password")

        assert decrypted["site_name"] == "gmail"
        assert len(decrypted["cookies"]) == 2
        assert decrypted["cookies"][0]["name"] == "SID"

    def test_wrong_password_fails(self, sample_session):
        from tokenade.core.crypto.at_rest import encrypt_session_data, decrypt_session_data

        encrypted = encrypt_session_data(sample_session, "correct_password")
        with pytest.raises(Exception):
            decrypt_session_data(encrypted, "wrong_password")

    def test_different_passwords_produce_different_ciphertext(self, sample_session):
        from tokenade.core.crypto.at_rest import encrypt_session_data

        enc1 = encrypt_session_data(sample_session, "password1")
        enc2 = encrypt_session_data(sample_session, "password2")
        assert enc1 != enc2


class TestSaveLoadEncrypted:
    """Test save/load encrypted session files."""

    def test_save_and_load(self, tmp_dir, sample_session):
        from tokenade.core.crypto.at_rest import save_encrypted, load_encrypted

        path = tmp_dir / "session.tokenade"
        save_encrypted(sample_session, str(path), password="test123")

        loaded = load_encrypted(str(path), password="test123")
        assert loaded["site_name"] == "gmail"
        assert len(loaded["cookies"]) == 2

    def test_save_creates_parent_dirs(self, tmp_dir, sample_session):
        from tokenade.core.crypto.at_rest import save_encrypted

        path = tmp_dir / "subdir" / "deep" / "session.tokenade"
        save_encrypted(sample_session, str(path), password="test123")
        assert path.exists()

    def test_save_no_password_raises(self, tmp_dir, sample_session):
        from tokenade.core.crypto.at_rest import save_encrypted

        path = tmp_dir / "session.tokenade"
        with pytest.raises(ValueError, match="No encryption password"):
            save_encrypted(sample_session, str(path))

    def test_load_no_password_raises(self, tmp_dir, sample_session):
        from tokenade.core.crypto.at_rest import save_encrypted, load_encrypted

        path = tmp_dir / "session.tokenade"
        save_encrypted(sample_session, str(path), password="test123")

        with pytest.raises(ValueError, match="No decryption password"):
            load_encrypted(str(path))

    def test_load_nonexistent_raises(self, tmp_dir):
        from tokenade.core.crypto.at_rest import load_encrypted

        with pytest.raises(FileNotFoundError):
            load_encrypted(str(tmp_dir / "nonexistent.tokenade"), password="test")

    def test_load_plaintext_fails(self, tmp_dir):
        from tokenade.core.crypto.at_rest import load_encrypted

        path = tmp_dir / "plain.tokenade"
        path.write_text('{"site_name": "test"}')

        with pytest.raises(Exception):
            load_encrypted(str(path), password="test")


class TestPasswordResolution:
    """Test password resolution from various sources."""

    def test_explicit_password(self):
        from tokenade.core.crypto.at_rest import get_encryption_password
        assert get_encryption_password(password="explicit") == "explicit"

    def test_key_file(self, tmp_dir):
        from tokenade.core.crypto.at_rest import get_encryption_password

        key_file = tmp_dir / "key.txt"
        key_file.write_text("from_keyfile")

        result = get_encryption_password(key_file=str(key_file))
        assert result == "from_keyfile"

    def test_env_variable(self, monkeypatch):
        from tokenade.core.crypto.at_rest import get_encryption_password
        monkeypatch.setenv("TOKENADE_PASSWORD", "env_pass")
        assert get_encryption_password() == "env_pass"

    def test_no_password_returns_none(self, monkeypatch):
        from tokenade.core.crypto.at_rest import get_encryption_password
        monkeypatch.delenv("TOKENADE_PASSWORD", raising=False)
        assert get_encryption_password() is None


class TestShouldEncrypt:
    """Test encryption config check."""

    def test_default_off(self, tmp_dir):
        from tokenade.core.crypto.at_rest import should_encrypt
        # Without config, should default to False
        assert not should_encrypt()


class TestSessionPackagerEncrypted:
    """Test SessionPackager with transparent encryption."""

    def test_save_load_round_trip(self, tmp_dir, sample_session, monkeypatch):
        from tokenade.core.importer.session_packager import SessionPackager

        monkeypatch.setenv("TOKENADE_PASSWORD", "test_pass")

        packager = SessionPackager()
        path = tmp_dir / "encrypted.tokenade"

        # Save with explicit encryption
        packager.save(sample_session, str(path), encrypt=True)

        # Verify file is encrypted
        from tokenade.core.crypto.at_rest import is_encrypted_file
        assert is_encrypted_file(str(path))

    def test_save_plaintext(self, tmp_dir, sample_session):
        from tokenade.core.importer.session_packager import SessionPackager

        packager = SessionPackager()
        path = tmp_dir / "plain.tokenade"

        packager.save(sample_session, str(path), encrypt=False)

        from tokenade.core.crypto.at_rest import is_encrypted_file
        assert not is_encrypted_file(str(path))

        loaded = packager.load(str(path))
        assert loaded["site_name"] == "gmail"
