"""Comprehensive tests for fingerprint.manager module - coverage boost."""

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from tokenade.core.fingerprint.manager import (
    BrowserFingerprint,
    FingerprintCollector,
    FingerprintManager,
)


# ---------------------------------------------------------------------------
# BrowserFingerprint dataclass tests
# ---------------------------------------------------------------------------

class TestBrowserFingerprint:
    def test_defaults(self):
        fp = BrowserFingerprint()
        assert fp.screen_width == 1920
        assert fp.screen_height == 1080
        assert fp.language == "en-US"
        assert fp.hardware_concurrency == 4

    def test_to_dict(self):
        fp = BrowserFingerprint(user_agent="Test/1.0", language="de-DE")
        d = fp.to_dict()
        assert isinstance(d, dict)
        assert d["user_agent"] == "Test/1.0"
        assert d["language"] == "de-DE"
        assert "screen_width" in d
        assert "plugins" in d

    def test_to_dict_roundtrip(self):
        fp = BrowserFingerprint(user_agent="Agent/2.0", platform="Linux")
        d = fp.to_dict()
        fp2 = BrowserFingerprint(**d)
        assert fp2.user_agent == "Agent/2.0"
        assert fp2.platform == "Linux"

    def test_to_playwright_context(self):
        fp = BrowserFingerprint(
            viewport_width=1280,
            viewport_height=720,
            screen_width=1920,
            screen_height=1080,
            user_agent="Mozilla/5.0 Test",
            language="en-US",
            timezone="America/New_York",
            device_pixel_ratio=2.0,
            max_touch_points=5,
        )
        ctx = fp.to_playwright_context()
        assert ctx["viewport"] == {"width": 1280, "height": 720}
        assert ctx["screen"] == {"width": 1920, "height": 1080}
        assert ctx["user_agent"] == "Mozilla/5.0 Test"
        assert ctx["locale"] == "en-US"
        assert ctx["timezone_id"] == "America/New_York"
        assert ctx["device_scale_factor"] == 2.0
        assert ctx["has_touch"] is True
        assert ctx["is_mobile"] is False

    def test_to_playwright_no_touch(self):
        fp = BrowserFingerprint(max_touch_points=0)
        ctx = fp.to_playwright_context()
        assert ctx["has_touch"] is False

    def test_to_json(self):
        fp = BrowserFingerprint(user_agent="Agent/3.0")
        j = fp.to_json()
        parsed = json.loads(j)
        assert parsed["user_agent"] == "Agent/3.0"

    def test_from_json(self):
        fp = BrowserFingerprint(user_agent="Agent/4.0", language="fr-FR")
        j = fp.to_json()
        fp2 = BrowserFingerprint.from_json(j)
        assert fp2.user_agent == "Agent/4.0"
        assert fp2.language == "fr-FR"

    def test_from_dict(self):
        d = {"user_agent": "Bot/1.0", "platform": "Windows", "timezone": "UTC"}
        fp = BrowserFingerprint.from_dict(d)
        assert fp.user_agent == "Bot/1.0"
        assert fp.platform == "Windows"
        assert fp.timezone == "UTC"

    def test_from_json_roundtrip(self):
        fp = BrowserFingerprint(
            user_agent="X",
            fonts=["Arial", "Helvetica"],
            plugins=[{"name": "PDF", "description": "PDF Viewer"}],
            canvas_fingerprint="abc123",
            webgl_vendor="Intel",
            webgl_renderer="HD",
        )
        j = fp.to_json()
        fp2 = BrowserFingerprint.from_json(j)
        assert fp2.fonts == ["Arial", "Helvetica"]
        assert fp2.plugins == [{"name": "PDF", "description": "PDF Viewer"}]
        assert fp2.canvas_fingerprint == "abc123"

    def test_to_dict_all_fields(self):
        fp = BrowserFingerprint(
            user_agent="UA",
            screen_width=100,
            screen_height=200,
            viewport_width=300,
            viewport_height=400,
            device_pixel_ratio=1.5,
            color_depth=32,
            platform="Win",
            os_type="Windows",
            language="en",
            languages=["en", "de"],
            timezone="UTC",
            timezone_offset=-300,
            hardware_concurrency=8,
            device_memory=16.0,
            max_touch_points=1,
            webgl_vendor="V",
            webgl_renderer="R",
            canvas_fingerprint="cf",
            fonts=["F1"],
            plugins=[{"n": 1}],
            chrome_version="100",
            accept_language="en",
        )
        d = fp.to_dict()
        assert d["user_agent"] == "UA"
        assert d["screen_width"] == 100
        assert d["languages"] == ["en", "de"]
        assert d["timezone_offset"] == -300

    def test_to_playwright_context_all_fields(self):
        fp = BrowserFingerprint(
            viewport_width=800,
            viewport_height=600,
            screen_width=1920,
            screen_height=1080,
            user_agent="UA",
            language="de",
            timezone="Europe/Berlin",
            device_pixel_ratio=2.0,
            max_touch_points=0,
        )
        ctx = fp.to_playwright_context()
        assert ctx["color_scheme"] == "light"
        assert ctx["reduced_motion"] == "no-preference"
        assert ctx["is_mobile"] is False


