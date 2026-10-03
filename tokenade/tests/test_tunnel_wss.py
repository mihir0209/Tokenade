"""Loopback E2E: relay + origin + consumer on 127.0.0.1 (no internet).

NOTE: everything is built inside each test's own event loop via the
`live_circuit` helper. Do NOT use async fixtures here: with
function-scoped fixture loops, servers/sockets would bind to a different
loop than the test runs on, which wedges teardown.
"""
import asyncio
import json
from contextlib import asynccontextmanager

import pytest

from tokenade.core.tunnel.consumer import ConsumerCircuit
from tokenade.core.tunnel.errors import AuthError, PairingError, TunnelError
from tokenade.core.tunnel.origin import OriginEndpoint
from tokenade.core.tunnel.pairing import (
    create_pairing,
    load_consumer_token,
    redeem_pairing,
    save_consumer_record,
)
from tokenade.core.tunnel.relay import RelayServer

ALLOW = ["navigator.platform", "screen.width"]


async def _free_port():
    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()
    return port


async def _echo_handler(reader, writer):
    try:
        while True:
            chunk = await reader.read(32768)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    finally:
        writer.close()


@asynccontextmanager
async def live_circuit(
    *,
    consumer_token="tok123",
    origin_tokens=("tok123",),
    snapshot_values=None,
    with_echo_target=False,
    with_echo_responder=False,
):
    """Spin up relay + origin + paired consumer, all on this loop."""
    relay_port = await _free_port()
    relay = RelayServer("127.0.0.1", relay_port)
    relay_task = asyncio.ensure_future(relay.start())
    await asyncio.sleep(0.2)
    relay_url = f"ws://127.0.0.1:{relay_port}"

    origin = OriginEndpoint(
        relay_url, "ref-1", consumer_tokens=set(origin_tokens),
        snapshot_values=snapshot_values or {
            "navigator.platform": "Win32", "screen.width": 1920},
        oracle_allowlist=ALLOW,
    )
    origin_task = asyncio.ensure_future(origin.start())
    await asyncio.sleep(0.2)

    consumer = ConsumerCircuit(relay_url, "ref-1", consumer_token)
    try:
        await consumer.connect()
    except Exception:
        # Setup failed (e.g. AuthError): unwind what we started, then reraise.
        await consumer.close()
        await origin.stop()
        origin_task.cancel()
        try:
            await origin_task
        except (asyncio.CancelledError, Exception):
            pass
        await relay.aclose()
        relay_task.cancel()
        try:
            await relay_task
        except (asyncio.CancelledError, Exception):
            pass
        raise

    extra = {}
    if with_echo_target:
        port = await _free_port()
        extra["echo_server"] = await asyncio.start_server(
            _echo_handler, "127.0.0.1", port)
        extra["echo_port"] = port
    if with_echo_responder:
        payload = json.dumps({"ip": "9.9.9.9", "country": "IN", "asn": "AS24560"})

        async def _http(reader, writer):
            try:
                await reader.readuntil(b"\r\n\r\n")
                body = payload.encode()
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                    b"Content-Length: " + str(len(body)).encode()
                    + b"\r\n\r\n" + body
                )
                await writer.drain()
            finally:
                writer.close()

        port = await _free_port()
        extra["echo_http"] = await asyncio.start_server(_http, "127.0.0.1", port)
        extra["echo_url"] = f"http://127.0.0.1:{port}/echo"

    try:
        yield {"consumer": consumer, "origin": origin, **extra}
    finally:
        await consumer.close()
        await origin.stop()
        origin_task.cancel()
        try:
            await origin_task
        except (asyncio.CancelledError, Exception):
            pass
        for key in ("echo_server", "echo_http"):
            server = extra.get(key)
            if server is not None:
                server.close()
                await server.wait_closed()
        await relay.aclose()
        relay_task.cancel()
        try:
            await relay_task
        except (asyncio.CancelledError, Exception):
            pass


async def test_stream_roundtrip():
    async with live_circuit(with_echo_target=True) as live:
        stream = await live["consumer"].open_stream("127.0.0.1", live["echo_port"])
        await stream.write(b"hello-tunnel")
        assert await stream.read() == b"hello-tunnel"
        await stream.close()


async def test_oracle_query_and_deny():
    async with live_circuit() as live:
        assert await live["consumer"].query("navigator.platform") == "Win32"
        with pytest.raises(TunnelError):
            await live["consumer"].query("canvas.readback")


async def test_egress_echo():
    async with live_circuit(with_echo_responder=True) as live:
        echo = await live["consumer"].egress_echo(live["echo_url"])
        assert echo["country"] == "IN" and echo["asn"] == "AS24560"
        assert echo["ip_hash"].startswith("sha256:")


async def test_local_listener_connect():
    async with live_circuit(with_echo_target=True) as live:
        proxy = await live["consumer"].serve_local_listener()
        port = int(proxy["server"].rsplit(":", 1)[1])
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(
            f"CONNECT 127.0.0.1:{live['echo_port']} HTTP/1.1\r\nHost: x\r\n\r\n".encode()
        )
        await writer.drain()
        head = await reader.readuntil(b"\r\n\r\n")
        assert b"200" in head
        writer.write(b"ping")
        await writer.drain()
        assert await reader.readexactly(4) == b"ping"
        writer.close()
        await writer.wait_closed()


async def test_bad_token_rejected():
    # connect() inside the helper raises AuthError before yield.
    with pytest.raises(AuthError):
        async with live_circuit(consumer_token="evil", origin_tokens=("good",)):
            pass  # pragma: no cover


def test_pairing_single_use(tmp_path):
    store = tmp_path / "pairings.json"
    created = create_pairing("ref-9", "ws://x", "tok9", store=store)
    redeemed = redeem_pairing(created["code"], store=store)
    assert redeemed["consumer_token"] == "tok9"
    with pytest.raises(PairingError):
        redeem_pairing(created["code"], store=store)


def test_consumer_record_roundtrip(tmp_path, monkeypatch):
    store = tmp_path / "consumers.json"
    memory = {}

    class _FakeKeyring:
        @staticmethod
        def set_password(service, user, pw):
            memory[(service, user)] = pw

        @staticmethod
        def get_password(service, user):
            return memory.get((service, user))

    monkeypatch.setitem(__import__("sys").modules, "keyring", _FakeKeyring)
    save_consumer_record("ref-9", "ws://x", "tok9", store=store)
    assert load_consumer_token("ref-9", store=store) == "tok9"
