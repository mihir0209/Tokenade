"""
Tests for API server monitor endpoints — events, start, stop.
"""
import time
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config():
    return APIServerConfig(api_key="test-key")


@pytest.fixture
def server(config):
    return TokenadeAPIServer(config)


@pytest.fixture
def mock_monitor():
    monitor = MagicMock()
    monitor.get_summary.return_value = {
        "total_sessions": 2,
        "total_cookies": 50,
        "overall_health": 85.0,
    }
    monitor.get_status.return_value = MagicMock(
        session_id="s1",
        site_name="example.com",
        health_score=90.0,
        cookie_count=25,
        healthy_cookies=20,
        warning_cookies=3,
        expired_cookies=2,
        last_check=time.time(),
        last_refresh=None,
        refresh_count=0,
        issues=["Cookie 'sid' missing Secure flag"],
        recommendations=["Cookie 'sid' has SameSite=None"],
        cookies=[
            MagicMock(
                name="sid", domain=".example.com", health="healthy",
                remaining_seconds=3600.0, is_secure=True,
                is_http_only=True, same_site="Lax", expires=time.time() + 3600,
            ),
        ],
    )
    monitor.get_event_history.return_value = [
        {
            "timestamp": time.time(),
            "session_id": "s1",
            "event_type": "health_change",
            "message": "Health changed",
            "health_score": 90.0,
            "metadata": {},
        },
    ]
    return monitor


# ---------------------------------------------------------------------------
# _handle_monitor_events
# ---------------------------------------------------------------------------

class TestHandleMonitorEvents:
    @pytest.mark.asyncio
    async def test_no_auth(self, aiohttp_client):
        server = TokenadeAPIServer(APIServerConfig(api_key="wrong"))
        app = server.create_app()
        client = await aiohttp_client(app)
        resp = await client.get("/api/monitor/events")
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_no_monitor(self, aiohttp_client):
        server = TokenadeAPIServer(APIServerConfig())
        app = server.create_app()
        client = await aiohttp_client(app)
        resp = await client.get("/api/monitor/events")
        assert resp.status == 200
        data = await resp.json()
        assert data["events"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_with_monitor(self, aiohttp_client, mock_monitor):
        server = TokenadeAPIServer(APIServerConfig())
        server._monitor = mock_monitor
        app = server.create_app()
        client = await aiohttp_client(app)
        resp = await client.get("/api/monitor/events?limit=10")
        assert resp.status == 200
        data = await resp.json()
        assert data["total"] == 1
        assert data["events"][0]["event_type"] == "health_change"


# ---------------------------------------------------------------------------
# _handle_monitor_start
# ---------------------------------------------------------------------------

class TestHandleMonitorStart:
    @pytest.mark.asyncio
    async def test_no_auth(self, aiohttp_client):
        server = TokenadeAPIServer(APIServerConfig(api_key="wrong"))
        app = server.create_app()
        client = await aiohttp_client(app)
        resp = await client.post("/api/monitor/start", json={})
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_start_default(self, aiohttp_client, tmp_path):
        server = TokenadeAPIServer(APIServerConfig())
        app = server.create_app()
        client = await aiohttp_client(app)
        resp = await client.post("/api/monitor/start", json={
            "sessions_dir": str(tmp_path),
            "interval": 30,
        })
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert data["interval"] == 30

        # Cleanup
        if server._monitor:
            server._monitor.stop()

    @pytest.mark.asyncio
    async def test_start_with_sessions(self, aiohttp_client, tmp_path):
        # Create a session file
        import json
        session = {"cookies": [{"name": "c1", "domain": ".x.com", "expires": time.time() + 3600}]}
        (tmp_path / "test.tokenade").write_text(json.dumps(session))

        server = TokenadeAPIServer(APIServerConfig())
        app = server.create_app()
        client = await aiohttp_client(app)
        resp = await client.post("/api/monitor/start", json={
            "sessions_dir": str(tmp_path),
        })
        assert resp.status == 200
        data = await resp.json()
        assert data["sessions_monitored"] == 1

        if server._monitor:
            server._monitor.stop()


# ---------------------------------------------------------------------------
# _handle_monitor_stop
# ---------------------------------------------------------------------------

class TestHandleMonitorStop:
    @pytest.mark.asyncio
    async def test_no_auth(self, aiohttp_client):
        server = TokenadeAPIServer(APIServerConfig(api_key="wrong"))
        app = server.create_app()
        client = await aiohttp_client(app)
        resp = await client.post("/api/monitor/stop")
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_stop_no_monitor(self, aiohttp_client):
        server = TokenadeAPIServer(APIServerConfig())
        app = server.create_app()
        client = await aiohttp_client(app)
        resp = await client.post("/api/monitor/stop")
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_stop_with_monitor(self, aiohttp_client, mock_monitor):
        server = TokenadeAPIServer(APIServerConfig())
        server._monitor = mock_monitor
        app = server.create_app()
        client = await aiohttp_client(app)
        resp = await client.post("/api/monitor/stop")
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        mock_monitor.stop.assert_called_once()
        assert server._monitor is None


# ---------------------------------------------------------------------------
# get_endpoints includes new routes
# ---------------------------------------------------------------------------

class TestGetEndpoints:
    def test_includes_monitor_endpoints(self, server):
        endpoints = server.get_endpoints()
        paths = [e["path"] for e in endpoints]
        assert "/api/monitor/events" in paths
        assert "/api/monitor/start" in paths
        assert "/api/monitor/stop" in paths
