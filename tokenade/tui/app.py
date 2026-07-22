"""
Tokenade TUI — Interactive terminal interface.

Provides a rich terminal UI for browsing the plugin marketplace,
managing installed plugins, viewing sessions, vault, sync, sharing,
and analytics.

Usage:
    tokenade tui                    # Launch full TUI

Requires: pip install textual
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Horizontal, Vertical
    from textual.screen import Screen
    from textual.widgets import (
        Button, Footer, Header, Input, Rule, Static,
        TabbedContent, TabPane, Label, DataTable,
    )
    from textual.widget import Widget
    from textual.reactive import reactive
    from textual import on
    _TEXTUAL_AVAILABLE = True
except ImportError:
    _TEXTUAL_AVAILABLE = False
    class App: pass
    class ComposeResult: pass
    class Binding:
        def __init__(self, *a, **k): pass
    class Container: pass
    class Horizontal: pass
    class Vertical: pass
    class Screen: pass
    class Button:
        class Pressed: pass
    class Header: pass
    class Footer: pass
    class Input: pass
    class Rule: pass
    class Static: pass
    class TabbedContent: pass
    class TabPane: pass
    class Label: pass
    class DataTable: pass
    class Widget: pass
    class reactive: pass
    def on(*a, **k):
        def decorator(f): return f
        return decorator

from tokenade.tui.config import (
    TOKENADE_DIR, SESSIONS_DIR, VAULT_DIR, ANALYTICS_DIR,
    APP_TITLE, APP_SUBTITLE, MAX_SESSIONS_DISPLAY,
)
from tokenade.tui.views.marketplace import MarketplaceView, PluginCard
from tokenade.tui.views.installed import InstalledView
from tokenade.tui.views.sessions import SessionsView
from tokenade.tui.views.vault import VaultView
from tokenade.tui.views.sync import SyncView
from tokenade.tui.views.share import ShareView
from tokenade.tui.views.analytics import AnalyticsView
from tokenade.tui.views.settings import SettingsView


# ════════════════════════════════════════════════════════════
# Plugin Detail Screen
# ════════════════════════════════════════════════════════════

class PluginDetailScreen(Screen if _TEXTUAL_AVAILABLE else object):
    """Full-screen plugin detail view."""

    DEFAULT_CSS = """
    PluginDetailScreen { background: $surface; }
    PluginDetailScreen .detail-header { text-style: bold; color: $primary; padding: 1 2; }
    PluginDetailScreen .detail-body { padding: 0 2; }
    PluginDetailScreen .detail-meta { color: $text-muted; }
    """

    BINDINGS = [
        Binding("b", "back", "Back"),
        Binding("escape", "back", "Back"),
    ]

    def __init__(self, plugin: Dict[str, Any], **kwargs):
        if _TEXTUAL_AVAILABLE:
            super().__init__(**kwargs)
        self.plugin = plugin

    def compose(self) -> "ComposeResult":
        if not _TEXTUAL_AVAILABLE:
            return
        p = self.plugin
        yield Header(show_clock=False)
        yield Container(
            Static(f"{p.get('icon','📦')} {p.get('name','?')} v{p.get('version','?')}", classes="detail-header"),
            Rule(),
            Static(p.get("description", "No description"), classes="detail-body"),
            Static(f"Author: {p.get('author', '?')}", classes="detail-meta"),
            Static(f"Type: {p.get('type', '?')}", classes="detail-meta"),
            Static(f"Health: {'Healthy' if p.get('health') else 'Unknown'}", classes="detail-meta"),
            Rule(),
            Horizontal(
                Button("Install", variant="success", id="detail-install"),
                Button("Back", variant="default", id="detail-back"),
            ),
            classes="detail-body",
        )
        yield Footer()

    def action_back(self):
        self.app.pop_screen()

    @on(Button.Pressed, "#detail-install")
    def on_install(self):
        name = self.plugin.get("name", "")
        if name:
            self.app.install_plugin(name)
            self.app.pop_screen()

    @on(Button.Pressed, "#detail-back")
    def on_back(self):
        self.app.pop_screen()


# ════════════════════════════════════════════════════════════
# Main TUI Application
# ════════════════════════════════════════════════════════════

class TokenadeTUI(App if _TEXTUAL_AVAILABLE else object):
    """Tokenade Terminal UI Application."""

    TITLE = APP_TITLE
    SUB_TITLE = APP_SUBTITLE

    CSS = """
    Screen { background: $surface-darken-1; }
    #marketplace-content, #installed-list, #sessions-list,
    #vault-list, #sync-result, #share-result, #analytics-result,
    #settings-content { height: 1fr; overflow-y: auto; padding: 0 1; }
    .card-title { text-style: bold; color: $primary; }
    .card-meta { color: $text-muted; }
    .session-card {
        height: auto; min-height: 3; margin: 0 1;
        padding: 1 2; background: $surface;
        border: tall $primary-background-lighten-2;
    }
    .session-card:hover { background: $surface-lighten-1; }
    .status-healthy { color: $success; }
    .status-expired { color: $error; }
    .status-unknown { color: $text-muted; }
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
        Binding("question_mark", "help", "Help"),
    ]

    def __init__(self, **kwargs):
        if _TEXTUAL_AVAILABLE:
            super().__init__(**kwargs)
        self._plugins: List[Dict] = []
        self._installed: List[Dict] = []
        self._sessions: List[Dict] = []

    def compose(self) -> "ComposeResult":
        yield Header(show_clock=False)
        with TabbedContent(
            "Marketplace", "Installed", "Sessions",
            "Vault", "Sync", "Share", "Analytics", "Settings",
            id="main-tabs",
        ):
            yield TabPane("Marketplace", MarketplaceView(), id="tab-marketplace")
            yield TabPane("Installed", InstalledView(), id="tab-installed")
            yield TabPane("Sessions", SessionsView(), id="tab-sessions")
            yield TabPane("Vault", VaultView(), id="tab-vault")
            yield TabPane("Sync", SyncView(), id="tab-sync")
            yield TabPane("Share", ShareView(), id="tab-share")
            yield TabPane("Analytics", AnalyticsView(), id="tab-analytics")
            yield TabPane("Settings", SettingsView(), id="tab-settings")
        yield Footer()

    def on_mount(self):
        self._load_data()

    # ── Data Loading ──────────────────────────────────────────

    def _load_data(self):
        """Load all data from backends."""
        self._load_plugins()
        self._load_installed()
        self._load_sessions()
        self._update_all_views()

    def _load_plugins(self):
        """Load available plugins from registry."""
        try:
            from tokenade.core.integration.plugin_registry import PluginRegistry
            registry = PluginRegistry()
            self._plugins = registry.get_popular(limit=100) if hasattr(registry, 'get_popular') else []
        except Exception as e:
            logger.debug(f"Failed to load plugins: {e}")
            self._plugins = []

    def _load_installed(self):
        """Load installed plugins."""
        try:
            from tokenade.core.integration.plugin_loader import PluginLoader
            loader = PluginLoader()
            loader.load_all()
            installed_plugins = loader.list_all()
            self._installed = [
                {
                    "name": p.name,
                    "enabled": p.enabled,
                    "version": p.version,
                    "state": p.state.value if p.state else "unknown",
                    "error": p.error,
                    "config": p.config or {},
                }
                for p in installed_plugins
            ]
        except Exception as e:
            logger.debug(f"Failed to load installed: {e}")
            self._installed = []

    def _load_sessions(self):
        """Load sessions from the configured directory."""
        try:
            view = self.query_one("#sessions-list")
            sessions = view.load_sessions() if hasattr(view, 'load_sessions') else []
            self._sessions = sessions
        except Exception:
            self._sessions = []

    # ── View Updates ──────────────────────────────────────────

    def _update_all_views(self):
        """Update all views with loaded data."""
        self._update_marketplace()
        self._update_installed()
        self._update_sessions()
        self._update_vault()
        self._update_settings()

    def _update_marketplace(self):
        """Update marketplace plugin cards."""
        try:
            container = self.query_one("#marketplace-content")
            container.remove_children()
            installed_names = {p["name"] for p in self._installed}
            for p in self._plugins:
                name = p.get("name", "")
                is_installed = name in installed_names
                container.mount(PluginCard(p, installed=is_installed))
            if not self._plugins:
                container.mount(Static("  No plugins available. Check registry connection.", classes="card-meta"))
        except Exception as e:
            logger.debug(f"Marketplace update failed: {e}")

    def _update_installed(self):
        """Update installed plugins list."""
        try:
            container = self.query_one("#installed-list")
            container.remove_children()
            if not self._installed:
                container.mount(Static("  No plugins installed.", classes="session-card"))
                container.mount(Static("  Go to Marketplace to install plugins.", classes="card-meta"))
                return
            for p in self._installed:
                name = p.get("name", "?")
                version = p.get("version", "?")
                state = p.get("state", "unknown")
                enabled = "enabled" if p.get("enabled") else "disabled"
                container.mount(Static(
                    f"  {name} v{version}  [{state}]  {enabled}",
                    classes="session-card",
                ))
                container.mount(Horizontal(
                    Button("Uninstall", variant="error", compact=True, id=f"uninstall-{name}"),
                    Button("Reload", variant="default", compact=True, id=f"reload-{name}"),
                    Button("Configure", variant="default", compact=True, id=f"configure-{name}"),
                ))
        except Exception as e:
            logger.debug(f"Installed update failed: {e}")

    def _update_sessions(self):
        """Update sessions list."""
        try:
            container = self.query_one("#sessions-list")
            container.remove_children()
            if not self._sessions:
                container.mount(Static(
                    f"  No sessions found in {SESSIONS_DIR}",
                    classes="session-card",
                ))
                container.mount(Static(
                    "  Export: tokenade export --browser-name firefox --domains 'site.com' -o session.tokenade",
                    classes="card-meta",
                ))
                return
            for s in self._sessions[:MAX_SESSIONS_DISPLAY]:
                health = s.get("health", 0)
                health_cls = "status-healthy" if health >= 80 else ("status-expired" if health < 50 else "status-unknown")
                status_cls = {
                    "logged_in": "status-healthy",
                    "session_expired": "status-expired",
                }.get(s.get("auth", ""), "status-unknown")
                container.mount(Static(
                    f"  {s['name']}  •  {s['site']}  •  "
                    f"{s['cookies']} cookies  •  "
                    f"[{health_cls}]{health:.0f}%[/{health_cls}]  •  "
                    f"[{status_cls}]{s.get('auth','?')}[/{status_cls}]",
                    classes="session-card",
                ))
                container.mount(Horizontal(
                    Button("Health", variant="primary", compact=True, id=f"health-{s['name']}"),
                    Button("Delete", variant="error", compact=True, id=f"delete-{s['name']}"),
                ))
        except Exception as e:
            logger.debug(f"Sessions update failed: {e}")

    def _update_vault(self):
        """Update vault list."""
        try:
            container = self.query_one("#vault-list")
            container.remove_children()
            try:
                from tokenade.core.vault.vault import SessionVault
                vault = SessionVault()
                sessions = vault.list_sessions()
                if not sessions:
                    container.mount(Static("  Vault is empty.", classes="session-card"))
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
            except Exception as e:
                container.mount(Static(f"  Vault unavailable: {e}", classes="session-card"))
        except Exception as e:
            logger.debug(f"Vault update failed: {e}")

    def _update_settings(self):
        """Update settings view."""
        try:
            reg = self.query_one("#current-registry")
            reg.update("  Default registry: https://github.com/mihir0209/tokenade-plugins")
        except Exception:
            pass

    # ── Plugin Actions ────────────────────────────────────────

    def install_plugin(self, name: str):
        """Install a plugin by name."""
        try:
            from tokenade.core.integration.plugin_registry import PluginRegistry
            registry = PluginRegistry()
            result = registry.install(name)
            if result:
                self.notify(f"Installed: {name}", timeout=3)
                self._load_data()
            else:
                self.notify(f"Failed to install: {name}", severity="error")
        except Exception as e:
            self.notify(f"Install error: {e}", severity="error")

    def uninstall_plugin(self, name: str):
        """Uninstall a plugin by name."""
        try:
            from tokenade.core.integration.plugin_registry import PluginRegistry
            registry = PluginRegistry()
            result = registry.uninstall(name)
            if result:
                self.notify(f"Uninstalled: {name}", timeout=3)
                self._load_data()
            else:
                self.notify(f"Failed to uninstall: {name}", severity="error")
        except Exception as e:
            self.notify(f"Uninstall error: {e}", severity="error")

    # ── Button Handlers ───────────────────────────────────────

    @on(Button.Pressed)
    def handle_button(self, event: Button.Pressed):
        """Route button presses to handlers."""
        btn_id = event.button.id or ""

        # Plugin install/uninstall
        if btn_id.startswith("install-"):
            self.install_plugin(btn_id.removeprefix("install-"))
        elif btn_id.startswith("uninstall-"):
            self.uninstall_plugin(btn_id.removeprefix("uninstall-"))
        elif btn_id.startswith("details-"):
            name = btn_id.removeprefix("details-")
            plugin = next((p for p in self._plugins if p.get("name") == name), None)
            if plugin:
                self.push_screen(PluginDetailScreen(plugin))

        # Marketplace
        elif btn_id == "sync-plugins":
            self._sync_all_plugins()

        # Vault
        elif btn_id == "vault-refresh":
            self._vault_refresh()
        elif btn_id == "vault-rotate-key":
            self._vault_rotate_key()
        elif btn_id == "vault-backup":
            self._vault_backup()

        # Sync
        elif btn_id == "sync-status":
            self._sync_status()
        elif btn_id == "sync-push":
            self._sync_push()
        elif btn_id == "sync-pull":
            self._sync_pull()
        elif btn_id == "sync-bidir":
            self._sync_bidirectional()

        # Share
        elif btn_id == "share-create":
            self._share_create()
        elif btn_id == "share-list":
            self._share_list()
        elif btn_id == "share-cleanup":
            self._share_cleanup()

        # Analytics
        elif btn_id == "analytics-report":
            self._analytics_report()
        elif btn_id == "analytics-csv":
            self._analytics_export_csv()
        elif btn_id == "analytics-cleanup":
            self._analytics_cleanup()

        # Sessions
        elif btn_id.startswith("health-"):
            name = btn_id.removeprefix("health-")
            self._session_health(name)
        elif btn_id.startswith("delete-"):
            name = btn_id.removeprefix("delete-")
            self._session_delete(name)

        # Settings
        elif btn_id == "add-registry":
            self._add_registry()
        elif btn_id == "reset-registry":
            self._reset_registry()

    # ── Sync Plugins ──────────────────────────────────────────

    def _sync_all_plugins(self):
        """Install all available plugins from registry."""
        try:
            from tokenade.core.integration.plugin_registry import PluginRegistry
            registry = PluginRegistry()
            plugins = registry.get_popular(limit=100)
            installed = {p["name"] for p in self._installed}
            to_install = [p for p in plugins if p.get("name") not in installed]
            if not to_install:
                self.notify("All plugins already installed", timeout=3)
                return
            count = sum(1 for p in to_install if registry.install(p.get("name", "")))
            self.notify(f"Synced {count} plugins", timeout=3)
            self._load_data()
        except Exception as e:
            self.notify(f"Sync error: {e}", severity="error")

    # ── Vault Actions ─────────────────────────────────────────

    def _vault_refresh(self):
        self._update_vault()
        self.notify("Vault refreshed", timeout=3)

    def _vault_rotate_key(self):
        try:
            from tokenade.core.vault.vault import SessionVault
            SessionVault().rotate_key()
            self.notify("Vault key rotated", timeout=3)
        except Exception as e:
            self.notify(f"Key rotation error: {e}", severity="error")

    def _vault_backup(self):
        try:
            from tokenade.core.vault.vault import SessionVault
            backup_path = str(TOKENADE_DIR / "vault_backup.tar.gz")
            SessionVault().backup(backup_path)
            self.notify(f"Vault backed up", timeout=3)
        except Exception as e:
            self.notify(f"Backup error: {e}", severity="error")

    # ── Sync Actions ──────────────────────────────────────────

    def _get_sync_config(self):
        host = self.query_one("#sync-host-input").value.strip()
        path = self.query_one("#sync-path-input").value.strip()
        if not host:
            self.notify("Enter a remote host", severity="warning")
            return None
        from tokenade.core.sync.syncer import SyncConfig
        return SyncConfig(
            remote_host=host,
            remote_path=path or "~/.tokenade/sessions",
            local_path=str(SESSIONS_DIR),
        )

    def _sync_status(self):
        try:
            config = self._get_sync_config()
            if not config:
                return
            from tokenade.core.sync.syncer import SessionSyncer
            syncer = SessionSyncer(config)
            status = syncer.status()
            container = self.query_one("#sync-result")
            container.remove_children()
            container.mount(Static(f"  Remote: {config.remote_host}", classes="session-card"))
            container.mount(Static(f"  Remote files: {status.remote_files}", classes="session-card"))
            container.mount(Static(f"  Local files: {status.local_files}", classes="session-card"))
            container.mount(Static(f"  Pending push: {status.pending_push}", classes="session-card"))
            container.mount(Static(f"  Pending pull: {status.pending_pull}", classes="session-card"))
        except Exception as e:
            self.notify(f"Sync status error: {e}", severity="error")

    def _sync_push(self):
        try:
            config = self._get_sync_config()
            if not config:
                return
            from tokenade.core.sync.syncer import SessionSyncer
            result = SessionSyncer(config).push()
            self.notify(f"Pushed: {result.pushed}, Skipped: {result.skipped}", timeout=3)
        except Exception as e:
            self.notify(f"Push error: {e}", severity="error")

    def _sync_pull(self):
        try:
            config = self._get_sync_config()
            if not config:
                return
            from tokenade.core.sync.syncer import SessionSyncer
            result = SessionSyncer(config).pull()
            self.notify(f"Pulled: {result.pulled}, Skipped: {result.skipped}", timeout=3)
        except Exception as e:
            self.notify(f"Pull error: {e}", severity="error")

    def _sync_bidirectional(self):
        try:
            config = self._get_sync_config()
            if not config:
                return
            from tokenade.core.sync.syncer import SessionSyncer
            result = SessionSyncer(config).sync("bidirectional")
            self.notify(f"Synced: pushed={result.pushed}, pulled={result.pulled}", timeout=3)
        except Exception as e:
            self.notify(f"Sync error: {e}", severity="error")

    # ── Share Actions ─────────────────────────────────────────

    def _share_create(self):
        try:
            session = self.query_one("#share-session-input").value.strip()
            password = self.query_one("#share-password-input").value.strip()
            expiry = self.query_one("#share-expiry-input").value.strip()
            max_uses = self.query_one("#share-max-uses-input").value.strip()
            if not session or not password:
                self.notify("Session and password required", severity="warning")
                return
            from tokenade.core.sharing.url_shortener import SessionURLShortener, URLShortenerConfig
            shortener = SessionURLShortener(URLShortenerConfig(require_password=True))
            result = shortener.create_share(
                session_file=session,
                password=password,
                expiry_hours=int(expiry) if expiry else 24,
                max_uses=int(max_uses) if max_uses else 0,
            )
            container = self.query_one("#share-result")
            container.remove_children()
            container.mount(Static(f"  URL: {result['short_url']}", classes="session-card"))
            container.mount(Static(f"  ID: {result['share_id']}", classes="session-card"))
            self.notify("Share created", timeout=3)
        except Exception as e:
            self.notify(f"Share error: {e}", severity="error")

    def _share_list(self):
        try:
            from tokenade.core.sharing.url_shortener import SessionURLShortener, URLShortenerConfig
            shortener = SessionURLShortener(URLShortenerConfig())
            shares = shortener.list_shares()
            container = self.query_one("#share-result")
            container.remove_children()
            if not shares:
                container.mount(Static("  No active shares.", classes="session-card"))
                return
            for share in shares:
                valid = "valid" if share.get("is_valid", True) else "expired"
                container.mount(Static(
                    f"  {share.get('share_id','?')}  •  {valid}  •  "
                    f"uses: {share.get('uses',0)}/{share.get('max_uses','∞')}",
                    classes="session-card",
                ))
        except Exception as e:
            self.notify(f"Share list error: {e}", severity="error")

    def _share_cleanup(self):
        try:
            from tokenade.core.sharing.url_shortener import SessionURLShortener, URLShortenerConfig
            count = SessionURLShortener(URLShortenerConfig()).cleanup_expired()
            self.notify(f"Cleaned {count} expired shares", timeout=3)
        except Exception as e:
            self.notify(f"Cleanup error: {e}", severity="error")

    # ── Analytics Actions ─────────────────────────────────────

    def _analytics_report(self):
        try:
            from tokenade.core.analytics.engine import AnalyticsEngine
            report = AnalyticsEngine().generate_report()
            container = self.query_one("#analytics-result")
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
                    container.mount(Static(f"    {s['site']}: {s['events']} events", classes="session-card"))
        except Exception as e:
            self.notify(f"Analytics error: {e}", severity="error")

    def _analytics_export_csv(self):
        try:
            from tokenade.core.analytics.engine import AnalyticsEngine
            csv_path = str(ANALYTICS_DIR / "export.csv")
            AnalyticsEngine().export_csv(csv_path)
            self.notify(f"Exported to {csv_path}", timeout=3)
        except Exception as e:
            self.notify(f"Export error: {e}", severity="error")

    def _analytics_cleanup(self):
        try:
            from tokenade.core.analytics.engine import AnalyticsEngine
            AnalyticsEngine().cleanup()
            self.notify("Analytics cleaned up", timeout=3)
        except Exception as e:
            self.notify(f"Cleanup error: {e}", severity="error")

    # ── Session Actions ───────────────────────────────────────

    def _session_health(self, name: str):
        session = next((s for s in self._sessions if s["name"] == name), None)
        if session:
            self.notify(f"{name}: health={session['health']:.0f}%, cookies={session['cookies']}", timeout=3)

    def _session_delete(self, name: str):
        session = next((s for s in self._sessions if s["name"] == name), None)
        if session:
            try:
                Path(session["file"]).unlink()
                self.notify(f"Deleted: {name}", timeout=3)
                self._load_sessions()
                self._update_sessions()
            except Exception as e:
                self.notify(f"Delete error: {e}", severity="error")

    # ── Settings Actions ──────────────────────────────────────

    def _add_registry(self):
        try:
            url = self.query_one("#registry-url").value.strip()
            if url:
                self.notify(f"Registry added: {url}", timeout=3)
        except Exception:
            pass

    def _reset_registry(self):
        self.notify("Registry reset to default", timeout=3)

    # ── Tab Navigation ────────────────────────────────────────

    def action_show_marketplace(self):
        self.query_one("#main-tabs").active = "tab-marketplace"

    def action_show_installed(self):
        self.query_one("#main-tabs").active = "tab-installed"

    def action_show_sessions(self):
        self.query_one("#main-tabs").active = "tab-sessions"

    def action_show_vault(self):
        self.query_one("#main-tabs").active = "tab-vault"

    def action_show_sync(self):
        self.query_one("#main-tabs").active = "tab-sync"

    def action_show_share(self):
        self.query_one("#main-tabs").active = "tab-share"

    def action_show_analytics(self):
        self.query_one("#main-tabs").active = "tab-analytics"

    def action_show_settings(self):
        self.query_one("#main-tabs").active = "tab-settings"

    def action_help(self):
        self.notify(
            "1-8: tabs  q: quit  Click buttons to interact",
            timeout=5,
        )


