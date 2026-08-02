"""Settings view — TokenadeConfig controls with clear sections."""

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, ScrollableContainer, Vertical
    from textual.widgets import Static, Button, Input, Rule, Select, Label, Switch
    _OK = True
except ImportError:
    _OK = False

    class ComposeResult:
        pass

    class Horizontal:
        pass

    class ScrollableContainer:
        pass

    class Vertical:
        pass

    class Static:
        pass

    class Button:
        pass

    class Input:
        pass

    class Rule:
        pass

    class Select:
        pass

    class Label:
        pass

    class Switch:
        pass


from tokenade.tui.config import TOKENADE_DIR, SESSIONS_DIR, VAULT_DIR, ANALYTICS_DIR, PLUGINS_DIR
from tokenade.tui.views.base import BaseView


def _browser_options() -> list:
    try:
        from tokenade.tui.views.sessions import launch_browser_options

        opts = launch_browser_options()
        out = []
        for label, value in opts:
            if value == "cloak":
                out.append(("cloak (recommended)", "cloak"))
            else:
                out.append((label, value))
        return out or [("cloak (recommended)", "cloak")]
    except Exception:
        return [("cloak (recommended)", "cloak")]


STEALTH_OPTIONS = [
    ("maximum — JS + args + CloakBrowser", "maximum"),
    ("advanced — JS + launch args", "advanced"),
    ("basic — JS patches only", "basic"),
]


