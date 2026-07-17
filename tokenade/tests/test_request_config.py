"""Tests for nested Tokenade request.json validation."""

import json

import pytest

from tokenade.core.request_config import (
    RequestConfigError,
    parse_request_config,
    load_request_config,
    validate_required_plugins,
)


def test_parse_nested_request_with_dynamic_plugin_config():
    request = parse_request_config({
        "version": "1",
        "operation": "run",
        "plugins": [{
            "name": "alphaM",
            "required": True,
            "roles": {
                "site_handler": {"sites": ["example"]},
                "proxy_provider": {"mode": "sticky"},
            },
            "config": {"deep": {"plugin": "owned"}},
        }],
    })

    assert request.operation == "run"
    assert request.plugins[0].name == "alphaM"
    assert request.plugins[0].roles["proxy_provider"] == {"mode": "sticky"}
    assert request.plugins[0].config == {"deep": {"plugin": "owned"}}


@pytest.mark.parametrize("payload,message", [
    ([], "request must be a JSON object"),
    ({"plugins": []}, "request.operation is required"),
    ({"operation": "run", "version": 1}, "request.version must be a string"),
    ({"operation": "run", "plugins": {}}, "request.plugins must be an array"),
    ({"operation": "run", "execution": []}, "request.execution must be an object"),
    ({"operation": "run", "execution": {"stop_on_error": "yes"}}, "stop_on_error must be a boolean"),
])
def test_parse_rejects_bad_request_shape(payload, message):
    with pytest.raises(RequestConfigError, match=message):
        parse_request_config(payload)


@pytest.mark.parametrize("entry,message", [
    ("not-object", r"plugins\[0\] must be an object"),
    ({}, r"plugins\[0\].name is required"),
    ({"name": "x", "required": "yes"}, r"plugins\[0\].required must be a boolean"),
    ({"name": "x", "roles": []}, r"plugins\[0\].roles must be an object"),
    ({"name": "x", "roles": {"run": []}}, r"plugins\[0\].roles.run must be an object"),
    ({"name": "x", "config": []}, r"plugins\[0\].config must be an object"),
])
def test_parse_rejects_bad_plugin_shape(entry, message):
    with pytest.raises(RequestConfigError, match=message):
        parse_request_config({"operation": "run", "plugins": [entry]})


def test_load_request_config_rejects_invalid_json(tmp_path):
    request_file = tmp_path / "request.json"
    request_file.write_text("not json")

    with pytest.raises(RequestConfigError, match="invalid request file"):
        load_request_config(request_file)


def test_validate_required_plugins_reports_install_commands():
    request = parse_request_config({
        "operation": "run",
        "plugins": [{"name": "missing-plugin", "required": True}],
    })

    with pytest.raises(RequestConfigError) as exc:
        validate_required_plugins(request.plugins)

    message = str(exc.value)
    assert "Required plugin not installed: missing-plugin" in message
    assert "tokenade plugin install missing-plugin" in message
    assert "tokenade plugin install missing-plugin --registry <registry-name-or-url>" in message


def test_optional_missing_plugin_is_allowed():
    request = parse_request_config({
        "operation": "run",
        "plugins": [{"name": "missing-plugin", "required": False}],
    })

    validate_required_plugins(request.plugins)


def test_load_request_config_success(tmp_path, monkeypatch):
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"operation": "run", "plugins": []}))
    monkeypatch.setattr("tokenade.core.request_config.validate_required_plugins", lambda plugins: None)

    request = load_request_config(request_file)

    assert request.operation == "run"
