"""
Browser Profile Cloner — copy browser profiles and optionally inject sessions.

Creates a complete copy of a browser profile at a new location,
preserving fingerprint-relevant data (extensions, settings, bookmarks).
Optionally injects session cookies/storage into the clone.
"""

import json
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

SKIP_DIRS = {
    "Cache", "Code Cache", "GPUCache", "ShaderCache", "ShaderCache",
    "Service Worker", "IndexedDB", "Session Storage", "Local Storage",
    "blob_storage", "File System", "GCM Store", "databases",
    "component_crx_cache", "extensions_crx_cache", "BudgetDatabase",
    "WebStorage", "Storage", "heavy_ad_intervention",
}


@dataclass
class CloneResult:
    """Result of a profile clone operation."""
    source_path: str
    dest_path: str
    browser: str
    files_copied: int
    size_bytes: int
    session_injected: bool = False
    cookies_injected: int = 0
    localStorage_injected: int = 0
    sessionStorage_injected: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    @property
    def summary(self) -> str:
        parts = [
            f"{self.files_copied} files",
            f"{self.size_bytes / (1024 * 1024):.1f} MB",
        ]
        if self.session_injected:
            parts.append(f"{self.cookies_injected} cookies injected")
        return ", ".join(parts)


class ProfileCloner:
    """Clone browser profiles with optional session injection."""

    def clone_profile(
        self,
        source_path: str,
        dest_path: str,
        browser: str = "chrome",
        session_file: Optional[str] = None,
    ) -> CloneResult:
        """
        Clone a browser profile to a new location.

        Args:
            source_path: Path to source browser profile directory
            dest_path: Path to create the clone
            browser: Browser name (chrome, firefox, brave, edge)
            session_file: Optional .tokenade file to inject into the clone

        Returns:
            CloneResult with operation details
        """
        source = Path(source_path)
        dest = Path(dest_path)

        result = CloneResult(
            source_path=str(source),
            dest_path=str(dest),
            browser=browser,
            files_copied=0,
            size_bytes=0,
        )

        if not source.exists():
            result.errors.append(f"Source profile not found: {source}")
            return result

        if dest.exists():
            result.errors.append(f"Destination already exists: {dest}")
            return result

        # Copy the profile
        try:
            result.files_copied, result.size_bytes = self._copy_profile(source, dest)
            logger.info(f"Profile cloned: {source} -> {dest} ({result.files_copied} files)")
        except Exception as e:
            result.errors.append(f"Copy failed: {e}")
            return result

        # Inject session if provided
        if session_file:
            try:
                self._inject_session(dest, browser, session_file, result)
            except Exception as e:
                result.errors.append(f"Session injection failed: {e}")

        return result

    def clone_default_profile(
        self,
        dest_path: str,
        browser: str = "chrome",
        profile_name: Optional[str] = None,
        session_file: Optional[str] = None,
    ) -> CloneResult:
        """
        Clone the default system browser profile.

        Args:
            dest_path: Path to create the clone
            browser: Browser name
            profile_name: Specific profile to clone (None = default)
            session_file: Optional .tokenade file to inject

        Returns:
            CloneResult
        """
        from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery

        discovery = BrowserProfileDiscovery()
        all_profiles = discovery.discover_all()
        profiles = all_profiles.get(browser, [])

        if not profiles:
            return CloneResult(
                source_path="",
                dest_path=dest_path,
                browser=browser,
                files_copied=0,
                size_bytes=0,
                errors=[f"No {browser} profiles found"],
            )

        # Find the target profile
        target = None
        if profile_name:
            for p in profiles:
                if p.name == profile_name:
                    target = p
                    break
        else:
            # Use the default or first profile
            for p in profiles:
                if p.is_default:
                    target = p
                    break
            if not target:
                target = profiles[0]

        return self.clone_profile(
            source_path=str(target.path),
            dest_path=dest_path,
            browser=browser,
            session_file=session_file,
        )

    def list_profiles(self, browser: str = "chrome") -> List[Dict]:
        """List available system browser profiles."""
        from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery

        discovery = BrowserProfileDiscovery()
        all_profiles = discovery.discover_all()
        profiles = all_profiles.get(browser, [])

        return [
            {
                "name": p.name,
                "path": str(p.path),
                "browser": p.browser,
                "is_default": p.is_default,
                "last_used": p.last_used,
            }
            for p in profiles
        ]

    def _copy_profile(self, source: Path, dest: Path) -> tuple:
        """Copy profile directory, skipping cache dirs. Returns (file_count, total_size)."""
        file_count = 0
        total_size = 0

        def _ignore(directory, contents):
            return [c for c in contents if c in SKIP_DIRS]

        shutil.copytree(str(source), str(dest), ignore=_ignore)

        # Count files and size
        for f in dest.rglob("*"):
            if f.is_file():
                file_count += 1
                total_size += f.stat().st_size

        return file_count, total_size

    def _inject_session(
        self,
        profile_dir: Path,
        browser: str,
        session_file: str,
        result: CloneResult,
    ):
        """Inject session cookies/storage into the cloned profile."""
        from tokenade.core.importer.session_packager import SessionPackager

        packager = SessionPackager()
        session = packager.load(session_file)

        cookies = session.get("cookies", [])
        local_storage = session.get("local_storage", {})
        session_storage = session.get("session_storage", {})

        if not cookies:
            return

        # For Chromium-based browsers, inject into Cookies SQLite
        if browser in ("chrome", "brave", "edge"):
            self._inject_chromium_cookies(profile_dir, browser, cookies, result)
        elif browser == "firefox":
            self._inject_firefox_cookies(profile_dir, cookies, result)

        result.session_injected = True
        result.cookies_injected = len(cookies)
        result.localStorage_injected = len(local_storage)
        result.sessionStorage_injected = len(session_storage)

    def _inject_chromium_cookies(
        self,
        profile_dir: Path,
        browser: str,
        cookies: List[Dict],
        result: CloneResult,
    ):
        """Inject cookies into Chromium-based browser profile."""
        # Find the Cookies database
        default_db = profile_dir / "Default" / "Cookies"
        if not default_db.exists():
            # Try Profile 1
            default_db = profile_dir / "Profile 1" / "Cookies"
        if not default_db.exists():
            result.errors.append("Cookies database not found in profile")
            return

        try:
            import sqlite3
            conn = sqlite3.connect(str(default_db))
            cursor = conn.cursor()

            # Get existing table schema
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}

            if "cookies" in tables:
                # Modern Chromium format
                for cookie in cookies:
                    try:
                        cursor.execute(
                            """INSERT OR REPLACE INTO cookies
                            (host_key, name, value, path, expires_utc, is_secure, is_httponly, samesite, encrypted_value)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                cookie.get("domain", ""),
                                cookie.get("name", ""),
                                cookie.get("value", ""),
                                cookie.get("path", "/"),
                                cookie.get("expires", 0),
                                1 if cookie.get("secure") else 0,
                                1 if cookie.get("httpOnly") else 0,
                                self._same_site_value(cookie.get("sameSite", "Lax")),
                                b"",  # encrypted_value (empty for plain import)
                            ),
                        )
                    except sqlite3.Error as e:
                        logger.warning(f"Failed to inject cookie {cookie.get('name')}: {e}")

            conn.commit()
            conn.close()
        except ImportError:
            result.errors.append("sqlite3 not available")
        except Exception as e:
            result.errors.append(f"Cookie injection error: {e}")

    def _inject_firefox_cookies(
        self,
        profile_dir: Path,
        cookies: List[Dict],
        result: CloneResult,
    ):
        """Inject cookies into Firefox profile."""
        cookies_db = profile_dir / "cookies.sqlite"
        if not cookies_db.exists():
            result.errors.append("cookies.sqlite not found in profile")
            return

        try:
            import sqlite3
            conn = sqlite3.connect(str(cookies_db))
            cursor = conn.cursor()

            for cookie in cookies:
                try:
                    cursor.execute(
                        """INSERT OR REPLACE INTO moz_cookies
                        (baseDomain, name, value, path, expiry, isSecure, isHttpOnly, sameSite, host)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            cookie.get("domain", "").lstrip("."),
                            cookie.get("name", ""),
                            cookie.get("value", ""),
                            cookie.get("path", "/"),
                            cookie.get("expires", 0),
                            1 if cookie.get("secure") else 0,
                            1 if cookie.get("httpOnly") else 0,
                            self._same_site_value(cookie.get("sameSite", "Lax")),
                            cookie.get("domain", ""),
                        ),
                    )
                except sqlite3.Error as e:
                    logger.warning(f"Failed to inject cookie {cookie.get('name')}: {e}")

            conn.commit()
            conn.close()
        except Exception as e:
            result.errors.append(f"Firefox cookie injection error: {e}")

    @staticmethod
    def _same_site_value(same_site: str) -> int:
        """Convert SameSite string to integer for SQLite storage."""
        mapping = {"strict": 0, "lax": 1, "none": 2}
        return mapping.get(same_site.lower(), 1)
