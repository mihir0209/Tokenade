"""Comprehensive tests for fingerprint injector module."""

from unittest.mock import MagicMock

from tokenade.core.fingerprint.manager import BrowserFingerprint


# ---------------------------------------------------------------------------
# inject_stealth_script tests
# ---------------------------------------------------------------------------

class TestInjectStealthScript:
    def _make_fp(self, **kwargs):
        defaults = {
            "user_agent": "Mozilla/5.0 Test",
            "platform": "Linux",
            "language": "en-US",
            "languages": ["en-US"],
            "hardware_concurrency": 4,
            "device_memory": 8.0,
            "max_touch_points": 0,
            "screen_width": 1920,
            "screen_height": 1080,
            "device_pixel_ratio": 1.0,
            "color_depth": 24,
            "webgl_vendor": "Intel Inc.",
            "webgl_renderer": "Intel HD Graphics",
        }
        defaults.update(kwargs)
        return BrowserFingerprint(**defaults)

    def test_inject_via_add_init_script(self):
        from tokenade.core.fingerprint.injector import inject_stealth_script
        bm = MagicMock()
        bm._context = MagicMock()
        fp = self._make_fp()

        result = inject_stealth_script(bm, fp, level="basic")
        assert result is True
        bm._context.add_init_script.assert_called_once()

    def test_inject_via_evaluate_fallback(self):
        from tokenade.core.fingerprint.injector import inject_stealth_script
        bm = MagicMock()
        bm._context = None
        bm.evaluate = MagicMock()
        fp = self._make_fp()

        result = inject_stealth_script(bm, fp, level="basic")
        assert result is True
        bm.evaluate.assert_called_once()

    def test_inject_no_methods_returns_false(self):
        from tokenade.core.fingerprint.injector import inject_stealth_script
        bm = MagicMock(spec=[])  # no attributes
        fp = self._make_fp()

        result = inject_stealth_script(bm, fp)
        assert result is False

    def test_inject_add_init_script_failure_falls_back_to_evaluate(self):
        from tokenade.core.fingerprint.injector import inject_stealth_script
        bm = MagicMock()
        bm._context = MagicMock()
        bm._context.add_init_script.side_effect = RuntimeError("not supported")
        bm.evaluate = MagicMock()
        fp = self._make_fp()

        result = inject_stealth_script(bm, fp, level="basic")
        assert result is True
        bm.evaluate.assert_called_once()

    def test_inject_exception_returns_false(self):
        from tokenade.core.fingerprint.injector import inject_stealth_script
        bm = MagicMock()
        del bm._context  # no _context attribute
        bm.evaluate = MagicMock(side_effect=Exception("fatal"))
        fp = self._make_fp()

        result = inject_stealth_script(bm, fp)
        assert result is False

    def test_inject_maximum_level(self):
        from tokenade.core.fingerprint.injector import inject_stealth_script
        bm = MagicMock()
        bm._context = MagicMock()
        fp = self._make_fp()

        result = inject_stealth_script(bm, fp, level="maximum")
        assert result is True
        script = bm._context.add_init_script.call_args[0][0]
        assert "WebRTC" in script or "webrtc" in script.lower() or "Battery" in script or "battery" in script.lower()

    def test_inject_advanced_level(self):
        from tokenade.core.fingerprint.injector import inject_stealth_script
        bm = MagicMock()
        bm._context = MagicMock()
        fp = self._make_fp()

        result = inject_stealth_script(bm, fp, level="advanced")
        assert result is True
        script = bm._context.add_init_script.call_args[0][0]
        assert "Audio" in script or "audio" in script.lower()

    def test_inject_with_canvas_fingerprint(self):
        from tokenade.core.fingerprint.injector import inject_stealth_script
        bm = MagicMock()
        bm._context = MagicMock()
        fp = self._make_fp(canvas_fingerprint="data:image/png;base64,abc123")

        result = inject_stealth_script(bm, fp, level="maximum")
        assert result is True
        script = bm._context.add_init_script.call_args[0][0]
        assert "Canvas" in script or "canvas" in script.lower() or "toDataURL" in script

    def test_inject_with_plugins(self):
        from tokenade.core.fingerprint.injector import inject_stealth_script
        bm = MagicMock()
        bm._context = MagicMock()
        plugins = [{"name": "Chrome PDF", "description": "PDF", "filename": "pdf.so", "length": 1}]
        fp = self._make_fp(plugins=plugins)

        result = inject_stealth_script(bm, fp, level="basic")
        assert result is True
        script = bm._context.add_init_script.call_args[0][0]
        assert "Chrome PDF" in script or "plugins" in script.lower()

    def test_inject_no_canvas_skips_canvas_spoof(self):
        from tokenade.core.fingerprint.injector import inject_stealth_script
        bm = MagicMock()
        bm._context = MagicMock()
        fp = self._make_fp(canvas_fingerprint="")

        inject_stealth_script(bm, fp, level="basic")
        script = bm._context.add_init_script.call_args[0][0]
        assert "toDataURL" not in script

    def test_inject_no_plugins_skips_plugin_spoof(self):
        from tokenade.core.fingerprint.injector import inject_stealth_script
        bm = MagicMock()
        bm._context = MagicMock()
        fp = self._make_fp(plugins=[])

        inject_stealth_script(bm, fp, level="basic")
        script = bm._context.add_init_script.call_args[0][0]
        assert "pluginsData" not in script

    def test_inject_evaluate_with_exception_returns_false(self):
        from tokenade.core.fingerprint.injector import inject_stealth_script
        bm = MagicMock()
        bm._context = None
        bm.evaluate = MagicMock(side_effect=RuntimeError("evaluate failed"))
        fp = self._make_fp()

        result = inject_stealth_script(bm, fp)
        assert result is False


