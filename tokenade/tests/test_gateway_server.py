"""Tests for hidden gateway control-plane contracts."""

import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from tokenade.core.events.types import EventType
from tokenade.core.gateway.server import GatewayConfigError, create_gateway_control_plane
from tokenade.core.gateway.runtime import GatewayRuntime
from tokenade.core.importer.format_importer import FormatImporter
from tokenade.core.request_config import parse_request_config
from tokenade.tests.test_gateway_runtime import FakeContextFactory


def _write_session(tmp_path, name, site_name="github", metadata=None):
    path = Path(tmp_path) / name
    path.write_text(json.dumps({
        "version": "1.0",
        "created_at": "2026-07-18T00:00:00",
        "site_name": site_name,
        "auth_status": "logged_in",
        "cookies": [{
            "name": "sid",
            "value": "secret-cookie-value",
            "domain": f".{site_name}.com",
            "path": "/",
            "expires": time.time() + 172800,
        }],
        "metadata": metadata or {},
        "storage": {"local": {"https://example.com": {"token": "secret-storage-value"}}},
    }))
    return path


def _request(tmp_path, extra=None):
    payload = {
        "version": "1",
        "operation": "gateway",
        "sessions": {"dir": str(tmp_path), "pattern": "*.tokenade"},
        "gateway": {"host": "127.0.0.1", "port": 0, "backend": "cdp"},
        "routing": {"object": "session", "strategy": "round-robin", "switch_interval_seconds": 5},
        "plugins": [],
    }
    if extra:
        payload.update(extra)
    return parse_request_config(payload)


def _start_account_server():
    accounts = {}

    class AccountHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/accounts":
                self._send_json(404, {"error": "not found"})
                return

            length = int(self.headers.get("Content-Length", "0") or "0")
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            username = str(payload.get("username") or "").strip()
            if not username:
                self._send_json(400, {"error": "username required"})
                return

            account_id = f"acct-{len(accounts) + 1}"
            session_value = f"session-{account_id}-{username}"
            accounts[session_value] = {"account_id": account_id, "username": username}
            self._send_json(
                201,
                {
                    "account_id": account_id,
                    "username": username,
                    "session_value": session_value,
                    "origin": f"http://127.0.0.1:{self.server.server_port}",
                },
                {"Set-Cookie": f"ta_session={session_value}; Path=/; HttpOnly; SameSite=Lax"},
            )

        def do_GET(self):
            if self.path != "/whoami":
                self._send_json(404, {"error": "not found"})
                return
            cookies = self.headers.get("Cookie", "")
            session_value = ""
            for item in cookies.split(";"):
                name, _, value = item.strip().partition("=")
                if name == "ta_session":
                    session_value = value
                    break
            account = accounts.get(session_value)
            if not account:
                self._send_json(401, {"error": "not authenticated"})
                return
            self._send_json(200, {"authenticated": True, **account})

        def log_message(self, format, *args):
            return

        def _send_json(self, status, payload, headers=None):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), AccountHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread


def _post_json(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url, cookie_header=None):
    headers = {"Cookie": cookie_header} if cookie_header else {}
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _gateway_post(base_url, path, payload=None):
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(payload or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def test_gateway_routes_five_playwright_storage_state_accounts(tmp_path):
    """End-to-end-ish gateway smoke using generated Playwright storageState files.

    The account server mints five independent accounts and session cookies. The
    test then models Playwright's storageState JSON directly (no browser launch),
    converts each export into a v3 .tokenade session, and verifies the gateway can
    list, route, and select isolated runtime contexts for all accounts.
    """
    account_httpd, account_thread = _start_account_server()
    sessions_dir = tmp_path / "sessions"
    storage_dir = tmp_path / "storage-state"
    sessions_dir.mkdir()
    storage_dir.mkdir()
    origin = f"http://127.0.0.1:{account_httpd.server_port}"
    expires = int(time.time() + 172800)

    try:
        expected_ids = []
        expected_cookie_values = []
        for index in range(1, 6):
            username = f"account-{index}"
            account = _post_json(f"{origin}/accounts", {"username": username})
            assert _get_json(
                f"{origin}/whoami",
                f"ta_session={account['session_value']}",
            ) == {
                "authenticated": True,
                "account_id": account["account_id"],
                "username": username,
            }

            expected_ids.append(account["account_id"])
            expected_cookie_values.append(account["session_value"])
            storage_state_path = storage_dir / f"{account['account_id']}.json"
            storage_state_path.write_text(json.dumps({
                "cookies": [{
                    "name": "ta_session",
                    "value": account["session_value"],
                    "domain": "127.0.0.1",
                    "path": "/",
                    "expires": expires,
                    "httpOnly": True,
                    "secure": False,
                    "sameSite": "Lax",
                }],
                "origins": [{
                    "origin": origin,
                    "localStorage": [
                        {"name": "account_id", "value": account["account_id"]},
                        {"name": "username", "value": username},
                    ],
                }],
            }))

            session = FormatImporter.from_playwright_storagestate(str(storage_state_path))
            session["site_name"] = "account-server"
            session["auth_status"] = "logged_in"
            session.setdefault("metadata", {}).update({
                "session_id": account["account_id"],
                "site_name": "account-server",
            })
            (sessions_dir / f"{account['account_id']}.tokenade").write_text(json.dumps(session))

        control_plane = create_gateway_control_plane(parse_request_config({
            "version": "1",
            "operation": "gateway",
            "sessions": {"dir": str(sessions_dir), "pattern": "*.tokenade"},
            "gateway": {"host": "127.0.0.1", "port": 0, "backend": "cdp"},
            "routing": {"object": "session", "strategy": "round-robin"},
            "plugins": [],
        }))
        runtime_factory = FakeContextFactory()
        control_plane.runtime = GatewayRuntime(runtime_factory, target_url=origin)
        gateway_httpd = ThreadingHTTPServer(("127.0.0.1", 0), control_plane.make_handler())
        gateway_thread = threading.Thread(target=gateway_httpd.serve_forever, daemon=True)
        gateway_thread.start()
        base_url = f"http://127.0.0.1:{gateway_httpd.server_port}"

        try:
            with urllib.request.urlopen(f"{base_url}/status", timeout=5) as response:
                status = json.loads(response.read().decode("utf-8"))
            with urllib.request.urlopen(f"{base_url}/sessions", timeout=5) as response:
                sessions = json.loads(response.read().decode("utf-8"))["sessions"]

            routed_ids = [
                _gateway_post(base_url, "/route/next", {"scope": "activate-context"})["decision"]["session"]["id"]
                for _ in range(5)
            ]
            selected = _gateway_post(base_url, "/route/select", {"id": "acct-3", "scope": "activate-context"})
            with urllib.request.urlopen(f"{base_url}/contexts", timeout=5) as response:
                contexts = json.loads(response.read().decode("utf-8"))["contexts"]
        finally:
            gateway_httpd.shutdown()
            gateway_httpd.server_close()
            gateway_thread.join(timeout=5)
            control_plane.close()

        serialized_sessions = json.dumps(sessions)
        serialized_contexts = json.dumps(contexts)
        assert status["success"] is True
        assert status["session_count"] == 5
        assert [session["id"] for session in sessions] == expected_ids
        assert {session["site_name"] for session in sessions} == {"account-server"}
        assert {session["cookie_count"] for session in sessions} == {1}
        assert not any(value in serialized_sessions for value in expected_cookie_values)
        assert "account-1" not in serialized_sessions
        assert routed_ids == expected_ids
        assert selected["decision"]["session"]["id"] == "acct-3"
        assert len(contexts) == 5
        assert {tuple(context["origins"]) for context in contexts} == {(origin,)}
        assert not any(value in serialized_contexts for value in expected_cookie_values)
        assert sorted(runtime_factory.contexts) == expected_ids
        assert [runtime_factory.contexts[account_id].cookies[0]["value"] for account_id in expected_ids] == expected_cookie_values
        assert all(context.pages == [] for context in runtime_factory.contexts.values())
    finally:
        account_httpd.shutdown()
        account_httpd.server_close()
        account_thread.join(timeout=5)


def test_gateway_state_file_saves_and_restores_active_session(tmp_path):
    _write_session(tmp_path, "github.tokenade", site_name="github", metadata={"session_id": "github-stable"})
    _write_session(tmp_path, "discord.tokenade", site_name="discord", metadata={"session_id": "discord-stable"})
    state_file = tmp_path / "state" / "gateway_state.json"
    request = _request(tmp_path, {
        "gateway": {
            "host": "127.0.0.1",
            "port": 0,
            "backend": "cdp",
            "state_file": str(state_file),
        },
        "routing": {"object": "session", "strategy": "round-robin"},
    })

    control_plane = create_gateway_control_plane(request)
    try:
        assert control_plane.route_select({"id": "discord-stable"})["decision"]["session"]["id"] == "discord-stable"
    finally:
        control_plane.close()

    saved = json.loads(state_file.read_text())
    assert saved["active_session_id"] == "discord-stable"

    restored = create_gateway_control_plane(request)
    try:
        assert restored.status()["active_session"]["id"] == "discord-stable"
    finally:
        restored.close()


def test_gateway_webhook_failure_is_logged_not_raised(monkeypatch, tmp_path):
    _write_session(tmp_path, "github.tokenade", metadata={"session_id": "github-stable"})

    class ImmediateThread:
        def __init__(self, target, daemon=False, **kwargs):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    def fail_urlopen(*args, **kwargs):
        raise RuntimeError("webhook offline")

    monkeypatch.setattr("tokenade.core.gateway.server.threading.Thread", ImmediateThread)
    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)
    control_plane = create_gateway_control_plane(_request(tmp_path, {
        "gateway": {
            "host": "127.0.0.1",
            "port": 0,
            "backend": "cdp",
            "webhooks": {"on_select": "http://127.0.0.1:9/webhook"},
        },
        "routing": {"object": "session", "strategy": "round-robin"},
    }))

    try:
        control_plane.route_select({"id": "github-stable"})
    finally:
        control_plane.close()


