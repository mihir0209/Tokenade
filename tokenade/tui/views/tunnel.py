"""Tunnel status tab (read-only v1: paired remotes, no daemon control)."""

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, ScrollableContainer, Vertical
    from textual.widgets import Button, Static

    _OK = True
except ImportError:
    _OK = False

from tokenade.tui.views.base import BaseView


def format_status_rows(rows) -> str:
    """Render collect_tunnel_status() rows as plain text for the view/CLI."""
    if not rows:
        return ("No paired remotes.\n"
                "Pair one first: tokenade tunnel pair --bundle-file bundle.json")
    lines = []
    for row in rows:
        reachable = "reachable" if row.get("relay_reachable") else "UNREACHABLE"
        lines.append(
            f"• {row.get('remote_ref')} [{row.get('transport')}] "
            f"relay={row.get('relay_url')} ({reachable}) "
            f"token={row.get('token_state')}")
    return "\n".join(lines)


class TunnelView(BaseView):
    DEFAULT_CSS = """
    TunnelView { height: 1fr; layout: vertical; }
    TunnelView #tunnel-workspace {
        height: 1fr; min-height: 8; overflow-y: auto; padding: 0 1;
    }
    TunnelView .tunnel-section {
        height: auto; margin: 0 0 1 0; padding: 0 1;
        border-bottom: solid $primary-background-lighten-2;
    }
    TunnelView .section-title { height: 1; color: $accent; text-style: bold; }
    TunnelView .section-help { height: auto; color: $text-muted; margin-bottom: 1; }
    TunnelView .action-row { height: 3; }
    TunnelView .action-row Button { margin-right: 1; }
    TunnelView #tunnel-status { height: auto; min-height: 5; }
    """

    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        yield from self.compose_title(
            "Origin-Egress Tunnel",
            "Paired remotes for load/launch --tunnel auto (serve/share/pair stay on the CLI)",
        )
        yield Horizontal(
            Button(
                "Refresh status",
                variant="primary",
                compact=True,
                id="tunnel-refresh",
            ),
            classes="action-row",
        )
        with ScrollableContainer(id="tunnel-workspace"):
            with Vertical(classes="tunnel-section"):
                yield Static("Paired Remotes", classes="section-title")
                yield Static(
                    "Tokens live in the OS keyring, never in jars. "
                    "Unreachable relay = circuit cannot open (fail-closed).",
                    classes="section-help",
                )
                yield Static("Not checked yet — press Refresh status.",
                             id="tunnel-status")

    def render_status(self, rows) -> None:
        """Update the status widget (called by the app layer)."""
        try:
            self.query_one("#tunnel-status", Static).update(format_status_rows(rows))
        except Exception:
            pass
