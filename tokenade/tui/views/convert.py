"""Convert view — cookie/storage files → .tokenade with embedded file picker."""

from pathlib import Path
from typing import Iterable, List, Tuple

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import (
        Static,
        Button,
        Input,
        Select,
        Label,
        RichLog,
        Switch,
        DirectoryTree,
    )
    from textual.widget import Widget
    _OK = True
except ImportError:
    _OK = False

    class ComposeResult:
        pass

    class Horizontal:
        pass

    class Vertical:
        pass

    class Widget:
        pass

    class Static:
        pass

    class Button:
        pass

    class Input:
        pass

    class Select:
        pass

    class Label:
        pass

    class RichLog:
        pass

    class Switch:
        pass

    class DirectoryTree:
        pass


from tokenade.tui.config import SESSIONS_DIR
from tokenade.tui.views.base import BaseView

# Industry formats (labels for Select)
FORMAT_OPTIONS: List[Tuple[str, str]] = [
    ("auto-detect", "auto"),
    ("JSON (generic / Cookie-Editor / EditThisCookie)", "json"),
    ("Cookie-Editor / EditThisCookie", "cookie-editor"),
    ("Netscape cookie jar", "netscape"),
    ("curl cookie jar", "curl"),
    ("Playwright storageState", "playwright"),
    ("Puppeteer cookies JSON", "puppeteer"),
    ("Cypress cookies JSON", "cypress"),
    ("Selenium cookies JSON", "selenium"),
    ("Cookie request header", "header"),
    ("Set-Cookie response headers", "set-cookie"),
    ("HAR (HTTP Archive)", "har"),
    ("CSV", "csv"),
]

_PICKER_EXTS = {
    ".json",
    ".txt",
    ".cookies",
    ".cookie",
    ".jar",
    ".har",
    ".csv",
    ".header",
    ".headers",
    ".netscape",
    ".tokenade",
}


if _OK:

    class CookieDirectoryTree(DirectoryTree):
        """Directory tree that surfaces common cookie/export files."""

        def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
            out = []
            for p in paths:
                try:
                    if p.name.startswith("."):
                        continue
                    if p.is_dir():
                        out.append(p)
                    elif p.suffix.lower() in _PICKER_EXTS or p.suffix == "":
                        out.append(p)
                    else:
                        # still show other files so user can pick anything
                        out.append(p)
                except OSError:
                    continue
            return out


