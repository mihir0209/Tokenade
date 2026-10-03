"""Tests for per-site split routing (tunnel listed domains, direct rest).

Listener tests are self-contained on one loop (see test_tunnel_wss header).
"""
import asyncio

import pytest

from tokenade.core.session_runtime import (
    EgressCheckError,
    RuntimePlanBuilder,
    derive_tunnel_domains,
    host_in_domains,
    normalize_domain,
    resolve_split,
)
from tokenade.tests.test_tunnel_wss import live_circuit as _proven_circuit


def test_normalize_domain():
    assert normalize_domain("Example.COM.") == "example.com"
    assert normalize_domain("example.com:443") == "example.com"
    assert normalize_domain("  SUB.Example.com ") == "sub.example.com"


def test_host_in_domains():
    assert host_in_domains("a.example.com", ["example.com"])
    assert host_in_domains("example.com", ["example.com"])
    assert host_in_domains("EXAMPLE.com", ["example.com"])
    assert not host_in_domains("notexample.com", ["example.com"])
    assert not host_in_domains("example.com.evil.com", ["example.com"])
    assert not host_in_domains("", ["example.com"])
    assert not host_in_domains("example.com", [])


def test_derive_tunnel_domains():
    package = {
        "site_name": "example",
        "cookies": [{"name": "a", "value": "b", "domain": ".example.com"},
                    {"name": "c", "value": "d", "domain": ".cdn.example.com"}],
    }
    assert derive_tunnel_domains(package) == ["example.com", "cdn.example.com"]


def test_resolve_split():
    assert resolve_split({}, None)["enabled"] is False
    assert resolve_split({}, "off")["enabled"] is False
    package = {"site_name": "x",
               "cookies": [{"name": "a", "value": "b", "domain": ".example.com"}]}
    auto = resolve_split(package, "auto")
    assert auto == {"enabled": True, "domains": ["example.com"], "mode": "auto"}
    manual = resolve_split(package, "Example.com, CDN.Example.com")
    assert manual == {"enabled": True,
                      "domains": ["example.com", "cdn.example.com"], "mode": "manual"}


def test_plan_split_report_and_empty_refusal():
    jar = {"version": "3.1", "site_name": "x",
           "cookies": [{"name": "a", "value": "b", "domain": ".example.com"}]}
    plan = RuntimePlanBuilder().build(jar, cli_overrides={"tunnel_split": "auto"})
    assert plan.split == {"enabled": True, "domains": ["example.com"], "mode": "auto"}
    assert plan.report["split"]["enabled"] is True
    with pytest.raises(EgressCheckError):
        RuntimePlanBuilder().build({}, cli_overrides={"tunnel_split": "auto"})


def test_open_tunnel_split_empty_refuses_fast(monkeypatch):
    import tokenade.core.tunnel.connect as connect_mod

    jar = {"version": "3.1", "egress": {
        "mode": "origin-relay",
        "relay": {"transport": "wss-reverse", "rendezvous": "ws://x",
                  "remote_ref": "r"},
        "origin_hint": {}, "policy": {}}}
    with pytest.raises(EgressCheckError):
        connect_mod.open_tunnel_for_jar(jar, mode="auto", tunnel_split="auto")


async def _free_port():
    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()
    return port


async def _echo_server():
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

    port = await _free_port()
    server = await asyncio.start_server(_echo, "127.0.0.1", port)
    return server, port


async def _split_consumer(live, split):
    """Attach a split config to the proven helper's consumer (same loop)."""
    live["consumer"].split = dict(split)
    live["consumer"].split_stats = {"tunneled": 0, "direct": 0}
    return live["consumer"]


async def _connect_via_listener(consumer, host, port, payload: bytes) -> bytes:
    proxy = await consumer.serve_local_listener()
    lport = int(proxy["server"].rsplit(":", 1)[1])
    reader, writer = await asyncio.open_connection("127.0.0.1", lport)
    try:
        writer.write(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
        await writer.drain()
        head = await reader.readuntil(b"\r\n\r\n")
        assert b"200" in head
        writer.write(payload)
        await writer.drain()
        return await reader.readexactly(len(payload))
    finally:
        writer.close()


async def test_wss_split_tunneled_path():
    echo, echo_port = await _echo_server()
    try:
        async with _proven_circuit() as live:
            consumer = await _split_consumer(
                live, {"enabled": True, "domains": ["127.0.0.1"], "mode": "manual"})
            assert await _connect_via_listener(
                consumer, "127.0.0.1", echo_port, b"split-tun") == b"split-tun"
            assert consumer.split_stats == {"tunneled": 1, "direct": 0}
    finally:
        echo.close()
        await echo.wait_closed()


async def test_wss_split_direct_path():
    echo, echo_port = await _echo_server()
    try:
        async with _proven_circuit() as live:
            consumer = await _split_consumer(
                live, {"enabled": True, "domains": ["tunneled.invalid"],
                       "mode": "manual"})
            # 127.0.0.1 not listed → direct dial from this machine.
            assert await _connect_via_listener(
                consumer, "127.0.0.1", echo_port, b"split-dir") == b"split-dir"
            assert consumer.split_stats == {"tunneled": 0, "direct": 1}
    finally:
        echo.close()
        await echo.wait_closed()


async def test_wss_no_split_all_tunneled():
    echo, echo_port = await _echo_server()
    try:
        async with _proven_circuit() as live:
            consumer = live["consumer"]
            assert await _connect_via_listener(
                consumer, "127.0.0.1", echo_port, b"all-tun") == b"all-tun"
            assert consumer.split_stats == {"tunneled": 1, "direct": 0}
    finally:
        echo.close()
        await echo.wait_closed()
