"""
OAuth Automation Plugin - Base class for OAuth automation flows.

Provides infrastructure: CloakBrowser management, cookie injection,
session export. Each site plugin implements its own concrete flow.
"""

import json
import logging
import time
from abc import abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from tokenade.plugin.api import PluginResult
from tokenade.plugin.base import SiteHandlerPlugin

logger = logging.getLogger(__name__)


class OAuthAutomationPlugin(SiteHandlerPlugin):
    """
    Base class for OAuth automation plugins.

    Provides infrastructure: CloakBrowser management, cookie injection,
    session export. Does NOT define a concrete flow — each site plugin
    implements its own process() method.

    Subclasses MUST override:
        - target_url: The site to authenticate on
        - oauth_button_selector: CSS selector for the OAuth button
        - redirect_url_pattern: Regex for expected redirect URL
        - process(): The full automation flow
        - refresh_session(): Session refresh logic
    """

    # --- Must override (site-specific) ---
    target_url: str = ""
    oauth_button_selector: str = ""
    redirect_url_pattern: str = ""

    # --- Optional overrides ---
    account_chooser_email_selector: str = 'div[data-email], div[data-identifier]'
    continue_button_selectors: List[str] = [
        'button:has-text("Continue")',
        'button:has-text("Allow")',
        'button:has-text("Next")',
    ]
    logged_in_selectors: List[str] = []
    logged_out_selectors: List[str] = []
    post_oauth_actions: List[dict] = []
    target_cookie_domains: List[str] = []
    target_critical_cookies: List[str] = []
    timeout_seconds: int = 60

    def ensure_browser(self) -> bool:
        """
        Ensure browser is available; try CloakBrowser first, fall back to standard Playwright.

        Returns:
            True if browser is available
        """
        try:
            from tokenade.core.browser.stealth.cloak import CloakBrowserBackend
            cloak = CloakBrowserBackend()
            if cloak.is_available():
                logger.info("CloakBrowser is available")
                return True
            logger.info("CloakBrowser not available, will use standard Playwright")
            return True
        except ImportError:
            logger.info("CloakBrowser not installed, will use standard Playwright")
            return True
        except Exception as e:
            logger.warning(f"Failed to check CloakBrowser: {e}, will use standard Playwright")
            return True

    def launch_context(self, visible: bool = False) -> Any:
        """
        Launch browser with stealth, return Playwright BrowserContext.

        Tries CloakBrowser first, falls back to standard Playwright.

        Args:
            visible: Show browser window (for debugging)

        Returns:
            Playwright BrowserContext or None on failure
        """
        try:
            from tokenade.core.browser.stealth.cloak import CloakBrowserBackend
            cloak = CloakBrowserBackend()
            if cloak.is_available():
                context = cloak.launch_context(headless=not visible)
                logger.info("CloakBrowser context launched")
                return context
        except Exception:
            pass

        try:
            from tokenade.core.browser.manager import BrowserFactory, BrowserConfig
            config = BrowserConfig(
                browser_type='chromium',
                headless=not visible,
                stealth_level='maximum'
            )
            browser = BrowserFactory.create(**config.__dict__)
            browser.launch()
            logger.info("Standard Playwright browser launched")
            return browser
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            return None

    def inject_source_session(self, context: Any, session: dict) -> bool:
        """
        Inject source session cookies into browser context.

        Args:
            context: Playwright BrowserContext
            session: Session data dict with cookies

        Returns:
            True if cookies were injected
        """
        cookies = session.get("cookies", [])
        if not cookies:
            logger.warning("No cookies to inject")
            return False

        try:
            normalized_cookies = []
            for cookie in cookies:
                normalized = self._normalize_cookie_for_playwright(cookie)
                if normalized:
                    normalized_cookies.append(normalized)

            if not normalized_cookies:
                logger.warning("No valid cookies after normalization")
                return False

            context.add_cookies(normalized_cookies)
            logger.info(f"Injected {len(normalized_cookies)} source session cookies")
            return True
        except Exception as e:
            logger.error(f"Failed to inject cookies: {e}")
            return False

    def _normalize_cookie_for_playwright(self, cookie: dict) -> Optional[dict]:
        """Normalize cookie dict to Playwright format."""
        if "name" not in cookie or "value" not in cookie:
            return None

        normalized = {
            "name": cookie["name"],
            "value": cookie["value"],
            "domain": cookie.get("domain", ""),
            "path": cookie.get("path", "/"),
        }

        expires = cookie.get("expires")
        if expires and int(expires) > 0:
            expires_int = int(expires)
            if expires_int > 1262304000000:
                expires_int = expires_int // 1000
            if expires_int > 0:
                normalized["expires"] = expires_int

        secure = bool(cookie.get("secure"))
        http_only = bool(cookie.get("httpOnly"))
        same_site = cookie.get("sameSite", "")

        if same_site == "None":
            secure = True

        if secure:
            normalized["secure"] = True
        if http_only:
            normalized["httpOnly"] = True
        if same_site:
            normalized["sameSite"] = same_site

        return normalized

    def extract_email_from_session(self, session: dict) -> Optional[str]:
        """
        Extract email from .tokenade metadata.

        Args:
            session: Session data dict

        Returns:
            Email address or None
        """
        metadata = session.get("metadata", {})
        return metadata.get("email") or metadata.get("user_email")

    def verify_provider_session(self, page: Any, provider_url: str) -> bool:
        """
        Navigate to provider and verify we're logged in.

        Args:
            page: Playwright Page
            provider_url: Provider URL to check

        Returns:
            True if logged in
        """
        try:
            page.goto(provider_url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)

            current_url = page.url
            logged_out = any(
                p in current_url
                for p in ["/signin", "/login", "/accounts/signin", "/auth"]
            )

            if logged_out:
                logger.warning(f"Not logged in at {provider_url}")
                return False

            logger.info(f"Provider session verified at {provider_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to verify provider session: {e}")
            return False

    def export_target_session(
        self,
        context: Any,
        site_name: str,
        output_dir: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Extract target site cookies, package as .tokenade, return result.

        Args:
            context: Playwright BrowserContext
            site_name: Name of the target site
            output_dir: Output directory for .tokenade file

        Returns:
            Dict with session data and file path, or None on failure
        """
        try:
            if hasattr(context, 'get_cookies'):
                all_cookies = context.get_cookies()
            else:
                all_cookies = context.cookies()

            target_cookies = []
            for cookie in all_cookies:
                domain = cookie.get("domain", "")
                for d in self.target_cookie_domains:
                    if domain.endswith(d) or domain == d.lstrip("."):
                        target_cookies.append(cookie)
                        break

            if not self.target_critical_cookies:
                target_cookies_final = target_cookies
            else:
                target_cookies_final = [
                    c for c in target_cookies
                    if c.get("name") in self.target_critical_cookies
                ]

            if not target_cookies_final:
                target_cookies_final = target_cookies

            logger.info(f"Extracted {len(target_cookies_final)} target cookies")

            from tokenade.core.importer.session_packager import SessionPackager

            packager = SessionPackager()
            package = packager.package(
                cookies=target_cookies_final,
                browser="cloakbrowser",
                profile="default",
                local_storage=None,
            )

            package["site_name"] = site_name

            if output_dir:
                output_path = Path(output_dir)
                output_path.mkdir(parents=True, exist_ok=True)
                saved_path = packager.save(package, str(output_path / f"{site_name}_session"))
                logger.info(f"Session saved to: {saved_path}")
                package["_file_path"] = saved_path

            return package
        except Exception as e:
            logger.error(f"Failed to export target session: {e}")
            return None

    def decode_session_token(self, cookie_value: str) -> dict:
        """
        Decode JWE/JWT token from session cookie.

        Override in subclass for site-specific decoding.

        Args:
            cookie_value: Raw cookie value

        Returns:
            Decoded token dict
        """
        import base64

        parts = cookie_value.split(".")
        if len(parts) >= 2:
            try:
                payload = parts[1]
                padding = 4 - len(payload) % 4
                if padding != 4:
                    payload += "=" * padding
                decoded = base64.urlsafe_b64decode(payload)
                return json.loads(decoded)
            except Exception:
                pass
        return {}

    def save_session(self, session_data: dict, output_path: str) -> str:
        """
        Save session as .tokenade file via SessionPackager.

        Args:
            session_data: Session package dict
            output_path: Output path (without extension)

        Returns:
            Path to saved file
        """
        from tokenade.core.importer.session_packager import SessionPackager

        packager = SessionPackager()
        return packager.save(session_data, output_path)

    @abstractmethod
    def process(
        self,
        session_file: str,
        output_dir: Optional[str] = None,
    ) -> PluginResult:
        """
        Full automation flow. Each plugin implements this.

        Args:
            session_file: Path to source .tokenade file
            output_dir: Output directory for result

        Returns:
            PluginResult with session data
        """
        raise NotImplementedError

    @abstractmethod
    def refresh_session(self, session: dict) -> PluginResult:
        """
        Refresh an expired session. Each plugin implements this.

        Args:
            session: Old session data

        Returns:
            PluginResult with refreshed session
        """
        raise NotImplementedError
