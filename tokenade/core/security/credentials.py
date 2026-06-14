"""
Secure Credential Manager - Encrypt and store account credentials.

Uses system keyring when available, with fallback to AES-encrypted
file storage using a master password.

Features:
- System keyring integration (Windows Credential Manager, macOS Keychain, Linux Secret Service)
- AES-256-GCM encrypted file fallback
- Master password derivation with PBKDF2
- Automatic platform detection
"""

import json
import logging
import os
from base64 import b64decode, b64encode
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AccountCredentials:
    """Secure account credential storage."""
    number: int
    email: str
    password: str
    profile_dir: str = ""
    site: str = "google"
    metadata: Dict = field(default_factory=dict)

    def to_dict(self, include_password: bool = False) -> Dict:
        data = {
            "number": self.number,
            "email": self.email,
            "profile_dir": self.profile_dir,
            "site": self.site,
            "metadata": self.metadata,
        }
        if include_password:
            data["password"] = self.password
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> "AccountCredentials":
        return cls(
            number=data["number"],
            email=data["email"],
            password=data.get("password", ""),
            profile_dir=data.get("profile_dir", ""),
            site=data.get("site", "google"),
            metadata=data.get("metadata", {}),
        )


class CredentialManager:
    """
    Secure credential storage with keyring integration.

    Priority:
    1. System keyring (most secure)
    2. AES-encrypted file (fallback)
    3. Plaintext file (legacy, warns user)
    """

    def __init__(self, app_name: str = "tokenade", accounts_file: str = "accounts.json"):
        self.app_name = app_name
        self.accounts_file = Path(accounts_file)
        self._keyring_available = self._check_keyring()

    def _check_keyring(self) -> bool:
        """Check if system keyring is available."""
        try:
            import keyring
            # Test if keyring is functional
            keyring.get_keyring()
            return True
        except Exception:
            logger.warning("System keyring not available, using encrypted file storage")
            return False

    def _get_keyring_password(self, username: str) -> Optional[str]:
        """Get password from system keyring."""
        if not self._keyring_available:
            return None
        try:
            import keyring
            return keyring.get_password(self.app_name, username)
        except Exception as e:
            logger.error(f"Keyring read failed: {e}")
            return None

    def _set_keyring_password(self, username: str, password: str) -> bool:
        """Store password in system keyring."""
        if not self._keyring_available:
            return False
        try:
            import keyring
            keyring.set_password(self.app_name, username, password)
            return True
        except Exception as e:
            logger.error(f"Keyring write failed: {e}")
            return False

    def _derive_key(self, master_password: str, salt: bytes) -> bytes:
        """Derive AES key from master password using PBKDF2."""
        from Crypto.Protocol.KDF import PBKDF2
        return PBKDF2(master_password, salt, dkLen=32, count=100000)

    def _encrypt_data(self, data: str, master_password: str) -> str:
        """Encrypt data with AES-256-GCM."""
        from Crypto.Cipher import AES
        from Crypto.Random import get_random_bytes

        salt = get_random_bytes(16)
        nonce = get_random_bytes(12)
        key = self._derive_key(master_password, salt)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(data.encode("utf-8"))

        # Store: salt + nonce + tag + ciphertext
        encrypted = salt + nonce + tag + ciphertext
        return b64encode(encrypted).decode("utf-8")

    def _decrypt_data(self, encrypted_data: str, master_password: str) -> str:
        """Decrypt AES-256-GCM encrypted data."""
        from Crypto.Cipher import AES

        data = b64decode(encrypted_data.encode("utf-8"))
        salt = data[:16]
        nonce = data[16:28]
        tag = data[28:44]
        ciphertext = data[44:]

        key = self._derive_key(master_password, salt)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)
        return plaintext.decode("utf-8")

    def load_accounts(self, master_password: Optional[str] = None) -> List[AccountCredentials]:
        """
        Load accounts from secure storage.

        Args:
            master_password: Required for encrypted file storage

        Returns:
            List of AccountCredentials
        """
        accounts = []

        if not self.accounts_file.exists():
            return accounts

        try:
            with open(self.accounts_file, "r") as f:
                data = json.load(f)

            # Check if encrypted
            if isinstance(data, dict) and "encrypted" in data:
                if not master_password:
                    raise ValueError("Master password required for encrypted accounts file")
                decrypted = self._decrypt_data(data["encrypted"], master_password)
                data = json.loads(decrypted)

            # Load accounts
            for acc_data in data:
                account = AccountCredentials.from_dict(acc_data)

                # Try to get password from keyring
                keyring_password = self._get_keyring_password(account.email)
                if keyring_password:
                    account.password = keyring_password

                accounts.append(account)

        except Exception as e:
            logger.error(f"Failed to load accounts: {e}")
            raise

        return accounts

    def save_accounts(
        self,
        accounts: List[AccountCredentials],
        use_keyring: bool = True,
        encrypt_file: bool = False,
        master_password: Optional[str] = None,
    ) -> None:
        """
        Save accounts to secure storage.

        Args:
            accounts: List of accounts to save
            use_keyring: Store passwords in system keyring
            encrypt_file: Encrypt the accounts file
            master_password: Required if encrypt_file=True
        """
        # Store passwords in keyring
        if use_keyring and self._keyring_available:
            for account in accounts:
                if account.password:
                    self._set_keyring_password(account.email, account.password)

        # Prepare data for storage
        storage_data = []
        for account in accounts:
            if use_keyring and self._keyring_available:
                acc_dict = account.to_dict(include_password=False)
                acc_dict["password"] = ""
            else:
                acc_dict = account.to_dict(include_password=True)
            storage_data.append(acc_dict)

        # Encrypt if requested
        if encrypt_file:
            if not master_password:
                raise ValueError("Master password required for encryption")
            encrypted = self._encrypt_data(json.dumps(storage_data), master_password)
            storage_data = {"encrypted": encrypted, "version": 2}

        # Save to file
        with open(self.accounts_file, "w") as f:
            json.dump(storage_data, f, indent=2)

        logger.info(f"Saved {len(accounts)} accounts to {self.accounts_file}")

    def add_account(
        self,
        email: str,
        password: str,
        profile_dir: str = "",
        site: str = "google",
        use_keyring: bool = True,
    ) -> AccountCredentials:
        """
        Add a new account.

        Args:
            email: Account email/username
            password: Account password
            profile_dir: Browser profile directory
            site: Site handler name
            use_keyring: Store password in keyring

        Returns:
            Created AccountCredentials
        """
        accounts = self.load_accounts()
        account_num = len(accounts) + 1

        if not profile_dir:
            profile_dir = f"browser_data/{account_num}"

        account = AccountCredentials(
            number=account_num,
            email=email,
            password=password,
            profile_dir=profile_dir,
            site=site,
        )

        accounts.append(account)
        self.save_accounts(accounts, use_keyring=use_keyring)

        return account

    def remove_account(self, account_number: int) -> bool:
        """Remove an account by number."""
        accounts = self.load_accounts()
        original_count = len(accounts)
        accounts = [a for a in accounts if a.number != account_number]

        if len(accounts) == original_count:
            return False

        # Renumber remaining accounts
        for i, account in enumerate(accounts, 1):
            account.number = i

        self.save_accounts(accounts)
        return True

    def get_account(self, account_number: int) -> Optional[AccountCredentials]:
        """Get account by number."""
        accounts = self.load_accounts()
        for account in accounts:
            if account.number == account_number:
                return account
        return None

    def migrate_from_plaintext(self, master_password: Optional[str] = None) -> bool:
        """
        Migrate from plaintext accounts.json to secure storage.

        Args:
            master_password: Optional password for file encryption

        Returns:
            True if migration successful
        """
        if not self.accounts_file.exists():
            return False

        try:
            with open(self.accounts_file, "r") as f:
                data = json.load(f)

            # Check if already encrypted
            if isinstance(data, dict) and "encrypted" in data:
                logger.info("Accounts file already encrypted")
                return True

            # Load as plaintext
            accounts = [AccountCredentials.from_dict(d) for d in data]

            # Save with security
            self.save_accounts(
                accounts,
                use_keyring=True,
                encrypt_file=master_password is not None,
                master_password=master_password,
            )

            logger.info("Migrated accounts to secure storage")
            return True

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False


