"""
Settings view — configuration and registry management.
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


class SettingsView(BaseView):
    """Settings view for registry and config."""

    def compose(self) -> "ComposeResult":
        if not _TEXTUAL_AVAILABLE:
            return
        yield from self.compose_title("⚙ Settings")
        yield Container(
            Static("Plugin Registry", classes="card-title"),
            Static("", id="current-registry"),
            Rule(),
            Static("Plugin Management:", classes="card-title"),
            Horizontal(
                Button("Sync All", variant="primary", compact=True, id="sync-plugins-settings"),
                Button("Update All", variant="warning", compact=True, id="update-plugins-settings"),
            ),
            Rule(),
            Static("Add Custom Registry:"),
            Horizontal(
                Input(placeholder="https://github.com/org/plugins", id="registry-url"),
                Button("Add", variant="primary", id="add-registry"),
            ),
            Button("Reset to default", variant="default", id="reset-registry"),
            Rule(),
            Static("Installed registry sources:", classes="card-title"),
            Static("", id="custom-registries"),
            id="settings-content",
        )
