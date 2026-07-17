"""Tests for the generalized ``tokenade run`` CLI command."""

import json

import pytest

from tokenade.cli import _build_parser, cmd_run


def test_run_parser_has_only_runner_input_options():
    args = _build_parser().parse_args(["run", "--request", "request.json"])
    assert args.request == "request.json"


def test_run_cli_emits_json_success(monkeypatch, tmp_path, capsys):
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({
        "version": "1",
        "operation": "run",
        "plugins": [{
            "name": "example",
            "roles": {"run": {"method": "process"}},
            "config": {"value": 1},
        }],
    }))

    class Result:
        success = True

        def to_dict(self):
            return {"success": True, "plugin": "example", "method": "run", "data": {"ok": True}, "error": None}

    class Runner:
        def __init__(self):
            pass

        def run(self, plugin, request, method):
            assert plugin == "example"
            assert request == {"value": 1}
            assert method == "process"
            return Result()

    monkeypatch.setattr("tokenade.core.integration.plugin_runner.PluginRunner", Runner)
    monkeypatch.setattr("tokenade.core.request_config.validate_required_plugins", lambda plugins: None)
    args = _build_parser().parse_args(["run", "--request", str(request_file)])
    cmd_run(args)
    output = json.loads(capsys.readouterr().out)
    assert output["success"] is True
    assert output["results"][0]["plugin"] == "example"


def test_run_cli_invalid_input_exits_two(tmp_path, capsys):
    request_file = tmp_path / "request.json"
    request_file.write_text("not json")
    args = _build_parser().parse_args(["run", "--request", str(request_file)])
    with pytest.raises(SystemExit) as exc:
        cmd_run(args)
    assert exc.value.code == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "PLUGIN_ARGUMENT_ERROR"


def test_run_cli_rejects_non_run_operation(monkeypatch, tmp_path, capsys):
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"operation": "gateway", "plugins": []}))
    monkeypatch.setattr("tokenade.core.request_config.validate_required_plugins", lambda plugins: None)

    args = _build_parser().parse_args(["run", "--request", str(request_file)])
    with pytest.raises(SystemExit) as exc:
        cmd_run(args)

    assert exc.value.code == 2
    assert "operation must be 'run'" in json.loads(capsys.readouterr().out)["error"]["message"]


def test_run_cli_requires_roles_run(monkeypatch, tmp_path, capsys):
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({
        "operation": "run",
        "plugins": [{"name": "example", "roles": {"site_handler": {}}, "config": {}}],
    }))
    monkeypatch.setattr("tokenade.core.request_config.validate_required_plugins", lambda plugins: None)

    args = _build_parser().parse_args(["run", "--request", str(request_file)])
    with pytest.raises(SystemExit) as exc:
        cmd_run(args)

    assert exc.value.code == 2
    assert "roles.run" in json.loads(capsys.readouterr().out)["error"]["message"]


def test_run_cli_stops_on_first_error(monkeypatch, tmp_path, capsys):
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({
        "operation": "run",
        "plugins": [
            {"name": "bad", "roles": {"run": {"method": "process"}}, "config": {}},
            {"name": "skipped", "roles": {"run": {"method": "process"}}, "config": {}},
        ],
    }))

    class Result:
        success = False

        def __init__(self, plugin):
            self.plugin = plugin
            self.error = None

        def to_dict(self):
            return {"success": False, "plugin": self.plugin, "method": "process", "data": None, "error": {"code": "PLUGIN_ARGUMENT_ERROR", "message": "bad"}}

    class Runner:
        calls = []

        def run(self, plugin, request, method):
            self.calls.append(plugin)
            return Result(plugin)

    runner = Runner()
    monkeypatch.setattr("tokenade.core.integration.plugin_runner.PluginRunner", lambda: runner)
    monkeypatch.setattr("tokenade.core.request_config.validate_required_plugins", lambda plugins: None)

    args = _build_parser().parse_args(["run", "--request", str(request_file)])
    with pytest.raises(SystemExit) as exc:
        cmd_run(args)

    assert exc.value.code == 2
    assert runner.calls == ["bad"]
    assert len(json.loads(capsys.readouterr().out)["results"]) == 1


def test_run_cli_skips_optional_missing_plugin(monkeypatch, tmp_path, capsys):
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({
        "operation": "run",
        "plugins": [{
            "name": "optional-missing",
            "required": False,
            "roles": {"run": {"method": "process"}},
            "config": {},
        }],
    }))
    monkeypatch.setattr("tokenade.core.request_config.validate_required_plugins", lambda plugins: None)

    args = _build_parser().parse_args(["run", "--request", str(request_file)])
    cmd_run(args)

    output = json.loads(capsys.readouterr().out)
    assert output["success"] is True
    assert output["results"][0]["data"] == {
        "skipped": True,
        "reason": "optional plugin not installed",
    }


def test_run_cli_rejects_non_string_method(monkeypatch, tmp_path, capsys):
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({
        "operation": "run",
        "plugins": [{
            "name": "example",
            "roles": {"run": {"method": 123}},
            "config": {},
        }],
    }))
    monkeypatch.setattr("tokenade.core.request_config.validate_required_plugins", lambda plugins: None)

    args = _build_parser().parse_args(["run", "--request", str(request_file)])
    with pytest.raises(SystemExit) as exc:
        cmd_run(args)

    assert exc.value.code == 2
    assert "roles.run.method must be a string" in json.loads(capsys.readouterr().out)["error"]["message"]
