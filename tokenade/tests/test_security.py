"""
Unit tests for security/credentials module.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tokenade.core.security.credentials import (  # noqa: E402
    AccountCredentials,
    CredentialManager,
    SecureSessionStorage,
)


class TestAccountCredentials(unittest.TestCase):
    """Test AccountCredentials dataclass."""

    def test_creation(self):
        """Test basic creation."""
        acc = AccountCredentials(
            number=1,
            email="test@example.com",
            password="secret123",
        )
        self.assertEqual(acc.number, 1)
        self.assertEqual(acc.email, "test@example.com")
        self.assertEqual(acc.password, "secret123")
        self.assertEqual(acc.site, "google")  # default
        self.assertEqual(acc.profile_dir, "")  # default

    def test_to_dict(self):
        """Test serialization to dict."""
        acc = AccountCredentials(
            number=1,
            email="test@example.com",
            password="secret123",
            profile_dir="browser_data/1",
            site="github",
            metadata={"2fa": True},
        )
        # Default: password excluded
        data = acc.to_dict()
        self.assertEqual(data["number"], 1)
        self.assertEqual(data["email"], "test@example.com")
        self.assertNotIn("password", data)
        self.assertEqual(data["site"], "github")
        self.assertEqual(data["metadata"], {"2fa": True})

        # With include_password=True
        data_with_pw = acc.to_dict(include_password=True)
        self.assertEqual(data_with_pw["password"], "secret123")

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "number": 2,
            "email": "user@test.com",
            "password": "pass",
            "profile_dir": "browser_data/2",
            "site": "google",
            "metadata": {},
        }
        acc = AccountCredentials.from_dict(data)
        self.assertEqual(acc.number, 2)
        self.assertEqual(acc.email, "user@test.com")
        self.assertEqual(acc.password, "pass")

    def test_from_dict_defaults(self):
        """Test from_dict with missing optional fields."""
        data = {
            "number": 1,
            "email": "test@test.com",
            "password": "pass",
        }
        acc = AccountCredentials.from_dict(data)
        self.assertEqual(acc.profile_dir, "")
        self.assertEqual(acc.site, "google")
        self.assertEqual(acc.metadata, {})


class TestCredentialManager(unittest.TestCase):
    """Test CredentialManager with mocked keyring."""

    def setUp(self):
        """Create temporary directory for tests."""
        self.test_dir = tempfile.mkdtemp()
        self.accounts_file = Path(self.test_dir) / "test_accounts.json"
        self.manager = CredentialManager(
            app_name="test_app",
            accounts_file=str(self.accounts_file),
        )

    def tearDown(self):
        """Clean up temporary files."""
        if self.accounts_file.exists():
            self.accounts_file.unlink()
        os.rmdir(self.test_dir)

    @patch.object(CredentialManager, "_check_keyring", return_value=True)
    def test_keyring_available(self, mock_check):
        """Test keyring detection when available."""
        manager = CredentialManager(accounts_file=str(self.accounts_file))
        self.assertTrue(manager._keyring_available)

    @patch.object(CredentialManager, "_check_keyring", return_value=False)
    def test_keyring_unavailable(self, mock_check):
        """Test keyring detection when unavailable."""
        manager = CredentialManager(accounts_file=str(self.accounts_file))
        self.assertFalse(manager._keyring_available)

    @patch.object(CredentialManager, "_check_keyring", return_value=False)
    def test_save_and_load_plaintext(self, mock_check):
        """Test saving and loading accounts without keyring."""
        manager = CredentialManager(accounts_file=str(self.accounts_file))

        accounts = [
            AccountCredentials(1, "user1@test.com", "pass1"),
            AccountCredentials(2, "user2@test.com", "pass2"),
        ]
        manager.save_accounts(accounts, use_keyring=False)

        loaded = manager.load_accounts()
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].email, "user1@test.com")
        self.assertEqual(loaded[0].password, "pass1")

    @patch.object(CredentialManager, "_check_keyring", return_value=True)
    @patch.object(CredentialManager, "_set_keyring_password", return_value=True)
    def test_save_with_keyring(self, mock_set, mock_check):
        """Test saving passwords to keyring."""
        manager = CredentialManager(accounts_file=str(self.accounts_file))

        accounts = [AccountCredentials(1, "user@test.com", "secret")]
        manager.save_accounts(accounts, use_keyring=True)

        mock_set.assert_called_once_with("user@test.com", "secret")

    @patch.object(CredentialManager, "_check_keyring", return_value=True)
    @patch.object(CredentialManager, "_get_keyring_password", return_value="from_keyring")
    @patch.object(CredentialManager, "_set_keyring_password", return_value=True)
    def test_load_with_keyring_password(self, mock_set, mock_get, mock_check):
        """Test loading password from keyring."""
        manager = CredentialManager(accounts_file=str(self.accounts_file))

        # Save with empty password (keyring stores it)
        accounts = [AccountCredentials(1, "user@test.com", "")]
        manager.save_accounts(accounts, use_keyring=True)

        # Load should get password from keyring
        loaded = manager.load_accounts()
        self.assertEqual(loaded[0].password, "from_keyring")
        mock_get.assert_called_with("user@test.com")

    def test_encrypt_decrypt(self):
        """Test AES encryption and decryption."""
        manager = CredentialManager(accounts_file=str(self.accounts_file))
        plaintext = '{"test": "data"}'
        password = "master_password"

        encrypted = manager._encrypt_data(plaintext, password)
        self.assertNotEqual(encrypted, plaintext)

        decrypted = manager._decrypt_data(encrypted, password)
        self.assertEqual(decrypted, plaintext)

    def test_encrypt_decrypt_wrong_password(self):
        """Test decryption with wrong password fails."""
        manager = CredentialManager(accounts_file=str(self.accounts_file))
        plaintext = '{"test": "data"}'

        encrypted = manager._encrypt_data(plaintext, "correct_password")

        with self.assertRaises(Exception):
            manager._decrypt_data(encrypted, "wrong_password")

    def test_save_and_load_encrypted(self):
        """Test encrypted file storage."""
        manager = CredentialManager(accounts_file=str(self.accounts_file))
        accounts = [AccountCredentials(1, "user@test.com", "pass")]

        manager.save_accounts(accounts, encrypt_file=True, master_password="secret")

        # Verify file is encrypted
        with open(self.accounts_file, "r") as f:
            data = json.load(f)
        self.assertIn("encrypted", data)
        self.assertEqual(data["version"], 2)

        # Load with correct password
        loaded = manager.load_accounts(master_password="secret")
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].email, "user@test.com")

    def test_load_encrypted_without_password(self):
        """Test loading encrypted file without password raises error."""
        manager = CredentialManager(accounts_file=str(self.accounts_file))
        accounts = [AccountCredentials(1, "user@test.com", "pass")]

        manager.save_accounts(accounts, encrypt_file=True, master_password="secret")

        with self.assertRaises(ValueError) as ctx:
            manager.load_accounts()
        self.assertIn("Master password required", str(ctx.exception))

    def test_add_account(self):
        """Test adding a new account."""
        manager = CredentialManager(accounts_file=str(self.accounts_file))

        acc = manager.add_account("new@test.com", "password123", use_keyring=False)

        self.assertEqual(acc.number, 1)
        self.assertEqual(acc.email, "new@test.com")
        self.assertEqual(acc.password, "password123")
        self.assertEqual(acc.profile_dir, "browser_data/1")

    def test_add_account_auto_numbering(self):
        """Test auto-numbering when adding accounts."""
        manager = CredentialManager(accounts_file=str(self.accounts_file))

        acc1 = manager.add_account("user1@test.com", "pass1", use_keyring=False)
        acc2 = manager.add_account("user2@test.com", "pass2", use_keyring=False)

        self.assertEqual(acc1.number, 1)
        self.assertEqual(acc2.number, 2)

    def test_remove_account(self):
        """Test removing an account."""
        manager = CredentialManager(accounts_file=str(self.accounts_file))

        manager.add_account("user1@test.com", "pass1", use_keyring=False)
        manager.add_account("user2@test.com", "pass2", use_keyring=False)

        result = manager.remove_account(1)
        self.assertTrue(result)

        accounts = manager.load_accounts()
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].number, 1)  # Renumbered
        self.assertEqual(accounts[0].email, "user2@test.com")

    def test_remove_nonexistent_account(self):
        """Test removing non-existent account returns False."""
        manager = CredentialManager(accounts_file=str(self.accounts_file))
        result = manager.remove_account(999)
        self.assertFalse(result)

    def test_get_account(self):
        """Test getting account by number."""
        manager = CredentialManager(accounts_file=str(self.accounts_file))
        manager.add_account("user@test.com", "pass", use_keyring=False)

        acc = manager.get_account(1)
        self.assertIsNotNone(acc)
        self.assertEqual(acc.email, "user@test.com")

    def test_get_nonexistent_account(self):
        """Test getting non-existent account returns None."""
        manager = CredentialManager(accounts_file=str(self.accounts_file))
        acc = manager.get_account(999)
        self.assertIsNone(acc)

    def test_migrate_from_plaintext(self):
        """Test migrating from plaintext to secure storage."""
        # Create plaintext accounts file
        plaintext_data = [
            {"number": 1, "email": "user@test.com", "password": "pass"},
        ]
        with open(self.accounts_file, "w") as f:
            json.dump(plaintext_data, f)

        manager = CredentialManager(accounts_file=str(self.accounts_file))
        result = manager.migrate_from_plaintext()

        self.assertTrue(result)

        # Verify file is now encrypted or keyring-backed
        with open(self.accounts_file, "r") as f:
            data = json.load(f)
        # Should be list (keyring mode) or dict (encrypted)
        self.assertTrue(isinstance(data, list) or isinstance(data, dict))

    def test_migrate_already_encrypted(self):
        """Test migrating already encrypted file."""
        manager = CredentialManager(accounts_file=str(self.accounts_file))
        accounts = [AccountCredentials(1, "user@test.com", "pass")]
        manager.save_accounts(accounts, encrypt_file=True, master_password="secret")

        result = manager.migrate_from_plaintext()
        self.assertTrue(result)  # Already secure, returns True

    def test_migrate_no_file(self):
        """Test migrating when file doesn't exist."""
        manager = CredentialManager(accounts_file="/nonexistent/accounts.json")
        result = manager.migrate_from_plaintext()
        self.assertFalse(result)