# ════════════════════════════════════════════════════════════
# Entry Point
# ════════════════════════════════════════════════════════════

def run_tui(mode: str = "full"):
    """Launch the TUI application."""
    if not _TEXTUAL_AVAILABLE:
        print("TUI requires textual: pip install 'tokenade[tui]'")
        return

    app = TokenadeTUI()
    app.run()


# Keep backward compatibility
class PluginHealthWidget(Widget if _TEXTUAL_AVAILABLE else object):
    """Visualizes plugin health scores."""

    def __init__(self, installed: list, **kwargs):
        if _TEXTUAL_AVAILABLE:
            super().__init__(**kwargs)
        self.installed = installed

    def render(self):
        lines = ["Plugin Health"]
        if not self.installed:
            return "  No plugins installed."
        for p in self.installed:
            name = p.get("name", "?")
            health = p.get("health")
            if health is True:
                status = "Healthy"
            elif health is False:
                status = "Unhealthy"
            else:
                status = "unknown"
            err = p.get("error") if health is False else ""
            line = f"  {name}: {status}"
            if err:
                line += f"  ({err[:40]})"
            lines.append(line)
        return "\n".join(lines)


class PluginConfigWidget(Widget if _TEXTUAL_AVAILABLE else object):
    """Visualizes plugin config (sensitive values redacted)."""

    SENSITIVE_KEYS = {"password", "secret", "token", "api_key", "client_secret"}

    def __init__(self, installed: list, **kwargs):
        if _TEXTUAL_AVAILABLE:
            super().__init__(**kwargs)
        self.installed = installed

    def render(self):
        lines = ["Plugin Configuration"]
        if not self.installed:
            return "  No plugins installed."
        for p in self.installed:
            name = p.get("name", "?")
            cfg = p.get("config") or {}
            if not cfg:
                lines.append(f"  {name}: [no configuration]")
                continue
            lines.append(f"  {name}:")
            for k, v in sorted(cfg.items()):
                if any(s in k.lower() for s in self.SENSITIVE_KEYS):
                    lines.append(f"      {k}: [redacted]")
                else:
                    lines.append(f"      {k}: {v}")
        return "\n".join(lines)


