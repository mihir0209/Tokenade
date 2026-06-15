"""
Cookie Cryptography - Cross-platform cookie encryption/decryption.

Handles:
- Windows: DPAPI + AES-256-GCM (Chrome v80+)
- Linux: libsecret/keyring or "peanuts" fallback
- macOS: Keychain
"""

import os
import json
import base64
import sqlite3
import shutil
import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class DecryptedCookie:
    """Standardized cookie representation after decryption."""
    name: str
    value: str
    host_key: str
    path: str
    expires_utc: int = 0
    is_secure: bool = False
    is_httponly: bool = False
    creation_utc: int = 0
    last_access_utc: int = 0
    has_expires: bool = True
    is_persistent: bool = True
    priority: int = 1
    samesite: int = -1
    source_scheme: int = 2
    source_port: int = 443
    
    def to_playwright_format(self) -> Dict:
        """Convert to Playwright cookie format."""
        cookie = {
            "name": self.name,
            "value": self.value,
            "domain": self.host_key,
            "path": self.path,
        }
        if self.is_secure:
            cookie["secure"] = True
        if self.is_httponly:
            cookie["httpOnly"] = True
        
        # Convert Chrome time to Unix timestamp for expires
        if self.expires_utc > 0:
            chrome_epoch_offset = 11644473600
            expires = int((self.expires_utc / 1000000) - chrome_epoch_offset)
            if expires > 0:
                cookie["expires"] = expires
        
        # SameSite mapping
        if self.samesite == 1:
            cookie["sameSite"] = "Lax"
        elif self.samesite == 2:
            cookie["sameSite"] = "Strict"
        elif self.is_secure:
            cookie["sameSite"] = "None"
        
        return cookie
    
    def to_chrome_db_format(self) -> Tuple[Tuple, Dict]:
        """Convert to Chrome database format."""
        return (
            self.creation_utc,
            self.host_key,
            self.host_key,  # top_frame_site_key
            self.name,
            self.value,  # plain text for Linux
            b"",  # encrypted_value
            self.path,
            self.expires_utc,
            1 if self.is_secure else 0,
            1 if self.is_httponly else 0,
            self.last_access_utc,
            1 if self.has_expires else 0,
            1 if self.is_persistent else 0,
            self.priority,
            self.samesite,
            self.source_scheme,
            self.source_port,
            self.creation_utc,  # last_update_utc
            0,  # source_type
            0,  # has_cross_site_ancestor
        ), {}


class CookieCrypto(ABC):
    """Abstract base for platform-specific cookie cryptography."""
    
    @abstractmethod
    def get_encryption_key(self, browser_data_dir: str) -> Optional[bytes]:
        """Get the encryption key for this platform."""
        pass
    
    @abstractmethod
    def decrypt_cookie(self, encrypted_value: bytes, key: Optional[bytes] = None) -> Optional[str]:
        """Decrypt a single cookie value."""
        pass
    
    @abstractmethod
    def encrypt_cookie(self, plaintext: str, key: Optional[bytes] = None) -> bytes:
        """Encrypt a cookie value for this platform."""
        pass
    
    @abstractmethod
    def extract_cookies(self, cookies_db_path: str, browser_data_dir: Optional[str] = None) -> List[DecryptedCookie]:
        """Extract and decrypt all cookies from database."""
        pass


