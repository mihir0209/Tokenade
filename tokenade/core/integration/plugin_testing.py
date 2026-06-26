"""
Plugin Testing Framework — validate plugins work correctly.

Tests plugin loading, hooks, configuration, and integration.
"""

import importlib.util
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PluginTestResult:
    """Result of a plugin test."""
    test_name: str
    passed: bool
    message: str = ""
    duration: float = 0.0


@dataclass
class PluginTestSuite:
    """Full test results for a plugin."""
    plugin_name: str
    results: List[PluginTestResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"{self.plugin_name}: {status} ({self.passed_count}/{self.total})"


class PluginTestRunner:
    """Test runner for plugins."""

    def __init__(self, plugins_dir: Optional[Path] = None):
        from tokenade.core.integration.plugin_loader import DEFAULT_PLUGINS_DIR
        self.plugins_dir = plugins_dir or DEFAULT_PLUGINS_DIR

    def test_plugin(self, plugin_name: str) -> PluginTestSuite:
        """Run all tests on a plugin."""
        suite = PluginTestSuite(plugin_name=plugin_name)

        suite.results.append(self._test_manifest_exists(plugin_name))
        suite.results.append(self._test_manifest_valid(plugin_name))
        suite.results.append(self._test_entry_point_exists(plugin_name))
        suite.results.append(self._test_entry_class_importable(plugin_name))
        suite.results.append(self._test_plugin_instantiable(plugin_name))
        suite.results.append(self._test_plugin_metadata(plugin_name))
        suite.results.append(self._test_plugin_type_methods(plugin_name))

        return suite

    def _test_manifest_exists(self, plugin_name: str) -> PluginTestResult:
        """Test that plugin.json exists."""
        path = self.plugins_dir / plugin_name / "plugin.json"
        exists = path.exists()
        return PluginTestResult(
            test_name="manifest_exists",
            passed=exists,
            message="" if exists else f"Missing: {path}",
        )

    def _test_manifest_valid(self, plugin_name: str) -> PluginTestResult:
        """Test that plugin.json is valid JSON with required fields."""
        path = self.plugins_dir / plugin_name / "plugin.json"
        if not path.exists():
            return PluginTestResult(test_name="manifest_valid", passed=False, message="No manifest")

        try:
            with open(path) as f:
                meta = json.load(f)
            required = ["name", "version", "type", "entry_point"]
            missing = [k for k in required if k not in meta]
            if missing:
                return PluginTestResult(
                    test_name="manifest_valid",
                    passed=False,
                    message=f"Missing fields: {missing}",
                )
            valid_types = ["handler", "export_format", "validator", "session_refresh",
                           "stealth", "proxy", "captcha"]
            if meta["type"] not in valid_types:
                return PluginTestResult(
                    test_name="manifest_valid",
                    passed=False,
                    message=f"Invalid type: {meta['type']}",
                )
            return PluginTestResult(test_name="manifest_valid", passed=True)
        except (json.JSONDecodeError, OSError) as e:
            return PluginTestResult(test_name="manifest_valid", passed=False, message=str(e))

    def _test_entry_point_exists(self, plugin_name: str) -> PluginTestResult:
        """Test that the entry point file exists."""
        plugin_dir = self.plugins_dir / plugin_name
        meta_path = plugin_dir / "plugin.json"
        if not meta_path.exists():
            return PluginTestResult(test_name="entry_point_exists", passed=False, message="No manifest")

        try:
            with open(meta_path) as f:
                meta = json.load(f)
            entry_point = plugin_dir / meta["entry_point"]
            exists = entry_point.exists()
            return PluginTestResult(
                test_name="entry_point_exists",
                passed=exists,
                message="" if exists else f"Missing: {entry_point}",
            )
        except (json.JSONDecodeError, OSError) as e:
            return PluginTestResult(test_name="entry_point_exists", passed=False, message=str(e))

    def _test_entry_class_importable(self, plugin_name: str) -> PluginTestResult:
        """Test that the entry class can be imported."""
        plugin_dir = self.plugins_dir / plugin_name
        meta_path = plugin_dir / "plugin.json"
        if not meta_path.exists():
            return PluginTestResult(test_name="entry_class_importable", passed=False, message="No manifest")

        try:
            with open(meta_path) as f:
                meta = json.load(f)
            entry_file = plugin_dir / meta["entry_point"]
            spec = importlib.util.spec_from_file_location(f"plugin_{plugin_name}", str(entry_file))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            entry_class_name = meta.get("entry_class", "")
            if entry_class_name:
                cls = getattr(module, entry_class_name, None)
                if cls is None:
                    return PluginTestResult(
                        test_name="entry_class_importable",
                        passed=False,
                        message=f"Class '{entry_class_name}' not found",
                    )
            return PluginTestResult(test_name="entry_class_importable", passed=True)
        except Exception as e:
            return PluginTestResult(test_name="entry_class_importable", passed=False, message=str(e))

    def _test_plugin_instantiable(self, plugin_name: str) -> PluginTestResult:
        """Test that the plugin can be instantiated."""
        plugin_dir = self.plugins_dir / plugin_name
        meta_path = plugin_dir / "plugin.json"
        if not meta_path.exists():
            return PluginTestResult(test_name="plugin_instantiable", passed=False, message="No manifest")

        try:
            with open(meta_path) as f:
                meta = json.load(f)
            entry_file = plugin_dir / meta["entry_point"]
            spec = importlib.util.spec_from_file_location(f"plugin_{plugin_name}", str(entry_file))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            entry_class_name = meta.get("entry_class", "")
            if entry_class_name:
                cls = getattr(module, entry_class_name, None)
                if cls:
                    instance = cls()
                    return PluginTestResult(test_name="plugin_instantiable", passed=True)

            # Auto-discover
            from tokenade.plugin.base import (
                PluginBase, SessionRefreshPlugin, SiteHandlerPlugin,
                ExportFormatPlugin, SessionValidatorPlugin,
                StealthPlugin, ProxyPlugin, CaptchaPlugin,
            )
            type_bases = {
                "handler": SiteHandlerPlugin,
                "export_format": ExportFormatPlugin,
                "validator": SessionValidatorPlugin,
                "session_refresh": SessionRefreshPlugin,
                "stealth": StealthPlugin,
                "proxy": ProxyPlugin,
                "captcha": CaptchaPlugin,
            }
            base = type_bases.get(meta["type"], PluginBase)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, base) and attr is not base:
                    instance = attr()
                    return PluginTestResult(test_name="plugin_instantiable", passed=True)

            return PluginTestResult(
                test_name="plugin_instantiable",
                passed=False,
                message="No instantiable class found",
            )
        except Exception as e:
            return PluginTestResult(test_name="plugin_instantiable", passed=False, message=str(e))

    def _test_plugin_metadata(self, plugin_name: str) -> PluginTestResult:
        """Test that plugin has required metadata."""
        plugin_dir = self.plugins_dir / plugin_name
        meta_path = plugin_dir / "plugin.json"
        if not meta_path.exists():
            return PluginTestResult(test_name="plugin_metadata", passed=False, message="No manifest")

        try:
            with open(meta_path) as f:
                meta = json.load(f)
            issues = []
            if not meta.get("name"):
                issues.append("missing name")
            if not meta.get("version"):
                issues.append("missing version")
            if not meta.get("description"):
                issues.append("missing description")
            if issues:
                return PluginTestResult(
                    test_name="plugin_metadata",
                    passed=False,
                    message=", ".join(issues),
                )
            return PluginTestResult(test_name="plugin_metadata", passed=True)
        except (json.JSONDecodeError, OSError) as e:
            return PluginTestResult(test_name="plugin_metadata", passed=False, message=str(e))

    def _test_plugin_type_methods(self, plugin_name: str) -> PluginTestResult:
        """Test that plugin implements required methods for its type."""
        plugin_dir = self.plugins_dir / plugin_name
        meta_path = plugin_dir / "plugin.json"
        if not meta_path.exists():
            return PluginTestResult(test_name="type_methods", passed=False, message="No manifest")

        try:
            with open(meta_path) as f:
                meta = json.load(f)
            entry_file = plugin_dir / meta["entry_point"]
            spec = importlib.util.spec_from_file_location(f"plugin_{plugin_name}", str(entry_file))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            from tokenade.plugin.base import (
                PluginBase, SessionRefreshPlugin, SiteHandlerPlugin,
                ExportFormatPlugin, SessionValidatorPlugin,
                StealthPlugin, ProxyPlugin, CaptchaPlugin,
            )
            type_methods = {
                "handler": ["can_handle", "extract_session", "inject_session"],
                "export_format": ["get_format_name", "export"],
                "validator": ["validate"],
                "session_refresh": ["can_refresh", "refresh"],
                "stealth": ["get_patches"],
                "proxy": ["get_proxy"],
                "captcha": ["get_supported_types", "solve"],
            }
            required = type_methods.get(meta["type"], [])
            if not required:
                return PluginTestResult(test_name="type_methods", passed=True)

            # Find instance
            entry_class_name = meta.get("entry_class", "")
            instance = None
            if entry_class_name:
                cls = getattr(module, entry_class_name, None)
                if cls:
                    instance = cls()
            else:
                type_bases = {
                    "handler": SiteHandlerPlugin,
                    "export_format": ExportFormatPlugin,
                    "validator": SessionValidatorPlugin,
                    "session_refresh": SessionRefreshPlugin,
                    "stealth": StealthPlugin,
                    "proxy": ProxyPlugin,
                    "captcha": CaptchaPlugin,
                }
                base = type_bases.get(meta["type"], PluginBase)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and issubclass(attr, base) and attr is not base:
                        instance = attr()
                        break

            if not instance:
                return PluginTestResult(
                    test_name="type_methods",
                    passed=False,
                    message="Could not instantiate plugin",
                )

            missing = [m for m in required if not hasattr(instance, m) or not callable(getattr(instance, m))]
            if missing:
                return PluginTestResult(
                    test_name="type_methods",
                    passed=False,
                    message=f"Missing methods: {missing}",
                )
            return PluginTestResult(test_name="type_methods", passed=True)
        except Exception as e:
            return PluginTestResult(test_name="type_methods", passed=False, message=str(e))

    def test_all(self) -> List[PluginTestSuite]:
        """Test all installed plugins."""
        suites = []
        if not self.plugins_dir.exists():
            return suites
        for d in sorted(self.plugins_dir.iterdir()):
            if d.is_dir() and not d.name.startswith(".") and (d / "plugin.json").exists():
                suites.append(self.test_plugin(d.name))
        return suites
