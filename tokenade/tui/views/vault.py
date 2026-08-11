"""Vault view — ~/.tokenade/vault."""

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, ScrollableContainer
    from textual.widgets import Static, Button, Input, Rule, RichLog

    _OK = True
except ImportError:
    _OK = False


from tokenade.tui.config import VAULT_DIR
from tokenade.tui.views.base import BaseView


class VaultView(BaseView):
    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        yield from self.compose_title(
            "🔒 Session Vault",
            f"Directory: {VAULT_DIR}",
        )
        yield Horizontal(
            Input(placeholder="Entry name", id="vault-name"),
            Input(placeholder="Session file path", id="vault-file"),
            Button("Store", variant="success", compact=True, id="vault-store"),
        )
        yield Horizontal(
            Input(
                placeholder="Backup/recovery passphrase",
                password=True,
                id="vault-passphrase",
            ),
            Button("Refresh", variant="primary", compact=True, id="vault-refresh"),
            Button("Verify", variant="default", compact=True, id="vault-verify"),
            Button(
                "Rotate Key", variant="warning", compact=True, id="vault-rotate-key"
            ),
            Button("Backup", variant="default", compact=True, id="vault-backup"),
            Button(
                "Restore Latest", variant="warning", compact=True, id="vault-restore"
            ),
        )
        yield Rule()
        yield ScrollableContainer(id="vault-list")
        yield RichLog(id="vault-log", wrap=True, markup=True, max_lines=500)
