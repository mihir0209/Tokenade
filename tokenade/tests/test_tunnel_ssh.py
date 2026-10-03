"""Tests for ssh-reverse transport (no SSH server needed).

A stub TCP listener stands in for sshd's `ssh -R` forwarding: it pipes each
inbound connection to the origin egress proxy. That exercises the consumer,
Bearer gate, special hosts, and pipe logic honestly; only the SSH handshake
itself needs a real box (manual runbook in USER_GUIDE).
"""
import asyncio
import functools
import json

import pytest

from tokenade.core.tunnel.errors import AuthError, TunnelError
from tokenade.core.tunnel.ssh_reverse import (
    ECHO_HOST,
    ORACLE_HOST,
    SshTunnelSession,
    TokenGatedEgressProxy,
)

TOKENS = {"tok123"}
SNAPSHOT = {"navigator.platform": "Win32"}
ALLOW = ["navigator.platform"]


async def _free_port():
    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()
    return port


async def _pipe(src, dst):
    try:
        while True:
            chunk = await src.read(32768)
            if not chunk:
                break
            dst.write(chunk)
            await dst.drain()
    except Exception:
        pass


class _Origin:
    """Egress proxy + echo target + echo responder, all on the test loop."""

    def __init__(self, proxy, echo_server, responder, responder_url):
        self.proxy = proxy
        self.echo_server = echo_server
        self.responder = responder
        self.responder_url = responder_url
        self.proxy_port = proxy.bound_port


async def live_origin():
    proxy = TokenGatedEgressProxy(TOKENS, SNAPSHOT, ALLOW)
    await proxy.serve(0)

    async def _echo(reader, writer):
        try:
            while True:
                chunk = await reader.read(32768)
                if not chunk:
                    break
                writer.write(chunk)
                await writer.drain()
        finally:
            writer.close()

    echo_port = await _free_port()
    echo_server = await asyncio.start_server(_echo, "127.0.0.1", echo_port)

    payload = json.dumps({"ip": "9.9.9.9", "country": "IN", "asn": "AS1"})

    async def _http(reader, writer):
        try:
            await reader.readuntil(b"\r\n\r\n")
            body = payload.encode()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                         b"Content-Length: " + str(len(body)).encode()
                         + b"\r\n\r\n" + body)
            await writer.drain()
        finally:
            writer.close()

    responder_port = await _free_port()
    responder = await asyncio.start_server(_http, "127.0.0.1", responder_port)
    origin = _Origin(proxy, echo_server, responder,
                     f"http://127.0.0.1:{responder_port}/echo")
    origin.echo_port = echo_port
    return origin


async def _request(port, head: bytes, body: bytes = b"") -> bytes:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        writer.write(head + body)
        await writer.drain()
        return await reader.read(-1)
    finally:
        writer.close()


def _auth(extra: bytes = b"") -> bytes:
    return b"Proxy-Authorization: Bearer tok123\r\n" + extra


async def test_bearer_gate_rejects_anonymous():
    origin = await live_origin()
    try:
        reply = await _request(origin.proxy_port,
                               b"CONNECT 127.0.0.1:80 HTTP/1.1\r\nHost: x\r\n\r\n")
        assert reply.startswith(b"HTTP/1.1 407")
        reply = await _request(
            origin.proxy_port,
            b"GET http://x/ HTTP/1.1\r\nHost: x\r\n"
            b"Proxy-Authorization: Bearer wrong\r\n\r\n")
        assert reply.startswith(b"HTTP/1.1 407")
    finally:
        await origin.proxy.aclose()
        origin.echo_server.close()
        origin.responder.close()


async def test_connect_tunnel_roundtrip():
    origin = await live_origin()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", origin.proxy_port)
        try:
            writer.write(f"CONNECT 127.0.0.1:{origin.echo_port} HTTP/1.1\r\n"
                         f"Host: x\r\n".encode() + _auth() + b"\r\n")
            await writer.drain()
            head = await reader.readuntil(b"\r\n\r\n")
            assert b"200" in head
            writer.write(b"ping")
            await writer.drain()
            assert await reader.readexactly(4) == b"ping"
        finally:
            writer.close()
    finally:
        await origin.proxy.aclose()
        origin.echo_server.close()
        origin.responder.close()


async def test_absolute_uri_fetch():
    origin = await live_origin()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", origin.proxy_port)
        try:
            head = (f"GET http://127.0.0.1:{origin.echo_port}/p HTTP/1.1\r\n"
                    f"Host: 127.0.0.1\r\n".encode() + _auth() + b"\r\n")
            writer.write(head + b"hello-abs")
            await writer.drain()
            # Echo target returns the forwarded head first, then the body.
            echoed = await reader.readexactly(len(head) + len(b"hello-abs"))
            assert echoed == head + b"hello-abs"
        finally:
            writer.close()
    finally:
        await origin.proxy.aclose()
        origin.echo_server.close()
        origin.responder.close()


