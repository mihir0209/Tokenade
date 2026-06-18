"""Tests for webhook integrations."""

import urllib.error
from unittest.mock import patch, MagicMock

from tokenade.core.integration.webhooks import (
    WebhookConfig,
    WebhookIntegration,
    WebhookManager,
)


SAMPLE_SESSION = {
    "site_name": "example.com",
    "cookie_count": 42,
    "created_at": "2025-01-01T00:00:00",
}


def _mock_urlopen(status=200):
    mock_resp = MagicMock()
    mock_resp.status = status
    return MagicMock(return_value=mock_resp)


class TestWebhookConfig:
    def test_defaults(self):
        cfg = WebhookConfig(url="https://example.com/hook")
        assert cfg.type == "custom"
        assert cfg.secret is None
        assert cfg.channel is None
        assert cfg.bot_token is None

    def test_all_fields(self):
        cfg = WebhookConfig(
            url="https://x.com/hook",
            type="slack",
            secret="s3cret",
            channel="#general",
            bot_token="tok123",
        )
        assert cfg.bot_token == "tok123"


class TestBuildPayload:
    def test_export_event(self):
        wi = WebhookIntegration(WebhookConfig(url="x"))
        p = wi._build_payload("export", SAMPLE_SESSION)
        assert p["event_type"] == "export"
        assert "42 cookies" in p["message"]
        assert p["site_name"] == "example.com"

    def test_share_event(self):
        wi = WebhookIntegration(WebhookConfig(url="x"))
        p = wi._build_payload("share", SAMPLE_SESSION)
        assert "shared" in p["message"]

    def test_refresh_event(self):
        wi = WebhookIntegration(WebhookConfig(url="x"))
        p = wi._build_payload("refresh", SAMPLE_SESSION)
        assert "refreshed" in p["message"]

    def test_expired_event(self):
        wi = WebhookIntegration(WebhookConfig(url="x"))
        p = wi._build_payload("expired", SAMPLE_SESSION)
        assert "expired" in p["message"]

    def test_unknown_event(self):
        wi = WebhookIntegration(WebhookConfig(url="x"))
        p = wi._build_payload("custom_action", SAMPLE_SESSION)
        assert "custom_action" in p["message"]

    def test_missing_fields(self):
        wi = WebhookIntegration(WebhookConfig(url="x"))
        p = wi._build_payload("export", {})
        assert p["site_name"] == "unknown"
        assert p["cookie_count"] == 0


class TestFormatSlack:
    def test_structure(self):
        wi = WebhookIntegration(WebhookConfig(url="x"))
        payload = {"event_type": "export", "message": "test msg", "site_name": "s", "cookie_count": 1}
        result = wi._format_slack(payload)
        assert result["text"] == "test msg"
        assert len(result["blocks"]) == 1
        assert result["blocks"][0]["type"] == "section"
        assert "Export" in result["blocks"][0]["text"]["text"]


class TestFormatDiscord:
    def test_green_on_non_expired(self):
        wi = WebhookIntegration(WebhookConfig(url="x"))
        payload = {"event_type": "export", "message": "m", "site_name": "s", "cookie_count": 5}
        result = wi._format_discord(payload)
        assert result["embeds"][0]["color"] == 0x00FF00

    def test_red_on_expired(self):
        wi = WebhookIntegration(WebhookConfig(url="x"))
        payload = {"event_type": "expired", "message": "m", "site_name": "s", "cookie_count": 5}
        result = wi._format_discord(payload)
        assert result["embeds"][0]["color"] == 0xFF0000

    def test_fields(self):
        wi = WebhookIntegration(WebhookConfig(url="x"))
        payload = {"event_type": "export", "message": "m", "site_name": "test.com", "cookie_count": 7}
        result = wi._format_discord(payload)
        fields = result["embeds"][0]["fields"]
        assert len(fields) == 2
        assert fields[0]["value"] == "test.com"
        assert fields[1]["value"] == "7"


class TestFormatTeams:
    def test_green_theme(self):
        wi = WebhookIntegration(WebhookConfig(url="x"))
        payload = {"event_type": "export", "message": "m", "site_name": "s", "cookie_count": 1}
        result = wi._format_teams(payload)
        assert result["themeColor"] == "00FF00"
        assert result["@type"] == "MessageCard"

    def test_red_theme_expired(self):
        wi = WebhookIntegration(WebhookConfig(url="x"))
        payload = {"event_type": "expired", "message": "m", "site_name": "s", "cookie_count": 1}
        result = wi._format_teams(payload)
        assert result["themeColor"] == "FF0000"


class TestSendTelegram:
    @patch("tokenade.core.integration.webhooks.urlopen")
    def test_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp

        cfg = WebhookConfig(url="x", type="telegram", bot_token="tok123", channel="12345")
        wi = WebhookIntegration(cfg)
        result = wi._send_telegram({"event_type": "export", "message": "m", "site_name": "s", "cookie_count": 1})
        assert result is True
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert "bottok123" in req.full_url
        assert req.method == "POST"

    def test_missing_bot_token(self):
        cfg = WebhookConfig(url="x", type="telegram")
        wi = WebhookIntegration(cfg)
        result = wi._send_telegram({"event_type": "export", "message": "m", "site_name": "s", "cookie_count": 1})
        assert result is False