def test_create_gateway_control_plane_returns_status(tmp_path):
    _write_session(tmp_path, "github.tokenade", metadata={"session_id": "github-stable"})

    control_plane = create_gateway_control_plane(_request(tmp_path))
    status = control_plane.status()

    assert status["success"] is True
    assert status["operation"] == "gateway"
    assert status["active_session"] is None
    assert status["session_count"] == 1
    assert status["routing"]["strategy"] == "round-robin"


def test_gateway_sessions_pattern_accepts_regex(tmp_path):
    _write_session(tmp_path, "google-default.tokenade", site_name="google")
    _write_session(tmp_path, "2-google-default.tokenade", site_name="google")
    _write_session(tmp_path, "github-default.tokenade", site_name="github")

    request = _request(tmp_path, {"sessions": {"dir": str(tmp_path), "pattern": r"(^|-)google-default\.tokenade$"}})
    control_plane = create_gateway_control_plane(request)

    try:
        assert [session.site_name for session in control_plane.sessions] == ["google", "google"]
    finally:
        control_plane.close()


def test_gateway_refresh_scheduler_fires_started_event(tmp_path):
    _write_session(tmp_path, "github.tokenade", metadata={"session_id": "github-stable"})
    request = _request(tmp_path, {"plugins": [{
        "name": "oauth2",
        "roles": {"session_refresher": {"enabled": True, "refresh_interval_seconds": 3600}},
        "config": {},
    }]})

    control_plane = create_gateway_control_plane(request)

    try:
        tasks = control_plane.scheduler.get_tasks()
        assert len(tasks) == 1
        assert tasks[0].event_type is EventType.REFRESH_STARTED
    finally:
        control_plane.close()


def test_gateway_refresh_task_executes_refresher_and_persists_session(tmp_path, monkeypatch):
    session_path = _write_session(tmp_path, "github.tokenade", metadata={"session_id": "github-stable"})
    request = _request(tmp_path, {"plugins": [{
        "name": "oauth2",
        "roles": {"session_refresher": {"enabled": True, "refresh_interval_seconds": 3600}},
        "config": {"account": "test-account"},
    }]})
    control_plane = create_gateway_control_plane(request)
    refreshed = {"version": "1.0", "site_name": "github", "cookies": [], "metadata": {"refreshed": True}}
    refresher = SimpleNamespace(
        can_refresh=lambda session: True,
        refresh=lambda session, credentials: SimpleNamespace(success=True, data={"session": refreshed}),
    )
    loader = SimpleNamespace(get_refresher=lambda name: refresher)
    monkeypatch.setattr(
        "tokenade.core.integration.plugin_loader.get_or_create_shared_loader",
        lambda: loader,
    )

    try:
        control_plane._on_refresh_task_fired(SimpleNamespace(data={
            "session_path": str(session_path),
            "plugin_name": "oauth2",
        }))
        assert json.loads(session_path.read_text()) == refreshed
    finally:
        control_plane.close()


