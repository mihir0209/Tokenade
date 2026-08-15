"""Vault view for protected local Session storage."""

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, ScrollableContainer, Vertical
    from textual.widgets import Button, Input, Label, RichLog, Select, Static

    _OK = True
except ImportError:
    _OK = False

from tokenade.tui.config import VAULT_DIR
from tokenade.tui.views.base import BaseView


class VaultView(BaseView):
    DEFAULT_CSS = """
    VaultView { height: 1fr; layout: vertical; }
    VaultView #vault-panes {
        height: 1fr; min-height: 8; width: 100%; layout: horizontal;
    }
    VaultView #vault-store-pane,
    VaultView #vault-sessions-pane {
        width: 1fr; height: 1fr; padding: 0 1 1 1;
        overflow-y: auto; overflow-x: hidden;
    }
    VaultView #vault-store-pane {
        border-right: heavy $primary;
        padding-right: 2;
    }
    VaultView #vault-sessions-pane {
        padding-left: 2;
    }
    VaultView .vault-section {
        height: auto; margin: 0 0 1 0; padding: 0 1;
        border-bottom: solid $primary-background-lighten-2;
    }
    VaultView .section-title { height: 1; color: $accent; text-style: bold; }
    VaultView .section-help { height: auto; color: $text-muted; margin-bottom: 1; }
    VaultView .field-label { height: 1; color: $text-muted; }
    VaultView .field-row { height: 3; }
    VaultView .field-row Input { width: 1fr; margin-right: 1; }
    VaultView .field-row Select { width: 1fr; margin-right: 1; }
    VaultView .action-row { height: 3; }
    VaultView .action-row Button { margin-right: 1; }
    VaultView #vault-list { height: auto; min-height: 5; width: 100%; }
    VaultView #vault-log {
        height: 28%; min-height: 5; max-height: 30%;
        border-top: tall $primary-background-lighten-2; background: $surface;
    }
    """

    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        yield from self.compose_title(
            "Session Vault",
            f"Encrypted local storage at {VAULT_DIR}",
        )
        with Horizontal(id="vault-panes"):
            with ScrollableContainer(id="vault-store-pane"):
                yield Static("Store a Session", classes="section-title")
                yield Static(
                    "Choose a display name and an existing .tokenade Session file.",
                    classes="section-help",
                )
                yield Label("Entry name", classes="field-label")
                yield Input(placeholder="e.g. github-work", id="vault-name")
                yield Label("Session file", classes="field-label")
                yield Horizontal(
                    Select(
                        [],
                        prompt="Select a Session from your Sessions directory",
                        allow_blank=True,
                        id="vault-session-select",
                    ),
                    Button(
                        "Browse...",
                        variant="default",
                        compact=True,
                        id="vault-browse",
                    ),
                    classes="field-row",
                )
                yield Input(
                    placeholder="Selected path or manually entered ~/.tokenade/sessions/example.tokenade",
                    id="vault-file",
                )
                yield Horizontal(
                    Button(
                        "Store Session",
                        variant="primary",
                        compact=True,
                        id="vault-store",
                    ),
                    Button(
                        "Refresh",
                        variant="default",
                        compact=True,
                        id="vault-refresh",
                    ),
                    classes="action-row",
                )

            with ScrollableContainer(id="vault-sessions-pane"):
                yield Static("Stored Sessions", classes="section-title")
                yield Static(
                    "Retrieve writes a usable Session into your Sessions directory. Delete removes only the selected Vault entry.",
                    classes="section-help",
                )
                yield Vertical(id="vault-list")

        yield RichLog(id="vault-log", wrap=True, markup=True, max_lines=500)