class TestSecureSessionStorage(unittest.TestCase):
    """Test SecureSessionStorage encryption."""

    def setUp(self):
        """Create temporary directory."""
        self.test_dir = tempfile.mkdtemp()
        self.storage = SecureSessionStorage(sessions_dir=self.test_dir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_save_and_load_session(self):
        """Test saving and loading encrypted session."""
        session_data = {
            "cookies": [{"name": "session", "value": "abc"}],
            "tokens": [{"type": "oauth", "value": "token123"}],
        }
        password = "session_password"

        filepath = self.storage.save_session(session_data, "test_session.json", password)
        self.assertTrue(filepath.exists())

        loaded = self.storage.load_session("test_session.json", password)
        self.assertEqual(loaded["cookies"], session_data["cookies"])
        self.assertEqual(loaded["tokens"], session_data["tokens"])

    def test_load_wrong_password(self):
        """Test loading with wrong password fails."""
        session_data = {"test": "data"}
        self.storage.save_session(session_data, "test.json", "correct")

        with self.assertRaises(Exception):
            self.storage.load_session("test.json", "wrong")

    def test_sessions_dir_created(self):
        """Test sessions directory is created if missing."""
        new_dir = os.path.join(self.test_dir, "new_sessions")
        SecureSessionStorage(sessions_dir=new_dir)
        self.assertTrue(os.path.exists(new_dir))


if __name__ == "__main__":
    unittest.main()
