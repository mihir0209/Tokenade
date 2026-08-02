"""Gateway control tab."""

from pathlib import Path
from typing import List, Tuple

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, ScrollableContainer, Vertical
    from textual.widgets import Button, Input, Label, RichLog, Select, Static
    _OK = True
except ImportError:
    _OK = False

    class ComposeResult:
        pass

    class Horizontal:
        pass

    class ScrollableContainer:
        pass

    class Vertical:
        pass

    class Button:
        pass

    class Input:
        pass

    class Label:
        pass

    class RichLog:
        pass

    class Select:
        BLANK = object()

    class Static:
        pass

from tokenade.tui.config import REQUESTS_DIR
from tokenade.tui.views.base import BaseView


ROUTING_STRATEGIES: List[Tuple[str, str]] = [
    ("round-robin", "round-robin"),
    ("random", "random"),
    ("health-weighted", "health-weighted"),
    ("sticky", "sticky"),
]

WINDOW_POLICIES: List[Tuple[str, str]] = [
    ("Reuse active window", "reuse-active-window"),
    ("New tab", "new-tab"),
]

ROUTE_SCOPES: List[Tuple[str, str]] = [
    ("Prepare Context", "activate-context"),
    ("Select Only", "future-only"),
    ("Open Target", "open-target"),
]


def gateway_request_options(root: Path | None = None) -> List[Tuple[str, str]]:
    """Return Gateway request JSON files from ~/.tokenade/requests by default."""
    base = Path(root) if root is not None else REQUESTS_DIR
    seen = set()
    out: List[Tuple[str, str]] = []
    if not base.exists() or not base.is_dir():
        return out
    for path in sorted(base.glob("*.json")):
        resolved = str(path.resolve())
        if resolved in seen or not path.is_file():
            continue
        seen.add(resolved)
        out.append((path.name, resolved))
    return out


class GatewayView(BaseView):
    DEFAULT_CSS = """
    GatewayView {
        height: 1fr;
        layout: vertical;
        align: left top;
    }
    GatewayView .gateway-body {
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
    }
    GatewayView .gateway-row {
        height: 3;
        align: left middle;
    }
    GatewayView .gateway-row Button, GatewayView .gateway-row Select, GatewayView .gateway-row Input {
        margin-right: 1;
    }
    GatewayView .field-label {
        color: $text-muted;
        height: 1;
    }
    GatewayView #gateway-request-select { width: 52; min-width: 32; }
    GatewayView #gateway-request-input { width: 64; min-width: 40; }
    GatewayView #gateway-host-input { width: 20; }
    GatewayView #gateway-port-input { width: 10; }
    GatewayView #gateway-url-input { width: 44; min-width: 28; }
    GatewayView #gateway-session-select { width: 42; min-width: 28; }
    GatewayView #gateway-strategy-select { width: 20; min-width: 14; }
    GatewayView #gateway-window-policy-select { width: 24; min-width: 18; }
    GatewayView #gateway-route-scope-select { width: 22; min-width: 18; }
    GatewayView #gateway-status-label {
        text-style: bold;
        color: $success;
        height: 1;
    }
    GatewayView #gateway-cli-log {
        height: 18;
        min-height: 10;
        background: $surface;
        border: tall $primary-background-lighten-2;
        scrollbar-size: 1 1;
        margin: 0 1;
    }
    """

    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        yield from self.compose_title("Gateway")
        with ScrollableContainer(classes="gateway-body"):
            yield Static("Gateway stopped", id="gateway-status-label")
            opts = gateway_request_options()
            request_options = opts or [("No gateway*.json files found", "")]
            yield Horizontal(
                Select(request_options, id="gateway-request-select", value=Select.NULL, allow_blank=True),
                Input(placeholder="selected request path", id="gateway-request-input"),
                Button("Use selected", variant="default", compact=True, id="gateway-use-selected"),
                Button("Browse...", variant="primary", compact=True, id="gateway-browse-request"),
                Button("Refresh", variant="default", compact=True, id="gateway-refresh-requests"),
                classes="gateway-row",
            )
            yield Static("No request loaded", id="gateway-request-summary", classes="field-label")
            yield Horizontal(
                Input(placeholder="host from request", id="gateway-host-input"),
                Input(placeholder="port from request", id="gateway-port-input"),
                Button("Launch", variant="success", compact=True, id="gateway-launch"),
                Button("Stop", variant="error", compact=True, id="gateway-stop"),
                Button("Status", variant="primary", compact=True, id="gateway-status"),
                Button("Sessions", variant="default", compact=True, id="gateway-sessions"),
                classes="gateway-row",
            )
            yield Horizontal(
                Input(placeholder="URL from request", id="gateway-url-input"),
                Select(WINDOW_POLICIES, id="gateway-window-policy-select", value="reuse-active-window", allow_blank=False),
                Select(ROUTE_SCOPES, id="gateway-route-scope-select", value="activate-context", allow_blank=False),
                Select(ROUTING_STRATEGIES, id="gateway-strategy-select", value="round-robin", allow_blank=False),
                Select([("No sessions loaded", "")], id="gateway-session-select", value="", allow_blank=False),
                classes="gateway-row",
            )
            yield Horizontal(
                Button("Route next", variant="warning", compact=True, id="gateway-route-next"),
                Button("Select", variant="default", compact=True, id="gateway-route-select"),
                Button("Open", variant="success", compact=True, id="gateway-open-tab"),
                Button("Next + open", variant="success", compact=True, id="gateway-next-tab"),
                Button("Select + open", variant="success", compact=True, id="gateway-select-tab"),
                Button("Lease", variant="primary", compact=True, id="gateway-lease"),
                Button("Release", variant="default", compact=True, id="gateway-release"),
                Button("Cleanup", variant="error", compact=True, id="gateway-drain"),
                classes="gateway-row",
            )
        yield RichLog(
            id="gateway-cli-log",
            highlight=True,
            markup=True,
            max_lines=400,
            wrap=True,
            auto_scroll=True,
        )
