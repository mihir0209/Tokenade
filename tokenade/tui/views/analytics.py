"""Analytics view."""

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, ScrollableContainer
    from textual.widgets import Static, Button, Input, Rule, RichLog

    _OK = True
except ImportError:
    _OK = False


from tokenade.tui.config import ANALYTICS_DIR
from tokenade.tui.views.base import BaseView


class AnalyticsView(BaseView):
    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        yield from self.compose_title(
            "📊 Analytics",
            f"Data: {ANALYTICS_DIR}",
        )
        yield Horizontal(
            Input(value="30", placeholder="Retention days", id="analytics-retention"),
            Button("Enable", variant="success", compact=True, id="analytics-enable"),
            Button("Disable", variant="warning", compact=True, id="analytics-disable"),
            Button("Status", variant="default", compact=True, id="analytics-status"),
            Button("Report", variant="primary", compact=True, id="analytics-report"),
            Button("Export CSV", variant="default", compact=True, id="analytics-csv"),
            Button("Cleanup", variant="warning", compact=True, id="analytics-cleanup"),
        )
        yield Rule()
        yield ScrollableContainer(id="analytics-result")
        yield RichLog(id="analytics-log", wrap=True, markup=True, max_lines=500)
