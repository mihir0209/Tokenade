"""
Tokenade Encryption - AES-256-GCM encryption for .tokenade files.

Provides secure encryption/decryption of session files using
PBKDF2 key derivation and AES-256-GCM authenticated encryption.
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# File format constants
MAGIC = b'TOKENADE_ENCRYPTED'
VERSION = 1
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
    
    File format:
    ┌─────────────────────────────────────────────────────┐
    │  TOKENADE_ENCRYPTED_v1                             │
    ├─────────────────────────────────────────────────────┤
    │  Salt (16 bytes)                                   │
    │  Nonce (12 bytes)                                  │
    │  Encrypted Data                                    │
    │  HMAC-SHA256 (32 bytes)                            │
    └─────────────────────────────────────────────────────┘
    
    Usage:
        encryptor = TokenadeEncryptor()
        
        # Encrypt
        encrypted = encryptor.encrypt(data, password)
        
        # Decrypt
        decrypted = encryptor.decrypt(encrypted, password)
    """
    
    def encrypt(self, data: bytes, password: str) -> bytes:
        """
        Encrypt data with password.
        
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
        
        # Encrypt with AES-GCM
        aesgcm = AESGCM(key)
        encrypted_data = aesgcm.encrypt(nonce, data, None)
        
        # Build encrypted payload
        payload = nonce + encrypted_data
        
        # Calculate HMAC
        h = hmac.new(key, payload, hashlib.sha256)
        hmac_digest = h.digest()
        
        # Build final output
        output = MAGIC + struct.pack('>I', VERSION) + salt + payload + hmac_digest
        
        return output
    
    def decrypt(self, encrypted: bytes, password: str) -> bytes:
        """
        Decrypt data with password.
        
        Args:
            encrypted: Encrypted data with header
            password: Decryption password
            
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
        
        version = struct.unpack('>I', encrypted[len(MAGIC):len(MAGIC)+4])[0]
        if version != VERSION:
            raise ValueError(f"Unsupported version: {version}")
        
        # Extract components
        offset = len(MAGIC) + 4
        salt = encrypted[offset:offset + SALT_SIZE]
        offset += SALT_SIZE
        
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
        
        # Verify HMAC
        h = hmac.new(key, payload, hashlib.sha256)
        if not hmac.compare_digest(h.digest(), stored_hmac):
            raise ValueError("Wrong password or corrupted data")
        
        # Extract nonce and ciphertext
        nonce = payload[:NONCE_SIZE]
        ciphertext = payload[NONCE_SIZE:]
        
        # Decrypt
        aesgcm = AESGCM(key)
        try:
            decrypted = aesgcm.decrypt(nonce, ciphertext, None)
        except Exception:
            raise ValueError("Wrong password or corrupted data")
        
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
        
        with open(output_path, 'wb') as f:
            f.write(encrypted)
        
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
        
        with open(output_path, 'wb') as f:
            f.write(decrypted)
        
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
