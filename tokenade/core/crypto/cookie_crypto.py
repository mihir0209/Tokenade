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
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
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

    @abstractmethod
    def decrypt_cookie(self, encrypted_value: bytes, key: Optional[bytes] = None) -> Optional[str]:
        """Decrypt a single cookie value."""

    @abstractmethod
    def encrypt_cookie(self, plaintext: str, key: Optional[bytes] = None) -> bytes:
        """Encrypt a cookie value for this platform."""

    @abstractmethod
    def extract_cookies(self, cookies_db_path: str, browser_data_dir: Optional[str] = None) -> List[DecryptedCookie]:
        """Extract and decrypt all cookies from database."""


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
    """Linux Chromium-family cookie crypto (Chrome / Brave / Edge / Chromium).

    On Linux, Chromium OSCrypt uses:
    - Prefix ``v10`` / ``v11``: AES-128-CBC, IV = 16 spaces (0x20)
    - PBKDF2-HMAC-SHA1(password, b"saltysalt", iterations=1, dkLen=16)
    - Password from libsecret or KWallet ("{Browser} Safe Storage")
    - Fallback password ``peanuts`` (and empty password for some legacy cookies)
    - Cookie DB v24+ prepends 32-byte domain integrity hash to plaintext
    """

    _SALT = b"saltysalt"
    _IV = b" " * 16
    _PBKDF2_ITERS = 1
    _KEY_LEN = 16

    # Map browser name → OSCrypt / KWallet folder names
    _BROWSER_CRYPT_NAMES = {
        "chrome": "Chrome",
        "brave": "Brave",
        "chromium": "Chromium",
        "edge": "Chromium",  # Edge Linux often uses Chromium store
        "msedge": "Chromium",
    }

    def __init__(self):
        self._keyring_available = self._check_keyring()

    def _check_keyring(self) -> bool:
        """Check if system keyring is available."""
        try:
            return True
        except ImportError:
            return False

    def _browser_crypt_name(self, browser: Optional[str] = None) -> str:
        b = (browser or "chrome").lower().strip()
        return self._BROWSER_CRYPT_NAMES.get(b, "Chrome")

    def _passwords_from_secretstorage(self, crypt_name: str) -> List[bytes]:
        out: List[bytes] = []
        if not self._keyring_available:
            return out
        try:
            import secretstorage

            bus = secretstorage.dbus_init()
            # Prefer attribute search (Chromium schema), then label scan
            labels_wanted = {
                f"{crypt_name} Safe Storage",
                f"{crypt_name} Keys/{crypt_name} Safe Storage",
                "Chrome Safe Storage",
                "Chrome Keys/Chrome Safe Storage",
                "Brave Safe Storage",
                "Chromium Safe Storage",
            }
            try:
                for schema in (
                    "chrome_libsecret_os_crypt_password_v2",
                    "chrome_libsecret_os_crypt_password_v1",
                ):
                    for item in secretstorage.search_items(
                        bus, {"xdg:schema": schema, "application": crypt_name.lower()}
                    ):
                        try:
                            sec = item.get_secret()
                            if isinstance(sec, (bytes, bytearray)) and sec:
                                out.append(bytes(sec))
                        except Exception:
                            continue
            except Exception as e:
                logger.debug(f"secretstorage schema search failed: {e}")

            for collection in secretstorage.get_all_collections(bus):
                try:
                    if collection.is_locked():
                        collection.unlock()
                except Exception:
                    pass
                try:
                    for item in collection.get_all_items():
                        try:
                            label = item.get_label() or ""
                            if label not in labels_wanted and "Safe Storage" not in label:
                                continue
                            # Prefer matching browser name when present
                            if crypt_name.lower() not in label.lower() and "chrome" not in label.lower():
                                # still accept any Safe Storage as candidate
                                if "Safe Storage" not in label:
                                    continue
                            sec = item.get_secret()
                            if isinstance(sec, (bytes, bytearray)) and sec:
                                out.append(bytes(sec))
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"secretstorage access failed: {e}")
        return out

    def _passwords_from_kwallet(self, crypt_name: str) -> List[bytes]:
        """Read OSCrypt password from KDE KWallet (Brave/Chrome on KDE).

        Uses jeepney when available (no dbus-python required), matching
        Chromium's folder layout: ``{Browser} Keys`` / ``{Browser} Safe Storage``.
        """
        out: List[bytes] = []
        folder = f"{crypt_name} Keys"
        entry = f"{crypt_name} Safe Storage"
        # 1) jeepney (preferred — same approach as browser-cookie3)
        try:
            import jeepney
            from jeepney.io.blocking import open_dbus_connection

            def _call(conn, addr, method, signature=None, *args):
                msg = jeepney.new_method_call(addr, method, signature, args)
                response = conn.send_and_get_reply(msg)
                if response.header.message_type == jeepney.MessageType.error:
                    raise RuntimeError(response.body[0] if response.body else "dbus error")
                return response.body[0] if len(response.body) == 1 else response.body

            for service, path in (
                ("org.kde.kwalletd6", "/modules/kwalletd6"),
                ("org.kde.kwalletd5", "/modules/kwalletd5"),
            ):
                try:
                    addr = jeepney.DBusAddress(
                        path, bus_name=service, interface="org.kde.KWallet"
                    )
                    with open_dbus_connection() as connection:
                        wallet_name = _call(connection, addr, "networkWallet")
                        handle = _call(
                            connection, addr, "open", "sxs", wallet_name, 0, "tokenade"
                        )
                        if int(handle) < 0:
                            continue
                        try:
                            has_folder = _call(
                                connection, addr, "hasFolder", "iss", handle, folder, "tokenade"
                            )
                            if not has_folder:
                                continue
                            password = _call(
                                connection,
                                addr,
                                "readPassword",
                                "isss",
                                handle,
                                folder,
                                entry,
                                "tokenade",
                            )
                            if password:
                                out.append(str(password).encode("utf-8"))
                        finally:
                            try:
                                _call(
                                    connection, addr, "close", "ibs", handle, False, "tokenade"
                                )
                            except Exception:
                                pass
                    if out:
                        return out
                except Exception as e:
                    logger.debug(f"KWallet jeepney via {service} failed: {e}")
        except Exception as e:
            logger.debug(f"KWallet jeepney unavailable: {e}")

        # 2) Optional dbus-python
        try:
            import dbus

            bus = dbus.SessionBus()
            proxy = bus.get_object("org.kde.kwalletd5", "/modules/kwalletd5")
            iface = dbus.Interface(proxy, "org.kde.KWallet")
            wid = iface.open("kdewallet", 0, "tokenade")
            if wid >= 0:
                try:
                    if iface.hasFolder(wid, folder, "tokenade"):
                        pw = iface.readPassword(wid, folder, entry, "tokenade")
                        if pw:
                            out.append(str(pw).encode("utf-8"))
                finally:
                    iface.close(wid, False, "tokenade")
        except Exception as e:
            logger.debug(f"KWallet dbus-python failed: {e}")
        return out

    def get_password_candidates(self, browser: Optional[str] = None) -> List[bytes]:
        """Return ordered OSCrypt password candidates for the browser."""
        crypt_name = self._browser_crypt_name(browser)
        candidates: List[bytes] = []
        seen = set()

        def add(pw: Optional[bytes]):
            if not pw:
                return
            if pw in seen:
                return
            seen.add(pw)
            candidates.append(pw)

        # Browser-specific first (Brave key is not Chrome's)
        try:
            for pw in self._passwords_from_kwallet(crypt_name):
                add(pw)
        except Exception as e:
            logger.debug(f"kwallet candidates failed: {e}")
        try:
            for pw in self._passwords_from_secretstorage(crypt_name):
                add(pw)
        except Exception as e:
            logger.debug(f"secretstorage candidates failed: {e}")
        # Cross-browser fallbacks (profile may be Chrome-derived)
        if crypt_name != "Chrome":
            try:
                for pw in self._passwords_from_kwallet("Chrome"):
                    add(pw)
            except Exception:
                pass
            try:
                for pw in self._passwords_from_secretstorage("Chrome"):
                    add(pw)
            except Exception:
                pass
        # Legacy defaults
        add(b"peanuts")
        add(b"")  # empty key — some older Linux cookies
        return candidates

    def get_encryption_key(
        self, browser_data_dir: str = "", browser: Optional[str] = None
    ) -> Optional[bytes]:
        """Get primary OSCrypt password for the browser (not the derived AES key)."""
        candidates = self.get_password_candidates(browser)
        # Prefer non-default passwords
        for pw in candidates:
            if pw not in (b"peanuts", b""):
                logger.debug(
                    "Using keyring/KWallet password for %s (%d bytes)",
                    self._browser_crypt_name(browser),
                    len(pw),
                )
                return pw
        logger.debug("Using fallback 'peanuts' key")
        return b"peanuts"

    def _derive_aes_key(self, password: bytes) -> bytes:
        import hashlib

        return hashlib.pbkdf2_hmac(
            "sha1", password, self._SALT, self._PBKDF2_ITERS, dklen=self._KEY_LEN
        )

    @staticmethod
    def _looks_like_text(s: str) -> bool:
        if not s:
            return True
        # Reject U+FFFD / control-heavy garbage from wrong-key decrypt
        if "\ufffd" in s:
            return False
        ctrl = sum(1 for ch in s if ord(ch) < 32 and ch not in "\t\n\r")
        return (ctrl / max(1, len(s))) < 0.1

    def _cbc_decrypt(self, ciphertext: bytes, aes_key: bytes) -> Optional[bytes]:
        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import unpad

            cipher = AES.new(aes_key, AES.MODE_CBC, self._IV)
            return unpad(cipher.decrypt(ciphertext), 16)
        except Exception:
            return None

    def _plaintext_to_value(self, decrypted: bytes) -> Optional[str]:
        """Strip optional 32-byte domain integrity prefix; return UTF-8 value.

        Modern Chromium cookie DBs (v24+) store a 32-byte domain hash before the
        value. The hash is high-entropy binary; if the first 32 bytes already look
        like plain text, treat the whole blob as the value (no strip).
        """
        if len(decrypted) > 32:
            head = decrypted[:32]
            # Domain integrity hash is not valid UTF-8 text
            try:
                head.decode("utf-8")
                head_is_text = self._looks_like_text(head.decode("utf-8"))
            except UnicodeDecodeError:
                head_is_text = False
            if not head_is_text:
                try:
                    stripped = decrypted[32:].decode("utf-8")
                    if self._looks_like_text(stripped) and stripped:
                        return stripped
                except UnicodeDecodeError:
                    pass
        try:
            text = decrypted.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return text if self._looks_like_text(text) else None

    def decrypt_cookie(self, encrypted_value: bytes, key: Optional[bytes] = None) -> Optional[str]:
        """Decrypt Linux Chromium cookie (v10/v11 AES-128-CBC).

        ``key`` is the OSCrypt *password* from keyring/KWallet (or peanuts),
        not the raw AES key.
        """
        if not encrypted_value:
            return ""

        try:
            version = encrypted_value[:3]
            if version in (b"v10", b"v11"):
                # Payload after version tag is pure CBC ciphertext (IV is fixed spaces)
                ciphertext = encrypted_value[3:]
                passwords: List[bytes] = []
                if key is not None:
                    passwords.append(key if isinstance(key, (bytes, bytearray)) else str(key).encode())
                # Always also try empty + peanuts when primary fails
                for extra in (b"", b"peanuts"):
                    if extra not in passwords:
                        passwords.append(extra)

                for pw in passwords:
                    aes_key = self._derive_aes_key(pw)
                    raw = self._cbc_decrypt(ciphertext, aes_key)
                    if raw is None:
                        continue
                    text = self._plaintext_to_value(raw)
                    if text is not None:
                        return text
                return None

            # Unencrypted / legacy plain blob
            try:
                text = encrypted_value.decode("utf-8")
                return text if self._looks_like_text(text) else None
            except UnicodeDecodeError:
                return None

        except Exception as e:
            logger.warning(f"Linux decryption failed: {e}")
            return None

    def decrypt_cookie_multi(
        self,
        encrypted_value: bytes,
        passwords: Optional[List[bytes]] = None,
        browser: Optional[str] = None,
    ) -> Optional[str]:
        """Try multiple OSCrypt passwords until one yields valid text."""
        if not encrypted_value:
            return ""
        if passwords is None:
            passwords = self.get_password_candidates(browser)
        for pw in passwords:
            result = self.decrypt_cookie(encrypted_value, pw)
            if result is not None:
                return result
        return None

    def encrypt_cookie(self, plaintext: str, key: Optional[bytes] = None) -> bytes:
        """Encrypt cookie for Linux Chrome (AES-128-CBC, v10 prefix).

        Format matches Chromium OSCrypt: ``v10`` + CBC(ciphertext) with fixed IV.
        """
        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import pad

            key_material = self._derive_aes_key(key or b"peanuts")
            plaintext_bytes = pad(plaintext.encode("utf-8"), 16)
            cipher = AES.new(key_material, AES.MODE_CBC, self._IV)
            ciphertext = cipher.encrypt(plaintext_bytes)
            return b"v10" + ciphertext

        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise

    def extract_cookies(
        self,
        cookies_db_path: str,
        browser_data_dir: Optional[str] = None,
        browser: Optional[str] = None,
    ) -> List[DecryptedCookie]:
        """Extract cookies from Linux Chrome/Brave database."""
        if not os.path.exists(cookies_db_path):
            logger.error(f"Cookie database not found: {cookies_db_path}")
            return []

        passwords = self.get_password_candidates(browser)
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
                if encrypted_value:
                    decrypted_value = self.decrypt_cookie_multi(encrypted_value, passwords, browser)

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
