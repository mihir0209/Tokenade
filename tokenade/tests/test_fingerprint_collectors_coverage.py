"""
Comprehensive tests for fingerprint collectors — battery, webrtc, canvas,
plugins, screen, webgl collectors.
"""

import unittest
from unittest.mock import MagicMock

from tokenade.core.fingerprint.collectors.battery import BatteryCollector
from tokenade.core.fingerprint.collectors.webrtc import WebRTCCollector
from tokenade.core.fingerprint.collectors.canvas import CanvasCollector
from tokenade.core.fingerprint.collectors.plugins import PluginsCollector
from tokenade.core.fingerprint.collectors.screen import ScreenCollector
from tokenade.core.fingerprint.collectors.webgl import WebGLCollector


class TestBaseCollector(unittest.TestCase):
    def test_build_script_bool(self):
        collector = BatteryCollector()
        result = collector.build_script({"charging": True})
        self.assertIn("charging: true", result)

    def test_build_script_int(self):
        collector = BatteryCollector()
        result = collector.build_script({"level": 5})
        self.assertIn("level: 5", result)

    def test_build_script_battery_template(self):
        collector = BatteryCollector()
        data = {
            "charging": False,
            "level": 0.75,
            "chargingTime": 3600,
            "dischargingTime": 7200,
        }
        result = collector.build_script(data)
        self.assertIn("charging: false", result)
        self.assertIn("level: 0.75", result)
        self.assertIn("chargingTime: 3600", result)

    def test_build_script_webgl(self):
        collector = WebGLCollector()
        data = {"vendor": "Intel", "renderer": "Mesa", "extensions": ["ext1"]}
        result = collector.build_script(data)
        self.assertIn("Intel", result)
        self.assertIn("Mesa", result)

    def test_build_script_canvas(self):
        collector = CanvasCollector()
        data = {"dataUrl": "data:image/png;base64,abc"}
        result = collector.build_script(data)
        self.assertIn("data:image/png;base64,abc", result)

    def test_build_script_plugins(self):
        collector = PluginsCollector()
        data = {
            "plugins": [{"name": "PDF"}],
            "mimeTypes": [{"type": "application/pdf"}],
        }
        result = collector.build_script(data)
        self.assertIn("PDF", result)

    def test_build_script_screen(self):
        collector = ScreenCollector()
        data = {
            "screenWidth": 1920,
            "screenHeight": 1080,
            "screenAvailWidth": 1920,
            "screenAvailHeight": 1040,
            "screenAvailLeft": 0,
            "screenAvailTop": 0,
            "screenColorDepth": 24,
            "screenPixelDepth": 24,
            "outerWidth": 1920,
            "outerHeight": 1080,
            "devicePixelRatio": 1.0,
        }
        result = collector.build_script(data)
        self.assertIn("1920", result)


class TestBatteryCollector(unittest.TestCase):
    def test_api_name(self):
        c = BatteryCollector()
        self.assertEqual(c.api_name, "battery")

    def test_collect_success(self):
        c = BatteryCollector()
        bm = MagicMock()
        bm.evaluate.return_value = {
            "charging": True,
            "level": 1.0,
            "chargingTime": 0,
            "dischargingTime": 3600,
        }
        result = c.collect(bm)
        self.assertTrue(result["charging"])

    def test_collect_non_dict(self):
        c = BatteryCollector()
        bm = MagicMock()
        bm.evaluate.return_value = "not a dict"
        result = c.collect(bm)
        self.assertEqual(result, {})

    def test_collect_exception(self):
        c = BatteryCollector()
        bm = MagicMock()
        bm.evaluate.side_effect = RuntimeError("fail")
        result = c.collect(bm)
        self.assertEqual(result, {})

    def test_get_script_template(self):
        c = BatteryCollector()
        template = c.get_script_template()
        self.assertIn("getBattery", template)


class TestWebRTCCollector(unittest.TestCase):
    def test_api_name(self):
        c = WebRTCCollector()
        self.assertEqual(c.api_name, "webrtc")

    def test_collect_success(self):
        c = WebRTCCollector()
        bm = MagicMock()
        bm.evaluate.return_value = {"ips": ["192.168.1.1"]}
        result = c.collect(bm)
        self.assertEqual(result["ips"], ["192.168.1.1"])

    def test_collect_non_dict(self):
        c = WebRTCCollector()
        bm = MagicMock()
        bm.evaluate.return_value = "text"
        result = c.collect(bm)
        self.assertEqual(result, {})

    def test_collect_exception(self):
        c = WebRTCCollector()
        bm = MagicMock()
        bm.evaluate.side_effect = RuntimeError("fail")
        result = c.collect(bm)
        self.assertEqual(result, {})

    def test_get_script_template(self):
        c = WebRTCCollector()
        template = c.get_script_template()
        self.assertIn("RTCPeerConnection", template)


