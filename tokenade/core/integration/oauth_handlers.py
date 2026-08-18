"""
Concrete OAuth Automation site handlers for standard provider sign-in flows.

Provides:
- GoogleOAuthAutomation: Automates 'Sign in with Google' on third-party targets.
- GitHubOAuthAutomation: Automates 'Sign in with GitHub' on third-party targets.
"""

import logging
from typing import Any, Dict, List, Optional
from tokenade.plugin.oauth_automation import OAuthAutomationPlugin
from tokenade.plugin.api import PluginResult

logger = logging.getLogger(__name__)


class GoogleOAuthAutomation(OAuthAutomationPlugin):
    """
    Automates 'Sign in with Google' on third-party sites using an active Google session.
    """
    name = "google-oauth-automation"
    version = "1.0.0"
    description = "Automated Sign in with Google flow"
    oauth_button_selector = 'button:has-text("Sign in with Google"), button:has-text("Continue with Google"), [data-provider="google"]'
    account_chooser_email_selector = 'div[data-email], div[data-identifier], li[data-authuser]'
    continue_button_selectors = [
        'button:has-text("Continue")',
        'button:has-text("Allow")',
        'button:has-text("Next")',
        'button#submit_approve_access',
    ]

    def extract_session(self, browser_context: Any, url: str) -> PluginResult:
        pkg = self.export_target_session(browser_context, url)
        return PluginResult(success=True, data=pkg)

    def inject_session(self, browser_context: Any, session: dict) -> PluginResult:
        success = self.inject_source_session(browser_context, session)
        return PluginResult(success=success, data={"injected": success})

    def refresh_session(self, session: dict) -> PluginResult:
        return PluginResult(success=True, data={"session": session})

    def process(self, source_session: Dict[str, Any], target_url: str, output_path: Optional[str] = None) -> PluginResult:
        """Execute automated Google sign-in on target_url using donor source_session."""
        self.target_url = target_url
        context = self.launch_context(visible=False)
        if not context:
            return PluginResult(success=False, error="Failed to launch browser context")

        try:
            # 1. Inject donor Google cookies
            self.inject_source_session(context, source_session)

            # 2. Navigate to target URL
            page = context.new_page()
            self.navigate_guarded(page, target_url, wait_until="domcontentloaded", timeout=self.timeout_seconds * 1000)

            # 3. Click OAuth button if present
            try:
                page.click(self.oauth_button_selector, timeout=5000)
            except Exception:
                pass  # May already be on OAuth page or auto-redirecting

            # 4. Handle Google account selection if prompted
            try:
                page.wait_for_selector(self.account_chooser_email_selector, timeout=5000)
                page.click(self.account_chooser_email_selector)
            except Exception:
                pass

            # 5. Handle consent/continue prompts
            for sel in self.continue_button_selectors:
                try:
                    if page.is_visible(sel):
                        page.click(sel)
                except Exception:
                    pass

            page.wait_for_timeout(2000)

            # 6. Export resulting target session
            pkg = self.export_target_session(context, target_url, output_path=output_path)
            return PluginResult(success=True, data=pkg)
        except Exception as e:
            return PluginResult(success=False, error=str(e))
        finally:
            context.close()


class GitHubOAuthAutomation(OAuthAutomationPlugin):
    """
    Automates 'Sign in with GitHub' on third-party sites using an active GitHub session.
    """
    name = "github-oauth-automation"
    version = "1.0.0"
    description = "Automated Sign in with GitHub flow"
    oauth_button_selector = 'button:has-text("Sign in with GitHub"), button:has-text("Continue with GitHub"), [data-provider="github"]'
    continue_button_selectors = [
        'button[name="authorize"]',
        'button:has-text("Authorize")',
        'input[type="submit"][value="Authorize"]',
    ]

    def extract_session(self, browser_context: Any, url: str) -> PluginResult:
        pkg = self.export_target_session(browser_context, url)
        return PluginResult(success=True, data=pkg)

    def inject_session(self, browser_context: Any, session: dict) -> PluginResult:
        success = self.inject_source_session(browser_context, session)
        return PluginResult(success=success, data={"injected": success})

    def refresh_session(self, session: dict) -> PluginResult:
        return PluginResult(success=True, data={"session": session})

    def process(self, source_session: Dict[str, Any], target_url: str, output_path: Optional[str] = None) -> PluginResult:
        """Execute automated GitHub sign-in on target_url using donor source_session."""
        self.target_url = target_url
        context = self.launch_context(visible=False)
        if not context:
            return PluginResult(success=False, error="Failed to launch browser context")

        try:
            self.inject_source_session(context, source_session)

            page = context.new_page()
            self.navigate_guarded(page, target_url, wait_until="domcontentloaded", timeout=self.timeout_seconds * 1000)

            try:
                page.click(self.oauth_button_selector, timeout=5000)
            except Exception:
                pass

            for sel in self.continue_button_selectors:
                try:
                    if page.is_visible(sel):
                        page.click(sel)
                except Exception:
                    pass

            page.wait_for_timeout(2000)
            pkg = self.export_target_session(context, target_url, output_path=output_path)
            return PluginResult(success=True, data=pkg)
        except Exception as e:
            return PluginResult(success=False, error=str(e))
        finally:
            context.close()
