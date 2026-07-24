"""Remote sync view."""

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, ScrollableContainer
    from textual.widgets import Static, Button, Input, Rule
    _OK = True
except ImportError:
    _OK = False

from tokenade.tui.views.base import BaseView


class SyncView(BaseView):
    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        yield from self.compose_title(
            "🔄 Session Sync",
            "SSH/SCP push/pull of ~/.tokenade/sessions",
        )
        yield Horizontal(
            Input(placeholder="user@host", id="sync-host-input"),
            Input(placeholder="~/.tokenade/sessions", id="sync-path-input"),
        )
        yield Horizontal(
            Button("Status", variant="primary", compact=True, id="sync-status"),
            Button("Push", variant="success", compact=True, id="sync-push"),
            Button("Pull", variant="warning", compact=True, id="sync-pull"),
            Button("Bidirectional", variant="default", compact=True, id="sync-bidir"),
        )
        yield Rule()
        yield ScrollableContainer(id="sync-result")
