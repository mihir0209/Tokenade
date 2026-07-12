"""Tests for Phase 48: Plugin Marketplace Enhancement — new plugin types + testing framework."""
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tokenade.plugin.base import (
    PluginBase,
    SessionRefreshPlugin,
    SiteHandlerPlugin,
    ExportFormatPlugin,
    SessionValidatorPlugin,
    StealthPlugin,
    ProxyProviderPlugin,
    CaptchaPlugin,
)
from tokenade.core.integration.plugin_loader import PluginLoader
from tokenade.core.integration.plugin_testing import (
    PluginTestRunner,
    PluginTestResult,
    PluginTestSuite,
)


# ─── New Plugin Type Base Class Tests ────────────────────────

class TestStealthPlugin:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            StealthPlugin()

    def test_concrete_impl(self):
        class TestStealth(StealthPlugin):
            name = "test-stealth"
            version = "1.0.0"
            description = "Test"
            
            def get_patches(self):
                return ["navigator.webdriver = undefined"]

        plugin = TestStealth()
        assert plugin.name == "test-stealth"
        patches = plugin.get_patches()
        assert len(patches) == 1
        assert "navigator.webdriver" in patches[0]
        assert plugin.get_tls_config() is None
        assert plugin.get_browser_args() == []


class TestProxyPlugin:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            ProxyProviderPlugin()

    def test_concrete_impl(self):
        from tokenade.plugin.api import PluginResult

        class TestProxy(ProxyProviderPlugin):
            name = "test-proxy"
            version = "1.0.0"
            description = "Test"
            
            def get_proxy(self, options=None):
                return PluginResult(success=True, data={"host": "1.1.1.1", "port": 8080})

            def rotate(self, session_id=None):
                return PluginResult(success=True, data={"host": "2.2.2.2", "port": 8080})

        plugin = TestProxy()
        result = plugin.get_proxy()
        assert result.success is True
        assert result.data["host"] == "1.1.1.1"


class TestCaptchaPlugin:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            CaptchaPlugin()

    def test_concrete_impl(self):
        class TestCaptcha(CaptchaPlugin):
            name = "test-captcha"
            version = "1.0.0"
            description = "Test"
            
            def get_supported_types(self):
                return ["recaptcha_v2"]
            def solve(self, captcha_type, site_key=None, page_url=None):
                return {"success": True, "token": "abc123"}

        plugin = TestCaptcha()
        assert plugin.get_supported_types() == ["recaptcha_v2"]
        result = plugin.solve("recaptcha_v2", "key123")
        assert result["success"] is True
        assert result["token"] == "abc123"
        assert plugin.get_balance() is None


# ─── Plugin Loader New Types Tests ────────────────────────────