class TestHttpPost:
    @patch("tokenade.core.integration.webhooks.urlopen")
    def test_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp

        wi = WebhookIntegration(WebhookConfig(url="https://hook.example.com"))
        result = wi._http_post("https://hook.example.com", {"key": "val"})
        assert result is True

    @patch("tokenade.core.integration.webhooks.urlopen")
    def test_hmac_signature_header(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp

        cfg = WebhookConfig(url="https://hook.example.com", secret="mysecret")
        wi = WebhookIntegration(cfg)
        wi._http_post("https://hook.example.com", {"key": "val"})

        req = mock_urlopen.call_args[0][0]
        sig = req.get_header("X-tokenade-signature")
        assert sig is not None
        assert len(sig) == 64

    @patch("tokenade.core.integration.webhooks.urlopen")
    def test_url_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("refused")
        wi = WebhookIntegration(WebhookConfig(url="https://bad.example.com"))
        result = wi._http_post("https://bad.example.com", {})
        assert result is False

    @patch("tokenade.core.integration.webhooks.urlopen")
    def test_generic_exception(self, mock_urlopen):
        mock_urlopen.side_effect = RuntimeError("boom")
        wi = WebhookIntegration(WebhookConfig(url="https://bad.example.com"))
        result = wi._http_post("https://bad.example.com", {})
        assert result is False

    @patch("tokenade.core.integration.webhooks.urlopen")
    def test_status_500(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_urlopen.return_value = mock_resp
        wi = WebhookIntegration(WebhookConfig(url="https://x"))
        result = wi._http_post("https://x", {})
        assert result is False


class TestSendSessionEvent:
    @patch("tokenade.core.integration.webhooks.urlopen")
    def test_slack(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp
        wi = WebhookIntegration(WebhookConfig(url="https://x", type="slack"))
        assert wi.send_session_event("export", SAMPLE_SESSION) is True
        req = mock_urlopen.call_args[0][0]
        assert "json" in req.get_header("Content-type")

    @patch("tokenade.core.integration.webhooks.urlopen")
    def test_discord(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp
        wi = WebhookIntegration(WebhookConfig(url="https://x", type="discord"))
        assert wi.send_session_event("share", SAMPLE_SESSION) is True

    @patch("tokenade.core.integration.webhooks.urlopen")
    def test_teams(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp
        wi = WebhookIntegration(WebhookConfig(url="https://x", type="teams"))
        assert wi.send_session_event("refresh", SAMPLE_SESSION) is True

    @patch("tokenade.core.integration.webhooks.urlopen")
    def test_custom(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp
        wi = WebhookIntegration(WebhookConfig(url="https://x", type="custom"))
        assert wi.send_session_event("expired", SAMPLE_SESSION) is True

    @patch("tokenade.core.integration.webhooks.urlopen")
    def test_telegram_via_send_session_event(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp
        wi = WebhookIntegration(WebhookConfig(url="https://x", type="telegram", bot_token="tok", channel="123"))
        assert wi.send_session_event("export", SAMPLE_SESSION) is True


class TestWebhookManager:
    def test_add_and_list(self):
        mgr = WebhookManager()
        mgr.add("a", WebhookConfig(url="https://a.com", type="slack"))
        mgr.add("b", WebhookConfig(url="https://b.com", type="discord"))
        listing = mgr.list_webhooks()
        assert len(listing) == 2
        assert listing[0]["name"] == "a"
        assert listing[0]["type"] == "slack"
        assert "..." in listing[0]["url"]

    def test_remove(self):
        mgr = WebhookManager()
        mgr.add("a", WebhookConfig(url="https://a.com"))
        assert mgr.remove("a") is True
        assert mgr.remove("a") is False

    def test_send_not_found(self):
        mgr = WebhookManager()
        assert mgr.send("nope", "export", SAMPLE_SESSION) is False

    @patch("tokenade.core.integration.webhooks.urlopen")
    def test_send_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp
        mgr = WebhookManager()
        mgr.add("hook", WebhookConfig(url="https://hook.com", type="slack"))
        assert mgr.send("hook", "export", SAMPLE_SESSION) is True

    @patch("tokenade.core.integration.webhooks.urlopen")
    def test_broadcast(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp
        mgr = WebhookManager()
        mgr.add("a", WebhookConfig(url="https://a.com", type="slack"))
        mgr.add("b", WebhookConfig(url="https://b.com", type="discord"))
        results = mgr.broadcast("export", SAMPLE_SESSION)
        assert results == {"a": True, "b": True}

    def test_broadcast_empty(self):
        mgr = WebhookManager()
        results = mgr.broadcast("export", SAMPLE_SESSION)
        assert results == {}