def test_health_check_callback_reschedules_after_check_failure(tmp_path, monkeypatch):
    _write_session(tmp_path, "github.tokenade")
    request = _request(tmp_path, {"routing": {
        "object": "session",
        "strategy": "round-robin",
        "health_check_interval_seconds": 10,
    }})
    control_plane = create_gateway_control_plane(request)
    scheduled = []

    try:
        monkeypatch.setattr(control_plane, "_check_all_sessions_health", lambda: (_ for _ in ()).throw(RuntimeError("probe failed")))
        monkeypatch.setattr(control_plane, "_start_health_monitor", lambda: scheduled.append(True))
        control_plane._health_check_callback()
        assert scheduled == [True]
    finally:
        control_plane.close()


def test_auto_rotate_callback_does_not_create_duplicate_timers(tmp_path, monkeypatch):
    _write_session(tmp_path, "github.tokenade")
    control_plane = create_gateway_control_plane(_request(tmp_path))
    scheduled = []

    try:
        monkeypatch.setattr(control_plane, "_auto_rotate_next", lambda: None)
        monkeypatch.setattr(control_plane, "_start_auto_rotate_timer", lambda: scheduled.append(True))

        control_plane._auto_rotate_callback()

        assert scheduled == [True]
    finally:
        control_plane.close()


def test_sessions_endpoint_contract_is_sanitized(tmp_path):
    _write_session(tmp_path, "github.tokenade", metadata={"session_id": "github-stable", "private": "secret"})

    control_plane = create_gateway_control_plane(_request(tmp_path))
    sessions = control_plane.session_list()["sessions"]

    assert sessions[0]["id"] == "github-stable"
    assert sessions[0]["cookie_count"] == 1
    serialized = json.dumps(sessions)
    assert "secret-cookie-value" not in serialized
    assert "secret-storage-value" not in serialized
    assert "private" not in sessions[0]["metadata"]


def test_route_next_changes_active_session_by_strategy(tmp_path):
    _write_session(tmp_path, "github.tokenade", site_name="github")
    _write_session(tmp_path, "discord.tokenade", site_name="discord")

    request = _request(tmp_path, {"routing": {"object": "session", "strategy": "round-robin"}})
    control_plane = create_gateway_control_plane(request)
    first = control_plane.route_next()["decision"]["session"]["site_name"]
    second = control_plane.route_next()["decision"]["session"]["site_name"]

    assert {first, second} == {"discord", "github"}
    assert first != second
    assert control_plane.active_session.site_name == second


def test_route_select_accepts_id_path_or_site_and_rejects_invalid(tmp_path):
    path = _write_session(tmp_path, "github.tokenade", site_name="github", metadata={"session_id": "github-stable"})

    control_plane = create_gateway_control_plane(_request(tmp_path))

    assert control_plane.route_select({"id": "github-stable"})["decision"]["reason"] == "manual-select"
    assert control_plane.route_select({"path": str(path.resolve())})["decision"]["session"]["site_name"] == "github"
    assert control_plane.route_select({"site": "github"})["decision"]["session"]["id"] == "github-stable"
    with pytest.raises(GatewayConfigError, match="no session matched selector"):
        control_plane.route_select({"id": "missing"})


def test_gateway_request_rejects_wrong_operation(tmp_path):
    request = parse_request_config({"operation": "run", "plugins": []})

    with pytest.raises(GatewayConfigError, match="operation must be 'gateway'"):
        create_gateway_control_plane(request)


def test_gateway_request_enforces_switch_interval_floor(tmp_path):
    _write_session(tmp_path, "github.tokenade")

    request = _request(tmp_path, {"routing": {"object": "session", "strategy": "round-robin", "switch_interval_seconds": 4}})
    with pytest.raises(GatewayConfigError, match="switch_interval_seconds must be >= 5"):
        create_gateway_control_plane(request)


