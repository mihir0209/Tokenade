"""Export view — interactive session export via CLI."""

from pathlib import Path
from typing import List, Tuple

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import Static, Button, Input, Select, Label, RichLog, Switch
    from textual.widget import Widget
    _OK = True
except ImportError:
    _OK = False

    class ComposeResult:
        pass

    class Horizontal:
        pass

    class Vertical:
        pass

    class Widget:
        pass

    class Static:
        pass

    class Button:
        pass

    class Input:
        pass

    class Select:
        pass

    class Label:
        pass

    class RichLog:
        pass

    class Switch:
        pass


from tokenade.tui.config import SESSIONS_DIR
from tokenade.tui.views.base import BaseView

# Sentinel for optional Select blanks (passed through as empty to CLI)
NONE_VALUE = "__none__"


def export_browser_options(*, refresh: bool = False) -> List[Tuple[str, str]]:
    """Dynamic browsers with profiles from BrowserProfileDiscovery."""
    try:
        from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery

        discovery = BrowserProfileDiscovery()
        if refresh:
            discovery.refresh_cache()
        opts = discovery.list_export_browsers(use_cache=True)
        return opts or [("firefox", "firefox")]
    except Exception:
        return [("firefox", "firefox")]


def export_profile_options(browser: str, *, refresh: bool = False) -> List[Tuple[str, str]]:
    """Real profile names for export (no clean-profile placeholder)."""
    try:
        from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery

        discovery = BrowserProfileDiscovery()
        if refresh:
            discovery.refresh_cache()
        raw = discovery.list_profiles_for_browser(browser or "firefox", use_cache=True)
        clean = BrowserProfileDiscovery.CLEAN_PROFILE_VALUE
        opts = [(label, val) for label, val in raw if val != clean]
        return opts or [("default", "default")]
    except Exception:
        return [("default", "default")]


