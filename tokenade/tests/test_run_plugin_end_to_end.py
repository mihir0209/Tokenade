"""End-to-end tests for ``tokenade run`` (request.json -> cmd_run -> PluginRunner).

Covers the full request flow against a real fake plugin installed in a
temporary plugins directory: successful invocation, default method selection,
failure envelopes and exit codes, optional plugin skipping, and missing
required plugin rejection.
"""

import json
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tokenade.plugin.api import PluginRunErrorCode


FAKE_PLUGIN_JSON = {
    "name": "hello-handler",
    "version": "1.0.0",
    "description": "Fake runnable plugin for end-to-end tests",
    "author": "Tokenade Team",
    "type": "handler",
    "entry_point": "plugin.py",
    "entry_class": "HelloHandler",
    "api_version": "1.3.0",
    "run": {
        "enabled": True,
        "default_method": "process",
        "methods": {
            "process": {
                "arguments": {
                    "greeting": {
                        "type": "string",
                        "required": False,
                        "default": "hi",
                    },
                    "count": {"type": "int", "required": False, "default": 1},
                    "fail": {"type": "bool", "required": False, "default": False},
                }
            }
        },
    },
}

FAKE_PLUGIN_PY = """\
class HelloHandler:
    API_VERSION = "1.3.0"

    def process(self, greeting="hi", count=1, fail=False):
        if fail:
            raise ValueError("kaboom")
        return {"greeting": greeting, "count": count}
"""


@pytest.fixture
def fake_plugins(tmp_path, monkeypatch):
    """Install a fake runnable plugin and point the CLI plumbing at it."""
    plugins_dir = tmp_path / "plugins"
    plugin_dir = plugins_dir / "hello-handler"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(json.dumps(FAKE_PLUGIN_JSON))
    (plugin_dir / "plugin.py").write_text(FAKE_PLUGIN_PY)

    from tokenade.core.integration import plugin_loader as loader_mod
    from tokenade.core.integration import plugin_runner as runner_mod
    import tokenade.core.request_config as request_config_mod

    real_loader = loader_mod.PluginLoader
    real_runner = runner_mod.PluginRunner

    def loader_factory(*args, **kwargs):
        if args or kwargs:
            return real_loader(*args, **kwargs)
        return real_loader(plugins_dir)

    monkeypatch.setattr(loader_mod, "PluginLoader", loader_factory)
    monkeypatch.setattr(request_config_mod, "PluginLoader", loader_factory)
    monkeypatch.setattr(
        runner_mod,
        "PluginRunner",
        lambda *args, **kwargs: real_runner(plugins_dir, *args, **kwargs),
    )
    return plugins_dir


def _run_cmd(request_path, expect_exit=None):
    from tokenade.cli import cmd_run

    args = SimpleNamespace(request=str(request_path))
    out = StringIO()
    with patch("sys.stdout", out):
        if expect_exit is None:
            cmd_run(args)
        else:
            with pytest.raises(SystemExit) as exc:
                cmd_run(args)
            assert exc.value.code == expect_exit
    return json.loads(out.getvalue())


def _write_request(tmp_path, plugins):
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps({"operation": "run", "version": "1", "plugins": plugins})
    )
    return request


def test_run_end_to_end_success(fake_plugins, tmp_path):
    request = _write_request(
        tmp_path,
        [
            {
                "name": "hello-handler",
                "roles": {"run": {"method": "process"}},
                "config": {"greeting": "hey", "count": 2},
            }
        ],
    )

    envelope = _run_cmd(request)
    assert envelope["success"] is True
    assert envelope["operation"] == "run"
    assert envelope["error"] is None
    result = envelope["results"][0]
    assert result["plugin"] == "hello-handler"
    assert result["method"] == "process"
    assert result["data"] == {"greeting": "hey", "count": 2}
    assert result["error"] is None


def test_run_end_to_end_default_method_and_defaults(fake_plugins, tmp_path):
    request = _write_request(
        tmp_path,
        [{"name": "hello-handler", "roles": {"run": {}}, "config": {}}],
    )

    envelope = _run_cmd(request)
    assert envelope["success"] is True
    result = envelope["results"][0]
    assert result["method"] == "process"
    assert result["data"] == {"greeting": "hi", "count": 1}


def test_run_end_to_end_plugin_failure(fake_plugins, tmp_path):
    request = _write_request(
        tmp_path,
        [
            {
                "name": "hello-handler",
                "roles": {"run": {"method": "process"}},
                "config": {"fail": True},
            }
        ],
    )

    envelope = _run_cmd(request, expect_exit=1)
    assert envelope["success"] is False
    result = envelope["results"][0]
    assert result["success"] is False
    assert result["method"] == "process"
    assert result["error"]["code"] == PluginRunErrorCode.PLUGIN_FAILURE.value
    assert "kaboom" in result["error"]["message"]


def test_run_end_to_end_optional_missing_plugin_skipped(fake_plugins, tmp_path):
    request = _write_request(
        tmp_path,
        [
            {
                "name": "not-installed",
                "required": False,
                "roles": {"run": {"method": "process"}},
                "config": {},
            }
        ],
    )

    envelope = _run_cmd(request)
    assert envelope["success"] is True
    result = envelope["results"][0]
    assert result["success"] is True
    assert result["data"] == {
        "skipped": True,
        "reason": "optional plugin not installed",
    }


def test_run_end_to_end_missing_required_plugin_rejected(fake_plugins, tmp_path):
    request = _write_request(
        tmp_path,
        [
            {
                "name": "not-installed",
                "required": True,
                "roles": {"run": {"method": "process"}},
                "config": {},
            }
        ],
    )

    envelope = _run_cmd(request, expect_exit=2)
    assert envelope["success"] is False
    assert envelope["error"]["code"] == PluginRunErrorCode.ARGUMENT_ERROR.value
    assert "Required plugin not installed" in envelope["error"]["message"]


def test_runner_infers_default_method_when_manifest_omits_it(tmp_path):
    """CR-05: PluginRunner resolves spec.default_method when default_method is omitted from manifest."""
    plugin_dir = tmp_path / "plugins" / "nodefault-handler"
    plugin_dir.mkdir(parents=True)
    manifest = {
        "name": "nodefault-handler",
        "version": "1.0.0",
        "type": "handler",
        "entry_point": "plugin.py",
        "entry_class": "NoDefaultHandler",
        "api_version": "1.3.0",
        "run": {
            "enabled": True,
            # No "default_method" key — parse_plugin_run_spec defaults to first method
            "methods": {
                "process": {
                    "arguments": {
                        "name": {"type": "string", "required": False, "default": "world"}
                    }
                }
            },
        },
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
    (plugin_dir / "plugin.py").write_text(
        "class NoDefaultHandler:\n"
        "    API_VERSION = '1.3.0'\n"
        "    def process(self, name='world'):\n"
        "        return {'hello': name}\n"
    )

    from tokenade.core.integration.plugin_runner import PluginRunner

    runner = PluginRunner(plugins_dir=tmp_path / "plugins")
    envelope = runner.run("nodefault-handler", {})
    assert envelope.success is True
    assert envelope.method == "process"
    assert envelope.data == {"hello": "world"}