class WindowsCookieCrypto(CookieCrypto):
    """Windows DPAPI + AES-256-GCM cookie decryption."""
    
    def __init__(self):
        self._dpapi = None
        self._aes = None
        self._ensure_imports()
    
    def _ensure_imports(self):
        """Lazy import Windows-specific modules."""
        try:
            import win32crypt
            from Crypto.Cipher import AES
            self._dpapi = win32crypt
            self._aes = AES
        except ImportError:
            logger.error("Windows crypto requires: pip install pywin32 pycryptodome")
            raise
    
    def get_encryption_key(self, browser_data_dir: str) -> Optional[bytes]:
        """Get Chrome's encryption key from Local State file."""
        local_state_path = os.path.join(browser_data_dir, "Local State")
        
        if not os.path.exists(local_state_path):
            logger.warning(f"Local State not found: {local_state_path}")
            return None
        
        try:
            with open(local_state_path, "r", encoding="utf-8") as f:
                local_state = json.load(f)
            
            encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
            encrypted_key = encrypted_key[5:]  # Remove DPAPI prefix
            
            decrypted_key = self._dpapi.CryptUnprotectData(
                encrypted_key, None, None, None, 0
            )[1]
            
            return decrypted_key
            
        except Exception as e:
            logger.error(f"Failed to get encryption key: {e}")
            return None
    
    def decrypt_cookie(self, encrypted_value: bytes, key: Optional[bytes] = None) -> Optional[str]:
        """Decrypt Windows Chrome cookie (AES-256-GCM)."""
        if not encrypted_value:
            return ""
        
        try:
            version = encrypted_value[:3]
            
            if version in (b"v10", b"v11"):
                nonce = encrypted_value[3:15]
                ciphertext = encrypted_value[15:]
                
                cipher = self._aes.new(key, self._aes.MODE_GCM, nonce=nonce)
                decrypted = cipher.decrypt(ciphertext[:-16])
                
                # Skip first 32 bytes (metadata)
                decrypted = decrypted[32:]
                return decrypted.decode("utf-8")
            else:
                # Old DPAPI encryption
                decrypted = self._dpapi.CryptUnprotectData(
                    encrypted_value, None, None, None, 0
                )[1]
                return decrypted.decode("utf-8")
                
        except Exception as e:
            logger.warning(f"Decryption failed: {e}")
            return None
    
    def encrypt_cookie(self, plaintext: str, key: Optional[bytes] = None) -> bytes:
        """Encrypt for Windows (not typically needed for our use case)."""
        raise NotImplementedError("Windows encryption not implemented - use native Chrome")
    
    def extract_cookies(self, cookies_db_path: str, browser_data_dir: Optional[str] = None) -> List[DecryptedCookie]:
        """Extract all cookies from Windows Chrome database."""
        if not os.path.exists(cookies_db_path):
            logger.error(f"Cookie database not found: {cookies_db_path}")
            return []
        
        key = self.get_encryption_key(browser_data_dir) if browser_data_dir else None
        
        # Copy database (Chrome locks it)
        temp_db = cookies_db_path + ".temp"
        try:
            shutil.copy2(cookies_db_path, temp_db)
        except Exception as e:
            logger.error(f"Cannot copy database: {e}")
            return []
        
        cookies = []
        try:
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT host_key, name, value, encrypted_value, path,
                       expires_utc, is_secure, is_httponly, creation_utc,
                       last_access_utc, has_expires, is_persistent, priority,
                       samesite, source_scheme
                FROM cookies
                ORDER BY host_key, name
            """)
            
            for row in cursor.fetchall():
                (host_key, name, value, encrypted_value, path,
                 expires_utc, is_secure, is_httponly, creation_utc,
                 last_access_utc, has_expires, is_persistent, priority,
                 samesite, source_scheme) = row
                
                decrypted_value = None
                if encrypted_value and key:
                    decrypted_value = self.decrypt_cookie(encrypted_value, key)
                
                if decrypted_value is None:
                    decrypted_value = value or ""
                
                cookies.append(DecryptedCookie(
                    name=name,
                    value=decrypted_value,
                    host_key=host_key,
                    path=path,
                    expires_utc=expires_utc,
                    is_secure=bool(is_secure),
                    is_httponly=bool(is_httponly),
                    creation_utc=creation_utc,
                    last_access_utc=last_access_utc,
                    has_expires=bool(has_expires),
                    is_persistent=bool(is_persistent),
                    priority=priority,
                    samesite=samesite,
                    source_scheme=source_scheme,
                ))
            
            conn.close()
            
        finally:
            if os.path.exists(temp_db):
                os.remove(temp_db)
        
        logger.info(f"Extracted {len(cookies)} cookies from {cookies_db_path}")
        return cookies


class LinuxCookieCrypto(CookieCrypto):
    """Linux cookie handling - uses plain text or system keyring."""
    
    def __init__(self):
        self._keyring_available = self._check_keyring()
    
    def _check_keyring(self) -> bool:
        """Check if system keyring is available."""
        try:
            import secretstorage
            return True
        except ImportError:
            return False
    
    def get_encryption_key(self, browser_data_dir: str) -> Optional[bytes]:
        """Get Linux Chrome encryption key."""
        if self._keyring_available:
            try:
                import secretstorage
                bus = secretstorage.dbus_init()
                collection = secretstorage.get_default_collection(bus)
                for item in collection.get_all_items():
                    if item.get_label() == "Chrome Safe Storage":
                        return item.get_secret()
            except Exception as e:
                logger.debug(f"Keyring access failed: {e}")
        
        # Fallback to "peanuts" key
        logger.debug("Using fallback 'peanuts' key")
        return b"peanuts"
    
    def decrypt_cookie(self, encrypted_value: bytes, key: Optional[bytes] = None) -> Optional[str]:
        """Decrypt Linux Chrome cookie."""
        if not encrypted_value:
            return ""
        
        try:
            from Crypto.Cipher import AES
            import hashlib
            
            version = encrypted_value[:3]
            if version in (b"v10", b"v11"):
                nonce = encrypted_value[3:15]
                ciphertext = encrypted_value[15:]
                
                # Derive key using PBKDF2
                key_material = hashlib.pbkdf2_hmac(
                    "sha1", key or b"peanuts", b"saltysalt", 1, dklen=16
                )
                
                cipher = AES.new(key_material, AES.MODE_GCM, nonce=nonce)
                decrypted = cipher.decrypt(ciphertext[:-16])
                return decrypted.decode("utf-8")
            else:
                return encrypted_value.decode("utf-8", errors="ignore")
                
        except Exception as e:
            logger.warning(f"Linux decryption failed: {e}")
            return None
    
    def encrypt_cookie(self, plaintext: str, key: Optional[bytes] = None) -> bytes:
        """Encrypt cookie for Linux Chrome."""
        try:
            from Crypto.Cipher import AES
            from Crypto.Random import get_random_bytes
            import hashlib
            
            key_material = hashlib.pbkdf2_hmac(
                "sha1", key or b"peanuts", b"saltysalt", 1, dklen=16
            )
            
            nonce = get_random_bytes(12)
            cipher = AES.new(key_material, AES.MODE_GCM, nonce=nonce)
            ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))
            
            return b"v10" + nonce + ciphertext + tag
            
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise
    
    def extract_cookies(self, cookies_db_path: str, browser_data_dir: Optional[str] = None) -> List[DecryptedCookie]:
        """Extract cookies from Linux Chrome database."""
        if not os.path.exists(cookies_db_path):
            logger.error(f"Cookie database not found: {cookies_db_path}")
            return []
        
        key = self.get_encryption_key(browser_data_dir) if browser_data_dir else None
        
        cookies = []
        try:
            conn = sqlite3.connect(cookies_db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT host_key, name, value, encrypted_value, path,
                       expires_utc, is_secure, is_httponly, creation_utc,
                       last_access_utc, has_expires, is_persistent, priority,
                       samesite, source_scheme
                FROM cookies
                ORDER BY host_key, name
            """)
            
            for row in cursor.fetchall():
                (host_key, name, value, encrypted_value, path,
                 expires_utc, is_secure, is_httponly, creation_utc,
                 last_access_utc, has_expires, is_persistent, priority,
                 samesite, source_scheme) = row
                
                decrypted_value = None
                if encrypted_value and key:
                    decrypted_value = self.decrypt_cookie(encrypted_value, key)
                
                if decrypted_value is None:
                    decrypted_value = value or ""
                
                cookies.append(DecryptedCookie(
                    name=name,
                    value=decrypted_value,
                    host_key=host_key,
                    path=path,
                    expires_utc=expires_utc,
                    is_secure=bool(is_secure),
                    is_httponly=bool(is_httponly),
                    creation_utc=creation_utc,
                    last_access_utc=last_access_utc,
                    has_expires=bool(has_expires),
                    is_persistent=bool(is_persistent),
                    priority=priority,
                    samesite=samesite,
                    source_scheme=source_scheme,
                ))
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to extract cookies: {e}")
        
        return cookies


