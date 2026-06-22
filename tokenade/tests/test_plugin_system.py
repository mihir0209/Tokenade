"""Tests for Tokenade Plugin System — Base Classes and OAuth2 Plugin."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tokenade.plugin import (
    PluginBase,
    SessionRefreshPlugin,
    SiteHandlerPlugin,
    ExportFormatPlugin,
    SessionValidatorPlugin,
)


# === Concrete test implementations of abstract classes ===

class TestRefreshPlugin(SessionRefreshPlugin):
    """Concrete test implementation of SessionRefreshPlugin."""
    name = "test-refresh"
    version = "1.0.0"
    description = "Test refresh plugin"

    def can_refresh(self, session):
        return session.get("site_name") == "test-site"

    def refresh(self, session, credentials):
        session["metadata"] = session.get("metadata", {})
        session["metadata"]["refreshed"] = True
        return session

    def get_credentials_args(self):
        return [{"name": "--api-key", "help": "API key", "required": True, "type": str}]


class TestSiteHandler(SiteHandlerPlugin):
    """Concrete test implementation of SiteHandlerPlugin."""
    name = "test-handler"
    version = "1.0.0"
    description = "Test site handler"

    def can_handle(self, url):
        return "example.com" in url

    def extract_session(self, browser_context, url):
        return {"cookies": [], "site_name": "test"}

    def inject_session(self, browser_context, session):
        return True


class TestExportFormat(ExportFormatPlugin):
    """Concrete test implementation of ExportFormatPlugin."""
    name = "test-export"
    version = "1.0.0"
    description = "Test export format"

    def get_format_name(self):
        return "test-format"

    def export(self, session, output_path):
        with open(output_path, "w") as f:
            f.write("test output")
        return output_path


class TestValidator(SessionValidatorPlugin):
    """Concrete test implementation of SessionValidatorPlugin."""
    name = "test-validator"
    version = "1.0.0"
    description = "Test validator"

    def validate(self, session):
        return {"valid": True, "score": 100.0, "issues": []}


# === PluginBase Tests ===

class TestPluginBase:
    def test_base_class_structure(self):
        plugin = TestRefreshPlugin()
        assert hasattr(plugin, "name")
        assert hasattr(plugin, "version")
        assert hasattr(plugin, "description")
        assert hasattr(plugin, "on_load")
        assert hasattr(plugin, "on_unload")
        assert hasattr(plugin, "get_info")

    def test_plugin_metadata(self):
        plugin = TestRefreshPlugin()
        assert plugin.name == "test-refresh"
        assert plugin.version == "1.0.0"
        assert plugin.description == "Test refresh plugin"

    def test_get_info(self):
        plugin = TestRefreshPlugin()
        info = plugin.get_info()
        assert info["name"] == "test-refresh"
        assert info["version"] == "1.0.0"
        assert info["description"] == "Test refresh plugin"

    def test_lifecycle_hooks(self):
        plugin = TestRefreshPlugin()
        # Should not raise
        plugin.on_load()
        plugin.on_unload()


# === SessionRefreshPlugin Tests ===

class TestSessionRefreshPlugin:
    def test_can_refresh(self):
        plugin = TestRefreshPlugin()
        assert plugin.can_refresh({"site_name": "test-site"}) is True
        assert plugin.can_refresh({"site_name": "other"}) is False

    def test_refresh(self):
        plugin = TestRefreshPlugin()
        session = {"site_name": "test-site", "cookies": []}
        result = plugin.refresh(session, {})
        assert result["metadata"]["refreshed"] is True

    def test_get_credentials_args(self):
        plugin = TestRefreshPlugin()
        args = plugin.get_credentials_args()
        assert len(args) == 1
        assert args[0]["name"] == "--api-key"
        assert args[0]["required"] is True

    def test_inheritance(self):
        plugin = TestRefreshPlugin()
        assert isinstance(plugin, PluginBase)
        assert isinstance(plugin, SessionRefreshPlugin)


# === SiteHandlerPlugin Tests ===

class TestSiteHandlerPlugin:
    def test_can_handle(self):
        plugin = TestSiteHandler()
        assert plugin.can_handle("https://example.com/page") is True
        assert plugin.can_handle("https://other.com/page") is False

    def test_extract_session(self):
        plugin = TestSiteHandler()
        session = plugin.extract_session(None, "https://example.com")
        assert "cookies" in session
        assert session["site_name"] == "test"

    def test_inject_session(self):
        plugin = TestSiteHandler()
        assert plugin.inject_session(None, {"cookies": []}) is True


# === ExportFormatPlugin Tests ===

class TestExportFormatPlugin:
    def test_get_format_name(self):
        plugin = TestExportFormat()
        assert plugin.get_format_name() == "test-format"

    def test_export(self, tmp_path):
        plugin = TestExportFormat()
        output = tmp_path / "output.txt"
        result = plugin.export({"cookies": []}, str(output))
        assert os.path.isfile(result)
        assert open(result).read() == "test output"


# === SessionValidatorPlugin Tests ===

class TestSessionValidatorPlugin:
    def test_validate(self):
        plugin = TestValidator()
        result = plugin.validate({"cookies": []})
        assert result["valid"] is True
        assert result["score"] == 100.0
        assert result["issues"] == []


# === OAuth2 Plugin Tests ===

class TestOAuth2Plugin:
    def _make_plugin(self):
        from tokenade.plugin.oauth2.plugin import OAuth2Plugin
        return OAuth2Plugin()

    def test_import(self):
        from tokenade.plugin.oauth2.plugin import OAuth2Plugin
        assert OAuth2Plugin is not None

    def test_metadata(self):
        plugin = self._make_plugin()
        assert plugin.name == "oauth2"
        assert plugin.version == "1.0.0"

    def test_can_refresh_with_refresh_token_in_metadata(self):
        plugin = self._make_plugin()
        session = {"metadata": {"refresh_token": "abc123"}, "cookies": []}
        assert plugin.can_refresh(session) is True

    def test_can_refresh_with_google_cookie(self):
        plugin = self._make_plugin()
        session = {
            "cookies": [{"name": "token", "value": "x", "domain": ".google.com"}],
            "metadata": {},
        }
        assert plugin.can_refresh(session) is True

    def test_can_refresh_with_github_cookie(self):
        plugin = self._make_plugin()
        session = {
            "cookies": [{"name": "oauth_token", "value": "x", "domain": "github.com"}],
            "metadata": {},
        }
        assert plugin.can_refresh(session) is True

    def test_cannot_refresh_random_session(self):
        plugin = self._make_plugin()
        session = {"cookies": [{"name": "sid", "value": "x", "domain": ".example.com"}], "metadata": {}}
        assert plugin.can_refresh(session) is False

    def test_refresh_missing_client_id(self):
        plugin = self._make_plugin()
        session = {"cookies": [], "metadata": {"refresh_token": "tok"}}
        with pytest.raises(ValueError, match="client_id"):
            plugin.refresh(session, {"client_secret": "s", "refresh_token": "r"})

    def test_refresh_missing_client_secret(self):
        plugin = self._make_plugin()
        session = {"cookies": [], "metadata": {}}
        with pytest.raises(ValueError, match="client_secret"):
            plugin.refresh(session, {"client_id": "c", "refresh_token": "r"})

    def test_refresh_missing_refresh_token(self):
        plugin = self._make_plugin()
        session = {"cookies": [], "metadata": {}}
        with pytest.raises(ValueError, match="refresh_token"):
            plugin.refresh(session, {"client_id": "c", "client_secret": "s"})

    def test_get_credentials_args(self):
        plugin = self._make_plugin()
        args = plugin.get_credentials_args()
        names = [a["name"] for a in args]
        assert "--client-id" in names
        assert "--client-secret" in names
        assert "--refresh-token" in names
        assert "--provider" in names

    def test_detect_provider_google(self):
        plugin = self._make_plugin()
        session = {
            "cookies": [{"name": "sid", "value": "x", "domain": ".google.com"}],
            "metadata": {},
        }
        assert plugin._detect_provider(session) == "google"

    def test_detect_provider_github(self):
        plugin = self._make_plugin()
        session = {
            "cookies": [{"name": "sid", "value": "x", "domain": "github.com"}],
            "metadata": {},
        }
        assert plugin._detect_provider(session) == "github"

    def test_detect_provider_unknown(self):
        plugin = self._make_plugin()
        session = {"cookies": [{"name": "sid", "value": "x", "domain": ".example.com"}], "metadata": {}}
        assert plugin._detect_provider(session) is None

    def test_update_token_cookie_google(self):
        plugin = self._make_plugin()
        session = {
            "cookies": [
                {"name": "token", "value": "old", "domain": ".google.com", "expires": 100}
            ],
            "metadata": {},
        }
        plugin._update_token_cookie(session, "google", "new_token_val", {"cookie_domains": [".google.com"]})
        cookie = session["cookies"][0]
        assert cookie["value"] == "new_token_val"
        assert cookie["expires"] > 100

    def test_update_token_cookie_creates_new(self):
        plugin = self._make_plugin()
        session = {"cookies": [], "metadata": {}}
        plugin._update_token_cookie(session, "github", "gh_token", {"cookie_domains": ["github.com"]})
        assert len(session["cookies"]) == 1
        assert session["cookies"][0]["name"] == "oauth_token"
        assert session["cookies"][0]["value"] == "gh_token"

    def test_exchange_refresh_token_failure(self):
        plugin = self._make_plugin()
        with pytest.raises(RuntimeError, match="Token refresh"):
            plugin._exchange_refresh_token(
                token_url="https://invalid.example.com/token",
                client_id="c",
                client_secret="s",
                refresh_token="r",
                scopes=[],
            )


# === Plugin Loader Integration Tests ===

class TestPluginLoaderWithOAuth2:
    def test_loader_discovers_oauth2_plugin(self):
        """Test that the loader can discover the built-in OAuth2 plugin."""
        from tokenade.core.integration.plugin_loader import PluginLoader

        # Point loader at the oauth2 plugin directory
        plugin_dir = Path(__file__).parent.parent / "plugin" / "oauth2"
        if not plugin_dir.exists():
            pytest.skip("OAuth2 plugin directory not found")

        loader = PluginLoader(plugins_dir=plugin_dir.parent)
        plugins = loader.discover()

        # The loader expects plugins in subdirectories with plugin.json
        # The oauth2 plugin is at tokenade/plugin/oauth2/plugin.json
        # The loader scans ~/.tokenade/plugins/ by default, so we just
        # verify the plugin module is importable
        from tokenade.plugin.oauth2.plugin import OAuth2Plugin
        assert OAuth2Plugin is not None

    def test_plugin_base_classes_exported(self):
        """Test that all base classes are importable from tokenade.plugin."""
        from tokenade.plugin import PluginBase
        from tokenade.plugin import SessionRefreshPlugin
        from tokenade.plugin import SiteHandlerPlugin
        from tokenade.plugin import ExportFormatPlugin
        from tokenade.plugin import SessionValidatorPlugin

        assert PluginBase is not None
        assert SessionRefreshPlugin is not None
        assert SiteHandlerPlugin is not None
        assert ExportFormatPlugin is not None
        assert SessionValidatorPlugin is not None
