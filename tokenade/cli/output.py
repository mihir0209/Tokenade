"""CLI output helpers with color support."""
import sys
import os

COLOR_ENABLED = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _color(code: str, text: str) -> str:
    if not COLOR_ENABLED:
        return text
    return f"\033[{code}m{text}\033[0m"


def success(msg: str):
    print(_color("32", f"✓ {msg}"))


def error(msg: str):
    print(_color("31", f"✗ {msg}"), file=sys.stderr)


def warning(msg: str):
    print(_color("33", f"⚠ {msg}"))


def info(msg: str):
    print(_color("36", f"ℹ {msg}"))


def heading(msg: str):
    print(_color("1", f"\n{msg}"))