# ---------------------------------------------------------------------------
# FingerprintCollector tests
# ---------------------------------------------------------------------------

class TestFingerprintCollector:
    def test_collect_from_system(self):
        fp = FingerprintCollector.collect_from_system()
        assert fp.os_type
        assert fp.platform
        assert fp.language

    def test_collect_from_system_lang_env(self):
        with patch.dict(os.environ, {"LANG": "de_DE.UTF-8"}):
            fp = FingerprintCollector.collect_from_system()
            assert fp.language == "de_DE"
            assert fp.languages == ["de_DE"]

    def test_collect_from_system_no_lang(self):
        with patch.dict(os.environ, {}, clear=True):
            fp = FingerprintCollector.collect_from_system()
            assert fp.language == "en-US"

    def test_collect_from_system_tzlocal_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("tokenade.core.fingerprint.manager.platform.system", return_value="Linux"):
                with patch("tokenade.core.fingerprint.manager.platform.platform", return_value="Linux-5.0"):
                    fp = FingerprintCollector.collect_from_system()
                    assert fp.timezone == "UTC"

    def test_collect_from_system_tzlocal_success(self):
        mock_tzlocal = MagicMock()
        mock_tzlocal.get_localzone.return_value = "America/New_York"
        with patch.dict(os.environ, {}, clear=True):
            with patch("tokenade.core.fingerprint.manager.platform.system", return_value="Linux"):
                with patch("tokenade.core.fingerprint.manager.platform.platform", return_value="Linux-5.0"):
                    with patch.dict("sys.modules", {"tzlocal": mock_tzlocal}):
                        fp = FingerprintCollector.collect_from_system()
                        assert fp.timezone == "America/New_York"

    def test_collect_from_browser(self):
        bm = MagicMock()
        bm.evaluate = MagicMock(side_effect=[
            "Mozilla/5.0 Test",                          # userAgent
            {"width": 1920, "height": 1080, "colorDepth": 24, "pixelRatio": 1.5},  # screen
            {"width": 1280, "height": 720},              # viewport
            "Linux",                                     # platform
            "en-US",                                     # language
            ["en-US", "en"],                             # languages
            "America/New_York",                          # timezone
            -300,                                        # timezoneOffset
            8,                                           # hardwareConcurrency
            4.0,                                         # deviceMemory
            0,                                           # maxTouchPoints
            {"vendor": "Intel Inc.", "renderer": "Intel HD"},  # webgl
            [{"name": "Chrome PDF", "description": "PDF"}],  # plugins
        ])

        fp = FingerprintCollector.collect_from_browser(bm)
        assert fp.user_agent == "Mozilla/5.0 Test"
        assert fp.screen_width == 1920
        assert fp.viewport_width == 1280
        assert fp.platform == "Linux"
        assert fp.language == "en-US"
        assert fp.languages == ["en-US", "en"]
        assert fp.timezone == "America/New_York"
        assert fp.timezone_offset == -300
        assert fp.hardware_concurrency == 8
        assert fp.device_memory == 4.0
        assert fp.webgl_vendor == "Intel Inc."
        assert fp.webgl_renderer == "Intel HD"
        assert len(fp.plugins) == 1

    def test_collect_from_browser_partial_failure(self):
        bm = MagicMock()
        bm.evaluate = MagicMock(side_effect=[
            "Mozilla/5.0",       # userAgent
            {"width": 1920, "height": 1080, "colorDepth": 24, "pixelRatio": 1.0},  # screen
            {"width": 1280, "height": 720},  # viewport
            RuntimeError("fail"),  # platform - will trigger except
        ])

        fp = FingerprintCollector.collect_from_browser(bm)
        assert fp.user_agent == "Mozilla/5.0"

    def test_collect_from_browser_webgl_exception(self):
        bm = MagicMock()
        bm.evaluate = MagicMock(side_effect=[
            "UA",                                                             # userAgent
            {"width": 1920, "height": 1080, "colorDepth": 24, "pixelRatio": 1.0},  # screen
            {"width": 1280, "height": 720},                                   # viewport
            "Linux",                                                          # platform
            "en-US",                                                          # language
            ["en-US"],                                                        # languages
            "UTC",                                                            # timezone
            0,                                                                # timezoneOffset
            4,                                                                # hardwareConcurrency
            8.0,                                                              # deviceMemory
            0,                                                                # maxTouchPoints
            Exception("webgl fail"),                                          # webgl
            [],                                                               # plugins
        ])

        fp = FingerprintCollector.collect_from_browser(bm)
        assert fp.user_agent == "UA"
        assert fp.webgl_vendor == ""

    def test_collect_from_browser_plugins_exception(self):
        bm = MagicMock()
        bm.evaluate = MagicMock(side_effect=[
            "UA",                                                             # userAgent
            {"width": 1920, "height": 1080, "colorDepth": 24, "pixelRatio": 1.0},  # screen
            {"width": 1280, "height": 720},                                   # viewport
            "Linux",                                                          # platform
            "en-US",                                                          # language
            ["en-US"],                                                        # languages
            "UTC",                                                            # timezone
            0,                                                                # timezoneOffset
            4,                                                                # hardwareConcurrency
            8.0,                                                              # deviceMemory
            0,                                                                # maxTouchPoints
            {"vendor": "V", "renderer": "R"},                                 # webgl
            Exception("plugin fail"),                                         # plugins
        ])

        fp = FingerprintCollector.collect_from_browser(bm)
        assert fp.webgl_vendor == "V"
        assert fp.plugins == []

    def test_collect_from_browser_hardware_falsy(self):
        bm = MagicMock()
        bm.evaluate = MagicMock(side_effect=[
            "UA",
            {"width": 1920, "height": 1080, "colorDepth": 24, "pixelRatio": 1.0},
            {"width": 1280, "height": 720},
            "Linux",
            "en-US",
            ["en-US"],
            "UTC",
            0,
            None,   # hardwareConcurrency -> fallback to 4
            None,   # deviceMemory -> fallback to 8.0
            None,   # maxTouchPoints -> fallback to 0
            {"vendor": "", "renderer": ""},
            [],
        ])

        fp = FingerprintCollector.collect_from_browser(bm)
        assert fp.hardware_concurrency == 4
        assert fp.device_memory == 8.0
        assert fp.max_touch_points == 0

    def test_collect_from_browser_webgl_empty(self):
        bm = MagicMock()
        bm.evaluate = MagicMock(side_effect=[
            "UA",
            {"width": 1920, "height": 1080, "colorDepth": 24, "pixelRatio": 1.0},
            {"width": 1280, "height": 720},
            "Linux",
            "en-US",
            ["en-US"],
            "UTC",
            0,
            4,
            8.0,
            0,
            {},
            [],
        ])

        fp = FingerprintCollector.collect_from_browser(bm)
        assert fp.webgl_vendor == ""
        assert fp.webgl_renderer == ""

    def test_collect_from_browser_plugins_empty(self):
        bm = MagicMock()
        bm.evaluate = MagicMock(side_effect=[
            "UA",
            {"width": 1920, "height": 1080, "colorDepth": 24, "pixelRatio": 1.0},
            {"width": 1280, "height": 720},
            "Linux",
            "en-US",
            ["en-US"],
            "UTC",
            0,
            4,
            8.0,
            0,
            {"vendor": "V", "renderer": "R"},
            None,
        ])

        fp = FingerprintCollector.collect_from_browser(bm)
        assert fp.plugins == []


