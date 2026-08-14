"""Tests for proxy provider plugin normalization and redaction."""

import json

import pytest

from tokenade.core.proxy.provider import ProxyProviderError, ProxyProviderResolver, normalize_proxy_result
from tokenade.core.integration.plugin_loader import PluginState
from tokenade.core.request_config import parse_request_config


class Loaded:
    def __init__(self, instance):
        self.instance = instance
        self.state = PluginState.ACTIVE


class FakeProvider:
    def __init__(self):
        self.calls = []

    def resolve_proxy(self, role_config, config, session_metadata, source_network):
        self.calls.append({
            "role_config": role_config,
            "config": config,
            "session_metadata": session_metadata,
            "source_network": source_network,
        })
        return {
            "server": "http://proxy.example:8080",
            "username": "user123",
            "password": "secret-password",
            "metadata": {"country": source_network.get("approx_country")},
        }


class FakeLoader:
    def __init__(self, provider=None, state=None):
        self.provider = provider
        self.state = state
        self.unloaded = []

    def load_by_name(self, name):
        if self.provider is None:
            return None
        loaded = Loaded(self.provider)
        if self.state is not None:
            loaded.state = self.state
        return loaded

    def unload(self, name):
        self.unloaded.append(name)


def _plugin_request():
    request = parse_request_config({
        "operation": "gateway",
        "plugins": [{
            "name": "brightdata",
            "roles": {"proxy_provider": {"mode": "sticky", "match_source_location": True}},
            "config": {"zone": "residential"},
        }],
    })
    return request.plugins[0]


def test_proxy_provider_receives_source_network_metadata_and_redacts_output():
    provider = FakeProvider()
    loader = FakeLoader(provider)
    resolver = ProxyProviderResolver(loader)

    proxy = resolver.resolve(
        _plugin_request(),
        session_metadata={"sites": ["github"]},
        source_network={"approx_country": "US"},
    )

    assert provider.calls[0]["role_config"]["match_source_location"] is True
    assert provider.calls[0]["config"] == {"zone": "residential"}
    assert provider.calls[0]["source_network"] == {"approx_country": "US"}
    assert proxy.to_dict()["username"] == "us***"
    assert proxy.to_dict()["password"] == "***"
    assert "secret-password" not in str(proxy.to_dict())
    assert proxy.to_dict(show_secrets=True)["password"] == "secret-password"
    assert loader.unloaded == ["brightdata"]


def test_missing_required_provider_fails_closed():
    resolver = ProxyProviderResolver(FakeLoader())

    with pytest.raises(ProxyProviderError, match="Required plugin not installed: brightdata"):
        resolver.resolve(_plugin_request())


def test_inactive_provider_fails_closed():
    resolver = ProxyProviderResolver(FakeLoader(FakeProvider(), state=PluginState.LOADED))

    with pytest.raises(ProxyProviderError, match="not active"):
        resolver.resolve(_plugin_request())


def test_normalize_proxy_result_requires_server():
    with pytest.raises(ProxyProviderError, match="result.server is required"):
        normalize_proxy_result({"username": "x"})


def test_proxy_resolve_cli_emits_redacted_provider_result(monkeypatch, tmp_path, capsys):
    from tokenade.cli import _build_parser
    from tokenade.cli.proxy import cmd_proxy

    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({
        "operation": "gateway",
        "source_network": {"approx_country": "US"},
        "plugins": [{
            "name": "brightdata",
            "roles": {"proxy_provider": {"mode": "sticky"}},
            "config": {"zone": "residential"},
        }],
    }))
    provider = FakeProvider()
    monkeypatch.setattr("tokenade.core.proxy.provider.PluginLoader", lambda: FakeLoader(provider))
    monkeypatch.setattr("tokenade.core.request_config.validate_required_plugins", lambda plugins: None)

    args = _build_parser().parse_args(["proxy", "resolve", "--request", str(request_file)])
    cmd_proxy(args)

    output = json.loads(capsys.readouterr().out)
    assert output["success"] is True
    assert output["operation"] == "proxy.resolve"
    assert output["results"][0]["proxy"]["password"] == "***"
    assert "secret-password" not in json.dumps(output)


def test_proxy_parser_keeps_legacy_hidden_but_callable():
    from tokenade.cli import _build_parser

    parser = _build_parser()
    help_text = parser.format_help()
    proxy_help = parser.parse_args(["proxy", "resolve", "--request", "request.json"])
    legacy_args = parser.parse_args(["proxy", "legacy", "--session", "s.tokenade"])

    assert "proxy" in help_text
    assert "fingerprint-matched proxy" not in help_text.lower()
    assert proxy_help.proxy_action == "resolve"
    assert legacy_args.proxy_action == "legacy"
