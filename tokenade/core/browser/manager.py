"""
Browser Manager - Core abstraction for browser lifecycle management.

Provides a unified interface for launching, managing, and closing
browser instances across different platforms and browser types.
"""

import os
import platform
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

CHALLENGE_CLEARANCE_COOKIES = {"cf_clearance", "datadome"}


@dataclass
class BrowserConfig:
    """Configuration for browser launch."""
    # Default automation engine is CloakBrowser (chromium-compatible).
    # Use browser_type="playwright"/"chromium" only as explicit override/fallback.
    browser_type: str = "cloakbrowser"  # cloakbrowser, chromium, firefox, webkit
    headless: bool = True
    user_data_dir: Optional[str] = None
    executable_path: Optional[str] = None
    channel: Optional[str] = None  # chrome, msedge, etc.
    viewport: Dict[str, int] = field(default_factory=lambda: {"width": 1920, "height": 1080})
    args: List[str] = field(default_factory=list)
    ignore_default_args: List[str] = field(default_factory=list)
    env: Optional[Dict[str, str]] = None
    proxy: Optional[Dict[str, str]] = None
    force_playwright: bool = False  # skip CloakBrowser even if available

    # Anti-detection flags
    disable_blink_features: bool = True
    no_sandbox: bool = True
    disable_dev_shm_usage: bool = True
    no_first_run: bool = True
    no_default_browser_check: bool = True

    # Fingerprint spoofing
    fingerprint: Optional[Dict] = None
    stealth_level: str = "maximum"  # basic, advanced, maximum

    # Challenge mitigation (Cloudflare/DataDome auto-solve after navigation)
    auto_solve_challenges: bool = True
    # Persist cleared artifacts (cf_clearance, tokens) into a .tokenade file
    capture_solved_sessions: bool = False
    session_output_dir: Optional[str] = None

    def __post_init__(self):
        """Apply default anti-detection args if not overridden."""
        default_args = []
        chromium_family = self.browser_type not in ("firefox", "webkit")
        if self.no_sandbox and chromium_family:
            default_args.append("--no-sandbox")
        if self.disable_dev_shm_usage and chromium_family:
            default_args.append("--disable-dev-shm-usage")
        if self.no_first_run and chromium_family:
            default_args.append("--no-first-run")
        if self.no_default_browser_check and chromium_family:
            default_args.append("--no-default-browser-check")
        if self.disable_blink_features and chromium_family:
            default_args.append("--disable-blink-features=AutomationControlled")

        # Merge with user args (user args take precedence)
        existing = set(self.args)
        for arg in default_args:
            if arg.split("=")[0] not in {a.split("=")[0] for a in existing}:
                self.args.append(arg)

        if "--enable-automation" not in self.ignore_default_args:
            self.ignore_default_args.append("--enable-automation")


class BrowserManager(ABC):
    """
    Abstract base class for browser management.

    Implementations handle specific browser automation backends
    (Playwright, Selenium, etc.)
    """

    def __init__(self, config: BrowserConfig):
        self.config = config
        self._context = None
        self._browser = None
        self._playwright = None

    @abstractmethod
    def launch(self) -> Any:
        """Launch browser and return context/page handle."""

    @abstractmethod
    def close(self):
        """Close browser and cleanup resources."""

    @abstractmethod
    def get_cookies(self, urls: Optional[List[str]] = None) -> List[Dict]:
        """Get cookies from browser context."""

    @abstractmethod
    def add_cookies(self, cookies: List[Dict]):
        """Add cookies to browser context."""

    @abstractmethod
    def navigate(self, url: str, wait_until: str = "networkidle", timeout: int = 30000) -> Any:
        """Navigate to URL and return response."""

    @abstractmethod
    def evaluate(self, expression: str) -> Any:
        """Evaluate JavaScript in browser context."""

    @property
    def is_active(self) -> bool:
        """Check if browser context is active."""
        return self._context is not None