def test_gateway_http_status_and_route_next(tmp_path):
    _write_session(tmp_path, "github.tokenade", metadata={"session_id": "github-stable"})
    control_plane = create_gateway_control_plane(_request(tmp_path))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), control_plane.make_handler())
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{httpd.server_port}"

    try:
        with urllib.request.urlopen(f"{base_url}/status", timeout=5) as response:
            status = json.loads(response.read().decode("utf-8"))
        request = urllib.request.Request(f"{base_url}/route/next", data=b"{}", method="POST")
        with urllib.request.urlopen(request, timeout=5) as response:
            next_route = json.loads(response.read().decode("utf-8"))
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)

    assert status["success"] is True
    assert status["session_count"] == 1
    assert next_route["success"] is True
    assert next_route["decision"]["session"]["id"] == "github-stable"


def test_control_plane_runtime_context_endpoints(tmp_path):
    _write_session(tmp_path, "github.tokenade", metadata={"session_id": "github-stable"})
    runtime = GatewayRuntime(FakeContextFactory())
    control_plane = create_gateway_control_plane(_request(tmp_path))
    control_plane.runtime = runtime

    route = control_plane.route_next({"scope": "activate-context"})
    contexts = control_plane.context_list()
    tab = control_plane.tabs_new()
    drain = control_plane.contexts_drain()

    assert route["runtime_context"]["session"]["id"] == "github-stable"
    assert contexts["runtime_enabled"] is True
    assert len(contexts["contexts"]) == 1
    assert tab["runtime"]["success"] is True
    assert drain["runtime"]["closed"] == []


def test_route_scope_future_only_does_not_activate_runtime(tmp_path):
    _write_session(tmp_path, "github.tokenade", metadata={"session_id": "github-stable"})
    runtime = GatewayRuntime(FakeContextFactory())
    control_plane = create_gateway_control_plane(_request(tmp_path, {"routing": {"default_scope": "future-only"}}))
    control_plane.runtime = runtime

    route = control_plane.route_next()

    assert route["runtime_context"] is None
    assert control_plane.context_list()["contexts"] == []


def test_route_default_scope_prepares_context(tmp_path):
    _write_session(tmp_path, "github.tokenade", metadata={"session_id": "github-stable"})
    runtime = GatewayRuntime(FakeContextFactory())
    control_plane = create_gateway_control_plane(_request(tmp_path))
    control_plane.runtime = runtime

    route = control_plane.route_next()

    assert route["runtime_context"]["session"]["id"] == "github-stable"
    assert control_plane.context_list()["contexts"][0]["session"]["id"] == "github-stable"


def test_route_scope_open_target_opens_with_window_policy(tmp_path):
    _write_session(tmp_path, "github.tokenade", metadata={"session_id": "github-stable"})
    runtime = GatewayRuntime(FakeContextFactory())
    control_plane = create_gateway_control_plane(_request(tmp_path))
    control_plane.runtime = runtime

    route = control_plane.route_next({
        "scope": "open-target",
        "url": "https://github.com",
        "window_policy": "reuse-active-window",
    })

    assert route["runtime_context"]["success"] is True
    assert route["runtime_context"]["window_policy"] == "reuse-active-window"
    assert route["runtime_context"]["context"]["page_count"] == 1


def test_context_lease_preserves_inactive_context_from_drain(tmp_path):
    _write_session(tmp_path, "github.tokenade", site_name="github")
    _write_session(tmp_path, "discord.tokenade", site_name="discord")
    runtime = GatewayRuntime(FakeContextFactory())
    control_plane = create_gateway_control_plane(_request(tmp_path, {"routing": {"object": "session", "strategy": "round-robin"}}))
    control_plane.runtime = runtime

    lease = control_plane.contexts_lease({"site": "discord", "ttl_seconds": 60, "leased_by": "test"})
    control_plane.route_select({"site": "github", "scope": "activate-context"})
    drain = runtime.drain_inactive()
    released = control_plane.contexts_release({"lease_id": lease["runtime"]["lease_id"]})
    drained_after_release = runtime.drain_inactive()

    assert drain["closed"] == []
    assert len(drain["preserved"]) == 1
    assert released["runtime"]["context_id"] == drain["preserved"][0]
    assert drained_after_release["closed"] == drain["preserved"]


