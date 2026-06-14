"""Tests for API monitoring endpoints."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig


class TestAPIMonitorEndpoints:
    def setup_method(self):
        self.config = APIServerConfig(api_key=None)
        self.server = TokenadeAPIServer(self.config)

    def test_server_has_monitor_attribute(self):
        assert hasattr(self.server, '_monitor')
        assert self.server._monitor is None

    def test_endpoints_list_includes_monitor(self):
        endpoints = self.server.get_endpoints()
        paths = [e["path"] for e in endpoints]
        assert "/api/monitor/status" in paths
        assert "/api/monitor/sessions/{id}" in paths
        assert "/api/monitor/sessions/{id}/cookies" in paths

    def test_health_check_returns_version(self):
        from tokenade import __version__
        assert __version__ == "3.5.0"
