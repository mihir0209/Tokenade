"""
Share view — password-protected session sharing via URL shortener.
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


class ShareView(BaseView):
    """Session sharing with password-protected URLs."""

    def compose(self) -> "ComposeResult":
        if not _TEXTUAL_AVAILABLE:
            return
        yield from self.compose_title(
            "🔗 Session Sharing (URL Shortener)",
            "Create password-protected share links with expiry",
        )
        yield Horizontal(
            Input(placeholder="/path/to/session.tokenade", id="share-session-input"),
            Input(placeholder="Password", password=True, id="share-password-input"),
        )
        yield Horizontal(
            Input(placeholder="Expiry hours (24)", id="share-expiry-input"),
            Input(placeholder="Max uses (0=unlimited)", id="share-max-uses-input"),
        )
        yield Horizontal(
            Button("Create Share", variant="success", compact=True, id="share-create"),
            Button("List Shares", variant="primary", compact=True, id="share-list"),
            Button("Cleanup", variant="warning", compact=True, id="share-cleanup"),
        )
        yield Rule()
        yield Container(id="share-result")
