"""Tests for OAuth Automation Plugin."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tokenade.plugin.api import PluginResult
from tokenade.plugin.oauth_automation import OAuthAutomationPlugin
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "Projects/tokenade-plugins/plugins/google-flow-handler"))
from plugin import GoogleFlowPlugin


class ConcreteOAuthPlugin(OAuthAutomationPlugin):
    """Concrete test implementation of OAuthAutomationPlugin."""

    name = "test-oauth"
    version = "1.0.0"
    description = "Test OAuth plugin"
    target_url = "https://example.com/login"
    oauth_button_selector = "#google-login"
    redirect_url_pattern = r"example\.com/dashboard.*"

    def process(self, session_file, output_dir=None):
        return PluginResult(success=True, data={"test": True})

    def refresh_session(self, session):
        return PluginResult(success=True, data={"refreshed": True})

    def extract_session(self, browser_context, url=""):
        return PluginResult(success=True, data={"cookies": []})

    def inject_session(self, browser_context, session):
        return PluginResult(success=True, data={"injected": True})


class TestOAuthAutomationPlugin:
    """Tests for OAuthAutomationPlugin base class."""

    def test_is_site_handler_plugin(self):
        plugin = ConcreteOAuthPlugin()
        assert isinstance(plugin, OAuthAutomationPlugin)

    def test_metadata(self):
        plugin = ConcreteOAuthPlugin()
        assert plugin.name == "test-oauth"
        assert plugin.version == "1.0.0"

    def test_target_config(self):
        plugin = ConcreteOAuthPlugin()
        assert plugin.target_url == "https://example.com/login"
        assert plugin.oauth_button_selector == "#google-login"
        assert plugin.redirect_url_pattern == r"example\.com/dashboard.*"

    def test_process_returns_plugin_result(self):
        plugin = ConcreteOAuthPlugin()
        result = plugin.process("test.session")
        assert isinstance(result, PluginResult)
        assert result.success is True

    def test_refresh_returns_plugin_result(self):
        plugin = ConcreteOAuthPlugin()
        result = plugin.refresh_session({"cookies": []})
        assert isinstance(result, PluginResult)
        assert result.success is True

    def test_extract_email_from_session(self):
        plugin = ConcreteOAuthPlugin()
        session = {
            "metadata": {"email": "test@gmail.com"},
            "cookies": [],
        }
        email = plugin.extract_email_from_session(session)
        assert email == "test@gmail.com"

    def test_extract_email_from_session_missing(self):
        plugin = ConcreteOAuthPlugin()
        session = {"metadata": {}, "cookies": []}
        email = plugin.extract_email_from_session(session)
        assert email is None

    def test_extract_email_user_email_key(self):
        plugin = ConcreteOAuthPlugin()
        session = {
            "metadata": {"user_email": "user@example.com"},
            "cookies": [],
        }
        email = plugin.extract_email_from_session(session)
        assert email == "user@example.com"

    def test_decode_session_token_jwt(self):
        import base64

        plugin = ConcreteOAuthPlugin()
        payload = {"email": "test@gmail.com", "exp": 1234567890}
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).decode()
        token = f"header.{encoded}.signature"

        decoded = plugin.decode_session_token(token)
        assert decoded["email"] == "test@gmail.com"
        assert decoded["exp"] == 1234567890

    def test_decode_session_token_invalid(self):
        plugin = ConcreteOAuthPlugin()
        decoded = plugin.decode_session_token("invalid-token")
        assert decoded == {}

    def test_inject_source_session(self):
        plugin = ConcreteOAuthPlugin()
        context = MagicMock()
        session = {
            "cookies": [
                {"name": "SID", "value": "abc", "domain": ".google.com"},
                {"name": "HSID", "value": "def", "domain": ".google.com"},
            ]
        }

        result = plugin.inject_source_session(context, session)
        assert result is True
        context.add_cookies.assert_called_once()
        injected = context.add_cookies.call_args[0][0]
        assert len(injected) == 2
        assert injected[0]["name"] == "SID"
        assert injected[0]["path"] == "/"

    def test_inject_source_session_empty(self):
        plugin = ConcreteOAuthPlugin()
        context = MagicMock()
        session = {"cookies": []}

        result = plugin.inject_source_session(context, session)
        assert result is False

    def test_verify_provider_session_success(self):
        plugin = ConcreteOAuthPlugin()
        page = MagicMock()
        page.url = "https://myaccount.google.com"

        result = plugin.verify_provider_session(page, "https://myaccount.google.com")
        assert result is True

    def test_verify_provider_session_logged_out(self):
        plugin = ConcreteOAuthPlugin()
        page = MagicMock()
        page.url = "https://accounts.google.com/signin"

        result = plugin.verify_provider_session(page, "https://myaccount.google.com")
        assert result is False

    def test_export_target_session(self):
        plugin = ConcreteOAuthPlugin()
        plugin.target_cookie_domains = ["example.com"]
        plugin.target_critical_cookies = ["session_token"]

        context = MagicMock()
        context.cookies.return_value = [
            {"name": "session_token", "value": "abc", "domain": "example.com"},
            {"name": "other", "value": "xyz", "domain": "other.com"},
        ]

        with patch("tokenade.core.importer.session_packager.SessionPackager") as mock_packager_cls:
            mock_packager = MagicMock()
            mock_packager.package.return_value = {"cookies": [], "site_name": "test"}
            mock_packager.save.return_value = "/tmp/test.tokenade"
            mock_packager_cls.return_value = mock_packager

            result = plugin.export_target_session(context, "test_site")
            assert result is not None
            assert result["site_name"] == "test_site"


class TestGoogleFlowPlugin:
    """Tests for GoogleFlowPlugin."""

    def test_is_oauth_automation_plugin(self):
        plugin = GoogleFlowPlugin()
        assert isinstance(plugin, OAuthAutomationPlugin)

    def test_metadata(self):
        plugin = GoogleFlowPlugin()
        assert plugin.name == "google-flow-handler"
        assert plugin.version == "1.0.0"
        assert plugin.author == "MiHiR"

    def test_target_config(self):
        plugin = GoogleFlowPlugin()
        assert plugin.target_url == "https://labs.google/fx/tools/flow"
        assert "accounts.google.com" in plugin.oauth_button_selector
        assert plugin.redirect_url_pattern == r"labs\.google/fx/tools/flow.*"

    def test_cookie_config(self):
        plugin = GoogleFlowPlugin()
        assert "labs.google" in plugin.target_cookie_domains
        assert "__Secure-next-auth.session-token" in plugin.target_critical_cookies
        assert "EMAIL" in plugin.target_critical_cookies

    def test_dependencies(self):
        plugin = GoogleFlowPlugin()
        assert "google-handler" in plugin.dependencies

    def test_process_missing_file(self):
        plugin = GoogleFlowPlugin()
        result = plugin.process("/nonexistent/file.tokenade")
        assert result.success is False
        assert "not found" in result.error.lower() or "failed" in result.error.lower()

    def test_process_no_email(self, tmp_path):
        plugin = GoogleFlowPlugin()
        session_file = tmp_path / "test.tokenade"
        session_file.write_text(json.dumps({
            "cookies": [{"name": "SID", "value": "abc", "domain": ".google.com"}],
            "metadata": {},
        }))

        result = plugin.process(str(session_file))
        assert result.success is False
        assert "email" in result.error.lower()

    def test_refresh_session_no_google_cookies(self):
        plugin = GoogleFlowPlugin()
        session = {
            "cookies": [{"name": "sid", "value": "x", "domain": ".example.com"}],
            "metadata": {},
        }
        result = plugin.refresh_session(session)
        assert result.success is False
        assert "google" in result.error.lower()

    def test_refresh_session_no_email(self):
        plugin = GoogleFlowPlugin()
        session = {
            "cookies": [{"name": "SID", "value": "x", "domain": ".google.com"}],
            "metadata": {},
        }
        result = plugin.refresh_session(session)
        assert result.success is False
        assert "email" in result.error.lower()