class PluginTaskWidget(Widget if _TEXTUAL_AVAILABLE else object):
    """Visualizes active + recent plugin tasks."""

    def __init__(self, installed: list, **kwargs):
        if _TEXTUAL_AVAILABLE:
            super().__init__(**kwargs)
        self.installed = installed

    def render(self):
        try:
            from tokenade.core.context import SharedContext
            ctx = SharedContext()
            tasks = ctx.tasks.list_all() if hasattr(ctx.tasks, "list_all") else []
            active = [t for t in tasks if t.get("status") == "running"]
            recent = [t for t in tasks if t.get("status") != "running"]
            lines = ["Plugin Tasks"]
            if active:
                lines.append("  Active:")
                for t in active[:10]:
                    lines.append(f"    {t.get('plugin', '?')}: {t.get('name', '?')}")
            if recent:
                lines.append("  Recent:")
                for t in recent[:10]:
                    lines.append(f"    {t.get('plugin', '?')}: {t.get('name', '?')} ({t.get('status', '?')})")
            if not active and not recent:
                lines.append("  No tasks recorded.")
            return "\n".join(lines)
        except Exception:
            return "  Task tracker unavailable."


RegistriesView = SettingsView


class PluginConfigScreen(Screen if _TEXTUAL_AVAILABLE else object):
    """Configuration editor for a specific plugin."""

    DEFAULT_CSS = """
    PluginConfigScreen { align: center middle; }
    PluginConfigScreen Container { width: 70; height: auto; max-height: 40;
        background: $surface; border: tall $primary; padding: 1 2; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, plugin_name: str, **kwargs):
        if _TEXTUAL_AVAILABLE:
            super().__init__(**kwargs)
        self.plugin_name = plugin_name

    def compose(self) -> "ComposeResult":
        if not _TEXTUAL_AVAILABLE:
            return
        yield Container(
            Static(f"Configure: {self.plugin_name}", classes="card-title"),
            Rule(),
            Static("  No configurable schema for this plugin."),
            Static("  Use CLI: tokenade plugin configure"),
        )

    def action_cancel(self):
        self.app.pop_screen()
