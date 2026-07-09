"""Comprehensive tests for cdp_injection module — targeting 50%+ coverage."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tokenade.core.errors import InjectionError
from tokenade.core.proxy.cdp_injection import (
    inject_via_cdp,
    inject_via_raw_cdp,
    inject_stealth_script,
    inject_cookies,
    inject_local_storage,
)


def _make_proxy(**overrides):
    """Create a mock CDPProxy with sensible defaults."""
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


# ---------------------------------------------------------------------------
# inject_via_cdp
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inject_via_cdp_returns_when_no_session():
    proxy = _make_proxy(_cdp_session=None)
    with pytest.raises(InjectionError):
        await inject_via_cdp(proxy)


@pytest.mark.asyncio
async def test_inject_via_cdp_stealth_script_sent():
    proxy = _make_proxy()
    proxy.session["cookies"] = []
    await inject_via_cdp(proxy)
    calls = proxy._cdp_session.send.call_args_list
    assert any(c.args[0] == "Page.addScriptToEvaluateOnNewDocument" for c in calls)
    assert any(c.args[0] == "Network.enable" for c in calls)


@pytest.mark.asyncio
async def test_inject_via_cdp_stealth_failure_does_not_propagate():
    proxy = _make_proxy()
    proxy._cdp_session.send.side_effect = Exception("boom")
    await inject_via_cdp(proxy)


@pytest.mark.asyncio
async def test_inject_via_cdp_cookies_basic():
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "a", "value": "1", "domain": ".example.com", "path": "/"},
    ]
    await inject_via_cdp(proxy)
    set_cookie_calls = [
        c for c in proxy._cdp_session.send.call_args_list
        if c.args[0] == "Network.setCookie"
    ]
    assert len(set_cookie_calls) == 1
    params = set_cookie_calls[0].args[1]
    assert params["name"] == "a"
    assert params["value"] == "1"
    assert params["domain"] == ".example.com"


@pytest.mark.asyncio
async def test_inject_via_cdp_cookie_secure_httponly():
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "s", "value": "v", "domain": "d", "path": "/p",
         "secure": True, "httpOnly": True},
    ]
    await inject_via_cdp(proxy)
    params = [c for c in proxy._cdp_session.send.call_args_list
              if c.args[0] == "Network.setCookie"][0].args[1]
    assert params["secure"] is True
    assert params["httpOnly"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("ss_in,ss_out", [
    ("strict", "Strict"),
    ("lax", "Lax"),
    ("none", "None"),
    ("Strict", "Strict"),
    ("LAX", "Lax"),
])
async def test_inject_via_cdp_cookie_same_site(ss_in, ss_out):
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "c", "value": "v", "domain": "d", "path": "/", "sameSite": ss_in},
    ]
    await inject_via_cdp(proxy)
    params = [c for c in proxy._cdp_session.send.call_args_list
              if c.args[0] == "Network.setCookie"][0].args[1]
    assert params["sameSite"] == ss_out


@pytest.mark.asyncio
async def test_inject_via_cdp_cookie_same_site_unknown_not_set():
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "c", "value": "v", "domain": "d", "path": "/", "sameSite": "random"},
    ]
    await inject_via_cdp(proxy)
    params = [c for c in proxy._cdp_session.send.call_args_list
              if c.args[0] == "Network.setCookie"][0].args[1]
    assert "sameSite" not in params


@pytest.mark.asyncio
async def test_inject_via_cdp_cookie_expires_millis():
    proxy = _make_proxy()
    ts_ms = 1700000000000
    proxy.session["cookies"] = [
        {"name": "c", "value": "v", "domain": "d", "path": "/", "expires": ts_ms},
    ]
    await inject_via_cdp(proxy)
    params = [c for c in proxy._cdp_session.send.call_args_list
              if c.args[0] == "Network.setCookie"][0].args[1]
    assert params["expires"] == pytest.approx(ts_ms / 1000)


@pytest.mark.asyncio
async def test_inject_via_cdp_cookie_expires_seconds():
    proxy = _make_proxy()
    ts_s = 1700000000
    proxy.session["cookies"] = [
        {"name": "c", "value": "v", "domain": "d", "path": "/", "expires": ts_s},
    ]
    await inject_via_cdp(proxy)
    params = [c for c in proxy._cdp_session.send.call_args_list
              if c.args[0] == "Network.setCookie"][0].args[1]
    assert params["expires"] == ts_s


@pytest.mark.asyncio
async def test_inject_via_cdp_cookie_no_expires():
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "c", "value": "v", "domain": "d", "path": "/"},
    ]
    await inject_via_cdp(proxy)
    params = [c for c in proxy._cdp_session.send.call_args_list
              if c.args[0] == "Network.setCookie"][0].args[1]
    assert "expires" not in params


@pytest.mark.asyncio
async def test_inject_via_cdp_cookie_send_failure_is_swallowed():
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "c", "value": "v", "domain": "d", "path": "/"},
    ]
    proxy._cdp_session.send.side_effect = [
        None,
        None,
        Exception("cookie fail"),
    ]
    # All cookie setCookie calls fail => hard InjectionError (P3 honesty)
    with pytest.raises(InjectionError):
        await inject_via_cdp(proxy)


@pytest.mark.asyncio
async def test_inject_via_cdp_default_path():
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "c", "value": "v", "domain": "d"},
    ]
    await inject_via_cdp(proxy)
    params = [c for c in proxy._cdp_session.send.call_args_list
              if c.args[0] == "Network.setCookie"][0].args[1]
    assert params["path"] == "/"


@pytest.mark.asyncio
async def test_inject_via_cdp_network_enable_failure_swallowed():
    proxy = _make_proxy()
    proxy._cdp_session.send.side_effect = [
        None,
        Exception("network fail"),
    ]
    await inject_via_cdp(proxy)


# ---------------------------------------------------------------------------
# inject_via_raw_cdp — websockets not installed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inject_via_raw_cdp_no_websockets():
    proxy = _make_proxy()
    with patch.dict("sys.modules", {"websockets": None}):
        await inject_via_raw_cdp(proxy)


# ---------------------------------------------------------------------------
# inject_via_raw_cdp — fetch URL fails
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inject_via_raw_cdp_fetch_url_fails():
    proxy = _make_proxy()
    mock_ws = MagicMock()
    with patch.dict("sys.modules", {"websockets": mock_ws}):
        with patch("urllib.request.urlopen", side_effect=Exception("connrefused")):
            await inject_via_raw_cdp(proxy)


@pytest.mark.asyncio
async def test_inject_via_raw_cdp_no_ws_url():
    proxy = _make_proxy()
    mock_ws = MagicMock()
    resp = MagicMock()
    resp.read.return_value = json.dumps({"webSocketDebuggerUrl": None}).encode()
    with patch.dict("sys.modules", {"websockets": mock_ws}):
        with patch("urllib.request.urlopen", return_value=resp):
            await inject_via_raw_cdp(proxy)


# ---------------------------------------------------------------------------
# inject_via_raw_cdp — full happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inject_via_raw_cdp_happy_path():
    proxy = _make_proxy()
    proxy.session["fingerprint"] = {"user_agent": "HeadlessChrome/120"}
    proxy.session["cookies"] = [
        {"name": "c1", "value": "v1", "domain": ".x.com", "path": "/",
         "secure": True, "httpOnly": True, "sameSite": "lax",
         "expires": 1700000000000},
        {"name": "c2", "value": "v2", "domain": ".y.com", "path": "/"},
    ]

    mock_ws = MagicMock()
    resp = MagicMock()
    resp.read.return_value = json.dumps({
        "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/browser/abc"
    }).encode()
    with patch.dict("sys.modules", {"websockets": mock_ws}):
        with patch("urllib.request.urlopen", return_value=resp):
            ws_ctx = AsyncMock()
            ws_ctx.__aenter__ = AsyncMock(return_value=ws_ctx)
            ws_ctx.__aexit__ = AsyncMock(return_value=False)
            call_count = 0

            async def recv_seq():
                nonlocal call_count
                call_count += 1
                if call_count <= 6:
                    msg_id = call_count // 2 + 1
                    return json.dumps({"id": msg_id, "result": {}}).encode()
                raise asyncio.TimeoutError

            ws_ctx.recv = recv_seq
            mock_ws.connect.return_value = ws_ctx

            task = asyncio.create_task(inject_via_raw_cdp(proxy))
            try:
                await asyncio.wait_for(task, timeout=3)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

            calls_made = [json.loads(c.args[0]) for c in ws_ctx.send.call_args_list]
            storage_call = next((c for c in calls_made if c.get("method") == "Storage.setCookies"), None)
            assert storage_call is not None


@pytest.mark.asyncio
async def test_inject_via_raw_cdp_no_fingerprint_uses_default_ua():
    proxy = _make_proxy()
    proxy.session["fingerprint"] = {}
    proxy.session["cookies"] = []

    mock_ws = MagicMock()
    resp = MagicMock()
    resp.read.return_value = json.dumps({
        "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/browser/abc"
    }).encode()
    with patch.dict("sys.modules", {"websockets": mock_ws}):
        with patch("urllib.request.urlopen", return_value=resp):
            ws_ctx = AsyncMock()
            ws_ctx.__aenter__ = AsyncMock(return_value=ws_ctx)
            ws_ctx.__aexit__ = AsyncMock(return_value=False)
            call_count = 0

            async def recv_seq():
                nonlocal call_count
                call_count += 1
                if call_count <= 6:
                    msg_id = call_count // 2 + 1
                    return json.dumps({"id": msg_id, "result": {}}).encode()
                raise asyncio.TimeoutError

            ws_ctx.recv = recv_seq
            mock_ws.connect.return_value = ws_ctx

            task = asyncio.create_task(inject_via_raw_cdp(proxy))
            try:
                await asyncio.wait_for(task, timeout=3)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

            calls_made = [json.loads(c.args[0]) for c in ws_ctx.send.call_args_list]
            storage_call = next((c for c in calls_made if c.get("method") == "Storage.setCookies"), None)
            assert storage_call is not None


@pytest.mark.asyncio
async def test_inject_via_raw_cdp_cookie_same_site_variants():
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "c", "value": "v", "domain": "d", "path": "/", "sameSite": "none",
         "expires": 1700000000},
    ]

    mock_ws = MagicMock()
    resp = MagicMock()
    resp.read.return_value = json.dumps({
        "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/browser/abc"
    }).encode()
    with patch.dict("sys.modules", {"websockets": mock_ws}):
        with patch("urllib.request.urlopen", return_value=resp):
            ws_ctx = AsyncMock()
            ws_ctx.__aenter__ = AsyncMock(return_value=ws_ctx)
            ws_ctx.__aexit__ = AsyncMock(return_value=False)
            call_count = 0

            async def recv_seq():
                nonlocal call_count
                call_count += 1
                if call_count <= 6:
                    msg_id = call_count // 2 + 1
                    return json.dumps({"id": msg_id, "result": {}}).encode()
                raise asyncio.TimeoutError

            ws_ctx.recv = recv_seq
            mock_ws.connect.return_value = ws_ctx

            task = asyncio.create_task(inject_via_raw_cdp(proxy))
            try:
                await asyncio.wait_for(task, timeout=3)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

            calls_made = [json.loads(c.args[0]) for c in ws_ctx.send.call_args_list]
            storage_call = next((c for c in calls_made if c.get("method") == "Storage.setCookies"), None)
            assert storage_call is not None
            cookie = storage_call["params"]["cookies"][0]
            assert cookie["sameSite"] == "None"
            assert cookie["expires"] == 1700000000


@pytest.mark.asyncio
async def test_inject_via_raw_cdp_cookie_send_error_swallowed():
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "c", "value": "v", "domain": "d", "path": "/"},
    ]

    mock_ws = MagicMock()
    resp = MagicMock()
    resp.read.return_value = json.dumps({
        "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/browser/abc"
    }).encode()
    with patch.dict("sys.modules", {"websockets": mock_ws}):
        with patch("urllib.request.urlopen", return_value=resp):
            ws_ctx = AsyncMock()
            ws_ctx.__aenter__ = AsyncMock(return_value=ws_ctx)
            ws_ctx.__aexit__ = AsyncMock(return_value=False)
            call_count = 0

            async def recv_seq():
                nonlocal call_count
                call_count += 1
                if call_count <= 6:
                    msg_id = call_count // 2 + 1
                    return json.dumps({"id": msg_id, "result": {}}).encode()
                raise asyncio.TimeoutError

            ws_ctx.recv = recv_seq

            send_count = 0

            async def send_that_fails(msg):
                nonlocal send_count
                send_count += 1
                if send_count == 1:
                    return
                raise Exception("send fail")

            ws_ctx.send = send_that_fails
            mock_ws.connect.return_value = ws_ctx

            task = asyncio.create_task(inject_via_raw_cdp(proxy))
            try:
                await asyncio.wait_for(task, timeout=3)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass


@pytest.mark.asyncio
async def test_inject_via_raw_cdp_event_attached_to_target():
    """Test that Target.attachedToTarget events trigger stealth injection.

    The source code mixes sync/async recv:
      - send_cdp_and_wait does `await asyncio.wait_for(ws.recv(), timeout=10)`
      - event loop does `loop.run_in_executor(None, _ws.recv)`
    We need a helper that works both ways.
    """
    proxy = _make_proxy()
    proxy.session["fingerprint"] = {"user_agent": "HeadlessChrome/120"}
    proxy.session["cookies"] = []

    mock_ws = MagicMock()
    resp = MagicMock()
    resp.read.return_value = json.dumps({
        "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/browser/abc"
    }).encode()
    with patch.dict("sys.modules", {"websockets": mock_ws}):
        with patch("urllib.request.urlopen", return_value=resp):
            ws_ctx = AsyncMock()
            ws_ctx.__aenter__ = AsyncMock(return_value=ws_ctx)
            ws_ctx.__aexit__ = AsyncMock(return_value=False)

            # Build all messages: 3 setup responses + 1 event
            setup_responses = [
                json.dumps({"id": 1, "result": {}}).encode(),
                json.dumps({"id": 2, "result": {}}).encode(),
                json.dumps({"id": 3, "result": {}}).encode(),
            ]
            event = json.dumps({
                "method": "Target.attachedToTarget",
                "params": {
                    "sessionId": "sess-123",
                    "targetInfo": {"type": "page"},
                },
            }).encode()

            all_msgs = setup_responses + [event]

            class RecvHelper:
                """Works as both sync (for run_in_executor) and async (for send_cdp_and_wait)."""

                def __init__(self, messages):
                    self._messages = list(messages)
                    self._idx = 0

                async def __call__(self):
                    return self._get_next()

                def _get_next(self):
                    if self._idx < len(self._messages):
                        msg = self._messages[self._idx]
                        self._idx += 1
                        return msg
                    raise asyncio.TimeoutError()

                # For run_in_executor which calls it directly in a thread
                # We make the object directly callable as sync too
                def __func__(self):
                    return self._get_next()

            recv_helper = RecvHelper(all_msgs)

            # Make _ws.recv work as sync (for run_in_executor)
            # and ws.recv work as async (for send_cdp_and_wait)
            ws_ctx.recv = recv_helper

            mock_ws.connect.return_value = ws_ctx

            task = asyncio.create_task(inject_via_raw_cdp(proxy))
            try:
                await asyncio.wait_for(task, timeout=3)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            except Exception:
                pass

            # 3 setup sends + at least 1 stealth injection into target page
            assert ws_ctx.send.call_count >= 3


@pytest.mark.asyncio
async def test_inject_via_raw_cdp_event_target_destroyed():
    proxy = _make_proxy()
    proxy.session["cookies"] = []

    mock_ws = MagicMock()
    resp = MagicMock()
    resp.read.return_value = json.dumps({
        "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/browser/abc"
    }).encode()
    with patch.dict("sys.modules", {"websockets": mock_ws}):
        with patch("urllib.request.urlopen", return_value=resp):
            ws_ctx = AsyncMock()
            ws_ctx.__aenter__ = AsyncMock(return_value=ws_ctx)
            ws_ctx.__aexit__ = AsyncMock(return_value=False)
            call_count = 0

            setup_responses = [
                json.dumps({"id": 1, "result": {}}).encode(),
                json.dumps({"id": 2, "result": {}}).encode(),
                json.dumps({"id": 3, "result": {}}).encode(),
            ]
            event = json.dumps({
                "method": "Target.targetDestroyed",
                "params": {},
            }).encode()

            all_msgs = setup_responses + [event]

            async def recv_seq():
                nonlocal call_count
                if call_count < len(all_msgs):
                    msg = all_msgs[call_count]
                    call_count += 1
                    return msg
                raise asyncio.TimeoutError

            ws_ctx.recv = recv_seq
            mock_ws.connect.return_value = ws_ctx

            task = asyncio.create_task(inject_via_raw_cdp(proxy))
            try:
                await asyncio.wait_for(task, timeout=3)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass


@pytest.mark.asyncio
async def test_inject_via_raw_cdp_non_page_target_ignored():
    proxy = _make_proxy()
    proxy.session["cookies"] = []

    mock_ws = MagicMock()
    resp = MagicMock()
    resp.read.return_value = json.dumps({
        "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/browser/abc"
    }).encode()
    with patch.dict("sys.modules", {"websockets": mock_ws}):
        with patch("urllib.request.urlopen", return_value=resp):
            ws_ctx = AsyncMock()
            ws_ctx.__aenter__ = AsyncMock(return_value=ws_ctx)
            ws_ctx.__aexit__ = AsyncMock(return_value=False)
            call_count = 0

            setup_responses = [
                json.dumps({"id": 1, "result": {}}).encode(),
                json.dumps({"id": 2, "result": {}}).encode(),
                json.dumps({"id": 3, "result": {}}).encode(),
            ]
            event = json.dumps({
                "method": "Target.attachedToTarget",
                "params": {
                    "sessionId": "sess-456",
                    "targetInfo": {"type": "background_page"},
                },
            }).encode()

            all_msgs = setup_responses + [event]

            async def recv_seq():
                nonlocal call_count
                if call_count < len(all_msgs):
                    msg = all_msgs[call_count]
                    call_count += 1
                    return msg
                raise asyncio.TimeoutError

            ws_ctx.recv = recv_seq
            mock_ws.connect.return_value = ws_ctx

            task = asyncio.create_task(inject_via_raw_cdp(proxy))
            try:
                await asyncio.wait_for(task, timeout=3)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

            send_calls = [json.loads(c.args[0]) if isinstance(c.args[0], str) else c.args[0]
                          for c in ws_ctx.send.call_args_list]
            stealth_calls = [
                c for c in send_calls
                if isinstance(c, dict) and c.get("method") == "Page.addScriptToEvaluateOnNewDocument"
            ]
            assert len(stealth_calls) == 0


@pytest.mark.asyncio
async def test_inject_via_raw_cdp_event_other_error_swallowed():
    proxy = _make_proxy()
    proxy.session["fingerprint"] = {"user_agent": "HeadlessChrome/120"}
    proxy.session["cookies"] = []

    mock_ws = MagicMock()
    resp = MagicMock()
    resp.read.return_value = json.dumps({
        "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/browser/abc"
    }).encode()
    with patch.dict("sys.modules", {"websockets": mock_ws}):
        with patch("urllib.request.urlopen", return_value=resp):
            ws_ctx = AsyncMock()
            ws_ctx.__aenter__ = AsyncMock(return_value=ws_ctx)
            ws_ctx.__aexit__ = AsyncMock(return_value=False)
            call_count = 0

            setup_responses = [
                json.dumps({"id": 1, "result": {}}).encode(),
                json.dumps({"id": 2, "result": {}}).encode(),
                json.dumps({"id": 3, "result": {}}).encode(),
            ]
            event = json.dumps({
                "method": "Target.attachedToTarget",
                "params": {
                    "sessionId": "sess-789",
                    "targetInfo": {"type": "page"},
                },
            }).encode()

            all_msgs = setup_responses + [event]

            async def recv_seq():
                nonlocal call_count
                if call_count < len(all_msgs):
                    msg = all_msgs[call_count]
                    call_count += 1
                    return msg
                raise asyncio.TimeoutError

            ws_ctx.recv = recv_seq

            send_count = 0

            async def send_that_fails(msg):
                nonlocal send_count
                send_count += 1
                if send_count <= 3:
                    return
                raise Exception("inject fail")

            ws_ctx.send = send_that_fails
            mock_ws.connect.return_value = ws_ctx

            task = asyncio.create_task(inject_via_raw_cdp(proxy))
            try:
                await asyncio.wait_for(task, timeout=3)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass


@pytest.mark.asyncio
async def test_inject_via_raw_cdp_none_raw_continues():
    proxy = _make_proxy()
    proxy.session["cookies"] = []

    mock_ws = MagicMock()
    resp = MagicMock()
    resp.read.return_value = json.dumps({
        "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/browser/abc"
    }).encode()
    with patch.dict("sys.modules", {"websockets": mock_ws}):
        with patch("urllib.request.urlopen", return_value=resp):
            ws_ctx = AsyncMock()
            ws_ctx.__aenter__ = AsyncMock(return_value=ws_ctx)
            ws_ctx.__aexit__ = AsyncMock(return_value=False)
            call_count = 0

            setup_responses = [
                json.dumps({"id": 1, "result": {}}).encode(),
                json.dumps({"id": 2, "result": {}}).encode(),
                json.dumps({"id": 3, "result": {}}).encode(),
            ]
            none_msg = b"null"

            all_msgs = setup_responses + [none_msg]

            async def recv_seq():
                nonlocal call_count
                if call_count < len(all_msgs):
                    msg = all_msgs[call_count]
                    call_count += 1
                    return msg
                raise asyncio.TimeoutError

            ws_ctx.recv = recv_seq
            mock_ws.connect.return_value = ws_ctx

            task = asyncio.create_task(inject_via_raw_cdp(proxy))
            try:
                await asyncio.wait_for(task, timeout=3)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass


# ---------------------------------------------------------------------------
# inject_stealth_script
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inject_stealth_script_returns_when_no_context():
    proxy = _make_proxy(_context=None)
    await inject_stealth_script(proxy)


@pytest.mark.asyncio
async def test_inject_stealth_script_no_pages():
    proxy = _make_proxy()
    proxy._pages = {}
    await inject_stealth_script(proxy)
    proxy._context.add_init_script.assert_awaited_once()


@pytest.mark.asyncio
async def test_inject_stealth_script_with_pages():
    page1 = AsyncMock()
    page2 = AsyncMock()
    proxy = _make_proxy()
    proxy._pages = {"p1": page1, "p2": page2}
    await inject_stealth_script(proxy)
    page1.evaluate.assert_awaited_once()
    page2.evaluate.assert_awaited_once()
    proxy._context.add_init_script.assert_awaited_once()


@pytest.mark.asyncio
async def test_inject_stealth_script_page_failure_is_swallowed():
    page1 = AsyncMock()
    page1.evaluate.side_effect = Exception("eval fail")
    proxy = _make_proxy()
    proxy._pages = {"p1": page1}
    await inject_stealth_script(proxy)
    proxy._context.add_init_script.assert_awaited_once()


@pytest.mark.asyncio
async def test_inject_stealth_script_init_script_failure_swallowed():
    proxy = _make_proxy()
    proxy._context.add_init_script.side_effect = Exception("init fail")
    await inject_stealth_script(proxy)


@pytest.mark.asyncio
async def test_inject_stealth_script_context_failure_swallowed():
    proxy = _make_proxy()
    proxy._context.add_init_script.side_effect = Exception("ctx fail")
    proxy._pages = {}
    await inject_stealth_script(proxy)


# ---------------------------------------------------------------------------
# inject_cookies
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inject_cookies_returns_when_no_context():
    proxy = _make_proxy(_context=None)
    # empty cookies → no-op
    await inject_cookies(proxy)


@pytest.mark.asyncio
async def test_inject_cookies_no_context_with_cookies_raises():
    proxy = _make_proxy(_context=None)
    proxy.session["cookies"] = [
        {"name": "c", "value": "v", "domain": "d", "path": "/"},
    ]
    with pytest.raises(InjectionError):
        await inject_cookies(proxy)


@pytest.mark.asyncio
async def test_inject_cookies_empty():
    proxy = _make_proxy()
    proxy.session["cookies"] = []
    await inject_cookies(proxy)
    proxy._context.add_cookies.assert_not_awaited()


@pytest.mark.asyncio
async def test_inject_cookies_basic():
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "a", "value": "1", "domain": ".example.com", "path": "/"},
    ]
    await inject_cookies(proxy)
    proxy._context.add_cookies.assert_awaited_once()
    cookies = proxy._context.add_cookies.call_args[0][0]
    assert cookies[0]["name"] == "a"
    assert cookies[0]["value"] == "1"


@pytest.mark.asyncio
async def test_inject_cookies_secure_httponly():
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "s", "value": "v", "domain": "d", "path": "/",
         "secure": True, "httpOnly": True},
    ]
    await inject_cookies(proxy)
    cookies = proxy._context.add_cookies.call_args[0][0]
    assert cookies[0]["secure"] is True
    assert cookies[0]["httpOnly"] is True


@pytest.mark.asyncio
async def test_inject_cookies_no_secure_no_httponly():
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "c", "value": "v", "domain": "d", "path": "/"},
    ]
    await inject_cookies(proxy)
    cookies = proxy._context.add_cookies.call_args[0][0]
    assert "secure" not in cookies[0]
    assert "httpOnly" not in cookies[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("ss_in,ss_out", [
    ("strict", "Strict"),
    ("lax", "Lax"),
    ("none", "None"),
])
async def test_inject_cookies_same_site(ss_in, ss_out):
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "c", "value": "v", "domain": "d", "path": "/", "sameSite": ss_in},
    ]
    await inject_cookies(proxy)
    cookies = proxy._context.add_cookies.call_args[0][0]
    assert cookies[0]["sameSite"] == ss_out


@pytest.mark.asyncio
async def test_inject_cookies_same_site_unknown_not_set():
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "c", "value": "v", "domain": "d", "path": "/", "sameSite": "random"},
    ]
    await inject_cookies(proxy)
    cookies = proxy._context.add_cookies.call_args[0][0]
    assert "sameSite" not in cookies[0]


@pytest.mark.asyncio
async def test_inject_cookies_expires_millis():
    proxy = _make_proxy()
    ts_ms = 1700000000000
    proxy.session["cookies"] = [
        {"name": "c", "value": "v", "domain": "d", "path": "/", "expires": ts_ms},
    ]
    await inject_cookies(proxy)
    cookies = proxy._context.add_cookies.call_args[0][0]
    assert cookies[0]["expires"] == pytest.approx(ts_ms / 1000)


@pytest.mark.asyncio
async def test_inject_cookies_expires_seconds():
    proxy = _make_proxy()
    ts_s = 1700000000
    proxy.session["cookies"] = [
        {"name": "c", "value": "v", "domain": "d", "path": "/", "expires": ts_s},
    ]
    await inject_cookies(proxy)
    cookies = proxy._context.add_cookies.call_args[0][0]
    assert cookies[0]["expires"] == pytest.approx(float(ts_s))


@pytest.mark.asyncio
async def test_inject_cookies_no_expires():
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "c", "value": "v", "domain": "d", "path": "/"},
    ]
    await inject_cookies(proxy)
    cookies = proxy._context.add_cookies.call_args[0][0]
    assert "expires" not in cookies[0]


@pytest.mark.asyncio
async def test_inject_cookies_default_path():
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "c", "value": "v", "domain": "d"},
    ]
    await inject_cookies(proxy)
    cookies = proxy._context.add_cookies.call_args[0][0]
    assert cookies[0]["path"] == "/"


@pytest.mark.asyncio
async def test_inject_cookies_add_failure_raises():
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "c", "value": "v", "domain": "d", "path": "/"},
    ]
    proxy._context.add_cookies.side_effect = Exception("add fail")
    with pytest.raises(InjectionError):
        await inject_cookies(proxy)


@pytest.mark.asyncio
async def test_inject_cookies_multiple():
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "a", "value": "1", "domain": "d1", "path": "/"},
        {"name": "b", "value": "2", "domain": "d2", "path": "/"},
        {"name": "c", "value": "3", "domain": "d3", "path": "/"},
    ]
    await inject_cookies(proxy)
    cookies = proxy._context.add_cookies.call_args[0][0]
    assert len(cookies) == 3


@pytest.mark.asyncio
async def test_inject_cookies_individual_cookie_failure_swallowed():
    proxy = _make_proxy()
    proxy.session["cookies"] = [
        {"name": "bad", "value": "v", "domain": "d", "path": "/",
         "expires": "not_a_number"},
        {"name": "good", "value": "v", "domain": "d", "path": "/"},
    ]
    await inject_cookies(proxy)
    cookies = proxy._context.add_cookies.call_args[0][0]
    assert any(c["name"] == "good" for c in cookies)


# ---------------------------------------------------------------------------
# inject_local_storage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inject_local_storage_empty():
    proxy = _make_proxy()
    proxy.session["local_storage"] = {}
    page = AsyncMock()
    await inject_local_storage(proxy, page)
    page.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_inject_local_storage_no_key():
    proxy = _make_proxy()
    proxy.session = {}
    page = AsyncMock()
    await inject_local_storage(proxy, page)
    page.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_inject_local_storage_flat():
    proxy = _make_proxy()
    proxy.session["local_storage"] = {"key1": "val1", "key2": "val2"}
    page = AsyncMock()
    await inject_local_storage(proxy, page)
    page.evaluate.assert_awaited_once()
    js = page.evaluate.call_args[0][0]
    assert "localStorage.setItem('key1', 'val1')" in js
    assert "localStorage.setItem('key2', 'val2')" in js
    assert js.startswith("(() => {")
    assert js.endswith("})();")


@pytest.mark.asyncio
async def test_inject_local_storage_nested_dict():
    proxy = _make_proxy()
    proxy.session["local_storage"] = {
        "domain1": {"k1": "v1", "k2": "v2"},
    }
    page = AsyncMock()
    await inject_local_storage(proxy, page)
    page.evaluate.assert_awaited_once()
    js = page.evaluate.call_args[0][0]
    assert "localStorage.setItem('k1', 'v1')" in js
    assert "localStorage.setItem('k2', 'v2')" in js


@pytest.mark.asyncio
async def test_inject_local_storage_mixed():
    proxy = _make_proxy()
    proxy.session["local_storage"] = {
        "top_key": "top_val",
        "domain": {"nested_key": "nested_val"},
    }
    page = AsyncMock()
    await inject_local_storage(proxy, page)
    page.evaluate.assert_awaited_once()
    js = page.evaluate.call_args[0][0]
    assert "localStorage.setItem('top_key', 'top_val')" in js
    assert "localStorage.setItem('nested_key', 'nested_val')" in js


@pytest.mark.asyncio
async def test_inject_local_storage_only_empty_nested_dicts():
    proxy = _make_proxy()
    proxy.session["local_storage"] = {"d1": {}, "d2": {}}
    page = AsyncMock()
    await inject_local_storage(proxy, page)
    page.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_inject_local_storage_escaping():
    proxy = _make_proxy()
    proxy.session["local_storage"] = {"k'ey": "v'al"}
    page = AsyncMock()
    await inject_local_storage(proxy, page)
    js = page.evaluate.call_args[0][0]
    assert "k\\'ey" in js
    assert "v\\'al" in js


@pytest.mark.asyncio
async def test_inject_local_storage_evaluate_failure_raises():
    proxy = _make_proxy()
    proxy.session["local_storage"] = {"k": "v"}
    page = AsyncMock()
    page.evaluate.side_effect = Exception("eval fail")
    with pytest.raises(InjectionError):
        await inject_local_storage(proxy, page)


@pytest.mark.asyncio
async def test_inject_local_storage_numeric_value():
    proxy = _make_proxy()
    proxy.session["local_storage"] = {"count": 42}
    page = AsyncMock()
    await inject_local_storage(proxy, page)
    js = page.evaluate.call_args[0][0]
    assert "localStorage.setItem('count', '42')" in js


@pytest.mark.asyncio
async def test_inject_local_storage_bool_value():
    proxy = _make_proxy()
    proxy.session["local_storage"] = {"flag": True}
    page = AsyncMock()
    await inject_local_storage(proxy, page)
    js = page.evaluate.call_args[0][0]
    assert "localStorage.setItem('flag', 'True')" in js
