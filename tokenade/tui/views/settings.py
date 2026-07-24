"""Settings view — real TokenadeConfig controls."""

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, ScrollableContainer, Vertical
    from textual.widgets import Static, Button, Input, Rule, Select, Label, Switch
    _OK = True
except ImportError:
    _OK = False
    class ComposeResult: pass
    class Horizontal: pass
    class ScrollableContainer: pass
    class Vertical: pass
    class Static: pass
    class Button: pass
    class Input: pass
    class Rule: pass
    class Select: pass
    class Label: pass
    class Switch: pass

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
    ("maximum", "maximum"),
    ("advanced", "advanced"),
    ("basic", "basic"),
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
        padding: 0 1;
        align: left top;
    }
    SettingsView .field-label {
        color: $text-muted;
        height: 1;
        margin-top: 1;
    }
    SettingsView .field-row {
        height: 3;
        align: left middle;
    }
    SettingsView .field-row Input, SettingsView .field-row Select {
        width: 1fr;
        margin-right: 1;
    }
    SettingsView .switch-row {
        height: 3;
        align: left middle;
    }
    SettingsView .switch-row Label {
        width: 1fr;
    }
    SettingsView .path-line {
        color: $text-muted;
        height: 1;
    }
    SettingsView .toolbar {
        height: 3;
        padding: 1 0;
    }
    SettingsView .toolbar Button {
        margin-right: 1;
    }
    """

    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        yield from self.compose_title("⚙ Settings", "Persists to ~/.tokenade/config.json")
        yield ScrollableContainer(
            Static("Paths (read-only)", classes="card-title"),
            Static(f"home:      {TOKENADE_DIR}", id="settings-tokenade-dir", classes="path-line"),
            Static(f"sessions:  {SESSIONS_DIR}", id="settings-sessions-dir", classes="path-line"),
            Static(f"vault:     {VAULT_DIR}", id="settings-vault-dir", classes="path-line"),
            Static(f"analytics: {ANALYTICS_DIR}", id="settings-analytics-dir", classes="path-line"),
            Static(f"plugins:   {PLUGINS_DIR}", id="settings-plugins-dir", classes="path-line"),
            Rule(),
            Static("Automation", classes="card-title"),
            Label("Default export browser", classes="field-label"),
            Select(
                _browser_options(),
                id="settings-default-browser",
                allow_blank=True,
                prompt="(auto-detect)",
            ),
            Label("Automation browser", classes="field-label"),
            Select(
                _browser_options(),
                id="settings-automation-browser",
                allow_blank=False,
                value="cloak",
            ),
            Label("Stealth level", classes="field-label"),
            Select(
                STEALTH_OPTIONS,
                id="settings-stealth-level",
                allow_blank=False,
                value="maximum",
            ),
            Label("Default profile name", classes="field-label"),
            Input(placeholder="e.g. default", id="settings-default-profile"),
            Label("Output directory", classes="field-label"),
            Input(placeholder=str(SESSIONS_DIR), id="settings-output-dir"),
            Horizontal(
                Label("Show browser window (visible)"),
                Switch(id="settings-visible", value=False),
                classes="switch-row",
            ),
            Horizontal(
                Label("Auto-validate after export"),
                Switch(id="settings-auto-validate", value=True),
                classes="switch-row",
            ),
            Horizontal(
                Label("Encrypt sessions by default"),
                Switch(id="settings-encrypt", value=False),
                classes="switch-row",
            ),
            Rule(),
            Static("Local proxy", classes="card-title"),
            Label("Proxy host / port", classes="field-label"),
            Horizontal(
                Input(placeholder="127.0.0.1", id="settings-proxy-host"),
                Input(placeholder="9223", id="settings-proxy-port"),
                classes="field-row",
            ),
            Rule(),
            Static("Remote share (Supabase)", classes="card-title"),
            Static(
                "Default: public Tokenade project (ciphertext only; password never stored). "
                "Override with your own project for full privacy. "
                "CLI: share-url status | --supabase-url/--supabase-key | --no-remote",
                classes="path-line",
            ),
            Horizontal(
                Label("Use public default remote"),
                Switch(id="settings-supabase-use-default", value=True),
                classes="switch-row",
            ),
            Label("Private Supabase URL (optional override)", classes="field-label"),
            Input(placeholder="https://xxxx.supabase.co", id="settings-supabase-url"),
            Label("Private anon / publishable key", classes="field-label"),
            Input(placeholder="sb_publishable_… or eyJ…", password=True, id="settings-supabase-key"),
            Static("", id="settings-supabase-status", classes="path-line"),
            Rule(),
            Static("Plugin registry", classes="card-title"),
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
            Rule(),
            Horizontal(
                Button("Save settings", variant="success", compact=True, id="settings-save"),
                Button("Reload from disk", variant="default", compact=True, id="settings-reload"),
                Button("Refresh all data", variant="primary", compact=True, id="refresh-all"),
                classes="toolbar",
            ),
            Static("", id="settings-status", classes="path-line"),
            id="settings-body",
        )
