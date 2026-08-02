"""Screenshot-based TUI tests.

Uses Textual's run_test pilot + SVG export to prove each tab renders
real data (marketplace plugins, sessions, vault entries, etc.).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tokenade.tui import _check_textual

_textual_available = _check_textual()
SHOT_DIR = Path(__file__).resolve().parent / "tui_screenshots"


@pytest.fixture(autouse=True)
def _shot_dir():
    SHOT_DIR.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def isolated_tokenade(tmp_path, monkeypatch):
    """Point TUI paths at a temp tree with sample sessions."""
    root = tmp_path / ".tokenade"
    sessions = root / "sessions"
    vault = root / "vault"
    analytics = root / "analytics"
    plugins = root / "plugins"
    for d in (sessions, vault, analytics, plugins):
        d.mkdir(parents=True)

    sample = {
        "site_name": "example.com",
        "auth_status": "logged_in",
        "cookies": [
            {"name": "sid", "value": "abc", "domain": ".example.com", "expires": 9999999999},
            {"name": "old", "value": "x", "domain": ".example.com", "expires": 1},
        ],
    }
    (sessions / "example-session.tokenade").write_text(json.dumps(sample))

    monkeypatch.setenv("TOKENADE_DIR", str(root))
    monkeypatch.setenv("TOKENADE_SESSIONS_DIR", str(sessions))
    monkeypatch.setenv("TOKENADE_VAULT_DIR", str(vault))
    monkeypatch.setenv("TOKENADE_ANALYTICS_DIR", str(analytics))
    monkeypatch.setenv("TOKENADE_PLUGINS_DIR", str(plugins))

    # Reload config module so paths pick up env
    import importlib
    import tokenade.tui.config as cfg
    importlib.reload(cfg)
    import tokenade.tui.views.sessions as sess_mod
    importlib.reload(sess_mod)
    import tokenade.tui.views.marketplace as mkt_mod
    importlib.reload(mkt_mod)
    import tokenade.tui.views.installed as inst_mod
    importlib.reload(inst_mod)
    import tokenade.tui.views.share as share_mod
    importlib.reload(share_mod)
    import tokenade.tui.views.settings as set_mod
    importlib.reload(set_mod)
    import tokenade.tui.app as app_mod
    importlib.reload(app_mod)

    # Seed vault with one entry
    from tokenade.core.vault.vault import SessionVault, VaultConfig
    v = SessionVault(VaultConfig(vault_path=str(vault)))
    v.store("vault-demo", b'{"cookies":[]}', metadata={"site": "demo"})

    return {
        "root": root,
        "sessions": sessions,
        "vault": vault,
        "analytics": analytics,
        "app_mod": app_mod,
        "cfg": cfg,
    }


def _svg_text(app) -> str:
    """Export current screen as SVG string (Textual API varies by version)."""
    try:
        return app.export_screenshot(title="tokenade-tui")
    except TypeError:
        return app.export_screenshot()


def _save_shot(name: str, svg: str) -> Path:
    path = SHOT_DIR / f"{name}.svg"
    path.write_text(svg)
    return path


def _widget_text(widget) -> str:
    """Best-effort plain text from a Textual widget or container."""
    parts: list[str] = []
    content = getattr(widget, "content", None)
    if content is not None:
        parts.append(str(content))
    try:
        for child in widget.children:
            parts.append(_widget_text(child))
    except Exception:
        pass
    return "\n".join(parts)


@pytest.mark.skipif(not _textual_available, reason="textual not installed")
class TestTUIScreenshots:
    """End-to-end TUI tab screenshots with content assertions."""

    @pytest.mark.asyncio
    async def test_marketplace_shows_plugins(self, isolated_tokenade):
        fake_plugins = [
            {
                "name": "auto-refresh",
                "version": "1.2.0",
                "description": "Auto refresh sessions",
                "author": "tokenade",
                "icon": "🔄",
            },
            {
                "name": "cookie-export",
                "version": "1.1.0",
                "description": "Export cookies",
                "author": "tokenade",
                "icon": "🍪",
            },
        ]
        app_mod = isolated_tokenade["app_mod"]
        with patch(
            "tokenade.core.integration.plugin_registry.PluginRegistry.get_popular",
            return_value=fake_plugins,
        ), patch(
            "tokenade.core.integration.plugin_registry.PluginRegistry.search",
            return_value=fake_plugins,
        ):
            app = app_mod.TokenadeTUI()
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                # Force reload after mount in case first load raced
                app._load_data()
                await pilot.pause()
                svg = _svg_text(app)
                _save_shot("01-marketplace", svg)
                # Prefer grid; fall back to list
                try:
                    host = app.query_one("#plugin-grid")
                except Exception:
                    host = app.query_one("#plugin-list")
                cards = list(host.query("PluginCard"))
                assert len(cards) >= 2, f"expected plugin cards, got {len(cards)}"
                names = {c.plugin.get("name") for c in cards}
                assert "auto-refresh" in names
                assert "cookie-export" in names

    @pytest.mark.asyncio
    async def test_sessions_tab_lists_files(self, isolated_tokenade):
        app_mod = isolated_tokenade["app_mod"]
        with patch(
            "tokenade.core.integration.plugin_registry.PluginRegistry.get_popular",
            return_value=[],
        ):
            app = app_mod.TokenadeTUI()
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.action_show_sessions()
                await pilot.pause()
                app._load_sessions()
                app._update_sessions()
                await pilot.pause()
                svg = _svg_text(app)
                _save_shot("02-sessions", svg)
                assert any(s["name"] == "example-session" for s in app._sessions)
                try:
                    host = app.query_one("#session-grid")
                except Exception:
                    host = app.query_one("#sessions-list")
                tiles = list(host.query("SessionTile"))
                text_blob = _widget_text(host)
                assert tiles or "example-session" in text_blob or "example-session" in svg
                if tiles:
                    assert any(t.session.get("name") == "example-session" for t in tiles)

    @pytest.mark.asyncio
    async def test_vault_tab_lists_entries(self, isolated_tokenade):
        app_mod = isolated_tokenade["app_mod"]
        with patch(
            "tokenade.core.integration.plugin_registry.PluginRegistry.get_popular",
            return_value=[],
        ):
            app = app_mod.TokenadeTUI()
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.action_show_vault()
                await pilot.pause()
                app._update_vault()
                await pilot.pause()
                svg = _svg_text(app)
                _save_shot("03-vault", svg)
                text_blob = _widget_text(app.query_one("#vault-list"))
                assert "vault-demo" in text_blob or "vault-demo" in svg

    @pytest.mark.asyncio
    async def test_settings_shows_canonical_paths(self, isolated_tokenade):
        app_mod = isolated_tokenade["app_mod"]
        cfg = isolated_tokenade["cfg"]
        with patch(
            "tokenade.core.integration.plugin_registry.PluginRegistry.get_popular",
            return_value=[],
        ):
            app = app_mod.TokenadeTUI()
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.action_show_settings()
                await pilot.pause()
                app._update_settings()
                await pilot.pause()
                svg = _svg_text(app)
                _save_shot("04-settings", svg)
                sessions_txt = str(app.query_one("#settings-sessions-dir").content)
                assert str(cfg.SESSIONS_DIR) in sessions_txt or "sessions" in sessions_txt
                assert "/tmp/real-sessions" not in sessions_txt
                assert "/tmp/real-sessions" not in svg
                # Real controls present
                assert app.query_one("#settings-save") is not None
                assert app.query_one("#settings-automation-browser") is not None
                assert app.query_one("#settings-stealth-level") is not None

    @pytest.mark.asyncio
    async def test_share_list_renders(self, isolated_tokenade):
        app_mod = isolated_tokenade["app_mod"]
        with patch(
            "tokenade.core.integration.plugin_registry.PluginRegistry.get_popular",
            return_value=[],
        ), patch(
            "tokenade.core.sharing.url_shortener.SessionURLShortener.list_shares",
            return_value=[
                {"short_id": "abc123xyz", "current_uses": 0, "max_uses": 5},
            ],
        ):
            app = app_mod.TokenadeTUI()
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.action_show_share()
                await pilot.pause()
                # Password fields must exist
                pw = app.query_one("#share-password-input")
                assert pw is not None
                conf = app.query_one("#share-password-confirm")
                assert conf is not None
                # Session picker (Select) or fallback Static
                picker = app.query_one("#share-session-select")
                assert picker is not None
                app._share_list()
                await pilot.pause()
                svg = _svg_text(app)
                _save_shot("05-share", svg)
                text_blob = _widget_text(app.query_one("#share-result"))
                assert "abc123xyz" in text_blob or "abc123xyz" in svg

    @pytest.mark.asyncio
    async def test_plugin_detail_shows_metadata(self, isolated_tokenade):
        app_mod = isolated_tokenade["app_mod"]
        plugin = {
            "name": "auto-refresh",
            "version": "1.2.0",
            "description": "CloakBrowser live session revalidation",
            "author": "Tokenade Team",
            "type": "session_refresh",
            "category": "authentication",
            "tags": ["refresh", "daemon"],
            "entry_point": "plugin.py",
            "entry_class": "AutoRefreshPlugin",
            "icon": "🔄",
            "downloads": 3,
            "verified": False,
            "_registry": "official",
        }
        with patch(
            "tokenade.core.integration.plugin_registry.PluginRegistry.get_popular",
            return_value=[plugin],
        ), patch(
            "tokenade.core.integration.plugin_registry.PluginRegistry.get_plugin_details",
            return_value=plugin,
        ):
            app = app_mod.TokenadeTUI()
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.push_screen(app_mod.PluginDetailScreen(plugin))
                await pilot.pause()
                svg = _svg_text(app)
                _save_shot("07-plugin-detail", svg)
                body = _widget_text(app.screen)
                assert "auto-refresh" in body or "auto-refresh" in svg
                assert "Tokenade Team" in body or "Tokenade Team" in svg
                assert "session_refresh" in body or "session_refresh" in svg
                assert "authentication" in body or "authentication" in svg

    @pytest.mark.asyncio
    async def test_analytics_report_renders(self, isolated_tokenade):
        app_mod = isolated_tokenade["app_mod"]
        from tokenade.core.analytics.engine import AnalyticsReport

        fake = AnalyticsReport(
            period_days=30,
            total_events=12,
            total_exports=5,
            total_loads=4,
            total_shares=2,
            total_syncs=1,
            success_rate=0.95,
            top_sites=[{"site": "example.com", "events": 7}],
        )
        with patch(
            "tokenade.core.integration.plugin_registry.PluginRegistry.get_popular",
            return_value=[],
        ), patch(
            "tokenade.core.analytics.engine.AnalyticsEngine.generate_report",
            return_value=fake,
        ):
            app = app_mod.TokenadeTUI()
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.action_show_analytics()
                await pilot.pause()
                app._analytics_report()
                await pilot.pause()
                svg = _svg_text(app)
                _save_shot("06-analytics", svg)
                text_blob = _widget_text(app.query_one("#analytics-result"))
                assert "Total events: 12" in text_blob or "12" in text_blob


@pytest.mark.skipif(not _textual_available, reason="textual not installed")
class TestConfigPaths:
    def test_defaults_under_home_tokenade(self, monkeypatch):
        monkeypatch.delenv("TOKENADE_DIR", raising=False)
        monkeypatch.delenv("TOKENADE_SESSIONS_DIR", raising=False)
        import importlib
        import tokenade.tui.config as cfg
        importlib.reload(cfg)
        assert cfg.SESSIONS_DIR == Path.home() / ".tokenade" / "sessions"
        assert cfg.VAULT_DIR == Path.home() / ".tokenade" / "vault"
        assert "/tmp/real-sessions" not in str(cfg.SESSIONS_DIR)

    def test_load_sessions_helper(self, tmp_path):
        from tokenade.tui.views.sessions import load_sessions
        sdir = tmp_path / "sessions"
        sdir.mkdir()
        (sdir / "a.tokenade").write_text(json.dumps({
            "site_name": "a.com",
            "auth_status": "logged_in",
            "cookies": [{"expires": 9999999999}],
        }))
        rows = load_sessions(sdir)
        assert len(rows) == 1
        assert rows[0]["name"] == "a"
        assert rows[0]["site"] == "a.com"