# ---------------------------------------------------------------------------
# FingerprintManager tests
# ---------------------------------------------------------------------------

class TestFingerprintManager:
    def test_init_creates_dir(self, tmp_path):
        d = tmp_path / "fps"
        FingerprintManager(str(d))
        assert d.exists()

    def test_save_and_load(self, tmp_path):
        mgr = FingerprintManager(str(tmp_path))
        fp = BrowserFingerprint(user_agent="Save/1.0", language="fr")
        path = mgr.save("my_fp", fp)
        assert Path(path).exists()

        loaded = mgr.load("my_fp")
        assert loaded is not None
        assert loaded.user_agent == "Save/1.0"
        assert loaded.language == "fr"

    def test_load_nonexistent(self, tmp_path):
        mgr = FingerprintManager(str(tmp_path))
        assert mgr.load("nope") is None

    def test_list(self, tmp_path):
        mgr = FingerprintManager(str(tmp_path))
        mgr.save("fp_a", BrowserFingerprint(user_agent="A"))
        mgr.save("fp_b", BrowserFingerprint(user_agent="B"))
        names = mgr.list()
        assert sorted(names) == ["fp_a", "fp_b"]

    def test_list_empty(self, tmp_path):
        mgr = FingerprintManager(str(tmp_path))
        assert mgr.list() == []

    def test_delete_existing(self, tmp_path):
        mgr = FingerprintManager(str(tmp_path))
        mgr.save("to_del", BrowserFingerprint())
        assert mgr.delete("to_del") is True
        assert mgr.load("to_del") is None

    def test_delete_nonexistent(self, tmp_path):
        mgr = FingerprintManager(str(tmp_path))
        assert mgr.delete("nope") is False

    def test_apply_to_config(self, tmp_path):
        mgr = FingerprintManager(str(tmp_path))
        fp = BrowserFingerprint(
            viewport_width=800,
            viewport_height=600,
            user_agent="Apply/1.0",
            screen_width=1920,
            screen_height=1080,
            language="de",
            timezone="Europe/Berlin",
            device_pixel_ratio=2.0,
            max_touch_points=0,
        )
        mgr.save("apply_fp", fp)
        config = {"headless": True}
        result = mgr.apply_to_config("apply_fp", config)
        assert result["viewport"] == {"width": 800, "height": 600}
        assert result["user_agent"] == "Apply/1.0"
        assert result["headless"] is True

    def test_apply_to_config_missing(self, tmp_path):
        mgr = FingerprintManager(str(tmp_path))
        config = {"headless": True}
        result = mgr.apply_to_config("nope", config)
        assert result == {"headless": True}

    def test_compare_identical(self):
        fp1 = BrowserFingerprint(user_agent="X", language="en")
        fp2 = BrowserFingerprint(user_agent="X", language="en")
        mgr = FingerprintManager()
        diffs = mgr.compare(fp1, fp2)
        assert diffs == {}

    def test_compare_differences(self):
        fp1 = BrowserFingerprint(user_agent="A", screen_width=1920, language="en")
        fp2 = BrowserFingerprint(user_agent="B", screen_width=1280, language="de")
        mgr = FingerprintManager()
        diffs = mgr.compare(fp1, fp2)
        assert "user_agent" in diffs
        assert diffs["user_agent"]["source"] == "A"
        assert diffs["user_agent"]["target"] == "B"
        assert "screen_width" in diffs
        assert "language" in diffs

    def test_compare_single_field(self):
        fp1 = BrowserFingerprint(timezone="UTC")
        fp2 = BrowserFingerprint(timezone="US/Eastern")
        mgr = FingerprintManager()
        diffs = mgr.compare(fp1, fp2)
        assert len(diffs) == 1
        assert "timezone" in diffs

    def test_save_returns_path(self, tmp_path):
        mgr = FingerprintManager(str(tmp_path))
        path = mgr.save("test_path", BrowserFingerprint())
        assert str(tmp_path) in path
        assert "test_path.json" in path

    def test_load_deserializes_all_fields(self, tmp_path):
        mgr = FingerprintManager(str(tmp_path))
        fp = BrowserFingerprint(
            user_agent="Full/1.0",
            screen_width=2560,
            screen_height=1440,
            viewport_width=1920,
            viewport_height=1080,
            device_pixel_ratio=1.25,
            color_depth=30,
            platform="MacIntel",
            os_type="Darwin",
            language="ja",
            languages=["ja", "en"],
            timezone="Asia/Tokyo",
            timezone_offset=-540,
            hardware_concurrency=12,
            device_memory=16.0,
            max_touch_points=0,
            webgl_vendor="Apple",
            webgl_renderer="Apple M1",
            canvas_fingerprint="hash123",
            fonts=["Hiragino", "Arial"],
            plugins=[{"name": "PDF"}],
            chrome_version="114",
            accept_language="ja,en;q=0.9",
        )
        mgr.save("full", fp)
        loaded = mgr.load("full")
        assert loaded.screen_width == 2560
        assert loaded.languages == ["ja", "en"]
        assert loaded.fonts == ["Hiragino", "Arial"]
        assert loaded.chrome_version == "114"

    def test_overwrite_existing(self, tmp_path):
        mgr = FingerprintManager(str(tmp_path))
        mgr.save("fp", BrowserFingerprint(user_agent="old"))
        mgr.save("fp", BrowserFingerprint(user_agent="new"))
        loaded = mgr.load("fp")
        assert loaded.user_agent == "new"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_manager_default_dir(self):
        mgr = FingerprintManager()
        assert mgr.storage_dir == Path(".fingerprints")

    def test_fingerprint_default_values(self):
        fp = BrowserFingerprint()
        assert fp.webgl_vendor == ""
        assert fp.webgl_renderer == ""
        assert fp.canvas_fingerprint == ""
        assert fp.chrome_version == ""
        assert fp.fonts == []
        assert fp.plugins == []

    def test_from_dict_known_fields(self):
        d = {
            "user_agent": "X",
            "language": "en",
        }
        fp = BrowserFingerprint.from_dict(d)
        assert fp.user_agent == "X"
        assert fp.language == "en"

    def test_to_json_is_valid_json(self):
        fp = BrowserFingerprint(user_agent="JSON/1.0")
        j = fp.to_json()
        parsed = json.loads(j)
        assert parsed["user_agent"] == "JSON/1.0"

    def test_collect_from_system_returns_consistent_fields(self):
        fp1 = FingerprintCollector.collect_from_system()
        fp2 = FingerprintCollector.collect_from_system()
        assert fp1.os_type == fp2.os_type
        assert fp1.platform == fp2.platform

    def test_compare_all_fields_same(self):
        fp = BrowserFingerprint(
            user_agent="UA",
            screen_width=100,
            screen_height=200,
            viewport_width=300,
            viewport_height=400,
            device_pixel_ratio=1.5,
            color_depth=32,
            platform="Win",
            os_type="Windows",
            language="en",
            languages=["en", "de"],
            timezone="UTC",
            timezone_offset=-300,
            hardware_concurrency=8,
            device_memory=16.0,
            max_touch_points=1,
            webgl_vendor="V",
            webgl_renderer="R",
            canvas_fingerprint="cf",
            fonts=["F1"],
            plugins=[{"n": 1}],
            chrome_version="100",
            accept_language="en",
        )
        mgr = FingerprintManager()
        diffs = mgr.compare(fp, fp)
        assert diffs == {}

    def test_delete_and_recreate(self, tmp_path):
        mgr = FingerprintManager(str(tmp_path))
        mgr.save("fp", BrowserFingerprint(user_agent="v1"))
        mgr.delete("fp")
        mgr.save("fp", BrowserFingerprint(user_agent="v2"))
        loaded = mgr.load("fp")
        assert loaded.user_agent == "v2"

    def test_multiple_managers_different_dirs(self, tmp_path):
        d1 = tmp_path / "dir1"
        d2 = tmp_path / "dir2"
        mgr1 = FingerprintManager(str(d1))
        mgr2 = FingerprintManager(str(d2))
        mgr1.save("fp", BrowserFingerprint(user_agent="in_d1"))
        assert mgr1.load("fp") is not None
        assert mgr2.load("fp") is None
