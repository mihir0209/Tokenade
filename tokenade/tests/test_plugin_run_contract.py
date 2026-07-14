"""White-box tests for the Plugin API 1.3 external-run contract."""

import pytest

from tokenade.plugin.api import (
    API_VERSION,
    PluginRunEnvelope,
    PluginRunError,
    PluginRunErrorCode,
    parse_plugin_run_spec,
    validate_plugin_run_input,
)


def _manifest(**run):
    return {"name": "test", "version": "1.0.0", "type": "handler", "run": run}


class TestPluginRunContract:
    def test_api_version_is_1_3_0(self):
        assert API_VERSION == "1.3.0"

    def test_missing_run_section_is_internal_only(self):
        assert parse_plugin_run_spec({"name": "internal"}) is None

    def test_parses_enabled_method_and_arguments(self):
        spec = parse_plugin_run_spec(_manifest(
            enabled=True,
            default_method="process",
            methods={
                "process": {
                    "arguments": {
                        "session_file": {"type": "path", "required": True},
                        "output_dir": {"type": "path", "default": None},
                    }
                }
            },
        ))
        assert spec.enabled is True
        assert spec.default_method == "process"
        assert spec.methods["process"].arguments["session_file"].required is True

    @pytest.mark.parametrize("bad", [
        {"enabled": "yes", "methods": {"process": {}}},
        {"enabled": True, "methods": {"delete": {}}},
        {"enabled": True, "methods": {"process": {"arguments": {"x": {"type": "date"}}}}},
        {"enabled": True, "default_method": "run", "methods": {"process": {}}},
    ])
    def test_rejects_malformed_run_section(self, bad):
        with pytest.raises(ValueError):
            parse_plugin_run_spec(_manifest(**bad))

    def test_validates_defaults_and_types(self):
        spec = parse_plugin_run_spec(_manifest(
            enabled=True,
            methods={
                "process": {
                    "arguments": {
                        "path": {"type": "path", "required": True},
                        "count": {"type": "int", "default": 2},
                        "enabled": {"type": "bool", "default": False},
                        "ratio": {"type": "float", "default": 1},
                        "tags": {"type": "list", "default": []},
                        "metadata": {"type": "object", "default": {}},
                    }
                }
            },
        ))
        request = validate_plugin_run_input(spec.methods["process"], {"path": "/tmp/x"})
        assert request == {
            "path": "/tmp/x",
            "count": 2,
            "enabled": False,
            "ratio": 1.0,
            "tags": [],
            "metadata": {},
        }

    def test_rejects_unknown_and_missing_arguments(self):
        spec = parse_plugin_run_spec(_manifest(
            enabled=True,
            methods={"process": {"arguments": {"required": {"required": True}}}},
        ))
        method = spec.methods["process"]
        with pytest.raises(ValueError, match="unknown arguments"):
            validate_plugin_run_input(method, {"extra": 1})
        with pytest.raises(ValueError, match="missing required argument"):
            validate_plugin_run_input(method, {})

    def test_rejects_wrong_types(self):
        spec = parse_plugin_run_spec(_manifest(
            enabled=True,
            methods={"process": {"arguments": {"count": {"type": "int"}}}},
        ))
        with pytest.raises(ValueError, match="must be an int"):
            validate_plugin_run_input(spec.methods["process"], {"count": "1"})

    def test_envelope_serializes_error(self):
        envelope = PluginRunEnvelope(
            success=False,
            plugin="test",
            method="process",
            error=PluginRunError(
                PluginRunErrorCode.ARGUMENT_ERROR,
                "bad input",
            ),
        )
        assert envelope.to_dict() == {
            "success": False,
            "plugin": "test",
            "method": "process",
            "data": None,
            "error": {
                "code": "PLUGIN_ARGUMENT_ERROR",
                "message": "bad input",
            },
        }
