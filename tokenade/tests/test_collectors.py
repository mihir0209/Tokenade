"""
Unit tests for fingerprint collectors.
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tokenade.core.fingerprint.collectors.base import BaseCollector
from tokenade.core.fingerprint.collectors.navigator import NavigatorCollector
from tokenade.core.fingerprint.collectors.screen import ScreenCollector
from tokenade.core.fingerprint.collectors.webgl import WebGLCollector
from tokenade.core.fingerprint.collectors.canvas import CanvasCollector
from tokenade.core.fingerprint.collectors.audio import AudioCollector
from tokenade.core.fingerprint.collectors.plugins import PluginsCollector
from tokenade.core.fingerprint.collectors.webrtc import WebRTCCollector
from tokenade.core.fingerprint.collectors.battery import BatteryCollector


class TestNavigatorCollector(unittest.TestCase):
    """Test NavigatorCollector."""
    
    def setUp(self):
        self.collector = NavigatorCollector()
        self.mock_browser = MagicMock()
    
    def test_api_name(self):
        self.assertEqual(self.collector.api_name, "navigator")
    
    def test_collect(self):
        self.mock_browser.evaluate.return_value = {
            "userAgent": "Mozilla/5.0",
            "platform": "Win32",
            "language": "en-US",
            "languages": ["en-US", "en"],
            "hardwareConcurrency": 8,
            "deviceMemory": 8,
            "maxTouchPoints": 0,
            "pdfViewerEnabled": True,
            "bluetooth": False,
            "usb": False,
            "keyboard": True,
            "mediaCapabilities": {"codecs": False},
            "cookieEnabled": True,
            "onLine": True,
            "vendor": "Google Inc.",
            "product": "Gecko",
            "productSub": "20030107",
            "doNotTrack": None,
            "javaEnabled": False,
            "webdriver": False,
            "permissions": True
        }
        
        result = self.collector.collect(self.mock_browser)
        self.assertEqual(result["userAgent"], "Mozilla/5.0")
        self.assertEqual(result["platform"], "Win32")
        self.assertEqual(result["hardwareConcurrency"], 8)
    
    def test_collect_error(self):
        self.mock_browser.evaluate.side_effect = Exception("Browser closed")
        result = self.collector.collect(self.mock_browser)
        self.assertEqual(result, {})
    
    def test_build_script(self):
        data = {
            "userAgent": "Mozilla/5.0",
            "platform": "Win32",
            "language": "en-US",
            "languages": ["en-US"],
            "hardwareConcurrency": 8,
            "deviceMemory": 8,
            "maxTouchPoints": 0,
            "pdfViewerEnabled": True,
            "vendor": "Google Inc.",
            "product": "Gecko",
            "productSub": "20030107",
            "doNotTrack": "null",
            "cookieEnabled": True,
            "onLine": True,
            "bluetooth": False,
            "usb": False,
            "keyboard": True
        }
        
        script = self.collector.build_script(data)
        self.assertIn("navigator", script)
        self.assertIn("Mozilla/5.0", script)
        self.assertIn("Win32", script)


class TestScreenCollector(unittest.TestCase):
    """Test ScreenCollector."""
    
    def setUp(self):
        self.collector = ScreenCollector()
        self.mock_browser = MagicMock()
    
    def test_api_name(self):
        self.assertEqual(self.collector.api_name, "screen")
    
    def test_collect(self):
        self.mock_browser.evaluate.return_value = {
            "screenWidth": 1920,
            "screenHeight": 1080,
            "screenAvailWidth": 1920,
            "screenAvailHeight": 1040,
            "screenAvailLeft": 0,
            "screenAvailTop": 0,
            "screenColorDepth": 24,
            "screenPixelDepth": 24,
            "devicePixelRatio": 1.0,
            "outerWidth": 1920,
            "outerHeight": 1080,
            "innerWidth": 1920,
            "innerHeight": 969,
            "screenLeft": 0,
            "screenTop": 0
        }
        
        result = self.collector.collect(self.mock_browser)
        self.assertEqual(result["screenWidth"], 1920)
        self.assertEqual(result["screenHeight"], 1080)
    
    def test_build_script(self):
        data = {
            "screenWidth": 1920,
            "screenHeight": 1080,
            "screenAvailWidth": 1920,
            "screenAvailHeight": 1040,
            "screenAvailLeft": 0,
            "screenAvailTop": 0,
            "screenColorDepth": 24,
            "screenPixelDepth": 24,
            "devicePixelRatio": 1.0,
            "outerWidth": 1920,
            "outerHeight": 1080
        }
        
        script = self.collector.build_script(data)
        self.assertIn("screen", script)
        self.assertIn("1920", script)


class TestWebGLCollector(unittest.TestCase):
    """Test WebGLCollector."""
    
    def setUp(self):
        self.collector = WebGLCollector()
        self.mock_browser = MagicMock()
    
    def test_api_name(self):
        self.assertEqual(self.collector.api_name, "webgl")
    
    def test_collect(self):
        self.mock_browser.evaluate.return_value = {
            "vendor": "Intel Inc.",
            "renderer": "Intel Iris Xe",
            "params": {"MAX_TEXTURE_SIZE": 16384},
            "extensions": ["WEBGL_debug_renderer_info"]
        }
        
        result = self.collector.collect(self.mock_browser)
        self.assertEqual(result["vendor"], "Intel Inc.")
        self.assertEqual(result["renderer"], "Intel Iris Xe")
    
    def test_build_script(self):
        data = {
            "vendor": "Intel Inc.",
            "renderer": "Intel Iris Xe",
            "extensions": ["WEBGL_debug_renderer_info"]
        }
        
        script = self.collector.build_script(data)
        self.assertIn("WebGL", script)
        self.assertIn("Intel Inc.", script)


class TestCanvasCollector(unittest.TestCase):
    """Test CanvasCollector."""
    
    def setUp(self):
        self.collector = CanvasCollector()
        self.mock_browser = MagicMock()
    
    def test_api_name(self):
        self.assertEqual(self.collector.api_name, "canvas")
    
    def test_collect(self):
        self.mock_browser.evaluate.return_value = {
            "dataUrl": "data:image/png;base64,abc123",
            "width": 280,
            "height": 60
        }
        
        result = self.collector.collect(self.mock_browser)
        self.assertEqual(result["dataUrl"], "data:image/png;base64,abc123")
    
    def test_build_script(self):
        data = {
            "dataUrl": "data:image/png;base64,abc123",
            "width": 280,
            "height": 60
        }
        
        script = self.collector.build_script(data)
        self.assertIn("toDataURL", script)
        self.assertIn("abc123", script)


class TestPluginsCollector(unittest.TestCase):
    """Test PluginsCollector."""
    
    def setUp(self):
        self.collector = PluginsCollector()
        self.mock_browser = MagicMock()
    
    def test_api_name(self):
        self.assertEqual(self.collector.api_name, "plugins")
    
    def test_collect(self):
        self.mock_browser.evaluate.return_value = {
            "plugins": [{"name": "Chrome PDF Plugin"}],
            "mimeTypes": [{"type": "application/pdf"}],
            "pluginsLength": 1,
            "mimeTypesLength": 1
        }
        
        result = self.collector.collect(self.mock_browser)
        self.assertEqual(len(result["plugins"]), 1)
    
    def test_build_script(self):
        data = {
            "plugins": [{"name": "Chrome PDF Plugin", "description": "Portable Document Format", "filename": "internal-pdf-viewer", "version": "undefined", "length": 1}],
            "mimeTypes": [{"type": "application/pdf", "description": "Portable Document Format", "suffixes": "pdf", "enabledPlugin": "Chrome PDF Plugin"}]
        }
        
        script = self.collector.build_script(data)
        self.assertIn("plugins", script)


class TestWebRTCCollector(unittest.TestCase):
    """Test WebRTCCollector."""
    
    def setUp(self):
        self.collector = WebRTCCollector()
        self.mock_browser = MagicMock()
    
    def test_api_name(self):
        self.assertEqual(self.collector.api_name, "webrtc")
    
    def test_collect(self):
        self.mock_browser.evaluate.return_value = {"ips": ["192.168.1.1"]}
        
        result = self.collector.collect(self.mock_browser)
        self.assertIn("192.168.1.1", result["ips"])


class TestBatteryCollector(unittest.TestCase):
    """Test BatteryCollector."""
    
    def setUp(self):
        self.collector = BatteryCollector()
        self.mock_browser = MagicMock()
    
    def test_api_name(self):
        self.assertEqual(self.collector.api_name, "battery")
    
    def test_collect(self):
        self.mock_browser.evaluate.return_value = {
            "charging": True,
            "level": 1.0,
            "chargingTime": 0,
            "dischargingTime": float('inf')
        }
        
        result = self.collector.collect(self.mock_browser)
        self.assertTrue(result["charging"])


if __name__ == "__main__":
    unittest.main()
