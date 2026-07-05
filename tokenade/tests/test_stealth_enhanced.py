"""Tests for Phase 46: Enhanced Browser Stealth."""
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tokenade.core.browser.stealth.manager import (
    StealthConfig,
    StealthManager,
    build_stealth_script,
    generate_canvas_seed,
    get_canvas_consistency_script,
    get_session_aging_script,
    _build_webdriver_patch,
    _build_chrome_object_patch,
    _build_plugins_patch,
    _build_permissions_patch,
    _build_webgl_patch,
    _build_iframe_patch,
    _build_worker_patch,
    _build_screen_patch,
    _build_connection_patch,
    _build_automation_cleanup,
    _build_tostring_patch,
    _build_headless_fixes,
)


# ─── StealthConfig Tests ──────────────────────────────────────

class TestStealthConfig:
    def test_default_config(self):
        config = StealthConfig()
        assert config.enable_webdriver is True
        assert config.enable_chrome_object is True
        assert config.enable_plugins is True
        assert config.enable_permissions is True
        assert config.enable_webgl is True
        assert config.enable_canvas is True
        assert config.enable_iframe is True
        assert config.enable_worker is True
        assert config.enable_screen is True
        assert config.enable_connection is True
        assert config.enable_session_aging is True
        assert config.session_age_seconds == 300
        assert config.screen_width == 1920
        assert config.screen_height == 1080

    def test_custom_config(self):
        config = StealthConfig(
            enable_webdriver=False,
            webgl_vendor="Custom Vendor",
            screen_width=2560,
            screen_height=1440,
        )
        assert config.enable_webdriver is False
        assert config.webgl_vendor == "Custom Vendor"
        assert config.screen_width == 2560
        assert config.screen_height == 1440


# ─── Patch Generation Tests ──────────────────────────────────

class TestPatchGeneration:
    def test_webdriver_patch(self):
        script = _build_webdriver_patch()
        assert "navigator.webdriver" in script
        assert "undefined" in script
        assert "getOwnPropertyDescriptor" in script

    def test_chrome_object_patch(self):
        script = _build_chrome_object_patch()
        assert "window.chrome" in script
        assert "loadTimes" in script
        assert "csi" in script
        assert "runtime" in script

    def test_plugins_patch(self):
        script = _build_plugins_patch()
        assert "PluginArray" in script
        assert "Chrome PDF Plugin" in script
        assert "Native Client" in script
        assert "mimeTypes" in script

    def test_permissions_patch(self):
        script = _build_permissions_patch()
        assert "navigator.permissions" in script
        assert "notifications" in script
        assert "push" in script

    def test_webgl_patch(self):
        config = StealthConfig()
        script = _build_webgl_patch(config)
        assert "WebGLRenderingContext" in script
        assert "WebGL2RenderingContext" in script
        assert "37445" in script
        assert "37446" in script
        assert config.webgl_vendor in script

    def test_iframe_patch(self):
        script = _build_iframe_patch()
        assert "HTMLIFrameElement" in script
        assert "contentWindow" in script
        assert "contentDocument" in script

    def test_worker_patch(self):
        script = _build_worker_patch()
        assert "Worker" in script
        assert "ServiceWorker" in script

    def test_screen_patch(self):
        config = StealthConfig(screen_width=2560, screen_height=1440)
        script = _build_screen_patch(config)
        assert "screen.width" in script
        assert "2560" in script
        assert "1440" in script

    def test_connection_patch(self):
        script = _build_connection_patch()
        assert "navigator.connection" in script
        assert "effectiveType" in script
        assert "4g" in script

    def test_automation_cleanup(self):
        script = _build_automation_cleanup()
        assert "cdc_" in script
        assert "__webdriver_" in script
        assert "__selenium_" in script
        assert "phantom" in script

    def test_tostring_patch(self):
        script = _build_tostring_patch()
        assert "Function.prototype.toString" in script
        assert "nativeToString" in script

    def test_headless_fixes(self):
        script = _build_headless_fixes()
        assert "HeadlessChrome" in script
        assert "hardwareConcurrency" in script
        assert "deviceMemory" in script
        assert "devicePixelRatio" in script


# ─── Build Stealth Script Tests ──────────────────────────────

