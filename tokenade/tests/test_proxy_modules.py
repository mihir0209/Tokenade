"""Tests for proxy modules: forward_proxy, extension_bridge, cdp_proxy."""

import asyncio
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from argparse import Namespace

from tokenade.core.proxy.cdp_proxy import (
    CDPProxyConfig, _is_safe_url, _strip_duplicate_headers,
    _LenientProtocol, _LenientServerFactory, create_cdp_proxy_from_file,
)
from tokenade.core.proxy.extension_bridge import BridgeMessage, ExtensionBridge
from tokenade.core.proxy.forward_proxy import ForwardProxy


class TestCDPProxyConfig:
    def test_defaults(self):
        c = CDPProxyConfig()
        assert c.port == 9222
        assert c.host == "127.0.0.1"
        assert c.headless is True
        assert c.timeout == 30
        assert c.use_fingerprint is False

    def test_custom(self):
        c = CDPProxyConfig(port=8080, host="0.0.0.0", headless=False, timeout=60)
        assert c.port == 8080
        assert c.host == "0.0.0.0"
        assert c.headless is False
        assert c.timeout == 60


class TestIsSafeUrl:
    def test_safe_urls(self):
        assert _is_safe_url("https://google.com")
        assert _is_safe_url("https://example.com/path?q=1")

    def test_unsafe_urls(self):
        assert not _is_safe_url("http://localhost:8080")
        assert not _is_safe_url("http://127.0.0.1")
        assert not _is_safe_url("http://192.168.1.1")
        assert not _is_safe_url("http://10.0.0.1")
        assert not _is_safe_url("http://172.16.0.1")
        assert not _is_safe_url("http://169.254.0.1")
        assert not _is_safe_url("http://[::1]")

    def test_edge_cases(self):
        assert not _is_safe_url("")
        assert not _is_safe_url("not-a-url")
        assert not _is_safe_url("http://0.0.0.0")


class TestStripDuplicateHeaders:
    def test_no_duplicates(self):
        raw = b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
        result = _strip_duplicate_headers(raw)
        assert b"Host: example.com" in result

    def test_with_duplicates(self):
        raw = b"GET / HTTP/1.1\r\nHost: example.com\r\nHost: dup.com\r\n\r\n"
        result = _strip_duplicate_headers(raw)
        lines = result.split(b"\r\n")
        host_lines = [l for l in lines if l.lower().startswith(b"host:")]
        assert len(host_lines) == 1

    def test_corrupt_data(self):
        result = _strip_duplicate_headers(b"no headers here")
        assert result == b"no headers here"


class TestLenientProtocol:
    def test_strips_duplicates(self):
        inner = MagicMock()
        proto = _LenientProtocol(inner)

        raw = b"GET / HTTP/1.1\r\nHost: a.com\r\nHost: b.com\r\n\r\n"
        proto.data_received(raw)
        inner.data_received.assert_called_once()
        data = inner.data_received.call_args[0][0]
        assert data.count(b"Host:") == 1

    def test_connection_made(self):
        inner = MagicMock()
        proto = _LenientProtocol(inner)
        transport = MagicMock()
        proto.connection_made(transport)
        inner.connection_made.assert_called_once_with(transport)

    def test_connection_lost(self):
        inner = MagicMock()
        proto = _LenientProtocol(inner)
        proto.connection_lost(None)
        inner.connection_lost.assert_called_once_with(None)


class TestLenientServerFactory:
    def test_creates_wrapped_protocol(self):
        inner_factory = MagicMock()
        inner_factory.return_value = MagicMock()
        factory = _LenientServerFactory(inner_factory)
        proto = factory()
        assert isinstance(proto, _LenientProtocol)


class TestForwardProxy:
    def test_init(self):
        session = {"cookies": [{"name": "SID", "value": "abc", "domain": ".google.com"}]}
        proxy = ForwardProxy(session, port=9223, host="127.0.0.1")
        assert proxy.port == 9223
        assert proxy.host == "127.0.0.1"
        assert proxy.session == session
        assert proxy.stats["requests"] == 0

    def test_stats_initialized(self):
        proxy = ForwardProxy({})
        assert proxy.stats == {"requests": 0, "bytes_sent": 0, "bytes_received": 0, "errors": 0}


class TestBridgeMessage:
    def test_creation(self):
        msg = BridgeMessage(type="cookie_update", data={"cookies": []}, source="extension")
        assert msg.type == "cookie_update"
        assert msg.source == "extension"
        assert msg.data == {"cookies": []}

    def test_defaults(self):
        msg = BridgeMessage(type="heartbeat")
        assert msg.data == {}
        assert msg.source == ""


class TestExtensionBridge:
    def test_init(self):
        bridge = ExtensionBridge(host="127.0.0.1", port=9223)
        assert bridge.host == "127.0.0.1"
        assert bridge.port == 9223
        assert bridge._running is False
        assert len(bridge._clients) == 0

    def test_on_message(self):
        bridge = ExtensionBridge()
        handler = MagicMock()
        bridge.on_message("cookie_update", handler)
        assert bridge._message_handlers["cookie_update"] is handler

    def test_on_session_update(self):
        bridge = ExtensionBridge()
        callback = MagicMock()
        bridge.on_session_update(callback)
        assert bridge._session_callback is callback

    def test_get_status(self):
        bridge = ExtensionBridge(host="0.0.0.0", port=8080)
        status = bridge.get_status()
        assert status["host"] == "0.0.0.0"
        assert status["port"] == 8080
        assert status["running"] is False
        assert status["connected_clients"] == 0

    def test_stop(self):
        bridge = ExtensionBridge()
        bridge._running = True
        bridge.stop()
        assert bridge._running is False

    @pytest.mark.asyncio
    async def test_broadcast_empty(self):
        bridge = ExtensionBridge()
        await bridge.broadcast({"type": "test"})
        assert len(bridge._clients) == 0

    @pytest.mark.asyncio
    async def test_broadcast_to_clients(self):
        bridge = ExtensionBridge()
        mock_client = AsyncMock()
        mock_client.send = AsyncMock()
        bridge._clients.add(mock_client)

        await bridge.broadcast({"type": "test", "data": "hello"})
        mock_client.send.assert_called_once_with(json.dumps({"type": "test", "data": "hello"}))

    @pytest.mark.asyncio
    async def test_broadcast_handles_disconnected(self):
        bridge = ExtensionBridge()
        bad_client = AsyncMock()
        bad_client.send = AsyncMock(side_effect=Exception("disconnected"))
        bridge._clients.add(bad_client)

        await bridge.broadcast({"type": "test"})
        assert bad_client not in bridge._clients

    def test_send_session_update_creates_task(self):
        bridge = ExtensionBridge()
        with patch("asyncio.create_task") as mock_task:
            bridge.send_session_update({"cookies": []})
            mock_task.assert_called_once()
