"""
Plugin Testing Framework — validate plugins work correctly.

Tests plugin loading, hooks, configuration, and integration.
"""

import importlib.util
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

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
        suite.results.append(self._test_api_compatibility(plugin_name))
        suite.results.append(self._test_run_manifest(plugin_name))
        suite.results.append(self._test_plugin_type_methods(plugin_name))
        suite.results.append(self._test_type_class_match(plugin_name))
        suite.results.append(self._test_runtime_dependencies(plugin_name))

        return suite

    def _test_runtime_dependencies(self, plugin_name: str) -> PluginTestResult:
        """Test platform-applicable Python and system runtime requirements."""
        try:
            with open(self.plugins_dir / plugin_name / "plugin.json") as f:
                meta = json.load(f)
            from tokenade.core.integration.plugin_dependencies import check_runtime_dependencies
            report = check_runtime_dependencies(meta)
            message = "; ".join(
                f"{issue.kind} {issue.requirement}: {issue.reason}" for issue in report.issues
            )
            return PluginTestResult("runtime_dependencies", report.ready, message)
        except Exception as exc:
            return PluginTestResult("runtime_dependencies", False, str(exc))

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
            valid_types = [
                "handler", "export_format", "validator", "session_refresh",
                "stealth", "proxy", "captcha", "notification",
                "challenge_detector", "challenge_solver",
                "egress_provider", "fingerprint_oracle",
            ]
            if meta["type"] not in valid_types:
                return PluginTestResult(
                    test_name="manifest_valid",
                    passed=False,
                    message=f"Invalid type: {meta['type']}",
                )
            # Honesty: no hand-edited vanity metrics in official manifests
            vanity = [k for k in ("downloads", "rating") if k in meta]
            if vanity:
                return PluginTestResult(
                    test_name="manifest_valid",
                    passed=False,
                    message=f"Vanity metrics not allowed until real telemetry: {vanity}",
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
            from tokenade.plugin.base import PluginBase, PLUGIN_TYPE_BASE_CLASSES
            bases = PLUGIN_TYPE_BASE_CLASSES.get(meta.get("type", ""), (PluginBase,))
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if not isinstance(attr, type):
                    continue
                for base in bases:
                    if issubclass(attr, base) and attr is not base:
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

    def _test_api_compatibility(self, plugin_name: str) -> PluginTestResult:
        """Test manifest and entry class API version declarations."""
        plugin_dir = self.plugins_dir / plugin_name
        try:
            with open(plugin_dir / "plugin.json") as f:
                meta = json.load(f)
            from tokenade.plugin.api import API_VERSION

            if meta.get("api_version") != API_VERSION:
                return PluginTestResult(
                    "api_compatibility", False,
                    f"Manifest API {meta.get('api_version')!r} != {API_VERSION!r}",
                )

            entry_file = plugin_dir / meta["entry_point"]
            spec = importlib.util.spec_from_file_location(f"api_{plugin_name}", str(entry_file))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            entry_class = getattr(module, meta.get("entry_class", ""), None)
            if entry_class is None:
                from tokenade.plugin.base import (
                    CaptchaPlugin, ChallengeDetectorPlugin, ChallengeSolverPlugin,
                    EgressProviderPlugin, ExportFormatPlugin, FingerprintOraclePlugin,
                    NotificationPlugin,
                    PluginBase, ProxyProviderPlugin, SessionRefreshPlugin,
                    SessionValidatorPlugin, SiteHandlerPlugin, StealthPlugin,
                )
                base_map = {
                    "handler": SiteHandlerPlugin,
                    "egress_provider": EgressProviderPlugin,
                    "fingerprint_oracle": FingerprintOraclePlugin,
                    "export_format": ExportFormatPlugin,
                    "validator": SessionValidatorPlugin,
                    "session_refresh": SessionRefreshPlugin,
                    "stealth": StealthPlugin,
                    "proxy": ProxyProviderPlugin,
                    "notification": NotificationPlugin,
                    "captcha": CaptchaPlugin,
                    "challenge_detector": ChallengeDetectorPlugin,
                    "challenge_solver": ChallengeSolverPlugin,
                }
                base = base_map.get(meta.get("type"), PluginBase)
                for candidate in vars(module).values():
                    if isinstance(candidate, type) and issubclass(candidate, base) and candidate is not base:
                        entry_class = candidate
                        break
            if entry_class is None:
                return PluginTestResult("api_compatibility", False, "Entry class not found")
            class_api = getattr(entry_class, "API_VERSION", None)
            if class_api != API_VERSION:
                return PluginTestResult(
                    "api_compatibility", False,
                    f"Class API {class_api!r} != {API_VERSION!r}",
                )
            return PluginTestResult("api_compatibility", True)
        except Exception as e:
            return PluginTestResult("api_compatibility", False, str(e))

    def _test_run_manifest(self, plugin_name: str) -> PluginTestResult:
        """Test optional API 1.3 external-run manifest metadata."""
        try:
            with open(self.plugins_dir / plugin_name / "plugin.json") as f:
                meta = json.load(f)
            from tokenade.plugin.api import parse_plugin_run_spec
            parse_plugin_run_spec(meta)
            return PluginTestResult("run_manifest", True)
        except Exception as e:
            return PluginTestResult("run_manifest", False, str(e))

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
                PluginBase, PLUGIN_TYPE_BASE_CLASSES, PLUGIN_TYPE_REQUIRED_METHODS,
            )
            required = PLUGIN_TYPE_REQUIRED_METHODS.get(meta.get("type", ""), [])
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
                bases = PLUGIN_TYPE_BASE_CLASSES.get(meta.get("type", ""), (PluginBase,))
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if not isinstance(attr, type):
                        continue
                    for base in bases:
                        if issubclass(attr, base) and attr is not base:
                            instance = attr()
                            break
                    if instance:
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

    def _test_type_class_match(self, plugin_name: str) -> PluginTestResult:
        """Manifest type must match the entry class base (no mis-typed plugins)."""
        plugin_dir = self.plugins_dir / plugin_name
        meta_path = plugin_dir / "plugin.json"
        if not meta_path.exists():
            return PluginTestResult(test_name="type_class_match", passed=False, message="No manifest")

        try:
            with open(meta_path) as f:
                meta = json.load(f)
            entry_class_name = meta.get("entry_class", "")
            if not entry_class_name:
                # Legacy manifests may omit entry_class; type_methods already covered them
                return PluginTestResult(
                    test_name="type_class_match",
                    passed=True,
                    message="skipped (no entry_class)",
                )

            entry_file = plugin_dir / meta["entry_point"]
            spec = importlib.util.spec_from_file_location(
                f"plugin_match_{plugin_name}", str(entry_file)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            cls = getattr(module, entry_class_name, None)
            if cls is None:
                return PluginTestResult(
                    test_name="type_class_match",
                    passed=False,
                    message=f"Class {entry_class_name} not found",
                )

            from tokenade.plugin.base import PLUGIN_TYPE_BASE_CLASSES
            expected = PLUGIN_TYPE_BASE_CLASSES.get(meta.get("type", ""), ())

            if not expected:
                return PluginTestResult(
                    test_name="type_class_match",
                    passed=False,
                    message=f"Unknown type {meta.get('type')}",
                )

            if any(issubclass(cls, base) for base in expected):
                return PluginTestResult(test_name="type_class_match", passed=True)

            return PluginTestResult(
                test_name="type_class_match",
                passed=False,
                message=(
                    f"type={meta.get('type')} but {entry_class_name} is not "
                    f"subclass of {[b.__name__ for b in expected]}"
                ),
            )
        except Exception as e:
            return PluginTestResult(test_name="type_class_match", passed=False, message=str(e))

    def test_all(self) -> List[PluginTestSuite]:
        """Test all installed plugins."""
        suites = []
        if not self.plugins_dir.exists():
            return suites
        for d in sorted(self.plugins_dir.iterdir()):
            if d.is_dir() and not d.name.startswith(".") and (d / "plugin.json").exists():
                suites.append(self.test_plugin(d.name))
        return suites
