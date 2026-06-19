import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch


class TestCredentialsCoverage(unittest.TestCase):
    def test_check_keyring_unavailable(self):
        mock_keyring = MagicMock()
        mock_keyring.get_keyring.side_effect = RuntimeError("no keyring")
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            from tokenade.core.security.credentials import CredentialManager

            with tempfile.TemporaryDirectory() as tmpdir:
                mgr = CredentialManager(
                    accounts_file=os.path.join(tmpdir, "acc.json")
                )
                self.assertFalse(mgr._keyring_available)

    def test_get_keyring_password_exception(self):
        mock_keyring = MagicMock()
        mock_keyring.get_password.side_effect = RuntimeError("fail")
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            from tokenade.core.security.credentials import CredentialManager

            with tempfile.TemporaryDirectory() as tmpdir:
                mgr = CredentialManager(
                    accounts_file=os.path.join(tmpdir, "acc.json")
                )
                mgr._keyring_available = True
                result = mgr._get_keyring_password("test@example.com")
                self.assertIsNone(result)

    def test_set_keyring_password_exception(self):
        mock_keyring = MagicMock()
        mock_keyring.set_password.side_effect = RuntimeError("fail")
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            from tokenade.core.security.credentials import CredentialManager

            with tempfile.TemporaryDirectory() as tmpdir:
                mgr = CredentialManager(
                    accounts_file=os.path.join(tmpdir, "acc.json")
                )
                mgr._keyring_available = True
                result = mgr._set_keyring_password("test@example.com", "pass")
                self.assertFalse(result)

    def test_migration_exception(self):
        from tokenade.core.security.credentials import CredentialManager

        with tempfile.TemporaryDirectory() as tmpdir:
            acc_path = os.path.join(tmpdir, "acc.json")
            with open(acc_path, "w") as f:
                json.dump(
                    [{"number": 1, "email": "a@b.com", "password": "p"}], f
                )
            mgr = CredentialManager(accounts_file=acc_path)
            with patch.object(
                mgr, "save_accounts", side_effect=RuntimeError("disk full")
            ):
                result = mgr.migrate_from_plaintext()
                self.assertFalse(result)
