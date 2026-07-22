"""
Sessions view — browse, validate, delete sessions.
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List

try:
    from textual.app import ComposeResult
    from textual.containers import Container, Horizontal, Vertical
    from textual.widgets import Static, Rule, Button
    from textual.widget import Widget
    _TEXTUAL_AVAILABLE = True
except ImportError:
    _TEXTUAL_AVAILABLE = False

from tokenade.tui.config import SESSIONS_DIR
from tokenade.tui.views.base import BaseView


class SessionsView(BaseView):
    """Session management view with health scores and actions."""

    def compose(self) -> "ComposeResult":
        if not _TEXTUAL_AVAILABLE:
            return
        yield from self.compose_title(
            "📁 Sessions",
            f"Looking in: {SESSIONS_DIR}",
        )
        yield Container(id="sessions-list")

    def load_sessions(self) -> List[Dict[str, Any]]:
        """Load sessions from the configured sessions directory."""
        sessions = []
        sessions_dir = Path(SESSIONS_DIR)
        if not sessions_dir.exists():
            return sessions

        for f in sessions_dir.glob("*.tokenade"):
            try:
                with open(f) as fh:
                    data = json.load(fh)
                cookies = data.get("cookies", [])
                expired = 0
                now = time.time()
                for c in cookies:
                    exp = c.get("expires", 0)
                    if exp and int(exp) > 0:
                        exp_int = int(exp)
                        if exp_int > 1262304000000:
                            exp_int = exp_int // 1000
                        if exp_int < now:
                            expired += 1
                total = len(cookies)
                health = ((total - expired) / total * 100) if total > 0 else 0
                sessions.append({
                    "name": f.stem,
                    "file": str(f),
                    "site": data.get("site_name", "unknown"),
                    "auth": data.get("auth_status", "unknown"),
                    "cookies": total,
                    "expired": expired,
                    "health": health,
                })
            except Exception:
                pass
        return sessions
