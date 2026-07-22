"""
Tokenade TUI — Interactive terminal interface.

Provides a rich terminal UI for browsing the plugin marketplace,
managing installed plugins, viewing sessions, and configuring settings.

Usage:
    tokenade tui                    # Launch full TUI
    tokenade tui marketplace        # Launch marketplace only
    tokenade tui sessions           # Launch session manager only

Requires: pip install textual
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# ── Module-level textual imports (for Phase 10 new classes) ────────────────
# These are optional; if textual is not installed, the classes still exist
# but cannot be instantiated. Tests can import them and skip when not available.
try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Horizontal, Vertical
    from textual.screen import Screen
    from textual.widgets import (
        Button, Header, Footer, Input, Rule, Static, TabbedContent, TabPane,
        Label, LoadingIndicator, DataTable, ListView, ListItem,
    )
    from textual.widget import Widget
    from textual.reactive import reactive
    from textual import on
    _TEXTUAL_AVAILABLE = True
except ImportError:
    _TEXTUAL_AVAILABLE = False
    # Stub classes so the module still imports without textual

    class App:
        pass

    class ComposeResult:
        pass

    class Binding:
        def __init__(self, *args, **kwargs):
            pass

    class Container:
        pass

    class Horizontal:
        pass

    class Vertical:
        pass

    class Screen:
        pass

    class Button:
        class Pressed:
            pass

    class Header:
        pass

    class Footer:
        pass

    class Input:
        pass

    class Rule:
        pass

    class Static:
        pass

    class TabbedContent:
        pass

    class TabPane:
        pass

    class Label:
        pass

    class LoadingIndicator:
        pass

    class DataTable:
        pass

    class ListView:
        pass

    class ListItem:
        pass

    class MarketplaceView:
        pass

    class InstalledView:
        pass

    class Widget:
        pass

    class reactive:
        pass

    def on(*a, **k):
        def decorator(f):
            return f
        return decorator


def _check_textual():
    """Check if textual is available."""
    try:
        import textual  # noqa: F401
        return True
    except ImportError:
        return False


# ════════════════════════════════════════════════════════════════════════════
# Phase 10 — Module-level classes (importable by tests)
# ════════════════════════════════════════════════════════════════════════════


class PluginHealthWidget(Widget if _TEXTUAL_AVAILABLE else object):
    """Visualizes plugin health scores for all installed plugins."""

    def __init__(self, installed: List[Dict[str, Any]], **kwargs):
        super().__init__(**kwargs) if _TEXTUAL_AVAILABLE else None
        self.installed = installed

    def render(self):
        lines = ["Plugin Health"]
        if not self.installed:
            return "  No plugins installed."
        for p in self.installed:
            name = p.get("name", "?")
            health = p.get("health")
            if health is True:
                status = "💚 Healthy"
            elif health is False:
                status = "💔 Unhealthy"
            else:
                status = "⚪ unknown"
            err = p.get("error") if health is False else ""
            line = f"  • {name}: {status}"
            if err:
                line += f"  ({err[:40]}{'...' if len(err) > 40 else ''})"
            lines.append(line)
        return "\n".join(lines)

    @property
    def lines_count(self) -> int:
        return max(1, len(self.installed) + 1)


class PluginConfigWidget(Widget if _TEXTUAL_AVAILABLE else object):
    """Visualizes plugin config (sensitive values redacted)."""

    SENSITIVE_KEYS = {"password", "secret", "token", "api_key", "client_secret"}

    def __init__(self, installed: List[Dict[str, Any]], **kwargs):
        super().__init__(**kwargs) if _TEXTUAL_AVAILABLE else None
        self.installed = installed

    def render(self):
        lines = ["Plugin Configuration"]
        if not self.installed:
            return "  No plugins installed."
        for p in self.installed:
            name = p.get("name", "?")
            cfg = p.get("config") or {}
            if not cfg:
                lines.append(f"  • {name}: [no configuration]")
                continue
            lines.append(f"  • {name}:")
            for k, v in sorted(cfg.items()):
                if any(s in k.lower() for s in self.SENSITIVE_KEYS):
                    lines.append(f"      {k}: [redacted]")
                else:
                    lines.append(f"      {k}: {v}")
        return "\n".join(lines)


class PluginTaskWidget(Widget if _TEXTUAL_AVAILABLE else object):
    """Visualizes active + recent plugin tasks from the TaskTracker."""

    def __init__(self, installed: List[Dict[str, Any]], **kwargs):
        super().__init__(**kwargs) if _TEXTUAL_AVAILABLE else None
        self.installed = installed

    def render(self):
        lines = ["Plugin Tasks"]
        try:
            from tokenade.core.context import SharedContext
            ctx = SharedContext()
            tasks = ctx.tasks.list_all() if hasattr(ctx.tasks, "list_all") else []
            active = [t for t in tasks if t.get("status") == "running"]
            recent = [t for t in tasks if t.get("status") != "running"]
            if active:
                lines.append("  Active:")
                for t in active[:10]:
                    lines.append(
                        f"    • {t.get('plugin', '?')}: {t.get('name', '?')} "
                        f"(started: {t.get('started', '?')})"
                    )
            if recent:
                lines.append("  Recent:")
                for t in recent[:10]:
                    status_icon = "✅" if t.get("status") == "completed" else "❌"
                    lines.append(
                        f"    • {status_icon} {t.get('plugin', '?')}: {t.get('name', '?')} "
                        f"({t.get('status', '?')})"
                    )
            if not active and not recent:
                lines.append("  No tasks recorded.")
        except Exception:
            lines.append("  Task tracker unavailable.")
        return "\n".join(lines)


class MarketplaceView(Vertical if _TEXTUAL_AVAILABLE else object):
    """Plugin marketplace browse view."""

    def compose(self):
        if not _TEXTUAL_AVAILABLE:
            return
        yield Static("🔌  Plugin Marketplace", classes="card-title")
        yield Rule()
        yield Container(id="marketplace-content")


class InstalledView(Vertical if _TEXTUAL_AVAILABLE else object):
    """Installed plugins management view."""

    def compose(self):
        if not _TEXTUAL_AVAILABLE:
            return
        yield Static("📦  Installed Plugins", classes="card-title")
        yield Rule()
        yield Container(id="installed-content")


class RegistriesView(Vertical if _TEXTUAL_AVAILABLE else object):
    """Registry management view — primary surface for registry ops."""

    def compose(self):
        if not _TEXTUAL_AVAILABLE:
            return
        yield Static("🗄  Registries", classes="card-title")
        yield Rule()
        yield Container(id="registries-list")
        yield Rule()
        yield Static("Add Registry:")
        yield Horizontal(
            Input(placeholder="https://github.com/org/plugins", id="registry-add-url"),
            Input(placeholder="priority (int)", id="registry-add-priority", type="integer"),
            Button("Add", variant="primary", compact=True, id="registry-add-btn"),
        )


class PluginConfigScreen(Screen if _TEXTUAL_AVAILABLE else object):
    """Configuration editor for a specific plugin."""

    DEFAULT_CSS = """
    PluginConfigScreen {
        align: center middle;
    }
    PluginConfigScreen Container {
        width: 70;
        height: auto;
        max-height: 40;
        background: $surface;
        border: tall $primary;
        padding: 1 2;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, plugin_name: str, **kwargs):
        super().__init__(**kwargs) if _TEXTUAL_AVAILABLE else None
        self.plugin_name = plugin_name
        self._config = {}

    def compose(self):
        if not _TEXTUAL_AVAILABLE:
            return
        from tokenade.core.integration.plugin_config import PluginConfigManager
        mgr = PluginConfigManager()
        self._config = mgr.get_full_config(self.plugin_name) or {}
        schema = mgr.get_schema(self.plugin_name) or {}

        yield Container(
            Static(f"Configure: {self.plugin_name}", classes="card-title"),
            Rule(),
        )
        if not schema:
            yield Container(
                Static("  No configurable schema for this plugin."),
                Static("  Use CLI: tokenade plugin configure", classes="card-meta"),
            )
        for key, spec in sorted(schema.items()):
            default = spec.get("default", "")
            current = self._config.get(key, default)
            label = spec.get("description", spec.get("type", ""))
            yield Container(
                Static(f"  {key} ({label}):"),
                Input(value=str(current), id=f"cfg-{key}"),
            )
        yield Container(
            Horizontal(
                Button("Save", variant="success", id="cfg-save"),
                Button("Reset to Defaults", variant="warning", id="cfg-reset"),
                Button("Cancel", variant="default", id="cfg-cancel"),
            ),
        )

    @on(Button.Pressed, "#cfg-save")
    def save_config(self):
        from tokenade.core.integration.plugin_config import PluginConfigManager
        mgr = PluginConfigManager()
        schema = mgr.get_schema(self.plugin_name) or {}
        new_cfg = {}
        for key, spec in schema.items():
            try:
                inp = self.query_one(f"#cfg-{key}", Input)
                raw = inp.value
                t = spec.get("type", "string")
                if t == "integer":
                    new_cfg[key] = int(raw)
                elif t == "number":
                    new_cfg[key] = float(raw)
                elif t == "boolean":
                    new_cfg[key] = raw.lower() in ("true", "1", "yes", "on")
                else:
                    new_cfg[key] = raw
            except Exception:
                pass
        ok = mgr.save_config(self.plugin_name, new_cfg)
        if ok:
            self.app.notify(f"✅ Config saved: {self.plugin_name}")
            self.app.pop_screen()
        else:
            self.app.notify("❌ Failed to save config", severity="error")

    @on(Button.Pressed, "#cfg-reset")
    def reset_config(self):
        from tokenade.core.integration.plugin_config import PluginConfigManager
        mgr = PluginConfigManager()
        if mgr.delete_config(self.plugin_name):
            self.app.notify(f"✅ Reset to defaults: {self.plugin_name}")
        self.app.pop_screen()

    @on(Button.Pressed, "#cfg-cancel")
    def cancel_config(self):
        self.app.pop_screen()

    def action_cancel(self):
        self.app.pop_screen()


