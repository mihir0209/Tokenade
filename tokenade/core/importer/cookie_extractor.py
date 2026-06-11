"""
Cookie Extractor - Read and decrypt cookies from browser databases.

Supports site-specific filtering so users only export what they need.
"""

import json
import os
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

from tokenade.core.crypto.cookie_crypto import CookieCryptoFactory, DecryptedCookie

logger = logging.getLogger(__name__)


# Site detection rules: which domains and critical cookies identify a site
SITE_DETECTION = {
    "google": {
        "domains": [
            "google.com",
            "accounts.google.com",
            "mail.google.com",
            "labs.google.com",
            "myaccount.google.com",
            ".google.com",
        ],
        "critical_cookies": [
            "SID", "SSID", "APISID", "SAPISID", "HSID",
            "__Secure-1PSID", "__Secure-3PSID",
            "__Secure-1PAPISID", "__Secure-3PAPISID",
            "OSID", "__Secure-OSID",
            "__Host-GAPS", "COMPASS",
        ],
    },
    "github": {
        "domains": [
            "github.com",
            ".github.com",
        ],
        "critical_cookies": [
            "user_session",
            "__Host-user_session_same_site",
            "__Host-device_id",
            "has_recent_activity",
        ],
    },
    "discord": {
        "domains": [
            "discord.com",
            "discordapp.com",
            ".discord.com",
        ],
        "critical_cookies": [
            "__dcfduid",
            "__sdcfduid",
            "authorization",
            "discord_session",
        ],
    },
    "reddit": {
        "domains": [
            "reddit.com",
            "www.reddit.com",
            ".reddit.com",
        ],
        "critical_cookies": [
            "reddit_session",
            "token",
            "session",
        ],
    },
    "openai": {
        "domains": [
            "openai.com",
            ".openai.com",
            "chatgpt.com",
            ".chatgpt.com",
            "auth.openai.com",
            ".auth.openai.com",
            "chat.openai.com",
            ".chat.openai.com",
            "platform.openai.com",
            ".platform.openai.com",
        ],
        "critical_cookies": [
            "__Secure-next-auth.session-token.0",
            "__Secure-next-auth.session-token.1",
            "__Secure-next-auth.session-token.2",
            "__Secure-oai-is",
            "oai-did",
            "oai-client-auth-info",
            "cf_clearance",
            "unified_session_manifest",
            "usc_",
        ],
    },
}


class SiteFilter:
    """Filters cookies by site/domain."""

    def __init__(self, sites: Optional[List[str]] = None):
        """
        Initialize site filter.

        Args:
            sites: List of site names to filter by (e.g., ["google", "github"]).
                   If None, no filtering is applied.
        """
        self.sites = [s.lower() for s in (sites or [])]
        self._domain_patterns: List[str] = []
        self._critical_cookies: List[str] = []

        if self.sites:
            for site in self.sites:
                rules = SITE_DETECTION.get(site)
                if rules:
                    self._domain_patterns.extend(rules["domains"])
                    self._critical_cookies.extend(rules["critical_cookies"])
                else:
                    logger.warning(f"Unknown site: {site}")

    def matches(self, cookie: Dict) -> bool:
        """Check if a cookie matches the filter."""
        if not self.sites:
            return True  # No filter = accept all

        domain = cookie.get("domain", "")
        name = cookie.get("name", "")

        # Check domain match
        for pattern in self._domain_patterns:
            if pattern.startswith("."):
                # Wildcard domain: .google.com matches google.com and mail.google.com
                clean_pattern = pattern[1:]
                if domain == clean_pattern or domain.endswith(pattern):
                    return True
            else:
                if domain == pattern or domain.endswith("." + pattern):
                    return True

        # Check critical cookie name match (exact or prefix)
        for crit in self._critical_cookies:
            if crit.endswith("_"):
                if name.startswith(crit):
                    return True
            elif name == crit:
                return True

        return False

    def filter_cookies(self, cookies: List[Dict]) -> List[Dict]:
        """Filter a list of cookies."""
        if not self.sites:
            return cookies
        return [c for c in cookies if self.matches(c)]

    def detect_site(self, cookies: List[Dict]) -> Optional[str]:
        """Detect which site these cookies belong to.

        Prioritizes domain matching over cookie name matching to avoid
        false positives from generic cookie names like 'authorization'.
        """
        cookie_names = {c.get("name", "") for c in cookies}
        cookie_domains = {c.get("domain", "") for c in cookies}

        # Phase 1: Domain-based detection (most reliable)
        domain_matches = {}
        for site_name, rules in SITE_DETECTION.items():
            for domain in cookie_domains:
                for pattern in rules["domains"]:
                    if pattern.startswith("."):
                        if domain.endswith(pattern):
                            domain_matches[site_name] = domain_matches.get(site_name, 0) + 1
                    else:
                        if domain == pattern or domain.endswith("." + pattern):
                            domain_matches[site_name] = domain_matches.get(site_name, 0) + 1

        if domain_matches:
            # Return site with most domain matches
            return max(domain_matches, key=domain_matches.get)

        # Phase 2: Critical cookie name matching (only if no domain matches)
        # Use only non-generic cookie names for this phase
        GENERIC_NAMES = {"authorization", "token", "session"}
        for site_name, rules in SITE_DETECTION.items():
            for crit in rules["critical_cookies"]:
                if crit in GENERIC_NAMES:
                    continue  # Skip overly generic names
                if crit.endswith("_"):
                    if any(name.startswith(crit) for name in cookie_names):
                        return site_name
                elif crit in cookie_names:
                    return site_name

        return None


