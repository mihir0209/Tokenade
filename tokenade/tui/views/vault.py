"""Vault view — ~/.tokenade/vault."""

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, ScrollableContainer
    from textual.widgets import Static, Button, Rule
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
            Button("Refresh", variant="primary", compact=True, id="vault-refresh"),
            Button("Rotate Key", variant="warning", compact=True, id="vault-rotate-key"),
            Button("Backup", variant="default", compact=True, id="vault-backup"),
        )
        yield Rule()
        yield ScrollableContainer(id="vault-list")
