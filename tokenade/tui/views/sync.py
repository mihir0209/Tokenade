"""Remote sync view."""

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, ScrollableContainer
    from textual.widgets import Static, Button, Input, Rule, Select, Switch, RichLog

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
            "Hash-based local or strict SSH/SFTP repository sync",
        )
        yield Horizontal(
            Input(placeholder="Peer name", id="sync-peer-name"),
            Select(
                [("Local directory", "local"), ("SSH/SFTP", "ssh")],
                value="local",
                id="sync-transport",
            ),
            Input(placeholder="Remote/local repository path", id="sync-path-input"),
        )
        yield Horizontal(
            Input(placeholder="SSH host", id="sync-host-input"),
            Input(placeholder="SSH user", id="sync-user-input"),
            Input(placeholder="Identity file", id="sync-identity-input"),
            Switch(value=False, id="sync-allow-plaintext"),
            Static("Allow plaintext", classes="field-label"),
        )
        yield Horizontal(
            Button("Save Peer", variant="success", compact=True, id="sync-save-peer"),
            Button("Status", variant="primary", compact=True, id="sync-status"),
            Button("Preview Plan", variant="default", compact=True, id="sync-plan"),
            Button("Run Two-Way", variant="warning", compact=True, id="sync-bidir"),
        )
        yield Rule()
        yield ScrollableContainer(id="sync-result")
        yield RichLog(id="sync-log", wrap=True, markup=True, max_lines=500)
