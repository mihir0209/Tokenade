"""Tests for proxy provider plugin normalization and redaction."""

import pytest

from tokenade.core.proxy.provider import ProxyProviderError, ProxyProviderResolver, normalize_proxy_result
from tokenade.core.request_config import parse_request_config


class Loaded:
    def __init__(self, instance):
        self.instance = instance


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
    def __init__(self, provider=None):
        self.provider = provider
        self.unloaded = []

    def load_by_name(self, name):
        if self.provider is None:
            return None
        return Loaded(self.provider)

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


def test_normalize_proxy_result_requires_server():
    with pytest.raises(ProxyProviderError, match="result.server is required"):
        normalize_proxy_result({"username": "x"})