class TestCanvasCollector(unittest.TestCase):
    def test_api_name(self):
        c = CanvasCollector()
        self.assertEqual(c.api_name, "canvas")

    def test_collect_success(self):
        c = CanvasCollector()
        bm = MagicMock()
        bm.evaluate.return_value = {
            "dataUrl": "data:image/png;base64,abc",
            "width": 280,
            "height": 60,
        }
        result = c.collect(bm)
        self.assertEqual(result["width"], 280)

    def test_collect_non_dict(self):
        c = CanvasCollector()
        bm = MagicMock()
        bm.evaluate.return_value = None
        result = c.collect(bm)
        self.assertEqual(result, {})

    def test_collect_exception(self):
        c = CanvasCollector()
        bm = MagicMock()
        bm.evaluate.side_effect = RuntimeError("fail")
        result = c.collect(bm)
        self.assertEqual(result, {})

    def test_get_script_template(self):
        c = CanvasCollector()
        template = c.get_script_template()
        self.assertIn("toDataURL", template)


class TestPluginsCollector(unittest.TestCase):
    def test_api_name(self):
        c = PluginsCollector()
        self.assertEqual(c.api_name, "plugins")

    def test_collect_success(self):
        c = PluginsCollector()
        bm = MagicMock()
        bm.evaluate.return_value = {
            "plugins": [],
            "mimeTypes": [],
            "pluginsLength": 0,
            "mimeTypesLength": 0,
        }
        result = c.collect(bm)
        self.assertEqual(result["pluginsLength"], 0)

    def test_collect_non_dict(self):
        c = PluginsCollector()
        bm = MagicMock()
        bm.evaluate.return_value = []
        result = c.collect(bm)
        self.assertEqual(result, {})

    def test_collect_exception(self):
        c = PluginsCollector()
        bm = MagicMock()
        bm.evaluate.side_effect = RuntimeError("fail")
        result = c.collect(bm)
        self.assertEqual(result, {})

    def test_get_script_template(self):
        c = PluginsCollector()
        template = c.get_script_template()
        self.assertIn("fakePlugins", template)


class TestScreenCollector(unittest.TestCase):
    def test_api_name(self):
        c = ScreenCollector()
        self.assertEqual(c.api_name, "screen")

    def test_collect_success(self):
        c = ScreenCollector()
        bm = MagicMock()
        bm.evaluate.return_value = {
            "screenWidth": 1920,
            "screenHeight": 1080,
            "devicePixelRatio": 1.0,
        }
        result = c.collect(bm)
        self.assertEqual(result["screenWidth"], 1920)

    def test_collect_non_dict(self):
        c = ScreenCollector()
        bm = MagicMock()
        bm.evaluate.return_value = 42
        result = c.collect(bm)
        self.assertEqual(result, {})

    def test_collect_exception(self):
        c = ScreenCollector()
        bm = MagicMock()
        bm.evaluate.side_effect = RuntimeError("fail")
        result = c.collect(bm)
        self.assertEqual(result, {})

    def test_get_script_template(self):
        c = ScreenCollector()
        template = c.get_script_template()
        self.assertIn("screenProps", template)


class TestWebGLCollector(unittest.TestCase):
    def test_api_name(self):
        c = WebGLCollector()
        self.assertEqual(c.api_name, "webgl")

    def test_collect_success(self):
        c = WebGLCollector()
        bm = MagicMock()
        bm.evaluate.return_value = {
            "vendor": "Intel",
            "renderer": "Mesa",
            "params": {},
            "extensions": [],
        }
        result = c.collect(bm)
        self.assertEqual(result["vendor"], "Intel")

    def test_collect_non_dict(self):
        c = WebGLCollector()
        bm = MagicMock()
        bm.evaluate.return_value = "text"
        result = c.collect(bm)
        self.assertEqual(result, {})

    def test_collect_exception(self):
        c = WebGLCollector()
        bm = MagicMock()
        bm.evaluate.side_effect = RuntimeError("fail")
        result = c.collect(bm)
        self.assertEqual(result, {})

    def test_get_script_template(self):
        c = WebGLCollector()
        template = c.get_script_template()
        self.assertIn("WEBGL_debug_renderer_info", template)


if __name__ == "__main__":
    unittest.main()