class SecureSessionStorage:
    """
    Encrypt session files with AES-256-GCM.

    Uses a master password to encrypt/decrypt session data.
    """

    def __init__(self, sessions_dir: str = "sessions"):
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(exist_ok=True)

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive key from password."""
        from Crypto.Protocol.KDF import PBKDF2
        return PBKDF2(password, salt, dkLen=32, count=100000)

    def save_session(
        self,
        session_data: Dict,
        filename: str,
        password: str,
    ) -> Path:
        """
        Save encrypted session file.

        Args:
            session_data: Session dictionary
            filename: Output filename
            password: Encryption password

        Returns:
            Path to saved file
        """
        from Crypto.Cipher import AES
        from Crypto.Random import get_random_bytes

        salt = get_random_bytes(16)
        key = self._derive_key(password, salt)
        cipher = AES.new(key, AES.MODE_GCM)

        plaintext = json.dumps(session_data).encode("utf-8")
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)

        encrypted_data = {
            "salt": b64encode(salt).decode(),
            "nonce": b64encode(cipher.nonce).decode(),
            "tag": b64encode(tag).decode(),
            "ciphertext": b64encode(ciphertext).decode(),
        }

        filepath = self.sessions_dir / filename
        with open(filepath, "w") as f:
            json.dump(encrypted_data, f, indent=2)

        return filepath

    def load_session(self, filename: str, password: str) -> Dict:
        """
        Load and decrypt session file.

        Args:
            filename: Session filename
            password: Decryption password

        Returns:
            Decrypted session dictionary
        """
        from Crypto.Cipher import AES

        filepath = self.sessions_dir / filename
        with open(filepath, "r") as f:
            encrypted_data = json.load(f)

        salt = b64decode(encrypted_data["salt"])
        nonce = b64decode(encrypted_data["nonce"])
        tag = b64decode(encrypted_data["tag"])
        ciphertext = b64decode(encrypted_data["ciphertext"])

        key = self._derive_key(password, salt)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)

        return json.loads(plaintext.decode("utf-8"))
