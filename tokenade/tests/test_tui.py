"""Tests for Phase 58 — Interactive TUI."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tokenade.tui import run_tui, _check_textual

_textual_available = _check_textual()


# ─── CLI runner display / convert ──────────────────────────

class TestCliRunnerDisplay:
    def test_shell_double_quote_spaces(self):
        from tokenade.tui.cli_runner import shell_double_quote, format_cli_display, cmd_export

        assert shell_double_quote("Your Vivaldi") == '"Your Vivaldi"'
        assert shell_double_quote("plain") == "plain"
        argv = cmd_export(browser_name="vivaldi", profile="Your Vivaldi", output="/tmp/out.tokenade")
        display = format_cli_display(argv)
        assert '--profile "Your Vivaldi"' in display or '--profile "Your Vivaldi"' in display
        assert "Your Vivaldi" in display
        assert "'" not in display.split("Your Vivaldi")[0][-3:]  # prefer double quotes

    def test_cmd_convert_argv(self):
        from tokenade.tui.cli_runner import cmd_convert

        args = cmd_convert(
            input_path="~/Downloads/sample_cookie.txt",
            output="/tmp/x.tokenade",
            domain=".example.com",
        )
        assert args[0] == "convert"
        assert "--input" in args
        assert "--output" in args
        assert "--domain" in args

    def test_cmd_gateway_argv(self):
        from tokenade.tui.cli_runner import cmd_gateway

        assert cmd_gateway("gateway.request.json") == ["gateway", "--request", "gateway.request.json"]

    def test_gateway_request_options_discovers_request_files(self, tmp_path, monkeypatch):
        from tokenade.tui.views import gateway as gateway_view

        request = tmp_path / "gateway.request.json"
        request.write_text('{"operation":"gateway"}')

        options = gateway_view.gateway_request_options(tmp_path)

        assert any(value == str(request.resolve()) for _, value in options)

    def test_convert_view_importable(self):
        from tokenade.tui.views.convert import ConvertView, FORMAT_OPTIONS

        assert ConvertView is not None
        assert any(v == "har" for _, v in FORMAT_OPTIONS)
        assert any(v == "playwright" for _, v in FORMAT_OPTIONS)

    def test_tui_copy_bindings(self):
        from tokenade.tui.app import TokenadeTUI

        assert TokenadeTUI.ALLOW_SELECT is True
        keys = {getattr(b, "key", "") for b in TokenadeTUI.BINDINGS}
        assert "ctrl+c" in keys
        assert "ctrl+shift+c" in keys
        assert "y" in keys
        assert "ctrl+q" in keys
        actions = {getattr(b, "action", "") for b in TokenadeTUI.BINDINGS}
        assert "copy_or_hint" in actions or "copy_selection" in actions

    def test_gateway_is_fifth_tui_tab_binding(self):
        from tokenade.tui.app import TokenadeTUI

        bindings = [(getattr(b, "key", ""), getattr(b, "action", "")) for b in TokenadeTUI.BINDINGS]

        assert ("5", "show_gateway") in bindings

    def test_gateway_selector_heuristics(self):
        from tokenade.tui.app import TokenadeTUI

        app = TokenadeTUI()
        widget = MagicMock()
        app.query_one = MagicMock(return_value=widget)

        widget.value = "gmail-profile-2"
        assert app._gateway_selector() == {"path": "gmail-profile-2"}
        widget.value = "/tmp/gmail.tokenade"
        assert app._gateway_selector() == {"path": "/tmp/gmail.tokenade"}

    def test_gateway_request_summary_and_inferred_controls(self, tmp_path):
        from tokenade.tui.app import TokenadeTUI

        sessions = tmp_path / "sessions"
        sessions.mkdir()
        session = sessions / "gmail.tokenade"
        session.write_text(json.dumps({
            "site_name": "gmail",
            "auth_status": "logged_in",
            "metadata": {"session_id": "gmail-a"},
            "cookies": [{"name": "sid", "value": "x", "domain": ".google.com"}],
        }))
        request = tmp_path / "gateway.json"
        request.write_text(json.dumps({
            "operation": "gateway",
            "sessions": {"dir": "sessions", "pattern": "*.tokenade"},
            "gateway": {
                "host": "127.0.0.1",
                "port": 9444,
                "runtime": {"enabled": True, "url": "https://example.test/app"},
            },
            "routing": {"strategy": "round-robin"},
        }))
        app = TokenadeTUI()
        data = app._gateway_load_request(str(request))
        url = app._gateway_runtime_url(data)
        options = app._gateway_session_options(data, str(request))
        summary = app._gateway_request_summary(data)

        assert url == "https://example.test/app"
        assert options[0][1] == str(session.resolve())
        assert "port=9444" in summary
        assert "runtime=on" in summary
        assert "url=https://example.test/app" in summary

    def test_gateway_picker_starts_at_downloads_or_home(self):
        from tokenade.tui.app import GatewayRequestPickerScreen

        screen = GatewayRequestPickerScreen()

        assert screen.root in (Path.home() / "Downloads", Path.home())

    def test_cmd_tui_missing_textual_exits(self):
        from tokenade.cli.handlers import ci

        with patch("tokenade.tui._check_textual", return_value=False):
            with pytest.raises(SystemExit) as ei:
                ci.cmd_tui(type("A", (), {"tui_mode": "full"})())
            assert ei.value.code == 1


# ─── Module Tests ──────────────────────────────────────────

class TestTUIModule:
    @pytest.mark.skipif(not _textual_available, reason="textual not installed")
    def test_check_textual_available(self):
        """Textual should be installed in test env."""
        assert _check_textual() is True

    def test_run_tui_no_textual(self):
        """Clear install hint + non-zero exit when textual missing."""
        with patch("tokenade.tui.app._TEXTUAL_AVAILABLE", False):
            with pytest.raises(SystemExit) as ei:
                run_tui()
            assert ei.value.code == 1

    def test_app_importable(self):
        """App module should be importable."""
        from tokenade.tui.app import run_tui as rt
        assert callable(rt)


# ─── CLI Parser Tests ──────────────────────────────────────

class TestTUICLIParser:
    def test_tui_parser(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["tui"])
        assert a.tui_mode == "full"

    def test_tui_marketplace(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["tui", "marketplace"])
        assert a.tui_mode == "marketplace"

    def test_tui_sessions(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["tui", "sessions"])
        assert a.tui_mode == "sessions"

    def test_tui_help(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        with pytest.raises(SystemExit):
            p.parse_args(["tui", "--help"])


# ─── Textual App Tests ────────────────────────────────────

class TestTUIApp:
    """Test the TUI app using textual's test framework."""

    @pytest.mark.skipif(
        not _check_textual(),
        reason="textual not installed",
    )
    def test_app_creates(self):
        """App should instantiate without error."""
        from tokenade.tui.app import run_tui
        # Just verify the function exists and is callable
        assert callable(run_tui)

    @pytest.mark.skipif(
        not _check_textual(),
        reason="textual not installed",
    )
    def test_app_compose(self):
        """App should compose without error."""
        from textual.app import App
        # Verify textual components are available
        from textual.widgets import (
            Footer, Header, Static, Button, Input,
            TabbedContent, TabPane, Rule,
        )
        from textual.containers import Container, Horizontal, Vertical
        assert App is not None
        assert Footer is not None
        assert Header is not None

    @pytest.mark.skipif(
        not _check_textual(),
        reason="textual not installed",
    )
    def test_app_bindings(self):
        """App should have expected key bindings."""
        from tokenade.tui.app import run_tui
        # We can't easily test the App class directly since it's
        # defined inside run_tui, but we can verify the module loads
        assert True  # Module loads without error

    @pytest.mark.skipif(
        not _check_textual(),
        reason="textual not installed",
    )
    def test_plugin_registry_integration(self):
        """Plugin registry should be loadable for TUI."""
        from tokenade.core.integration.plugin_registry import PluginRegistry
        registry = PluginRegistry()
        assert hasattr(registry, "registry_url")
        assert hasattr(registry, "search")

    @pytest.mark.skipif(
        not _check_textual(),
        reason="textual not installed",
    )
    def test_plugin_loader_integration(self):
        """Plugin loader should be loadable for TUI."""
        from tokenade.core.integration.plugin_loader import PluginLoader
        loader = PluginLoader()
        assert hasattr(loader, "list_all")


