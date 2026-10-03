"""Tests for core.tunnel.connect: TunnelSession, open_tunnel_for_jar, capture.

Blocking sync API runs in an executor thread inside async tests: the relay
and origin live on the test loop, so calling open_tunnel_for_jar directly
would starve them and deadlock.
"""
import asyncio
import functools
import json

import pytest

from tokenade.core.session_runtime.policy import EgressCheckError
from tokenade.core.tunnel.connect import (
    capture_egress_block,
    open_tunnel_for_jar,
    snapshot_values_from_fingerprint,
)
from tokenade.core.tunnel.consumer import ConsumerCircuit  # noqa: F401
from tokenade.core.tunnel.origin import OriginEndpoint
from tokenade.core.tunnel.relay import RelayServer


async def _free_port():
    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()
    return port


def _jar(relay_url, hint=None, ref="ref-1"):
    return {
        "version": "3.1",
        "egress": {
            "mode": "origin-relay",
            "relay": {"transport": "wss-reverse", "rendezvous": relay_url,
                      "remote_ref": ref},
            "origin_hint": hint or {"country": "IN", "asn": "AS1"},
            "policy": {"required": True, "fallback": "deny"},
        },
    }


async def _responder(payload):
    async def _http(reader, writer):
        try:
            await reader.readuntil(b"\r\n\r\n")
            body = json.dumps(payload).encode()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                         b"Content-Length: " + str(len(body)).encode()
                         + b"\r\n\r\n" + body)
            await writer.drain()
        finally:
            writer.close()

    port = await _free_port()
    server = await asyncio.start_server(_http, "127.0.0.1", port)
    return server, f"http://127.0.0.1:{port}/echo"


class _Backend:
    def __init__(self, relay, relay_task, origin, origin_task, responder, echo_url):
        self.relay = relay
        self.relay_task = relay_task
        self.origin = origin
        self.origin_task = origin_task
        self.responder = responder
        self.echo_url = echo_url
        self.relay_url = None

    async def aclose(self):
        await self.origin.stop()
        self.origin_task.cancel()
        try:
            await self.origin_task
        except (asyncio.CancelledError, Exception):
            pass
        if self.responder is not None:
            self.responder.close()
            await self.responder.wait_closed()
        await self.relay.aclose()
        self.relay_task.cancel()
        try:
            await self.relay_task
        except (asyncio.CancelledError, Exception):
            pass


async def live_backend(snapshot_values=None):
    port = await _free_port()
    relay = RelayServer("127.0.0.1", port)
    relay_task = asyncio.ensure_future(relay.start())
    await asyncio.sleep(0.2)
    relay_url = f"ws://127.0.0.1:{port}"
    origin = OriginEndpoint(
        relay_url, "ref-1", consumer_tokens={"tok123"},
        snapshot_values=snapshot_values or {"navigator.platform": "Win32"},
        oracle_allowlist=["navigator.platform"],
    )
    origin_task = asyncio.ensure_future(origin.start())
    await asyncio.sleep(0.2)
    responder, echo_url = await _responder({"ip": "9.9.9.9", "country": "IN", "asn": "AS1"})
    backend = _Backend(relay, relay_task, origin, origin_task, responder, echo_url)
    backend.relay_url = relay_url
    return backend


async def test_open_verified_ok(monkeypatch):
    monkeypatch.setattr(
        "tokenade.core.tunnel.connect.load_consumer_token", lambda ref: "tok123")
    backend = await live_backend()
    try:
        loop = asyncio.get_running_loop()
        state = await loop.run_in_executor(
            None,
            functools.partial(
                open_tunnel_for_jar,
                _jar(backend.relay_url),
                mode="auto",
                echo_url=backend.echo_url,
            ),
        )
        try:
            assert state["local_proxy"]["server"].startswith("http://127.0.0.1:")
            assert state["oracle"]["mode"] == "live"
            assert state["egress_check"]["action"] == "ok"
            session = state["_session"]
            value = await loop.run_in_executor(
                None, functools.partial(session.query, "navigator.platform"))
            assert value == "Win32"
        finally:
            await loop.run_in_executor(None, state["_session"].close)
    finally:
        await backend.aclose()


async def test_open_deny_closes_session(monkeypatch):
    monkeypatch.setattr(
        "tokenade.core.tunnel.connect.load_consumer_token", lambda ref: "tok123")
    backend = await live_backend()
    try:
        loop = asyncio.get_running_loop()
        jar = _jar(backend.relay_url, hint={"country": "XX", "asn": "AS9"})
        with pytest.raises(EgressCheckError):
            await loop.run_in_executor(
                None,
                functools.partial(open_tunnel_for_jar, jar, mode="auto",
                                  echo_url=backend.echo_url),
            )
    finally:
        await backend.aclose()


def test_open_off_returns_none():
    assert open_tunnel_for_jar(_jar("ws://x"), mode="off") is None


def test_open_missing_egress_block_raises():
    with pytest.raises(EgressCheckError):
        open_tunnel_for_jar({"version": "3.0"}, mode="auto")


def test_snapshot_values_mapping():
    fp = {"platform": "Win32", "screen_width": 1920, "user_agent": "",
          "timezone": "Asia/Kolkata", "bogus": 1}
    values = snapshot_values_from_fingerprint(fp)
    assert values["navigator.platform"] == "Win32"
    assert values["screen.width"] == 1920
    assert values["Intl.timeZone"] == "Asia/Kolkata"
    assert "navigator.userAgent" not in values  # empty skipped
    assert "bogus" not in str(values)
    assert snapshot_values_from_fingerprint(None) == {}


def test_capture_egress_block(monkeypatch):
    monkeypatch.setattr(
        "tokenade.core.network.source_context.capture_source_network",
        lambda **kw: {"approx_country": "IN", "asn": "AS1", "ip": "1.2.3.4"},
    )
    captured = capture_egress_block(
        relay_url="ws://relay:8765", remote_ref="r1",
        fingerprint={"platform": "Win32"},
    )
    egress, snap = captured["egress"], captured["oracle_snapshot"]
    assert egress["mode"] == "origin-relay"
    assert egress["relay"]["remote_ref"] == "r1"
    assert egress["origin_hint"]["country"] == "IN"
    assert egress["origin_hint"]["ip_hash"].startswith("sha256:")
    assert "1.2.3.4" not in json.dumps(egress)  # raw IP never stored
    assert snap["values"]["navigator.platform"] == "Win32"
    assert snap["origin_sig"] and snap["origin_pub"]
    assert "1.2.3.4" not in json.dumps(snap)

    from tokenade.core.session_runtime import verify_snapshot

    ok, reason, _ = verify_snapshot(snap)
    assert ok, reason