def export_handler_options() -> List[Tuple[str, str]]:
    """Site handler plugins from PluginExporter (same source as --list-handlers)."""
    opts: List[Tuple[str, str]] = [("none (auto | default)", NONE_VALUE)]
    try:
        from tokenade.core.importer.plugin_export import PluginExporter

        seen = set()
        for h in PluginExporter().list_handlers():
            name = (h.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            ver = h.get("version") or "?"
            desc = (h.get("description") or "").strip()
            label = f"{name} v{ver}"
            if desc:
                short = desc if len(desc) <= 48 else desc[:45] + "..."
                label = f"{name} v{ver} — {short}"
            opts.append((label, name))
    except Exception:
        pass
    return opts


def export_proxy_plugin_options() -> List[Tuple[str, str]]:
    """Installed proxy provider plugins for --proxy-plugin metadata."""
    opts: List[Tuple[str, str]] = [("none", NONE_VALUE)]
    try:
        from tokenade.core.integration.plugin_loader import PluginLoader

        loader = PluginLoader()
        try:
            loader.load_all()
        except Exception:
            pass
        proxies = loader.list_proxy_plugins() or {}
        for name in sorted(proxies.keys()):
            opts.append((name, name))
    except Exception:
        pass
    return opts


class ExportView(BaseView):
    DEFAULT_CSS = """
    ExportView {
        height: 1fr;
        layout: vertical;
        align: left top;
    }
    ExportView #export-form {
        height: auto;
        max-height: 70%;
        padding: 0 1 1 1;
        overflow-y: auto;
    }
    ExportView .field-label {
        color: $text-muted;
        height: 1;
        margin-top: 1;
    }
    ExportView .field-row {
        height: 3;
        width: 100%;
        layout: horizontal;
        align: left middle;
    }
    ExportView .field-row Input,
    ExportView .field-row Select {
        width: 1fr;
        margin-right: 1;
    }
    ExportView .field-row > *:last-child {
        margin-right: 0;
    }
    ExportView .field-row #export-browser-select { width: 1fr; min-width: 16; }
    ExportView .field-row #export-profile-select { width: 2fr; min-width: 28; }
    ExportView .field-row #export-plugin-select { width: 2fr; min-width: 28; }
    ExportView .field-row #export-proxy-select { width: 1fr; min-width: 16; }
    ExportView .switch-row {
        height: 3;
        width: 100%;
        layout: horizontal;
        align: left middle;
    }
    ExportView .switch-row Switch {
        margin-right: 1;
    }
    ExportView .switch-row .sw-label {
        color: $text-muted;
        width: auto;
        margin-right: 2;
        height: 1;
    }
    ExportView .btn-row {
        height: 3;
        width: 100%;
        layout: horizontal;
        align: left middle;
        margin-top: 1;
    }
    ExportView .btn-row Button {
        width: 1fr;
        margin-right: 1;
        min-width: 12;
    }
    ExportView .btn-row Button:last-child {
        margin-right: 0;
    }
    ExportView #export-cli-log {
        height: 1fr;
        min-height: 8;
        background: $surface;
        border: tall $primary-background-lighten-2;
        scrollbar-size: 1 1;
        margin: 0 1 1 1;
    }
    """

    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        yield from self.compose_title(
            "Export",
            f"Extract browser sessions → {SESSIONS_DIR}",
        )
        browser_opts = export_browser_options()
        default_browser = next(
            (v for _, v in browser_opts if v == "firefox"),
            browser_opts[0][1] if browser_opts else "firefox",
        )
        prof_opts = export_profile_options(default_browser)
        default_prof = prof_opts[0][1] if prof_opts else "default"
        for label, val in prof_opts:
            if "· default" in label or label.endswith(" default"):
                default_prof = val
                break
        default_out = str(Path(SESSIONS_DIR) / "export.tokenade")
        handler_opts = export_handler_options()
        proxy_opts = export_proxy_plugin_options()

        with Vertical(id="export-form"):
            yield Label("Browser | profile", classes="field-label")
            with Horizontal(classes="field-row"):
                yield Select(
                    browser_opts,
                    id="export-browser-select",
                    value=default_browser,
                    allow_blank=False,
                )
                yield Select(
                    prof_opts,
                    id="export-profile-select",
                    value=default_prof,
                    allow_blank=False,
                )

            yield Label("Domains (comma-separated) | output path", classes="field-label")
            with Horizontal(classes="field-row"):
                yield Input(
                    placeholder="e.g. google.com,accounts.google.com (empty = all)",
                    id="export-domains-input",
                )
                yield Input(
                    value=default_out,
                    placeholder="Output .tokenade path",
                    id="export-output-input",
                )

            yield Label(
                "Site handler | proxy plugin (optional)",
                classes="field-label",
            )
            with Horizontal(classes="field-row"):
                yield Select(
                    handler_opts,
                    id="export-plugin-select",
                    value=NONE_VALUE,
                    allow_blank=False,
                )
                yield Select(
                    proxy_opts,
                    id="export-proxy-select",
                    value=NONE_VALUE,
                    allow_blank=False,
                )

            yield Label(
                "CDP port | encrypt password (--encrypt-password)",
                classes="field-label",
            )
            with Horizontal(classes="field-row"):
                yield Input(
                    placeholder="CDP port (running browser)",
                    id="export-cdp-input",
                )
                yield Input(
                    placeholder="Optional encrypt password",
                    password=True,
                    id="export-password-input",
                )

            with Horizontal(classes="switch-row"):
                yield Switch(value=True, id="export-full-switch")
                yield Static("full (cookies+storage)", classes="sw-label")
                yield Switch(value=False, id="export-fingerprint-switch")
                yield Static("fingerprint", classes="sw-label")
                yield Switch(value=False, id="export-no-plugin-switch")
                yield Static("no-plugin", classes="sw-label")

            with Horizontal(classes="btn-row"):
                yield Button(
                    "Export",
                    variant="success",
                    compact=True,
                    id="export-run",
                )
                yield Button(
                    "List profiles",
                    variant="primary",
                    compact=True,
                    id="export-list-profiles",
                )
                yield Button(
                    "List handlers",
                    variant="default",
                    compact=True,
                    id="export-list-handlers",
                )
                yield Button(
                    "Refresh discovery",
                    variant="default",
                    compact=True,
                    id="export-refresh",
                )

        yield RichLog(
            id="export-cli-log",
            highlight=True,
            markup=True,
            max_lines=300,
            wrap=True,
            auto_scroll=True,
        )