class TestBuildStealthScript:
    def test_build_default(self):
        script = build_stealth_script()
        assert len(script) > 500
        assert "'use strict'" in script
        assert "navigator.webdriver" in script

    def test_build_with_config(self):
        config = StealthConfig(enable_webdriver=False, enable_canvas=False)
        script = build_stealth_script(config)
        assert len(script) > 200

    def test_build_minimal(self):
        config = StealthConfig(
            enable_webdriver=False,
            enable_chrome_object=False,
            enable_plugins=False,
            enable_permissions=False,
            enable_webgl=False,
            enable_iframe=False,
            enable_worker=False,
            enable_screen=False,
            enable_connection=False,
        )
        script = build_stealth_script(config)
        # Always includes automation cleanup, tostring, headless fixes
        assert len(script) < 5000
        full_script = build_stealth_script()
        assert len(script) < len(full_script)

    def test_script_is_valid_js_structure(self):
        script = build_stealth_script()
        assert script.strip().startswith("(function()")
        assert script.strip().endswith("})();")


# ─── Canvas Consistency Tests ─────────────────────────────────

class TestCanvasConsistency:
    def test_generate_seed_deterministic(self):
        seed1 = generate_canvas_seed("test-session-123")
        seed2 = generate_canvas_seed("test-session-123")
        assert seed1 == seed2

    def test_generate_seed_different(self):
        seed1 = generate_canvas_seed("session-1")
        seed2 = generate_canvas_seed("session-2")
        assert seed1 != seed2

    def test_get_canvas_script(self):
        script = get_canvas_consistency_script("test-session")
        assert "SEED" in script
        assert "toDataURL" in script
        assert "toBlob" in script
        assert "getImageData" in script
        assert "mulberry32" in script

    def test_canvas_script_is_valid_structure(self):
        script = get_canvas_consistency_script("test-session")
        assert script.strip().startswith("(function()")
        assert script.strip().endswith("})();")


# ─── Session Aging Tests ──────────────────────────────────────

class TestSessionAging:
    def test_get_session_aging_script(self):
        script = get_session_aging_script("test-session")
        assert "SESSION_AGE" in script
        assert "SESSION_ID" in script
        assert "localStorage" in script
        assert "sessionStorage" in script
        assert "history" in script

    def test_session_aging_script_structure(self):
        script = get_session_aging_script("test-session")
        assert script.strip().startswith("(function()")
        assert script.strip().endswith("})();")


# ─── StealthManager Tests ─────────────────────────────────────

class TestStealthManager:
    def test_default_manager(self):
        manager = StealthManager()
        assert manager.config is not None
        assert manager.config.enable_webdriver is True

    def test_custom_config_manager(self):
        config = StealthConfig(screen_width=2560)
        manager = StealthManager(config)
        assert manager.config.screen_width == 2560

    def test_get_comprehensive_script(self):
        manager = StealthManager()
        script = manager.get_comprehensive_script()
        assert len(script) > 500
        assert "navigator.webdriver" in script

    def test_get_canvas_script(self):
        manager = StealthManager()
        script = manager.get_canvas_script("session-123")
        assert "SEED" in script
        assert "toDataURL" in script

    def test_get_session_aging_script(self):
        manager = StealthManager()
        script = manager.get_session_aging_script("session-123")
        assert "SESSION_AGE" in script

    def test_get_all_scripts(self):
        manager = StealthManager()
        scripts = manager.get_all_scripts("session-123")
        assert len(scripts) == 3
        assert all(len(s) > 100 for s in scripts)

    def test_get_all_scripts_no_session(self):
        manager = StealthManager()
        scripts = manager.get_all_scripts()
        assert len(scripts) == 1

    def test_get_combined_script(self):
        manager = StealthManager()
        combined = manager.get_combined_script("session-123")
        assert len(combined) > 1000
        assert "navigator.webdriver" in combined
        assert "SEED" in combined

    def test_get_config_dict(self):
        manager = StealthManager()
        config = manager.get_config_dict()
        assert "enable_webdriver" in config
        assert "webgl_vendor" in config
        assert "screen_width" in config
        assert isinstance(config, dict)

    def test_apply_to_context(self):
        manager = StealthManager()
        mock_context = MagicMock()
        manager.apply_to_context(mock_context, "session-123")
        assert mock_context.add_init_script.call_count == 3

    def test_apply_to_page(self):
        manager = StealthManager()
        mock_page = MagicMock()
        manager.apply_to_page(mock_page, "session-123")
        assert mock_page.evaluate.call_count == 3


# ─── TLS Fingerprint Tests ────────────────────────────────────

