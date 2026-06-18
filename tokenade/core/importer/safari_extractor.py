"""
Safari cookie extraction with Keychain decryption.

Extracts cookies from Safari on macOS, including encrypted cookies
that require Keychain access for decryption.
"""
import os
import sys
import struct
import subprocess
from pathlib import Path
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)

# Mac absolute time offset: seconds between 2001-01-01 and 1970-01-01
MAC_EPOCH_OFFSET = 978307200


class SafariExtractor:
    """Extract cookies from Safari on macOS."""

    # Default Safari cookie locations
    COOKIE_PATHS = [
        "~/Library/Cookies/Cookies.binarycookies",
        "~/Library/Safari/Cookies/Cookies.binarycookies",
    ]

    # Safari Technology Preview location
    TECH_PREVIEW_PATHS = [
        "~/Library/Safari Technology Preview/Cookies/Cookies.binarycookies",
    ]

    def __init__(self, profile_path: Optional[str] = None, tech_preview: bool = False):
        self._platform_check()
        self.tech_preview = tech_preview
        if profile_path is None:
            profile_path = os.path.expanduser(
                "~/Library/Cookies/Cookies.binarycookies"
            )
        self.profile_path = profile_path

    def _platform_check(self):
        """Ensure we're on macOS."""
        if sys.platform != "darwin":
            raise ImportError(
                "SafariExtractor is only supported on macOS. "
                f"Current platform: {sys.platform}"
            )

    def _find_cookies_file(self) -> Optional[Path]:
        """Find the Safari cookies file."""
        if self.profile_path:
            path = Path(self.profile_path)
            if path.exists():
                return path
            return None

        paths = self.TECH_PREVIEW_PATHS if self.tech_preview else self.COOKIE_PATHS
        for p in paths:
            expanded = Path(p).expanduser()
            if expanded.exists():
                return expanded
        return None

    def extract(self, site_filter=None) -> List[Dict]:
        """Extract cookies from Safari.

        Args:
            site_filter: Optional SiteFilter object or list of domain strings to filter by

        Returns:
            List of cookie dictionaries in standard format
        """
        cookies_file = self._find_cookies_file()
        if not cookies_file:
            logger.warning("Safari cookies file not found")
            return []

        try:
            raw_cookies = self._parse_binary_cookies(str(cookies_file))
        except Exception as e:
            logger.error(f"Failed to parse Safari cookies: {e}")
            return []

        # Apply site filter
        if site_filter:
            # Handle SiteFilter objects (backward compatibility)
            if hasattr(site_filter, 'filter_cookies'):
                return site_filter.filter_cookies(raw_cookies)
            # Handle list of domain strings
            filtered = []
            for cookie in raw_cookies:
                domain = cookie.get("domain", "")
                for site in site_filter:
                    if domain == site or domain.endswith("." + site) or site.endswith(domain):
                        filtered.append(cookie)
                        break
            return filtered

        return raw_cookies

    def _parse_binary_cookies(self, file_path: str) -> List[Dict]:
        """Parse Safari's Cookies.binarycookies format.

        Format:
        - Header: b'cook' (4 bytes)
        - Number of pages: uint32
        - Page sizes: uint32[] (one per page)
        - Pages: each page contains a cookie count and cookie entries
        """
        try:
            with open(file_path, "rb") as f:
                data = f.read()
        except IOError as e:
            logger.error(f"Failed to read Safari cookies file: {e}")
            return []

        cookies = []
        offset = 0

        # Validate header
        if len(data) < 8:
            logger.warning("Safari cookies file too small to contain valid data")
            return []

        header = data[offset:offset + 4]
        offset += 4
        if header != b"cook":
            logger.warning("Invalid Safari cookies file header (expected b'cook')")
            return []

        # Read number of pages
        num_pages = struct.unpack(">I", data[offset:offset + 4])[0]
        offset += 4

        # Read page sizes
        page_sizes = []
        for _ in range(num_pages):
            page_sizes.append(struct.unpack(">I", data[offset:offset + 4])[0])
            offset += 4

        # Parse each page
        for page_size in page_sizes:
            page_data = data[offset:offset + page_size]
            offset += page_size
            page_cookies = self._parse_page(page_data)
            cookies.extend(page_cookies)

        logger.info(f"Extracted {len(cookies)} cookies from Safari")
        return cookies

    def _parse_page(self, page_data: bytes) -> List[Dict]:
        """Parse a single page of cookies."""
        cookies = []
        if len(page_data) < 4:
            return cookies

        # Skip page header (4 bytes: 0x00000100)
        offset = 4

        # Number of cookies in this page
        if offset + 4 > len(page_data):
            return cookies
        num_cookies = struct.unpack(">I", page_data[offset:offset + 4])[0]
        offset += 4

        # Cookie offsets table
        cookie_offsets = []
        for _ in range(num_cookies):
            if offset + 4 > len(page_data):
                break
            cookie_offsets.append(struct.unpack(">I", page_data[offset:offset + 4])[0])
            offset += 4

        # Parse each cookie at its offset
        for cookie_offset in cookie_offsets:
            if cookie_offset >= len(page_data):
                continue
            cookie = self._parse_cookie_entry(page_data, cookie_offset)
            if cookie:
                cookies.append(cookie)

        return cookies

    def _parse_cookie_entry(self, page_data: bytes, offset: int) -> Optional[Dict]:
        """Parse a single cookie entry from the page data.

        Cookie entry format:
        - Flags: uint32 (bit 0 = secure, bit 1 = httponly)
        - Padding: uint32
        - URL offset: uint32
        - Name offset: uint32
        - Value offset: uint32
        - Domain offset: uint32
        - Path offset: uint32
        - Comment offset: uint32
        - Expiry: double (Mac absolute time)
        - Creation: double (Mac absolute time)
        """
        if offset + 4 > len(page_data):
            return None

        # Flags (uint32): bit 0 = secure, bit 1 = httponly
        flags = struct.unpack(">I", page_data[offset:offset + 4])[0]
        offset += 4

        # Skip padding (4 bytes)
        offset += 4

        # Read string offsets: url, name, value, domain, path, comment
        string_offsets = []
        for _ in range(6):
            if offset + 4 > len(page_data):
                return None
            string_offsets.append(
                struct.unpack(">I", page_data[offset:offset + 4])[0]
            )
            offset += 4

        # Skip comment (4 bytes)
        offset += 4

        # Expiry (Mac absolute time as double, 8 bytes)
        if offset + 8 > len(page_data):
            return None
        expiry_mac = struct.unpack(">d", page_data[offset:offset + 8])[0]
        offset += 8

        # Creation (Mac absolute time as double, 8 bytes)
        if offset + 8 > len(page_data):
            return None
        offset += 8  # We don't need creation time

        # Extract strings from page data
        name = self._read_string(page_data, string_offsets[1])
        value = self._read_string(page_data, string_offsets[2])
        domain = self._read_string(page_data, string_offsets[3])
        path = self._read_string(page_data, string_offsets[4])

        if not name and not domain:
            return None

        # Convert Mac absolute time to Unix timestamp
        expires = None
        if expiry_mac > 0:
            expires = int(expiry_mac - MAC_EPOCH_OFFSET)

        cookie = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": path,
            "secure": bool(flags & 0x1),
            "httpOnly": bool(flags & 0x2),
            "sameSite": "Lax",
        }
        if expires is not None and expires > 0:
            cookie["expires"] = expires

        return cookie

    @staticmethod
    def _read_string(data: bytes, offset: int) -> str:
        """Read a null-terminated string from binary data."""
        if offset >= len(data):
            return ""

        end = data.index(b"\x00", offset) if b"\x00" in data[offset:] else len(data)
        try:
            return data[offset:end].decode("utf-8", errors="replace")
        except Exception:
            return ""

    @staticmethod
    def _read_cstring(data: bytes, offset: int) -> str:
        """Read a null-terminated C string from data."""
        if offset >= len(data):
            return ""

        end = data.index(b"\x00", offset) if b"\x00" in data[offset:] else len(data)
        return data[offset:end].decode("utf-8", errors="replace")

    def attempt_keychain_decrypt(self, cookie_name: str, cookie_value: str) -> Optional[str]:
        """Attempt to decrypt a Safari cookie using macOS Keychain.

        Safari stores some cookie values encrypted with keys in the Keychain.
        Uses AES-128-CBC with PKCS7 padding.

        Returns decrypted value or None if decryption fails.
        """
        try:
            # Try to find the Safari Safe Encryption key
            result = subprocess.run(
                [
                    "security", "find-generic-password",
                    "-s", "Safari Safe Encryption",
                    "-a", "Safari",
                    "-w"
                ],
                capture_output=True, text=True, timeout=5
            )

            if result.returncode != 0:
                logger.debug("Safari encryption key not found in Keychain")
                return cookie_value

            key_hex = result.stdout.strip()
            key = bytes.fromhex(key_hex)
            logger.debug(f"Found Safari encryption key ({len(key)} bytes)")

            # Try to decrypt the cookie value
            return self._aes_cbc_decrypt(cookie_value, key)

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.debug(f"Keychain access failed: {e}")
            return cookie_value
        except Exception as e:
            logger.debug(f"Safari decryption failed: {e}")
            return cookie_value

    @staticmethod
    def _aes_cbc_decrypt(cookie_value: str, key: bytes) -> str:
        """Decrypt a Safari cookie value using AES-128-CBC.

        Safari cookie encryption format:
        - First 3 bytes: version header (e.g., "v10")
        - Next 16 bytes: IV
        - Remaining bytes: AES-CBC encrypted data with PKCS7 padding
        """
        try:
            from Crypto.Cipher import AES
            import base64

            # Check if the value looks encrypted (base64 or hex)
            try:
                data = base64.b64decode(cookie_value)
            except Exception:
                # Try hex decoding
                try:
                    data = bytes.fromhex(cookie_value)
                except Exception:
                    # Not encrypted, return as-is
                    return cookie_value

            if len(data) < 19:  # 3 (header) + 16 (IV)
                return cookie_value

            # Parse header
            header = data[:3]
            if header not in (b"v10", b"v11"):
                return cookie_value

            iv = data[3:19]
            ciphertext = data[19:]

            # Truncate key if needed for AES-128
            aes_key = key[:16] if len(key) >= 16 else key.ljust(16, b'\0')

            cipher = AES.new(aes_key, AES.MODE_CBC, iv)
            decrypted = cipher.decrypt(ciphertext)

            # Remove PKCS7 padding
            pad_len = decrypted[-1]
            if 1 <= pad_len <= 16:
                decrypted = decrypted[:-pad_len]

            return decrypted.decode("utf-8", errors="replace")

        except ImportError:
            logger.debug("pycryptodome not installed for Safari decryption")
            return cookie_value
        except Exception as e:
            logger.debug(f"AES decryption failed: {e}")
            return cookie_value
