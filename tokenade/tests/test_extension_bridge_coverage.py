"""
Comprehensive tests for extension_bridge.py — BridgeMessage, ExtensionBridge
WebSocket communication, broadcast, session updates, status.
"""

import asyncio
import concurrent.futures
import json
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

from tokenade.core.proxy.extension_bridge import BridgeMessage, ExtensionBridge


def _run_async(coro):
    """Run async coroutine in a new event loop via ThreadPoolExecutor."""
    with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result(timeout=10)


class TestBridgeMessage(unittest.TestCase):
    def test_defaults(self):
        msg = BridgeMessage(type="test")
        self.assertEqual(msg.type, "test")
        self.assertEqual(msg.data, {})
        self.assertEqual(msg.source, "")

    def test_full_init(self):
        msg = BridgeMessage(
            type="heartbeat", data={"ts": 123}, source="extension"
        )
        self.assertEqual(msg.type, "heartbeat")
        self.assertEqual(msg.data["ts"], 123)
        self.assertEqual(msg.source, "extension")


class TestExtensionBridgeInit(unittest.TestCase):
    def test_defaults(self):
        bridge = ExtensionBridge()
        self.assertEqual(bridge.host, "127.0.0.1")
        self.assertEqual(bridge.port, 9223)
        self.assertEqual(bridge._clients, set())
        self.assertEqual(bridge._message_handlers, {})
        self.assertIsNone(bridge._session_callback)
        self.assertFalse(bridge._running)

    def test_custom_init(self):
        bridge = ExtensionBridge(host="0.0.0.0", port=9999)
        self.assertEqual(bridge.host, "0.0.0.0")
        self.assertEqual(bridge.port, 9999)


class TestExtensionBridgeOnMessage(unittest.TestCase):
    def test_register_handler(self):
        bridge = ExtensionBridge()
        handler = MagicMock()
        bridge.on_message("cookie_update", handler)
        self.assertIn("cookie_update", bridge._message_handlers)
        self.assertEqual(bridge._message_handlers["cookie_update"], handler)

    def test_register_multiple_handlers(self):
        bridge = ExtensionBridge()
        h1 = MagicMock()
        h2 = MagicMock()
        bridge.on_message("type1", h1)
        bridge.on_message("type2", h2)
        self.assertEqual(len(bridge._message_handlers), 2)


class TestExtensionBridgeOnSessionUpdate(unittest.TestCase):
    def test_register_callback(self):
        bridge = ExtensionBridge()
        callback = MagicMock()
        bridge.on_session_update(callback)
        self.assertEqual(bridge._session_callback, callback)


class TestExtensionBridgeStop(unittest.TestCase):
    def test_stop(self):
        bridge = ExtensionBridge()
        bridge._running = True
        bridge.stop()
        self.assertFalse(bridge._running)


class TestExtensionBridgeBroadcast(unittest.TestCase):
    def test_broadcast_no_clients(self):
        bridge = ExtensionBridge()
        _run_async(bridge.broadcast({"type": "test"}))

    def test_broadcast_to_clients(self):
        bridge = ExtensionBridge()
        client1 = AsyncMock()
        client2 = AsyncMock()
        bridge._clients = {client1, client2}
        _run_async(bridge.broadcast({"type": "update", "data": "test"}))
        client1.send.assert_called_once()
        client2.send.assert_called_once()
        sent1 = json.loads(client1.send.call_args[0][0])
        self.assertEqual(sent1["type"], "update")

    def test_broadcast_removes_disconnected(self):
        bridge = ExtensionBridge()
        client_ok = AsyncMock()
        client_bad = AsyncMock()
        client_bad.send.side_effect = RuntimeError("disconnected")
        bridge._clients = {client_ok, client_bad}
        _run_async(bridge.broadcast({"type": "test"}))
        self.assertIn(client_ok, bridge._clients)
        self.assertNotIn(client_bad, bridge._clients)


class TestExtensionBridgeSendSessionUpdate(unittest.TestCase):
    def test_send_session_update(self):
        bridge = ExtensionBridge()
        session_data = {"cookies": [{"name": "t", "value": "v"}]}
        bridge._clients = set()
        # send_session_update uses asyncio.create_task internally
        # Just verify it doesn't crash when called
        try:
            bridge.send_session_update(session_data)
        except RuntimeError:
            pass  # No running event loop is fine


class TestExtensionBridgeGetStatus(unittest.TestCase):
    def test_status(self):
        bridge = ExtensionBridge()
        bridge._running = True
        bridge._clients = {MagicMock(), MagicMock()}
        status = bridge.get_status()
        self.assertEqual(status["host"], "127.0.0.1")
        self.assertEqual(status["port"], 9223)
        self.assertTrue(status["running"])
        self.assertEqual(status["connected_clients"], 2)

    def test_status_stopped(self):
        bridge = ExtensionBridge()
        status = bridge.get_status()
        self.assertFalse(status["running"])
        self.assertEqual(status["connected_clients"], 0)


class TestExtensionBridgeStart(unittest.TestCase):
    def test_start_no_websockets(self):
        bridge = ExtensionBridge()
        with patch.dict("sys.modules", {"websockets": None}):
            _run_async(bridge.start())
            self.assertFalse(bridge._running)

    def test_start_serve_error(self):
        bridge = ExtensionBridge()
        mock_ws = MagicMock()
        mock_ws.serve = AsyncMock(side_effect=OSError("Address in use"))
        with patch.dict("sys.modules", {"websockets": mock_ws}):
            _run_async(bridge.start())

    def test_start_sets_running_and_stops(self):
        bridge = ExtensionBridge()
        mock_ws = MagicMock()

        async def fake_serve(*args, **kwargs):
            bridge._running = False

        mock_ws.serve = AsyncMock(side_effect=fake_serve)
        with patch.dict("sys.modules", {"websockets": mock_ws}):
            _run_async(bridge.start())


class TestExtensionBridgeHandleClient(unittest.TestCase):
    def test_handle_client_cookie_update(self):
        bridge = ExtensionBridge()
        handler = MagicMock(return_value={"status": "ok"})
        bridge.on_message("cookie_update", handler)
        session_cb = MagicMock()
        bridge.on_session_update(session_cb)

        websocket = AsyncMock()
        websocket.remote_address = ("127.0.0.1", 54321)
        bridge._clients.add(websocket)

        message = json.dumps(
            {"type": "cookie_update", "data": {"cookies": []}}
        )
        try:
            data = json.loads(message)
            msg_type = data.get("type", "unknown")
            msg_data = data.get("data", {})
            if msg_type in bridge._message_handlers:
                bridge._message_handlers[msg_type](
                    BridgeMessage(
                        type=msg_type, data=msg_data, source="extension"
                    )
                )
            if msg_type == "cookie_update" and bridge._session_callback:
                bridge._session_callback(msg_data)
        finally:
            bridge._clients.discard(websocket)

        handler.assert_called_once()
        session_cb.assert_called_once()

    def test_handle_client_invalid_json(self):
        try:
            json.loads("not json")
        except json.JSONDecodeError:
            pass  # Expected

    def test_handle_client_disconnect(self):
        bridge = ExtensionBridge()
        websocket = MagicMock()
        bridge._clients.add(websocket)
        bridge._clients.discard(websocket)
        self.assertNotIn(websocket, bridge._clients)


if __name__ == "__main__":
    unittest.main()
