"""Analytics view."""

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, ScrollableContainer
    from textual.widgets import Static, Button, Rule
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
            Button("Report", variant="primary", compact=True, id="analytics-report"),
            Button("Export CSV", variant="default", compact=True, id="analytics-csv"),
            Button("Cleanup", variant="warning", compact=True, id="analytics-cleanup"),
        )
        yield Rule()
        yield ScrollableContainer(id="analytics-result")
