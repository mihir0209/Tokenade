"""
Session Rotator — Health-weighted session rotation for load balancing.

Selects sessions based on health scores, tracks cooldowns,
and maintains selection metrics.
"""
import json
import time
import random
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionEntry:
    """A session with its health metadata for rotation."""
    path: str
    session_id: str
    site_name: str
    health_score: float = 100.0
    cookie_count: int = 0
    last_selected: float = 0.0
    selection_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    cooldown_until: float = 0.0
    is_healthy: bool = True


@dataclass
class RotatorMetrics:
    """Metrics for rotation decisions."""
    total_selections: int = 0
    total_failures: int = 0
    average_health: float = 0.0
    sessions_rotated: int = 0


class SessionRotator:
    """Rotate between sessions using health-weighted selection.

    Strategies:
    - health-weighted: Prefer sessions with higher health scores
    - round-robin: Cycle through sessions sequentially
    - random: Random selection
    - least-recently-used: Prefer sessions not used recently
    """

    STRATEGIES = ("health-weighted", "round-robin", "random", "least-recently-used")

    def __init__(
        self,
        sessions_dir: Optional[str] = None,
        strategy: str = "health-weighted",
        cooldown_seconds: float = 300.0,
        min_health: float = 10.0,
    ):
        self.sessions_dir = Path(sessions_dir).expanduser() if sessions_dir else None
        self.strategy = strategy
        self.cooldown_seconds = cooldown_seconds
        self.min_health = min_health
        self._entries: Dict[str, SessionEntry] = {}
        self._round_robin_index = 0
        self._metrics = RotatorMetrics()
        self._state_file: Optional[Path] = None

    def load_sessions(self, session_paths: Optional[List[str]] = None) -> int:
        """Load sessions from directory or explicit paths. Returns count loaded."""
        if session_paths:
            paths = [Path(p) for p in session_paths]
        elif self.sessions_dir:
            paths = []
            for ext in ("*.tokenade", "*.session"):
                paths.extend(self.sessions_dir.glob(ext))
        else:
            return 0

        count = 0
        for path in paths:
            if path.exists() and path.suffix in (".tokenade", ".session"):
                try:
                    with open(path) as f:
                        data = json.load(f)
                    session_id = path.stem
                    site_name = data.get("metadata", {}).get("site_name", session_id)
                    cookies = data.get("cookies", [])
                    entry = SessionEntry(
                        path=str(path),
                        session_id=session_id,
                        site_name=site_name,
                        cookie_count=len(cookies),
                    )
                    self._entries[session_id] = entry
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to load session {path}: {e}")
        return count

    def add_session(self, path: str, health_score: float = 100.0) -> Optional[SessionEntry]:
        """Add a single session file."""
        p = Path(path)
        if not p.exists():
            return None
        try:
            with open(p) as f:
                data = json.load(f)
            session_id = p.stem
            site_name = data.get("metadata", {}).get("site_name", session_id)
            cookies = data.get("cookies", [])
            entry = SessionEntry(
                path=str(p),
                session_id=session_id,
                site_name=site_name,
                health_score=health_score,
                cookie_count=len(cookies),
            )
            self._entries[session_id] = entry
            return entry
        except Exception as e:
            logger.warning(f"Failed to add session {p}: {e}")
            return None

    def remove_session(self, session_id: str):
        """Remove a session by ID."""
        self._entries.pop(session_id, None)

    def next(self) -> Optional[str]:
        """Select next session based on strategy. Returns path or None."""
        available = [
            e for e in self._entries.values()
            if e.is_healthy and e.cooldown_until <= time.time()
        ]
        if not available:
            return None

        if self.strategy == "round-robin":
            entry = available[self._round_robin_index % len(available)]
            self._round_robin_index += 1
        elif self.strategy == "random":
            entry = random.choice(available)
        elif self.strategy == "least-recently-used":
            entry = min(available, key=lambda e: e.last_selected)
        else:
            # health-weighted
            total = sum(e.health_score for e in available)
            if total == 0:
                entry = random.choice(available)
            else:
                r = random.uniform(0, total)
                cumulative = 0
                entry = available[-1]
                for e in available:
                    cumulative += e.health_score
                    if cumulative >= r:
                        entry = e
                        break

        entry.last_selected = time.time()
        entry.selection_count += 1
        self._metrics.total_selections += 1
        return entry.path

    def set_cooldown(self, session_id: str, seconds: float):
        """Set cooldown for a session."""
        if session_id in self._entries:
            self._entries[session_id].cooldown_until = time.time() + seconds

    def record_failure(self, session_id: str):
        """Record a failure and apply cooldown."""
        if session_id in self._entries:
            entry = self._entries[session_id]
            entry.failure_count += 1
            self._metrics.total_failures += 1
            backoff = min(300, 30 * (2 ** min(entry.failure_count - 1, 5)))
            entry.cooldown_until = time.time() + backoff

    def record_success(self, session_id: str):
        """Record a success."""
        if session_id in self._entries:
            self._entries[session_id].success_count += 1

    def update_health(self, session_id: str, score: float):
        """Update health score for a session."""
        if session_id in self._entries:
            entry = self._entries[session_id]
            entry.health_score = score
            entry.is_healthy = score >= self.min_health

    def _average_health(self) -> float:
        """Calculate average health of all sessions."""
        if not self._entries:
            return 0.0
        return sum(e.health_score for e in self._entries.values()) / len(self._entries)

    def get_status(self) -> dict:
        """Get current rotator status."""
        available = [
            e for e in self._entries.values()
            if e.is_healthy and e.cooldown_until <= time.time()
        ]
        return {
            "strategy": self.strategy,
            "total_sessions": len(self._entries),
            "available_sessions": len(available),
            "metrics": {
                "total_selections": self._metrics.total_selections,
                "total_failures": self._metrics.total_failures,
                "average_health": self._average_health(),
            },
            "sessions": [
                {
                    "id": e.session_id,
                    "health": e.health_score,
                    "selections": e.selection_count,
                    "healthy": e.is_healthy,
                }
                for e in self._entries.values()
            ],
        }

    def save_state(self, path: str):
        """Save rotator state to file."""
        state = {
            "round_robin_index": self._round_robin_index,
            "metrics": {
                "total_selections": self._metrics.total_selections,
                "total_failures": self._metrics.total_failures,
            },
            "sessions": {
                sid: {
                    "selection_count": e.selection_count,
                    "success_count": e.success_count,
                    "failure_count": e.failure_count,
                    "health_score": e.health_score,
                }
                for sid, e in self._entries.items()
            },
        }
        with open(path, "w") as f:
            json.dump(state, f)

    def load_state(self, path: str):
        """Load rotator state from file."""
        p = Path(path)
        if not p.exists():
            return
        try:
            with open(p) as f:
                state = json.load(f)
            self._round_robin_index = state.get("round_robin_index", 0)
            metrics = state.get("metrics", {})
            self._metrics.total_selections = metrics.get("total_selections", 0)
            self._metrics.total_failures = metrics.get("total_failures", 0)
            for sid, data in state.get("sessions", {}).items():
                if sid in self._entries:
                    e = self._entries[sid]
                    e.selection_count = data.get("selection_count", 0)
                    e.success_count = data.get("success_count", 0)
                    e.failure_count = data.get("failure_count", 0)
                    e.health_score = data.get("health_score", 100.0)
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")