def test_tabs_new_url_uses_active_session_not_url_as_selector(tmp_path):
    _write_session(tmp_path, "github.tokenade", metadata={"session_id": "github-stable"})
    runtime = GatewayRuntime(FakeContextFactory())
    control_plane = create_gateway_control_plane(_request(tmp_path))
    control_plane.runtime = runtime

    control_plane.route_select({"id": "github-stable", "scope": "activate-context"})
    tab = control_plane.tabs_new({"url": "https://github.com"})
    reused = control_plane.tabs_new({"url": "https://github.com/settings"})
    new_tab = control_plane.tabs_new({"url": "https://github.com/new", "window_policy": "new-tab"})

    assert tab["runtime"]["success"] is True
    assert tab["runtime"]["page_reused"] is False
    assert reused["runtime"]["page_reused"] is True
    assert reused["runtime"]["context"]["page_count"] == 1
    assert new_tab["runtime"]["page_reused"] is False
    assert new_tab["runtime"]["context"]["page_count"] == 2


def test_gateway_http_runtime_contexts(tmp_path):
    _write_session(tmp_path, "github.tokenade", metadata={"session_id": "github-stable"})
    runtime = GatewayRuntime(FakeContextFactory())
    control_plane = create_gateway_control_plane(_request(tmp_path))
    control_plane.runtime = runtime
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), control_plane.make_handler())
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{httpd.server_port}"

    try:
        next_request = urllib.request.Request(f"{base_url}/route/next", data=b'{"scope":"activate-context"}', method="POST")
        with urllib.request.urlopen(next_request, timeout=5) as response:
            next_route = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/contexts", timeout=5) as response:
            contexts = json.loads(response.read().decode("utf-8"))
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)

    assert next_route["runtime_context"]["session"]["id"] == "github-stable"
    assert contexts["runtime_enabled"] is True
    assert len(contexts["contexts"]) == 1


def test_gateway_serve_forever_uses_single_threaded_http_server(monkeypatch, tmp_path):
    _write_session(tmp_path, "github.tokenade", metadata={"session_id": "github-stable"})
    control_plane = create_gateway_control_plane(_request(tmp_path))
    captured = {}

    class Server:
        def __init__(self, address, handler):
            captured["class"] = self.__class__
            captured["address"] = address

        def serve_forever(self):
            raise KeyboardInterrupt()

        def server_close(self):
            captured["closed"] = True

    class FakeHTTPServer(Server):
        pass

    monkeypatch.setattr("tokenade.core.gateway.server.HTTPServer", FakeHTTPServer)

    try:
        control_plane.serve_forever()
    except KeyboardInterrupt:
        pass

    assert captured["class"] is FakeHTTPServer
    assert captured["address"] == ("127.0.0.1", 0)
    assert captured["closed"] is True
    assert HTTPServer is not ThreadingHTTPServer


def test_gateway_control_plane_shutdown_stops_server(monkeypatch, tmp_path):
    _write_session(tmp_path, "github.tokenade", metadata={"session_id": "github-stable"})
    control_plane = create_gateway_control_plane(_request(tmp_path))

    class Server:
        def __init__(self, address, handler):
            self.shutdown_called = False

        def serve_forever(self):
            pass

        def shutdown(self):
            self.shutdown_called = True

        def server_close(self):
            pass

    monkeypatch.setattr("tokenade.core.gateway.server.HTTPServer", Server)
    control_plane.serve_forever()

    assert getattr(control_plane, "_server", None) is None


def test_gateway_status_includes_redacted_proxy_provider(monkeypatch, tmp_path):
    _write_session(tmp_path, "github.tokenade", metadata={
        "session_id": "github-stable",
        "source_network": {"approx_country": "US", "raw_ip_stored": False},
    })

    class Proxy:
        def to_dict(self, show_secrets=False):
            assert show_secrets is False
            return {"server": "http://proxy.example:8080", "username": "us***", "password": "***"}

    class Resolver:
        def resolve(self, plugin, session_metadata=None, source_network=None):
            assert plugin.name == "brightdata"
            assert source_network["approx_country"] == "US"
            assert "github" in session_metadata["sites"]
            return Proxy()

    monkeypatch.setattr("tokenade.core.gateway.server.ProxyProviderResolver", lambda: Resolver())
    request = _request(tmp_path, {"plugins": [{
        "name": "brightdata",
        "roles": {"proxy_provider": {"mode": "sticky", "match_source_location": True}},
        "config": {"zone": "residential"},
    }]})

    status = create_gateway_control_plane(request).status()

    assert status["upstream_proxies"] == [{
        "plugin_name": "brightdata",
        "proxy": {"server": "http://proxy.example:8080", "username": "us***", "password": "***"},
    }]


