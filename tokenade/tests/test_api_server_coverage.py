"""Tests for tokenade/core/api/server.py uncovered lines."""

import asyncio
import unittest
from unittest.mock import MagicMock, patch, AsyncMock


def _run_async(coro):
    return asyncio.run(coro)


def _make_request(headers=None, match_info=None):
    request = MagicMock()
    request.headers = headers or {}
    request.match_info = match_info or {}
    return request


class TestSessionGetAuthFailure(unittest.TestCase):
    """Lines 95: _handle_session_get returns 401 when auth fails."""

    def test_session_get_no_auth(self):
        from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig

        config = APIServerConfig(host="127.0.0.1", port=0, api_key="secret")
        server = TokenadeAPIServer(config)
        request = _make_request(headers={}, match_info={"id": "test123"})

        response = _run_async(server._handle_session_get(request))
        self.assertEqual(response.status, 401)


class TestSessionDeleteAuthFailure(unittest.TestCase):
    """Lines 116: _handle_session_delete returns 401 when auth fails."""

    def test_session_delete_no_auth(self):
        from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig

        config = APIServerConfig(host="127.0.0.1", port=0, api_key="secret")
        server = TokenadeAPIServer(config)
        request = _make_request(headers={}, match_info={"id": "test123"})

        response = _run_async(server._handle_session_delete(request))
        self.assertEqual(response.status, 401)


class TestShareCreateAuthFailure(unittest.TestCase):
    """Line 174: _handle_share_create returns 401 when auth fails."""

    def test_share_create_no_auth(self):
        from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig

        config = APIServerConfig(host="127.0.0.1", port=0, api_key="secret")
        server = TokenadeAPIServer(config)
        request = _make_request(headers={})

        response = _run_async(server._handle_share_create(request))
        self.assertEqual(response.status, 401)


class TestExportSuccessPath(unittest.TestCase):
    """Line 200 area: _handle_export success when subprocess returns 0."""

    def test_export_success(self):
        from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig

        config = APIServerConfig(host="127.0.0.1", port=0)
        server = TokenadeAPIServer(config)

        request = _make_request(headers={})
        request.json = AsyncMock(return_value={"browser": "chrome", "domains": []})

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "exported"

        with patch("subprocess.run", return_value=mock_result):
            response = _run_async(server._handle_export(request))

        self.assertEqual(response.status, 200)


class TestMonitorStatusAuthFailure(unittest.TestCase):
    """Line 205: _handle_monitor_status returns 401 when auth fails."""

    def test_monitor_status_no_auth(self):
        from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig

        config = APIServerConfig(host="127.0.0.1", port=0, api_key="secret")
        server = TokenadeAPIServer(config)
        request = _make_request(headers={})

        response = _run_async(server._handle_monitor_status(request))
        self.assertEqual(response.status, 401)


class TestMonitorSessionAuthFailure(unittest.TestCase):
    """Line 222: _handle_monitor_session returns 401 when auth fails."""

    def test_monitor_session_no_auth(self):
        from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig

        config = APIServerConfig(host="127.0.0.1", port=0, api_key="secret")
        server = TokenadeAPIServer(config)
        request = _make_request(headers={}, match_info={"id": "test123"})

        response = _run_async(server._handle_monitor_session(request))
        self.assertEqual(response.status, 401)


class TestMonitorCookiesAuthFailure(unittest.TestCase):
    """Line 263: _handle_monitor_cookies returns 401 when auth fails."""

    def test_monitor_cookies_no_auth(self):
        from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig

        config = APIServerConfig(host="127.0.0.1", port=0, api_key="secret")
        server = TokenadeAPIServer(config)
        request = _make_request(headers={}, match_info={"id": "test123"})

        response = _run_async(server._handle_monitor_cookies(request))
        self.assertEqual(response.status, 401)


class TestDashboardNotFound(unittest.TestCase):
    """Line 305: _handle_dashboard returns 404 when dashboard file missing."""

    def test_dashboard_not_found(self):
        from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig

        config = APIServerConfig(host="127.0.0.1", port=0)
        server = TokenadeAPIServer(config)
        request = _make_request(headers={})

        with patch("pathlib.Path.exists", return_value=False):
            response = _run_async(server._handle_dashboard(request))

        self.assertEqual(response.status, 404)


class TestSyncListHandler(unittest.TestCase):
    """Lines 338-342: _handle_sync_list returns targets."""

    def test_sync_list(self):
        from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig

        config = APIServerConfig(host="127.0.0.1", port=0)
        server = TokenadeAPIServer(config)
        request = _make_request(headers={})

        with patch("tokenade.core.importer.session_sync.SessionSyncDaemon") as MockDaemon:
            mock_instance = MagicMock()
            mock_instance.get_status.return_value = []
            MockDaemon.load_config.return_value = mock_instance

            response = _run_async(server._handle_sync_list(request))

        self.assertEqual(response.status, 200)


class TestSyncRunHandler(unittest.TestCase):
    """Lines 346-350: _handle_sync_run runs one-time sync."""

    def test_sync_run(self):
        from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig

        config = APIServerConfig(host="127.0.0.1", port=0)
        server = TokenadeAPIServer(config)
        request = _make_request(headers={})

        with patch("tokenade.core.importer.session_sync.SessionSyncDaemon") as MockDaemon:
            mock_instance = MagicMock()
            mock_instance.check_once.return_value = {}
            MockDaemon.load_config.return_value = mock_instance

            response = _run_async(server._handle_sync_run(request))

        self.assertEqual(response.status, 200)


class TestStartMethod(unittest.TestCase):
    """Lines 354-363: start() creates app, runner, TCPSite."""

    def test_start_creates_runner_and_site(self):
        from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig

        config = APIServerConfig(host="127.0.0.1", port=0)
        server = TokenadeAPIServer(config)

        with patch("aiohttp.web.AppRunner") as MockRunner, \
             patch("aiohttp.web.TCPSite") as MockSite:
            mock_runner = MagicMock()
            mock_runner.setup = AsyncMock()
            MockRunner.return_value = mock_runner

            mock_site = MagicMock()
            mock_site.start = AsyncMock()
            MockSite.return_value = mock_site

            _run_async(server.start())

            mock_runner.setup.assert_called_once()
            mock_site.start.assert_called_once()


class TestStopMethod(unittest.TestCase):
    """Lines 367-368: stop() calls runner.cleanup()."""

    def test_stop_calls_cleanup(self):
        from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig

        config = APIServerConfig(host="127.0.0.1", port=0)
        server = TokenadeAPIServer(config)
        server._runner = MagicMock()
        server._runner.cleanup = AsyncMock()

        _run_async(server.stop())

        server._runner.cleanup.assert_called_once()

    def test_stop_with_no_runner(self):
        from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig

        config = APIServerConfig(host="127.0.0.1", port=0)
        server = TokenadeAPIServer(config)
        server._runner = None

        _run_async(server.stop())


if __name__ == "__main__":
    unittest.main()
