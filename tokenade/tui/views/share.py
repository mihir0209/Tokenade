"""Share-URL view — left create / right receive, resizable log below."""

from pathlib import Path
from typing import List, Tuple

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, ScrollableContainer, Vertical
    from textual.events import MouseDown, MouseMove, MouseUp
    from textual.widget import Widget
    from textual.widgets import Static, Button, Input, Rule, Select, Label
    _OK = True
except ImportError:
    _OK = False
    class ComposeResult: pass
    class Horizontal: pass
    class ScrollableContainer: pass
    class Vertical: pass
    class Widget: pass
    class Static: pass
    class Button: pass
    class Input: pass
    class Rule: pass
    class Select: pass
    class Label: pass
    class MouseDown: pass
    class MouseMove: pass
    class MouseUp: pass

from tokenade.tui.config import SESSIONS_DIR
from tokenade.tui.views.base import BaseView
from tokenade.tui.views.sessions import load_sessions


def session_select_options(sessions_dir: Path | None = None) -> List[Tuple[str, str]]:
    """Build Select options: (label, value=path)."""
    rows = load_sessions(sessions_dir or SESSIONS_DIR)
    opts: List[Tuple[str, str]] = []
    for s in rows:
        label = f"{s['name']}  ({s.get('site', '?')}, {s.get('cookies', 0)} ck)"
        opts.append((label, s["file"]))
    return opts


if _OK:

    class LogSplitter(Widget):
        """Drag handle between share panes and log (default log ~30%)."""

        DEFAULT_CSS = """
        LogSplitter {
            height: 1;
            width: 100%;
            background: $primary-background-lighten-1;
            color: $text-muted;
            content-align: center middle;
            text-align: center;
        }
        LogSplitter:hover {
            background: $primary;
            color: $text;
        }
        """
        can_focus = True

        def render(self) -> str:
            return "═  drag to resize log  ═"

        def on_mouse_down(self, event: MouseDown) -> None:
            event.stop()
            self.capture_mouse()
            try:
                self.app._share_log_dragging = True
            except Exception:
                pass

        def on_mouse_up(self, event: MouseUp) -> None:
            event.stop()
            self.release_mouse()
            try:
                self.app._share_log_dragging = False
            except Exception:
                pass

        def on_mouse_move(self, event: MouseMove) -> None:
            if not event.button:
                return
            try:
                view = self.app.query_one(ShareView)
            except Exception:
                return
            try:
                # y relative to ShareView
                y = event.screen_y - view.region.y
                total = max(view.size.height, 12)
                # Log height = space below splitter (1 row) inside view
                log_h = max(4, min(total - 8, total - y - 1))
                view._user_resized_log = True
                view.apply_log_height(log_h)
            except Exception:
                pass

else:

    class LogSplitter:  # type: ignore
        pass