class TestPluginLoaderNewTypes:
    def test_stealth_registry(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        plugin_dir = tmp_path / "my-stealth"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "my-stealth", "version": "1.0.0", "type": "stealth",
            "entry_point": "plugin.py", "description": "Test stealth",
        }))
        (plugin_dir / "plugin.py").write_text("""
from tokenade.plugin.base import StealthPlugin
class MyStealth(StealthPlugin):
    name = "my-stealth"
    version = "1.0.0"
    description = "Test stealth"
    
    def get_patches(self):
        return ["test"]
""")
        loader.load_all()
        assert loader.get_stealth("my-stealth") is not None
        assert "my-stealth" in loader.list_stealths()

    def test_proxy_registry(self, tmp_path):
        from tokenade.plugin.api import PluginResult

        loader = PluginLoader(plugins_dir=tmp_path)
        plugin_dir = tmp_path / "my-proxy"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "my-proxy", "version": "1.0.0", "type": "proxy",
            "entry_point": "plugin.py", "description": "Test proxy",
        }))
        (plugin_dir / "plugin.py").write_text("""
from tokenade.plugin.base import ProxyProviderPlugin
from tokenade.plugin.api import PluginResult
class MyProxy(ProxyProviderPlugin):
    name = "my-proxy"
    version = "1.0.0"
    description = "Test proxy"
    
    def get_proxy(self, options=None):
        return PluginResult(success=True, data={"host": "1.1.1.1", "port": 8080})

    def rotate(self, session_id=None):
        return PluginResult(success=True, data={"host": "2.2.2.2", "port": 8080})
""")
        loader.load_all()
        assert loader.get_proxy_plugin("my-proxy") is not None
        assert "my-proxy" in loader.list_proxy_plugins()

    def test_captcha_registry(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        plugin_dir = tmp_path / "my-captcha"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "my-captcha", "version": "1.0.0", "type": "captcha",
            "entry_point": "plugin.py", "description": "Test captcha",
        }))
        (plugin_dir / "plugin.py").write_text("""
from tokenade.plugin.base import CaptchaPlugin
class MyCaptcha(CaptchaPlugin):
    name = "my-captcha"
    version = "1.0.0"
    description = "Test captcha"
    
    def get_supported_types(self):
        return ["recaptcha_v2"]
    def solve(self, captcha_type, site_key=None, page_url=None):
        return {"success": True, "token": "abc"}
""")
        loader.load_all()
        assert loader.get_captcha("my-captcha") is not None
        assert "my-captcha" in loader.list_captchas()

    def test_unload_new_types(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        for ptype, cls_name, base in [
            ("stealth", "MyStealth", "StealthPlugin"),
            ("proxy", "MyProxy", "ProxyProviderPlugin"),
            ("captcha", "MyCaptcha", "CaptchaPlugin"),
        ]:
            plugin_dir = tmp_path / f"test-{ptype}"
            plugin_dir.mkdir(exist_ok=True)
            (plugin_dir / "plugin.json").write_text(json.dumps({
                "name": f"test-{ptype}", "version": "1.0.0", "type": ptype,
                "entry_point": "plugin.py", "description": f"Test {ptype}",
            }))
            (plugin_dir / "plugin.py").write_text(f"""
from tokenade.plugin.base import {base}
from tokenade.plugin.api import PluginResult
class {cls_name}({base}):
    name = "test-{ptype}"
    version = "1.0.0"
    description = "Test {ptype}"
    
    def get_patches(self): return []
    def get_proxy(self, options=None): return PluginResult(success=True, data={{}})
    def rotate(self, session_id=None): return PluginResult(success=True, data={{}})
    def get_supported_types(self): return []
    def solve(self, t, k=None, u=None): return {{}}
""")
        loader.load_all()
        assert loader.get_stealth("test-stealth") is not None
        assert loader.get_proxy_plugin("test-proxy") is not None
        assert loader.get_captcha("test-captcha") is not None

        loader.unload("test-stealth")
        assert loader.get_stealth("test-stealth") is None


# ─── Plugin Testing Framework Tests ──────────────────────────

class TestPluginTestRunner:
    def test_test_manifest_exists(self, tmp_path):
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "my-plugin", "version": "1.0.0", "type": "stealth",
            "entry_point": "plugin.py", "description": "Test",
        }))
        (plugin_dir / "plugin.py").write_text("""
from tokenade.plugin.base import StealthPlugin
class MyPlugin(StealthPlugin):
    name = "my-plugin"
    version = "1.0.0"
    description = "Test"
    
    def get_patches(self):
        return ["test"]
""")
        runner = PluginTestRunner(plugins_dir=tmp_path)
        result = runner._test_manifest_exists("my-plugin")
        assert result.passed is True

    def test_test_manifest_missing(self, tmp_path):
        runner = PluginTestRunner(plugins_dir=tmp_path)
        result = runner._test_manifest_exists("nonexistent")
        assert result.passed is False

    def test_test_manifest_valid(self, tmp_path):
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "my-plugin", "version": "1.0.0", "type": "stealth",
            "entry_point": "plugin.py", "description": "Test",
        }))
        runner = PluginTestRunner(plugins_dir=tmp_path)
        result = runner._test_manifest_valid("my-plugin")
        assert result.passed is True

    def test_test_manifest_invalid_json(self, tmp_path):
        plugin_dir = tmp_path / "bad-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text("{invalid json")
        runner = PluginTestRunner(plugins_dir=tmp_path)
        result = runner._test_manifest_valid("bad-plugin")
        assert result.passed is False

    def test_test_manifest_missing_fields(self, tmp_path):
        plugin_dir = tmp_path / "incomplete"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({"name": "incomplete"}))
        runner = PluginTestRunner(plugins_dir=tmp_path)
        result = runner._test_manifest_valid("incomplete")
        assert result.passed is False
        assert "Missing fields" in result.message

    def test_test_entry_point_exists(self, tmp_path):
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "my-plugin", "version": "1.0.0", "type": "stealth",
            "entry_point": "plugin.py", "description": "Test",
        }))
        (plugin_dir / "plugin.py").write_text("# plugin")
        runner = PluginTestRunner(plugins_dir=tmp_path)
        result = runner._test_entry_point_exists("my-plugin")
        assert result.passed is True

    def test_test_plugin_instantiable(self, tmp_path):
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "my-plugin", "version": "1.0.0", "type": "stealth",
            "entry_point": "plugin.py", "description": "Test",
        }))
        (plugin_dir / "plugin.py").write_text("""
from tokenade.plugin.base import StealthPlugin
class MyPlugin(StealthPlugin):
    name = "my-plugin"
    version = "1.0.0"
    description = "Test"
    
    def get_patches(self):
        return ["test"]
""")
        runner = PluginTestRunner(plugins_dir=tmp_path)
        result = runner._test_plugin_instantiable("my-plugin")
        assert result.passed is True

    def test_full_test_suite(self, tmp_path):
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "my-plugin", "version": "1.0.0", "type": "stealth",
            "entry_point": "plugin.py", "description": "Test",
        }))
        (plugin_dir / "plugin.py").write_text("""
from tokenade.plugin.base import StealthPlugin
class MyPlugin(StealthPlugin):
    name = "my-plugin"
    version = "1.0.0"
    description = "Test"
    
    def get_patches(self):
        return ["test"]
""")
        runner = PluginTestRunner(plugins_dir=tmp_path)
        suite = runner.test_plugin("my-plugin")
        assert suite.passed is True
        assert suite.total == 8  # includes type_class_match (P2)
        assert suite.passed_count == 8
        assert suite.failed_count == 0

    def test_test_all(self, tmp_path):
        for name, ptype, base, methods in [
            ("stealth-p", "stealth", "StealthPlugin", "def get_patches(self): return []"),
            ("proxy-p", "proxy", "ProxyProviderPlugin", "def get_proxy(self, options=None): from tokenade.plugin.api import PluginResult; return PluginResult(success=True, data={})\n    def rotate(self, session_id=None): from tokenade.plugin.api import PluginResult; return PluginResult(success=True, data={})"),
            ("captcha-p", "captcha", "CaptchaPlugin", "def get_supported_types(self): return []\n    def solve(self, t, k=None, u=None): return {}"),
        ]:
            d = tmp_path / name
            d.mkdir()
            (d / "plugin.json").write_text(json.dumps({
                "name": name, "version": "1.0.0", "type": ptype,
                "entry_point": "plugin.py", "description": "Test",
            }))
            (d / "plugin.py").write_text(f"""
from tokenade.plugin.base import {base}
class Plugin({base}):
    name = "{name}"
    version = "1.0.0"
    description = "Test"
    {methods}
""")
        runner = PluginTestRunner(plugins_dir=tmp_path)
        suites = runner.test_all()
        assert len(suites) == 3
        assert all(s.passed for s in suites)


class TestPluginTestSuite:
    def test_summary_pass(self):
        suite = PluginTestSuite(
            plugin_name="test",
            results=[PluginTestResult("t1", True), PluginTestResult("t2", True)],
        )
        assert suite.passed is True
        assert "PASS" in suite.summary()

    def test_summary_fail(self):
        suite = PluginTestSuite(
            plugin_name="test",
            results=[PluginTestResult("t1", True), PluginTestResult("t2", False, "error")],
        )
        assert suite.passed is False
        assert "FAIL" in suite.summary()