class ConvertView(BaseView):
    DEFAULT_CSS = """
    ConvertView {
        height: 1fr;
        layout: vertical;
        align: left top;
    }
    ConvertView #convert-body {
        height: 1fr;
        layout: horizontal;
        padding: 0 1;
    }
    ConvertView #convert-picker-pane {
        width: 40%;
        height: 100%;
        layout: vertical;
        margin-right: 1;
    }
    ConvertView #convert-form-pane {
        width: 60%;
        height: 100%;
        layout: vertical;
    }
    ConvertView #convert-tree {
        height: 1fr;
        min-height: 20%;
        background: $surface;
        border: tall $primary-background-lighten-2;
        scrollbar-size: 1 1;
    }
    ConvertView .field-label {
        color: $text-muted;
        height: 1;
        width: 100%;
        margin-top: 1;
    }
    ConvertView .field-row {
        height: 3;
        width: 100%;
        layout: horizontal;
        align: left middle;
    }
    ConvertView .field-row Input,
    ConvertView .field-row Select {
        width: 1fr;
        margin-right: 1;
    }
    ConvertView .field-row > *:last-child {
        margin-right: 0;
    }
    ConvertView #convert-format-select {
        width: 55%;
    }
    ConvertView #convert-domain-input {
        width: 45%;
    }
    ConvertView #convert-password-row {
        height: 3;
        width: 100%;
        layout: horizontal;
        align: left middle;
    }
    /* Password field: 80% of form pane width (form pane is 60% of tab) */
    ConvertView #convert-password-input {
        width: 80%;
        margin-right: 1;
    }
    ConvertView #convert-encrypt-switch {
        width: auto;
        margin-right: 1;
    }
    ConvertView .switch-row {
        height: 3;
        width: 100%;
        layout: horizontal;
        align: left middle;
    }
    ConvertView .switch-row Switch {
        margin-right: 1;
    }
    ConvertView .switch-row .sw-label {
        color: $text-muted;
        width: auto;
        margin-right: 2;
        height: 1;
    }
    ConvertView .btn-row {
        height: 3;
        width: 100%;
        layout: horizontal;
        align: left middle;
        margin-top: 1;
    }
    ConvertView .btn-row Button {
        width: 1fr;
        margin-right: 1;
        min-width: 10%;
    }
    ConvertView .btn-row Button:last-child {
        margin-right: 0;
    }
    ConvertView #convert-cli-log {
        height: 35%;
        min-height: 15%;
        background: $surface;
        border: tall $primary-background-lighten-2;
        scrollbar-size: 1 1;
        margin-top: 1;
    }
    ConvertView #convert-root-row Input {
        width: 1fr;
    }
    ConvertView #convert-root-row Button {
        width: auto;
        min-width: 10%;
        margin-left: 1;
    }
    """

    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        yield from self.compose_title(
            "Convert",
            "Cookie / storage files → .tokenade  (JSON · Netscape · Playwright · HAR · …)",
        )
        home = str(Path.home())
        default_out = str(Path(SESSIONS_DIR) / "converted.tokenade")
        start = Path.home() / "Downloads"
        if not start.is_dir():
            start = Path.home()

        with Horizontal(id="convert-body"):
            with Vertical(id="convert-picker-pane"):
                yield Label("Browse files", classes="field-label")
                with Horizontal(id="convert-root-row", classes="field-row"):
                    yield Input(value=str(start), id="convert-root-input", placeholder="Start directory")
                    yield Button("Go", compact=True, id="convert-root-go", variant="default")
                    yield Button("Home", compact=True, id="convert-root-home", variant="default")
                    yield Button("Downloads", compact=True, id="convert-root-downloads", variant="default")
                yield CookieDirectoryTree(str(start), id="convert-tree")

            with Vertical(id="convert-form-pane"):
                yield Label("Input file", classes="field-label")
                yield Input(
                    placeholder="Select from tree or paste path…",
                    id="convert-input-path",
                )

                yield Label("Format | default domain (header / set-cookie)", classes="field-label")
                with Horizontal(classes="field-row"):
                    yield Select(
                        FORMAT_OPTIONS,
                        id="convert-format-select",
                        value="auto",
                        allow_blank=False,
                    )
                    yield Input(
                        placeholder="e.g. .example.com (optional)",
                        id="convert-domain-input",
                    )

                yield Label("Output .tokenade path", classes="field-label")
                yield Input(
                    value=default_out,
                    placeholder=str(Path(SESSIONS_DIR) / "converted.tokenade"),
                    id="convert-output-input",
                )

                yield Label(
                    "Encrypt password (optional, ~70% width) | encrypt switch",
                    classes="field-label",
                )
                with Horizontal(id="convert-password-row"):
                    yield Input(
                        placeholder="Leave empty for plaintext",
                        password=True,
                        id="convert-password-input",
                    )
                    yield Switch(value=False, id="convert-encrypt-switch")
                    yield Static("encrypt", classes="sw-label")

                with Horizontal(classes="btn-row"):
                    yield Button("Convert", variant="success", compact=True, id="convert-run")
                    yield Button("Detect format", variant="primary", compact=True, id="convert-detect")
                    yield Button("Clear log", variant="default", compact=True, id="convert-clear-log")

                yield RichLog(
                    id="convert-cli-log",
                    highlight=True,
                    markup=True,
                    max_lines=400,
                    wrap=True,
                    auto_scroll=True,
                )
