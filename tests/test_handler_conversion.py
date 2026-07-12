"""Tests for plugin-format handler conversions.

Tests that the legacy Google, GitHub, and Generic OAuth2 handlers are
correctly wrapped as SiteHandlerPlugin adapters, can be instantiated
subclass SiteHandlerPlugin, return PluginResult from extract/inject,
and that the legacy loading still works.
"""

from unittest.mock import MagicMock, patch

import pytest

from tokenade.plugin.api import PluginResult
from tokenade.plugin.base import SiteHandlerPlugin
from tokenade.handlers.plugin_adapters import (
    GenericOAuth2HandlerAdapter,
    GitHubHandlerAdapter,
    GoogleHandlerAdapter,
    LegacyHandlerAdapter,
)


class TestGoogleHandlerAdapter:
    """Tests for GoogleHandlerAdapter."""

    def test_is_site_handler_plugin(self):
        adapter = GoogleHandlerAdapter()
        assert isinstance(adapter, SiteHandlerPlugin)

    def test_metadata(self):
        adapter = GoogleHandlerAdapter()
        assert adapter.name == "google-handler"
        assert adapter.version == "1.0.0"
        assert adapter.author == "MiHiR"
        assert adapter.API_VERSION == "1.1.0"

    def test_extract_session_returns_plugin_result(self):
        adapter = GoogleHandlerAdapter()

        # Mock the legacy handler's extract_cookies to avoid
        # actually opening a browser
        adapter._get_legacy = lambda ctx=None: MagicMock(
            extract_cookies=MagicMock(return_value=[{"name": "SID"}])
        )
        result = adapter.extract_session(None, url="https://google.com")

        assert isinstance(result, PluginResult)
        assert result.success is True
        assert "cookies" in result.data

    def test_extract_session_handles_errors(self):
        adapter = GoogleHandlerAdapter()

        def fail(): raise RuntimeError("network error")
        adapter._get_legacy = lambda ctx=None: MagicMock(
            extract_cookies=fail
        )
        result = adapter.extract_session(None, url="https://google.com")
        assert result.success is False

    def test_inject_session_returns_plugin_result(self):
        adapter = GoogleHandlerAdapter()
        mock_legacy = MagicMock()
        adapter._get_legacy = lambda ctx=None: mock_legacy

        result = adapter.inject_session(
            None, session={"cookies": [{"name": "SID", "value": "abc"}]}
        )
        assert isinstance(result, PluginResult)
        assert result.success is True
        assert result.data["injected_count"] == 1

    def test_validate_returns_plugin_result(self):
        adapter = GoogleHandlerAdapter()
        adapter._get_legacy = lambda ctx=None: MagicMock(
            validate_session=MagicMock(return_value=True)
        )
        result = adapter.validate({"cookies": [{"name": "SID"}]})
        assert isinstance(result, PluginResult)
        assert result.data["valid"] is True


class TestGitHubHandlerAdapter:
    """Tests for GitHubHandlerAdapter."""

    def test_is_site_handler_plugin(self):
        adapter = GitHubHandlerAdapter()
        assert isinstance(adapter, SiteHandlerPlugin)

    def test_metadata(self):
        adapter = GitHubHandlerAdapter()
        assert adapter.name == "github-handler"
        assert adapter.version == "1.0.0"
        assert adapter.API_VERSION == "1.1.0"

    def test_extract_session(self):
        adapter = GitHubHandlerAdapter()
        adapter._get_legacy = lambda ctx=None: MagicMock(
            extract_cookies=MagicMock(return_value=[{"name": "user_session"}])
        )
        result = adapter.extract_session(None, url="https://github.com")
        assert result.success is True
        assert result.data["cookies"][0]["name"] == "user_session"