def test_gateway_health_probe_timeout_config(tmp_path):
    """Probe timeout is configurable via gateway.health.probe_timeout_seconds."""
    _write_session(tmp_path, "github.tokenade")
    request = _request(tmp_path, {
        "gateway": {
            "host": "127.0.0.1", "port": 0, "backend": "cdp",
            "health": {"probe_timeout_seconds": 3.5, "probe_min_interval_seconds": 15},
        },
    })

    control_plane = create_gateway_control_plane(request)
    try:
        assert control_plane._probe_timeout == 3.5
        assert control_plane._probe_min_interval == 15.0
    finally:
        control_plane.close()


def test_gateway_health_probe_timeout_default(tmp_path):
    """Probe timeout defaults to 8s when not configured."""
    _write_session(tmp_path, "github.tokenade")
    control_plane = create_gateway_control_plane(_request(tmp_path))
    try:
        assert control_plane._probe_timeout == 8.0
        assert control_plane._probe_min_interval == 60.0
    finally:
        control_plane.close()


def test_gateway_probe_rate_limits_same_domain(tmp_path, monkeypatch):
    """Probes to the same domain are rate-limited by _probe_min_interval."""
    _write_session(
        tmp_path,
        "github.tokenade",
        site_name="github",
        metadata={"site_handler": {"session_check_url": "https://github.com/settings/profile"}},
    )
    control_plane = create_gateway_control_plane(_request(tmp_path))
    try:
        # Force a small min interval and record a recent probe for github.com
        control_plane._probe_min_interval = 30.0
        control_plane._probe_last_run["github.com"] = time.time()
        # _probe_session_health should no-op due to rate limit
        before = dict(control_plane._probe_last_run)
        session = control_plane.sessions[0]
        control_plane._probe_session_health(session, True)
        # No new entry added; existing entry unchanged
        assert control_plane._probe_last_run == before
    finally:
        control_plane.close()


def test_gateway_probe_session_health_emits_degraded_on_false(tmp_path, monkeypatch):
    """HEALTH_DEGRADED emitted when probe returns False."""
    _write_session(
        tmp_path,
        "github.tokenade",
        site_name="github",
        metadata={"site_handler": {"session_check_url": "https://github.com/settings/profile"}},
    )
    control_plane = create_gateway_control_plane(_request(tmp_path))
    try:
        # Patch SessionProbe.probe to return False
        from tokenade.core.refresh import health_checker
        monkeypatch.setattr(health_checker.SessionProbe, "probe", staticmethod(lambda *a, **k: False))
        control_plane._probe_last_run.clear()
        events = []
        control_plane.event_bus.on(EventType.HEALTH_DEGRADED, lambda e: events.append(e.data))
        session = control_plane.sessions[0]
        object.__setattr__(session, '_healthy', True)
        object.__setattr__(session, '_health_failures', 0)
        # Force a low unhealthy_threshold so the probe failure crosses it
        object.__setattr__(control_plane.routing_config, 'unhealthy_threshold', 1)
        control_plane._probe_session_health(session, True)
        # Allow async handler to run
        time.sleep(0.1)
        # Failures incremented
        assert getattr(session, '_health_failures', 0) >= 1
        assert len(events) == 1
        assert events[0]["probe"] == "server_invalidated"
    finally:
        control_plane.close()


def test_gateway_probe_session_health_emits_recovered_on_true(tmp_path, monkeypatch):
    """HEALTH_RECOVERED emitted when probe returns True after degraded."""
    _write_session(
        tmp_path,
        "github.tokenade",
        site_name="github",
        metadata={"site_handler": {"session_check_url": "https://github.com/settings/profile"}},
    )
    control_plane = create_gateway_control_plane(_request(tmp_path))
    try:
        from tokenade.core.refresh import health_checker
        monkeypatch.setattr(health_checker.SessionProbe, "probe", staticmethod(lambda *a, **k: True))
        control_plane._probe_last_run.clear()
        events = []
        control_plane.event_bus.on(EventType.HEALTH_RECOVERED, lambda e: events.append(e.data))
        session = control_plane.sessions[0]
        object.__setattr__(session, '_healthy', False)
        object.__setattr__(session, '_health_failures', 2)
        control_plane._probe_session_health(session, False)
        time.sleep(0.1)
        assert len(events) == 1
        assert events[0]["probe"] == "server_valid"
    finally:
        control_plane.close()
