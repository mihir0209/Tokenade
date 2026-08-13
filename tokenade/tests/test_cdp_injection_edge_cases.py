"""Edge-case CDP injection paths (raw CDP, per-cookie failures).

Formerly test_cdp_injection_coverage4 — unique paths not covered by the main suite.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tokenade.core.proxy.cdp_injection import (
    inject_via_raw_cdp,
    inject_stealth_script,
    inject_cookies,
)


def _make_proxy(**overrides):
    proxy = MagicMock()
    proxy._cdp_session = AsyncMock()
    proxy._cdp_port = 9223
    proxy._context = AsyncMock()
    proxy._pages = {}
    proxy.session = {
        "cookies": [],
        "fingerprint": {},
    }
    for k, v in overrides.items():
        setattr(proxy, k, v)
    return proxy


class _RecvMsg(str):
    """String that can be returned by the async WebSocket receive mock."""

    def __await__(self):
        async def _return():
            return str(self)
        return _return().__await__()


class _RecvHelper:
    """Provide awaitable messages to the WebSocket receive mock."""

    def __init__(self, messages):
        self._messages = list(messages)
        self._idx = 0

    def __call__(self):
        return self._get_next()

    def _get_next(self):
        if self._idx < len(self._messages):
            msg = self._messages[self._idx]
            self._idx += 1
            if isinstance(msg, _RecvMsg):
                return msg
            return _RecvMsg(msg)
        raise asyncio.CancelledError()


def _setup_raw_cdp(proxy, messages):
    """Set up mock websocket and urllib for inject_via_raw_cdp."""
    mock_ws_module = MagicMock()
    resp = MagicMock()
    resp.read.return_value = json.dumps({
        "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/browser/abc"
    }).encode()

    ws_ctx = AsyncMock()
    ws_ctx.__aenter__ = AsyncMock(return_value=ws_ctx)
    ws_ctx.__aexit__ = AsyncMock(return_value=False)

    recv_helper = _RecvHelper(messages)
    ws_ctx.recv = recv_helper
    mock_ws_module.connect.return_value = ws_ctx
    return mock_ws_module, resp, ws_ctx


async def _arun_raw_cdp(proxy, mock_ws, resp, ws_ctx, timeout=0.1):
    """Run inject_via_raw_cdp with mocks, returning after timeout or completion."""
    with patch.dict("sys.modules", {"websockets": mock_ws}):
        with patch("urllib.request.urlopen", return_value=resp):
            task = asyncio.create_task(inject_via_raw_cdp(proxy))
            try:
                await asyncio.wait_for(task, timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass


# ---------------------------------------------------------------------------
# Lines 122-125: send_cdp_and_wait buffered events and TimeoutError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_cdp_and_wait_buffers_method_event():
    """During send_cdp_and_wait, a message with 'method' gets buffered (line 122)."""
    proxy = _make_proxy()
    proxy.session["cookies"] = []

    messages = [
        json.dumps({"method": "SomeEvent", "params": {"foo": "bar"}}),
        json.dumps({"id": 1, "result": {}}),
        json.dumps({"id": 2, "result": {}}),
        json.dumps({"id": 3, "result": {}}),
    ]

    mock_ws, resp, ws_ctx = _setup_raw_cdp(proxy, messages)
    await _arun_raw_cdp(proxy, mock_ws, resp, ws_ctx)

    send_calls = [
        json.loads(c.args[0]) for c in ws_ctx.send.call_args_list
    ]
    assert any(c.get("method") == "Storage.enable" for c in send_calls)
    assert any(c.get("method") == "Storage.setCookies" for c in send_calls)


@pytest.mark.asyncio
async def test_send_cdp_and_wait_timeout_returns_none():
    """recv raises TimeoutError inside send_cdp_and_wait, causing break (lines 123-125)."""
    proxy = _make_proxy()
    proxy.session["cookies"] = []

    mock_ws_module = MagicMock()
    resp = MagicMock()
    resp.read.return_value = json.dumps({
        "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/browser/abc"
    }).encode()

    ws_ctx = AsyncMock()
    ws_ctx.__aenter__ = AsyncMock(return_value=ws_ctx)
    ws_ctx.__aexit__ = AsyncMock(return_value=False)
    ws_ctx.recv = _RecvHelper([])  # Empty = immediately TimeoutError
    mock_ws_module.connect.return_value = ws_ctx

    await _arun_raw_cdp(proxy, mock_ws_module, resp, ws_ctx)

    send_calls = [
        json.loads(c.args[0]) for c in ws_ctx.send.call_args_list
    ]
    assert any(c.get("method") == "Storage.enable" for c in send_calls)


# ---------------------------------------------------------------------------
# Lines 152-153: Cookie processing exception in raw CDP cookie loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_raw_cdp_cookie_processing_exception():
    """A cookie that raises during processing is skipped (lines 152-153)."""
    proxy = _make_proxy()
    bad_cookie = MagicMock()
    bad_cookie.get.side_effect = Exception("cookie process error")
    good_cookie = {
        "name": "good", "value": "v", "domain": ".x.com", "path": "/",
    }
    proxy.session["cookies"] = [bad_cookie, good_cookie]

    messages = [
        json.dumps({"id": 1, "result": {}}),
        json.dumps({"id": 2, "result": {}}),
        json.dumps({"id": 3, "result": {}}),
    ]

    mock_ws, resp, ws_ctx = _setup_raw_cdp(proxy, messages)
    await _arun_raw_cdp(proxy, mock_ws, resp, ws_ctx)

    send_calls = [
        json.loads(c.args[0]) for c in ws_ctx.send.call_args_list
    ]
    set_cookies = next(
        (c for c in send_calls if c.get("method") == "Storage.setCookies"),
        None,
    )
    assert set_cookies is not None
    cookies_sent = set_cookies["params"]["cookies"]
    assert len(cookies_sent) == 1
    assert cookies_sent[0]["name"] == "good"


# ---------------------------------------------------------------------------
# Lines 178, 181-209, 212: Event loop handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_raw_cdp_target_attached_page_injects_stealth():
    """Target.attachedToTarget with page type triggers stealth injection (lines 184-206)."""
    proxy = _make_proxy()
    proxy.session["cookies"] = []

    messages = [
        json.dumps({"id": 1, "result": {}}),
        json.dumps({"id": 2, "result": {}}),
        json.dumps({"id": 3, "result": {}}),
        json.dumps({
            "method": "Target.attachedToTarget",
            "params": {
                "sessionId": "sess-page1",
                "targetInfo": {"type": "page"},
            },
        }),
    ]

    mock_ws, resp, ws_ctx = _setup_raw_cdp(proxy, messages)
    await _arun_raw_cdp(proxy, mock_ws, resp, ws_ctx)

    send_calls = [
        json.loads(c.args[0]) for c in ws_ctx.send.call_args_list
    ]
    stealth_calls = [
        c for c in send_calls
        if c.get("method") == "Page.addScriptToEvaluateOnNewDocument"
        and c.get("sessionId") == "sess-page1"
    ]
    assert len(stealth_calls) == 1
    assert stealth_calls[0]["params"]["runImmediately"] is True

    network_calls = [
        c for c in send_calls
        if c.get("method") == "Network.enable"
        and c.get("sessionId") == "sess-page1"
    ]
    assert len(network_calls) == 1


@pytest.mark.asyncio
async def test_raw_cdp_target_destroyed_noop():
    """Target.targetDestroyed is a no-op (lines 208-209)."""
    proxy = _make_proxy()
    proxy.session["cookies"] = []

    messages = [
        json.dumps({"id": 1, "result": {}}),
        json.dumps({"id": 2, "result": {}}),
        json.dumps({"id": 3, "result": {}}),
        json.dumps({
            "method": "Target.targetDestroyed",
            "params": {"targetId": "t1"},
        }),
    ]

    mock_ws, resp, ws_ctx = _setup_raw_cdp(proxy, messages)
    await _arun_raw_cdp(proxy, mock_ws, resp, ws_ctx)

    send_calls = [
        json.loads(c.args[0]) for c in ws_ctx.send.call_args_list
    ]
    stealth_calls = [
        c for c in send_calls
        if c.get("method") == "Page.addScriptToEvaluateOnNewDocument"
    ]
    assert len(stealth_calls) == 0


@pytest.mark.asyncio
async def test_raw_cdp_non_page_target_ignored():
    """attachedToTarget with non-page type is ignored (line 187 check)."""
    proxy = _make_proxy()
    proxy.session["cookies"] = []

    messages = [
        json.dumps({"id": 1, "result": {}}),
        json.dumps({"id": 2, "result": {}}),
        json.dumps({"id": 3, "result": {}}),
        json.dumps({
            "method": "Target.attachedToTarget",
            "params": {
                "sessionId": "sess-bg",
                "targetInfo": {"type": "background_page"},
            },
        }),
    ]

    mock_ws, resp, ws_ctx = _setup_raw_cdp(proxy, messages)
    await _arun_raw_cdp(proxy, mock_ws, resp, ws_ctx)

    send_calls = [
        json.loads(c.args[0]) for c in ws_ctx.send.call_args_list
    ]
    stealth_calls = [
        c for c in send_calls
        if c.get("method") == "Page.addScriptToEvaluateOnNewDocument"
    ]
    assert len(stealth_calls) == 0


@pytest.mark.asyncio
async def test_raw_cdp_none_raw_in_event_loop():
    """raw is None in event loop causes continue (line 178)."""
    proxy = _make_proxy()
    proxy.session["cookies"] = []

    messages = [
        json.dumps({"id": 1, "result": {}}),
        json.dumps({"id": 2, "result": {}}),
        json.dumps({"id": 3, "result": {}}),
        "null",
    ]

    mock_ws, resp, ws_ctx = _setup_raw_cdp(proxy, messages)
    await _arun_raw_cdp(proxy, mock_ws, resp, ws_ctx)

    send_calls = [
        json.loads(c.args[0]) for c in ws_ctx.send.call_args_list
    ]
    assert any(c.get("method") == "Storage.enable" for c in send_calls)


@pytest.mark.asyncio
async def test_raw_cdp_timeout_in_event_loop_continues():
    """TimeoutError in event loop causes continue (line 212)."""
    proxy = _make_proxy()
    proxy.session["cookies"] = []

    messages = [
        json.dumps({"id": 1, "result": {}}),
        json.dumps({"id": 2, "result": {}}),
        json.dumps({"id": 3, "result": {}}),
    ]

    mock_ws, resp, ws_ctx = _setup_raw_cdp(proxy, messages)
    await _arun_raw_cdp(proxy, mock_ws, resp, ws_ctx)

    send_calls = [
        json.loads(c.args[0]) for c in ws_ctx.send.call_args_list
    ]
    assert any(c.get("method") == "Target.setAutoAttach" for c in send_calls)


# ---------------------------------------------------------------------------
# Lines 241-242: inject_stealth_script outer exception
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stealth_script_outer_exception():
    """Exception in the outer try of inject_stealth_script (lines 241-242)."""
    proxy = _make_proxy()
    proxy._context = AsyncMock()
    proxy._pages = MagicMock()
    proxy._pages.items.side_effect = RuntimeError("items iteration failed")

    await inject_stealth_script(proxy)
    proxy._context.add_init_script.assert_not_awaited()


# ---------------------------------------------------------------------------
# Lines 283-284: inject_cookies per-cookie exception
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inject_cookies_per_cookie_exception():
    """Per-cookie exception is caught and remaining cookies processed (lines 283-284)."""
    proxy = _make_proxy()
    proxy._context = AsyncMock()

    bad_cookie = MagicMock()
    bad_cookie.get.side_effect = Exception("cookie processing error")

    good_cookie = {
        "name": "good", "value": "v", "domain": ".x.com", "path": "/",
    }

    proxy.session["cookies"] = [bad_cookie, good_cookie]

    await inject_cookies(proxy)
    proxy._context.add_cookies.assert_awaited_once()
    cookies_added = proxy._context.add_cookies.call_args[0][0]
    assert len(cookies_added) == 1
    assert cookies_added[0]["name"] == "good"


@pytest.mark.asyncio
async def test_inject_cookies_bad_samesite_type():
    """Cookie with non-string sameSite triggers per-cookie exception (lines 283-284)."""
    proxy = _make_proxy()
    proxy._context = AsyncMock()

    bad_cookie = {
        "name": "bad", "value": "v", "domain": ".x.com", "path": "/",
        "sameSite": 123,
    }
    good_cookie = {
        "name": "good", "value": "v2", "domain": ".y.com", "path": "/",
    }

    proxy.session["cookies"] = [bad_cookie, good_cookie]

    await inject_cookies(proxy)
    proxy._context.add_cookies.assert_awaited_once()
    cookies_added = proxy._context.add_cookies.call_args[0][0]
    assert len(cookies_added) == 1
    assert cookies_added[0]["name"] == "good"
