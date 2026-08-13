"""White-box tests for the lifecycle-aware PluginRunner."""

import json
from pathlib import Path
from unittest.mock import patch

from tokenade.core.integration.plugin_loader import LoadedPlugin, PluginState
from tokenade.core.integration.plugin_runner import PluginRunner


def _write_plugin(tmp_path: Path, source: str, run: dict) -> None:
    plugin_dir = tmp_path / "test-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.py").write_text(source)
    manifest = {
        "name": "test-plugin",
        "version": "1.0.0",
        "type": "handler",
        "entry_point": "plugin.py",
        "entry_class": "TestPlugin",
    }
    if run:
        manifest["run"] = run
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest))


PLUGIN_SOURCE = """
from tokenade.plugin.base import SiteHandlerPlugin
from tokenade.plugin.api import PluginResult

class TestPlugin(SiteHandlerPlugin):
    API_VERSION = "1.3.0"
    name = "test-plugin"

    def on_load(self):
        self.loaded = True

    def on_unload(self):
        self.unloaded = True

    def extract_session(self, browser_context, url=""):
        return PluginResult(success=True, data={})

    def inject_session(self, browser_context, session):
        return PluginResult(success=True, data={})

    def process(self, session_file, output_dir=None):
        return PluginResult(success=True, data={"session_file": session_file, "output_dir": output_dir})

    def refresh_session(self, session):
        return PluginResult(success=False, error="expired")
"""


RUN_SPEC = {
    "enabled": True,
    "default_method": "process",
    "methods": {
        "process": {"arguments": {
            "session_file": {"type": "path", "required": True},
            "output_dir": {"type": "path", "default": None},
        }},
        "refresh_session": {"arguments": {
            "session": {"type": "object", "required": True},
        }},
    },
}


class TestPluginRunner:
    def test_runs_default_method_and_unloads(self, tmp_path):
        _write_plugin(tmp_path, PLUGIN_SOURCE, RUN_SPEC)
        result = PluginRunner(tmp_path).run(
            "test-plugin", {"session_file": "source.tokenade"}
        )
        assert result.to_dict() == {
            "success": True,
            "plugin": "test-plugin",
            "method": "process",
            "data": {"session_file": "source.tokenade", "output_dir": None},
            "error": None,
        }

    def test_selects_explicit_method(self, tmp_path):
        _write_plugin(tmp_path, PLUGIN_SOURCE, RUN_SPEC)
        result = PluginRunner(tmp_path).run(
            "test-plugin", {"session": {"site": "test"}}, "refresh_session"
        )
        assert result.success is False
        assert result.method == "refresh_session"
        assert result.error.code.value == "PLUGIN_FAILURE"
        assert result.error.message == "expired"

    def test_rejects_internal_plugin(self, tmp_path):
        _write_plugin(tmp_path, PLUGIN_SOURCE, {})
        result = PluginRunner(tmp_path).run("test-plugin", {})
        assert result.success is False
        assert result.error.code.value == "PLUGIN_MANIFEST_ERROR"

    def test_rejects_bad_request_before_loading(self, tmp_path):
        _write_plugin(tmp_path, PLUGIN_SOURCE, RUN_SPEC)
        result = PluginRunner(tmp_path).run("test-plugin", {"unknown": 1})
        assert result.success is False
        assert result.error.code.value == "PLUGIN_ARGUMENT_ERROR"

    def test_missing_plugin_is_structured_error(self, tmp_path):
        result = PluginRunner(tmp_path).run("missing", {})
        assert result.success is False
        assert result.error.code.value == "PLUGIN_LOAD_ERROR"

    def test_rejects_plugin_that_is_not_active(self, tmp_path):
        _write_plugin(tmp_path, PLUGIN_SOURCE, RUN_SPEC)
        loaded = LoadedPlugin(
            name="test-plugin",
            version="1.0.0",
            description="",
            plugin_type="handler",
            module=None,
            entry_class=None,
            instance=object(),
            state=PluginState.LOADED,
        )
        with patch(
            "tokenade.core.integration.plugin_loader.PluginLoader.load_by_name",
            return_value=loaded,
        ):
            result = PluginRunner(tmp_path).run(
                "test-plugin", {"session_file": "source.tokenade"}
            )

        assert result.success is False
        assert result.error.code.value == "PLUGIN_LOAD_ERROR"
        assert "not active" in result.error.message