class TestGenericOAuth2HandlerAdapter:
    """Tests for GenericOAuth2HandlerAdapter."""

    def test_is_site_handler_plugin(self):
        adapter = GenericOAuth2HandlerAdapter()
        assert isinstance(adapter, SiteHandlerPlugin)

    def test_metadata(self):
        adapter = GenericOAuth2HandlerAdapter()
        assert adapter.name == "generic-oauth-handler"

    def test_extract_session(self):
        adapter = GenericOAuth2HandlerAdapter()
        adapter._get_legacy = lambda ctx=None: MagicMock(
            extract_cookies=MagicMock(return_value=[])
        )
        result = adapter.extract_session(None, url="https://example.com")
        assert result.success is True
        assert result.data["cookies"] == []


class TestLegacyLoading:
    """Tests that legacy handler loading still works."""

    def test_resolve_legacy_handler_class_google(self):
        from tokenade.handlers.resolve import resolve_legacy_handler_class
        from tokenade.handlers.google import GoogleHandler

        handler_cls = resolve_legacy_handler_class("google")
        assert handler_cls is GoogleHandler

    def test_resolve_legacy_handler_class_github(self):
        from tokenade.handlers.resolve import resolve_legacy_handler_class
        from tokenade.handlers.github import GitHubHandler

        handler_cls = resolve_legacy_handler_class("github")
        assert handler_cls is GitHubHandler

    def test_resolve_legacy_handler_class_default(self):
        from tokenade.handlers.resolve import resolve_legacy_handler_class
        from tokenade.handlers.google import GoogleHandler

        # Default is Google when no site specified
        handler_cls = resolve_legacy_handler_class(None)
        assert handler_cls is GoogleHandler

    def test_resolve_legacy_handler_class_alias(self):
        from tokenade.handlers.resolve import resolve_legacy_handler_class
        from tokenade.handlers.google import GoogleHandler

        # "gmail" should alias to "google"
        handler_cls = resolve_legacy_handler_class("gmail")
        assert handler_cls is GoogleHandler

    def test_registry_can_create_google(self):
        # Ensure handlers are imported so they register
        import tokenade.handlers.google  # noqa: F401
        from tokenade.handlers.base import HandlerRegistry
        from tokenade.handlers.google import GoogleHandler

        # Explicitly register in case earlier tests cleared the registry
        HandlerRegistry.register(GoogleHandler)
        handler = HandlerRegistry.create("google")
        assert handler is not None

    def test_registry_can_create_github(self):
        # Ensure handlers are imported so they register
        import tokenade.handlers.github  # noqa: F401
        from tokenade.handlers.base import HandlerRegistry
        from tokenade.handlers.github import GitHubHandler

        # Explicitly register in case earlier tests cleared the registry
        HandlerRegistry.register(GitHubHandler)
        handler = HandlerRegistry.create("github")
        assert handler is not None


class TestSiteConfigs:
    """Tests that site_config.json files exist and are valid."""

    def test_google_site_config(self):
        import json
        from pathlib import Path

        config_path = Path(__file__).parent.parent / "tokenade" / "handlers" / "site_configs" / "google.json"
        assert config_path.exists(), f"Site config not found at {config_path}"

        with open(config_path) as f:
            config = json.load(f)
        assert config["name"] == "google"
        assert "google.com" in config["domains"]
        assert "SID" in config["critical_cookies"]

    def test_github_site_config(self):
        import json
        from pathlib import Path

        config_path = Path(__file__).parent.parent / "tokenade" / "handlers" / "site_configs" / "github.json"
        assert config_path.exists(), f"Site config not found at {config_path}"

        with open(config_path) as f:
            config = json.load(f)
        assert config["name"] == "github"
        assert "github.com" in config["domains"]
        assert "user_session" in config["critical_cookies"]

    def test_generic_oauth_site_config(self):
        import json
        from pathlib import Path

        config_path = Path(__file__).parent.parent / "tokenade" / "handlers" / "site_configs" / "generic_oauth.json"
        assert config_path.exists(), f"Site config not found at {config_path}"

        with open(config_path) as f:
            config = json.load(f)
        assert config["name"] == "generic-oauth"
