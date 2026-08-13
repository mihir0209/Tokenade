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
    VaultView #vault-workspace {
        height: 1fr; min-height: 8; overflow-y: auto; padding: 0 1;
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
    VaultView #vault-primary-actions {
        height: 3; padding: 0 1;
    }
    VaultView #vault-primary-actions Input { width: 1fr; margin-right: 1; }
    VaultView #vault-primary-actions Button { margin-right: 1; }
    VaultView #vault-list { height: auto; min-height: 5; }
    VaultView #vault-log {
        height: 28%; min-height: 5; max-height: 30%;
        border-top: tall $primary-background-lighten-2; background: $surface;
    }
    VaultView #vault-passphrase {
        border: tall $accent; background: $surface-lighten-1;
    }
    """

    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        yield from self.compose_title(
            "Session Vault",
            f"Encrypted local storage at {VAULT_DIR}",
        )
        yield Label(
            "Recovery passphrase",
            classes="field-label",
        )
        yield Horizontal(
            Input(
                placeholder="Enter recovery passphrase",
                password=True,
                id="vault-passphrase",
            ),
            Button(
                "Create backup",
                variant="primary",
                compact=True,
                id="vault-backup",
            ),
            Button(
                "Restore latest",
                variant="default",
                compact=True,
                id="vault-restore",
            ),
            Button("Verify", variant="default", compact=True, id="vault-verify"),
            id="vault-primary-actions",
        )
        with ScrollableContainer(id="vault-workspace"):
            with Vertical(classes="vault-section"):
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

            with Vertical(classes="vault-section"):
                yield Static("Backup And Recovery", classes="section-title")
                yield Static(
                    "Backups are created only when requested. Your passphrase encrypts the complete portable .tvbak archive.",
                    classes="section-help",
                )
                yield Static("Checking local backups...", id="vault-backup-status")
                yield Horizontal(
                    Button(
                        "Rotate key",
                        variant="default",
                        compact=True,
                        id="vault-rotate-key",
                    ),
                    Button(
                        "Migrate legacy Vault",
                        variant="warning",
                        compact=True,
                        id="vault-migrate",
                    ),
                    classes="action-row",
                )

            with Vertical(classes="vault-section"):
                yield Static("Stored Sessions", classes="section-title")
                yield Static(
                    "Retrieve writes a usable Session into your Sessions directory. Delete removes only the selected Vault entry.",
                    classes="section-help",
                )
                yield Vertical(id="vault-list")

        yield RichLog(id="vault-log", wrap=True, markup=True, max_lines=500)
