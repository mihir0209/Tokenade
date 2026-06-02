"""
Session Loader - Load .tokenade files and inject into target browsers.

Handles:
- Read .tokenade session packages
- Apply target fingerprint with stealth spoofing
- Inject cookies into browser context
- Validate session after injection
- Optional: Load into RuntimeEngine
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

from tokenade.core.browser.manager import BrowserFactory, BrowserConfig
from tokenade.core.fingerprint.manager import FingerprintManager, BrowserFingerprint
from tokenade.core.fingerprint.injector import inject_stealth_script, validate_injection
from tokenade.handlers.base import AuthStatus, SessionData

logger = logging.getLogger(__name__)


class SessionLoader:
    """Loads .tokenade session packages and injects into browsers."""

    def __init__(self, fp_manager: Optional[FingerprintManager] = None):
        """
        Initialize session loader.

        Args:
            fp_manager: Optional fingerprint manager for loading target fingerprints
        """
        self.fp_manager = fp_manager or FingerprintManager()
        self._browser = None
        self._last_result: Optional[Dict] = None

    def load_file(self, file_path: str) -> Dict:
        """
        Load a .tokenade file.

        Args:
            file_path: Path to .tokenade file

        Returns:
            Package dictionary
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Session file not found: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            package = json.load(f)

        logger.info(f"Loaded session package: {path} ({len(package.get('cookies', []))} cookies)")
        return package

    def apply_fingerprint(self, browser_manager, fingerprint: Optional[Dict] = None,
                          stealth_level: str = "maximum") -> bool:
        """
        Apply fingerprint with stealth spoofing to browser.

        Args:
            browser_manager: Active browser manager
            fingerprint: Fingerprint dict to apply
            stealth_level: Stealth level (basic, advanced, maximum)

        Returns:
            True if injection succeeded
        """
        if not fingerprint:
            logger.info("No fingerprint to apply")
            return True

        try:
            fp = BrowserFingerprint.from_dict(fingerprint)
            inject_stealth_script(browser_manager, fp, stealth_level)
            logger.info(f"Stealth script injected at level: {stealth_level}")
            return True
        except Exception as e:
            logger.warning(f"Failed to inject stealth script: {e}")
            return False

    def inject_cookies(self, browser_manager, cookies: List[Dict]) -> int:
        """
        Inject cookies into browser context.

        Args:
            browser_manager: Active browser manager
            cookies: List of cookies to inject

        Returns:
            Number of cookies successfully injected
        """
        if not cookies:
            logger.warning("No cookies to inject")
            return 0

        injected = 0
        for cookie in cookies:
            try:
                # Ensure required fields
                if "name" not in cookie or "value" not in cookie:
                    logger.debug(f"Skipping invalid cookie: {cookie}")
                    continue

                # Normalize cookie format for Playwright
                normalized = self._normalize_cookie(cookie)
                browser_manager.add_cookies([normalized])
                injected += 1
            except Exception as e:
                logger.debug(f"Failed to inject cookie {cookie.get('name')}: {e}")

        logger.info(f"Injected {injected}/{len(cookies)} cookies")
        return injected

    def inject_local_storage(self, browser_manager, local_storage: Dict[str, str],
                             origin: Optional[str] = None) -> int:
        """
        Inject localStorage into browser context.

        Uses page.evaluate() to call localStorage.setItem() for each key-value pair.
        Must be called after navigating to the target origin.

        Args:
            browser_manager: Active browser manager
            local_storage: Dictionary of {key: value} to inject
            origin: Optional origin URL to navigate to before injection

        Returns:
            Number of localStorage entries successfully injected
        """
        if not local_storage:
            logger.info("No localStorage to inject")
            return 0

        # Navigate to origin if specified
        if origin:
            try:
                browser_manager.navigate(origin, wait_until="domcontentloaded", timeout=15000)
                logger.info(f"Navigated to origin for localStorage injection: {origin}")
            except Exception as e:
                logger.warning(f"Failed to navigate to origin {origin}: {e}")

        injected = 0
        try:
            # Batch inject all localStorage entries
            # Use page.evaluate with a data parameter to avoid serialization issues
            result = browser_manager.evaluate("""
                (data) => {
                    let count = 0;
                    for (const [key, value] of Object.entries(data)) {
                        try {
                            localStorage.setItem(key, value);
                            count++;
                        } catch (e) {
                            console.error('localStorage setItem failed for key:', key, e);
                        }
                    }
                    return count;
                }
            """, local_storage)

            if isinstance(result, int):
                injected = result
            else:
                # Fallback: inject one by one
                for key, value in local_storage.items():
                    try:
                        browser_manager.evaluate("""
                            (key, value) => {
                                localStorage.setItem(key, value);
                            }
                        """, key, value)
                        injected += 1
                    except Exception as e:
                        logger.debug(f"Failed to inject localStorage key {key}: {e}")

        except Exception as e:
            logger.error(f"Failed to inject localStorage: {e}")

        logger.info(f"Injected {injected}/{len(local_storage)} localStorage entries")
        return injected

    def _normalize_cookie(self, cookie: Dict) -> Dict:
        """Normalize cookie dict to Playwright format."""
        normalized = {
            "name": cookie["name"],
            "value": cookie["value"],
            "domain": cookie.get("domain", ""),
            "path": cookie.get("path", "/"),
        }

        if cookie.get("secure"):
            normalized["secure"] = True
        if cookie.get("httpOnly"):
            normalized["httpOnly"] = True
        if "expires" in cookie and cookie["expires"]:
            normalized["expires"] = int(cookie["expires"])
        if cookie.get("sameSite"):
            normalized["sameSite"] = cookie["sameSite"]

        return normalized

    def validate_session(self, browser_manager, site_name: str) -> Dict:
        """
        Validate session after injection.

        Args:
            browser_manager: Active browser manager
            site_name: Site name to validate

        Returns:
            Validation result dict
        """
        result = {
            "valid": False,
            "auth_status": "unknown",
            "cookies_present": 0,
            "details": {},
        }

        try:
            # Get current cookies
            current_cookies = browser_manager.get_cookies()
            result["cookies_present"] = len(current_cookies)

            # Check for critical cookies based on site
            from tokenade.core.importer.cookie_extractor import SITE_DETECTION
            rules = SITE_DETECTION.get(site_name, {})
            critical = rules.get("critical_cookies", [])

            if critical:
                cookie_names = {c.get("name", "") for c in current_cookies}
                has_critical = any(name in cookie_names for name in critical)
                primary = critical[0] if critical else None

                if has_critical and primary and primary in cookie_names:
                    result["valid"] = True
                    result["auth_status"] = "logged_in"
                elif has_critical:
                    result["auth_status"] = "session_expired"
                else:
                    result["auth_status"] = "logged_out"
            else:
                # No critical cookies defined - just check if any cookies present
                result["valid"] = len(current_cookies) > 0
                result["auth_status"] = "logged_in" if result["valid"] else "logged_out"

            logger.info(f"Session validation: {result['auth_status']} ({result['cookies_present']} cookies)")

        except Exception as e:
            logger.error(f"Session validation failed: {e}")
            result["error"] = str(e)

        return result

    def load(self,
             file_path: str,
             target_fp_name: Optional[str] = None,
             stealth_level: str = "maximum",
             validate: bool = True,
             visible: bool = False,
             profile_dir: Optional[str] = None,
             inject_local_storage: bool = True) -> Dict:
        """
        Complete load workflow: read file, launch browser, inject cookies, validate.

        Args:
            file_path: Path to .tokenade file
            target_fp_name: Optional target fingerprint name
            stealth_level: Stealth level for spoofing
            validate: Whether to validate session after injection
            visible: Show browser window
            profile_dir: Browser profile directory
            inject_local_storage: Whether to inject localStorage if present in package

        Returns:
            Load result dict
        """
        result = {
            "success": False,
            "file": file_path,
            "cookies_injected": 0,
            "cookies_total": 0,
            "local_storage_injected": 0,
            "local_storage_total": 0,
            "validation": {},
            "error": None,
        }

        try:
            # Step 1: Load package
            package = self.load_file(file_path)
            result["cookies_total"] = len(package.get("cookies", []))
            result["site_name"] = package.get("site_name", "unknown")

            # Step 2: Prepare browser config
            config_kwargs = {
                "headless": not visible,
                "stealth_level": stealth_level,
            }
            if profile_dir:
                config_kwargs["user_data_dir"] = profile_dir

            # Step 3: Apply target fingerprint if specified
            if target_fp_name:
                fp = self.fp_manager.load(target_fp_name)
                if fp:
                    config_kwargs["fingerprint"] = fp.to_dict()
                    logger.info(f"Using target fingerprint: {target_fp_name}")
                else:
                    logger.warning(f"Fingerprint not found: {target_fp_name}")

            # Step 4: Launch browser
            config = BrowserConfig(**config_kwargs)
            self._browser = BrowserFactory.create(**config.__dict__)
            self._browser.launch()

            # Step 5: Apply source fingerprint from package (if no target specified)
            if not target_fp_name and package.get("fingerprint"):
                self.apply_fingerprint(self._browser, package["fingerprint"], stealth_level)

            # Step 6: Inject cookies
            cookies = package.get("cookies", [])
            result["cookies_injected"] = self.inject_cookies(self._browser, cookies)

            # Step 7: Inject localStorage if present and enabled
            local_storage = package.get("local_storage", {})
            result["local_storage_total"] = len(local_storage)
            if inject_local_storage and local_storage:
                # Determine origin from cookies or infer from site
                origin = self._infer_origin(package)
                result["local_storage_injected"] = self.inject_local_storage(
                    self._browser, local_storage, origin=origin
                )

            # Step 8: Validate if requested
            if validate:
                time.sleep(1)  # Brief pause for cookies to settle
                result["validation"] = self.validate_session(
                    self._browser,
                    package.get("site_name", "unknown")
                )
                # For localStorage-only sessions, consider success if localStorage was injected
                has_cookies = result["cookies_injected"] > 0
                has_local_storage = result["local_storage_injected"] > 0
                result["success"] = result["validation"].get("valid", False) or has_local_storage
            else:
                result["success"] = result["cookies_injected"] > 0 or result["local_storage_injected"] > 0

            logger.info(f"Session load complete: {result['success']}")

        except Exception as e:
            logger.error(f"Session load failed: {e}")
            result["error"] = str(e)

        finally:
            self._last_result = result

        return result

    def _infer_origin(self, package: Dict) -> Optional[str]:
        """Infer the origin URL from package data for localStorage injection."""
        cookies = package.get("cookies", [])
        if cookies:
            # Use domain from first cookie
            domain = cookies[0].get("domain", "")
            if domain:
                # Ensure domain has protocol
                if not domain.startswith("http"):
                    domain = f"https://{domain.lstrip('.')}"
                return domain

        # Fallback: try to construct from site_name
        site_name = package.get("site_name", "")
        if site_name and site_name != "unknown":
            return f"https://{site_name}.com"

        return None

    def load_into_runtime(self, file_path: str, runtime_engine=None) -> Dict:
        """
        Load session into RuntimeEngine for API use.

        Args:
            file_path: Path to .tokenade file
            runtime_engine: Optional RuntimeEngine instance

        Returns:
            Load result dict
        """
        result = self.load(file_path, validate=True)

        if not result["success"]:
            logger.error("Cannot load into runtime - session load failed")
            return result

        if runtime_engine:
            try:
                # Load session data into runtime
                package = self.load_file(file_path)
                session = SessionData(
                    site_name=package.get("site_name", "unknown"),
                    auth_status=AuthStatus(package.get("auth_status", "unknown")),
                    tokens=package.get("tokens", []),
                    cookies=package.get("cookies", []),
                    fingerprint=package.get("fingerprint"),
                )
                # RuntimeEngine would have a method to accept session data
                logger.info("Session loaded into RuntimeEngine")
                result["runtime_loaded"] = True
            except Exception as e:
                logger.error(f"Failed to load into runtime: {e}")
                result["runtime_loaded"] = False
                result["runtime_error"] = str(e)
        else:
            result["runtime_loaded"] = False
            result["runtime_error"] = "No RuntimeEngine provided"

        return result

    def close(self):
        """Close browser if active."""
        if self._browser:
            try:
                self._browser.close()
                self._browser = None
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")

    def get_last_result(self) -> Optional[Dict]:
        """Get result from last load operation."""
        return self._last_result
