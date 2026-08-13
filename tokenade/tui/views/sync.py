"""Peer Session synchronization view."""

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, ScrollableContainer, Vertical
    from textual.widgets import Button, Input, Label, RichLog, Select, Static, Switch

    _OK = True
except ImportError:
    _OK = False

from tokenade.tui.views.base import BaseView


class SyncView(BaseView):
    DEFAULT_CSS = """
    SyncView { height: 1fr; layout: vertical; }
    SyncView #sync-workspace {
        height: 1fr; min-height: 8; overflow-y: auto; padding: 0 1;
    }
    SyncView .sync-section {
        height: auto; margin: 0 0 1 0; padding: 0 1;
        border-bottom: solid $primary-background-lighten-2;
    }
    SyncView .section-title { height: 1; color: $accent; text-style: bold; }
    SyncView .section-help { height: auto; color: $text-muted; margin-bottom: 1; }
    SyncView .field-label { height: 1; color: $text-muted; }
    SyncView Input, SyncView Select { width: 100%; }
    SyncView .pair-row { height: 3; }
    SyncView .pair-row Input, SyncView .pair-row Select { width: 1fr; margin-right: 1; }
    SyncView .switch-row { height: 3; align: left middle; }
    SyncView .switch-row Static { width: 1fr; padding-left: 1; }
    SyncView .action-row { height: 3; }
    SyncView .action-row Button { margin-right: 1; }
    SyncView #sync-primary-actions {
        height: 3; padding: 0 1;
    }
    SyncView #sync-primary-actions Button { margin-right: 1; }
    SyncView #sync-result { height: auto; min-height: 5; }
    SyncView #sync-log {
        height: 28%; min-height: 5; max-height: 30%;
        border-top: tall $primary-background-lighten-2; background: $surface;
    }
    """

    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        yield from self.compose_title(
            "Session Sync",
            "Hash-based reconciliation with local directories or strict SSH/SFTP peers",
        )
        yield Horizontal(
            Button(
                "Save peer",
                variant="default",
                compact=True,
                id="sync-save-peer",
            ),
            Button(
                "Preview plan",
                variant="primary",
                compact=True,
                id="sync-plan",
            ),
            Button(
                "Status",
                variant="default",
                compact=True,
                id="sync-status",
            ),
            Button(
                "Run two-way",
                variant="warning",
                compact=True,
                id="sync-bidir",
            ),
            id="sync-primary-actions",
        )
        with ScrollableContainer(id="sync-workspace"):
            with Vertical(classes="sync-section"):
                yield Static("Peer Repository", classes="section-title")
                yield Static(
                    "Local peers need a name and repository path. Save before previewing.",
                    classes="section-help",
                )
                yield Label("Peer name and transport", classes="field-label")
                yield Horizontal(
                    Input(placeholder="e.g. laptop", id="sync-peer-name"),
                    Select(
                        [("Local directory", "local"), ("SSH/SFTP", "ssh")],
                        value="local",
                        allow_blank=False,
                        id="sync-transport",
                    ),
                    classes="pair-row",
                )
                yield Label("Peer repository path", classes="field-label")
                yield Input(
                    placeholder="/mnt/private/tokenade or .tokenade/sessions",
                    id="sync-path-input",
                )

            with Vertical(classes="sync-section"):
                yield Static("SSH Connection", classes="section-title")
                yield Static(
                    "Optional for local peers. SSH hosts must already be trusted.",
                    classes="section-help",
                )
                yield Label("Host and user", classes="field-label")
                yield Horizontal(
                    Input(placeholder="host.example.com", id="sync-host-input"),
                    Input(placeholder="SSH user", id="sync-user-input"),
                    classes="pair-row",
                )
                yield Label("Identity file", classes="field-label")
                yield Input(placeholder="~/.ssh/id_ed25519", id="sync-identity-input")
                yield Horizontal(
                    Switch(value=False, id="sync-allow-plaintext"),
                    Static(
                        "Allow plaintext Sessions on protected peer storage",
                    ),
                    classes="switch-row",
                )

            with Vertical(classes="sync-section"):
                yield Static("Plan Result", classes="section-title")
                yield Vertical(id="sync-result")

        yield RichLog(id="sync-log", wrap=True, markup=True, max_lines=500)