# ════════════════════════════════════════════════════════════════════════════


def run_tui(mode: str = "full"):
    """Launch the TUI application."""
    if not _check_textual():
        print("TUI requires textual: pip install 'tokenade[tui]'")
        print("Or use: tokenade plugin browse (static HTML)")
        return

    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Horizontal, Vertical
    from textual.screen import Screen
    from textual.widgets import (
        Footer, Header, Static, Button, Input,
        TabbedContent, TabPane, Rule,
    )
    from textual.widget import Widget
    from textual.reactive import reactive
    from textual import on

    # ── Plugin Card Widget ────────────────────────────────────

    class PluginCard(Widget):
        """A card widget displaying a single plugin."""

        DEFAULT_CSS = """
        PluginCard {
            height: auto;
            min-height: 3;
            max-height: 5;
            margin: 0 0;
            padding: 0 1;
            background: $surface;
            border-bottom: tall $primary-background-lighten-2;
        }
        PluginCard:hover {
            background: $surface-lighten-1;
        }
        PluginCard:focus {
            background: $surface-lighten-1;
            border-bottom: tall $accent;
        }
        PluginCard .card-title {
            text-style: bold;
            color: $text;
        }
        PluginCard .card-desc {
            color: $text-muted;
            height: 0;
            overflow: hidden;
        }
        PluginCard .card-desc.expanded {
            height: auto;
            overflow: visible;
        }
        PluginCard .card-meta {
            color: $text-muted;
        }
        PluginCard .card-tags {
            height: 0;
            overflow: hidden;
        }
        PluginCard .card-actions {
            height: auto;
            margin: 0;
        }
        PluginCard .badge-installed {
            color: $success;
        }
        PluginCard .badge-update {
            color: $warning;
        }
        """

        def __init__(self, plugin: Dict[str, Any], installed: bool = False,
                     update_available: bool = False, **kwargs):
            super().__init__(**kwargs)
            self.plugin = plugin
            self.installed = installed
            self.update_available = update_available
            self.can_focus = True

        def compose(self) -> ComposeResult:
            p = self.plugin
            icon = p.get("icon", "📦")
            name = p.get("name", "unknown")
            version = p.get("version", "?")
            desc = p.get("description", "No description")
            author = p.get("author", "Unknown")
            verified = p.get("verified", False)
            verified_str = " ✓" if verified else " (unverified)"
            # rating/downloads omitted until real telemetry exists
            social = ""
            if p.get("rating") is not None:
                rating = float(p["rating"])
                social += f"  {'★' * int(rating)}{'☆' * (5 - int(rating))} {rating:.1f}"
            if p.get("downloads") is not None:
                social += f"  {p['downloads']}↓"

            # Badges
            badges = ""
            if self.installed:
                badges += " [installed]"
            if self.update_available:
                badges += " [update]"

            yield Static(
                f"{icon} {name} v{version}{verified_str}{social}  by {author}"
                f"{badges}",
                classes="card-title",
            )
            yield Static(desc[:80], classes="card-desc", id=f"desc-{name}")
            yield Horizontal(
                Button(
                    "Update" if self.update_available else
                    ("Installed" if self.installed else "Install"),
                    variant="warning" if self.update_available else
                    ("default" if self.installed else "success"),
                    compact=True,
                    id=f"install-{name}",
                    disabled=self.installed and not self.update_available,
                ),
                Button("Details", variant="default", compact=True,
                       id=f"details-{name}"),
                classes="card-actions",
            )

    # ── Category Sidebar ──────────────────────────────────────

    class CategorySidebar(Widget):
        """Sidebar with plugin categories."""

        DEFAULT_CSS = """
        CategorySidebar {
            width: 25;
            min-width: 20;
            background: $surface-darken-1;
            border-right: tall $primary-background-lighten-2;
            padding: 1 0;
        }
        CategorySidebar .sidebar-title {
            text-style: bold;
            color: $primary;
            padding: 0 1;
            margin: 0 0 1 0;
        }
        CategorySidebar .category-item {
            padding: 0 2;
            color: $text-muted;
        }
        CategorySidebar .category-item:hover {
            background: $surface-lighten-1;
            color: $text;
        }
        CategorySidebar .category-active {
            background: $primary-background-darken-2;
            color: $primary;
            text-style: bold;
        }
        CategorySidebar .registry-info {
            padding: 1 2;
            color: $text-muted;
            margin: 2 0 0 0;
        }
        """

        categories = reactive([])
        active_category = reactive("all")

        def compose(self) -> ComposeResult:
            yield Static("📂 Categories", classes="sidebar-title")
            yield Static("", id="category-list")
            yield Rule()
            yield Static("", classes="registry-info", id="registry-info")

        def update_categories(self, cats: List[Dict[str, Any]]):
            self.categories = cats
            self._render_categories()

        def _render_categories(self):
            list_el = self.query_one("#category-list")
            total = sum(c.get("count", 0) for c in self.categories)
            lines = [f"  {'▸' if self.active_category == 'all' else ' '} All ({total})"]
            for cat in self.categories:
                name = cat.get("name", "")
                count = cat.get("count", 0)
                active = self.active_category == name
                icon = "▸" if active else " "
                lines.append(f"  {icon} {name.title()} ({count})")
            list_el.update("\n".join(lines))

        def update_registry(self, url: str):
            info = self.query_one("#registry-info")
            short = url.split("/")[-2:] if "/" in url else [url]
            info.update(f"  Registry:\n  {'/'.join(short)[-30:]}")

    # ── Status Bar ────────────────────────────────────────────

    class StatusBar(Widget):
        """Bottom status bar with context info."""

        DEFAULT_CSS = """
        StatusBar {
            height: 1;
            background: $surface-darken-2;
            color: $text-muted;
            padding: 0 1;
            dock: bottom;
        }
        """

        text = reactive("")

        def render(self):
            return self.text

    # ── Plugin Detail View ────────────────────────────────────

    class PluginDetailScreen(Screen):
        """Full-screen plugin detail view."""

        DEFAULT_CSS = """
        PluginDetailScreen {
            background: $surface;
        }
        PluginDetailScreen .detail-header {
            text-style: bold;
            color: $primary;
            padding: 1 2;
        }
        PluginDetailScreen .detail-body {
            padding: 0 2;
        }
        PluginDetailScreen .detail-meta {
            color: $text-muted;
            margin: 0 0 1 0;
        }
        PluginDetailScreen .detail-desc {
            margin: 0 0 1 0;
        }
        PluginDetailScreen .detail-tags {
            color: $warning;
            margin: 0 0 1 0;
        }
        PluginDetailScreen .detail-actions {
            margin: 2 0 0 0;
        }
        """

        BINDINGS = [
            Binding("b", "back", "Back"),
            Binding("escape", "back", "Back"),
            Binding("i", "install", "Install"),
            Binding("r", "rate", "Rate"),
        ]

        def __init__(self, plugin: Dict[str, Any], **kwargs):
            super().__init__(**kwargs)
            self.plugin = plugin

        def compose(self) -> ComposeResult:
            p = self.plugin
            icon = p.get("icon", "📦")
            name = p.get("name", "unknown")
            version = p.get("version", "?")
            desc = p.get("description", "No description")
            author = p.get("author", "Unknown")
            verified = p.get("verified", False)
            tags = p.get("tags", [])
            category = p.get("category", "")
            ptype = p.get("type", "")
            min_ver = p.get("min_version", "")
            deps = p.get("dependencies", [])
            state = p.get("state", "unknown")
            health = p.get("health")
            error = p.get("error")
            cfg = p.get("config") or {}

            verified_str = "✓ verified" if verified else "✗ unverified (default for all until review)"
            if p.get("rating") is not None:
                rating = float(p["rating"])
                social = f"{'★' * int(rating)}{'☆' * (5 - int(rating))} ({rating:.1f})"
            else:
                social = "rating: n/a (not tracked)"
            if p.get("downloads") is not None:
                social += f"  •  {p['downloads']} downloads"
            else:
                social += "  •  downloads: n/a (not tracked)"
            tag_str = "  ".join(f"[{t}]" for t in tags)

            if health is True:
                health_str = "💚 Healthy"
            elif health is False:
                health_str = "💔 Unhealthy"
            else:
                health_str = "⚪ unknown"

            yield Header(show_clock=False)
            yield Container(
                Static(f"{icon} {name} v{version}", classes="detail-header"),
                Rule(),
                Static(desc, classes="detail-desc"),
                Static("", classes="detail-meta"),
                Static(f"Author:    {author}", classes="detail-meta"),
                Static(f"Category:  {category}", classes="detail-meta"),
                Static(f"Type:      {ptype}", classes="detail-meta"),
                Static(f"Verified:  {verified_str}", classes="detail-meta"),
                Static("", classes="detail-meta"),
                Static(social, classes="detail-meta"),
                Static(f"Compatible: tokenade >= {min_ver}", classes="detail-meta"),
                Static(f"Dependencies: {', '.join(deps) if deps else 'none'}", classes="detail-meta"),
                Static("", classes="detail-meta"),
                Static(f"Lifecycle: {state}", classes="detail-meta"),
                Static(f"Health:    {health_str}", classes="detail-meta"),
                Static("", classes="detail-tags"),
                Static(f"Tags: {tag_str}", classes="detail-tags"),
                Rule(),
                Horizontal(
                    Button("Install", variant="success", id="detail-install"),
                    Button("Reload", variant="warning", id="detail-reload"),
                    Button("Configure", variant="primary", id="detail-configure"),
                    Button("Rate", variant="default", id="detail-rate"),
                    Button("Back [b]", variant="default", id="detail-back"),
                    classes="detail-actions",
                ),
                classes="detail-body",
            )
            yield Footer()

        def action_back(self):
            self.app.pop_screen()

        def action_install(self):
            self.app.install_plugin(self.plugin.get("name", ""))

        def action_rate(self):
            self.app.push_screen(RateScreen(self.plugin))

        @on(Button.Pressed, "#detail-install")
        def on_install(self):
            self.app.install_plugin(self.plugin.get("name", ""))

        @on(Button.Pressed, "#detail-reload")
        def on_reload(self):
            self.app._reload_plugin(self.plugin.get("name", ""))

        @on(Button.Pressed, "#detail-configure")
        def on_configure(self):
            self.app._configure_plugin(self.plugin.get("name", ""))

        @on(Button.Pressed, "#detail-rate")
        def on_rate(self):
            self.app.push_screen(RateScreen(self.plugin))

        @on(Button.Pressed, "#detail-back")
        def on_back(self):
            self.app.pop_screen()

    # ── Rate Screen ───────────────────────────────────────────

    class RateScreen(Screen):
        """Rating input screen."""

        DEFAULT_CSS = """
        RateScreen {
            align: center middle;
        }
        RateScreen Container {
            width: 60;
            height: auto;
            max-height: 25;
            background: $surface;
            border: tall $primary;
            padding: 1 2;
        }
        """

        BINDINGS = [Binding("escape", "cancel", "Cancel")]

        def __init__(self, plugin: Dict[str, Any], **kwargs):
            super().__init__(**kwargs)
            self.plugin = plugin

        def compose(self) -> ComposeResult:
            name = self.plugin.get("name", "unknown")
            yield Container(
                Static(f"Rate: {name}", classes="card-title"),
                Rule(),
                Static("Rating (1-5 stars):"),
                Input(placeholder="4", id="rating-input"),
                Static("Review (optional):"),
                Input(placeholder="Great plugin!", id="review-input"),
                Horizontal(
                    Button("Submit", variant="success", id="rate-submit"),
                    Button("Cancel", variant="default", id="rate-cancel"),
                ),
            )

        @on(Button.Pressed, "#rate-submit")
        def submit_rating(self):
            rating_inp = self.query_one("#rating-input", Input)
            review_inp = self.query_one("#review-input", Input)
            try:
                rating = int(rating_inp.value)
                if 1 <= rating <= 5:
                    name = self.plugin.get("name", "")
                    review = review_inp.value.strip()
                    self.app.rate_plugin(name, rating, review)
                    self.app.pop_screen()
            except ValueError:
                pass

        @on(Button.Pressed, "#rate-cancel")
        def cancel_rating(self):
            self.app.pop_screen()

        def action_cancel(self):
            self.app.pop_screen()

    # ── Sessions View ─────────────────────────────────────────

    class SessionsView(Vertical):
        """Session management view with health scores and actions."""

        def compose(self) -> ComposeResult:
            yield Static("📁 Sessions", classes="card-title")
            yield Rule()
            yield Container(id="sessions-list")

    # ── Vault View ────────────────────────────────────────────

    class VaultView(Vertical):
        """Encrypted session vault management view."""

        def compose(self) -> ComposeResult:
            yield Static("🔒 Session Vault", classes="card-title")
            yield Rule()
            yield Static("  Encrypted storage with AES-256-GCM key rotation", classes="card-meta")
            yield Horizontal(
                Button("Refresh", variant="primary", compact=True, id="vault-refresh"),
                Button("Rotate Key", variant="warning", compact=True, id="vault-rotate-key"),
                Button("Backup", variant="default", compact=True, id="vault-backup"),
            )
            yield Rule()
            yield Container(id="vault-list")

    # ── Sync View ─────────────────────────────────────────────

    class SyncView(Vertical):
        """Cross-machine session sync view."""

        def compose(self) -> ComposeResult:
            yield Static("🔄 Session Sync (Remote)", classes="card-title")
            yield Rule()
            yield Static("  Sync sessions via SSH/SCP with connection pooling", classes="card-meta")
            yield Horizontal(
                Input(placeholder="user@remote-host", id="sync-host-input"),
                Input(placeholder="~/.tokenade/sessions", id="sync-path-input"),
            )
            yield Horizontal(
                Button("Status", variant="primary", compact=True, id="sync-status"),
                Button("Push", variant="success", compact=True, id="sync-push"),
                Button("Pull", variant="warning", compact=True, id="sync-pull"),
                Button("Bidirectional", variant="default", compact=True, id="sync-bidir"),
            )
            yield Rule()
            yield Container(id="sync-result")

    # ── Share View ────────────────────────────────────────────

    class ShareView(Vertical):
        """Session sharing with password-protected URLs."""

        def compose(self) -> ComposeResult:
            yield Static("🔗 Session Sharing (URL Shortener)", classes="card-title")
            yield Rule()
            yield Static("  Create password-protected share links with expiry", classes="card-meta")
            yield Horizontal(
                Input(placeholder="/path/to/session.tokenade", id="share-session-input"),
                Input(placeholder="Password", password=True, id="share-password-input"),
            )
            yield Horizontal(
                Input(placeholder="Expiry hours (24)", id="share-expiry-input"),
                Input(placeholder="Max uses (0=unlimited)", id="share-max-uses-input"),
            )
            yield Horizontal(
                Button("Create Share", variant="success", compact=True, id="share-create"),
                Button("List Shares", variant="primary", compact=True, id="share-list"),
                Button("Cleanup Expired", variant="warning", compact=True, id="share-cleanup"),
            )
            yield Rule()
            yield Container(id="share-result")

    # ── Analytics View ────────────────────────────────────────

    class AnalyticsView(Vertical):
        """Session usage analytics view."""

        def compose(self) -> ComposeResult:
            yield Static("📊 Session Analytics", classes="card-title")
            yield Rule()
            yield Static("  Usage patterns, health trends, and insights", classes="card-meta")
            yield Horizontal(
                Button("Generate Report", variant="primary", compact=True, id="analytics-report"),
                Button("Export CSV", variant="default", compact=True, id="analytics-csv"),
                Button("Cleanup Old Events", variant="warning", compact=True, id="analytics-cleanup"),
            )
            yield Rule()
            yield Container(id="analytics-result")

    # ── Settings View ─────────────────────────────────────────

    class SettingsView(Vertical):
        """Settings view for registry and config."""

        def compose(self) -> ComposeResult:
            yield Static("⚙ Settings", classes="card-title")
            yield Rule()
            yield Container(
                Static("Plugin Registry", classes="card-title"),
                Static("", id="current-registry"),
                Rule(),
                Static("Plugin Management:", classes="card-title"),
                Horizontal(
                    Button("Sync All", variant="primary", compact=True, id="sync-plugins"),
                    Button("Update All", variant="warning", compact=True, id="update-plugins"),
                ),
                Rule(),
                Static("Add Custom Registry:"),
                Horizontal(
                    Input(placeholder="https://github.com/org/plugins", id="registry-url"),
                    Button("Add", variant="primary", id="add-registry"),
                ),
                Button("Reset to default", variant="default", id="reset-registry"),
                Rule(),
                Static("Installed registry sources:", classes="card-title"),
                Static("", id="custom-registries"),
                id="settings-content",
            )

    # ── Main App ──────────────────────────────────────────────

    class TokenadeTUI(App):
        """Tokenade Terminal UI Application."""

        TITLE = "Tokenade"
        SUB_TITLE = "Session Portability Tool"

        CSS = """
        Screen {
            background: $surface-darken-1;
        }
        #marketplace-layout {
            height: 100%;
        }
        #marketplace-content {
            width: 1fr;
        }
        #plugin-list {
            height: 1fr;
            overflow-y: auto;
        }
        #installed-list {
            height: 1fr;
            overflow-y: auto;
        }
        #sessions-list {
            height: 1fr;
            overflow-y: auto;
        }
        #settings-content {
            padding: 1 2;
            height: 1fr;
            overflow-y: auto;
        }
        .installed-card {
            height: auto;
            min-height: 5;
            margin: 0 1;
            padding: 1 2;
            background: $surface;
            border: tall $primary-background-lighten-2;
        }
        .installed-card:hover {
            background: $surface-lighten-1;
        }
        .session-card {
            height: auto;
            min-height: 4;
            margin: 0 1;
            padding: 1 2;
            background: $surface;
            border: tall $primary-background-lighten-2;
        }
        .session-card:hover {
            background: $surface-lighten-1;
        }
        .status-healthy {
            color: $success;
        }
        .status-expired {
            color: $error;
        }
        .status-unknown {
            color: $text-muted;
        }
        """

        BINDINGS = [
            Binding("1", "show_marketplace", "Marketplace"),
            Binding("2", "show_installed", "Installed"),
            Binding("3", "show_sessions", "Sessions"),
            Binding("4", "show_vault", "Vault"),
            Binding("5", "show_sync", "Sync"),
            Binding("6", "show_share", "Share"),
            Binding("7", "show_analytics", "Analytics"),
            Binding("8", "show_settings", "Settings"),
            Binding("q", "quit", "Quit"),
            Binding("slash", "focus_search", "Search", show=False),
            Binding("question_mark", "help", "Help"),
            Binding("j", "focus_next_card", "Next plugin", show=False),
            Binding("k", "focus_prev_card", "Prev plugin", show=False),
            Binding("enter", "open_details", "Details", show=False),
            Binding("i", "install_focused", "Install", show=False),
            Binding("u", "uninstall_focused", "Uninstall", show=False),
            Binding("r", "rate_focused", "Rate", show=False),
        ]

        def __init__(self, mode: str = "full", **kwargs):
            super().__init__(**kwargs)
            self.mode = mode
            self._plugins = []
            self._installed = []
            self._sessions = []
            self._categories = []
            self._registry_url = ""

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
            with TabbedContent(
                "Marketplace", "Installed", "Registries", "Sessions",
                "Vault", "Sync", "Share", "Analytics", "Settings",
                id="main-tabs",
            ):
                yield TabPane("Marketplace", MarketplaceView(), id="tab-marketplace")
                yield TabPane("Installed", InstalledView(), id="tab-installed")
                yield TabPane("Registries", RegistriesView(), id="tab-registries")
                yield TabPane("Sessions", SessionsView(), id="tab-sessions")
                yield TabPane("Vault", VaultView(), id="tab-vault")
                yield TabPane("Sync", SyncView(), id="tab-sync")
                yield TabPane("Share", ShareView(), id="tab-share")
                yield TabPane("Analytics", AnalyticsView(), id="tab-analytics")
                yield TabPane("Settings", SettingsView(), id="tab-settings")
            yield Footer()

        def on_mount(self):
            self._load_data()

        def _collect_deps(self, name: str) -> List[str]:
            """Read dependencies from a plugin's manifest (best-effort)."""
            try:
                from pathlib import Path as _P
                from tokenade.core.integration.plugin_loader import DEFAULT_PLUGINS_DIR
                mp = _P(DEFAULT_PLUGINS_DIR) / name / "plugin.json"
                if mp.exists():
                    import json as _j
                    with open(mp) as fh:
                        m = _j.load(fh)
                    return m.get("dependencies", []) or []
            except Exception:
                pass
            return []

        def _load_data(self):
            """Load plugin registry and session data."""
            try:
                from tokenade.core.integration.plugin_registry import PluginRegistry
                registry = PluginRegistry()
                self._plugins = registry.get_popular(limit=100) if hasattr(registry, 'get_popular') else []
                self._registry_url = registry.registry_url

                # Load categories
                cats = {}
                for p in self._plugins:
                    cat = p.get("category", "other")
                    cats[cat] = cats.get(cat, 0) + 1
                self._categories = [
                    {"name": k, "count": v} for k, v in sorted(cats.items())
                ]
            except Exception as e:
                logger.debug(f"Failed to load registry: {e}")

            try:
                from tokenade.core.integration.plugin_loader import PluginLoader
                loader = PluginLoader()
                loader.load_all()
                installed_plugins = loader.list_all()

                # Pull plugin-health snapshot from the shared context (best-effort).
                plugin_health = {}
                try:
                    from tokenade.core.context import SharedContext
                    ctx = SharedContext()
                    for lp in installed_plugins:
                        h = ctx.plugins.get_health(lp.name)
                        if h is not None:
                            plugin_health[lp.name] = h
                except Exception:
                    pass

                self._installed = [
                    {
                        "name": p.name,
                        "enabled": p.enabled,
                        "version": p.version,
                        "state": p.state.value if p.state else "unknown",
                        "error": p.error,
                        "config": p.config or {},
                        "dependencies": self._collect_deps(p.name),
                        "health": plugin_health.get(p.name),
                    }
                    for p in installed_plugins
                ]
            except Exception as e:
                logger.debug(f"Failed to load installed: {e}")

            try:
                sessions_dir = Path.home() / ".tokenade"
                self._sessions = []
                for f in sessions_dir.glob("*.tokenade"):
                    try:
                        with open(f) as fh:
                            data = json.load(fh)
                        cookies = data.get("cookies", [])
                        expired = 0
                        import time
                        now = time.time()
                        for c in cookies:
                            exp = c.get("expires", 0)
                            if exp and int(exp) > 0:
                                exp_int = int(exp)
                                if exp_int > 1262304000000:
                                    exp_int = exp_int // 1000
                                if exp_int < now:
                                    expired += 1
                        total = len(cookies)
                        health = ((total - expired) / total * 100) if total > 0 else 0
                        self._sessions.append({
                            "name": f.stem,
                            "file": str(f),
                            "site": data.get("site_name", "unknown"),
                            "auth": data.get("auth_status", "unknown"),
                            "cookies": total,
                            "expired": expired,
                            "health": health,
                        })
                    except Exception:
                        pass
            except Exception:
                pass

            self._update_views()

        def _update_views(self):
            """Update all views with loaded data."""
            try:
                self._update_marketplace()
                self._update_installed()
                self._update_registries()
                self._update_sessions()
                self._update_settings()
            except Exception:
                pass

        def _update_marketplace(self):
            """Update marketplace plugin cards."""
            try:
                container = self.query_one("#plugin-list", Container)
                container.remove_children()
                installed_map = {p["name"]: p.get("version", "") for p in self._installed}
                for p in self._plugins:
                    name = p.get("name", "")
                    is_installed = name in installed_map
                    update_available = (
                        is_installed
                        and p.get("version", "") != installed_map.get(name, "")
                    )
                    container.mount(PluginCard(
                        p, installed=is_installed,
                        update_available=update_available,
                    ))
                sidebar = self.query_one("#sidebar", CategorySidebar)
                sidebar.update_categories(self._categories)
                sidebar.update_registry(self._registry_url)
                status = self.query_one("#marketplace-status", StatusBar)
                installed_count = len(installed_map)
                status.text = f"📦 {len(self._plugins)} available  •  {installed_count} installed"
            except Exception:
                pass

        def _update_installed(self):
            """Update installed plugins list — shows lifecycle state + health."""
            try:
                container = self.query_one("#installed-list", Container)
                container.remove_children()
                if not self._installed:
                    container.mount(Static("  No plugins installed yet.", classes="installed-card"))
                    container.mount(Static("  Go to Marketplace tab to install plugins.", classes="installed-card"))
                else:
                    for p in self._installed:
                        name = p.get("name", "unknown")
                        enabled = p.get("enabled", True)
                        state = p.get("state", "unknown")
                        health = p.get("health")
                        enabled_str = "✅ enabled" if enabled else "⏸️ disabled"
                        health_str = ""
                        if health is True:
                            health_str = "  •  💚 healthy"
                        elif health is False:
                            health_str = "  •  💔 unhealthy"
                        update_hint = ""
                        registry_ver = None
                        for rp in self._plugins:
                            if rp.get("name") == name:
                                registry_ver = rp.get("version")
                                break
                        installed_ver = p.get("version", "?")
                        update_available = (
                            registry_ver and registry_ver != installed_ver
                        )
                        container.mount(Static(
                            f"  {name} v{installed_ver}  •  [{state}] {enabled_str}{health_str}{update_hint}",
                            classes="installed-card",
                        ))
                        if p.get("error"):
                            container.mount(Static(
                                f"  ⚠️  Error: {p['error']}",
                                classes="installed-card",
                            ))
                        container.mount(Horizontal(
                            Button(
                                "Uninstall", variant="error", compact=True,
                                id=f"uninstall-{name}",
                            ),
                            Button(
                                f"Update → v{registry_ver}" if update_available else "Up to date",
                                variant="primary" if update_available else "default",
                                compact=True,
                                id=f"update-{name}",
                                disabled=not update_available,
                            ),
                            Button(
                                "Reload", variant="default", compact=True,
                                id=f"reload-{name}",
                            ),
                            Button(
                                "Configure", variant="default", compact=True,
                                id=f"configure-{name}",
                            ),
                        ))
            except Exception:
                pass

        def _update_registries(self):
            """Update registries tab — lists configured registries with actions."""
            try:
                container = self.query_one("#registries-list", Container)
                container.remove_children()
                try:
                    from tokenade.core.integration.plugin_registry import PluginRegistry
                    reg = PluginRegistry()
                    registries = getattr(reg, "registries", []) or []
                    if not registries:
                        container.mount(Static(
                            "  No registries configured. Add one below.",
                            classes="installed-card",
                        ))
                    for r in registries:
                        url = r.get("url", "?")
                        priority = r.get("priority", 0)
                        enabled = r.get("enabled", True)
                        en_str = "✅ enabled" if enabled else "⏸️ disabled"
                        container.mount(Static(
                            f"  • [{url}]  priority {priority}  •  {en_str}",
                            classes="installed-card",
                        ))
                        container.mount(Horizontal(
                            Button("Disable" if enabled else "Enable", variant="warning",
                                   compact=True, id=f"registry-toggle-{priority}"),
                            Button("Up", variant="default", compact=True,
                                   id=f"registry-up-{priority}"),
                            Button("Down", variant="default", compact=True,
                                   id=f"registry-down-{priority}"),
                            Button("Remove", variant="error", compact=True,
                                   id=f"registry-remove-{priority}"),
                            Button("Refresh Cache", variant="primary", compact=True,
                                   id=f"registry-refresh-{priority}"),
                        ))
                except Exception as e:
                    container.mount(Static(
                        f"  Registry system unavailable: {e}",
                        classes="installed-card",
                    ))
            except Exception:
                pass

        def _update_sessions(self):
            """Update sessions list with health scores and action buttons."""
            try:
                container = self.query_one("#sessions-list", Container)
                container.remove_children()
                if not self._sessions:
                    container.mount(Static("  No sessions found.", classes="session-card"))
                    container.mount(Static(
                        "  Export one: tokenade export --browser-name brave "
                        "--domains 'google.com' -o gmail.tokenade",
                        classes="session-card",
                    ))
                for s in self._sessions:
                    auth = s.get("auth", "unknown")
                    health = s.get("health", 0)
                    expired = s.get("expired", 0)
                    # Color-code health
                    if health >= 80:
                        health_cls = "status-healthy"
                    elif health >= 50:
                        health_cls = "status-warn"
                    else:
                        health_cls = "status-expired"
                    status_cls = {
                        "logged_in": "status-healthy",
                        "session_expired": "status-expired",
                    }.get(auth, "status-unknown")
                    container.mount(Static(
                        f"  {s['name']}  •  {s['site']}  •  "
                        f"{s['cookies']} cookies  •  "
                        f"[{health_cls}]{health:.0f}%[/{health_cls}]  •  "
                        f"{expired} expired  •  "
                        f"[{status_cls}]{auth}[/{status_cls}]",
                        classes="session-card",
                    ))
                    container.mount(Horizontal(
                        Button("Autopsy", variant="default", compact=True,
                               id=f"autopsy-{s['name']}"),
                        Button("Delete", variant="error", compact=True,
                               id=f"delete-session-{s['name']}"),
                    ))
            except Exception:
                pass

        def _update_settings(self):
            """Update settings view."""
            try:
                reg = self.query_one("#current-registry", Static)
                reg.update(f"  {self._registry_url}")
            except Exception:
                pass

        @on(Input.Changed, "#search-input")
        def search_changed(self, event: Input.Changed):
            """Filter plugins by search query."""
            query = event.value.lower().strip()
            if not query:
                self._update_marketplace()
                return
            try:
                container = self.query_one("#plugin-list", Container)
                container.remove_children()
                installed_names = {p["name"] for p in self._installed}
                for p in self._plugins:
                    searchable = (
                        p.get("name", "") + " "
                        + p.get("description", "") + " "
                        + " ".join(p.get("tags", []))
                    ).lower()
                    if query in searchable:
                        is_installed = p.get("name", "") in installed_names
                        container.mount(PluginCard(p, installed=is_installed))
            except Exception:
                pass

        @on(Button.Pressed)
        def handle_button(self, event: Button.Pressed):
            """Handle install, uninstall, update, and details button presses."""
            btn_id = event.button.id or ""
            if btn_id.startswith("install-"):
                name = btn_id.removeprefix("install-")
                self.install_plugin(name)
            elif btn_id.startswith("uninstall-"):
                name = btn_id.removeprefix("uninstall-")
                self.uninstall_plugin(name)
            elif btn_id.startswith("update-"):
                name = btn_id.removeprefix("update-")
                self.update_plugin(name)
            elif btn_id == "sync-plugins":
                self._sync_all_plugins()
            elif btn_id == "update-plugins":
                self._update_all_plugins()
            elif btn_id.startswith("details-"):
                name = btn_id.removeprefix("details-")
                # Prefer installed dict (which has state/health/config) over registry entry
                installed = next(
                    (p for p in self._installed if p.get("name") == name), None
                )
                plugin = installed or next(
                    (p for p in self._plugins if p.get("name") == name), None
                )
                if plugin:
                    self.push_screen(PluginDetailScreen(plugin))
            elif btn_id.startswith("reload-"):
                name = btn_id.removeprefix("reload-")
                self._reload_plugin(name)
            elif btn_id.startswith("configure-"):
                name = btn_id.removeprefix("configure-")
                self._configure_plugin(name)
            elif btn_id.startswith("registry-toggle-"):
                prio = btn_id.removeprefix("registry-toggle-")
                self._toggle_registry(prio)
            elif btn_id.startswith("registry-up-"):
                prio = btn_id.removeprefix("registry-up-")
                self._shift_registry(prio, up=True)
            elif btn_id.startswith("registry-down-"):
                prio = btn_id.removeprefix("registry-down-")
                self._shift_registry(prio, up=False)
            elif btn_id.startswith("registry-remove-"):
                prio = btn_id.removeprefix("registry-remove-")
                self._remove_registry(prio)
            elif btn_id.startswith("registry-refresh-"):
                prio = btn_id.removeprefix("registry-refresh-")
                self._refresh_registry_cache(prio)
            elif btn_id == "registry-add-btn":
                self._add_registry_from_input()
            elif btn_id.startswith("autopsy-"):
                name = btn_id.removeprefix("autopsy-")
                self._run_autopsy(name)
            elif btn_id.startswith("delete-session-"):
                name = btn_id.removeprefix("delete-session-")
                self._delete_session(name)
            elif btn_id == "vault-refresh":
                self._vault_refresh()
            elif btn_id == "vault-rotate-key":
                self._vault_rotate_key()
            elif btn_id == "vault-backup":
                self._vault_backup()
            elif btn_id == "sync-status":
                self._sync_status()
            elif btn_id == "sync-push":
                self._sync_push()
            elif btn_id == "sync-pull":
                self._sync_pull()
            elif btn_id == "sync-bidir":
                self._sync_bidirectional()
            elif btn_id == "share-create":
                self._share_create()
            elif btn_id == "share-list":
                self._share_list()
            elif btn_id == "share-cleanup":
                self._share_cleanup()
            elif btn_id == "analytics-report":
                self._analytics_report()
            elif btn_id == "analytics-csv":
                self._analytics_export_csv()
            elif btn_id == "analytics-cleanup":
                self._analytics_cleanup()

        # ── Plugin action handlers (Phase 10) ──────────────────

        def _reload_plugin(self, name: str):
            """Reload a plugin via PluginLoader (preserves config)."""
            try:
                from tokenade.core.integration.plugin_loader import PluginLoader
                loader = PluginLoader()
                loader.load_all()
                loaded = loader.reload(name)
                if loaded:
                    self.notify(f"✅ {name} reloaded ({loaded.state.value})")
                else:
                    self.notify(f"❌ Failed to reload {name}", severity="error")
            except Exception as e:
                self.notify(f"❌ Reload error: {e}", severity="error")
            self._load_data()

        def _configure_plugin(self, name: str):
            """Push a config editor screen for the plugin."""
            try:
                self.push_screen(PluginConfigScreen(name))
            except Exception as e:
                self.notify(f"❌ Configure error: {e}", severity="error")

        # ── Registry management handlers (Phase 10) ─────────────

        def _add_registry_from_input(self):
            try:
                url_input = self.query_one("#registry-add-url", Input)
                prio_input = self.query_one("#registry-add-priority", Input)
                url = url_input.value.strip()
                prio = int(prio_input.value or "10")
                if not url:
                    self.notify("Enter a registry URL", severity="warning")
                    return
                from tokenade.core.integration.plugin_registry import PluginRegistry
                reg = PluginRegistry()
                if hasattr(reg, "add_registry"):
                    reg.add_registry(url, priority=prio)
                else:
                    reg.config.set_registry_url(url)
                self.notify(f"✅ Registry added: {url}")
                self._load_data()
            except Exception as e:
                self.notify(f"❌ Add registry error: {e}", severity="error")

        def _toggle_registry(self, prio: str):
            try:
                from tokenade.core.integration.plugin_registry import PluginRegistry
                reg = PluginRegistry()
                if hasattr(reg, "toggle_registry"):
                    reg.toggle_registry(int(prio))
                self._load_data()
            except Exception as e:
                logger.debug("toggle_registry failed: %s", e)

        def _shift_registry(self, prio: str, up: bool):
            try:
                from tokenade.core.integration.plugin_registry import PluginRegistry
                reg = PluginRegistry()
                if hasattr(reg, "set_priority"):
                    delta = -1 if up else 1
                    reg.set_priority(int(prio), int(prio) + delta)
                self._load_data()
            except Exception as e:
                logger.debug("shift_registry failed: %s", e)

        def _remove_registry(self, prio: str):
            try:
                from tokenade.core.integration.plugin_registry import PluginRegistry
                reg = PluginRegistry()
                if hasattr(reg, "remove_registry"):
                    reg.remove_registry(int(prio))
                self._load_data()
            except Exception as e:
                logger.debug("remove_registry failed: %s", e)

        def _refresh_registry_cache(self, prio: str):
            try:
                from tokenade.core.integration.plugin_registry import PluginRegistry
                reg = PluginRegistry()
                if hasattr(reg, "refresh_cache"):
                    reg.refresh_cache(int(prio))
                self.notify("✅ Cache refreshed")
            except Exception as e:
                self.notify(f"❌ Refresh failed: {e}", severity="error")

        @on(Button.Pressed, "#add-registry")
        def add_registry(self):
            """Add custom registry URL."""
            try:
                url_input = self.query_one("#registry-url", Input)
                url = url_input.value.strip()
                if url:
                    self._registry_url = url
                    self._update_settings()
                    url_input.value = ""
            except Exception:
                pass

        @on(Button.Pressed, "#reset-registry")
        def reset_registry(self):
            """Reset registry to default."""
            try:
                from tokenade.core.integration.plugin_registry import PluginRegistry
                self._registry_url = PluginRegistry().registry_url
                self._update_settings()
            except Exception:
                pass

        def install_plugin(self, name: str):
            """Install a plugin by name."""
            try:
                from tokenade.core.integration.plugin_registry import PluginRegistry
                registry = PluginRegistry()
                result = registry.install(name)
                if result:
                    self.notify(f"✅ Installed: {name}", timeout=3)
                    # Update button state
                    try:
                        btn = self.query_one(f"#install-{name}", Button)
                        btn.label = "Installed"
                        btn.disabled = True
                        btn.variant = "default"
                    except Exception:
                        pass
                    # Reload plugins and refresh views
                    self._load_data()
                    self._update_installed()
                    self._update_marketplace()
                else:
                    self.notify(f"❌ Failed to install: {name}", severity="error")
            except Exception as e:
                self.notify(f"❌ Error: {e}", severity="error")

        def uninstall_plugin(self, name: str):
            """Uninstall a plugin by name."""
            try:
                from tokenade.core.integration.plugin_registry import PluginRegistry
                registry = PluginRegistry()
                result = registry.uninstall(name)
                if result:
                    self.notify(f"🗑️ Uninstalled: {name}", timeout=3)
                    # Reload plugins and refresh views
                    self._load_data()
                    self._update_installed()
                    self._update_marketplace()
                else:
                    self.notify(f"❌ Failed to uninstall: {name}", severity="error")
            except Exception as e:
                self.notify(f"❌ Error: {e}", severity="error")

        def update_plugin(self, name: str):
            """Update a plugin to latest version."""
            try:
                from tokenade.core.integration.plugin_registry import PluginRegistry
                registry = PluginRegistry()
                result = registry.update(name)
                if result:
                    self.notify(f"🔄 Updated: {name}", timeout=3)
                    self._load_data()
                    self._update_installed()
                    self._update_marketplace()
                else:
                    self.notify(f"❌ Failed to update: {name}", severity="error")
            except Exception as e:
                self.notify(f"❌ Error: {e}", severity="error")

        def _sync_all_plugins(self):
            """Install all available plugins from registry."""
            try:
                from tokenade.core.integration.plugin_registry import PluginRegistry
                registry = PluginRegistry()
                plugins = registry.get_popular(limit=100)
                installed = {p["name"] for p in self._installed}
                to_install = [p for p in plugins if p.get("name") not in installed]

                if not to_install:
                    self.notify("✅ All plugins already installed", timeout=3)
                    return

                count = 0
                for p in to_install:
                    name = p.get("name", "")
                    if registry.install(name):
                        count += 1

                self.notify(f"✅ Synced {count} plugins", timeout=3)
                self._load_data()
                self._update_installed()
                self._update_marketplace()
            except Exception as e:
                self.notify(f"❌ Sync error: {e}", severity="error")

        def _update_all_plugins(self):
            """Update all installed plugins."""
            try:
                from tokenade.core.integration.plugin_registry import PluginRegistry
                registry = PluginRegistry()
                outdated = registry.get_outdated()

                if not outdated:
                    self.notify("✅ All plugins up to date", timeout=3)
                    return

                count = 0
                for name in outdated:
                    if registry.update(name):
                        count += 1

                self.notify(f"🔄 Updated {count} plugins", timeout=3)
                self._load_data()
                self._update_installed()
                self._update_marketplace()
            except Exception as e:
                self.notify(f"❌ Update error: {e}", severity="error")

        def _run_autopsy(self, name: str):
            """Run autopsy on a session and show results."""
            try:
                session = next(
                    (s for s in self._sessions if s["name"] == name),
                    None,
                )
                if not session:
                    self.notify(f"Session not found: {name}", severity="error")
                    return
                from tokenade.core.forensics.autopsy import SessionAutopsy
                autopsy = SessionAutopsy(session["file"])
                report = autopsy.analyze()
                # Show summary as notification
                self.notify(
                    f"{name}: {report.cause_of_death} "
                    f"({report.confidence}) — "
                    f"{report.cookie_count} cookies, "
                    f"{report.expired_count} expired",
                    timeout=5,
                )
            except Exception as e:
                self.notify(f"Autopsy error: {e}", severity="error")

        def _delete_session(self, name: str):
            """Delete a session file."""
            try:
                session = next(
                    (s for s in self._sessions if s["name"] == name),
                    None,
                )
                if not session:
                    self.notify(f"Session not found: {name}", severity="error")
                    return
                import os
                os.remove(session["file"])
                self.notify(f"🗑️ Deleted: {name}", timeout=3)
                self._load_data()
                self._update_sessions()
            except Exception as e:
                self.notify(f"Delete error: {e}", severity="error")

        def rate_plugin(self, name: str, rating: int, review: str = ""):
            """Rate a plugin with optional review."""
            try:
                from tokenade.core.integration.plugin_registry import PluginRegistry
                registry = PluginRegistry()
                registry.rate_plugin(name, rating)
                self.notify(f"⭐ Rated {name}: {rating}/5 stars")
                # Refresh marketplace to show updated rating
                self._load_data()
                self._update_marketplace()
            except Exception as e:
                self.notify(f"❌ Error: {e}", severity="error")

        def action_show_marketplace(self):
            self.query_one("#main-tabs").active = "tab-marketplace"

        def action_show_installed(self):
            self.query_one("#main-tabs").active = "tab-installed"

        def action_show_sessions(self):
            self.query_one("#main-tabs").active = "tab-sessions"

        def action_show_settings(self):
            self.query_one("#main-tabs").active = "tab-settings"

        def action_show_vault(self):
            self.query_one("#main-tabs").active = "tab-vault"

        def action_show_sync(self):
            self.query_one("#main-tabs").active = "tab-sync"

        def action_show_share(self):
            self.query_one("#main-tabs").active = "tab-share"

        def action_show_analytics(self):
            self.query_one("#main-tabs").active = "tab-analytics"

        def action_focus_search(self):
            try:
                self.query_one("#search-input", Input).focus()
            except Exception:
                pass

        def action_help(self):
            self.notify(
                "1-8: tabs  /: search  j/k: nav  "
                "Enter: details  i: install  u: uninstall  "
                "r: rate  q: quit",
                timeout=5,
            )

        def action_focus_next_card(self):
            """Focus next plugin card in marketplace."""
            try:
                cards = self.query("PluginCard")
                if not cards:
                    return
                focused = self.focused
                if focused and focused in cards:
                    idx = list(cards).index(focused)
                    next_idx = (idx + 1) % len(cards)
                    cards[next_idx].focus()
                else:
                    cards[0].focus()
            except Exception:
                pass

        def action_focus_prev_card(self):
            """Focus previous plugin card in marketplace."""
            try:
                cards = self.query("PluginCard")
                if not cards:
                    return
                focused = self.focused
                if focused and focused in cards:
                    idx = list(cards).index(focused)
                    prev_idx = (idx - 1) % len(cards)
                    cards[prev_idx].focus()
                else:
                    cards[-1].focus()
            except Exception:
                pass

        def _get_focused_plugin(self) -> Optional[Dict[str, Any]]:
            """Get the plugin data from the currently focused card."""
            try:
                focused = self.focused
                if focused and hasattr(focused, "plugin"):
                    return focused.plugin
            except Exception:
                pass
            return None

        def action_open_details(self):
            """Open detail view for focused plugin."""
            plugin = self._get_focused_plugin()
            if plugin:
                self.push_screen(PluginDetailScreen(plugin))

        def action_install_focused(self):
            """Install the focused plugin."""
            plugin = self._get_focused_plugin()
            if plugin:
                name = plugin.get("name", "")
                installed_names = {p["name"] for p in self._installed}
                if name not in installed_names:
                    self.install_plugin(name)
                else:
                    self.notify(f"Already installed: {name}")

        def action_uninstall_focused(self):
            """Uninstall the focused plugin."""
            plugin = self._get_focused_plugin()
            if plugin:
                name = plugin.get("name", "")
                installed_names = {p["name"] for p in self._installed}
                if name in installed_names:
                    self.uninstall_plugin(name)
                else:
                    self.notify(f"Not installed: {name}")

        def action_rate_focused(self):
            """Rate the focused plugin."""
            plugin = self._get_focused_plugin()
            if plugin:
                self.push_screen(RateScreen(plugin))

        # ── Vault handlers ─────────────────────────────────────

        def _vault_refresh(self):
            """Refresh vault contents display."""
            try:
                container = self.query_one("#vault-list", Container)
                container.remove_children()
                from tokenade.core.vault.vault import SessionVault
                vault = SessionVault()
                sessions = vault.list_sessions()
                if not sessions:
                    container.mount(Static("  Vault is empty.", classes="session-card"))
                    container.mount(Static("  Store a session: tokenade vault store <file> --name <name>", classes="session-card"))
                    return
                for name, meta in sessions.items():
                    created = meta.get("created_at", meta.get("created", "?"))
                    container.mount(Static(
                        f"  {name}  •  created: {created}",
                        classes="session-card",
                    ))
                    container.mount(Horizontal(
                        Button("Retrieve", variant="primary", compact=True, id=f"vault-retrieve-{name}"),
                        Button("Delete", variant="error", compact=True, id=f"vault-delete-{name}"),
                    ))
                self.notify(f"Loaded {len(sessions)} vault sessions", timeout=3)
            except Exception as e:
                self.notify(f"Vault refresh error: {e}", severity="error")

        def _vault_rotate_key(self):
            """Rotate vault encryption key."""
            try:
                from tokenade.core.vault.vault import SessionVault
                vault = SessionVault()
                vault.rotate_key()
                self.notify("Vault encryption key rotated", timeout=3)
            except Exception as e:
                self.notify(f"Key rotation error: {e}", severity="error")

        def _vault_backup(self):
            """Backup vault."""
            try:
                from tokenade.core.vault.vault import SessionVault
                vault = SessionVault()
                backup_path = str(Path.home() / ".tokenade" / "vault_backup.tar.gz")
                vault.backup(backup_path)
                self.notify(f"Vault backed up to {backup_path}", timeout=3)
            except Exception as e:
                self.notify(f"Backup error: {e}", severity="error")

        # ── Sync handlers ──────────────────────────────────────

        def _sync_status(self):
            """Show sync status."""
            try:
                host = self.query_one("#sync-host-input", Input).value.strip()
                path = self.query_one("#sync-path-input", Input).value.strip()
                if not host:
                    self.notify("Enter a remote host", severity="warning")
                    return
                from tokenade.core.sync.syncer import SessionSyncer, SyncConfig
                config = SyncConfig(
                    remote_host=host,
                    remote_path=path or "~/.tokenade/sessions",
                    local_path=str(Path.home() / ".tokenade" / "sessions"),
                )
                syncer = SessionSyncer(config)
                status = syncer.status()
                container = self.query_one("#sync-result", Container)
                container.remove_children()
                container.mount(Static(f"  Remote: {host}", classes="session-card"))
                container.mount(Static(f"  Remote files: {status.remote_files}", classes="session-card"))
                container.mount(Static(f"  Local files: {status.local_files}", classes="session-card"))
                container.mount(Static(f"  Pending push: {status.pending_push}", classes="session-card"))
                container.mount(Static(f"  Pending pull: {status.pending_pull}", classes="session-card"))
                self.notify("Sync status loaded", timeout=3)
            except Exception as e:
                self.notify(f"Sync status error: {e}", severity="error")

        def _sync_push(self):
            """Push sessions to remote."""
            try:
                host = self.query_one("#sync-host-input", Input).value.strip()
                path = self.query_one("#sync-path-input", Input).value.strip()
                if not host:
                    self.notify("Enter a remote host", severity="warning")
                    return
                from tokenade.core.sync.syncer import SessionSyncer, SyncConfig
                config = SyncConfig(
                    remote_host=host,
                    remote_path=path or "~/.tokenade/sessions",
                    local_path=str(Path.home() / ".tokenade" / "sessions"),
                )
                syncer = SessionSyncer(config)
                result = syncer.push()
                self.notify(f"Push complete: {result.pushed} pushed, {result.skipped} skipped", timeout=3)
            except Exception as e:
                self.notify(f"Push error: {e}", severity="error")

        def _sync_pull(self):
            """Pull sessions from remote."""
            try:
                host = self.query_one("#sync-host-input", Input).value.strip()
                path = self.query_one("#sync-path-input", Input).value.strip()
                if not host:
                    self.notify("Enter a remote host", severity="warning")
                    return
                from tokenade.core.sync.syncer import SessionSyncer, SyncConfig
                config = SyncConfig(
                    remote_host=host,
                    remote_path=path or "~/.tokenade/sessions",
                    local_path=str(Path.home() / ".tokenade" / "sessions"),
                )
                syncer = SessionSyncer(config)
                result = syncer.pull()
                self.notify(f"Pull complete: {result.pulled} pulled, {result.skipped} skipped", timeout=3)
            except Exception as e:
                self.notify(f"Pull error: {e}", severity="error")

        def _sync_bidirectional(self):
            """Bidirectional sync."""
            try:
                host = self.query_one("#sync-host-input", Input).value.strip()
                path = self.query_one("#sync-path-input", Input).value.strip()
                if not host:
                    self.notify("Enter a remote host", severity="warning")
                    return
                from tokenade.core.sync.syncer import SessionSyncer, SyncConfig
                config = SyncConfig(
                    remote_host=host,
                    remote_path=path or "~/.tokenade/sessions",
                    local_path=str(Path.home() / ".tokenade" / "sessions"),
                )
                syncer = SessionSyncer(config)
                result = syncer.sync("bidirectional")
                self.notify(f"Sync complete: {result.pushed} pushed, {result.pulled} pulled", timeout=3)
            except Exception as e:
                self.notify(f"Sync error: {e}", severity="error")

        # ── Share handlers ─────────────────────────────────────

        def _share_create(self):
            """Create a share URL."""
            try:
                session = self.query_one("#share-session-input", Input).value.strip()
                password = self.query_one("#share-password-input", Input).value.strip()
                expiry = self.query_one("#share-expiry-input", Input).value.strip()
                max_uses = self.query_one("#share-max-uses-input", Input).value.strip()
                if not session or not password:
                    self.notify("Session and password are required", severity="warning")
                    return
                from tokenade.core.sharing.url_shortener import SessionURLShortener, URLShortenerConfig
                config = URLShortenerConfig(
                    require_password=True,
                    password_min_length=8,
                )
                shortener = SessionURLShortener(config)
                result = shortener.create_share(
                    session_file=session,
                    password=password,
                    expiry_hours=int(expiry) if expiry else 24,
                    max_uses=int(max_uses) if max_uses else 0,
                )
                container = self.query_one("#share-result", Container)
                container.remove_children()
                container.mount(Static(f"  Share URL: {result['short_url']}", classes="session-card"))
                container.mount(Static(f"  Share ID: {result['share_id']}", classes="session-card"))
                self.notify("Share created", timeout=3)
            except Exception as e:
                self.notify(f"Share error: {e}", severity="error")

        def _share_list(self):
            """List active shares."""
            try:
                from tokenade.core.sharing.url_shortener import SessionURLShortener, URLShortenerConfig
                config = URLShortenerConfig()
                shortener = SessionURLShortener(config)
                shares = shortener.list_shares()
                container = self.query_one("#share-result", Container)
                container.remove_children()
                if not shares:
                    container.mount(Static("  No active shares.", classes="session-card"))
                    return
                for share in shares:
                    valid = "valid" if share.get("is_valid", True) else "expired"
                    container.mount(Static(
                        f"  {share.get('share_id', '?')}  •  {valid}  •  "
                        f"uses: {share.get('uses', 0)}/{share.get('max_uses', '∞')}",
                        classes="session-card",
                    ))
                self.notify(f"Found {len(shares)} shares", timeout=3)
            except Exception as e:
                self.notify(f"Share list error: {e}", severity="error")

        def _share_cleanup(self):
            """Cleanup expired shares."""
            try:
                from tokenade.core.sharing.url_shortener import SessionURLShortener, URLShortenerConfig
                config = URLShortenerConfig()
                shortener = SessionURLShortener(config)
                count = shortener.cleanup_expired()
                self.notify(f"Cleaned up {count} expired shares", timeout=3)
            except Exception as e:
                self.notify(f"Cleanup error: {e}", severity="error")

        # ── Analytics handlers ─────────────────────────────────

        def _analytics_report(self):
            """Generate analytics report."""
            try:
                from tokenade.core.analytics.engine import AnalyticsEngine
                engine = AnalyticsEngine()
                report = engine.generate_report()
                container = self.query_one("#analytics-result", Container)
                container.remove_children()
                container.mount(Static(f"  Period: {report.period_days} days", classes="session-card"))
                container.mount(Static(f"  Total events: {report.total_events}", classes="session-card"))
                container.mount(Static(f"  Exports: {report.total_exports}", classes="session-card"))
                container.mount(Static(f"  Loads: {report.total_loads}", classes="session-card"))
                container.mount(Static(f"  Shares: {report.total_shares}", classes="session-card"))
                container.mount(Static(f"  Syncs: {report.total_syncs}", classes="session-card"))
                container.mount(Static(f"  Success rate: {report.success_rate:.1%}", classes="session-card"))
                if report.top_sites:
                    container.mount(Static("  Top sites:", classes="session-card"))
                    for s in report.top_sites[:5]:
                        container.mount(Static(
                            f"    {s['site']}: {s['events']} events",
                            classes="session-card",
                        ))
                self.notify("Analytics report generated", timeout=3)
            except Exception as e:
                self.notify(f"Analytics error: {e}", severity="error")

        def _analytics_export_csv(self):
            """Export analytics to CSV."""
            try:
                from tokenade.core.analytics.engine import AnalyticsEngine
                engine = AnalyticsEngine()
                csv_path = str(Path.home() / ".tokenade" / "analytics" / "export.csv")
                engine.export_csv(csv_path)
                self.notify(f"Exported to {csv_path}", timeout=3)
            except Exception as e:
                self.notify(f"Export error: {e}", severity="error")

        def _analytics_cleanup(self):
            """Cleanup old analytics events."""
            try:
                from tokenade.core.analytics.engine import AnalyticsEngine
                engine = AnalyticsEngine()
                engine.cleanup()
                self.notify("Analytics events cleaned up", timeout=3)
            except Exception as e:
                self.notify(f"Cleanup error: {e}", severity="error")

    # ── Launch ────────────────────────────────────────────────

    app = TokenadeTUI(mode=mode)
    app.run()
