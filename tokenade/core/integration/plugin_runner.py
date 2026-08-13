"""Execute explicitly runnable plugins through the normal plugin lifecycle."""

import inspect
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from tokenade.core.integration.plugin_loader import PluginLoader, PluginState
from tokenade.plugin.api import (
    PluginResult,
    PluginRunEnvelope,
    PluginRunError,
    PluginRunErrorCode,
    parse_plugin_run_spec,
    validate_plugin_run_input,
)

logger = logging.getLogger(__name__)


class PluginRunner:
    """Run one installed plugin operation from a validated request."""

    def __init__(self, plugins_dir: Optional[Path] = None):
        self.plugins_dir = plugins_dir

    def run(
        self,
        plugin_name: str,
        request: Dict[str, Any],
        method: Optional[str] = None,
    ) -> PluginRunEnvelope:
        """Run a plugin and always return a serializable result envelope."""
        loader = PluginLoader(self.plugins_dir) if self.plugins_dir else PluginLoader()
        manifest = loader.get_manifest(plugin_name)
        if manifest is None:
            return self._error(
                plugin_name,
                method or "",
                PluginRunErrorCode.LOAD_ERROR,
                f"plugin not installed: {plugin_name}",
            )
        selected_method = method or self._manifest_default_method(manifest)

        try:
            spec = parse_plugin_run_spec(manifest)
            if spec is None or not spec.enabled:
                return self._error(
                    plugin_name,
                    selected_method,
                    PluginRunErrorCode.MANIFEST_ERROR,
                    "plugin does not declare enabled external execution",
                )
            if selected_method not in spec.methods:
                return self._error(
                    plugin_name,
                    selected_method,
                    PluginRunErrorCode.METHOD_ERROR,
                    f"method is not declared: {selected_method}",
                )
            kwargs = validate_plugin_run_input(spec.methods[selected_method], request)
        except ValueError as exc:
            return self._error(
                plugin_name,
                selected_method,
                PluginRunErrorCode.ARGUMENT_ERROR,
                str(exc),
            )

        loaded = None
        try:
            loaded = loader.load_by_name(plugin_name)
            if loaded is None or loaded.instance is None:
                return self._error(
                    plugin_name,
                    selected_method,
                    PluginRunErrorCode.LOAD_ERROR,
                    "plugin could not be loaded",
                )
            if loaded.state != PluginState.ACTIVE:
                return self._error(
                    plugin_name,
                    selected_method,
                    PluginRunErrorCode.LOAD_ERROR,
                    loaded.error or f"plugin is not active ({loaded.state.value})",
                )

            operation = getattr(loaded.instance, selected_method, None)
            if operation is None or not callable(operation):
                return self._error(
                    plugin_name,
                    selected_method,
                    PluginRunErrorCode.METHOD_ERROR,
                    f"plugin has no callable method: {selected_method}",
                )

            result = operation(**kwargs)
            if inspect.isawaitable(result):
                raise TypeError("async plugin methods are not supported by this runner")
            return self._success(plugin_name, selected_method, result)
        except Exception as exc:
            logger.exception("Plugin %s.%s failed", plugin_name, selected_method)
            return self._error(
                plugin_name,
                selected_method,
                PluginRunErrorCode.PLUGIN_FAILURE,
                str(exc),
            )
        finally:
            if loaded is not None:
                loader.unload(plugin_name)

    @staticmethod
    def _manifest_default_method(manifest: Dict[str, Any]) -> str:
        raw_run = manifest.get("run")
        if isinstance(raw_run, dict) and raw_run.get("default_method"):
            return raw_run["default_method"]
        return ""

    @staticmethod
    def _success(plugin: str, method: str, result: Any) -> PluginRunEnvelope:
        if isinstance(result, PluginResult):
            return PluginRunEnvelope(result.success, plugin, method, result.data,
                                     PluginRunError(PluginRunErrorCode.PLUGIN_FAILURE, result.error)
                                     if not result.success and result.error else None)
        if isinstance(result, dict):
            return PluginRunEnvelope(True, plugin, method, result)
        return PluginRunEnvelope(True, plugin, method, result)

    @staticmethod
    def _error(plugin: str, method: str, code: PluginRunErrorCode, message: str) -> PluginRunEnvelope:
        return PluginRunEnvelope(False, plugin, method, error=PluginRunError(code, message))
