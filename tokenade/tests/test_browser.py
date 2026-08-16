"""
Unit tests for browser manager module.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from tokenade.core.browser.manager import (  # noqa: E402
    BrowserConfig,
    BrowserManager,
    PlaywrightBrowserManager,
    BrowserFactory,
)


class TestBrowserConfig(unittest.TestCase):
    """Test BrowserConfig dataclass."""

    def test_defaults(self):
        """Test default configuration values."""
        config = BrowserConfig()
        self.assertEqual(config.browser_type, "cloakbrowser")
        self.assertTrue(config.headless)
        self.assertIsNone(config.user_data_dir)
        self.assertEqual(config.viewport, {"width": 1920, "height": 1080})

    def test_anti_detection_args(self):
        """Test anti-detection arguments are applied."""
        config = BrowserConfig()
        self.assertIn("--no-sandbox", config.args)
        self.assertIn("--disable-dev-shm-usage", config.args)
        self.assertIn("--disable-blink-features=AutomationControlled", config.args)
        self.assertIn("--enable-automation", config.ignore_default_args)

    def test_firefox_excludes_chromium_only_args(self):
        config = BrowserConfig(browser_type="firefox")
        self.assertNotIn("--no-sandbox", config.args)
        self.assertNotIn("--disable-blink-features=AutomationControlled", config.args)

    def test_custom_args(self):
        """Test custom args merge with defaults."""
        config = BrowserConfig(args=["--custom-flag"])
        self.assertIn("--custom-flag", config.args)
        self.assertIn("--no-sandbox", config.args)

    def test_no_sandbox_disabled(self):
        """Test disabling no_sandbox flag."""
        config = BrowserConfig(no_sandbox=False)
        self.assertNotIn("--no-sandbox", config.args)

    def test_user_data_dir(self):
        """Test user data directory configuration."""
        config = BrowserConfig(user_data_dir="/tmp/test-profile")
        self.assertEqual(config.user_data_dir, "/tmp/test-profile")


class TestBrowserFactory(unittest.TestCase):
    """Test BrowserFactory."""

    def test_create_playwright(self):
        """Test creating Playwright browser manager."""
        manager = BrowserFactory.create("playwright")
        self.assertIsInstance(manager, PlaywrightBrowserManager)

    def test_create_unknown_backend(self):
        """Test creating unknown backend raises error."""
        with self.assertRaises(ValueError) as ctx:
            BrowserFactory.create("selenium")
        self.assertIn("Unknown browser backend", str(ctx.exception))

    def test_register_backend(self):
        """Test registering custom backend."""
        class CustomManager(BrowserManager):
            def launch(self):
                pass

            def close(self):
                pass

            def get_cookies(self, urls=None):
                return []

            def add_cookies(self, cookies):
                pass

            def navigate(self, url, wait_until="networkidle", timeout=30000):
                pass

            def evaluate(self, expression):
                pass

        BrowserFactory.register("custom", CustomManager)
        manager = BrowserFactory.create("custom")
        self.assertIsInstance(manager, CustomManager)

    @patch("platform.system")
    @patch("os.path.exists")
    def test_detect_chrome_path_linux(self, mock_exists, mock_system):
        """Test Chrome detection on Linux."""
        mock_system.return_value = "Linux"
        mock_exists.side_effect = lambda p: p == "/usr/bin/google-chrome"
        path = BrowserFactory.detect_chrome_path()
        self.assertEqual(path, "/usr/bin/google-chrome")

    @patch("platform.system")
    @patch("os.path.exists")
    def test_detect_chrome_path_windows(self, mock_exists, mock_system):
        """Test Chrome detection on Windows."""
        mock_system.return_value = "Windows"
        mock_exists.return_value = False
        path = BrowserFactory.detect_chrome_path()
        self.assertIsNone(path)

    @patch("platform.system")
    @patch("os.path.exists")
    def test_detect_chrome_path_macos(self, mock_exists, mock_system):
        """Test Chrome detection on macOS."""
        mock_system.return_value = "Darwin"
        mock_exists.side_effect = lambda p: "Chrome" in p
        path = BrowserFactory.detect_chrome_path()
        self.assertIn("Google Chrome.app", path)


@unittest.skipUnless(HAS_PLAYWRIGHT, "playwright not installed")
class TestPlaywrightBrowserManager(unittest.TestCase):
    """Test PlaywrightBrowserManager with mocked Playwright."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = BrowserConfig(headless=True, force_playwright=True)
        self.manager = PlaywrightBrowserManager(self.config)

    def test_initial_state(self):
        """Test initial manager state."""
        self.assertFalse(self.manager.is_active)
        self.assertIsNone(self.manager._context)
        self.assertIsNone(self.manager._browser)
        self.assertIsNone(self.manager._playwright)

    @patch("playwright.sync_api.sync_playwright")
    def test_launch_success(self, mock_sync_playwright):
        """Test successful browser launch."""
        # Mock Playwright chain
        mock_playwright = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_sync_playwright.return_value.start.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        page = self.manager.launch()

        self.assertTrue(self.manager.is_active)
        self.assertEqual(page, mock_page)
        mock_playwright.chromium.launch.assert_called_once()

    @patch("playwright.sync_api.sync_playwright")
    def test_launch_persistent_context(self, mock_sync_playwright):
        """Test launch with persistent context."""
        config = BrowserConfig(user_data_dir="/tmp/test", headless=True, force_playwright=True)
        manager = PlaywrightBrowserManager(config)

        mock_playwright = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_sync_playwright.return_value.start.return_value = mock_playwright
        mock_playwright.chromium.launch_persistent_context.return_value = mock_context
        mock_context.pages = [mock_page]

        manager.launch()

        self.assertTrue(manager.is_active)
        mock_playwright.chromium.launch_persistent_context.assert_called_once()

    @patch("playwright.sync_api.sync_playwright")
    def test_launch_failure(self, mock_sync_playwright):
        """Test browser launch failure."""
        mock_sync_playwright.return_value.start.side_effect = Exception("Launch failed")

        with self.assertRaises(Exception) as ctx:
            self.manager.launch()
        self.assertIn("Launch failed", str(ctx.exception))

    @patch("playwright.sync_api.sync_playwright")
    def test_close(self, mock_sync_playwright):
        """Test browser cleanup."""
        mock_playwright = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()

        mock_sync_playwright.return_value.start.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = MagicMock()

        self.manager.launch()
        self.manager.close()

        self.assertFalse(self.manager.is_active)
        mock_context.close.assert_called_once()
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()

    @patch("playwright.sync_api.sync_playwright")
    def test_get_cookies(self, mock_sync_playwright):
        """Test getting cookies."""
        mock_playwright = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()

        mock_sync_playwright.return_value.start.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = MagicMock()
        mock_context.cookies.return_value = [{"name": "test", "value": "123"}]

        self.manager.launch()
        cookies = self.manager.get_cookies()

        self.assertEqual(len(cookies), 1)
        self.assertEqual(cookies[0]["name"], "test")
        mock_context.cookies.assert_called_once()

    def test_get_cookies_not_launched(self):
        """Test getting cookies without launch raises error."""
        with self.assertRaises(RuntimeError) as ctx:
            self.manager.get_cookies()
        self.assertIn("Browser not launched", str(ctx.exception))

    @patch("playwright.sync_api.sync_playwright")
    def test_add_cookies(self, mock_sync_playwright):
        """Test adding cookies."""
        mock_playwright = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()

        mock_sync_playwright.return_value.start.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = MagicMock()

        self.manager.launch()
        test_cookies = [{"name": "session", "value": "abc"}]
        self.manager.add_cookies(test_cookies)

        mock_context.add_cookies.assert_called_once_with(test_cookies)

    @patch("playwright.sync_api.sync_playwright")
    def test_navigate(self, mock_sync_playwright):
        """Test page navigation."""
        mock_page = MagicMock()
        mock_playwright = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()

        mock_sync_playwright.return_value.start.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        self.manager.launch()
        self.manager.navigate("https://example.com")

        mock_page.goto.assert_called_once_with(
            "https://example.com",
            wait_until="networkidle",
            timeout=30000,
        )

    @patch("playwright.sync_api.sync_playwright")
    def test_evaluate(self, mock_sync_playwright):
        """Test JavaScript evaluation."""
        mock_page = MagicMock()
        mock_page.evaluate.return_value = {"result": "ok"}

        mock_playwright = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()

        mock_sync_playwright.return_value.start.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        self.manager.launch()
        result = self.manager.evaluate("document.title")

        self.assertEqual(result, {"result": "ok"})
        mock_page.evaluate.assert_called_once_with("document.title")

    @patch("playwright.sync_api.sync_playwright")
    def test_query_selector(self, mock_sync_playwright):
        """Test element query."""
        mock_page = MagicMock()
        mock_element = MagicMock()
        mock_page.query_selector.return_value = mock_element

        mock_playwright = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()

        mock_sync_playwright.return_value.start.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        self.manager.launch()
        result = self.manager.query_selector("#test")

        self.assertEqual(result, mock_element)
        mock_page.query_selector.assert_called_once_with("#test")

    @patch("playwright.sync_api.sync_playwright")
    def test_click(self, mock_sync_playwright):
        """Test element click."""
        mock_element = MagicMock()
        mock_page = MagicMock()
        mock_page.wait_for_selector.return_value = mock_element

        mock_playwright = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()

        mock_sync_playwright.return_value.start.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        self.manager.launch()
        result = self.manager.click("#button")

        self.assertEqual(result, mock_element)
        mock_element.click.assert_called_once()

    @patch("playwright.sync_api.sync_playwright")
    def test_fill(self, mock_sync_playwright):
        """Test input fill."""
        mock_element = MagicMock()
        mock_page = MagicMock()
        mock_page.wait_for_selector.return_value = mock_element

        mock_playwright = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()

        mock_sync_playwright.return_value.start.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        self.manager.launch()
        result = self.manager.fill("#input", "test value")

        self.assertEqual(result, mock_element)
        mock_element.fill.assert_called_once_with("test value")


if __name__ == "__main__":
    unittest.main()