class PlaywrightBrowserManager(BrowserManager):
    """
    Playwright-based browser manager implementation.
    Production-grade with proper error handling and resource management.
    """

    def __init__(self, config: BrowserConfig):
        super().__init__(config)
        self._page = None
        self._uses_cloak = False

    def launch(self) -> Any:
        """Launch browser: CloakBrowser first (default), Playwright fallback."""
        try:
            return self._launch_impl()
        except Exception as e:
            error_msg = str(e).lower()
            hint = ""
            if "executable path" in error_msg or "not found" in error_msg:
                hint = " Install: tokenade cloak install  OR  playwright install chromium"
            elif "timeout" in error_msg:
                hint = " Browser launch timed out. Try closing other browser instances."
            elif "already connected" in error_msg or "address in use" in error_msg:
                hint = " Port in use. Try a different port or close conflicting processes."
            elif "permission denied" in error_msg:
                hint = " Check file permissions for browser profile directory."
            elif "playwright" in error_msg and "not installed" in error_msg:
                hint = " Run: pip install playwright && playwright install chromium"
            elif "cloak" in error_msg:
                hint = " Install: pip install cloakbrowser && tokenade cloak install"

            logger.error(f"Failed to launch browser ({self.config.browser_type}): {e}{hint}")
            self.close()
            raise

    def _prefer_cloak(self) -> bool:
        if self.config.force_playwright:
            return False
        if self.config.browser_type in ("firefox", "webkit"):
            return False
        # cloakbrowser / chromium / chrome → try Cloak first
        return self.config.browser_type in (
            "cloakbrowser", "cloak", "chromium", "chrome", "default", ""
        )

    def _launch_impl(self) -> Any:
        if self._prefer_cloak():
            try:
                from tokenade.core.browser.stealth.cloak import CloakBrowserBackend
                backend = CloakBrowserBackend()
                if backend.is_available():
                    proxy = None
                    if self.config.proxy:
                        proxy = self.config.proxy.get("server") or self.config.proxy
                    if self.config.user_data_dir:
                        self._context = backend.launch_persistent(
                            profile_dir=self.config.user_data_dir,
                            headless=self.config.headless,
                            proxy=proxy,
                            args=self.config.args or None,
                        )
                        self._page = (
                            self._context.pages[0]
                            if self._context.pages
                            else self._context.new_page()
                        )
                    else:
                        self._browser = backend.launch(
                            headless=self.config.headless,
                            proxy=proxy,
                            args=self.config.args or None,
                        )
                        context_options = {"viewport": self.config.viewport}
                        self._context = self._browser.new_context(**context_options)
                        self._page = self._context.new_page()
                    logger.info(
                        "Browser launched via CloakBrowser, headless=%s",
                        self.config.headless,
                    )
                    self._uses_cloak = True
                    return self._page
            except Exception as e:
                logger.warning("CloakBrowser launch failed, falling back to Playwright: %s", e)

        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()

        launch_options = {
            "headless": self.config.headless,
            "args": self.config.args,
            "ignore_default_args": self.config.ignore_default_args,
        }

        if self.config.executable_path:
            launch_options["executable_path"] = self.config.executable_path
        if self.config.channel:
            launch_options["channel"] = self.config.channel
        if self.config.proxy:
            launch_options["proxy"] = self.config.proxy

        pw_type = self.config.browser_type
        if pw_type in ("cloakbrowser", "cloak", "chrome", "playwright", "default", ""):
            pw_type = "chromium"
        browser_type = getattr(self._playwright, pw_type)

        if self.config.user_data_dir:
            self._context = browser_type.launch_persistent_context(
                user_data_dir=self.config.user_data_dir,
                **launch_options
            )
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        else:
            self._browser = browser_type.launch(**launch_options)
            context_options = {
                "viewport": self.config.viewport,
            }
            if self.config.env:
                context_options["env"] = self.config.env
            self._context = self._browser.new_context(**context_options)
            self._page = self._context.new_page()

        if self.config.fingerprint:
            try:
                from ..fingerprint.injector import inject_stealth_script
                from ..fingerprint.manager import BrowserFingerprint

                if isinstance(self.config.fingerprint, dict):
                    fingerprint = BrowserFingerprint.from_dict(self.config.fingerprint)
                else:
                    fingerprint = self.config.fingerprint

                inject_stealth_script(self, fingerprint, self.config.stealth_level)
                logger.info(f"Stealth script injected at level: {self.config.stealth_level}")
            except Exception as e:
                logger.warning(f"Failed to inject stealth script: {e}")

        logger.info(
            "Browser launched via Playwright: %s, headless=%s",
            pw_type,
            self.config.headless,
        )
        return self._page

    def close(self):
        """Close browser and cleanup Playwright."""
        try:
            if self._context:
                self._context.close()
                self._context = None
            if self._browser:
                self._browser.close()
                self._browser = None
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
            logger.info("Browser closed and resources cleaned up")
        except Exception as e:
            logger.warning(f"Error during browser cleanup: {e}")

    def get_cookies(self, urls: Optional[List[str]] = None) -> List[Dict]:
        """Get cookies from browser context."""
        if not self._context:
            raise RuntimeError("Browser not launched")
        return self._context.cookies(urls)

    def add_cookies(self, cookies: List[Dict]):
        """Add cookies to browser context."""
        if not self._context:
            raise RuntimeError("Browser not launched")
        self._context.add_cookies(cookies)

    def navigate(self, url: str, wait_until: str = "networkidle", timeout: int = 30000) -> Any:
        """Navigate to URL, auto-clearing anti-bot challenges when CloakBrowser is active."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        capture_implicit = (
            self.config.auto_solve_challenges
            and self._uses_cloak
            and self.config.capture_solved_sessions
        )
        clearance_before = self._clearance_cookies(url) if capture_implicit else set()
        response = self._page.goto(url, wait_until=wait_until, timeout=timeout)
        if self.config.auto_solve_challenges and self._uses_cloak:
            try:
                from tokenade.core.browser.challenge_guard import ChallengeGuard
                result = ChallengeGuard(self._page).try_mitigate(url, settle_s=1.0)
                if result is not None:
                    solved = bool(result.success and result.data.get("solved"))
                    logger.info(
                        "Challenge mitigation for %s: solved=%s method=%s",
                        url, solved, result.data.get("method"),
                    )
                    if solved and self.config.capture_solved_sessions:
                        self._capture_solved_session(url, result)
                elif self.config.capture_solved_sessions:
                    clearance_after = self._clearance_cookies(url)
                    if clearance_after - clearance_before:
                        from tokenade.plugin.api import PluginResult
                        implicit_result = PluginResult(
                            success=True,
                            data={
                                "solved": True,
                                "method": "cloakbrowser_load",
                                "provider": self._provider_for_clearance(clearance_after),
                                "elapsed_s": 0,
                            },
                        )
                        self._capture_solved_session(url, implicit_result)
            except Exception as e:
                logger.warning("Challenge mitigation failed for %s: %s", url, e)
        return response

    def _clearance_cookies(self, url: str) -> set:
        """Return clearance cookie name/value pairs scoped to a URL."""
        if not self._context:
            return set()
        try:
            return {
                (cookie.get("name"), cookie.get("value"))
                for cookie in self._context.cookies(url)
                if cookie.get("name") in CHALLENGE_CLEARANCE_COOKIES
            }
        except Exception:
            return set()

    @staticmethod
    def _provider_for_clearance(cookies: set) -> str:
        names = {name for name, _value in cookies}
        if "cf_clearance" in names:
            return "cloudflare"
        if "datadome" in names:
            return "datadome"
        return ""

    def _capture_solved_session(self, url: str, solver_result: Any) -> Optional[str]:
        """Persist the solved page's cookies/tokens into a .tokenade file."""
        try:
            from tokenade.core.integration.challenge_capture import SolvedSessionCapturer
            capturer = SolvedSessionCapturer(
                output_dir=self.config.session_output_dir,
                encrypt=None,
            )
            path = capturer.capture(self._page, url, solver_result)
            return str(path) if path else None
        except Exception as e:
            logger.warning("Session capture failed for %s: %s", url, e)
            return None

    def evaluate(self, expression: str) -> Any:
        """Evaluate JavaScript."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        return self._page.evaluate(expression)

    def evaluate_with_arg(self, expression: str, arg: Any) -> Any:
        """Evaluate JavaScript with an argument."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        return self._page.evaluate(expression, arg)

    def query_selector(self, selector: str, timeout: Optional[int] = None):
        """Query element on page."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        if timeout:
            return self._page.wait_for_selector(selector, timeout=timeout)
        return self._page.query_selector(selector)

    def click(self, selector: str, timeout: int = 5000):
        """Click element on page."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        element = self._page.wait_for_selector(selector, timeout=timeout)
        if element:
            element.click()
        return element

    def fill(self, selector: str, value: str, timeout: int = 5000):
        """Fill input field."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        element = self._page.wait_for_selector(selector, timeout=timeout)
        if element:
            element.fill(value)
        return element


class BrowserFactory:
    """Factory for creating browser managers."""

    _registry: Dict[str, type] = {
        "playwright": PlaywrightBrowserManager,
    }

    @classmethod
    def register(cls, name: str, manager_class: type):
        """Register a new browser manager implementation."""
        cls._registry[name] = manager_class

    @classmethod
    def create(cls, backend: str = "playwright", **config_kwargs) -> BrowserManager:
        """Create browser manager instance.

        Default path uses PlaywrightBrowserManager which prefers CloakBrowser
        when available (unless force_playwright=True or browser_type is firefox/webkit).
        """
        if backend in ("cloak", "cloakbrowser"):
            backend = "playwright"
            config_kwargs.setdefault("browser_type", "cloakbrowser")
        if backend not in cls._registry:
            raise ValueError(f"Unknown browser backend: {backend}. Available: {list(cls._registry.keys())}")

        config = BrowserConfig(**config_kwargs)
        return cls._registry[backend](config)

    @classmethod
    def detect_chrome_path(cls) -> Optional[str]:
        """Auto-detect Chrome executable path based on OS."""
        os_type = platform.system()

        paths = {
            "Windows": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            ],
            "Linux": [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
            ],
            "Darwin": [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ],
        }

        for path in paths.get(os_type, []):
            if os.path.exists(path):
                return path
        return None