class ShareView(BaseView):
    DEFAULT_CSS = """
    ShareView {
        height: 1fr;
        layout: vertical;
        align: left top;
    }
    ShareView #share-panes {
        height: 1fr;
        width: 100%;
        layout: horizontal;
        min-height: 8;
    }
    ShareView #share-create-pane,
    ShareView #share-receive-pane {
        width: 1fr;
        height: 1fr;
        layout: vertical;
        padding: 0 1 1 1;
        overflow-y: auto;
        overflow-x: hidden;
    }
    ShareView #share-create-pane {
        border-right: heavy $primary;
        padding-right: 2;
    }
    ShareView #share-receive-pane {
        padding-left: 2;
    }
    ShareView .pane-title {
        text-style: bold;
        color: $text;
        height: 1;
        margin: 0 0 1 0;
        background: $primary-background-darken-1;
        padding: 0 1;
    }
    ShareView .field-label {
        color: $text-muted;
        height: 1;
        margin-top: 1;
    }
    ShareView .field-row {
        height: 3;
        width: 100%;
        layout: horizontal;
        align: left middle;
    }
    ShareView .field-row Input,
    ShareView .field-row Select,
    ShareView .field-row Button {
        width: 1fr;
        margin-right: 1;
    }
    ShareView .field-row > *:last-child {
        margin-right: 0;
    }
    ShareView .btn-grid {
        height: auto;
        width: 100%;
        layout: vertical;
        margin-top: 1;
    }
    ShareView .btn-row {
        height: 3;
        width: 100%;
        layout: horizontal;
        align: left middle;
    }
    ShareView .btn-row Button {
        width: 1fr;
        margin-right: 1;
        min-width: 12;
    }
    ShareView .btn-row Button:last-child {
        margin-right: 0;
    }
    ShareView #share-receive {
        width: auto;
        min-width: 14;
        margin-top: 1;
    }
    ShareView #share-log-split {
        height: 1;
        dock: none;
    }
    ShareView #share-result {
        height: 30%;
        min-height: 4;
        max-height: 80%;
        overflow-y: auto;
        padding: 0 1;
        background: $surface;
        border-top: solid $primary-background-lighten-2;
    }
    """

    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        with Horizontal(id="share-panes"):
            with Vertical(id="share-create-pane"):
                yield Static("Session share", classes="pane-title")
                yield Label("Session file", classes="field-label")
                opts = session_select_options()
                with Horizontal(classes="field-row"):
                    if opts:
                        yield Select(
                            opts,
                            prompt="Pick a .tokenade session…",
                            id="share-session-select",
                            allow_blank=True,
                        )
                    else:
                        yield Static(
                            f"No sessions in {SESSIONS_DIR}",
                            id="share-session-select",
                            classes="card-meta",
                        )
                    yield Input(
                        placeholder="Or paste path to .tokenade",
                        id="share-session-input",
                    )
                with Horizontal(classes="field-row"):
                    yield Button(
                        "Refresh list",
                        variant="default",
                        compact=True,
                        id="share-refresh-sessions",
                    )

                yield Label("Password (min 8)", classes="field-label")
                with Horizontal(classes="field-row"):
                    yield Input(
                        placeholder="Share password…",
                        password=True,
                        id="share-password-input",
                    )
                    yield Input(
                        placeholder="Confirm password…",
                        password=True,
                        id="share-password-confirm",
                    )

                yield Label("Options", classes="field-label")
                with Horizontal(classes="field-row"):
                    yield Input(
                        placeholder="Expiry hours (default 24)",
                        id="share-expiry-input",
                    )
                    yield Input(
                        placeholder="Max uses (0 = unlimited)",
                        id="share-max-uses-input",
                    )

                with Vertical(classes="btn-grid"):
                    with Horizontal(classes="btn-row"):
                        yield Button(
                            "Create share",
                            variant="success",
                            compact=True,
                            id="share-create",
                        )
                        yield Button(
                            "Copy full URL",
                            variant="primary",
                            compact=True,
                            id="share-copy-full",
                        )
                        yield Button(
                            "Copy short id",
                            variant="default",
                            compact=True,
                            id="share-copy-id",
                        )
                    with Horizontal(classes="btn-row"):
                        yield Button(
                            "Copy receive cmd",
                            variant="default",
                            compact=True,
                            id="share-copy-cmd",
                        )
                        yield Button(
                            "List shares",
                            variant="default",
                            compact=True,
                            id="share-list",
                        )
                        yield Button(
                            "Cleanup expired",
                            variant="warning",
                            compact=True,
                            id="share-cleanup",
                        )

            with Vertical(id="share-receive-pane"):
                yield Static("Receive a share", classes="pane-title")
                yield Label("Share reference", classes="field-label")
                yield Input(
                    placeholder="short id or tokenade://share/… URL",
                    id="share-receive-input",
                )
                yield Label("Password", classes="field-label")
                yield Input(
                    placeholder="password",
                    password=True,
                    id="share-receive-password",
                )
                yield Label("Output path", classes="field-label")
                yield Input(
                    placeholder="default: original session name",
                    id="share-receive-output",
                )
                yield Button(
                    "Receive",
                    variant="success",
                    compact=True,
                    id="share-receive",
                )

        yield LogSplitter(id="share-log-split")
        yield ScrollableContainer(id="share-result")

    _log_frac: float = 0.30
    _user_resized_log: bool = False

    def on_mount(self) -> None:
        self.call_after_refresh(self._apply_default_split)

    def on_resize(self) -> None:
        if not self._user_resized_log:
            self._apply_default_split()
        else:
            # Keep user's fraction on window resize
            try:
                total = max(self.size.height, 12)
                self.apply_log_height(max(4, int(total * self._log_frac)))
            except Exception:
                pass

    def _apply_default_split(self) -> None:
        try:
            total = max(int(self.size.height or 0), 12)
            self.apply_log_height(max(4, int(total * self._log_frac)))
        except Exception:
            pass

    def apply_log_height(self, rows: int) -> None:
        rows = max(4, int(rows))
        try:
            panes = self.query_one("#share-panes")
            log = self.query_one("#share-result")
            total = max(int(self.size.height or 0), rows + 9)
            # panes take the rest minus splitter (1)
            pane_h = max(6, total - rows - 1)
            panes.styles.height = pane_h
            log.styles.height = rows
            log.styles.min_height = 4
            if total > 0:
                self._log_frac = rows / total
        except Exception:
            pass