class SettingsView(BaseView):
    DEFAULT_CSS = """
    SettingsView {
        height: 1fr;
        layout: vertical;
        align: left top;
    }
    SettingsView #settings-body {
        height: 1fr;
        overflow-y: auto;
        padding: 0 1 1 1;
        align: left top;
    }
    SettingsView .settings-section {
        height: auto;
        margin: 0 0 1 0;
        padding: 1 1;
        background: $surface;
        border: tall $primary-background-lighten-2;
    }
    SettingsView .section-title {
        color: $accent;
        text-style: bold;
        height: 1;
        margin-bottom: 0;
    }
    SettingsView .section-help {
        color: $text-muted;
        height: auto;
        margin: 0 0 1 0;
    }
    SettingsView .field-label {
        color: $text-muted;
        height: 1;
        margin-top: 1;
    }
    SettingsView .field-hint {
        color: $text-muted;
        height: auto;
        margin: 0 0 0 0;
    }
    SettingsView .field-row {
        height: 3;
        align: left middle;
        margin-top: 0;
    }
    SettingsView .field-row Input,
    SettingsView .field-row Select {
        width: 1fr;
        margin-right: 1;
    }
    SettingsView Select {
        width: 100%;
        margin-bottom: 0;
    }
    SettingsView Input {
        width: 100%;
    }
    SettingsView .switch-row {
        height: 3;
        align: left middle;
        margin-top: 0;
    }
    SettingsView .switch-row Label {
        width: 1fr;
        color: $text;
    }
    SettingsView .path-grid {
        height: auto;
        layout: vertical;
    }
    SettingsView .path-line {
        color: $text-muted;
        height: 1;
    }
    SettingsView .path-key {
        color: $secondary;
    }
    SettingsView .status-ok {
        color: $success;
        height: auto;
        margin-top: 1;
    }
    SettingsView .status-line {
        color: $text-muted;
        height: auto;
        margin-top: 1;
    }
    SettingsView .toolbar {
        height: 3;
        padding: 1 0 0 0;
        dock: bottom;
        background: $surface;
    }
    SettingsView .toolbar Button {
        margin-right: 1;
    }
    SettingsView #settings-summary {
        height: auto;
        margin: 0 0 1 0;
        padding: 1 1;
        background: $boost;
        border: tall $accent;
        color: $text;
    }
    """

    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        yield from self.compose_title(
            "⚙ Settings",
            "Saved to ~/.tokenade/config.json · used by TUI export / launch / share defaults",
        )
        yield Static(
            "Loading configuration…",
            id="settings-summary",
        )
        yield ScrollableContainer(
            Vertical(
                Static("Directories", classes="section-title"),
                Static(
                    "Where Tokenade keeps jars, vault ciphertext, analytics, and plugins on this machine.",
                    classes="section-help",
                ),
                Vertical(
                    Static(f"home       {TOKENADE_DIR}", id="settings-tokenade-dir", classes="path-line"),
                    Static(f"sessions   {SESSIONS_DIR}", id="settings-sessions-dir", classes="path-line"),
                    Static(f"vault      {VAULT_DIR}", id="settings-vault-dir", classes="path-line"),
                    Static(f"analytics  {ANALYTICS_DIR}", id="settings-analytics-dir", classes="path-line"),
                    Static(f"plugins    {PLUGINS_DIR}", id="settings-plugins-dir", classes="path-line"),
                    classes="path-grid",
                ),
                classes="settings-section",
            ),
            Vertical(
                Static("Browsers & stealth", classes="section-title"),
                Static(
                    "Export browser = donor profile SQLite read. Automation browser = load/launch target "
                    "(cloak recommended). Stealth level only applies when CloakBrowser/automation runs.",
                    classes="section-help",
                ),
                Label("Default export browser", classes="field-label"),
                Select(
                    _browser_options(),
                    id="settings-default-browser",
                    allow_blank=True,
                    prompt="(auto-detect from installed profiles)",
                ),
                Static("Used when Export tab leaves browser blank.", classes="field-hint"),
                Label("Automation / load browser", classes="field-label"),
                Select(
                    _browser_options(),
                    id="settings-automation-browser",
                    allow_blank=False,
                    value="cloak",
                ),
                Static("CloakBrowser is the default stealth Chromium backend.", classes="field-hint"),
                Label("Stealth level", classes="field-label"),
                Select(
                    STEALTH_OPTIONS,
                    id="settings-stealth-level",
                    allow_blank=False,
                    value="maximum",
                ),
                Label("Default profile name", classes="field-label"),
                Input(placeholder="e.g. default  (optional)", id="settings-default-profile"),
                Label("Default session output directory", classes="field-label"),
                Input(placeholder=str(SESSIONS_DIR), id="settings-output-dir"),
                Horizontal(
                    Label("Show browser window when loading (visible)"),
                    Switch(id="settings-visible", value=False),
                    classes="switch-row",
                ),
                Horizontal(
                    Label("Auto-validate jars after export"),
                    Switch(id="settings-auto-validate", value=True),
                    classes="switch-row",
                ),
                Horizontal(
                    Label("Encrypt new sessions by default"),
                    Switch(id="settings-encrypt", value=False),
                    classes="switch-row",
                ),
                classes="settings-section",
            ),
            Vertical(
                Static("Local session proxy", classes="section-title"),
                Static(
                    "Defaults for CDP / reverse proxy (CLI tokenade proxy and SDK SessionProxy). "
                    "Bind 127.0.0.1 unless you intentionally expose the port.",
                    classes="section-help",
                ),
                Label("Proxy host", classes="field-label"),
                Input(placeholder="127.0.0.1", id="settings-proxy-host"),
                Label("Proxy port", classes="field-label"),
                Input(placeholder="9222", id="settings-proxy-port"),
                classes="settings-section",
            ),
            Vertical(
                Static("Remote share (share-url)", classes="section-title"),
                Static(
                    "Password-protected ciphertext links. Password is never stored remotely. "
                    "Public default project is optional convenience; use your own Supabase for private ops. "
                    "CLI: tokenade share-url status | --no-remote",
                    classes="section-help",
                ),
                Horizontal(
                    Label("Use public Tokenade remote (when no private URL/key)"),
                    Switch(id="settings-supabase-use-default", value=True),
                    classes="switch-row",
                ),
                Label("Private Supabase URL (optional)", classes="field-label"),
                Input(placeholder="https://xxxx.supabase.co", id="settings-supabase-url"),
                Label("Private anon / publishable key", classes="field-label"),
                Input(placeholder="sb_publishable_… or eyJ…", password=True, id="settings-supabase-key"),
                Static("", id="settings-supabase-status", classes="status-line"),
                classes="settings-section",
            ),
            Vertical(
                Static("Plugin marketplace registry", classes="section-title"),
                Static(
                    "GitHub (or HTTP) source for tokenade plugin sync / marketplace. "
                    "Reset restores the official default.",
                    classes="section-help",
                ),
                Static("", id="current-registry", classes="path-line"),
                Horizontal(
                    Input(
                        placeholder="https://github.com/org/tokenade-plugins",
                        id="registry-url",
                    ),
                    Button("Add", variant="primary", compact=True, id="add-registry"),
                    Button("Reset", variant="default", compact=True, id="reset-registry"),
                    classes="field-row",
                ),
                classes="settings-section",
            ),
            Static("", id="settings-status", classes="status-ok"),
            id="settings-body",
        )
        yield Horizontal(
            Button("Save settings", variant="success", compact=True, id="settings-save"),
            Button("Reload from disk", variant="default", compact=True, id="settings-reload"),
            Button("Refresh all data", variant="primary", compact=True, id="refresh-all"),
            classes="toolbar",
        )