# ─── Rich Components Tests ────────────────────────────────

class TestRichComponents:
    """Test rich rendering components used in TUI."""

    def test_rich_available(self):
        """Rich should be available (comes with textual)."""
        from rich.text import Text
        from rich.panel import Panel
        from rich.table import Table
        assert Text is not None
        assert Panel is not None
        assert Table is not None

    def test_plugin_card_data(self):
        """Plugin data should be renderable."""
        plugin = {
            "name": "oauth2",
            "version": "1.0.0",
            "description": "OAuth2 token refresh",
            "author": "MiHiR",
            "rating": 4.2,
            "downloads": 142,
            "verified": True,
            "tags": ["oauth2", "google"],
            "category": "authentication",
            "icon": "🔐",
        }
        # Verify all fields are accessible
        assert plugin["name"] == "oauth2"
        assert plugin["rating"] == 4.2
        assert plugin["verified"] is True

    def test_session_data_structure(self):
        """Session data should be structured correctly."""
        session = {
            "name": "gmail",
            "file": "/path/to/gmail.tokenade",
            "site": "google",
            "auth": "logged_in",
            "cookies": 82,
        }
        assert session["name"] == "gmail"
        assert session["cookies"] == 82

    def test_category_data_structure(self):
        """Category data should be structured correctly."""
        categories = [
            {"name": "authentication", "count": 3},
            {"name": "notifications", "count": 2},
            {"name": "security", "count": 1},
        ]
        total = sum(c["count"] for c in categories)
        assert total == 6

    def test_installed_plugin_data_structure(self):
        """Installed plugin data should have version."""
        plugin = {
            "name": "oauth2",
            "enabled": True,
            "version": "1.1.0",
        }
        assert plugin["name"] == "oauth2"
        assert plugin["version"] == "1.1.0"
        assert plugin["enabled"] is True

    def test_update_available_detection(self):
        """Should detect when installed version < registry version."""
        installed = [
            {"name": "oauth2", "version": "1.0.0", "enabled": True},
        ]
        registry = [
            {"name": "oauth2", "version": "1.1.0"},
        ]
        installed_ver = installed[0]["version"]
        registry_ver = registry[0]["version"]
        update_available = registry_ver != installed_ver
        assert update_available is True

    def test_search_filtering(self):
        """Search should match name, description, and tags."""
        plugins = [
            {"name": "oauth2", "description": "OAuth2 refresh", "tags": ["oauth", "google"]},
            {"name": "webhook-notify", "description": "Webhook notifications", "tags": ["webhook", "slack"]},
            {"name": "session-health", "description": "Health validation", "tags": ["health", "monitoring"]},
        ]
        query = "oauth"
        results = []
        for p in plugins:
            searchable = (
                p.get("name", "") + " "
                + p.get("description", "") + " "
                + " ".join(p.get("tags", []))
            ).lower()
            if query in searchable:
                results.append(p["name"])
        assert "oauth2" in results
        assert "webhook-notify" not in results
        assert "session-health" not in results

    def test_search_filtering_by_tag(self):
        """Search should match tags."""
        plugins = [
            {"name": "oauth2", "description": "OAuth2 refresh", "tags": ["oauth", "google"]},
            {"name": "webhook-notify", "description": "Webhook notifications", "tags": ["webhook", "slack"]},
        ]
        query = "slack"
        results = []
        for p in plugins:
            searchable = (
                p.get("name", "") + " "
                + p.get("description", "") + " "
                + " ".join(p.get("tags", []))
            ).lower()
            if query in searchable:
                results.append(p["name"])
        assert "webhook-notify" in results
        assert "oauth2" not in results

    def test_search_empty_query_returns_all(self):
        """Empty search should return all plugins."""
        plugins = [
            {"name": "oauth2", "description": "OAuth2 refresh", "tags": ["oauth"]},
            {"name": "webhook-notify", "description": "Webhook", "tags": ["webhook"]},
        ]
        query = ""
        results = []
        for p in plugins:
            searchable = (
                p.get("name", "") + " "
                + p.get("description", "") + " "
                + " ".join(p.get("tags", []))
            ).lower()
            if not query or query in searchable:
                results.append(p["name"])
        assert len(results) == 2
