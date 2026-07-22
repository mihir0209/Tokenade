"""
Installed Plugins view — manage installed plugins.
"""

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


class InstalledView(BaseView):
    """Installed plugins management view."""

    def compose(self) -> "ComposeResult":
        if not _TEXTUAL_AVAILABLE:
            return
        yield from self.compose_title("📦  Installed Plugins")
        yield Horizontal(
            Button("Sync All", variant="primary", compact=True, id="sync-plugins"),
            Button("Update All", variant="warning", compact=True, id="update-plugins"),
        )
        yield Container(id="installed-list")
