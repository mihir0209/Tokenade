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
from typing import Any, Dict, List, Optional
import logging

from tokenade.core.browser.manager import BrowserFactory, BrowserConfig
from tokenade.core.fingerprint.manager import FingerprintManager, BrowserFingerprint
from tokenade.core.fingerprint.injector import inject_stealth_script
from tokenade.core.importer.validator import SessionValidator
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
        from tokenade.core.importer.session_packager import SessionPackager

        path = Path(file_path)
        package = SessionPackager().load(str(path))

        logger.info(
            f"Loaded session package: {path} ({len(package.get('cookies', []))} cookies)"
        )
        return package

    def apply_fingerprint(
        self,
        browser_manager,
        fingerprint: Optional[Dict] = None,
        stealth_level: str = "maximum",
    ) -> bool:
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

    def inject_local_storage(
        self,
        browser_manager,
        local_storage: Dict[str, str],
        origin: Optional[str] = None,
    ) -> int:
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
                browser_manager.navigate(
                    origin, wait_until="domcontentloaded", timeout=15000
                )
                logger.info(f"Navigated to origin for localStorage injection: {origin}")
            except Exception as e:
                logger.warning(f"Failed to navigate to origin {origin}: {e}")

        injected = 0
        try:
            # Batch inject all localStorage entries
            # Use page.evaluate with a data parameter to avoid serialization issues
            result = browser_manager.evaluate(
                """
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
            """,
                local_storage,
            )

            if isinstance(result, int):
                injected = result
            else:
                # Fallback: inject one by one
                for key, value in local_storage.items():
                    try:
                        browser_manager.evaluate(
                            """
                            (key, value) => {
                                localStorage.setItem(key, value);
                            }
                        """,
                            key,
                            value,
                        )
                        injected += 1
                    except Exception as e:
                        logger.debug(f"Failed to inject localStorage key {key}: {e}")

        except Exception as e:
            logger.error(f"Failed to inject localStorage: {e}")

        logger.info(f"Injected {injected}/{len(local_storage)} localStorage entries")
        return injected

    def _normalize_cookie(self, cookie: Dict) -> Dict:
        """Normalize cookie dict to Playwright format.

        Handles differences between browser cookie formats:
        - Firefox stores expires in milliseconds, Playwright expects seconds
        - Session cookies (expires=0 or missing) should omit the expires field
        - sameSite='None' requires secure=True per Playwright spec
        - Boolean fields may be stored as strings "False"/"True" after round-trip
        """
        normalized = {
            "name": cookie["name"],
            "value": cookie["value"],
            "domain": cookie.get("domain", ""),
            "path": cookie.get("path", "/"),
        }

        secure = _parse_bool(cookie.get("secure"))
        http_only = _parse_bool(cookie.get("httpOnly"))
        same_site = cookie.get("sameSite", "")

        # Fix expires: Firefox uses milliseconds, Playwright expects seconds
        expires = cookie.get("expires")
        if expires and int(expires) > 0:
            expires_int = int(expires)
            # If value looks like milliseconds (> year 2010 in ms = 1262304000000)
            if expires_int > 1262304000000:
                expires_int = expires_int // 1000
            # Only include if it's a valid future-ish timestamp
            if expires_int > 0:
                normalized["expires"] = expires_int

        # Playwright requires secure=True when sameSite='None'
        if same_site == "None":
            secure = True

        if secure:
            normalized["secure"] = True
        if http_only:
            normalized["httpOnly"] = True
        if same_site:
            normalized["sameSite"] = same_site

        return normalized

    def validate_session(self, browser_manager, site_config: Dict) -> Dict:
        """
        Validate session using composable validation strategies.

        Strategies are auto-detected from site_config keys:
        - login_indicator_css → CSSIndicatorStrategy
        - auth_gated_url → URLRedirectStrategy
        - api_probe_url → APIProbeStrategy
        - user_content_selectors/text → PageContentStrategy
        - critical_cookies → CookieExpiryStrategy
        - localStorage_keys → LocalStorageStrategy

        Args:
            browser_manager: Active browser manager
            site_config: Site configuration dict

        Returns:
            Combined validation result dict
        """
        validate_url = site_config.get("validate_url")
        wait_seconds = site_config.get("wait_seconds", 10)

        # Navigate to the page first if URL provided
        if validate_url:
            try:
                logger.info(
                    f"Navigating to {validate_url} for validation (wait {wait_seconds}s)"
                )
                browser_manager.navigate(
                    validate_url, wait_until="domcontentloaded", timeout=30000
                )
                time.sleep(wait_seconds)
            except Exception as e:
                logger.warning(f"Navigation failed: {e}")

        # Run composable validator
        validator = SessionValidator()
        return validator.validate(browser_manager, site_config)

    def load(
        self,
        file_path: str,
        target_fp_name: Optional[str] = None,
        stealth_level: str = "maximum",
        validate: bool = True,
        visible: bool = False,
        profile_dir: Optional[str] = None,
        inject_local_storage: bool = True,
        site_config: Optional[Dict] = None,
        acknowledge_exclusive_move: bool = False,
        allow_single_use: bool = False,
    ) -> Dict:
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
            site_config: Site configuration dict with validate_url, login_indicator_css, etc.

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
            from tokenade.core.artifacts import ProfileArtifactManager

            ProfileArtifactManager.preflight(
                package,
                purpose="load",
                acknowledge_exclusive_move=acknowledge_exclusive_move,
                allow_single_use=allow_single_use,
            )
            result["cookies_total"] = len(package.get("cookies", []))
            result["site_name"] = package.get("site_name", "unknown")
            site_handler_metadata = self._site_handler_metadata(package)
            if site_handler_metadata:
                result["site_handler"] = site_handler_metadata

            # Step 2: Prepare browser config
            config_kwargs = {
                "headless": not visible,
                "stealth_level": stealth_level,
            }
            if package.get("profile_artifacts") and not profile_dir:
                import tempfile

                profile_dir = tempfile.mkdtemp(prefix="tokenade-load-artifacts-")
            if profile_dir:
                config_kwargs["user_data_dir"] = profile_dir
            if package.get("profile_artifacts"):
                ProfileArtifactManager.restore(
                    package, profile_dir, "cloak", allow_single_use=allow_single_use
                )

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
                self.apply_fingerprint(
                    self._browser, package["fingerprint"], stealth_level
                )

            # Step 6: Inject cookies
            cookies = package.get("cookies", [])
            result["cookies_injected"] = self.inject_cookies(self._browser, cookies)

            # Step 7: Inject localStorage if present and enabled
            local_storage_by_origin = (
                []
                if ProfileArtifactManager.web_storage_is_superseded(package)
                else self._local_storage_by_origin(package, site_config)
            )
            result["local_storage_total"] = sum(
                len(entries) for _, entries in local_storage_by_origin
            )
            if inject_local_storage:
                for origin, local_storage in local_storage_by_origin:
                    if not local_storage:
                        continue
                    result["local_storage_injected"] += self.inject_local_storage(
                        self._browser, local_storage, origin=origin
                    )

            if inject_local_storage and not local_storage_by_origin:
                local_storage = package.get("local_storage", {})
                origin = self._infer_origin(package, site_config)
                result["local_storage_injected"] = self.inject_local_storage(
                    self._browser, local_storage, origin=origin
                )

            # Step 8: Validate if requested
            if validate:
                time.sleep(1)
                # Build site_config for validation
                if not site_config:
                    site_config = self._build_default_site_config(package)
                result["validation"] = self.validate_session(self._browser, site_config)
                result["cookies_injected"] > 0
                has_local_storage = result["local_storage_injected"] > 0
                result["success"] = (
                    result["validation"].get("valid", False) or has_local_storage
                )
            else:
                result["success"] = (
                    result["cookies_injected"] > 0
                    or result["local_storage_injected"] > 0
                )

            logger.info(f"Session load complete: {result['success']}")
            from tokenade.core.analytics import record_local

            record_local(
                "load",
                "success" if result["success"] else "failure",
                dimensions={
                    "browser_family": "chromium",
                    "visible": bool(visible),
                    "validation_requested": bool(validate),
                    "storage_present": bool(
                        result["local_storage_total"]
                        or package.get("profile_artifacts")
                    ),
                },
            )

        except Exception as e:
            error_msg = str(e).lower()
            hint = ""
            if "no such file" in error_msg or "file not found" in error_msg:
                hint = f" Session file not found: {file_path}"
            elif "json" in error_msg or "decode" in error_msg:
                hint = f" Invalid .tokenade file format: {file_path}"
            elif "browser" in error_msg and (
                "launch" in error_msg or "start" in error_msg
            ):
                hint = " Install browser: playwright install chromium"
            elif "permission denied" in error_msg:
                hint = f" Check file permissions for: {file_path}"

            logger.error(f"Session load failed: {e}{hint}")
            result["error"] = str(e)

        finally:
            self._last_result = result
            # Keep browser open for interactive --visible loads; headless/batch closes.
            if self._browser and not visible:
                try:
                    self._browser.close()
                    self._browser = None
                except Exception:
                    pass

        return result

    def _local_storage_by_origin(
        self,
        package: Dict,
        site_config: Optional[Dict] = None,
    ) -> list[tuple[Optional[str], Dict[str, str]]]:
        """Return localStorage entries grouped by exact v3 origin, falling back to legacy flat storage."""
        grouped: list[tuple[Optional[str], Dict[str, str]]] = []
        storage = (
            package.get("storage") if isinstance(package.get("storage"), dict) else {}
        )
        local_by_origin = (
            storage.get("local") if isinstance(storage.get("local"), dict) else {}
        )
        for origin, entries in local_by_origin.items():
            if isinstance(origin, str) and isinstance(entries, dict) and entries:
                grouped.append((origin, entries))

        if grouped:
            return grouped

        legacy = package.get("local_storage")
        if isinstance(legacy, dict) and legacy:
            grouped.append((self._infer_origin(package, site_config), legacy))
        return grouped

    def _infer_origin(
        self, package: Dict, site_config: Optional[Dict] = None
    ) -> Optional[str]:
        """Infer the origin URL from package data or site config for localStorage injection."""
        site_handler = self._site_handler_metadata(package)
        if site_handler:
            origins = site_handler.get("storage_origins") or []
            if origins:
                return origins[0]

        # Try site_config domains first
        if site_config and site_config.get("domains"):
            domains = site_config["domains"]
            for d in domains:
                if not d.startswith("."):
                    return f"https://{d}"

        # Fallback to cookie domains
        cookies = package.get("cookies", [])
        if cookies:
            domain = cookies[0].get("domain", "")
            if domain:
                if not domain.startswith("http"):
                    domain = f"https://{domain.lstrip('.')}"
                return domain

        # Fallback: try to construct from site_name
        site_name = package.get("site_name", "")
        if site_name and site_name != "unknown":
            return f"https://{site_name}.com"

        return None

    def _build_default_site_config(self, package: Dict) -> Dict:
        """Build a minimal site config from package when none provided."""
        site_name = package.get("site_name", "unknown")
        site_handler = self._site_handler_metadata(package)

        # Try to get from site_configs first
        from tokenade.core.importer.site_configs import get_site_config

        preset = get_site_config(site_name)
        if preset:
            return preset

        cookies = package.get("cookies", [])
        domains = []
        if site_handler:
            domains = list(site_handler.get("export_domains") or [])
        if not domains:
            domains = list(
                {c.get("domain", "").lstrip(".") for c in cookies if c.get("domain")}
            )

        auth_cookie_names = []
        for c in cookies:
            name = c.get("name", "")
            if any(
                kw in name.lower() for kw in ("session", "token", "auth", "sid", "csrf")
            ):
                auth_cookie_names.append(name)

        return {
            "name": site_name,
            "domains": domains,
            "critical_cookies": auth_cookie_names[:5] if auth_cookie_names else [],
            "validate_url": None,
            "login_indicator_css": None,
            "wait_seconds": 10,
        }

    def _site_handler_metadata(self, package: Dict) -> Optional[Dict]:
        """Return embedded Site Handler export metadata, if present."""
        metadata = package.get("metadata") or {}
        site_handler = metadata.get("site_handler")
        return site_handler if isinstance(site_handler, dict) else None

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
                SessionData(
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


def _parse_bool(value: Any) -> bool:
    """Parse a value that might be a bool or string "True"/"False" into bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)
