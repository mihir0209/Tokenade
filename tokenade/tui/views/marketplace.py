"""
Plugin Marketplace view — browse, search, install plugins.
"""

from pathlib import Path
from typing import Any, Dict, List

try:
    from textual.app import ComposeResult
    from textual.containers import Container, Horizontal, Vertical
    from textual.widgets import Static, Rule, Button, Input
    from textual.widget import Widget
    from textual.reactive import reactive
    from textual import on
    _TEXTUAL_AVAILABLE = True
except ImportError:
    _TEXTUAL_AVAILABLE = False

from tokenade.tui.views.base import BaseView


class PluginCard(Widget if _TEXTUAL_AVAILABLE else object):
    """A card widget displaying a single plugin."""

    DEFAULT_CSS = """
    PluginCard {
        height: auto;
        min-height: 3;
        max-height: 5;
        margin: 0 0;
        padding: 0 1;
        background: $surface;
        border-bottom: tall $primary-background-lighten-2;
    }
    PluginCard:hover {
        background: $surface-lighten-1;
    }
    PluginCard:focus {
        background: $surface-lighten-1;
        border-bottom: tall $accent;
    }
    """

    def __init__(self, plugin: Dict[str, Any], installed: bool = False,
                 update_available: bool = False, **kwargs):
        if _TEXTUAL_AVAILABLE:
            super().__init__(**kwargs)
        self.plugin = plugin
        self.installed = installed
        self.update_available = update_available
        self.can_focus = True

    def compose(self) -> "ComposeResult":
        if not _TEXTUAL_AVAILABLE:
            return
        p = self.plugin
        icon = p.get("icon", "📦")
        name = p.get("name", "unknown")
        version = p.get("version", "?")
        desc = p.get("description", "No description")
        author = p.get("author", "Unknown")
        verified = " ✓" if p.get("verified", False) else " (unverified)"

        badges = ""
        if self.installed:
            badges += " [installed]"
        if self.update_available:
            badges += " [update]"

        yield Static(
            f"{icon} {name} v{version}{verified}  by {author}{badges}",
            classes="card-title",
        )
        yield Static(desc[:80], classes="card-desc", id=f"desc-{name}")
        yield Horizontal(
            Button(
                "Update" if self.update_available else
                ("Installed" if self.installed else "Install"),
                variant="warning" if self.update_available else
                ("default" if self.installed else "success"),
                compact=True,
                id=f"install-{name}",
                disabled=self.installed and not self.update_available,
            ),
            Button("Details", variant="default", compact=True,
                   id=f"details-{name}"),
            classes="card-actions",
        )


class MarketplaceView(BaseView):
    """Plugin marketplace browse view with search and categories."""

    def compose(self) -> "ComposeResult":
        if not _TEXTUAL_AVAILABLE:
            return
        yield from self.compose_title("🔌  Plugin Marketplace")
        yield Input(placeholder="Search plugins...", id="search-input")
        yield Container(id="plugin-list")
