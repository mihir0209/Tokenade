"""Tests for P8 API, SDK, and webhook features."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestAPIServer:
    """Tests for TokenadeAPIServer."""
    
    def test_config_defaults(self):
        """Should have sensible defaults."""
        from tokenade.core.api.server import APIServerConfig
        config = APIServerConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 9224
        assert config.api_key is None
    
    def test_config_custom(self):
        """Should accept custom config."""
        from tokenade.core.api.server import APIServerConfig
        config = APIServerConfig(host="0.0.0.0", port=8080, api_key="secret")
        assert config.host == "0.0.0.0"
        assert config.port == 8080
        assert config.api_key == "secret"
    
    def test_server_init(self):
        """Should initialize with config."""
        from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig
        config = APIServerConfig()
        server = TokenadeAPIServer(config)
        assert server.config == config
    
    def test_get_endpoints(self):
        """Should return list of endpoints."""
        from tokenade.core.api.server import TokenadeAPIServer
        server = TokenadeAPIServer()
        endpoints = server.get_endpoints()
        assert isinstance(endpoints, list)
        assert len(endpoints) >= 5
        
        paths = [e["path"] for e in endpoints]
        assert "/api/health" in paths
        assert "/api/sessions" in paths
    
    def test_check_auth_no_key(self):
        """Should allow all requests when no API key set."""
        from tokenade.core.api.server import TokenadeAPIServer
        server = TokenadeAPIServer()
        
        request = MagicMock()
        request.headers = {}
        
        assert server._check_auth(request) is True
    
    def test_check_auth_with_key(self):
        """Should validate API key when set."""
        from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig
        config = APIServerConfig(api_key="test-key-123")
        server = TokenadeAPIServer(config)
        
        request = MagicMock()
        request.headers = {"Authorization": "Bearer test-key-123"}
        assert server._check_auth(request) is True
        
        request.headers = {"Authorization": "Bearer wrong-key"}
        assert server._check_auth(request) is False
        
        request.headers = {}
        assert server._check_auth(request) is False
    
    def test_check_auth_x_api_key(self):
        """Should validate X-API-Key header."""
        from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig
        config = APIServerConfig(api_key="my-secret")
        server = TokenadeAPIServer(config)
        
        request = MagicMock()
        request.headers = {"X-API-Key": "my-secret"}
        assert server._check_auth(request) is True
        
        request.headers = {"X-API-Key": "wrong"}
        assert server._check_auth(request) is False
    
    def test_create_app(self):
        """Should create aiohttp application."""
        from tokenade.core.api.server import TokenadeAPIServer
        server = TokenadeAPIServer()
        app = server.create_app()
        assert app is not None


class TestSDK:
    """Tests for TokenadeClient."""
    
    def test_client_init(self, tmp_path):
        """Should initialize with custom sessions dir."""
        from tokenade.sdk import TokenadeClient
        client = TokenadeClient(sessions_dir=str(tmp_path / "sessions"))
        assert client.sessions_dir.exists()
    
    def test_list_sessions_empty(self, tmp_path):
        """Should return empty list for empty directory."""
        from tokenade.sdk import TokenadeClient
        client = TokenadeClient(sessions_dir=str(tmp_path))
        sessions = client.list_sessions()
        assert sessions == []
    
    def test_load_nonexistent(self):
        """Should return None for nonexistent file."""
        from tokenade.sdk import TokenadeClient
        client = TokenadeClient()
        result = client.load("/nonexistent/file.tokenade")
        assert result is None
    
    def test_health_check_nonexistent(self):
        """Should return error for nonexistent file."""
        from tokenade.sdk import TokenadeClient
        client = TokenadeClient()
        result = client.health_check("/nonexistent/file.tokenade")
        assert result["healthy"] is False
    
    def test_export_playwright(self, tmp_path, sample_session):
        """Should export to Playwright format."""
        from tokenade.sdk import TokenadeClient
        
        client = TokenadeClient(sessions_dir=str(tmp_path))
        
        session_file = tmp_path / "test.tokenade"
        session_file.write_text(json.dumps(sample_session))
        
        output = tmp_path / "storage_state.json"
        result = client.export_playwright(str(session_file), str(output))
        
        assert result is True
        assert output.exists()
        
        with open(output) as f:
            data = json.load(f)
        assert "cookies" in data
    
    def test_share_nonexistent(self):
        """Should return None for nonexistent session."""
        from tokenade.sdk import TokenadeClient
        client = TokenadeClient()
        result = client.share("/nonexistent/file.tokenade")
        assert result is None


class TestWebhooks:
    """Tests for webhook integrations."""
    
    def test_webhook_config(self):
        """Should create webhook config."""
        from tokenade.core.integration.webhooks import WebhookConfig
        config = WebhookConfig(
            url="https://hooks.slack.com/test",
            type="slack",
            secret="my-secret",
        )
        assert config.url == "https://hooks.slack.com/test"
        assert config.type == "slack"
        assert config.secret == "my-secret"
    
    def test_build_payload(self):
        """Should build notification payload."""
        from tokenade.core.integration.webhooks import WebhookIntegration, WebhookConfig
        
        config = WebhookConfig(url="https://example.com/webhook")
        integration = WebhookIntegration(config)
        
        payload = integration._build_payload("export", {
            "site_name": "github",
            "cookie_count": 15,
            "created_at": "2026-01-01T00:00:00Z",
        })
        
        assert payload["event_type"] == "export"
        assert payload["site_name"] == "github"
        assert payload["cookie_count"] == 15
        assert "github" in payload["message"]
    
    def test_webhook_manager_add_remove(self):
        """Should add and remove webhooks."""
        from tokenade.core.integration.webhooks import WebhookManager, WebhookConfig
        
        manager = WebhookManager()
        config = WebhookConfig(url="https://example.com/hook")
        
        manager.add("test", config)
        assert len(manager.list_webhooks()) == 1
        
        manager.remove("test")
        assert len(manager.list_webhooks()) == 0
    
    def test_webhook_manager_send_no_webhook(self):
        """Should return False for nonexistent webhook."""
        from tokenade.core.integration.webhooks import WebhookManager
        
        manager = WebhookManager()
        result = manager.send("nonexistent", "export", {})
        assert result is False
    
    def test_webhook_manager_broadcast_empty(self):
        """Should return empty dict for no webhooks."""
        from tokenade.core.integration.webhooks import WebhookManager
        
        manager = WebhookManager()
        results = manager.broadcast("export", {})
        assert results == {}
    
    def test_slack_payload_format(self):
        """Should format Slack payload correctly."""
        from tokenade.core.integration.webhooks import WebhookIntegration, WebhookConfig
        
        config = WebhookConfig(url="https://hooks.slack.com/test", type="slack")
        integration = WebhookIntegration(config)
        
        payload = integration._build_payload("share", {"site_name": "test", "cookie_count": 5})
        slack_payload = integration._format_slack(payload)
        
        assert "text" in slack_payload
        assert "blocks" in slack_payload
    
    def test_discord_payload_format(self):
        """Should format Discord payload correctly."""
        from tokenade.core.integration.webhooks import WebhookIntegration, WebhookConfig
        
        config = WebhookConfig(url="https://discord.com/api/webhooks/test", type="discord")
        integration = WebhookIntegration(config)
        
        payload = integration._build_payload("export", {"site_name": "test", "cookie_count": 10})
        discord_payload = integration._format_discord(payload)
        
        assert "embeds" in discord_payload
        assert discord_payload["embeds"][0]["title"] is not None
    
    def test_teams_payload_format(self):
        """Should format Teams payload correctly."""
        from tokenade.core.integration.webhooks import WebhookIntegration, WebhookConfig
        
        config = WebhookConfig(url="https://example.webhook.office.com/test", type="teams")
        integration = WebhookIntegration(config)
        
        payload = integration._build_payload("refresh", {"site_name": "example", "cookie_count": 8})
        teams_payload = integration._format_teams(payload)
        
        assert teams_payload["@type"] == "MessageCard"
        assert "sections" in teams_payload
    
    def test_build_payload_expired(self):
        """Should build expired event payload."""
        from tokenade.core.integration.webhooks import WebhookIntegration, WebhookConfig
        
        config = WebhookConfig(url="https://example.com/webhook")
        integration = WebhookIntegration(config)
        
        payload = integration._build_payload("expired", {
            "site_name": "github",
            "cookie_count": 0,
        })
        
        assert payload["event_type"] == "expired"
        assert "expired" in payload["message"].lower()
