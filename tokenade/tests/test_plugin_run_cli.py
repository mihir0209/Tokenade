"""Tests for the generalized ``tokenade run`` CLI command."""

import json

import pytest

from tokenade.cli import _build_parser, cmd_run


def test_run_parser_has_only_runner_input_options():
    args = _build_parser().parse_args([
        "run", "example", "refresh_session", "--input", "request.json",
    ])
    assert args.plugin_name == "example"
    assert args.method == "refresh_session"
    assert args.input == "request.json"


def test_run_cli_emits_json_success(monkeypatch, tmp_path, capsys):
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"value": 1}))

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
            assert method is None
            return Result()

    monkeypatch.setattr("tokenade.core.integration.plugin_runner.PluginRunner", Runner)
    args = _build_parser().parse_args(["run", "example", "--input", str(request_file)])
    cmd_run(args)
    assert json.loads(capsys.readouterr().out)["success"] is True


def test_run_cli_invalid_input_exits_two(tmp_path, capsys):
    request_file = tmp_path / "request.json"
    request_file.write_text("not json")
    args = _build_parser().parse_args(["run", "example", "--input", str(request_file)])
    with pytest.raises(SystemExit) as exc:
        cmd_run(args)
    assert exc.value.code == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "PLUGIN_ARGUMENT_ERROR"
