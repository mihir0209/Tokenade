"""
Tokenade Encryption - AES-256-GCM encryption for .tokenade files.

Provides secure encryption/decryption of session files using
PBKDF2 key derivation and AES-256-GCM authenticated encryption.
"""

import hashlib
import hmac
import logging
import os
import secrets
import struct
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# File format constants
MAGIC = b'TOKENADE_ENCRYPTED'
VERSION = 2
SALT_SIZE = 16
NONCE_SIZE = 12
HMAC_SIZE = 32
KEY_SIZE = 32  # AES-256
PBKDF2_ITERATIONS = 600000


@dataclass
class EncryptionConfig:
    """Encryption configuration."""
    password: str
    iterations: int = PBKDF2_ITERATIONS
    key_file: Optional[str] = None


class TokenadeEncryptor:
    """
    Encrypts and decrypts .tokenade files using AES-256-GCM.

    File format (v2):
    ┌─────────────────────────────────────────────────────┐
    │  TOKENADE_ENCRYPTED_v1                             │
    ├─────────────────────────────────────────────────────┤
    │  Salt (16 bytes)                                   │
    │  Nonce (12 bytes)                                  │
    │  Encrypted Data + GCM Auth Tag (16 bytes)          │
    └─────────────────────────────────────────────────────┘

    v1 format (deprecated, still supported for decryption):
    Includes HMAC-SHA256 (32 bytes) at the end.
    """

    def encrypt(self, data: bytes, password: str) -> bytes:
        """
        Encrypt data with password.

        Uses AES-256-GCM (authentication via GCM tag, no redundant HMAC).

        Args:
            data: Data to encrypt
            password: Encryption password

        Returns:
            Encrypted data with header
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes

        # Generate salt and derive key
        salt = secrets.token_bytes(SALT_SIZE)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_SIZE,
            salt=salt,
            iterations=self.config.iterations if hasattr(self, 'config') else PBKDF2_ITERATIONS,
        )
        key = kdf.derive(password.encode('utf-8'))

        # Generate nonce
        nonce = secrets.token_bytes(NONCE_SIZE)

        # Encrypt with AES-GCM (GCM tag provides authentication)
        aesgcm = AESGCM(key)
        encrypted_data = aesgcm.encrypt(nonce, data, None)

        # Build output: MAGIC + version + salt + nonce + ciphertext
        # No HMAC — AES-GCM's authentication tag is sufficient
        output = MAGIC + struct.pack('>I', VERSION) + salt + nonce + encrypted_data

        return output

    def decrypt(self, encrypted: bytes, password: str) -> bytes:
        """
        Decrypt data with password.

        Supports both v1 (with HMAC) and v2 (no HMAC) formats.

        Args:
            encrypted: Encrypted data with header
            password: Encryption password

        Returns:
            Decrypted data

        Raises:
            ValueError: If password is wrong or data is corrupted
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes

        # Verify magic and version
        if encrypted[:len(MAGIC)] != MAGIC:
            raise ValueError("Invalid file format")

        version = struct.unpack('>I', encrypted[len(MAGIC):len(MAGIC) + 4])[0]
        if version not in (1, VERSION):
            raise ValueError(f"Unsupported version: {version}")

        # Extract components
        offset = len(MAGIC) + 4
        salt = encrypted[offset:offset + SALT_SIZE]
        offset += SALT_SIZE

        if version == 1:
            # v1 format: salt + payload + HMAC
            payload = encrypted[offset:-HMAC_SIZE]
            stored_hmac = encrypted[-HMAC_SIZE:]

            # Derive key
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=KEY_SIZE,
                salt=salt,
                iterations=self.config.iterations if hasattr(self, 'config') else PBKDF2_ITERATIONS,
            )
            key = kdf.derive(password.encode('utf-8'))

            # Verify HMAC (backward compat)
            h = hmac.new(key, payload, hashlib.sha256)
            if not hmac.compare_digest(h.digest(), stored_hmac):
                raise ValueError("Wrong password or corrupted data")

            nonce = payload[:NONCE_SIZE]
            ciphertext = payload[NONCE_SIZE:]
        else:
            # v2 format: salt + nonce + ciphertext (no HMAC)
            nonce = encrypted[offset:offset + NONCE_SIZE]
            offset += NONCE_SIZE
            ciphertext = encrypted[offset:]

            # Derive key
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=KEY_SIZE,
                salt=salt,
                iterations=self.config.iterations if hasattr(self, 'config') else PBKDF2_ITERATIONS,
            )
            key = kdf.derive(password.encode('utf-8'))

        # Decrypt (AES-GCM verifies authentication tag)
        aesgcm = AESGCM(key)
        try:
            decrypted = aesgcm.decrypt(nonce, ciphertext, None)
        except Exception as exc:
            from tokenade.core.errors import DecryptionError
            raise DecryptionError(
                "Wrong password or corrupted data",
                operation="decrypt",
            ) from exc

        return decrypted

    def encrypt_file(self, input_path: str, output_path: str, password: str) -> str:
        """
        Encrypt a file.

        Args:
            input_path: Path to file to encrypt
            output_path: Path to encrypted output
            password: Encryption password

        Returns:
            Path to encrypted file
        """
        with open(input_path, 'rb') as f:
            data = f.read()

        encrypted = self.encrypt(data, password)

        umask = os.umask(0o177)
        try:
            with open(output_path, 'wb') as f:
                f.write(encrypted)
        finally:
            os.umask(umask)

        logger.info(f"File encrypted: {input_path} -> {output_path}")
        return output_path

    def decrypt_file(self, input_path: str, output_path: str, password: str) -> str:
        """
        Decrypt a file.

        Args:
            input_path: Path to encrypted file
            output_path: Path to decrypted output
            password: Decryption password

        Returns:
            Path to decrypted file
        """
        with open(input_path, 'rb') as f:
            encrypted = f.read()

        decrypted = self.decrypt(encrypted, password)

        umask = os.umask(0o177)
        try:
            with open(output_path, 'wb') as f:
                f.write(decrypted)
        finally:
            os.umask(umask)

        logger.info(f"File decrypted: {input_path} -> {output_path}")
        return output_path

    def rekey(self, encrypted: bytes, old_password: str, new_password: str) -> bytes:
        """
        Change encryption password.

        Args:
            encrypted: Encrypted data
            old_password: Current password
            new_password: New password

        Returns:
            Re-encrypted data
        """
        # Decrypt with old password
        decrypted = self.decrypt(encrypted, old_password)

        # Re-encrypt with new password
        return self.encrypt(decrypted, new_password)


def encrypt_session(session_file: str, password: str, output: Optional[str] = None) -> str:
    """
    Convenience function to encrypt a session file.

    Args:
        session_file: Path to session file
        password: Encryption password
        output: Output path (optional)

    Returns:
        Path to encrypted file
    """
    if not output:
        output = session_file + '.encrypted'

    encryptor = TokenadeEncryptor()
    return encryptor.encrypt_file(session_file, output, password)


def decrypt_session(encrypted_file: str, password: str, output: Optional[str] = None) -> str:
    """
    Convenience function to decrypt a session file.

    Args:
        encrypted_file: Path to encrypted file
        password: Decryption password
        output: Output path (optional)

    Returns:
        Path to decrypted file
    """
    if not output:
        output = encrypted_file.replace('.encrypted', '')
        if output == encrypted_file:
            output = encrypted_file + '.decrypted'

    encryptor = TokenadeEncryptor()
    return encryptor.decrypt_file(encrypted_file, output, password)


def load_key_from_file(key_file: str) -> str:
    """
    Load password from key file.

    Args:
        key_file: Path to key file

    Returns:
        Password string
    """
    with open(key_file, 'r') as f:
        return f.read().strip()
