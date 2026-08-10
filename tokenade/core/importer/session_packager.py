"""
Session Packager - Package extracted cookies into .tokenade format.

Handles:
- Site detection from cookies
- Auth status inference
- Fingerprint collection from source browser
- Packaging into portable .tokenade files
"""

import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import logging

from tokenade.core.importer.cookie_extractor import SiteFilter, SITE_DETECTION
from tokenade.handlers.base import AuthStatus
from urllib.parse import unquote

logger = logging.getLogger(__name__)


class SessionPackager:
    """Packages cookies into portable .tokenade session files."""

    TOKENADE_VERSION = "3.0"

    def __init__(self, site_filter: Optional[SiteFilter] = None, cache_ttl: int = 300):
        """
        Initialize packager.

        Args:
            site_filter: Optional site filter for detecting the site
            cache_ttl: Cache TTL in seconds for loaded sessions (0 to disable)
        """
        self.site_filter = site_filter or SiteFilter()
        self._cache = None
        if cache_ttl > 0:
            from tokenade.core.utils.performance import LRUCache
            self._cache = LRUCache(max_size=50, default_ttl=cache_ttl)

    def detect_site(self, cookies: List[Dict]) -> Optional[str]:
        """Detect which site these cookies belong to."""
        return self.site_filter.detect_site(cookies)

    def infer_auth_status(self, cookies: List[Dict], site_name: Optional[str] = None) -> AuthStatus:
        """
        Infer authentication status from cookies.

        Checks for critical cookies that indicate an active session.
        For unknown sites, uses heuristics based on cookie characteristics.
        """
        if not cookies:
            return AuthStatus.LOGGED_OUT

        site = site_name or self.detect_site(cookies)

        if site and site in SITE_DETECTION:
            # Known site: use critical cookie rules
            rules = SITE_DETECTION[site]
            cookie_names = {c.get("name", "") for c in cookies}
            critical = rules["critical_cookies"]

            # Check for at least one critical cookie
            has_critical = any(name in cookie_names for name in critical)
            if not has_critical:
                return AuthStatus.LOGGED_OUT

            # Check for primary session cookie (first in critical list)
            primary = critical[0]
            if primary not in cookie_names:
                return AuthStatus.SESSION_EXPIRED

            return AuthStatus.LOGGED_IN
        else:
            # Unknown site: use heuristics
            # Blocklist: known non-auth cookies that have secure+httpOnly but aren't sessions
            non_auth_cookies = {
                "_ga", "_gid", "_gat", "__cf_bm", "cf_clearance",
                "__utmz", "__utma", "__utmc", "__utmb",
                "_fbp", "_fbc", "fr", "IDE", "NID", "1P_JAR",
                "AnalyticsSyncHistory", "__hstc", "hubspotutk",
            }
            # Look for session-like cookies (secure + httpOnly + long expiry)
            session_like = 0
            for c in cookies:
                name = c.get("name", "")
                if name in non_auth_cookies:
                    continue
                if c.get("secure") and c.get("httpOnly"):
                    session_like += 1
                # Session token patterns
                name_lower = name.lower()
                if any(kw in name_lower for kw in ("session", "token", "auth", "sid", "csr", "xsrf")):
                    session_like += 1

            if session_like >= 2:
                return AuthStatus.LOGGED_IN
            elif session_like >= 1:
                return AuthStatus.UNKNOWN
            else:
                return AuthStatus.LOGGED_OUT

    def collect_fingerprint(self, browser_manager=None) -> Optional[Dict]:
        """
        Collect fingerprint from source browser.

        Args:
            browser_manager: Optional browser manager to collect from

        Returns:
            Fingerprint dict or None
        """
        if browser_manager is None:
            return None

        try:
            from tokenade.core.fingerprint.manager import FingerprintCollector
            fp = FingerprintCollector.collect_from_browser(browser_manager)
            return fp.to_dict()
        except Exception as e:
            logger.warning(f"Failed to collect fingerprint: {e}")
            return None

    def _extract_email(self, cookies: List[Dict], site_name: Optional[str] = None) -> Optional[str]:
        """Extract email from cookies (e.g., EMAIL cookie on Google/Labs sites)."""
        for c in cookies:
            name = c.get("name", "")
            if name in ("EMAIL", "email"):
                raw = c.get("value", "")
                email = unquote(raw).strip('"')
                if "@" in email:
                    return email
        return None

    def package(self,
                cookies: List[Dict],
                browser: str = "unknown",
                profile: str = "unknown",
                fingerprint: Optional[Dict] = None,
                tokens: Optional[List[Dict]] = None,
                local_storage: Optional[Dict[str, str]] = None,
                session_storage: Optional[Dict[str, str]] = None,
                storage: Optional[Dict[str, Dict[str, Dict[str, str]]]] = None,
                source_browser_manager=None,
                tls_profile: Optional[Dict] = None,
                oauth_config: Optional[Dict] = None,
                extra_cookies: Optional[List[Dict]] = None,
                metadata: Optional[Dict] = None) -> Dict:
        """
        Package cookies into .tokenade format (v3.0).

        Args:
            cookies: List of extracted cookies
            browser: Source browser name
            profile: Source profile name
            fingerprint: Optional fingerprint dict
            tokens: Optional list of tokens
            local_storage: Optional localStorage key-value dict (flat, legacy)
            session_storage: Optional sessionStorage key-value dict (flat, legacy)
            storage: Optional per-origin storage dict {"local": {origin: {k: v}}, "session": {origin: {k: v}}}
            source_browser_manager: Optional browser manager for fingerprint collection
            tls_profile: Optional TLS profile for proxy mode
            oauth_config: Optional OAuth 2.0 configuration dict
            metadata: Optional additional metadata to merge into package metadata

        Returns:
            .tokenade format dictionary (v3.0)
        """
        site_name = self.detect_site(cookies)
        auth_status = self.infer_auth_status(cookies, site_name)

        # Auto-collect fingerprint if not provided
        if fingerprint is None and source_browser_manager is not None:
            fingerprint = self.collect_fingerprint(source_browser_manager)

        # Auto-detect TLS profile from browser if not provided
        if tls_profile is None:
            tls_profile = self._detect_tls_profile(browser, fingerprint)

        # Count critical cookies
        critical_count = 0
        if site_name and site_name in SITE_DETECTION:
            critical_names = set(SITE_DETECTION[site_name]["critical_cookies"])
            critical_count = sum(1 for c in cookies if c.get("name") in critical_names)

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Build storage dict (v3.0 per-origin format)
        storage_data = {"local": {}, "session": {}}
        if storage:
            storage_data = storage
        elif local_storage or session_storage:
            # Convert flat dicts to per-origin format
            origin = self._infer_origin(cookies)
            if local_storage:
                storage_data["local"][origin] = local_storage
            if session_storage:
                storage_data["session"][origin] = session_storage

        email = self._extract_email(cookies, site_name)
        if not email and extra_cookies:
            email = self._extract_email(extra_cookies, site_name)

        package_metadata = {
            "extraction_method": "sqlite_direct",
            "cookie_count": len(cookies),
            "critical_cookie_count": critical_count,
            "local_storage_count": sum(len(v) for v in storage_data["local"].values()),
            "session_storage_count": sum(len(v) for v in storage_data["session"].values()),
            **({"email": email} if email else {}),
        }
        if metadata:
            package_metadata.update(metadata)

        package = {
            "version": self.TOKENADE_VERSION,
            "created_at": now,
            "source_device": {
                "browser": browser,
                "profile": profile,
                "platform": platform.system(),
                "hostname": "anonymous",
            },
            "site_name": site_name or "unknown",
            "auth_status": auth_status.value,
            "cookies": cookies,
            "tokens": tokens or [],
            "storage": storage_data,
            "fingerprint": fingerprint,
            "tls_profile": tls_profile,
            "oauth_config": oauth_config,
            "metadata": package_metadata,
        }

        ls_count = sum(len(v) for v in storage_data["local"].values())
        ss_count = sum(len(v) for v in storage_data["session"].values())
        ls_info = f", {ls_count} localStorage" if ls_count else ""
        ss_info = f", {ss_count} sessionStorage" if ss_count else ""
        logger.info(f"Packaged session: {site_name} ({len(cookies)} cookies, {critical_count} critical{ls_info}{ss_info})")
        return package

    def _infer_origin(self, cookies: List[Dict]) -> str:
        """Infer the origin from cookie domains."""
        for c in cookies:
            domain = c.get("domain", "")
            if domain.startswith("."):
                domain = domain[1:]
            if domain:
                return f"https://{domain}"
        return "https://unknown"

    def _detect_tls_profile(self, browser: str, fingerprint: Optional[Dict] = None) -> Dict:
        """
        Detect TLS profile from browser name and fingerprint.

        Note: curl-cffi only supports Chrome impersonation, not Firefox.
        We always use Chrome impersonation for TLS matching.

        Args:
            browser: Browser name
            fingerprint: Optional fingerprint dict

        Returns:
            TLS profile dict
        """
        from tokenade.core.runtime.tls_matcher import IMPERSONATE_TARGETS

        # Always use Chrome for TLS impersonation (Firefox not supported by curl-cffi)
        tls_browser = "chrome"
        version = "120"
        impersonate = "chrome120"

        # Try to extract Chrome version from user agent
        if fingerprint and fingerprint.get("user_agent"):
            ua = fingerprint["user_agent"]
            import re
            chrome_match = re.search(r'Chrome/(\d+)', ua)
            if chrome_match:
                version = chrome_match.group(1)
                # Find closest impersonation target
                for target_key in IMPERSONATE_TARGETS:
                    if target_key.startswith(f"chrome{version}"):
                        impersonate = target_key
                        break

        return {
            "browser": tls_browser,
            "version": version,
            "impersonate": impersonate,
            "http_version": "2"
        }

    def save(self, package: Dict, output_path: str, encrypt: Optional[bool] = None) -> str:
        """
        Save package to .tokenade file.

        Args:
            package: .tokenade format dictionary
            output_path: Output file path
            encrypt: Force encryption on/off. None = use config default.

        Returns:
            Absolute path to saved file
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Determine if we should encrypt
        do_encrypt = encrypt
        if do_encrypt is None:
            try:
                from tokenade.core.crypto.at_rest import should_encrypt
                do_encrypt = should_encrypt()
            except Exception:
                do_encrypt = False

        if do_encrypt:
            try:
                from tokenade.core.crypto.at_rest import save_encrypted
                result = save_encrypted(package, str(path))
                if self._cache is not None:
                    self._cache.set(str(path.absolute()), package)
                logger.info(f"Session saved (encrypted): {path}")
                return result
            except ValueError as e:
                logger.warning(f"Encryption failed, saving plaintext: {e}")

        # Atomic write: never truncate the real file until JSON serializes cleanly.
        # (A failed dump used to leave 0-byte .tokenade files → sessions "vanished".)
        import os
        import tempfile

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(package, f, indent=2, ensure_ascii=False, default=str)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

        # Update cache
        if self._cache is not None:
            self._cache.set(str(path.absolute()), package)

        logger.info(f"Session saved: {path}")
        return str(path.absolute())

    def load(self, file_path: str, password: Optional[str] = None) -> Dict:
        """
        Load .tokenade file with backward compatibility and auto-decryption.

        Handles:
        - Encrypted files (auto-detected by magic header)
        - Legacy formats missing newer fields

        Args:
            file_path: Path to .tokenade file
            password: Decryption password (optional, resolved from config if needed)

        Returns:
            Package dictionary (normalized to current format)
        """
        path = Path(file_path)
        abs_path = str(path.absolute())

        # Check cache first
        if self._cache is not None:
            cached = self._cache.get(abs_path)
            if cached is not None:
                logger.debug(f"Session loaded from cache: {path}")
                return cached

        if not path.exists():
            raise FileNotFoundError(f"Session file not found: {file_path}")

        # Auto-detect encrypted files
        try:
            from tokenade.core.crypto.at_rest import is_encrypted_file, load_encrypted
            if is_encrypted_file(str(path)):
                package = load_encrypted(str(path), password=password)
                package = self._normalize_legacy(package)
                if self._cache is not None:
                    self._cache.set(abs_path, package)
                logger.info(f"Session loaded (encrypted): {path} ({len(package.get('cookies', []))} cookies)")
                return package
        except ImportError:
            pass  # encryption module not available, try plaintext
        except ValueError as e:
            logger.error(f"Decryption failed for {path}: {e}")
            raise

        with open(path, "r", encoding="utf-8") as f:
            package = json.load(f)

        # Backward compatibility: normalize legacy format
        package = self._normalize_legacy(package)

        # Store in cache
        if self._cache is not None:
            self._cache.set(abs_path, package)

        logger.info(f"Session loaded: {path} ({len(package.get('cookies', []))} cookies)")
        return package

    def _normalize_legacy(self, package: Dict) -> Dict:
        """
        Normalize legacy .tokenade format to current version.

        Handles:
        - Missing version field
        - Missing created_at field
        - Missing source_device (flat browser/platform keys)
        - auth_state instead of auth_status
        - Missing tokens, local_storage, oauth_config fields
        - Missing fingerprint, tls_profile fields
        """
        # Add version if missing
        if "version" not in package:
            package["version"] = self.TOKENADE_VERSION

        # Add created_at if missing
        if "created_at" not in package:
            package["created_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Handle flat browser/platform keys → source_device
        if "source_device" not in package:
            browser = package.pop("browser", "unknown")
            platform_name = package.pop("platform", "unknown")
            profile = package.pop("profile", "unknown")
            package["source_device"] = {
                "browser": browser,
                "profile": profile,
                "platform": platform_name,
                "hostname": "anonymous",
            }

        # Handle auth_state → auth_status
        if "auth_state" in package and "auth_status" not in package:
            package["auth_status"] = package.pop("auth_state")

        # Ensure auth_status exists
        if "auth_status" not in package:
            package["auth_status"] = "unknown"

        # Ensure tokens list exists
        if "tokens" not in package:
            package["tokens"] = []

        # Ensure local_storage dict exists
        if "local_storage" not in package:
            package["local_storage"] = {}

        # Ensure oauth_config exists (None for old sessions)
        if "oauth_config" not in package:
            package["oauth_config"] = None

        # Ensure metadata exists
        if "metadata" not in package:
            package["metadata"] = {}

        if "profile_artifacts" not in package:
            package["profile_artifacts"] = []

        # Add cookie count to metadata if missing
        if "cookie_count" not in package.get("metadata", {}):
            package["metadata"]["cookie_count"] = len(package.get("cookies", []))

        return package

    def validate_format(self, package: Dict) -> bool:
        """
        Validate .tokenade format.

        Checks for required fields and correct structure.
        """
        required_top = ["version", "created_at", "site_name", "auth_status", "cookies"]
        for field in required_top:
            if field not in package:
                logger.error(f"Missing required field: {field}")
                return False

        if not isinstance(package.get("cookies"), list):
            logger.error("cookies must be a list")
            return False

        # Validate cookie structure
        for i, cookie in enumerate(package["cookies"]):
            if not isinstance(cookie, dict):
                logger.error(f"Cookie {i} is not a dict")
                return False
            if "name" not in cookie or "value" not in cookie:
                logger.error(f"Cookie {i} missing name or value")
                return False

        return True

    def get_summary(self, package: Dict) -> str:
        """Generate a text summary of a package."""
        lines = []
        lines.append("=" * 60)
        lines.append("SESSION PACKAGE SUMMARY")
        lines.append("=" * 60)
        lines.append(f"Version: {package.get('version', 'unknown')}")
        lines.append(f"Created: {package.get('created_at', 'unknown')}")
        lines.append(f"Site: {package.get('site_name', 'unknown')}")
        lines.append(f"Auth Status: {package.get('auth_status', 'unknown')}")

        source = package.get("source_device", {})
        lines.append(f"Source Browser: {source.get('browser', 'unknown')}")
        lines.append(f"Source Profile: {source.get('profile', 'unknown')}")
        lines.append(f"Source Platform: {source.get('platform', 'unknown')}")

        meta = package.get("metadata", {})
        lines.append(f"Cookies: {meta.get('cookie_count', 0)}")
        lines.append(f"Critical Cookies: {meta.get('critical_cookie_count', 0)}")

        fp = package.get("fingerprint")
        if fp:
            lines.append("Fingerprint: collected")
            lines.append(f"  User Agent: {fp.get('user_agent', 'unknown')[:60]}...")
            lines.append(f"  Screen: {fp.get('screen_width', 0)}x{fp.get('screen_height', 0)}")
        else:
            lines.append("Fingerprint: not collected")

        lines.append("=" * 60)
        return "\n".join(lines)
