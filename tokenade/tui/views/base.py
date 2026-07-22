"""
Base view classes for the Tokenade TUI.
"""

from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static, Rule

try:
    from textual.widget import Widget
    _TEXTUAL_AVAILABLE = True
except ImportError:
    _TEXTUAL_AVAILABLE = False
    class Widget:
        pass


class BaseView(Vertical if _TEXTUAL_AVAILABLE else object):
    """Base class for all views with common layout."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs) if _TEXTUAL_AVAILABLE else None

    def compose_title(self, title: str, subtitle: str = ""):
        """Yield common title elements."""
        yield Static(title, classes="card-title")
        if subtitle:
            yield Static(subtitle, classes="card-meta")
        yield Rule()

    def compose_actions(self, actions: list):
        """Yield a horizontal button bar."""
        yield Horizontal(*actions)
        yield Rule()
