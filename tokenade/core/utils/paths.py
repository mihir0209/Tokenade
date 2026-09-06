"""Cross-platform home-directory helpers.

Background: :meth:`pathlib.Path.expanduser` and :meth:`pathlib.Path.home`
ignore an explicitly exported ``HOME`` on Windows (``USERPROFILE`` is
authoritative there), while POSIX honors it. That divergence breaks test
isolation (``HOME=<tmp>`` subprocess runs) and POSIX-style shells on Windows
(Git Bash / MSYS2 export ``HOME``).

These helpers prefer an explicitly exported ``HOME`` and fall back to
``Path.home()`` otherwise, so behavior is identical on normal systems on
every platform. Use them for Tokenade's *own* data directories
(``~/.tokenade/...``) and for expanding user-supplied ``~`` paths at CLI
boundaries. Do NOT use them for real browser-profile discovery paths, which
must always resolve to the OS home.
"""

from __future__ import annotations

import os
from pathlib import Path


def tokenade_home() -> Path:
    """Home directory for Tokenade data (``$HOME`` when exported)."""
    home = os.environ.get("HOME")
    if home:
        return Path(home)
    return Path.home()


def expand_user(path: str | Path) -> Path:
    """Expand a leading ``~`` honoring an exported ``HOME`` on all platforms."""
    text = str(path)
    if text == "~" or text.startswith("~/") or text.startswith("~\\"):
        return tokenade_home() / text[2:]
    return Path(text).expanduser()
