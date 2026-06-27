"""
CLI Output Formatter — Colored output, JSON mode, progress indicators.
"""
import sys
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Backward-compatible module-level flag
COLOR_ENABLED = sys.stdout.isatty()

# ANSI color codes
_COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
}


class OutputFormatter:
    """Format CLI output with colors, JSON mode, and progress."""

    def __init__(self, use_color: Optional[bool] = None, json_mode: bool = False):
        if use_color is None:
            use_color = sys.stdout.isatty() and not json_mode
        self.use_color = use_color
        self.json_mode = json_mode
        self._pending_json: List[Dict] = []

    def _c(self, color: str, text: str) -> str:
        """Wrap text in color codes if color is enabled."""
        if not self.use_color:
            return text
        code = _COLORS.get(color, "")
        reset = _COLORS["reset"]
        return f"{code}{text}{reset}"

    def success(self, message: str):
        """Print a success message."""
        if self.json_mode:
            self._pending_json.append({"status": "success", "message": message})
        else:
            print(f"  {self._c('green', '✓')} {message}")

    def error(self, message: str):
        """Print an error message."""
        if self.json_mode:
            self._pending_json.append({"status": "error", "message": message})
        else:
            print(f"  {self._c('red', '✗')} {message}")

    def warning(self, message: str):
        """Print a warning message."""
        if self.json_mode:
            self._pending_json.append({"status": "warning", "message": message})
        else:
            print(f"  {self._c('yellow', '⚠')} {message}")

    def info(self, message: str):
        """Print an info message."""
        if self.json_mode:
            self._pending_json.append({"status": "info", "message": message})
        else:
            print(f"  {self._c('blue', 'ℹ')} {message}")

    def header(self, title: str, width: int = 70):
        """Print a section header."""
        if self.json_mode:
            self._pending_json.append({"type": "header", "title": title})
        else:
            print(f"\n{'=' * width}")
            print(self._c("bold", title))
            print(f"{'=' * width}")

    def table(self, headers: List[str], rows: List[List[str]], widths: Optional[List[int]] = None):
        """Print a formatted table."""
        if self.json_mode:
            self._pending_json.append({
                "type": "table",
                "headers": headers,
                "rows": rows,
            })
            return

        if not widths:
            widths = [max(len(h), max((len(r[i]) for r in rows), default=0))
                      for i, h in enumerate(headers)]

        header_line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
        print(f"\n  {self._c('bold', header_line)}")
        print(f"  {'  '.join('-' * w for w in widths)}")

        for row in rows:
            line = "  ".join(str(c).ljust(w) for c, w in zip(row, widths))
            print(f"  {line}")

    def progress(self, current: int, total: int, label: str = ""):
        """Print a progress indicator."""
        if self.json_mode:
            return
        pct = (current / total * 100) if total > 0 else 0
        bar_width = 20
        filled = int(pct / 100 * bar_width)
        bar = "█" * filled + "." * (bar_width - filled)
        label_str = f" {label}" if label else ""
        print(f"\r  [{bar}] {pct:.0f}%{label_str}", end="", flush=True)
        if current >= total:
            print()

    def flush_json(self) -> Optional[str]:
        """Flush pending JSON output. Returns JSON string or None."""
        if not self.json_mode or not self._pending_json:
            return None
        output = json.dumps(self._pending_json, indent=2)
        self._pending_json.clear()
        return output

    def print_json(self, data: Any):
        """Print data as JSON."""
        print(json.dumps(data, indent=2, default=str))


def create_formatter(verbose: bool = False, json_mode: bool = False) -> OutputFormatter:
    """Create an OutputFormatter with standard settings."""
    return OutputFormatter(json_mode=json_mode)


# ---------------------------------------------------------------------------
# Backward-compatible module-level functions
# ---------------------------------------------------------------------------

def _color(code: str, text: str) -> str:
    """Wrap text in ANSI color codes if color is enabled."""
    if not COLOR_ENABLED:
        return text
    return f"\033[{code}m{text}\033[0m"


def success(message: str):
    """Print a success message to stdout."""
    check = "\u2713"
    print(f"  {_color('32', check)} {message}")


def error(message: str):
    """Print an error message to stderr."""
    cross = "\u2717"
    print(f"  {_color('31', cross)} {message}", file=sys.stderr)


def warning(message: str):
    """Print a warning message to stdout."""
    warn = "\u26a0"
    print(f"  {_color('33', warn)} {message}")


def info(message: str):
    """Print an info message to stdout."""
    icon = "\u2139"
    print(f"  {_color('34', icon)} {message}")


def heading(title: str, width: int = 70):
    """Print a section heading."""
    print(f"\n{'=' * width}")
    print(_color("1", title))
    print(f"{'=' * width}")
