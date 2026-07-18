"""Tests for hidden gateway control-plane contracts."""

import json
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from tokenade.core.gateway.server import GatewayConfigError, create_gateway_control_plane
from tokenade.core.gateway.runtime import GatewayRuntime
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


def test_create_gateway_control_plane_returns_status(tmp_path):
    _write_session(tmp_path, "github.tokenade", metadata={"session_id": "github-stable"})

    control_plane = create_gateway_control_plane(_request(tmp_path))
    status = control_plane.status()

    assert status["success"] is True
    assert status["operation"] == "gateway"
    assert status["active_session"] is None
    assert status["session_count"] == 1
    assert status["routing"]["strategy"] == "round-robin"


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

    prewarm = control_plane.contexts_prewarm()
    route = control_plane.route_next()
    contexts = control_plane.context_list()
    tab = control_plane.tabs_new()
    drain = control_plane.contexts_drain()

    assert prewarm["runtime"]["context_count"] == 1
    assert route["runtime_context"]["session"]["id"] == "github-stable"
    assert contexts["runtime_enabled"] is True
    assert len(contexts["contexts"]) == 1
    assert tab["runtime"]["success"] is True
    assert drain["runtime"]["closed"] == []


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
        prewarm_request = urllib.request.Request(f"{base_url}/contexts/prewarm", data=b"{}", method="POST")
        with urllib.request.urlopen(prewarm_request, timeout=5) as response:
            prewarm = json.loads(response.read().decode("utf-8"))
        next_request = urllib.request.Request(f"{base_url}/route/next", data=b"{}", method="POST")
        with urllib.request.urlopen(next_request, timeout=5) as response:
            next_route = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(f"{base_url}/contexts", timeout=5) as response:
            contexts = json.loads(response.read().decode("utf-8"))
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)

    assert prewarm["runtime"]["context_count"] == 1
    assert next_route["runtime_context"]["session"]["id"] == "github-stable"
    assert contexts["runtime_enabled"] is True
    assert len(contexts["contexts"]) == 1
