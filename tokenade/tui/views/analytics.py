"""
Analytics view — session usage analytics and reports.
"""

try:
    from textual.app import ComposeResult
    from textual.containers import Container, Horizontal, Vertical
    from textual.widgets import Static, Rule, Button
    from textual.widget import Widget
    _TEXTUAL_AVAILABLE = True
except ImportError:
    _TEXTUAL_AVAILABLE = False

from tokenade.tui.views.base import BaseView


class AnalyticsView(BaseView):
    """Session usage analytics view."""

    def compose(self) -> "ComposeResult":
        if not _TEXTUAL_AVAILABLE:
            return
        yield from self.compose_title(
            "📊 Session Analytics",
            "Usage patterns, health trends, and insights",
        )
        yield Horizontal(
            Button("Report", variant="primary", compact=True, id="analytics-report"),
            Button("Export CSV", variant="default", compact=True, id="analytics-csv"),
            Button("Cleanup", variant="warning", compact=True, id="analytics-cleanup"),
        )
        yield Rule()
        yield Container(id="analytics-result")