class CookieExtractor:
    """Extracts cookies from browser databases with optional decryption."""

    def __init__(self, profile_path: str, browser: str = "chrome"):
        """
        Initialize cookie extractor.

        Args:
            profile_path: Path to browser profile directory
            browser: Browser type (chrome, firefox, edge)
        """
        self.profile_path = profile_path
        self.browser = browser.lower()
        self._crypto = None

    def _get_crypto(self):
        """Lazy-init crypto handler."""
        if self._crypto is None:
            self._crypto = CookieCryptoFactory.create()
        return self._crypto

    def _copy_db(self, db_path: str) -> str:
        """Copy database to temp file (browser may lock it).

        Also copies WAL (-wal) and SHM (-shm) files if present,
        since Firefox/Chrome use WAL mode and data may be in WAL.
        """
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Cookie database not found: {db_path}")

        temp_fd, temp_path = tempfile.mkstemp(suffix=".db")
        os.close(temp_fd)
        shutil.copy2(db_path, temp_path)

        # Copy WAL and SHM files if present
        for suffix in ("-wal", "-shm"):
            wal_path = db_path + suffix
            if os.path.exists(wal_path):
                temp_wal = temp_path + suffix
                shutil.copy2(wal_path, temp_wal)

        return temp_path

    def extract_chrome(self, site_filter: Optional[SiteFilter] = None) -> List[Dict]:
        """Extract cookies from Chrome/Chromium/Edge."""
        cookies_db = os.path.join(self.profile_path, "Cookies")
        if not os.path.exists(cookies_db):
            logger.warning(f"Chrome cookies DB not found: {cookies_db}")
            return []

        temp_db = self._copy_db(cookies_db)
        cookies = []

        try:
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()

            # Chrome cookies schema (v80+)
            cursor.execute("""
                SELECT host_key, name, value, encrypted_value, path,
                       expires_utc, is_secure, is_httponly, samesite,
                       creation_utc, last_access_utc
                FROM cookies
                ORDER BY host_key, name
            """)

            crypto = self._get_crypto()
            key = None

            # Try to get encryption key from parent directory
            browser_data_dir = os.path.dirname(self.profile_path)
            if hasattr(crypto, "get_encryption_key"):
                try:
                    key = crypto.get_encryption_key(browser_data_dir)
                except Exception as e:
                    logger.debug(f"Could not get encryption key: {e}")

            for row in cursor.fetchall():
                (host_key, name, value, encrypted_value, path,
                 expires_utc, is_secure, is_httponly, samesite,
                 creation_utc, last_access_utc) = row

                # Decrypt if needed
                decrypted_value = value or ""
                if encrypted_value and key:
                    try:
                        decrypted = crypto.decrypt_cookie(encrypted_value, key)
                        if decrypted is not None:
                            decrypted_value = decrypted
                    except Exception as e:
                        logger.debug(f"Failed to decrypt cookie {name}: {e}")

                # Convert Chrome time to Unix timestamp
                expires = None
                if expires_utc and expires_utc > 0:
                    chrome_epoch_offset = 11644473600
                    expires = int((expires_utc / 1000000) - chrome_epoch_offset)

                cookie = {
                    "name": name,
                    "value": decrypted_value,
                    "domain": host_key,
                    "path": path,
                    "secure": bool(is_secure),
                    "httpOnly": bool(is_httponly),
                    "sameSite": self._map_samesite(samesite),
                }
                if expires and expires > 0:
                    cookie["expires"] = expires

                cookies.append(cookie)

            conn.close()

        finally:
            if os.path.exists(temp_db):
                os.remove(temp_db)

        # Apply site filter
        if site_filter:
            cookies = site_filter.filter_cookies(cookies)

        logger.info(f"Extracted {len(cookies)} cookies from Chrome")
        return cookies

    def extract_firefox(self, site_filter: Optional[SiteFilter] = None) -> List[Dict]:
        """Extract cookies from Firefox."""
        cookies_db = os.path.join(self.profile_path, "cookies.sqlite")
        if not os.path.exists(cookies_db):
            logger.warning(f"Firefox cookies DB not found: {cookies_db}")
            return []

        temp_db = self._copy_db(cookies_db)
        cookies = []

        try:
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT host, name, value, path, expiry, isSecure, isHttpOnly, sameSite
                FROM moz_cookies
                ORDER BY host, name
            """)

            for row in cursor.fetchall():
                host, name, value, path, expiry, is_secure, is_httponly, same_site = row

                cookie = {
                    "name": name,
                    "value": value,
                    "domain": host,
                    "path": path,
                    "secure": bool(is_secure),
                    "httpOnly": bool(is_httponly),
                    "sameSite": self._map_samesite_firefox(same_site),
                }
                if expiry and expiry > 0:
                    cookie["expires"] = expiry

                cookies.append(cookie)

            conn.close()

        finally:
            if os.path.exists(temp_db):
                os.remove(temp_db)

        # Apply site filter
        if site_filter:
            cookies = site_filter.filter_cookies(cookies)

        logger.info(f"Extracted {len(cookies)} cookies from Firefox")
        return cookies

    def extract(self, site_filter: Optional[SiteFilter] = None) -> List[Dict]:
        """Extract cookies based on browser type."""
        if self.browser in ("chrome", "chromium", "edge", "brave"):
            return self.extract_chrome(site_filter)
        elif self.browser == "firefox":
            return self.extract_firefox(site_filter)
        else:
            logger.error(f"Unsupported browser: {self.browser}")
            return []

    @staticmethod
    def parse_netscape(content: str) -> List[Dict]:
        """Parse Netscape cookies.txt format."""
        cookies = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) >= 7:
                domain, flag, path, secure, expires, name, value = parts[:7]
                cookies.append({
                    "domain": domain,
                    "name": name,
                    "value": value,
                    "path": path,
                    "secure": secure.lower() == "true",
                    "httpOnly": flag.startswith("#HttpOnly_"),
                    "expires": int(expires) if expires.isdigit() else None,
                })

        return cookies

    @staticmethod
    def parse_json(content: str) -> List[Dict]:
        """Parse JSON cookie format."""
        data = json.loads(content)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "cookies" in data:
            return data["cookies"]
        return []

    @staticmethod
    def parse_curl(content: str) -> List[Dict]:
        """Parse curl cookie format."""
        # curl format is similar to Netscape
        return CookieExtractor.parse_netscape(content)

    def extract_from_file(self, file_path: str, format_type: str = "auto",
                          site_filter: Optional[SiteFilter] = None) -> List[Dict]:
        """Extract cookies from a file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        content = path.read_text()

        # Auto-detect format
        if format_type == "auto":
            if file_path.endswith(".json"):
                format_type = "json"
            else:
                format_type = "netscape"

        if format_type == "netscape":
            cookies = self.parse_netscape(content)
        elif format_type == "json":
            cookies = self.parse_json(content)
        elif format_type == "curl":
            cookies = self.parse_curl(content)
        else:
            raise ValueError(f"Unknown format: {format_type}")

        if site_filter:
            cookies = site_filter.filter_cookies(cookies)

        return cookies

    @staticmethod
    def _map_samesite(value: int) -> str:
        """Map Chrome samesite integer to string."""
        mapping = {0: "None", 1: "Lax", 2: "Strict", -1: "None"}
        return mapping.get(value, "Lax")

    @staticmethod
    def _map_samesite_firefox(value: int) -> str:
        """Map Firefox samesite integer to string."""
        # Firefox uses 0=None, 1=Lax, 2=Strict, 3=SameSite=None (as of some versions)
        mapping = {0: "None", 1: "Lax", 2: "Strict"}
        return mapping.get(value, "Lax")
