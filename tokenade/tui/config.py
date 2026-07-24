"""TUI configuration — all paths under ~/.tokenade/."""

import os
from pathlib import Path

TOKENADE_DIR = Path(os.environ.get("TOKENADE_DIR", Path.home() / ".tokenade"))
SESSIONS_DIR = Path(os.environ.get("TOKENADE_SESSIONS_DIR", TOKENADE_DIR / "sessions"))
VAULT_DIR = Path(os.environ.get("TOKENADE_VAULT_DIR", TOKENADE_DIR / "vault"))
ANALYTICS_DIR = Path(os.environ.get("TOKENADE_ANALYTICS_DIR", TOKENADE_DIR / "analytics"))
PLUGINS_DIR = Path(os.environ.get("TOKENADE_PLUGINS_DIR", TOKENADE_DIR / "plugins"))
CONFIG_FILE = TOKENADE_DIR / "config.yaml"

APP_TITLE = "Tokenade"
APP_SUBTITLE = "Session Portability Tool"
MAX_SESSIONS_DISPLAY = 100
MAX_PLUGINS_DISPLAY = 100

# Ensure dirs exist
for _d in (SESSIONS_DIR, VAULT_DIR, ANALYTICS_DIR, PLUGINS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