async def test_echo_special_host():
    origin = await live_origin()
    try:
        import urllib.parse as up

        target = f"http://{ECHO_HOST}/?url=" + up.quote(origin.responder_url, safe="")
        reply = await _request(
            origin.proxy_port,
            f"GET {target} HTTP/1.1\r\nHost: {ECHO_HOST}\r\n".encode()
            + _auth() + b"\r\n")
        head, _, body = reply.partition(b"\r\n\r\n")
        assert b"200" in head.split(b"\r\n", 1)[0]
        data = json.loads(body.decode())
        assert data["country"] == "IN" and data["asn"] == "AS1"
    finally:
        await origin.proxy.aclose()
        origin.echo_server.close()
        origin.responder.close()


async def test_oracle_special_host():
    origin = await live_origin()
    try:
        reply = await _request(
            origin.proxy_port,
            f"GET http://{ORACLE_HOST}/q?method=navigator.platform HTTP/1.1\r\n"
            f"Host: {ORACLE_HOST}\r\n".encode() + _auth() + b"\r\n")
        assert b"200" in reply.split(b"\r\n", 1)[0]
        assert b"Win32" in reply
        reply = await _request(
            origin.proxy_port,
            f"GET http://{ORACLE_HOST}/q?method=canvas.readback HTTP/1.1\r\n"
            f"Host: {ORACLE_HOST}\r\n".encode() + _auth() + b"\r\n")
        assert b"403" in reply.split(b"\r\n", 1)[0]
    finally:
        await origin.proxy.aclose()
        origin.echo_server.close()
        origin.responder.close()


async def _stub_box(proxy_port):
    """Mimic sshd -R forwarding: pipe inbound TCP to the egress proxy."""
    async def _forward(reader, writer):
        try:
            reader2, writer2 = await asyncio.open_connection("127.0.0.1", proxy_port)
        except Exception:
            writer.close()
            return
        try:
            await asyncio.gather(_pipe(reader, writer2), _pipe(reader2, writer))
        finally:
            try:
                writer2.close()
            except Exception:
                pass
            try:
                writer.close()
            except Exception:
                pass

    port = await _free_port()
    server = await asyncio.start_server(_forward, "127.0.0.1", port)
    return server, port


async def test_consumer_session_via_stub_box():
    origin = await live_origin()
    box, box_port = await _stub_box(origin.proxy_port)
    try:
        loop = asyncio.get_running_loop()
        session = await loop.run_in_executor(
            None,
            functools.partial(
                SshTunnelSession("127.0.0.1", 22, box_port, "tok123").open, 20.0),
        )
        try:
            assert session.local_proxy["server"].startswith("http://127.0.0.1:")
            assert session.oracle["mode"] == "live"
            value = await loop.run_in_executor(
                None, functools.partial(session.query, "navigator.platform"))
            assert value == "Win32"
            with pytest.raises(TunnelError):
                await loop.run_in_executor(
                    None, functools.partial(session.query, "canvas.readback"))
            echo = await session.fetch_echo(origin.responder_url)
            assert echo["country"] == "IN"
        finally:
            await loop.run_in_executor(None, session.close)
    finally:
        box.close()
        await box.wait_closed()
        await origin.proxy.aclose()
        origin.echo_server.close()
        origin.responder.close()


async def test_consumer_wrong_token_rejected():
    origin = await live_origin()
    box, box_port = await _stub_box(origin.proxy_port)
    try:
        loop = asyncio.get_running_loop()
        with pytest.raises(AuthError):
            await loop.run_in_executor(
                None,
                functools.partial(
                    SshTunnelSession("127.0.0.1", 22, box_port, "evil").open, 20.0),
            )
    finally:
        box.close()
        await box.wait_closed()
        await origin.proxy.aclose()
        origin.echo_server.close()
        origin.responder.close()


def test_open_dispatch_ssh_transport(monkeypatch):
    import tokenade.core.tunnel.connect as connect_mod
    from tokenade.core.session_runtime.policy import EgressCheckError

    calls = {}

    class _StubSession:
        local_proxy = {"server": "http://127.0.0.1:1"}
        echo = {}

        @property
        def oracle(self):
            return {"mode": "live"}

    def fake_open(relay, ref, token, echo_url, timeout):
        calls.update(relay=relay, ref=ref, token=token)
        return _StubSession()

    monkeypatch.setattr(connect_mod, "_open_ssh_session", fake_open)
    monkeypatch.setattr(connect_mod, "load_consumer_token", lambda ref: "tok")
    jar = {
        "version": "3.1",
        "egress": {
            "mode": "origin-relay",
            "relay": {"transport": "ssh-reverse", "rendezvous": "ssh://box:22",
                      "remote_ref": "r1", "ssh_host": "box",
                      "ssh_remote_port": 18080},
            "origin_hint": {}, "policy": {"fallback": "deny"},
        },
    }
    state = connect_mod.open_tunnel_for_jar(jar, mode="auto")
    assert state["local_proxy"]["server"] == "http://127.0.0.1:1"
    assert calls["ref"] == "r1"

    bad = {"version": "3.1", "egress": {"mode": "x",
           "relay": {"transport": "teleport", "rendezvous": "y", "remote_ref": "r"},
           "policy": {}}}
    with pytest.raises(EgressCheckError):
        connect_mod.open_tunnel_for_jar(bad, mode="auto")

    missing = {"version": "3.1", "egress": {"mode": "x",
               "relay": {"transport": "ssh-reverse", "remote_ref": "r"},
               "policy": {}}}
    with pytest.raises(EgressCheckError):
        connect_mod.open_tunnel_for_jar(missing, mode="auto")
