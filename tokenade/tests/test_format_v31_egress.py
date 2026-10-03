"""Tests for .tokenade v3.1 egress + oracle_snapshot blocks."""
import pytest

from tokenade.core.importer.session_packager import SessionPackager


def _cookies():
    return [{"name": "sid", "value": "abc", "domain": ".example.com"}]


def test_package_embeds_egress_block():
    egress = {
        "mode": "origin-relay",
        "relay": {"transport": "wss-reverse", "remote_ref": "r1"},
        "origin_hint": {"country": "IN", "asn": "AS1"},
        "policy": {"required": True, "fallback": "deny"},
    }
    pkg = SessionPackager().package(cookies=_cookies(), egress=egress)
    assert pkg["version"] == "3.1"
    assert pkg["egress"] == egress
    assert pkg["metadata"]["egress_mode"] == "origin-relay"


def test_package_embeds_oracle_snapshot():
    snap = {"values": {"a": 1}, "collected_at": "x",
            "ttl_s": 60, "origin_pub": "p", "origin_sig": "s"}
    pkg = SessionPackager().package(cookies=_cookies(), oracle_snapshot=snap)
    assert pkg["oracle_snapshot"] == snap


def test_package_defaults_are_none():
    pkg = SessionPackager().package(cookies=_cookies())
    assert pkg["egress"] is None and pkg["oracle_snapshot"] is None


def test_package_rejects_non_dict_blocks():
    with pytest.raises(ValueError):
        SessionPackager().package(cookies=_cookies(), egress="nope")
    with pytest.raises(ValueError):
        SessionPackager().package(cookies=_cookies(), oracle_snapshot=["nope"])


def test_legacy_jar_normalizes_v31_blocks(tmp_path):
    legacy = {
        "version": "3.0", "site_name": "example", "auth_status": "unknown",
        "cookies": _cookies(), "tokens": [],
    }
    path = tmp_path / "legacy.tokenade"
    path.write_text(__import__("json").dumps(legacy))
    loaded = SessionPackager().load(str(path))
    assert loaded["version"] == "3.0"  # input version preserved
    assert loaded["egress"] is None and loaded["oracle_snapshot"] is None
