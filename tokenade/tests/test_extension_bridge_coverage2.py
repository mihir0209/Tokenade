"""
Comprehensive tests for extension_bridge.py — covers start(), handle_client
WebSocket communication, message handling, error paths, and client lifecycle.
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


class MockWebSocket:
    """Mock websocket for testing handle_client."""

    def __init__(self, messages=None, raise_on_iter=None):
        self._messages = messages or []
        self._raise_on_iter = raise_on_iter
        self.remote_address = ("127.0.0.1", 12345)
        self.sent = []

    async def __aiter__(self):
        for msg in self._messages:
            yield msg
        if self._raise_on_iter is not None:
            raise self._raise_on_iter

    async def send(self, msg):
        self.sent.append(msg)

    def __await__(self):
        yield


async def cancel_after_sleep(*args, **kwargs):
    """Raise CancelledError to exit the while loop in start()."""
    raise asyncio.CancelledError()


class TestStartWithWebsockets(unittest.TestCase):
    """Test start() method with mocked websockets module."""

    def test_start_sets_running_and_serve_called(self):
        """start() imports websockets, sets _running, and calls serve."""
        bridge = ExtensionBridge()
        mock_ws = MagicMock()

        async def fake_serve(handler_func, host, port):
            bridge._running = False

        mock_ws.serve = AsyncMock(side_effect=fake_serve)

        with patch.dict("sys.modules", {"websockets": mock_ws}):
            _run_async(bridge.start())

        mock_ws.serve.assert_called_once()
        self.assertFalse(bridge._running)

    def test_start_loop_executes_until_sleep_cancelled(self):
        """The while loop runs asyncio.sleep(1) until stopped."""
        bridge = ExtensionBridge()
        mock_ws = MagicMock()
        mock_ws.serve = AsyncMock()

        with patch.dict("sys.modules", {"websockets": mock_ws}):
            with patch("asyncio.sleep", side_effect=cancel_after_sleep):
                with self.assertRaises(asyncio.CancelledError):
                    _run_async(bridge.start())

        self.assertTrue(bridge._running)


class TestHandleClientViaStart(unittest.TestCase):
    """Test handle_client by capturing it through the mocked serve call."""

    def _start_with_client(self, bridge, ws):
        """Start bridge and run handle_client with the given websocket."""

        async def fake_serve(handler_func, host, port):
            await handler_func(ws)
            bridge._running = False

        mock_ws = MagicMock()
        mock_ws.serve = AsyncMock(side_effect=fake_serve)

        with patch.dict("sys.modules", {"websockets": mock_ws}):
            _run_async(bridge.start())

    def test_valid_message_calls_handler(self):
        """Valid JSON message triggers the registered handler."""
        bridge = ExtensionBridge()
        handler = MagicMock(return_value=None)
        bridge.on_message("heartbeat", handler)

        ws = MockWebSocket([
            json.dumps({"type": "heartbeat", "data": {"ts": 123}})
        ])

        self._start_with_client(bridge, ws)
        handler.assert_called_once()
        msg_arg = handler.call_args[0][0]
        self.assertIsInstance(msg_arg, BridgeMessage)
        self.assertEqual(msg_arg.type, "heartbeat")
        self.assertEqual(msg_arg.data["ts"], 123)
        self.assertEqual(msg_arg.source, "extension")

    def test_handler_return_value_sent_to_client(self):
        """Handler return value is sent back to the websocket."""
        bridge = ExtensionBridge()
        bridge.on_message("session_request", MagicMock(return_value={"status": "ok"}))

        ws = MockWebSocket([
            json.dumps({"type": "session_request", "data": {}})
        ])

        self._start_with_client(bridge, ws)
        self.assertEqual(len(ws.sent), 1)
        sent = json.loads(ws.sent[0])
        self.assertEqual(sent["status"], "ok")

    def test_handler_return_none_no_send(self):
        """None return value does not trigger websocket.send."""
        bridge = ExtensionBridge()
        bridge.on_message("heartbeat", MagicMock(return_value=None))

        ws = MockWebSocket([
            json.dumps({"type": "heartbeat", "data": {}})
        ])

        self._start_with_client(bridge, ws)
        self.assertEqual(len(ws.sent), 0)

    def test_cookie_update_calls_session_callback(self):
        """cookie_update message triggers the registered session_callback."""
        bridge = ExtensionBridge()
        session_cb = MagicMock()
        bridge.on_session_update(session_cb)

        ws = MockWebSocket([
            json.dumps({"type": "cookie_update", "data": {"cookies": [{"name": "t"}]}})
        ])

        self._start_with_client(bridge, ws)
        session_cb.assert_called_once_with({"cookies": [{"name": "t"}]})

    def test_cookie_update_without_session_callback(self):
        """cookie_update without session_callback does not crash."""
        bridge = ExtensionBridge()

        ws = MockWebSocket([
            json.dumps({"type": "cookie_update", "data": {"value": "v"}})
        ])

        self._start_with_client(bridge, ws)
        self.assertNotIn(ws, bridge._clients)

    def test_cookie_update_with_handler_and_callback(self):
        """cookie_update triggers both handler and session_callback."""
        bridge = ExtensionBridge()
        handler = MagicMock(return_value={"ack": True})
        bridge.on_message("cookie_update", handler)
        session_cb = MagicMock()
        bridge.on_session_update(session_cb)

        ws = MockWebSocket([
            json.dumps({"type": "cookie_update", "data": {"cookies": []}})
        ])

        self._start_with_client(bridge, ws)
        handler.assert_called_once()
        session_cb.assert_called_once()

    def test_invalid_json_does_not_crash(self):
        """Invalid JSON is caught by JSONDecodeError handler."""
        bridge = ExtensionBridge()
        handler = MagicMock()
        bridge.on_message("any_type", handler)

        ws = MockWebSocket(["not json at all"])

        self._start_with_client(bridge, ws)
        handler.assert_not_called()
        self.assertNotIn(ws, bridge._clients)

    def test_unknown_message_type_no_handler(self):
        """Message with no registered handler does not crash."""
        bridge = ExtensionBridge()

        ws = MockWebSocket([
            json.dumps({"type": "unknown_type", "data": {}})
        ])

        self._start_with_client(bridge, ws)
        self.assertNotIn(ws, bridge._clients)

    def test_client_removed_on_disconnect_exception(self):
        """Client is removed from _clients when an exception occurs."""
        bridge = ExtensionBridge()

        ws = MockWebSocket(raise_on_iter=RuntimeError("connection lost"))

        self._start_with_client(bridge, ws)
        self.assertNotIn(ws, bridge._clients)

    def test_client_added_then_removed(self):
        """Client lifecycle: added on connect, removed in finally block."""
        bridge = ExtensionBridge()

        ws = MockWebSocket([
            json.dumps({"type": "heartbeat", "data": {}})
        ])

        self.assertNotIn(ws, bridge._clients)
        self._start_with_client(bridge, ws)
        self.assertNotIn(ws, bridge._clients)

    def test_multiple_messages_processed(self):
        """Multiple messages from same client are all processed."""
        bridge = ExtensionBridge()
        handler = MagicMock(return_value=None)
        bridge.on_message("heartbeat", handler)

        ws = MockWebSocket([
            json.dumps({"type": "heartbeat", "data": {"i": 1}}),
            json.dumps({"type": "heartbeat", "data": {"i": 2}}),
            json.dumps({"type": "heartbeat", "data": {"i": 3}}),
        ])

        self._start_with_client(bridge, ws)
        self.assertEqual(handler.call_count, 3)

    def test_handler_exception_disconnects_client(self):
        """Handler raising exception causes client disconnect."""
        bridge = ExtensionBridge()
        bridge.on_message("boom", MagicMock(side_effect=ValueError("bad")))

        ws = MockWebSocket([
            json.dumps({"type": "boom", "data": {}})
        ])

        self._start_with_client(bridge, ws)
        self.assertNotIn(ws, bridge._clients)


if __name__ == "__main__":
    unittest.main()
