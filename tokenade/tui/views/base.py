"""Base view helpers."""

try:
    from textual.containers import Vertical
    from textual.widgets import Static, Rule
    _OK = True
except ImportError:
    _OK = False

    class Vertical:
        pass

    class Static:
        pass

    class Rule:
        pass


class BaseView(Vertical if _OK else object):
    """Shared layout for tab panes."""

    def compose_title(self, title: str, subtitle: str = ""):
        yield Static(title, classes="card-title")
        if subtitle:
            yield Static(subtitle, classes="card-meta")
        yield Rule()
