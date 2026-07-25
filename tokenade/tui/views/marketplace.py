"""Plugin marketplace view — 3-column tile grid."""

from typing import Any, Dict, List, Optional

try:
    from textual.app import ComposeResult
    from textual.containers import Grid, Horizontal, ScrollableContainer, Vertical
    from textual.widgets import Static, Rule, Button, Input, Label
    from textual.widget import Widget
    _OK = True
except ImportError:
    _OK = False

    class Widget:
        pass

    class ComposeResult:
        pass

    class Grid:
        pass

    class Horizontal:
        pass

    class ScrollableContainer:
        pass

    class Vertical:
        pass

    class Static:
        pass

    class Rule:
        pass

    class Button:
        pass

    class Input:
        pass

    class Label:
        pass


from tokenade.tui.views.base import BaseView


class PluginCard(Widget if _OK else object):
    """Compact marketplace plugin tile (fits 3 per row)."""

    DEFAULT_CSS = """
    PluginCard {
        width: 1fr;
        height: 7;
        min-height: 7;
        max-height: 7;
        margin: 0 1 1 0;
        padding: 0 1;
        background: $surface;
        border: tall $primary-background-lighten-2;
        layout: vertical;
    }
    PluginCard:hover {
        background: $surface-lighten-1;
        border: tall $primary;
    }
    PluginCard .tile-title {
        text-style: bold;
        color: $primary;
        height: 1;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    PluginCard .tile-meta {
        color: $text-muted;
        height: 2;
        overflow: hidden;
    }
    PluginCard .tile-actions {
        height: 1;
        dock: bottom;
        align: left middle;
    }
    PluginCard .tile-actions Button {
        margin-right: 1;
        min-width: 10;
    }
    """

    def __init__(self, plugin: Dict[str, Any], installed: bool = False, **kwargs):
        if _OK:
            super().__init__(**kwargs)
        self.plugin = plugin
        self.installed = installed
        self.can_focus = True

    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        p = self.plugin
        name = p.get("name", "unknown")
        icon = p.get("icon") or "📦"
        ver = p.get("version") or "?"
        desc = (p.get("description") or "").strip()
        if len(desc) > 70:
            desc = desc[:67] + "..."
        author = p.get("author") or "?"
        ptype = p.get("type") or p.get("category") or ""
        badge = " ✓" if self.installed else ""
        yield Static(f"{icon} {name}{badge}", classes="tile-title")
        yield Static(f"v{ver} · {author}" + (f" · {ptype}" if ptype else ""), classes="tile-meta")
        yield Static(desc or "(no description)", classes="tile-meta")
        yield Horizontal(
            Button(
                "Installed" if self.installed else "Install",
                variant="default" if self.installed else "success",
                compact=True,
                id=f"install-{name}",
                disabled=self.installed,
            ),
            Button("Details", variant="primary", compact=True, id=f"details-{name}"),
            classes="tile-actions",
        )


class PluginGrid(Grid if _OK else object):
    """3-column responsive plugin tile grid."""

    DEFAULT_CSS = """
    PluginGrid {
        grid-size: 3;
        grid-gutter: 0 1;
        grid-rows: auto;
        height: auto;
        padding: 0 1;
        align: left top;
    }
    """

    def __init__(self, **kwargs):
        if _OK:
            super().__init__(**kwargs)


class MarketplaceView(BaseView):
    """Browse / search / install plugins."""

    DEFAULT_CSS = """
    MarketplaceView {
        height: 1fr;
        layout: vertical;
    }
    MarketplaceView #plugin-list {
        height: 1fr;
        overflow-y: auto;
        padding: 0;
        align: left top;
    }
    """

    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        yield from self.compose_title("🔌 Plugin Marketplace")
        yield Input(placeholder="Search plugins…", id="search-input")
        yield ScrollableContainer(PluginGrid(id="plugin-grid"), id="plugin-list")


def format_plugin_detail(plugin: Dict[str, Any]) -> List[str]:
    """Human-readable detail lines for a registry plugin."""
    p = plugin or {}
    tags = p.get("tags") or []
    if isinstance(tags, list):
        tags_s = ", ".join(str(t) for t in tags) if tags else "—"
    else:
        tags_s = str(tags) or "—"
    deps = p.get("dependencies") or []
    if isinstance(deps, list):
        deps_s = ", ".join(str(d) for d in deps) if deps else "none"
    else:
        deps_s = str(deps) or "none"

    lines = [
        f"{p.get('icon') or '📦'}  {p.get('name', '?')}  v{p.get('version', '?')}",
        "",
        p.get("description") or "(no description)",
        "",
        f"Author:      {p.get('author') or '—'}",
        f"Type:        {p.get('type') or '—'}",
        f"Category:    {p.get('category') or '—'}",
        f"Tags:        {tags_s}",
        f"Entry:       {p.get('entry_point') or '—'} | {p.get('entry_class') or '—'}",
        f"API version: {p.get('api_version') or '—'}",
        f"Min Tokenade:{p.get('min_version') or '—'}",
        f"Verified:    {'yes' if p.get('verified') else 'no'}",
        f"Downloads:   {p.get('downloads', '—')}",
        f"Registry:    {p.get('_registry') or '—'}",
        f"Dependencies:{deps_s}",
    ]
    # Any extra keys not already shown
    shown = {
        "name", "version", "description", "author", "type", "category", "tags",
        "entry_point", "entry_class", "api_version", "min_version", "max_version",
        "verified", "downloads", "icon", "dependencies", "_registry", "rating",
        "review_count",
    }
    extras = {k: v for k, v in p.items() if k not in shown and v not in (None, "", [], {})}
    if extras:
        lines.append("")
        lines.append("Other:")
        for k, v in sorted(extras.items()):
            lines.append(f"  {k}: {v}")
    return lines
