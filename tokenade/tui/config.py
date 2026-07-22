"""
TUI configuration.

Defines paths, defaults, and settings for the Tokenade TUI.
"""

import os
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────
TOKENADE_DIR = Path(os.environ.get("TOKENADE_DIR", Path.home() / ".tokenade"))
SESSIONS_DIR = Path(os.environ.get("TOKENADE_SESSIONS_DIR", "/tmp/real-sessions"))
VAULT_DIR = TOKENADE_DIR / "vault"
ANALYTICS_DIR = TOKENADE_DIR / "analytics"
PLUGINS_DIR = TOKENADE_DIR / "plugins"
CONFIG_FILE = TOKENADE_DIR / "config.yaml"

# ── TUI Settings ─────────────────────────────────────────────
APP_TITLE = "Tokenade"
APP_SUBTITLE = "Session Portability Tool"
REFRESH_INTERVAL = 10  # seconds for auto-refresh
MAX_SESSIONS_DISPLAY = 50
MAX_PLUGINS_DISPLAY = 100

# ── Feature Flags ────────────────────────────────────────────
ENABLE_MARKETPLACE = True
ENABLE_VAULT = True
ENABLE_SYNC = True
ENABLE_SHARE = True
ENABLE_ANALYTICS = True
