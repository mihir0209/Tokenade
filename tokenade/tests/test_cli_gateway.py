"""Tests for the gateway CLI command."""

import json

import pytest

from tokenade.cli import _build_parser, cmd_gateway


def test_gateway_is_visible_after_live_runtime_witness():
    parser = _build_parser()
    help_text = parser.format_help()

    assert "gateway" in help_text
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["gateway", "--help"])
    assert exc.value.code == 0


def test_gateway_parser_requires_request():
    args = _build_parser().parse_args(["gateway", "--request", "request.json"])

    assert args.command == "gateway"
    assert args.request == "request.json"


def test_export_parser_has_network_and_proxy_metadata_flags():
    args = _build_parser().parse_args([
        "export",
        "--browser-name", "firefox",
        "--stamp-network",
        "--include-source-ip",
        "--proxy-plugin", "brightdata",
    ])

    assert args.stamp_network is True
    assert args.include_source_ip is True
    assert args.proxy_plugin == "brightdata"


def test_gateway_cli_invalid_request_exits_two(tmp_path, capsys):
    request_file = tmp_path / "request.json"
    request_file.write_text("not json")

    args = _build_parser().parse_args(["gateway", "--request", str(request_file)])
    with pytest.raises(SystemExit) as exc:
        cmd_gateway(args)

    assert exc.value.code == 2
    output = json.loads(capsys.readouterr().out)
    assert output["success"] is False
    assert output["operation"] == "gateway"
    assert output["error"]["code"] == "GATEWAY_CONFIG_ERROR"


def test_gateway_cli_starts_control_plane_after_validation(monkeypatch, tmp_path, capsys):
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"operation": "gateway", "plugins": []}))

    class ControlPlane:
        served = False

        def status(self):
            return {"success": True, "operation": "gateway", "session_count": 1}

        def serve_forever(self):
            self.served = True

    control_plane = ControlPlane()
    monkeypatch.setattr("tokenade.core.request_config.validate_required_plugins", lambda plugins: None)
    monkeypatch.setattr("tokenade.core.gateway.server.create_gateway_control_plane", lambda request: control_plane)

    args = _build_parser().parse_args(["gateway", "--request", str(request_file)])
    cmd_gateway(args)

    assert json.loads(capsys.readouterr().out)["session_count"] == 1
    assert control_plane.served is True
