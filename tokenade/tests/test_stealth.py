"""
Unit tests for stealth script builder and injector.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tokenade.core.fingerprint.stealth import StealthScriptBuilder  # noqa: E402
from tokenade.core.fingerprint.injector import inject_stealth_script, validate_injection  # noqa: E402
from tokenade.core.fingerprint.manager import BrowserFingerprint  # noqa: E402


class TestStealthScriptBuilder(unittest.TestCase):
    """Test StealthScriptBuilder."""

    def setUp(self):
        self.fingerprint = BrowserFingerprint(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            platform="Win32",
            language="en-US",
            languages=["en-US", "en"],
            hardware_concurrency=8,
            device_memory=8.0,
            max_touch_points=0,
            screen_width=1920,
            screen_height=1080,
            color_depth=24,
            device_pixel_ratio=1.0,
            webgl_vendor="Intel Inc.",
            webgl_renderer="Intel Iris Xe",
            canvas_fingerprint="data:image/png;base64,test123",
            plugins=[{"name": "Chrome PDF Plugin"}]
        )
        self.builder = StealthScriptBuilder(self.fingerprint)

    def test_build_basic(self):
        """Test building script at basic level."""
        script = self.builder.build("basic")
        self.assertIn("navigator", script)
        self.assertIn("Mozilla/5.0", script)
        self.assertIn("Win32", script)
        self.assertIn("screen", script)
        self.assertIn("1920", script)
        self.assertIn("WebGL", script)
        self.assertIn("Intel Inc.", script)

    def test_build_maximum(self):
        """Test building script at maximum level."""
        script = self.builder.build("maximum")
        self.assertIn("navigator", script)
        self.assertIn("WebRTC", script)
        self.assertIn("Battery", script)
        self.assertIn("Audio", script)

    def test_build_includes_automation_cleanup(self):
        """Test that automation cleanup is included."""
        script = self.builder.build("basic")
        self.assertIn("webdriver", script)
        self.assertIn("cdc_", script)

    def test_build_canvas_spoof(self):
        """Test canvas spoofing is included when fingerprint present."""
        script = self.builder.build("basic")
        self.assertIn("toDataURL", script)
        self.assertIn("test123", script)

    def test_build_no_canvas_without_fingerprint(self):
        """Test canvas spoofing skipped when no fingerprint."""
        fp = BrowserFingerprint()
        builder = StealthScriptBuilder(fp)
        script = builder.build("basic")
        # Should not contain canvas spoofing
        self.assertNotIn("toDataURL", script)


class TestInjector(unittest.TestCase):
    """Test stealth script injection."""

    def setUp(self):
        self.fingerprint = BrowserFingerprint(
            user_agent="Mozilla/5.0",
            platform="Win32"
        )
        self.mock_browser = MagicMock()

    def test_inject_via_add_init_script(self):
        """Test injection via add_init_script."""
        self.mock_browser._context = MagicMock()
        self.mock_browser._context.add_init_script = MagicMock()

        result = inject_stealth_script(self.mock_browser, self.fingerprint)
        self.assertTrue(result)
        self.mock_browser._context.add_init_script.assert_called_once()

    def test_inject_via_evaluate_fallback(self):
        """Test fallback to evaluate injection."""
        self.mock_browser._context = None
        self.mock_browser.evaluate = MagicMock()

        result = inject_stealth_script(self.mock_browser, self.fingerprint)
        self.assertTrue(result)
        self.mock_browser.evaluate.assert_called_once()

    def test_inject_no_method_available(self):
        """Test failure when no injection method available."""
        mock_browser = MagicMock()
        mock_browser._context = None
        del mock_browser.evaluate

        result = inject_stealth_script(mock_browser, self.fingerprint)
        self.assertFalse(result)

    def test_validate_injection(self):
        """Test injection validation."""
        self.mock_browser.evaluate.return_value = {
            "webdriver": None,
            "userAgent": "Mozilla/5.0",
            "platform": "Win32",
            "hardwareConcurrency": 8,
            "screenWidth": 1920,
            "screenHeight": 1080,
            "devicePixelRatio": 1.0,
            "pluginsLength": 1,
            "chromeRuntime": False
        }

        result = validate_injection(self.mock_browser)
        self.assertTrue(result["valid"])
        self.assertTrue(result["webdriver_undefined"])

    def test_validate_injection_detected(self):
        """Test validation when webdriver still present."""
        self.mock_browser.evaluate.return_value = {
            "webdriver": True,
            "userAgent": "Mozilla/5.0"
        }

        result = validate_injection(self.mock_browser)
        self.assertFalse(result["valid"])


if __name__ == "__main__":
    unittest.main()