class TestTLSFingerprint:
    def test_import_tls_module(self):
        from tokenade.core.browser.tls_fingerprint import TLSFingerprint, TLSFingerprintConfig
        assert TLSFingerprint is not None
        assert TLSFingerprintConfig is not None

    def test_default_config(self):
        from tokenade.core.browser.tls_fingerprint import TLSFingerprintConfig
        config = TLSFingerprintConfig()
        assert config.impersonate == "chrome131"
        assert config.verify is False
        assert config.timeout == 30

    def test_tls_fingerprint_creation(self):
        from tokenade.core.browser.tls_fingerprint import TLSFingerprint, TLSFingerprintConfig
        config = TLSFingerprintConfig()
        fp = TLSFingerprint(config)
        assert fp.is_available is False or fp.is_available is True

    def test_get_ja3_info(self):
        from tokenade.core.browser.tls_fingerprint import TLSFingerprint
        fp = TLSFingerprint()
        info = fp.get_ja3_info()
        assert "chrome_fingerprints" in info
        assert "firefox_fingerprints" in info
        assert "chrome131" in info["chrome_fingerprints"]

    def test_auto_select_target_chrome(self):
        from tokenade.core.browser.tls_fingerprint import TLSFingerprint
        fp = TLSFingerprint()
        session = {"user_agent": "Mozilla/5.0 Chrome/131.0.0.0"}
        target = fp.auto_select_target(session)
        assert "chrome" in target

    def test_auto_select_target_firefox(self):
        from tokenade.core.browser.tls_fingerprint import TLSFingerprint
        fp = TLSFingerprint()
        session = {"user_agent": "Mozilla/5.0 Firefox/128.0"}
        target = fp.auto_select_target(session)
        assert "firefox" in target

    def test_auto_select_target_default(self):
        from tokenade.core.browser.tls_fingerprint import TLSFingerprint
        fp = TLSFingerprint()
        target = fp.auto_select_target(None)
        assert target == "chrome131"

    def test_apply_to_session(self):
        from tokenade.core.browser.tls_fingerprint import TLSFingerprint
        fp = TLSFingerprint()
        session = {"user_agent": "Chrome/131.0"}
        result = fp.apply_to_session(session)
        assert "tls_impersonate" in result
        assert "tls_available" in result


# ─── Dependency Checker Tests ─────────────────────────────────

class TestDependencyChecker:
    def test_import_dependencies_module(self):
        from tokenade.core.browser.dependencies import DependencyChecker
        assert DependencyChecker is not None

    def test_checker_creation(self):
        from tokenade.core.browser.dependencies import DependencyChecker
        checker = DependencyChecker()
        assert checker.system in ("linux", "darwin", "windows")

    def test_check_package_unknown(self):
        from tokenade.core.browser.dependencies import DependencyChecker
        checker = DependencyChecker()
        result = checker.check_package("nonexistent-package-12345")
        assert result.installed is False
        assert result.name == "nonexistent-package-12345"

    def test_get_report(self):
        from tokenade.core.browser.dependencies import DependencyChecker
        checker = DependencyChecker()
        report = checker.get_report("chromium")
        assert "system" in report
        assert "total" in report
        assert "installed" in report
        assert "missing" in report
        assert "missing_packages" in report

    def test_check_system_deps_function(self):
        from tokenade.core.browser.dependencies import check_system_deps
        report = check_system_deps("chromium")
        assert isinstance(report, dict)
        assert "system" in report

    def test_install_system_deps_function(self):
        from tokenade.core.browser.dependencies import install_system_deps
        results = install_system_deps("chromium")
        assert isinstance(results, list)


# ─── Integration Tests ────────────────────────────────────────

class TestStealthIntegration:
    def test_stealth_script_patches_webdriver(self):
        script = build_stealth_script()
        assert "navigator.webdriver" in script
        assert "undefined" in script

    def test_stealth_script_patches_chrome(self):
        script = build_stealth_script()
        assert "window.chrome" in script
        assert "loadTimes" in script
        assert "csi" in script

    def test_stealth_script_patches_plugins(self):
        script = build_stealth_script()
        assert "PluginArray" in script
        assert "Chrome PDF Plugin" in script

    def test_stealth_script_patches_webgl(self):
        script = build_stealth_script()
        assert "WebGLRenderingContext" in script
        assert "WebGL2RenderingContext" in script

    def test_stealth_script_patches_iframe(self):
        script = build_stealth_script()
        assert "HTMLIFrameElement" in script
        assert "contentWindow" in script

    def test_stealth_script_patches_headless(self):
        script = build_stealth_script()
        assert "HeadlessChrome" in script
        assert "hardwareConcurrency" in script

    def test_stealth_script_removes_artifacts(self):
        script = build_stealth_script()
        assert "cdc_" in script
        assert "__webdriver_" in script
        assert "__selenium_" in script

    def test_canvas_consistency_with_session(self):
        script1 = get_canvas_consistency_script("session-a")
        script2 = get_canvas_consistency_script("session-a")
        assert script1 == script2

    def test_canvas_consistency_different_sessions(self):
        script1 = get_canvas_consistency_script("session-a")
        script2 = get_canvas_consistency_script("session-b")
        assert script1 != script2
