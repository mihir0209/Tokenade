"""Comprehensive tests for API server endpoints using pytest-aiohttp."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig


@pytest.fixture
def sessions_dir(tmp_path):
    return str(tmp_path)


@pytest.fixture
def server(sessions_dir):
    config = APIServerConfig(sessions_dir=sessions_dir)
    return TokenadeAPIServer(config)


@pytest.fixture
def server_with_key(tmp_path):
    config = APIServerConfig(sessions_dir=str(tmp_path), api_key="secret")
    return TokenadeAPIServer(config)


@pytest.fixture
def app(server):
    return server.create_app()


@pytest.fixture
def app_with_key(server_with_key):
    return server_with_key.create_app()


class TestAPIServerConfig:
    def test_defaults(self):
        config = APIServerConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 9224
        assert config.api_key is None
        assert config.cors_origins == ["*"]

    def test_custom(self):
        config = APIServerConfig(host="0.0.0.0", port=8080, api_key="secret")
        assert config.host == "0.0.0.0"
        assert config.api_key == "secret"


class TestCheckAuth:
    def test_no_api_key(self, server):
        request = MagicMock()
        request.headers = {}
        assert server._check_auth(request) is True

    def test_api_key_required_no_header(self, server_with_key):
        request = MagicMock()
        request.headers = {}
        assert server_with_key._check_auth(request) is False

    def test_api_key_bearer(self, server_with_key):
        request = MagicMock()
        request.headers = {"Authorization": "Bearer secret"}
        assert server_with_key._check_auth(request) is True

    def test_api_key_bearer_wrong(self, server_with_key):
        request = MagicMock()
        request.headers = {"Authorization": "Bearer wrong"}
        assert server_with_key._check_auth(request) is False

    def test_api_key_x_header(self, server_with_key):
        request = MagicMock()
        request.headers = {"X-API-Key": "secret"}
        assert server_with_key._check_auth(request) is True

    def test_api_key_x_header_wrong(self, server_with_key):
        request = MagicMock()
        request.headers = {"X-API-Key": "wrong"}
        assert server_with_key._check_auth(request) is False


class TestGetEndpoints:
    def test_endpoints_list(self, server):
        endpoints = server.get_endpoints()
        paths = [e["path"] for e in endpoints]
        assert "/api/health" in paths
        assert "/api/sessions" in paths
        assert "/api/sessions/{id}" in paths
        assert "/api/proxy/status" in paths
        assert "/api/export" in paths
        assert "/api/share" in paths
        assert "/api/monitor/status" in paths
        assert "/api/monitor/sessions/{id}" in paths
        assert "/api/monitor/sessions/{id}/cookies" in paths
        assert len(endpoints) == 10


class TestJSONResponse:
    def test_json_response_cors(self, server):
        resp = server._json_response({"ok": True})
        assert resp.headers["Access-Control-Allow-Origin"] == "*"
        assert "Authorization" in resp.headers["Access-Control-Allow-Headers"]

    def test_error_response(self, server):
        resp = server._error_response("not found", 404)
        assert resp.status == 404


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_check(self, aiohttp_client, app):
        client = await aiohttp_client(app)
        resp = await client.get("/api/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "sessions_dir" in data

    @pytest.mark.asyncio
    async def test_health_cors(self, aiohttp_client, app):
        client = await aiohttp_client(app)
        resp = await client.get("/api/health")
        assert resp.headers.get("Access-Control-Allow-Origin") == "*"


class TestSessionsEndpoint:
    @pytest.mark.asyncio
    async def test_list_empty(self, aiohttp_client, app):
        client = await aiohttp_client(app)
        resp = await client.get("/api/sessions")
        assert resp.status == 200
        data = await resp.json()
        assert data["sessions"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_with_files(self, aiohttp_client, sessions_dir, app):
        Path(sessions_dir, "test_session.tokenade").write_text(
            json.dumps({"cookies": [{"name": "a", "value": "1"}], "site_name": "test"})
        )
        client = await aiohttp_client(app)
        resp = await client.get("/api/sessions")
        assert resp.status == 200
        data = await resp.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_auth_required(self, aiohttp_client, app_with_key):
        client = await aiohttp_client(app_with_key)
        resp = await client.get("/api/sessions")
        assert resp.status == 401

        resp = await client.get("/api/sessions", headers={"Authorization": "Bearer secret"})
        assert resp.status == 200


class TestSessionGetEndpoint:
    @pytest.mark.asyncio
    async def test_not_found(self, aiohttp_client, app):
        client = await aiohttp_client(app)
        resp = await client.get("/api/sessions/nonexistent")
        assert resp.status == 404

    @pytest.mark.asyncio
    async def test_found(self, aiohttp_client, sessions_dir, app):
        Path(sessions_dir, "test_session.json").write_text(
            json.dumps({"cookies": [{"name": "a", "value": "1"}], "site_name": "test"})
        )
        client = await aiohttp_client(app)
        resp = await client.get("/api/sessions/test_session")
        assert resp.status == 200
        data = await resp.json()
        assert data["id"] == "test_session"
        assert "session" in data


class TestSessionDeleteEndpoint:
    @pytest.mark.asyncio
    async def test_not_found(self, aiohttp_client, app):
        client = await aiohttp_client(app)
        resp = await client.delete("/api/sessions/nonexistent")
        assert resp.status == 404

    @pytest.mark.asyncio
    async def test_found(self, aiohttp_client, sessions_dir, app):
        f = Path(sessions_dir, "to_delete.json")
        f.write_text(json.dumps({"cookies": []}))
        client = await aiohttp_client(app)
        resp = await client.delete("/api/sessions/to_delete")
        assert resp.status == 200
        data = await resp.json()
        assert data["deleted"] is True
        assert not f.exists()


class TestProxyStatusEndpoint:
    @pytest.mark.asyncio
    async def test_proxy_status(self, aiohttp_client, app):
        client = await aiohttp_client(app)
        resp = await client.get("/api/proxy/status")
        assert resp.status == 200
        data = await resp.json()
        assert data["proxy_running"] is False


class TestExportEndpoint:
    @pytest.mark.asyncio
    async def test_invalid_json(self, aiohttp_client, app):
        client = await aiohttp_client(app)
        resp = await client.post("/api/export", data="not json")
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_unauthorized(self, aiohttp_client, app_with_key):
        client = await aiohttp_client(app_with_key)
        resp = await client.post("/api/export", json={"browser": "chrome"})
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_success(self, aiohttp_client, app):
        mock_result = MagicMock(returncode=0, stdout="Exported", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            client = await aiohttp_client(app)
            resp = await client.post("/api/export", json={
                "browser": "chrome",
                "domains": ["github.com"],
                "output": "/tmp/test.tokenade",
            })
            assert resp.status == 200
            data = await resp.json()
            assert data["success"] is True

    @pytest.mark.asyncio
    async def test_failure(self, aiohttp_client, app):
        mock_result = MagicMock(returncode=1, stdout="", stderr="No browser found")
        with patch("subprocess.run", return_value=mock_result):
            client = await aiohttp_client(app)
            resp = await client.post("/api/export", json={"browser": "chrome"})
            assert resp.status == 500


class TestShareEndpoint:
    @pytest.mark.asyncio
    async def test_invalid_json(self, aiohttp_client, app):
        client = await aiohttp_client(app)
        resp = await client.post("/api/share", data="not json")
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_missing_session_file(self, aiohttp_client, app):
        client = await aiohttp_client(app)
        resp = await client.post("/api/share", json={"password": "test"})
        assert resp.status == 400
        data = await resp.json()
        assert "session_file required" in data["error"]

    @pytest.mark.asyncio
    async def test_success(self, aiohttp_client, app):
        mock_result = MagicMock(returncode=0, stdout="http://share.link/abc", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            client = await aiohttp_client(app)
            resp = await client.post("/api/share", json={
                "session_file": "/tmp/test.tokenade",
                "password": "secret",
                "expiry_hours": 48,
            })
            assert resp.status == 200
            data = await resp.json()
            assert data["success"] is True


class TestMonitorEndpoints:
    @pytest.mark.asyncio
    async def test_status_no_monitor(self, aiohttp_client, app, server):
        client = await aiohttp_client(app)
        resp = await client.get("/api/monitor/status")
        assert resp.status == 200
        data = await resp.json()
        assert data["monitoring"] is False

    @pytest.mark.asyncio
    async def test_session_no_monitor(self, aiohttp_client, app):
        client = await aiohttp_client(app)
        resp = await client.get("/api/monitor/sessions/test")
        assert resp.status == 404

    @pytest.mark.asyncio
    async def test_cookies_no_monitor(self, aiohttp_client, app):
        client = await aiohttp_client(app)
        resp = await client.get("/api/monitor/sessions/test/cookies")
        assert resp.status == 404

    @pytest.mark.asyncio
    async def test_status_with_monitor(self, aiohttp_client, app, server):
        mock_monitor = MagicMock()
        mock_monitor.get_summary.return_value = {"sessions_monitored": 2, "total_cookies": 50}
        server._monitor = mock_monitor
        client = await aiohttp_client(app)
        resp = await client.get("/api/monitor/status")
        assert resp.status == 200
        data = await resp.json()
        assert data["monitoring"] is True
        assert data["sessions_monitored"] == 2

    @pytest.mark.asyncio
    async def test_session_with_monitor(self, aiohttp_client, app, server):
        mock_status = MagicMock()
        mock_status.session_id = "s1"
        mock_status.site_name = "github.com"
        mock_status.health_score = 0.95
        mock_status.cookie_count = 10
        mock_status.healthy_cookies = 8
        mock_status.warning_cookies = 1
        mock_status.expired_cookies = 1
        mock_status.last_check = "2025-01-01"
        mock_status.last_refresh = None
        mock_status.refresh_count = 0
        mock_status.issues = []
        mock_status.recommendations = []
        mock_status.cookies = []

        mock_monitor = MagicMock()
        mock_monitor.get_status.return_value = mock_status
        server._monitor = mock_monitor

        client = await aiohttp_client(app)
        resp = await client.get("/api/monitor/sessions/s1")
        assert resp.status == 200
        data = await resp.json()
        assert data["session_id"] == "s1"
        assert data["health_score"] == 0.95

    @pytest.mark.asyncio
    async def test_session_not_found_with_monitor(self, aiohttp_client, app, server):
        mock_monitor = MagicMock()
        mock_monitor.get_status.return_value = None
        server._monitor = mock_monitor
        client = await aiohttp_client(app)
        resp = await client.get("/api/monitor/sessions/missing")
        assert resp.status == 404

    @pytest.mark.asyncio
    async def test_cookies_with_data(self, aiohttp_client, app, server):
        mock_cookie = MagicMock()
        mock_cookie.name = "sid"
        mock_cookie.domain = ".github.com"
        mock_cookie.expires = 1893456000
        mock_cookie.remaining_seconds = 86400
        mock_cookie.health = "healthy"
        mock_cookie.is_secure = True
        mock_cookie.is_http_only = True
        mock_cookie.same_site = "Lax"

        mock_status = MagicMock()
        mock_status.cookies = [mock_cookie]

        mock_monitor = MagicMock()
        mock_monitor.get_status.return_value = mock_status
        server._monitor = mock_monitor

        client = await aiohttp_client(app)
        resp = await client.get("/api/monitor/sessions/s1/cookies")
        assert resp.status == 200
        data = await resp.json()
        assert len(data["cookies"]) == 1
        assert data["cookies"][0]["name"] == "sid"

    @pytest.mark.asyncio
    async def test_cookies_not_found(self, aiohttp_client, app, server):
        mock_monitor = MagicMock()
        mock_monitor.get_status.return_value = None
        server._monitor = mock_monitor
        client = await aiohttp_client(app)
        resp = await client.get("/api/monitor/sessions/missing/cookies")
        assert resp.status == 404


class TestDashboardEndpoint:
    @pytest.mark.asyncio
    async def test_root_serves_html(self, aiohttp_client, app):
        client = await aiohttp_client(app)
        resp = await client.get("/")
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_dashboard_slash(self, aiohttp_client, app):
        client = await aiohttp_client(app)
        resp = await client.get("/dashboard/")
        assert resp.status == 200


class TestOPTIONS:
    @pytest.mark.asyncio
    async def test_options_returns_204(self, aiohttp_client, app):
        client = await aiohttp_client(app)
        resp = await client.options("/api/sessions")
        assert resp.status == 204
