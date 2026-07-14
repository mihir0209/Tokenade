"""Tests for Tokenade Plugin System — Base Classes and OAuth2 Plugin."""
import os
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

class ConcreteRefreshPlugin(SessionRefreshPlugin):
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


class ConcreteSiteHandler(SiteHandlerPlugin):
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


class ConcreteExportFormat(ExportFormatPlugin):
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


class ConcreteValidator(SessionValidatorPlugin):
    """Concrete test implementation of SessionValidatorPlugin."""
    name = "test-validator"
    version = "1.0.0"
    description = "Test validator"

    def validate(self, session):
        return {"valid": True, "score": 100.0, "issues": []}


# === PluginBase Tests ===

class TestPluginBase:
    def test_base_class_structure(self):
        plugin = ConcreteRefreshPlugin()
        assert hasattr(plugin, "name")
        assert hasattr(plugin, "version")
        assert hasattr(plugin, "description")
        assert hasattr(plugin, "on_load")
        assert hasattr(plugin, "on_unload")
        assert hasattr(plugin, "get_info")

    def test_plugin_metadata(self):
        plugin = ConcreteRefreshPlugin()
        assert plugin.name == "test-refresh"
        assert plugin.version == "1.0.0"
        assert plugin.description == "Test refresh plugin"

    def test_get_info(self):
        plugin = ConcreteRefreshPlugin()
        info = plugin.get_info()
        assert info["name"] == "test-refresh"
        assert info["version"] == "1.0.0"
        assert info["description"] == "Test refresh plugin"

    def test_lifecycle_hooks(self):
        plugin = ConcreteRefreshPlugin()
        # Should not raise
        plugin.on_load()
        plugin.on_unload()


# === SessionRefreshPlugin Tests ===

class TestSessionRefreshPlugin:
    def test_can_refresh(self):
        plugin = ConcreteRefreshPlugin()
        assert plugin.can_refresh({"site_name": "test-site"}) is True
        assert plugin.can_refresh({"site_name": "other"}) is False

    def test_refresh(self):
        plugin = ConcreteRefreshPlugin()
        session = {"site_name": "test-site", "cookies": []}
        result = plugin.refresh(session, {})
        assert result["metadata"]["refreshed"] is True

    def test_get_credentials_args(self):
        plugin = ConcreteRefreshPlugin()
        args = plugin.get_credentials_args()
        assert len(args) == 1
        assert args[0]["name"] == "--api-key"
        assert args[0]["required"] is True

    def test_inheritance(self):
        plugin = ConcreteRefreshPlugin()
        assert isinstance(plugin, PluginBase)
        assert isinstance(plugin, SessionRefreshPlugin)


# === SiteHandlerPlugin Tests ===

class TestSiteHandlerPlugin:
    def test_can_handle(self):
        plugin = ConcreteSiteHandler()
        assert plugin.can_handle("https://example.com/page") is True
        assert plugin.can_handle("https://other.com/page") is False

    def test_extract_session(self):
        plugin = ConcreteSiteHandler()
        session = plugin.extract_session(None, "https://example.com")
        assert "cookies" in session
        assert session["site_name"] == "test"

    def test_inject_session(self):
        plugin = ConcreteSiteHandler()
        assert plugin.inject_session(None, {"cookies": []}) is True


# === ExportFormatPlugin Tests ===

class TestExportFormatPlugin:
    def test_get_format_name(self):
        plugin = ConcreteExportFormat()
        assert plugin.get_format_name() == "test-format"

    def test_export(self, tmp_path):
        plugin = ConcreteExportFormat()
        output = tmp_path / "output.txt"
        result = plugin.export({"cookies": []}, str(output))
        assert os.path.isfile(result)
        assert open(result).read() == "test output"


# === SessionValidatorPlugin Tests ===

class TestSessionValidatorPlugin:
    def test_validate(self):
        plugin = ConcreteValidator()
        result = plugin.validate({"cookies": []})
        assert result["valid"] is True
        assert result["score"] == 100.0
        assert result["issues"] == []


# === Plugin Loader Integration Tests ===

class TestPluginLoaderWithOAuth2:
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
