"""Installed plugins view — compact top-aligned list."""

from typing import Any, Dict

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, ScrollableContainer, Vertical
    from textual.widgets import Static, Button
    from textual.widget import Widget
    _OK = True
except ImportError:
    _OK = False
    class Widget: pass
    class ComposeResult: pass
    class Horizontal: pass
    class ScrollableContainer: pass
    class Vertical: pass
    class Static: pass
    class Button: pass

from tokenade.tui.views.base import BaseView


class InstalledRow(Widget if _OK else object):
    """One installed plugin row — fixed height, top-packed."""

    DEFAULT_CSS = """
    InstalledRow {
        height: 3;
        min-height: 3;
        max-height: 3;
        margin: 0 0 1 0;
        padding: 0 1;
        background: $surface;
        border: tall $primary-background-lighten-2;
        layout: horizontal;
    }
    InstalledRow:hover { background: $surface-lighten-1; }
    InstalledRow .inst-info {
        width: 1fr;
        height: 100%;
        content-align: left middle;
    }
    InstalledRow .inst-actions {
        width: auto;
        height: 100%;
        align: right middle;
    }
    InstalledRow .inst-actions Button {
        margin-left: 1;
        min-width: 10;
    }
    """

    def __init__(self, plugin: Dict[str, Any], **kwargs):
        if _OK:
            super().__init__(**kwargs)
        self.plugin = plugin

    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        p = self.plugin
        name = p.get("name", "?")
        version = p.get("version", "?")
        state = p.get("state", "unknown")
        enabled = "on" if p.get("enabled") else "off"
        err = p.get("error")
        info = f"{name}  v{version}  [{state}]  {enabled}"
        if err:
            info += f"  ·  {str(err)[:40]}"
        yield Static(info, classes="inst-info")
        yield Horizontal(
            Button("Reload", variant="default", compact=True, id=f"reload-{name}"),
            Button("Config", variant="default", compact=True, id=f"configure-{name}"),
            Button("Remove", variant="error", compact=True, id=f"uninstall-{name}"),
            classes="inst-actions",
        )


class InstalledView(BaseView):
    DEFAULT_CSS = """
    InstalledView {
        height: 1fr;
        layout: vertical;
        align: left top;
    }
    InstalledView #installed-list {
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
        align: left top;
        layout: vertical;
    }
    InstalledView .toolbar {
        height: 3;
        padding: 0 1;
    }
    InstalledView .toolbar Button {
        margin-right: 1;
    }
    """

    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        yield from self.compose_title("📦 Installed Plugins")
        yield Horizontal(
            Button("Sync All", variant="primary", compact=True, id="sync-plugins"),
            Button("Refresh", variant="default", compact=True, id="refresh-installed"),
            classes="toolbar",
        )
        yield ScrollableContainer(id="installed-list")