# ---------------------------------------------------------------------------
# validate_injection tests
# ---------------------------------------------------------------------------

class TestValidateInjection:
    def test_validate_success(self):
        from tokenade.core.fingerprint.injector import validate_injection
        bm = MagicMock()
        bm.evaluate.return_value = {
            "webdriver": None,
            "userAgent": "Mozilla/5.0 Test",
            "platform": "Linux",
            "hardwareConcurrency": 4,
            "deviceMemory": 8,
            "screenWidth": 1920,
            "screenHeight": 1080,
            "devicePixelRatio": 1.0,
            "pluginsLength": 3,
            "chromeRuntime": True,
        }

        result = validate_injection(bm)
        assert result["valid"] is True
        assert result["webdriver_undefined"] is True
        assert result["user_agent"] == "Mozilla/5.0 Test"
        assert result["platform"] == "Linux"
        assert result["hardware_concurrency"] == 4
        assert result["screen_width"] == 1920
        assert result["screen_height"] == 1080
        assert result["device_pixel_ratio"] == 1.0
        assert result["plugins_count"] == 3
        assert result["chrome_runtime_present"] is True

    def test_validate_webdriver_not_none(self):
        from tokenade.core.fingerprint.injector import validate_injection
        bm = MagicMock()
        bm.evaluate.return_value = {
            "webdriver": True,
            "userAgent": "Bot",
            "platform": "Linux",
            "hardwareConcurrency": 2,
            "deviceMemory": 4,
            "screenWidth": 1024,
            "screenHeight": 768,
            "devicePixelRatio": 1.0,
            "pluginsLength": 0,
            "chromeRuntime": False,
        }

        result = validate_injection(bm)
        assert result["valid"] is False
        assert result["webdriver_undefined"] is False

    def test_validate_exception(self):
        from tokenade.core.fingerprint.injector import validate_injection
        bm = MagicMock()
        bm.evaluate.side_effect = Exception("browser dead")

        result = validate_injection(bm)
        assert result["valid"] is False
        assert "error" in result
        assert "browser dead" in result["error"]

    def test_validate_partial_result(self):
        from tokenade.core.fingerprint.injector import validate_injection
        bm = MagicMock()
        bm.evaluate.return_value = {
            "webdriver": None,
        }

        result = validate_injection(bm)
        assert result["valid"] is True
        assert result["webdriver_undefined"] is True
        assert result["user_agent"] == ""
        assert result["hardware_concurrency"] == 0

    def test_validate_calls_correct_script(self):
        from tokenade.core.fingerprint.injector import validate_injection
        bm = MagicMock()
        bm.evaluate.return_value = {
            "webdriver": None,
            "userAgent": "",
            "platform": "",
            "hardwareConcurrency": 0,
            "deviceMemory": 0,
            "screenWidth": 0,
            "screenHeight": 0,
            "devicePixelRatio": 0,
            "pluginsLength": 0,
            "chromeRuntime": False,
        }
        validate_injection(bm)
        script = bm.evaluate.call_args[0][0]
        assert "navigator.webdriver" in script
        assert "navigator.userAgent" in script
        assert "navigator.platform" in script
        assert "navigator.hardwareConcurrency" in script
        assert "screen.width" in script
        assert "devicePixelRatio" in script

    def test_validate_webdriver_false(self):
        from tokenade.core.fingerprint.injector import validate_injection
        bm = MagicMock()
        bm.evaluate.return_value = {
            "webdriver": False,
            "userAgent": "UA",
            "platform": "Win",
            "hardwareConcurrency": 4,
            "deviceMemory": 8,
            "screenWidth": 1920,
            "screenHeight": 1080,
            "devicePixelRatio": 1.0,
            "pluginsLength": 2,
            "chromeRuntime": False,
        }

        result = validate_injection(bm)
        assert result["valid"] is False
        assert result["webdriver_undefined"] is False

    def test_validate_webdriver_zero(self):
        from tokenade.core.fingerprint.injector import validate_injection
        bm = MagicMock()
        bm.evaluate.return_value = {
            "webdriver": 0,
            "userAgent": "UA",
            "platform": "Win",
            "hardwareConcurrency": 4,
            "deviceMemory": 8,
            "screenWidth": 1920,
            "screenHeight": 1080,
            "devicePixelRatio": 1.0,
            "pluginsLength": 2,
            "chromeRuntime": False,
        }

        result = validate_injection(bm)
        assert result["valid"] is False
        assert result["webdriver_undefined"] is False

    def test_validate_empty_result(self):
        from tokenade.core.fingerprint.injector import validate_injection
        bm = MagicMock()
        bm.evaluate.return_value = {}

        result = validate_injection(bm)
        assert result["valid"] is True
        assert result["webdriver_undefined"] is True
        assert result["plugins_count"] == 0
        assert result["chrome_runtime_present"] is False
