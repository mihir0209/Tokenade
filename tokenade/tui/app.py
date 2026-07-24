"""
Tokenade TUI — Interactive terminal interface.

Usage:
    tokenade tui
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
    from textual.screen import Screen
    from textual.widgets import (
        Button, Footer, Header, Input, Rule, Static,
        TabbedContent, TabPane, Select, Switch,
    )
    from textual.widget import Widget
    from textual import on
    _TEXTUAL_AVAILABLE = True
except ImportError:
    _TEXTUAL_AVAILABLE = False

    class App:
        pass

    class ComposeResult:
        pass

    class Binding:
        def __init__(self, *a, **k):
            pass

    class Container:
        pass

    class Horizontal:
        pass

    class Vertical:
        pass

    class ScrollableContainer:
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

    class Widget:
        pass

    class Select:
        BLANK = object()
        NULL = object()

        class Changed:
            pass

    class Switch:
        pass

    def on(*a, **k):
        def decorator(f):
            return f
        return decorator


from tokenade.tui.config import (
    TOKENADE_DIR, SESSIONS_DIR, VAULT_DIR, ANALYTICS_DIR, PLUGINS_DIR,
    APP_TITLE, APP_SUBTITLE, MAX_SESSIONS_DISPLAY,
)
from tokenade.tui.views.export import ExportView
from tokenade.tui.views.marketplace import (
    MarketplaceView, PluginCard, format_plugin_detail,
)
from tokenade.tui.views.installed import InstalledView, InstalledRow
from tokenade.tui.views.sessions import SessionsView, SessionTile, load_sessions, detect_session_url
from tokenade.tui.views.vault import VaultView
from tokenade.tui.views.sync import SyncView
from tokenade.tui.views.share import ShareView, session_select_options
from tokenade.tui.views.analytics import AnalyticsView
from tokenade.tui.views.settings import SettingsView
from tokenade.tui.cli_runner import (
    run_tokenade,
    run_tokenade_async,
    cmd_health,
    cmd_launch,
    cmd_load,
    cmd_refresh_browser,
    cmd_export,
    format_receive_help,
    copy_text,
)


class PluginDetailScreen(Screen if _TEXTUAL_AVAILABLE else object):
    """Full-screen plugin detail — shows all registry fields."""

    DEFAULT_CSS = """
    PluginDetailScreen { background: $surface; }
    PluginDetailScreen .detail-header {
        text-style: bold; color: $primary; padding: 1 2; height: 3;
    }
    PluginDetailScreen #detail-scroll {
        height: 1fr; padding: 0 2; overflow-y: auto;
    }
    PluginDetailScreen .detail-line { height: 1; }
    PluginDetailScreen .detail-meta { color: $text-muted; height: 1; }
    PluginDetailScreen .detail-actions {
        height: 3; padding: 0 2; dock: bottom;
    }
    PluginDetailScreen .detail-actions Button { margin-right: 1; }
    """

    BINDINGS = [
        Binding("b", "back", "Back"),
        Binding("escape", "back", "Back"),
        Binding("i", "install", "Install"),
    ]

    def __init__(self, plugin: Dict[str, Any], **kwargs):
        if _TEXTUAL_AVAILABLE:
            super().__init__(**kwargs)
        self.plugin = plugin

    def compose(self) -> "ComposeResult":
        if not _TEXTUAL_AVAILABLE:
            return
        p = self.plugin
        # Enrich from registry if thin
        try:
            from tokenade.core.integration.plugin_registry import PluginRegistry
            full = PluginRegistry().get_plugin_details(p.get("name", ""))
            if full:
                merged = dict(full)
                merged.update({k: v for k, v in p.items() if v not in (None, "", [])})
                p = merged
                self.plugin = p
        except Exception:
            pass

        yield Header(show_clock=False)
        yield Static(
            f"{p.get('icon') or '📦'}  {p.get('name', '?')}  v{p.get('version', '?')}",
            classes="detail-header",
        )
        with ScrollableContainer(id="detail-scroll"):
            for i, line in enumerate(format_plugin_detail(p)):
                cls = "detail-line" if line and not line.startswith(" ") else "detail-meta"
                if not line:
                    yield Static(" ", classes="detail-meta")
                else:
                    yield Static(line, classes=cls)
        yield Horizontal(
            Button("Install", variant="success", id="detail-install"),
            Button("Back", variant="default", id="detail-back"),
            classes="detail-actions",
        )
        yield Footer()

    def action_back(self):
        self.app.pop_screen()

    def action_install(self):
        self.on_install()

    @on(Button.Pressed, "#detail-install")
    def on_install(self):
        name = self.plugin.get("name", "")
        if name:
            self.app.install_plugin(name)
            self.app.pop_screen()

    @on(Button.Pressed, "#detail-back")
    def on_back(self):
        self.app.pop_screen()


class TokenadeTUI(App if _TEXTUAL_AVAILABLE else object):
    """Tokenade Terminal UI Application."""

    TITLE = APP_TITLE
    SUB_TITLE = APP_SUBTITLE

    CSS = """
    Screen { background: $surface-darken-1; }
    TabPane { align: left top; }
    #plugin-list, #installed-list, #sessions-list,
    #vault-list, #sync-result, #share-result, #analytics-result,
    #settings-body, #export-cli-log {
        height: 1fr; overflow-y: auto; padding: 0;
        align: left top;
    }
    .card-title { text-style: bold; color: $primary; height: auto; }
    .card-meta { color: $text-muted; height: auto; }
    .session-card {
        height: auto; min-height: 1; margin: 0 0 1 0;
        padding: 0 1; background: $surface;
        border: tall $primary-background-lighten-2;
    }
    .session-card:hover { background: $surface-lighten-1; }
    .status-healthy { color: $success; }
    .status-expired { color: $error; }
    .status-unknown { color: $text-muted; }
    """

    BINDINGS = [
        Binding("1", "show_export", "Export"),
        Binding("2", "show_sessions", "Sessions"),
        Binding("3", "show_share", "Share"),
        Binding("4", "show_vault", "Vault"),
        Binding("5", "show_sync", "Sync"),
        Binding("6", "show_analytics", "Analytics"),
        Binding("7", "show_installed", "Plugins"),
        Binding("8", "show_marketplace", "Marketplace"),
        Binding("9", "show_settings", "Settings"),
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "help", "Help"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, **kwargs):
        if _TEXTUAL_AVAILABLE:
            super().__init__(**kwargs)
        self._plugins: List[Dict] = []
        self._installed: List[Dict] = []
        self._sessions: List[Dict] = []
        self._selected_session: Optional[Dict] = None
        self._last_share: Dict[str, Any] = {}

    def compose(self) -> "ComposeResult":
        yield Header(show_clock=False)
        # Do NOT pass title strings here — that creates empty panes that
        # fight the real TabPane ids and break .active / Share… navigation.
        with TabbedContent(id="main-tabs"):
            yield TabPane("Export", ExportView(), id="tab-export")
            yield TabPane("Sessions", SessionsView(), id="tab-sessions")
            yield TabPane("Share", ShareView(), id="tab-share")
            yield TabPane("Vault", VaultView(), id="tab-vault")
            yield TabPane("Sync", SyncView(), id="tab-sync")
            yield TabPane("Analytics", AnalyticsView(), id="tab-analytics")
            yield TabPane("Installed plugins", InstalledView(), id="tab-installed")
            yield TabPane("Marketplace", MarketplaceView(), id="tab-marketplace")
            yield TabPane("Settings", SettingsView(), id="tab-settings")
        yield Footer()

    def on_mount(self):
        self._load_data()

    # ── Data Loading ──────────────────────────────────────────

    def _load_data(self):
        self._load_plugins()
        self._load_installed()
        self._load_sessions()
        self._update_all_views()

    def _load_plugins(self):
        try:
            from tokenade.core.integration.plugin_registry import PluginRegistry
            registry = PluginRegistry()
            self._plugins = registry.get_popular(limit=100) or []
        except Exception as e:
            logger.debug("Failed to load plugins: %s", e)
            self._plugins = []

    def _load_installed(self):
        try:
            from tokenade.core.integration.plugin_loader import PluginLoader
            loader = PluginLoader()
            loader.load_all()
            self._installed = [
                {
                    "name": p.name,
                    "enabled": p.enabled,
                    "version": p.version,
                    "state": p.state.value if p.state else "unknown",
                    "error": p.error,
                    "config": p.config or {},
                    "health": getattr(p, "health", None),
                }
                for p in loader.list_all()
            ]
        except Exception as e:
            logger.debug("Failed to load installed: %s", e)
            self._installed = []

    def _load_sessions(self):
        try:
            self._sessions = load_sessions(SESSIONS_DIR)
        except Exception as e:
            logger.debug("Failed to load sessions: %s", e)
            self._sessions = []

    # ── View Updates ──────────────────────────────────────────

    def _update_all_views(self):
        self._update_marketplace()
        self._update_installed()
        self._update_sessions()
        self._update_vault()
        self._update_settings()

    def _update_marketplace(self):
        try:
            try:
                grid = self.query_one("#plugin-grid")
            except Exception:
                grid = self.query_one("#plugin-list")
            grid.remove_children()
            installed_names = {p["name"] for p in self._installed}
            if not self._plugins:
                grid.mount(Static(
                    "  No plugins available. Check registry connection.",
                    classes="card-meta",
                ))
                return
            for p in self._plugins:
                name = p.get("name", "")
                grid.mount(PluginCard(p, installed=name in installed_names))
        except Exception as e:
            logger.debug("Marketplace update failed: %s", e)

    def _update_installed(self):
        try:
            container = self.query_one("#installed-list")
            container.remove_children()
            if not self._installed:
                container.mount(Static(
                    "No plugins installed. Open Marketplace to install.",
                    classes="card-meta",
                ))
                return
            # Sort: active first, then name
            rows = sorted(
                self._installed,
                key=lambda p: (
                    0 if p.get("state") == "active" else 1,
                    (p.get("name") or "").lower(),
                ),
            )
            for p in rows:
                container.mount(InstalledRow(p))
            # Keep scroll at top
            try:
                container.scroll_home(animate=False)
            except Exception:
                pass
        except Exception as e:
            logger.debug("Installed update failed: %s", e)

    def _update_sessions(self):
        try:
            try:
                grid = self.query_one("#session-grid")
            except Exception:
                grid = self.query_one("#sessions-list")
            grid.remove_children()
            self._refresh_session_browser_select()
            if not self._sessions:
                grid.mount(Static(
                    f"No sessions in {SESSIONS_DIR}",
                    classes="card-meta",
                ))
                self._set_selected_session(None)
                return
            sel_name = (
                self._selected_session.get("name")
                if self._selected_session else None
            )
            # Drop selection if file gone
            if sel_name and not any(s["name"] == sel_name for s in self._sessions):
                self._selected_session = None
                sel_name = None
            for s in self._sessions[:MAX_SESSIONS_DISPLAY]:
                grid.mount(SessionTile(s, selected=(s.get("name") == sel_name)))
            try:
                self.query_one("#sessions-list").scroll_home(animate=False)
            except Exception:
                pass
            self._refresh_selected_label()
        except Exception as e:
            logger.debug("Sessions update failed: %s", e)

    def _refresh_session_browser_select(self):
        """Refresh browser dropdown from profile discovery cache."""
        try:
            from tokenade.tui.views.sessions import launch_browser_options

            sel = self.query_one("#session-browser-select")
            opts = launch_browser_options()
            prev = None
            try:
                blank = getattr(Select, "NULL", Select.BLANK)
                cur = sel.value
                if cur is not blank and cur not in (None, "", False):
                    prev = str(cur)
            except Exception:
                prev = None
            sel.set_options(opts)
            values = [v for _, v in opts]
            pick = prev if prev in values else (
                "cloak" if "cloak" in values else (values[0] if values else None)
            )
            if pick is not None:
                sel.value = pick
            self._refresh_session_profile_select(str(pick or "cloak"))
        except Exception as e:
            logger.debug("Browser select refresh failed: %s", e)

    def _refresh_session_profile_select(self, browser: str | None = None):
        """Fill profile dropdown for the current browser."""
        try:
            from tokenade.tui.views.sessions import launch_profile_options

            browser = browser or self._session_browser()
            sel = self.query_one("#session-profile-select")
            opts = launch_profile_options(browser)
            prev = None
            try:
                blank = getattr(Select, "NULL", Select.BLANK)
                cur = sel.value
                if cur is not blank and cur not in (None, False):
                    prev = str(cur)
            except Exception:
                prev = None
            from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery

            clean = BrowserProfileDiscovery.CLEAN_PROFILE_VALUE
            sel.set_options(opts)
            values = [v for _, v in opts]
            pick = prev if prev in values else None
            if pick is None:
                for label, val in opts:
                    if "· default" in label or label.endswith(" default"):
                        if val in values:
                            pick = val
                            break
            if pick is None:
                pick = clean if clean in values else (values[0] if values else clean)
            try:
                sel.value = pick
            except Exception:
                if values:
                    sel.value = values[0]
        except Exception as e:
            logger.debug("Profile select refresh failed: %s", e)

    def on_select_changed(self, event) -> None:
        """When browser changes, reload profile list for that browser."""
        try:
            cid = getattr(event.control, "id", None)
            blank = getattr(Select, "NULL", Select.BLANK)
            val = event.value
            if val is blank or val in (None, False):
                return
            if cid == "session-browser-select":
                self._refresh_session_profile_select(str(val))
            elif cid == "export-browser-select":
                self._refresh_export_profile_select(str(val))
        except Exception:
            pass

    def _set_selected_session(self, session: Optional[Dict]):
        self._selected_session = session
        self._refresh_selected_label()
        self._fill_session_url(session)
        # Re-tint tiles without full rebuild when possible
        try:
            sel_name = session.get("name") if session else None
            for tile in self.query("SessionTile"):
                if sel_name and tile.session.get("name") == sel_name:
                    tile.add_class("-selected")
                else:
                    tile.remove_class("-selected")
        except Exception:
            pass

    def _fill_session_url(self, session: Optional[Dict]):
        """Auto-fill URL input from session metadata / cookies."""
        try:
            url_input = self.query_one("#session-url-input")
        except Exception:
            return
        if not session:
            return
        url = (session.get("url") or "").strip()
        if not url:
            # Re-parse file in case list entry is stale
            try:
                import json as _json
                with open(session["file"], encoding="utf-8") as fh:
                    data = _json.load(fh)
                url = detect_session_url(data) if isinstance(data, dict) else ""
            except Exception:
                url = ""
        if url:
            try:
                url_input.value = url
            except Exception:
                pass

    def _refresh_selected_label(self):
        try:
            label = self.query_one("#session-selected-label")
            if self._selected_session:
                s = self._selected_session
                flag = " ⚠ CORRUPT" if s.get("corrupt") else ""
                url = s.get("url") or ""
                extra = f"  ·  {url}" if url else ""
                label.update(
                    f"Selected: {s['name']}{flag}  ·  {s.get('site', '?')}  ·  {s['file']}{extra}"
                )
            else:
                label.update("No session selected — click Sel on a tile")
        except Exception:
            pass

    def _session_cli_log(self, text: str):
        """Append CLI output to the scrollable RichLog panel."""
        try:
            log = self.query_one("#session-cli-log")
        except Exception:
            return
        try:
            # RichLog path
            write = getattr(log, "write", None)
            if callable(write):
                for line in (text or "").splitlines() or [text or ""]:
                    write(line)
                try:
                    log.scroll_end(animate=False)
                except Exception:
                    pass
                return
        except Exception:
            pass
        # Fallback Static
        try:
            prev = str(getattr(log, "renderable", None) or getattr(log, "content", "") or "")
            if prev in ("CLI output appears here", ""):
                merged = text
            else:
                merged = prev + "\n" + text
            lines = merged.splitlines()
            if len(lines) > 80:
                lines = lines[-80:]
            log.update("\n".join(lines))
        except Exception:
            pass

    def _copy_to_clipboard(self, text: str, label: str = "Copied") -> bool:
        """Best-effort clipboard; always leave text visible as fallback."""
        if not text:
            self.notify("Nothing to copy", severity="warning")
            return False
        methods = []
        ok = False
        # Textual native (may no-op in some terminals)
        try:
            if _TEXTUAL_AVAILABLE and hasattr(self, "copy_to_clipboard"):
                self.copy_to_clipboard(text)
                methods.append("textual")
                ok = True
        except Exception:
            pass
        ok2, method = copy_text(text)
        if ok2:
            ok = True
            methods.append(method)
        # Always surface in share result + session log so user can select/copy
        self._session_cli_log(f"[clipboard:{'+'.join(methods) or 'none'}]\n{text[:2000]}")
        try:
            container = self.query_one("#share-result")
            container.mount(Static("— copied text —", classes="card-meta"))
            # chunk long URLs so they wrap in the TUI
            chunk = 100
            for i in range(0, min(len(text), 4000), chunk):
                container.mount(Static(text[i:i + chunk], classes="session-card"))
        except Exception:
            pass
        if ok:
            self.notify(f"{label} ({', '.join(methods)})", timeout=3)
        else:
            self.notify(
                f"{label} failed — text shown in panel (select & copy manually)",
                severity="warning",
                timeout=5,
            )
        return ok

    def _require_selected_session(self) -> Optional[Dict]:
        if not self._selected_session:
            self.notify("Select a session first (Sel button)", severity="warning")
            return None
        path = Path(self._selected_session["file"])
        if not path.exists():
            self.notify(f"Session file missing: {path}", severity="error")
            self._set_selected_session(None)
            return None
        return self._selected_session

    def _session_browser(self) -> str:
        try:
            val = self.query_one("#session-browser-select").value
            blank = getattr(Select, "NULL", Select.BLANK)
            if val is blank or val in (None, "", False):
                return "cloak"
            return str(val)
        except Exception:
            return "cloak"

    def _session_profile(self) -> str:
        """Discovered profile name for launch, or empty for clean profile."""
        try:
            from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery

            clean = BrowserProfileDiscovery.CLEAN_PROFILE_VALUE
            val = self.query_one("#session-profile-select").value
            blank = getattr(Select, "NULL", Select.BLANK)
            if val is blank or val in (None, False, "", clean):
                return ""
            return str(val).strip()
        except Exception:
            return ""

    def _session_url(self) -> str:
        try:
            return self.query_one("#session-url-input").value.strip()
        except Exception:
            return ""

    def _run_session_cli(self, args: List[str], *, background: bool = False, title: str = ""):
        cmdline = " ".join(args)
        self._session_cli_log(f"$ python3 -m tokenade {cmdline}")
        self.notify(f"Running {title or args[0]}…", timeout=2)

        def _done(result):
            def _ui():
                tag = title or (args[0] if args else "cmd")
                if result.ok:
                    self.notify(f"{tag} OK", timeout=3)
                else:
                    self.notify(
                        f"{tag} failed (exit {result.returncode})",
                        severity="error",
                        timeout=5,
                    )
                out = result.output or result.stdout or "(no output)"
                # Cap per-write but RichLog keeps history
                self._session_cli_log(out[-4000:] if len(out) > 4000 else out)
                if result.log_path:
                    self._session_cli_log(f"(full log: {result.log_path})")
                if args and args[0] in ("health", "refresh-browser"):
                    self._load_sessions()
                    self._update_sessions()

            try:
                self.call_from_thread(_ui)
            except Exception:
                _ui()

        # refresh-browser can take a while (navigate + wait); allow 4 min
        timeout = None if background else (240 if (args and args[0] == "refresh-browser") else 180)
        run_tokenade_async(
            args,
            on_done=_done,
            timeout=timeout,
            background=background,
        )

    def _update_vault(self):
        try:
            container = self.query_one("#vault-list")
            container.remove_children()
            try:
                from tokenade.core.vault.vault import SessionVault, VaultConfig
                vault = SessionVault(VaultConfig(vault_path=str(VAULT_DIR)))
                result = vault.list_entries()
                entries = result.data if result.success and result.data else []
                if not entries:
                    container.mount(Static("  Vault is empty.", classes="session-card"))
                    return
                for entry in entries:
                    name = entry.get("name", "?")
                    created = entry.get("created_at", 0)
                    created_s = (
                        time.strftime("%Y-%m-%d %H:%M", time.localtime(created))
                        if created else "?"
                    )
                    container.mount(Static(
                        f"  {name}  •  created: {created_s}",
                        classes="session-card",
                    ))
                    container.mount(Horizontal(
                        Button(
                            "Retrieve",
                            variant="primary",
                            compact=True,
                            id=f"vault-retrieve-{name}",
                        ),
                        Button(
                            "Delete",
                            variant="error",
                            compact=True,
                            id=f"vault-delete-{name}",
                        ),
                    ))
            except Exception as e:
                container.mount(Static(f"  Vault unavailable: {e}", classes="session-card"))
        except Exception as e:
            logger.debug("Vault update failed: %s", e)

    def _update_settings(self):
        try:
            from tokenade.core.config import load_config
            cfg = load_config()
            try:
                self.query_one("#current-registry").update(
                    "default: https://github.com/mihir0209/tokenade-plugins"
                )
            except Exception:
                pass
            for wid, val in (
                ("#settings-tokenade-dir", f"home:      {TOKENADE_DIR}"),
                ("#settings-sessions-dir", f"sessions:  {SESSIONS_DIR}"),
                ("#settings-vault-dir", f"vault:     {VAULT_DIR}"),
                ("#settings-analytics-dir", f"analytics: {ANALYTICS_DIR}"),
                ("#settings-plugins-dir", f"plugins:   {PLUGINS_DIR}"),
            ):
                try:
                    self.query_one(wid).update(val)
                except Exception:
                    pass

            def _set_select(sel_id: str, value):
                try:
                    sel = self.query_one(sel_id)
                    blank = getattr(Select, "NULL", Select.BLANK)
                    if value in (None, ""):
                        sel.value = blank
                    else:
                        sel.value = value
                except Exception:
                    pass

            def _set_input(inp_id: str, value):
                try:
                    self.query_one(inp_id).value = "" if value is None else str(value)
                except Exception:
                    pass

            def _set_switch(sw_id: str, value: bool):
                try:
                    self.query_one(sw_id).value = bool(value)
                except Exception:
                    pass

            _set_select("#settings-default-browser", cfg.get("default_browser"))
            _set_select(
                "#settings-automation-browser",
                cfg.get("automation_browser") or "cloak",
            )
            _set_select(
                "#settings-stealth-level",
                cfg.get("stealth_level") or "maximum",
            )
            _set_input("#settings-default-profile", cfg.get("default_profile") or "")
            _set_input("#settings-output-dir", cfg.get("output_dir") or "")
            _set_input("#settings-proxy-host", cfg.get("proxy_host") or "127.0.0.1")
            _set_input("#settings-proxy-port", cfg.get("proxy_port") or 9223)
            _set_switch("#settings-visible", bool(cfg.get("visible")))
            _set_switch("#settings-auto-validate", bool(cfg.get("auto_validate", True)))
            _set_switch("#settings-encrypt", bool(cfg.get("encrypt_by_default")))
            _set_input("#settings-supabase-url", cfg.get("supabase_url") or "")
            _set_input("#settings-supabase-key", cfg.get("supabase_anon_key") or "")
            _set_switch(
                "#settings-supabase-use-default",
                bool(cfg.get("supabase_use_default", True)),
            )
            try:
                from tokenade.core.sharing.supabase_store import SupabaseConfig
                sc = SupabaseConfig.from_env()
                if not sc.enabled:
                    status = "Remote share: OFF (full URL still works offline)"
                elif sc.is_public_default:
                    status = f"Remote share: ON — public default ({sc.url})"
                else:
                    status = f"Remote share: ON — private ({sc.source}: {sc.url})"
                self.query_one("#settings-supabase-status").update(status)
            except Exception:
                pass
        except Exception as e:
            logger.debug("Settings update failed: %s", e)

    def _refresh_share_sessions(self):
        """Rebuild share session Select from ~/.tokenade/sessions."""
        try:
            opts = session_select_options(SESSIONS_DIR)
            sel = self.query_one("#share-session-select")
            if isinstance(sel, Static):
                return
            if hasattr(sel, "set_options"):
                sel.set_options(opts)
            else:
                # Fallback: clear + reassign
                sel._options = []  # type: ignore[attr-defined]
                if opts:
                    sel.set_options(opts)
            self.notify(f"{len(opts)} sessions available", timeout=2)
        except Exception as e:
            logger.debug("Share session refresh failed: %s", e)

    # ── Plugin Actions ────────────────────────────────────────

    def install_plugin(self, name: str):
        try:
            from tokenade.core.integration.plugin_registry import PluginRegistry
            ok = PluginRegistry().install(name)
            if ok:
                self.notify(f"Installed: {name}", timeout=3)
                self._load_data()
            else:
                self.notify(f"Failed to install: {name}", severity="error")
        except Exception as e:
            self.notify(f"Install error: {e}", severity="error")

    def uninstall_plugin(self, name: str):
        try:
            from tokenade.core.integration.plugin_registry import PluginRegistry
            ok = PluginRegistry().uninstall(name)
            if ok:
                self.notify(f"Uninstalled: {name}", timeout=3)
                self._load_data()
            else:
                self.notify(f"Failed to uninstall: {name}", severity="error")
        except Exception as e:
            self.notify(f"Uninstall error: {e}", severity="error")

    def _reload_plugin(self, name: str):
        try:
            from tokenade.core.integration.plugin_loader import PluginLoader
            loaded = PluginLoader().reload(name)
            if loaded:
                self.notify(f"Reloaded: {name}", timeout=3)
                self._load_data()
            else:
                self.notify(f"Reload failed: {name}", severity="error")
        except Exception as e:
            self.notify(f"Reload error: {e}", severity="error")

    def _configure_plugin(self, name: str):
        self.push_screen(PluginConfigScreen(name))

    # ── Button Handlers ───────────────────────────────────────

    @on(Button.Pressed)
    def handle_button(self, event: Button.Pressed):
        btn_id = event.button.id or ""

        if btn_id.startswith("install-"):
            self.install_plugin(btn_id.removeprefix("install-"))
        elif btn_id.startswith("uninstall-"):
            self.uninstall_plugin(btn_id.removeprefix("uninstall-"))
        elif btn_id.startswith("reload-"):
            self._reload_plugin(btn_id.removeprefix("reload-"))
        elif btn_id.startswith("configure-"):
            self._configure_plugin(btn_id.removeprefix("configure-"))
        elif btn_id.startswith("details-"):
            name = btn_id.removeprefix("details-")
            plugin = next((p for p in self._plugins if p.get("name") == name), None)
            if plugin:
                self.push_screen(PluginDetailScreen(plugin))
        elif btn_id in ("sync-plugins", "sync-plugins-settings", "refresh-installed", "refresh-all"):
            self._load_data()
            self.notify("Refreshed", timeout=2)
        elif btn_id == "vault-refresh":
            self._update_vault()
            self.notify("Vault refreshed", timeout=2)
        elif btn_id == "vault-rotate-key":
            self._vault_rotate_key()
        elif btn_id == "vault-backup":
            self._vault_backup()
        elif btn_id.startswith("vault-retrieve-"):
            self._vault_retrieve(btn_id.removeprefix("vault-retrieve-"))
        elif btn_id.startswith("vault-delete-"):
            self._vault_delete(btn_id.removeprefix("vault-delete-"))
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
        elif btn_id == "share-refresh-sessions":
            self._refresh_share_sessions()
        elif btn_id == "analytics-report":
            self._analytics_report()
        elif btn_id == "analytics-csv":
            self._analytics_export_csv()
        elif btn_id == "analytics-cleanup":
            self._analytics_cleanup()
        elif btn_id.startswith("health-"):
            self._session_health(btn_id.removeprefix("health-"))
        elif btn_id.startswith("delete-"):
            self._session_delete(btn_id.removeprefix("delete-"))
        elif btn_id.startswith("select-"):
            self._session_select(btn_id.removeprefix("select-"))
        elif btn_id == "session-launch":
            self._session_action_launch()
        elif btn_id == "session-load":
            self._session_action_load()
        elif btn_id == "session-refresh":
            self._session_action_refresh()
        elif btn_id == "session-health-cli":
            self._session_action_health_cli()
        elif btn_id == "session-share":
            self._session_action_share()
        elif btn_id == "session-copy-path":
            self._session_action_copy_path()
        elif btn_id == "export-run":
            self._export_run()
        elif btn_id == "export-list-profiles":
            self._export_list_profiles()
        elif btn_id == "export-list-handlers":
            self._export_list_handlers()
        elif btn_id == "export-refresh":
            self._export_refresh()
        elif btn_id == "share-copy-full":
            self._share_copy("full")
        elif btn_id == "share-copy-id":
            self._share_copy("id")
        elif btn_id == "share-copy-cmd":
            self._share_copy("cmd")
        elif btn_id == "share-receive":
            self._share_receive()
        elif btn_id == "add-registry":
            self._add_registry()
        elif btn_id == "reset-registry":
            self._reset_registry()
        elif btn_id == "settings-save":
            self._settings_save()
        elif btn_id == "settings-reload":
            self._update_settings()
            self.notify("Settings reloaded", timeout=2)

    @on(Input.Submitted, "#search-input")
    def on_search(self, event: Input.Submitted):
        query = (event.value or "").strip().lower()
        try:
            from tokenade.core.integration.plugin_registry import PluginRegistry
            if query:
                self._plugins = PluginRegistry().search(query=query) or []
            else:
                self._plugins = PluginRegistry().get_popular(limit=100) or []
            self._update_marketplace()
        except Exception as e:
            self.notify(f"Search error: {e}", severity="error")

    # ── Vault Actions ─────────────────────────────────────────

    def _vault_rotate_key(self):
        try:
            from tokenade.core.vault.vault import SessionVault, VaultConfig
            result = SessionVault(VaultConfig(vault_path=str(VAULT_DIR))).rotate_key()
            if result.success:
                self.notify(result.message or "Vault key rotated", timeout=3)
                self._update_vault()
            else:
                self.notify(result.message or "Key rotation failed", severity="error")
        except Exception as e:
            self.notify(f"Key rotation error: {e}", severity="error")

    def _vault_backup(self):
        try:
            from tokenade.core.vault.vault import SessionVault, VaultConfig
            result = SessionVault(VaultConfig(vault_path=str(VAULT_DIR))).backup()
            if result.success:
                self.notify(result.message or "Vault backed up", timeout=3)
            else:
                self.notify(result.message or "Backup failed", severity="error")
        except Exception as e:
            self.notify(f"Backup error: {e}", severity="error")

    def _vault_retrieve(self, name: str):
        try:
            from tokenade.core.vault.vault import SessionVault, VaultConfig
            out = SESSIONS_DIR / f"{name}.tokenade"
            result = SessionVault(VaultConfig(vault_path=str(VAULT_DIR))).retrieve(
                name, output_path=str(out),
            )
            if result.success:
                self.notify(f"Retrieved to {out.name}", timeout=3)
                self._load_sessions()
                self._update_sessions()
            else:
                self.notify(result.message or "Retrieve failed", severity="error")
        except Exception as e:
            self.notify(f"Retrieve error: {e}", severity="error")

    def _vault_delete(self, name: str):
        try:
            from tokenade.core.vault.vault import SessionVault, VaultConfig
            result = SessionVault(VaultConfig(vault_path=str(VAULT_DIR))).delete(name)
            if result.success:
                self.notify(f"Deleted vault entry: {name}", timeout=3)
                self._update_vault()
            else:
                self.notify(result.message or "Delete failed", severity="error")
        except Exception as e:
            self.notify(f"Delete error: {e}", severity="error")

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

    def _render_sync_dict(self, title: str, data: Dict[str, Any]):
        container = self.query_one("#sync-result")
        container.remove_children()
        container.mount(Static(f"  {title}", classes="session-card"))
        for k, v in data.items():
            if k == "config":
                continue
            container.mount(Static(f"  {k}: {v}", classes="session-card"))

    def _sync_status(self):
        try:
            config = self._get_sync_config()
            if not config:
                return
            from tokenade.core.sync.syncer import SessionSyncer
            status = SessionSyncer(config).status()
            self._render_sync_dict(f"Remote: {config.remote_host}", status)
        except Exception as e:
            self.notify(f"Sync status error: {e}", severity="error")

    def _sync_push(self):
        try:
            config = self._get_sync_config()
            if not config:
                return
            from tokenade.core.sync.syncer import SessionSyncer
            result = SessionSyncer(config).push()
            msg = getattr(result, "message", None) or str(result)
            self.notify(f"Push: {msg}", timeout=3)
        except Exception as e:
            self.notify(f"Push error: {e}", severity="error")

    def _sync_pull(self):
        try:
            config = self._get_sync_config()
            if not config:
                return
            from tokenade.core.sync.syncer import SessionSyncer
            result = SessionSyncer(config).pull()
            msg = getattr(result, "message", None) or str(result)
            self.notify(f"Pull: {msg}", timeout=3)
            self._load_sessions()
            self._update_sessions()
        except Exception as e:
            self.notify(f"Pull error: {e}", severity="error")

    def _sync_bidirectional(self):
        try:
            config = self._get_sync_config()
            if not config:
                return
            from tokenade.core.sync.syncer import SessionSyncer
            result = SessionSyncer(config).sync("bidirectional")
            msg = getattr(result, "message", None) or str(result)
            self.notify(f"Sync: {msg}", timeout=3)
            self._load_sessions()
            self._update_sessions()
        except Exception as e:
            self.notify(f"Sync error: {e}", severity="error")

    # ── Share Actions ─────────────────────────────────────────

    def _resolve_share_session_path(self) -> Optional[Path]:
        """Prefer Select value, fall back to free-text path input."""
        path_s = ""
        try:
            sel = self.query_one("#share-session-select")
            if not isinstance(sel, Static):
                blank = getattr(Select, "NULL", Select.BLANK)
                val = getattr(sel, "value", blank)
                if val is not blank and val is not Select.BLANK and val not in (None, "", False):
                    path_s = str(val)
        except Exception:
            pass
        if not path_s:
            try:
                path_s = self.query_one("#share-session-input").value.strip()
            except Exception:
                path_s = ""
        if not path_s:
            return None
        path = Path(path_s).expanduser()
        if not path.is_absolute():
            path = SESSIONS_DIR / path_s
            if not path.suffix:
                path = path.with_suffix(".tokenade")
        return path

    def _share_create(self):
        try:
            path = self._resolve_share_session_path()
            password = self.query_one("#share-password-input").value
            confirm = ""
            try:
                confirm = self.query_one("#share-password-confirm").value
            except Exception:
                confirm = password
            expiry = self.query_one("#share-expiry-input").value.strip()
            max_uses = self.query_one("#share-max-uses-input").value.strip()

            if not path:
                self.notify("Pick a session or paste a .tokenade path", severity="warning")
                return
            if not path.exists():
                self.notify(f"Session not found: {path}", severity="error")
                return
            if not password or len(password) < 8:
                self.notify("Password required (min 8 characters)", severity="warning")
                return
            if confirm and password != confirm:
                self.notify("Passwords do not match", severity="warning")
                return

            from tokenade.core.sharing.url_shortener import (
                SessionURLShortener, URLShortenerConfig,
            )
            shortener = SessionURLShortener(URLShortenerConfig(require_password=True))
            result = shortener.create_share(
                session_file=str(path),
                password=password,
                expiry_hours=int(expiry) if expiry else 24,
                max_uses=int(max_uses) if max_uses else 0,
            )
            if not result.get("success", True):
                err = result.get("error") or result.get("message") or "Share failed"
                container = self.query_one("#share-result")
                container.remove_children()
                for line in (
                    f"Session:  {path.name}",
                    f"Error:    {err}",
                    f"Code:     {result.get('code') or '?'}",
                    f"Size:     {result.get('ciphertext_chars', '?')} / "
                    f"{result.get('max_chars', '?')} chars",
                    "",
                    result.get("message") or "",
                    "",
                    "Tip: re-export with --domains for the site, or scp the .tokenade file.",
                ):
                    container.mount(
                        Static(line or " ", classes="session-card" if line else "card-meta")
                    )
                self.notify(str(err)[:80], severity="error", timeout=8)
                return

            short_id = result.get("short_id", "")
            full_url = (
                result.get("full_url")
                or result.get("original_url")
                or ""
            )
            short_url = result.get("short_url") or f"tokenade://share/{short_id}"
            file_name = result.get("file_name") or path.name
            self._last_share = {
                "short_id": short_id,
                "full_url": full_url,
                "short_url": short_url,
                "password": password,
                "session": path.name,
                "file_name": file_name,
            }

            remote = bool(result.get("remote"))
            transport = result.get("transport") or ("supabase" if remote else "embedded")
            help_text = format_receive_help(
                short_id=short_id,
                full_url=full_url or short_url,
                short_url=short_url,
                password_hint="YOUR_PASSWORD",
                output=str(SESSIONS_DIR / file_name),
                remote=remote,
            )

            container = self.query_one("#share-result")
            container.remove_children()
            prune = "yes" if result.get("pruned") else "no"
            ct = result.get("ciphertext_chars")
            size_line = f"Ciphertext: {ct} chars" if ct else ""
            for line in (
                f"Session:    {path.name}",
                f"Transport:  {transport}",
                f"Short ID:   {short_id}",
                f"Short URL:  {short_url}",
                f"Pruned:     {prune}",
                size_line,
                "",
                (
                    "Full URL (payload embedded — offline):"
                    if full_url and "?data=" in full_url
                    else "Share ref (retrieve via short id + remote):"
                ),
            ):
                if not line and line != "":
                    continue
                container.mount(Static(line or " ", classes="session-card" if line else "card-meta"))
            # Show full URL in chunks so it's selectable in TUI
            show_url = full_url or short_url
            for i in range(0, min(len(show_url), 4000), 100):
                container.mount(Static(show_url[i:i + 100], classes="session-card"))
            if result.get("message"):
                container.mount(Static(" ", classes="card-meta"))
                container.mount(Static(str(result["message"])[:500], classes="card-meta"))
            container.mount(Static(" ", classes="card-meta"))
            for line in help_text.splitlines():
                container.mount(Static(line or " ", classes="card-meta"))

            # Prefer copying short id when remote works; else full URL
            if remote:
                self._copy_to_clipboard(short_id, "Short id copied")
                self.notify("Share created — short id copied", timeout=3)
            else:
                self._copy_to_clipboard(full_url or short_url, "Share URL copied")
                self.notify("Share created — URL copied", timeout=3)

            try:
                self.query_one("#share-password-input").value = ""
                self.query_one("#share-password-confirm").value = ""
            except Exception:
                pass
        except Exception as e:
            self.notify(f"Share error: {e}", severity="error")

    def _share_copy(self, kind: str):
        data = self._last_share or {}
        if kind == "full":
            text = data.get("full_url") or ""
            label = "Full URL copied"
        elif kind == "id":
            text = data.get("short_id") or ""
            label = "Short id copied"
        else:
            sid = data.get("short_id") or "SHORT_ID"
            out_name = data.get("file_name") or "received.tokenade"
            text = (
                f"python3 -m tokenade share-url retrieve {sid} "
                f"--password 'YOUR_PASSWORD' -o {out_name}"
            )
            label = "Receive command copied"
        if not text or text in ("", "SHORT_ID"):
            self.notify("Create a share first", severity="warning")
            return
        self._copy_to_clipboard(text, label)

    def _share_receive(self):
        try:
            ref = self.query_one("#share-receive-input").value.strip()
            password = self.query_one("#share-receive-password").value
            out = self.query_one("#share-receive-output").value.strip()
            if not ref:
                self.notify("Paste short id or tokenade:// URL", severity="warning")
                return
            if not password or len(password) < 8:
                self.notify("Password required (min 8)", severity="warning")
                return
            from tokenade.core.sharing.url_shortener import (
                SessionURLShortener, URLShortenerConfig,
            )
            result = SessionURLShortener(URLShortenerConfig()).retrieve_session(
                ref,
                password,
                output_path=out or None,
                default_dir=str(SESSIONS_DIR),
            )
            container = self.query_one("#share-result")
            container.remove_children()
            if result.get("success"):
                saved = result.get("output_path") or out or "?"
                container.mount(Static(f"  Saved → {saved}", classes="session-card"))
                container.mount(Static(
                    f"  Next: python3 -m tokenade load --file {saved} --visible",
                    classes="session-card",
                ))
                container.mount(Static(
                    f"  Or:   python3 -m tokenade launch -s {saved} --visible",
                    classes="session-card",
                ))
                self.notify(f"Received → {saved}", timeout=3)
                self._load_sessions()
                self._update_sessions()
            else:
                err = result.get("error") or "receive failed"
                container.mount(Static(f"  Error: {err}", classes="session-card"))
                self.notify(err, severity="error")
        except Exception as e:
            self.notify(f"Receive error: {e}", severity="error")

    def _share_list(self):
        try:
            from tokenade.core.sharing.url_shortener import (
                SessionURLShortener, URLShortenerConfig,
            )
            shares = SessionURLShortener(URLShortenerConfig()).list_shares()
            container = self.query_one("#share-result")
            container.remove_children()
            if not shares:
                container.mount(Static("  No active shares.", classes="session-card"))
                return
            for share in shares:
                sid = share.get("short_id") or share.get("share_id") or "?"
                uses = share.get("current_uses", share.get("uses", 0))
                max_uses = share.get("max_uses", 0)
                max_s = "∞" if not max_uses else str(max_uses)
                container.mount(Static(
                    f"  {sid}  •  uses: {uses}/{max_s}",
                    classes="session-card",
                ))
        except Exception as e:
            self.notify(f"Share list error: {e}", severity="error")

    def _share_cleanup(self):
        try:
            from tokenade.core.sharing.url_shortener import (
                SessionURLShortener, URLShortenerConfig,
            )
            stats = SessionURLShortener(URLShortenerConfig()).cleanup_local_store()
            self.notify(
                f"Cleaned shares: expired={stats.get('expired', 0)} "
                f"stripped={stats.get('stripped', 0)} "
                f"remaining={stats.get('remaining', 0)}",
                timeout=4,
            )
            self._share_list()
        except Exception as e:
            self.notify(f"Cleanup error: {e}", severity="error")

    # ── Analytics Actions ─────────────────────────────────────

    def _analytics_report(self):
        try:
            from tokenade.core.analytics.engine import AnalyticsEngine
            report = AnalyticsEngine().generate_report()
            container = self.query_one("#analytics-result")
            container.remove_children()
            container.mount(Static(
                f"  Period: {report.period_days} days",
                classes="session-card",
            ))
            container.mount(Static(
                f"  Total events: {report.total_events}",
                classes="session-card",
            ))
            container.mount(Static(
                f"  Exports: {report.total_exports}",
                classes="session-card",
            ))
            container.mount(Static(
                f"  Loads: {report.total_loads}",
                classes="session-card",
            ))
            container.mount(Static(
                f"  Shares: {report.total_shares}",
                classes="session-card",
            ))
            container.mount(Static(
                f"  Syncs: {report.total_syncs}",
                classes="session-card",
            ))
            container.mount(Static(
                f"  Success rate: {report.success_rate:.1%}",
                classes="session-card",
            ))
            if report.top_sites:
                container.mount(Static("  Top sites:", classes="session-card"))
                for s in report.top_sites[:5]:
                    site = s.get("site", "?") if isinstance(s, dict) else getattr(s, "site", "?")
                    events = (
                        s.get("events") or s.get("total_events") or 0
                        if isinstance(s, dict) else getattr(s, "total_events", 0)
                    )
                    container.mount(Static(
                        f"    {site}: {events} events",
                        classes="session-card",
                    ))
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

    def _session_select(self, name: str):
        session = next((s for s in self._sessions if s["name"] == name), None)
        if session:
            self._set_selected_session(session)
            url = (session.get("url") or "").strip()
            if session.get("corrupt"):
                self.notify(f"Selected {name} (corrupt/empty — re-export)", severity="warning", timeout=4)
            elif url:
                self.notify(f"Selected {name} → {url}", timeout=2)
            else:
                self.notify(f"Selected {name}", timeout=2)

    def _session_health(self, name: str):
        session = next((s for s in self._sessions if s["name"] == name), None)
        if session:
            self._set_selected_session(session)
            self.notify(
                f"{name}: health={session['health']:.0f}%, cookies={session['cookies']}",
                timeout=3,
            )
            # Also run real CLI health
            self._run_session_cli(
                cmd_health(session["file"]),
                title="health",
            )

    def _session_delete(self, name: str):
        session = next((s for s in self._sessions if s["name"] == name), None)
        if session:
            try:
                Path(session["file"]).unlink()
                if self._selected_session and self._selected_session.get("name") == name:
                    self._set_selected_session(None)
                self.notify(f"Deleted: {name}", timeout=3)
                self._load_sessions()
                self._update_sessions()
            except Exception as e:
                self.notify(f"Delete error: {e}", severity="error")

    def _session_action_launch(self):
        s = self._require_selected_session()
        if not s:
            return
        self._run_session_cli(
            cmd_launch(
                s["file"],
                browser=self._session_browser(),
                url=self._session_url(),
                visible=True,
                profile=self._session_profile(),
            ),
            background=True,
            title="launch",
        )

    def _session_action_load(self):
        s = self._require_selected_session()
        if not s:
            return
        self._run_session_cli(
            cmd_load(s["file"], visible=True, validate=False),
            background=True,
            title="load",
        )

    def _session_action_refresh(self):
        s = self._require_selected_session()
        if not s:
            return
        if s.get("corrupt"):
            self.notify("Session file is corrupt/empty — cannot refresh", severity="error")
            return
        self._run_session_cli(
            cmd_refresh_browser(
                s["file"],
                browser=self._session_browser(),
                url=self._session_url(),
                headless=True,
            ),
            background=False,
            title="refresh-browser",
        )

    def _session_action_health_cli(self):
        s = self._require_selected_session()
        if not s:
            return
        self._run_session_cli(cmd_health(s["file"]), title="health")

    def _activate_tab(self, pane_id: str) -> bool:
        """Switch main TabbedContent to pane_id (e.g. 'tab-share')."""
        try:
            tabs = self.query_one("#main-tabs")
        except Exception:
            return False
        try:
            # Textual 8+: show_tab is the reliable API
            if hasattr(tabs, "show_tab"):
                tabs.show_tab(pane_id)
            tabs.active = pane_id
            return True
        except Exception as e:
            logger.debug("activate tab %s failed: %s", pane_id, e)
            try:
                tabs.active = pane_id
                return True
            except Exception:
                return False

    def _session_action_share(self):
        s = self._require_selected_session()
        if not s:
            return
        if s.get("corrupt"):
            self.notify("Session file is corrupt/empty — cannot share", severity="error")
            return
        path = s["file"]
        name = s["name"]
        # Switch tab first, then prefill after layout settles
        ok = self._activate_tab("tab-share")
        if not ok:
            self.notify("Could not open Share tab — press 3", severity="warning")

        def _prefill():
            try:
                self._refresh_share_sessions()
            except Exception:
                pass
            try:
                self.query_one("#share-session-input").value = path
            except Exception:
                pass
            try:
                sel = self.query_one("#share-session-select")
                if not isinstance(sel, Static):
                    try:
                        opts = session_select_options()
                        if hasattr(sel, "set_options"):
                            sel.set_options(opts)
                    except Exception:
                        pass
                    try:
                        sel.value = path
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                # Focus password so user can type immediately
                self.query_one("#share-password-input").focus()
            except Exception:
                pass
            self.notify(f"Share: {name} ready — set password & Create", timeout=4)

        try:
            self.call_after_refresh(_prefill)
        except Exception:
            _prefill()

    def _force_share_select(self, path: str):
        try:
            sel = self.query_one("#share-session-select")
            if not isinstance(sel, Static):
                sel.value = path
        except Exception:
            pass

    def _session_action_copy_path(self):
        s = self._require_selected_session()
        if not s:
            return
        self._copy_to_clipboard(s["file"], "Path copied")

    # ── Settings Actions ──────────────────────────────────────

    def _settings_save(self):
        try:
            from tokenade.core.config import load_config

            def _sel(sel_id: str):
                try:
                    val = self.query_one(sel_id).value
                    blank = getattr(Select, "NULL", Select.BLANK)
                    if val is blank or val is Select.BLANK or val in (None, "", False):
                        return None
                    return val
                except Exception:
                    return None

            def _inp(inp_id: str):
                try:
                    return self.query_one(inp_id).value.strip()
                except Exception:
                    return ""

            def _sw(sw_id: str, default=False):
                try:
                    return bool(self.query_one(sw_id).value)
                except Exception:
                    return default

            cfg = load_config()
            cfg.set("default_browser", _sel("#settings-default-browser"))
            cfg.set(
                "automation_browser",
                _sel("#settings-automation-browser") or "cloak",
            )
            cfg.set(
                "stealth_level",
                _sel("#settings-stealth-level") or "maximum",
            )
            profile = _inp("#settings-default-profile")
            cfg.set("default_profile", profile or None)
            out = _inp("#settings-output-dir")
            cfg.set("output_dir", out or None)
            cfg.set("proxy_host", _inp("#settings-proxy-host") or "127.0.0.1")
            port_s = _inp("#settings-proxy-port") or "9223"
            try:
                cfg.set("proxy_port", int(port_s))
            except ValueError:
                cfg.set("proxy_port", 9223)
            cfg.set("visible", _sw("#settings-visible", False))
            cfg.set("auto_validate", _sw("#settings-auto-validate", True))
            cfg.set("encrypt_by_default", _sw("#settings-encrypt", False))
            sb_url = _inp("#settings-supabase-url")
            sb_key = _inp("#settings-supabase-key")
            cfg.set("supabase_url", sb_url or None)
            cfg.set("supabase_anon_key", sb_key or None)
            cfg.set(
                "supabase_use_default",
                _sw("#settings-supabase-use-default", True),
            )
            cfg.save()
            try:
                self.query_one("#settings-status").update(
                    f"Saved → {cfg.config_path}"
                )
            except Exception:
                pass
            try:
                from tokenade.core.sharing.supabase_store import SupabaseConfig
                sc = SupabaseConfig.from_env()
                if not sc.enabled:
                    st = "Remote share: OFF (full URL still works offline)"
                elif sc.is_public_default:
                    st = f"Remote share: ON — public default ({sc.url})"
                else:
                    st = f"Remote share: ON — private ({sc.source}: {sc.url})"
                self.query_one("#settings-supabase-status").update(st)
            except Exception:
                pass
            self.notify(f"Settings saved to {cfg.config_path}", timeout=3)
        except Exception as e:
            self.notify(f"Save failed: {e}", severity="error")

    def _add_registry(self):
        try:
            url = self.query_one("#registry-url").value.strip()
            if not url:
                self.notify("Enter a registry URL", severity="warning")
                return
            from tokenade.core.integration.plugin_registry import PluginRegistry
            reg = PluginRegistry()
            if hasattr(reg, "add_registry"):
                reg.add_registry(url)
            self.notify(f"Registry added: {url}", timeout=3)
            self._load_plugins()
            self._update_marketplace()
        except Exception as e:
            self.notify(f"Registry error: {e}", severity="error")

    def _reset_registry(self):
        self.notify("Registry reset to default", timeout=3)
        self._load_plugins()
        self._update_marketplace()

    # ── Export Actions ────────────────────────────────────────

    def _export_cli_log(self, text: str):
        try:
            log = self.query_one("#export-cli-log")
        except Exception:
            return
        try:
            write = getattr(log, "write", None)
            if callable(write):
                for line in (text or "").splitlines() or [text or ""]:
                    write(line)
                try:
                    log.scroll_end(animate=False)
                except Exception:
                    pass
                return
        except Exception:
            pass

    def _export_field(self, wid: str) -> str:
        try:
            from tokenade.tui.views.export import NONE_VALUE

            w = self.query_one(wid)
            blank = getattr(Select, "NULL", Select.BLANK)
            val = getattr(w, "value", None)
            if val is blank or val in (None, False, NONE_VALUE):
                return ""
            return str(val).strip()
        except Exception:
            return ""

    def _export_switch(self, wid: str, default: bool = False) -> bool:
        try:
            return bool(self.query_one(wid).value)
        except Exception:
            return default

    def _refresh_export_browser_select(self, *, refresh_cache: bool = False):
        try:
            from tokenade.tui.views.export import export_browser_options

            sel = self.query_one("#export-browser-select")
            opts = export_browser_options(refresh=refresh_cache)
            prev = self._export_field("#export-browser-select")
            sel.set_options(opts)
            values = [v for _, v in opts]
            pick = prev if prev in values else (
                "firefox" if "firefox" in values else (values[0] if values else None)
            )
            if pick is not None:
                sel.value = pick
            self._refresh_export_profile_select(str(pick or "firefox"), refresh_cache=refresh_cache)
        except Exception as e:
            logger.debug("Export browser select refresh failed: %s", e)

    def _refresh_export_profile_select(
        self, browser: str | None = None, *, refresh_cache: bool = False
    ):
        try:
            from tokenade.tui.views.export import export_profile_options

            browser = browser or self._export_field("#export-browser-select") or "firefox"
            sel = self.query_one("#export-profile-select")
            opts = export_profile_options(browser, refresh=refresh_cache)
            prev = self._export_field("#export-profile-select")
            sel.set_options(opts)
            values = [v for _, v in opts]
            pick = prev if prev in values else None
            if pick is None:
                for label, val in opts:
                    if "· default" in label or label.endswith(" default"):
                        if val in values:
                            pick = val
                            break
            if pick is None:
                pick = values[0] if values else "default"
            try:
                sel.value = pick
            except Exception:
                if values:
                    sel.value = values[0]
        except Exception as e:
            logger.debug("Export profile select refresh failed: %s", e)

    def _run_export_cli(self, args: List[str], *, title: str = ""):
        cmdline = " ".join(args)
        self._export_cli_log(f"$ python3 -m tokenade {cmdline}")
        self.notify(f"Running {title or args[0]}…", timeout=2)

        def _done(result):
            def _ui():
                tag = title or (args[0] if args else "export")
                if result.ok:
                    self.notify(f"{tag} OK", timeout=3)
                else:
                    self.notify(
                        f"{tag} failed (exit {result.returncode})",
                        severity="error",
                        timeout=5,
                    )
                out = result.output or result.stdout or "(no output)"
                self._export_cli_log(out[-4000:] if len(out) > 4000 else out)
                if result.log_path:
                    self._export_cli_log(f"(full log: {result.log_path})")
                if result.ok and args and args[0] == "export" and "--list-profiles" not in args and "--list-handlers" not in args:
                    try:
                        self._load_sessions()
                        self._update_sessions()
                        self._refresh_share_sessions()
                    except Exception:
                        pass

            try:
                self.call_from_thread(_ui)
            except Exception:
                _ui()

        # Cookie/SQLite export can be slow on large profiles
        run_tokenade_async(args, on_done=_done, timeout=300)

    def _export_run(self):
        browser = self._export_field("#export-browser-select")
        profile = self._export_field("#export-profile-select")
        domains = self._export_field("#export-domains-input")
        output = self._export_field("#export-output-input")
        cdp = self._export_field("#export-cdp-input")
        password = self._export_field("#export-password-input")
        plugin = self._export_field("#export-plugin-select")
        proxy_plugin = self._export_field("#export-proxy-select")
        if not cdp and not browser:
            self.notify("Select a browser or set CDP port", severity="warning")
            return
        if not output:
            output = str(SESSIONS_DIR / "export.tokenade")
        self._run_export_cli(
            cmd_export(
                browser_name=browser,
                profile=profile,
                domains=domains,
                output=output,
                full=self._export_switch("#export-full-switch", True),
                cdp_port=cdp,
                encrypt_password=password,
                plugin=plugin,
                proxy_plugin=proxy_plugin,
                no_plugin=self._export_switch("#export-no-plugin-switch", False),
                collect_fingerprint=self._export_switch(
                    "#export-fingerprint-switch", False
                ),
            ),
            title="export",
        )

    def _export_list_profiles(self):
        self._run_export_cli(cmd_export(list_profiles=True), title="list-profiles")

    def _export_list_handlers(self):
        self._run_export_cli(cmd_export(list_handlers=True), title="list-handlers")

    def _refresh_export_plugin_selects(self):
        try:
            from tokenade.tui.views.export import (
                NONE_VALUE,
                export_handler_options,
                export_proxy_plugin_options,
            )

            for sel_id, opts_fn in (
                ("#export-plugin-select", export_handler_options),
                ("#export-proxy-select", export_proxy_plugin_options),
            ):
                try:
                    sel = self.query_one(sel_id)
                    opts = opts_fn()
                    prev = self._export_field(sel_id)
                    sel.set_options(opts)
                    values = [v for _, v in opts]
                    if prev and prev in values:
                        sel.value = prev
                    elif NONE_VALUE in values:
                        sel.value = NONE_VALUE
                    elif values:
                        sel.value = values[0]
                except Exception:
                    pass
        except Exception as e:
            logger.debug("Export plugin select refresh failed: %s", e)

    def _export_refresh(self):
        self._refresh_export_browser_select(refresh_cache=True)
        self._refresh_export_plugin_selects()
        self.notify("Discovery refreshed", timeout=2)

    # ── Tab Navigation ────────────────────────────────────────

    def action_show_export(self):
        self._activate_tab("tab-export")

    def action_show_marketplace(self):
        self._activate_tab("tab-marketplace")

    def action_show_installed(self):
        self._activate_tab("tab-installed")

    def action_show_sessions(self):
        self._activate_tab("tab-sessions")

    def action_show_vault(self):
        self._activate_tab("tab-vault")

    def action_show_sync(self):
        self._activate_tab("tab-sync")

    def action_show_share(self):
        self._activate_tab("tab-share")

    def action_show_analytics(self):
        self._activate_tab("tab-analytics")

    def action_show_settings(self):
        self._activate_tab("tab-settings")

    def action_refresh(self):
        self._load_data()
        try:
            self._refresh_export_browser_select()
        except Exception:
            pass
        self.notify("Refreshed", timeout=2)

    def action_help(self):
        self.notify("1-9: tabs  r: refresh  q: quit", timeout=5)


def run_tui(mode: str = "full"):
    """Launch the TUI application."""
    if not _TEXTUAL_AVAILABLE:
        print("TUI requires textual: pip install 'tokenade[tui]'")
        return
    TokenadeTUI().run()


# ── Backward-compat widgets used by unit tests ────────────────


class PluginHealthWidget(Widget if _TEXTUAL_AVAILABLE else object):
    def __init__(self, installed: list, **kwargs):
        if _TEXTUAL_AVAILABLE:
            super().__init__(**kwargs)
        self.installed = installed

    def render(self):
        if not self.installed:
            return "  No plugins installed."
        lines = ["Plugin Health"]
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
    SENSITIVE_KEYS = {"password", "secret", "token", "api_key", "client_secret"}

    def __init__(self, installed: list, **kwargs):
        if _TEXTUAL_AVAILABLE:
            super().__init__(**kwargs)
        self.installed = installed

    def render(self):
        if not self.installed:
            return "  No plugins installed."
        lines = ["Plugin Configuration"]
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
                    lines.append(
                        f"    {t.get('plugin', '?')}: {t.get('name', '?')} "
                        f"({t.get('status', '?')})"
                    )
            if not active and not recent:
                lines.append("  No tasks recorded.")
            return "\n".join(lines)
        except Exception:
            return "  Task tracker unavailable."


RegistriesView = SettingsView


class PluginConfigScreen(Screen if _TEXTUAL_AVAILABLE else object):
    """Edit ~/.tokenade/plugins/<name>/config.json from manifest schema (or free-form keys)."""

    DEFAULT_CSS = """
    PluginConfigScreen { align: center middle; }
    PluginConfigScreen #pcfg-box {
        width: 72; height: auto; max-height: 36;
        background: $surface; border: tall $primary; padding: 1 2;
        overflow-y: auto;
    }
    PluginConfigScreen .pcfg-label { color: $text-muted; height: 1; margin-top: 1; }
    PluginConfigScreen .pcfg-hint { color: $text-muted; height: auto; }
    PluginConfigScreen .pcfg-row { height: 3; }
    PluginConfigScreen .pcfg-row Input { width: 1fr; }
    PluginConfigScreen .pcfg-actions { height: 3; margin-top: 1; }
    PluginConfigScreen .pcfg-actions Button { margin-right: 1; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
    ]

    SENSITIVE = ("password", "secret", "token", "api_key", "client_secret", "webhook")

    def __init__(self, plugin_name: str, **kwargs):
        if _TEXTUAL_AVAILABLE:
            super().__init__(**kwargs)
        self.plugin_name = plugin_name
        self._schema: dict = {}
        self._values: dict = {}
        self._field_keys: list = []

    def on_mount(self) -> None:
        try:
            from tokenade.core.integration.plugin_config import PluginConfigManager
            mgr = PluginConfigManager()
            self._schema = mgr.get_schema(self.plugin_name) or {}
            self._values = dict(mgr.get_full_config(self.plugin_name) or {})
            if not self._schema and self._values:
                # Free-form existing keys
                self._schema = {
                    k: {"type": "string", "default": v} for k, v in self._values.items()
                }
            self._field_keys = list(self._schema.keys()) if self._schema else []
            # Recompose fields dynamically
            try:
                box = self.query_one("#pcfg-fields")
                box.remove_children()
                if not self._field_keys:
                    box.mount(
                        Static(
                            "No config.schema in plugin.json.\n"
                            "Add keys below as KEY=value lines, one per line.\n"
                            f"Saved to ~/.tokenade/plugins/{self.plugin_name}/config.json",
                            classes="pcfg-hint",
                        )
                    )
                    try:
                        from textual.widgets import TextArea
                        lines = (
                            "\n".join(f"{k}={v}" for k, v in self._values.items())
                            if self._values
                            else ""
                        )
                        box.mount(
                            TextArea(
                                lines,
                                id="pcfg-freeform",
                            )
                        )
                    except Exception:
                        box.mount(
                            Input(
                                value=(
                                    "\n".join(f"{k}={v}" for k, v in self._values.items())
                                    if self._values
                                    else ""
                                ),
                                placeholder="webhook_url=https://...",
                                id="pcfg-freeform",
                            )
                        )
                else:
                    for key in self._field_keys:
                        spec = self._schema.get(key) or {}
                        desc = spec.get("description") or key
                        req = " (required)" if spec.get("required") else ""
                        default = spec.get("default", "")
                        cur = self._values.get(key, default)
                        if cur is None:
                            cur = ""
                        sensitive = any(s in key.lower() for s in self.SENSITIVE)
                        box.mount(Static(f"{desc}{req}", classes="pcfg-label"))
                        box.mount(
                            Input(
                                value=str(cur) if cur != "" else "",
                                placeholder=str(default) if default not in (None, "") else key,
                                password=sensitive,
                                id=f"pcfg-field-{key}",
                            )
                        )
            except Exception as e:
                logger.debug("PluginConfigScreen mount fields: %s", e)
        except Exception as e:
            logger.debug("PluginConfigScreen on_mount: %s", e)

    def compose(self) -> "ComposeResult":
        if not _TEXTUAL_AVAILABLE:
            return
        from textual.containers import Vertical, Horizontal
        yield Vertical(
            Static(f"Configure: {self.plugin_name}", classes="card-title"),
            Static(
                f"Per-plugin file: ~/.tokenade/plugins/{self.plugin_name}/config.json",
                classes="pcfg-hint",
            ),
            Rule(),
            Vertical(id="pcfg-fields"),
            Static("", id="pcfg-status", classes="pcfg-hint"),
            Horizontal(
                Button("Save", variant="success", compact=True, id="pcfg-save"),
                Button("Reset defaults", variant="default", compact=True, id="pcfg-reset"),
                Button("Cancel", variant="default", compact=True, id="pcfg-cancel"),
                classes="pcfg-actions",
            ),
            id="pcfg-box",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "pcfg-save":
            self.action_save()
        elif bid == "pcfg-cancel":
            self.action_cancel()
        elif bid == "pcfg-reset":
            self._reset()

    def _collect(self) -> dict:
        values: dict = {}
        if self._field_keys:
            for key in self._field_keys:
                try:
                    raw = self.query_one(f"#pcfg-field-{key}").value
                except Exception:
                    raw = ""
                spec = self._schema.get(key) or {}
                values[key] = self._coerce(raw, spec)
            return values
        # Free-form KEY=value
        try:
            w = self.query_one("#pcfg-freeform")
            text = getattr(w, "text", None) or getattr(w, "value", None) or ""
        except Exception:
            text = ""
        for line in str(text).splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if k:
                values[k] = v
        return values

    @staticmethod
    def _coerce(raw: str, spec: dict):
        t = (spec.get("type") or "string").lower()
        if raw is None or raw == "":
            if "default" in spec:
                return spec["default"]
            if t == "bool":
                return False
            return "" if t == "string" else None
        try:
            if t == "int":
                return int(raw)
            if t == "float":
                return float(raw)
            if t == "bool":
                return str(raw).lower() in ("1", "true", "yes", "on")
            if t in ("list", "dict"):
                import json as _json
                return _json.loads(raw)
        except Exception:
            return raw
        return raw

    def action_save(self) -> None:
        try:
            from tokenade.core.integration.plugin_config import PluginConfigManager
            mgr = PluginConfigManager()
            values = self._collect()
            errors = mgr.validate_config(self.plugin_name, values)
            if errors:
                msg = "; ".join(errors)[:120]
                try:
                    self.query_one("#pcfg-status").update(f"Validation: {msg}")
                except Exception:
                    pass
                self.notify(f"Validation: {msg}", severity="warning")
                # still allow save if schema empty-ish; only block hard required
                hard = [e for e in errors if "required" in e.lower()]
                if hard:
                    return
            ok = mgr.save_config(self.plugin_name, values)
            if ok:
                self.notify(f"Saved {self.plugin_name} config", timeout=3)
                self.app.pop_screen()
            else:
                self.notify("Save failed", severity="error")
        except Exception as e:
            self.notify(f"Save failed: {e}", severity="error")

    def _reset(self) -> None:
        try:
            from tokenade.core.integration.plugin_config import PluginConfigManager
            mgr = PluginConfigManager()
            defaults = mgr.get_defaults(self.plugin_name)
            mgr.save_config(self.plugin_name, defaults)
            self.notify("Reset to defaults", timeout=2)
            self.app.pop_screen()
        except Exception as e:
            self.notify(f"Reset failed: {e}", severity="error")

    def action_cancel(self):
        self.app.pop_screen()
