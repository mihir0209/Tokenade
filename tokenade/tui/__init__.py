"""
Tokenade TUI — Interactive terminal interface.

Provides a rich terminal UI for browsing the plugin marketplace,
managing installed plugins, viewing sessions, vault, sync, sharing,
and analytics.

Usage:
    tokenade tui                    # Launch full TUI

Requires: pip install textual
"""

from tokenade.tui.config import (
    TOKENADE_DIR, SESSIONS_DIR, VAULT_DIR, ANALYTICS_DIR,
    APP_TITLE, APP_SUBTITLE,
)
from tokenade.tui.app import run_tui, TokenadeTUI


def _check_textual():
    """Check if textual is available."""
    try:
        import textual  # noqa: F401
        return True
    except ImportError:
        return False


__all__ = [
    "run_tui",
    "TokenadeTUI",
    "_check_textual",
    "TOKENADE_DIR",
    "SESSIONS_DIR",
    "VAULT_DIR",
    "ANALYTICS_DIR",
]
