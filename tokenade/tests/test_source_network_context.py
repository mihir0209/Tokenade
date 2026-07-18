"""Tests for consent-gated source network stamping."""

import json
from io import BytesIO

import pytest

from tokenade.core.network.source_context import SourceNetworkError, capture_source_network


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_capture_source_network_omits_raw_ip_by_default(monkeypatch):
    def fake_urlopen(url, timeout):
        assert url == "https://ipapi.co/json/"
        assert timeout == 5
        return FakeResponse({
            "ip": "203.0.113.10",
            "country_code": "US",
            "region": "CA",
            "city": "San Francisco",
            "timezone": "America/Los_Angeles",
            "asn": "AS123",
            "asn_type": "residential",
        })

    monkeypatch.setattr("tokenade.core.network.source_context.urlopen", fake_urlopen)

    stamp = capture_source_network()

    assert stamp["provider"] == "tokenade-default-ip-lookup"
    assert stamp["approx_country"] == "US"
    assert stamp["approx_region"] == "CA"
    assert stamp["approx_city"] == "San Francisco"
    assert stamp["raw_ip_stored"] is False
    assert "ip" not in stamp


def test_capture_source_network_includes_raw_ip_only_when_requested(monkeypatch):
    monkeypatch.setattr(
        "tokenade.core.network.source_context.urlopen",
        lambda url, timeout: FakeResponse({"ip": "203.0.113.10", "country_code": "US"}),
    )

    stamp = capture_source_network(include_source_ip=True)

    assert stamp["raw_ip_stored"] is True
    assert stamp["ip"] == "203.0.113.10"


def test_capture_source_network_raises_on_lookup_failure(monkeypatch):
    def fail(url, timeout):
        raise OSError("offline")

    monkeypatch.setattr("tokenade.core.network.source_context.urlopen", fail)

    with pytest.raises(SourceNetworkError, match="source network lookup failed"):
        capture_source_network()
