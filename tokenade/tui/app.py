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


def _check_textual():
    """Check if textual is available."""
    try:
        import textual  # noqa: F401
        return True
    except ImportError:
        return False


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
            rating = p.get("rating", 0)
            downloads = p.get("downloads", 0)
            verified = p.get("verified", False)

            stars = "★" * int(rating) + "☆" * (5 - int(rating))
            verified_str = " ✓" if verified else ""

            # Badges
            badges = ""
            if self.installed:
                badges += " [installed]"
            if self.update_available:
                badges += " [update]"

            yield Static(
                f"{icon} {name} v{version}{verified_str}  "
                f"{stars} {rating:.1f}  {downloads}↓  by {author}"
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
            rating = p.get("rating", 0)
            downloads = p.get("downloads", 0)
            verified = p.get("verified", False)
            tags = p.get("tags", [])
            category = p.get("category", "")
            ptype = p.get("type", "")
            min_ver = p.get("min_version", "")
            deps = p.get("dependencies", [])

            stars = "★" * int(rating) + "☆" * (5 - int(rating))
            verified_str = "✓ verified" if verified else "✗ not verified"
            tag_str = "  ".join(f"[{t}]" for t in tags)

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
                Static(
                    f"{stars} ({rating:.1f})  •  {downloads} downloads",
                    classes="detail-meta",
                ),
                Static(f"Compatible: tokenade >= {min_ver}", classes="detail-meta"),
                Static(f"Dependencies: {', '.join(deps) if deps else 'none'}", classes="detail-meta"),
                Static("", classes="detail-tags"),
                Static(f"Tags: {tag_str}", classes="detail-tags"),
                Rule(),
                Horizontal(
                    Button("Install", variant="success", id="detail-install"),
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

    # ── Marketplace View ──────────────────────────────────────

    class MarketplaceView(Vertical):
        """Plugin marketplace with cards and sidebar."""

        def compose(self) -> ComposeResult:
            yield Horizontal(
                CategorySidebar(id="sidebar"),
                Vertical(
                    Input(
                        placeholder="Search plugins...",
                        id="search-input",
                    ),
                    Container(id="plugin-list"),
                    StatusBar(id="marketplace-status"),
                    id="marketplace-content",
                ),
                id="marketplace-layout",
            )

    # ── Installed View ────────────────────────────────────────

    class InstalledView(Vertical):
        """Installed plugins management."""

        def compose(self) -> ComposeResult:
            yield Static("📦 Installed Plugins", classes="card-title")
            yield Rule()
            yield Container(id="installed-list")

    # ── Sessions View ─────────────────────────────────────────

    class SessionsView(Vertical):
        """Session management view."""

        def compose(self) -> ComposeResult:
            yield Static("📁 Sessions", classes="card-title")
            yield Rule()
            yield Container(id="sessions-list")

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
            Binding("4", "show_settings", "Settings"),
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
            with TabbedContent("Marketplace", "Installed", "Sessions", "Settings", id="main-tabs"):
                yield TabPane("Marketplace", MarketplaceView(), id="tab-marketplace")
                yield TabPane("Installed", InstalledView(), id="tab-installed")
                yield TabPane("Sessions", SessionsView(), id="tab-sessions")
                yield TabPane("Settings", SettingsView(), id="tab-settings")
            yield Footer()

        def on_mount(self):
            self._load_data()

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
                self._installed = [
                    {"name": p.name, "enabled": p.enabled, "version": p.version}
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
            """Update installed plugins list."""
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
                        status = "✅ enabled" if enabled else "⏸️ disabled"
                        # Check if update available
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
                            f"  {name} v{installed_ver}  •  {status}",
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
                        p.get("name", "") + " " +
                        p.get("description", "") + " " +
                        " ".join(p.get("tags", []))
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
                plugin = next(
                    (p for p in self._plugins if p.get("name") == name),
                    None,
                )
                if plugin:
                    self.push_screen(PluginDetailScreen(plugin))
            elif btn_id.startswith("autopsy-"):
                name = btn_id.removeprefix("autopsy-")
                self._run_autopsy(name)
            elif btn_id.startswith("delete-session-"):
                name = btn_id.removeprefix("delete-session-")
                self._delete_session(name)

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

        def action_focus_search(self):
            try:
                self.query_one("#search-input", Input).focus()
            except Exception:
                pass

        def action_help(self):
            self.notify(
                "1-4: tabs  /: search  j/k: nav  "
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

    # ── Launch ────────────────────────────────────────────────

    app = TokenadeTUI(mode=mode)
    app.run()
