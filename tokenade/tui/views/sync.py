"""
Sync view — cross-machine session synchronization via SSH/SCP.
"""

try:
    from textual.app import ComposeResult
    from textual.containers import Container, Horizontal, Vertical
    from textual.widgets import Static, Rule, Button, Input
    from textual.widget import Widget
    _TEXTUAL_AVAILABLE = True
except ImportError:
    _TEXTUAL_AVAILABLE = False

from tokenade.tui.views.base import BaseView


class SyncView(BaseView):
    """Cross-machine session sync view."""

    def compose(self) -> "ComposeResult":
        if not _TEXTUAL_AVAILABLE:
            return
        yield from self.compose_title(
            "🔄 Session Sync (Remote)",
            "Sync sessions via SSH/SCP with connection pooling",
        )
        yield Horizontal(
            Input(placeholder="user@remote-host", id="sync-host-input"),
            Input(placeholder="~/.tokenade/sessions", id="sync-path-input"),
        )
        yield Horizontal(
            Button("Status", variant="primary", compact=True, id="sync-status"),
            Button("Push", variant="success", compact=True, id="sync-push"),
            Button("Pull", variant="warning", compact=True, id="sync-pull"),
            Button("Bidirectional", variant="default", compact=True, id="sync-bidir"),
        )
        yield Rule()
        yield Container(id="sync-result")
