"""
Unit tests for fingerprint management module.
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tokenade.core.fingerprint.manager import (
    BrowserFingerprint,
    FingerprintManager,
    FingerprintCollector,
)


class TestBrowserFingerprint(unittest.TestCase):
    """Test BrowserFingerprint dataclass."""

    def test_creation(self):
        """Test basic creation with defaults."""
        fp = BrowserFingerprint(
            user_agent="Mozilla/5.0",
            screen_width=1920,
            screen_height=1080,
        )
        self.assertEqual(fp.user_agent, "Mozilla/5.0")
        self.assertEqual(fp.screen_width, 1920)
        self.assertEqual(fp.device_pixel_ratio, 1.0)
        self.assertEqual(fp.language, "en-US")

    def test_serialization(self):
        """Test JSON serialization roundtrip."""
        fp = BrowserFingerprint(
            user_agent="Mozilla/5.0",
            screen_width=1920,
            screen_height=1080,
            viewport_width=1920,
            viewport_height=969,
            platform="Linux x86_64",
            language="en-US",
            timezone="Asia/Calcutta",
            hardware_concurrency=8,
            device_memory=8.0,
            color_depth=24,
            device_pixel_ratio=1.0,
            max_touch_points=0,
            webgl_vendor="Intel Inc.",
            webgl_renderer="Intel Iris Xe",
            fonts=["Arial", "Times"],
            plugins=[{"name": "Chrome PDF Plugin"}],
            canvas_fingerprint="abc123",
        )
        json_str = fp.to_json()
        self.assertIn("Mozilla/5.0", json_str)
        self.assertIn("1920", json_str)

        restored = BrowserFingerprint.from_json(json_str)
        self.assertEqual(restored.user_agent, "Mozilla/5.0")
        self.assertEqual(restored.screen_width, 1920)
        self.assertEqual(restored.fonts, ["Arial", "Times"])

    def test_to_playwright_context(self):
        """Test conversion to Playwright context options."""
        fp = BrowserFingerprint(
            user_agent="Mozilla/5.0",
            screen_width=1920,
            screen_height=1080,
            viewport_width=1366,
            viewport_height=768,
            language="en-US",
            timezone="America/New_York",
            color_depth=24,
            device_pixel_ratio=2.0,
            max_touch_points=1,
        )
        ctx = fp.to_playwright_context()
        self.assertEqual(ctx["user_agent"], "Mozilla/5.0")
        self.assertEqual(ctx["viewport"]["width"], 1366)
        self.assertEqual(ctx["viewport"]["height"], 768)
        self.assertEqual(ctx["locale"], "en-US")
        self.assertEqual(ctx["timezone_id"], "America/New_York")
        self.assertEqual(ctx["device_scale_factor"], 2.0)
        self.assertTrue(ctx["has_touch"])

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "user_agent": "Test/1.0",
            "screen_width": 1920,
            "screen_height": 1080,
        }
        fp = BrowserFingerprint.from_dict(data)
        self.assertEqual(fp.user_agent, "Test/1.0")
        self.assertEqual(fp.screen_width, 1920)


class TestFingerprintManager(unittest.TestCase):
    """Test FingerprintManager storage operations."""

    def setUp(self):
        """Create temporary directory for tests."""
        self.test_dir = Path("test_fingerprints")
        self.test_dir.mkdir(exist_ok=True)
        self.manager = FingerprintManager(str(self.test_dir))

    def tearDown(self):
        """Clean up test directory."""
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_save_and_load(self):
        """Test saving and loading fingerprints."""
        fp = BrowserFingerprint(
            user_agent="Test/1.0",
            screen_width=1920,
            screen_height=1080,
        )
        path = self.manager.save("test_fp", fp)
        self.assertTrue(Path(path).exists())

        loaded = self.manager.load("test_fp")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.user_agent, "Test/1.0")

    def test_load_nonexistent(self):
        """Test loading non-existent fingerprint."""
        result = self.manager.load("nonexistent")
        self.assertIsNone(result)

    def test_delete(self):
        """Test deleting fingerprints."""
        fp = BrowserFingerprint(user_agent="Test/1.0", screen_width=1920, screen_height=1080)
        self.manager.save("to_delete", fp)
        self.assertTrue(self.manager.delete("to_delete"))
        self.assertIsNone(self.manager.load("to_delete"))

    def test_delete_nonexistent(self):
        """Test deleting non-existent fingerprint."""
        self.assertFalse(self.manager.delete("nonexistent"))

    def test_list(self):
        """Test listing fingerprints."""
        fp = BrowserFingerprint(user_agent="Test/1.0", screen_width=1920, screen_height=1080)
        self.manager.save("fp1", fp)
        self.manager.save("fp2", fp)

        names = self.manager.list()
        self.assertEqual(len(names), 2)
        self.assertIn("fp1", names)
        self.assertIn("fp2", names)


class TestFingerprintCollector(unittest.TestCase):
    """Test FingerprintCollector."""

    def test_collect_from_browser(self):
        """Test collecting fingerprint from browser."""
        mock_browser = MagicMock()
        # Playwright evaluate returns Python dicts for JS objects, not JSON strings
        mock_browser.evaluate.side_effect = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",  # userAgent
            {
                "width": 1920,
                "height": 1080,
                "availWidth": 1920,
                "availHeight": 1040,
                "colorDepth": 24,
                "pixelRatio": 1.0,
            },  # screen info
            {
                "width": 1920,
                "height": 969,
            },  # viewport
            "Win32",  # platform
            "en-US",  # language
            ["en-US", "en"],  # languages
            "America/New_York",  # timezone
            300,  # timezone offset
            8,  # hardwareConcurrency
            8.0,  # deviceMemory
            0,  # maxTouchPoints
            {
                "vendor": "Google Inc.",
                "renderer": "ANGLE (Intel, Intel Iris Xe",
            },  # webgl
            [{"name": "Chrome PDF Plugin"}],  # plugins
        ]

        fp = FingerprintCollector.collect_from_browser(mock_browser)

        self.assertEqual(fp.user_agent, "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        self.assertEqual(fp.screen_width, 1920)
        self.assertEqual(fp.hardware_concurrency, 8)
        self.assertEqual(fp.timezone, "America/New_York")

    def test_collect_browser_error(self):
        """Test graceful handling of browser errors."""
        mock_browser = MagicMock()
        mock_browser.evaluate.side_effect = Exception("Browser closed")

        fp = FingerprintCollector.collect_from_browser(mock_browser)

        # Should return default fingerprint
        self.assertEqual(fp.user_agent, "")
        self.assertEqual(fp.screen_width, 1920)


if __name__ == "__main__":
    unittest.main()
