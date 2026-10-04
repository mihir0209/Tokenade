"""Tests for scripts/tunnel_preflight.py check functions (offline)."""
import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "tunnel_preflight",
    str(Path(__file__).resolve().parents[2] / "scripts" / "tunnel_preflight.py"),
)
_preflight = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_preflight)


def _jar_dict(**kw):
    from tokenade.core.importer.session_packager import SessionPackager

    base = SessionPackager().package(
        cookies=[{"name": "a", "value": "b", "domain": ".example.com"}])
    base.update(kw)
    return base


def _write(tmp_path, package):
    path = tmp_path / "p.tokenade"
    path.write_text(json.dumps(package))
    return str(path)


def test_missing_file():
    package, checks = _preflight.check_jar("/nonexistent/x.tokenade")
    assert package == {}
    assert checks[0][0] == "FAIL"


def test_no_egress_block(tmp_path):
    _, checks = _preflight.check_jar(_write(tmp_path, _jar_dict()))
    assert any(status == "FAIL" and "egress" in msg for status, msg in checks)


def test_wss_descriptor_passes(tmp_path):
    package = _jar_dict(egress={
        "mode": "origin-relay",
        "relay": {"transport": "wss-reverse", "rendezvous": "ws://h:1",
                  "remote_ref": "r"},
        "origin_hint": {}, "policy": {}})
    _, checks = _preflight.check_jar(_write(tmp_path, package))
    assert ("PASS", "egress block: wss-reverse") in checks


def test_snapshot_verified(tmp_path):
    from tokenade.core.session_runtime import generate_origin_keypair, sign_snapshot

    priv, _ = generate_origin_keypair()
    package = _jar_dict(
        egress={"mode": "origin-relay",
                "relay": {"transport": "wss-reverse", "rendezvous": "ws://h:1",
                          "remote_ref": "r"},
                "origin_hint": {}, "policy": {}},
        oracle_snapshot=sign_snapshot({"a": 1}, priv, ttl_s=3600))
    _, checks = _preflight.check_jar(_write(tmp_path, package))
    assert any(status == "PASS" and "oracle snapshot" in msg
               for status, msg in checks)


def test_pairing_present_and_missing(tmp_path, monkeypatch):
    memory = {("tokenade-tunnel", "r"): "tok"}

    class _FakeKeyring:
        @staticmethod
        def set_password(s, u, p):
            memory[(s, u)] = p

        @staticmethod
        def get_password(s, u):
            return memory.get((s, u))

    monkeypatch.setitem(__import__("sys").modules, "keyring", _FakeKeyring)
    package = {"egress": {"relay": {"remote_ref": "r"}}}
    assert _preflight.check_pairing(package)[0][0] == "PASS"
    assert _preflight.check_pairing(
        {"egress": {"relay": {"remote_ref": "nope"}}})[0][0] == "FAIL"
    assert _preflight.check_pairing({})[0][0] == "FAIL"


async def _closed_port():
    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()
    return port


def test_reachability_open_and_closed():
    async def _run():
        server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
        open_port = server.sockets[0].getsockname()[1]
        try:
            package = {"egress": {"relay": {
                "transport": "wss-reverse",
                "rendezvous": f"ws://127.0.0.1:{open_port}", "remote_ref": "r"}}}
            assert _preflight.check_reachability(package)[0][0] == "PASS"
        finally:
            server.close()
            await server.wait_closed()
        closed = await _closed_port()
        package = {"egress": {"relay": {
            "transport": "ssh-reverse", "ssh_host": "127.0.0.1",
            "ssh_port": closed, "remote_ref": "r"}}}
        assert _preflight.check_reachability(package)[0][0] == "FAIL"

    asyncio.run(_run())


def test_main_exit_codes(tmp_path):
    assert _preflight.main([str(tmp_path / "missing.tokenade")]) == 1
    assert _preflight.main([_write(tmp_path, _jar_dict())]) == 1
