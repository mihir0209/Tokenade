"""
Google Flow Plugin - OAuth automation for labs.google/fx/tools/flow.

Automates the OAuth flow using a stored Google session:
1. Load Google session cookies
2. Navigate to labs.google
3. Click "Create with Google Flow"
4. Handle Google account chooser
5. Wait for redirect back
6. Export labs.google session cookies
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

from tokenade.plugin.api import PluginResult
from tokenade.plugin.oauth_automation import OAuthAutomationPlugin

logger = logging.getLogger(__name__)


class GoogleFlowPlugin(OAuthAutomationPlugin):
    """
    OAuth automation plugin for labs.google/fx/tools/flow.

    Uses a stored Google session to authenticate on labs.google
    and export the resulting NextAuth session.
    """

    name = "google-flow-handler"
    version = "1.0.0"
    description = "OAuth automation for labs.google/fx/tools/flow"
    author = "MiHiR"
    dependencies = ["google-handler"]

    target_url = "https://labs.google/fx/tools/flow"
    oauth_button_selector = (
        'a[href*="accounts.google.com"], '
        'button:has-text("Create with Google"), '
        'button:has-text("Sign in with Google"), '
        '[data-provider="google"]'
    )
    redirect_url_pattern = r"labs\.google/fx/tools/flow.*"
    account_chooser_email_selector = 'div[data-email], div[data-identifier]'
    continue_button_selectors = [
        'button:has-text("Continue")',
        'button:has-text("Allow")',
        'button:has-text("Next")',
        '#submit_approve_access',
    ]
    logged_in_selectors = [
        'div.flow-editor',
        'a[href*="fx/tools/flow/create"]',
        'button:has-text("Create")',
    ]
    logged_out_selectors = [
        'a[href*="accounts.google.com"]',
        'button:has-text("Sign in")',
    ]
    target_cookie_domains = ["labs.google", ".labs.google"]
    target_critical_cookies = [
        "__Secure-next-auth.session-token",
        "EMAIL",
    ]

    def process(
        self,
        session_file: str,
        output_dir: Optional[str] = None,
    ) -> PluginResult:
        """
        Full OAuth flow for labs.google.

        Steps:
        1. Load source Google session
        2. Launch CloakBrowser
        3. Inject Google cookies
        4. Navigate to labs.google
        5. Click OAuth button
        6. Handle account chooser
        7. Wait for redirect
        8. Verify login
        9. Export session
        """
        try:
            package = self._load_session(session_file)
            if not package:
                return PluginResult(
                    success=False,
                    error="Failed to load session file"
                )

            email = self.extract_email_from_session(package)
            if not email:
                return PluginResult(
                    success=False,
                    error="No email in session metadata; re-export with latest tokenade"
                )

            if not self.ensure_browser():
                return PluginResult(
                    success=False,
                    error=(
                        "CloakBrowser not available. Install with: "
                        "pip install tokenade-cloakbrowser"
                    )
                )

            context = self.launch_context()
            if not context:
                return PluginResult(
                    success=False,
                    error="Failed to launch browser"
                )

            try:
                if not self.inject_source_session(context, package):
                    return PluginResult(
                        success=False,
                        error="Failed to inject Google session cookies"
                    )

                page = context.new_page()

                if not self.verify_provider_session(page, "https://accounts.google.com"):
                    return PluginResult(
                        success=False,
                        error="Google session expired; re-export from browser"
                    )

                result = self._execute_oauth_flow(page, context, email, output_dir)

                return result
            finally:
                context.close()

        except Exception as e:
            logger.error(f"OAuth flow failed: {e}")
            return PluginResult(
                success=False,
                error=str(e)
            )

    def _execute_oauth_flow(
        self,
        page: Any,
        context: Any,
        email: str,
        output_dir: Optional[str],
    ) -> PluginResult:
        """
        Execute the OAuth flow steps.
        """
        try:
            logger.info(f"Navigating to {self.target_url}")
            page.goto(self.target_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            if self._check_already_logged_in(page):
                logger.info("Already logged in on labs.google")
                return self._export_and_return(context, "labs_google", output_dir)

            clicked = self._click_oauth_button(page)
            if not clicked:
                return PluginResult(
                    success=False,
                    error="Could not find OAuth button on page"
                )

            time.sleep(3)

            self._handle_account_chooser(page, email)

            self._wait_for_redirect(page)

            if not self._check_already_logged_in(page):
                logger.warning("Login status uncertain after redirect")

            return self._export_and_return(context, "labs_google", output_dir)

        except Exception as e:
            logger.error(f"OAuth flow execution failed: {e}")
            return PluginResult(
                success=False,
                error=str(e)
            )

    def _load_session(self, session_file: str) -> Optional[dict]:
        """Load .tokenade session file."""
        try:
            path = Path(session_file)
            if not path.exists():
                logger.error(f"Session file not found: {session_file}")
                return None

            with open(path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load session file: {e}")
            return None

    def _check_already_logged_in(self, page: Any) -> bool:
        """Check if already logged in on target site."""
        for selector in self.logged_in_selectors:
            try:
                el = page.query_selector(selector)
                if el:
                    return True
            except Exception:
                pass
        return False

    def _click_oauth_button(self, page: Any) -> bool:
        """Click the OAuth sign-in button."""
        selectors = self.oauth_button_selector.split(", ")
        for selector in selectors:
            try:
                el = page.query_selector(selector.strip())
                if el:
                    el.click()
                    logger.info(f"Clicked OAuth button: {selector}")
                    return True
            except Exception:
                pass

        try:
            page.click(self.oauth_button_selector, timeout=5000)
            logger.info("Clicked OAuth button via Playwright")
            return True
        except Exception as e:
            logger.warning(f"Failed to click OAuth button: {e}")
            return False

    def _handle_account_chooser(self, page: Any, email: str) -> bool:
        """Handle Google account chooser if shown."""
        try:
            time.sleep(2)

            email_element = page.query_selector(
                f'{self.account_chooser_email_selector}:has-text("{email}")'
            )
            if email_element:
                email_element.click()
                logger.info(f"Selected account: {email}")
                return True

            for selector in self.continue_button_selectors:
                try:
                    el = page.query_selector(selector)
                    if el:
                        el.click()
                        logger.info(f"Clicked continue button: {selector}")
                        return True
                except Exception:
                    pass

            logger.info("No account chooser shown (single account)")
            return True

        except Exception as e:
            logger.warning(f"Account chooser handling failed: {e}")
            return False

    def _wait_for_redirect(self, page: Any) -> bool:
        """Wait for redirect back to target site."""
        try:
            start_time = time.time()
            while time.time() - start_time < self.timeout_seconds:
                current_url = page.url
                if re.search(self.redirect_url_pattern, current_url):
                    logger.info(f"Redirected to: {current_url}")
                    return True
                time.sleep(1)

            logger.warning("Redirect timeout")
            return False
        except Exception as e:
            logger.error(f"Redirect wait failed: {e}")
            return False

    def _export_and_return(
        self,
        context: Any,
        site_name: str,
        output_dir: Optional[str],
    ) -> PluginResult:
        """Export session and return result."""
        session = self.export_target_session(context, site_name, output_dir)
        if not session:
            return PluginResult(
                success=False,
                error="Failed to export target session"
            )

        jwt_data = {}
        cookies = session.get("cookies", [])
        for cookie in cookies:
            if cookie.get("name") == "__Secure-next-auth.session-token":
                jwt_data = self.decode_session_token(cookie.get("value", ""))
                break

        result_data = {
            "session": session,
            "session_file": str(session.get("_file_path", "")),
            "email": jwt_data.get("email", ""),
            "expires": jwt_data.get("exp", 0),
            "jwt": jwt_data,
        }

        logger.info(
            f"OAuth flow complete: email={result_data['email']}, "
            f"expires={result_data['expires']}"
        )

        return PluginResult(
            success=True,
            data=result_data,
        )

    def refresh_session(self, session: dict) -> PluginResult:
        """
        Refresh labs.google session by re-running OAuth.

        Args:
            session: Old session data with source Google cookies

        Returns:
            PluginResult with refreshed session
        """
        cookies = session.get("cookies", [])
        has_google_cookies = any(
            "google" in c.get("domain", "")
            for c in cookies
        )

        if not has_google_cookies:
            return PluginResult(
                success=False,
                error="No Google cookies in session; cannot refresh"
            )

        metadata = session.get("metadata", {})
        email = metadata.get("email")

        if not email:
            return PluginResult(
                success=False,
                error="No email in session metadata"
            )

        logger.info(f"Refreshing session for {email}")

        return self.process(
            session_file=metadata.get("source_file", ""),
            output_dir=metadata.get("output_dir"),
        )

    def extract_session(self, browser_context, url=""):
        """Extract session from browser context."""
        return self.export_target_session(browser_context, "labs_google")

    def inject_session(self, browser_context, session):
        """Inject session into browser context."""
        return self.inject_source_session(browser_context, session)