class MacCookieCrypto(CookieCrypto):
    """macOS cookie handling - uses Keychain for encryption key."""

    def get_encryption_key(self, browser_data_dir: str = None) -> Optional[bytes]:
        """Get Chrome encryption key from macOS Keychain."""
        try:
            import subprocess
            result = subprocess.run(
                ["security", "find-generic-password", "-s", "Chrome Safe Storage", "-w"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().encode("utf-8")
        except Exception as e:
            logger.debug(f"macOS Keychain access failed: {e}")

        # Fallback: Chrome on macOS also uses "peanuts" as default
        logger.debug("Using fallback 'peanuts' key for macOS")
        return b"peanuts"

    def decrypt_cookie(self, encrypted_value: bytes, key: Optional[bytes] = None) -> Optional[str]:
        """Decrypt macOS Chrome cookie (same v10/v11 format as Linux)."""
        if not encrypted_value:
            return ""
        try:
            from Crypto.Cipher import AES
            import hashlib

            version = encrypted_value[:3]
            if version in (b"v10", b"v11"):
                nonce = encrypted_value[3:15]
                ciphertext = encrypted_value[15:]
                key_material = hashlib.pbkdf2_hmac(
                    "sha1", key or b"peanuts", b"saltysalt", 1, dklen=16
                )
                cipher = AES.new(key_material, AES.MODE_GCM, nonce=nonce)
                decrypted = cipher.decrypt(ciphertext[:-16])
                return decrypted.decode("utf-8")
            else:
                return encrypted_value.decode("utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"macOS decryption failed: {e}")
            return None

    def encrypt_cookie(self, plaintext: str, key: Optional[bytes] = None) -> bytes:
        """Encrypt cookie for macOS Chrome."""
        try:
            from Crypto.Cipher import AES
            from Crypto.Random import get_random_bytes
            import hashlib

            key_material = hashlib.pbkdf2_hmac(
                "sha1", key or b"peanuts", b"saltysalt", 1, dklen=16
            )
            nonce = get_random_bytes(12)
            cipher = AES.new(key_material, AES.MODE_GCM, nonce=nonce)
            ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))
            return b"v10" + nonce + ciphertext + tag
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise

    def extract_cookies(self, cookies_db_path: str, browser_data_dir: Optional[str] = None) -> List[DecryptedCookie]:
        """Extract cookies from macOS Chrome database."""
        # Reuse Linux implementation (same DB format)
        return LinuxCookieCrypto().extract_cookies(cookies_db_path, browser_data_dir)


class CookieCryptoFactory:
    """Factory for platform-specific cookie crypto."""
    
    @staticmethod
    def get_platform() -> str:
        """Detect current platform."""
        import sys
        if sys.platform == "darwin":
            return "darwin"
        elif sys.platform == "win32":
            return "nt"
        else:
            return os.name
    
    @classmethod
    def create(cls, platform_override: Optional[str] = None) -> CookieCrypto:
        """Create appropriate crypto handler."""
        platform = platform_override or cls.get_platform()
        
        if platform == "nt" or platform_override == "windows":
            return WindowsCookieCrypto()
        elif platform == "darwin" or platform_override == "darwin":
            return MacCookieCrypto()
        elif platform == "posix" or platform_override == "linux":
            return LinuxCookieCrypto()
        else:
            raise ValueError(f"Unsupported platform: {platform}")
