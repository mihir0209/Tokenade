"""
Vault view — encrypted session storage management.
"""

from pathlib import Path
from typing import Any, Dict, List

try:
    from textual.app import ComposeResult
    from textual.containers import Container, Horizontal, Vertical
    from textual.widgets import Static, Rule, Button
    from textual.widget import Widget
    _TEXTUAL_AVAILABLE = True
except ImportError:
    _TEXTUAL_AVAILABLE = False

from tokenade.tui.views.base import BaseView


class VaultView(BaseView):
    """Encrypted session vault management view."""

    def compose(self) -> "ComposeResult":
        if not _TEXTUAL_AVAILABLE:
            return
        yield from self.compose_title(
            "🔒 Session Vault",
            "Encrypted storage with AES-256-GCM key rotation",
        )
        yield Horizontal(
            Button("Refresh", variant="primary", compact=True, id="vault-refresh"),
            Button("Rotate Key", variant="warning", compact=True, id="vault-rotate-key"),
            Button("Backup", variant="default", compact=True, id="vault-backup"),
        )
        yield Rule()
        yield Container(id="vault-list")

    def load_vault_sessions(self) -> Dict[str, Any]:
        """Load vault sessions."""
        try:
            from tokenade.core.vault.vault import SessionVault
            vault = SessionVault()
            return vault.list_sessions()
        except Exception:
            return {}
