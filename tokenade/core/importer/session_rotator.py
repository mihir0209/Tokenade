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

        loaded = 0
        for path in paths:
            entry = self._load_entry(path)
            if entry:
                self._entries[entry.session_id] = entry
                loaded += 1

        logger.info(f"Loaded {loaded} sessions for rotation")
        return loaded

    def add_session(self, path: str, health_score: float = 100.0) -> Optional[SessionEntry]:
        """Add a single session to the rotation pool."""
        entry = self._load_entry(Path(path))
        if entry:
            entry.health_score = health_score
            self._entries[entry.session_id] = entry
            return entry
        return None

    def remove_session(self, session_id: str):
        """Remove a session from the rotation pool."""
        self._entries.pop(session_id, None)

    def update_health(self, session_id: str, health_score: float):
        """Update a session's health score."""
        if session_id in self._entries:
            self._entries[session_id].health_score = health_score
            self._entries[session_id].is_healthy = health_score >= self.min_health

    def set_cooldown(self, session_id: str, seconds: Optional[float] = None):
        """Put a session on cooldown."""
        if session_id in self._entries:
            cooldown = seconds if seconds is not None else self.cooldown_seconds
            self._entries[session_id].cooldown_until = time.time() + cooldown
            logger.debug(f"Session {session_id} on cooldown for {cooldown}s")

    def next(self) -> Optional[str]:
        """Select the next session. Returns path or None if no sessions available."""
        available = self._get_available()
        if not available:
            logger.warning("No available sessions for rotation")
            return None

        if self.strategy == "health-weighted":
            selected = self._select_health_weighted(available)
        elif self.strategy == "round-robin":
            selected = self._select_round_robin(available)
        elif self.strategy == "random":
            selected = random.choice(available)
        elif self.strategy == "least-recently-used":
            selected = self._select_lru(available)
        else:
            selected = available[0]

        # Update metrics
        selected.last_selected = time.time()
        selected.selection_count += 1
        self._metrics.total_selections += 1
        self._metrics.sessions_rotated = len(self._entries)

        logger.debug(
            f"Selected session {selected.session_id} "
            f"(health={selected.health_score}, strategy={self.strategy})"
        )
        return selected.path

    def record_success(self, session_id: str):
        """Record a successful use of a session."""
        if session_id in self._entries:
            self._entries[session_id].success_count += 1

    def record_failure(self, session_id: str):
        """Record a failed use of a session and apply cooldown."""
        if session_id in self._entries:
            self._entries[session_id].failure_count += 1
            self._metrics.total_failures += 1
            self.set_cooldown(session_id)

    def get_status(self) -> Dict:
        """Get current rotation status."""
        available = self._get_available()
        all_entries = list(self._entries.values())

        return {
            "strategy": self.strategy,
            "total_sessions": len(all_entries),
            "available_sessions": len(available),
            "cooldown_sessions": len(all_entries) - len(available),
            "metrics": {
                "total_selections": self._metrics.total_selections,
                "total_failures": self._metrics.total_failures,
                "average_health": self._average_health(),
            },
            "sessions": [
                {
                    "id": e.session_id,
                    "path": e.path,
                    "site": e.site_name,
                    "health": e.health_score,
                    "selections": e.selection_count,
                    "successes": e.success_count,
                    "failures": e.failure_count,
                    "on_cooldown": time.time() < e.cooldown_until,
                    "cooldown_remaining": max(0, e.cooldown_until - time.time()),
                }
                for e in all_entries
            ],
        }

    def save_state(self, state_file: str):
        """Save rotation state to file."""
        state = {
            "strategy": self.strategy,
            "round_robin_index": self._round_robin_index,
            "sessions": {
                sid: {
                    "path": e.path,
                    "selection_count": e.selection_count,
                    "success_count": e.success_count,
                    "failure_count": e.failure_count,
                }
                for sid, e in self._entries.items()
            },
        }
        Path(state_file).write_text(json.dumps(state, indent=2))

    def load_state(self, state_file: str):
        """Load rotation state from file."""
        path = Path(state_file)
        if not path.exists():
            return
        try:
            state = json.loads(path.read_text())
            self._round_robin_index = state.get("round_robin_index", 0)
            for sid, data in state.get("sessions", {}).items():
                if sid in self._entries:
                    self._entries[sid].selection_count = data.get("selection_count", 0)
                    self._entries[sid].success_count = data.get("success_count", 0)
                    self._entries[sid].failure_count = data.get("failure_count", 0)
        except Exception as e:
            logger.warning(f"Failed to load rotation state: {e}")

    def _get_available(self) -> List[SessionEntry]:
        """Get sessions not on cooldown and healthy enough."""
        now = time.time()
        return [
            e for e in self._entries.values()
            if e.is_healthy and now >= e.cooldown_until
        ]

    def _select_health_weighted(self, available: List[SessionEntry]) -> SessionEntry:
        """Select session weighted by health score."""
        if not available:
            return list(self._entries.values())[0]

        weights = [max(e.health_score, 0.1) for e in available]
        return random.choices(available, weights=weights, k=1)[0]

    def _select_round_robin(self, available: List[SessionEntry]) -> SessionEntry:
        """Select session using round-robin."""
        if not available:
            return list(self._entries.values())[0]
        idx = self._round_robin_index % len(available)
        self._round_robin_index += 1
        return available[idx]

    def _select_lru(self, available: List[SessionEntry]) -> SessionEntry:
        """Select least recently used session."""
        if not available:
            return list(self._entries.values())[0]
        return min(available, key=lambda e: e.last_selected)

    def _average_health(self) -> float:
        """Calculate average health across all sessions."""
        if not self._entries:
            return 0.0
        total = sum(e.health_score for e in self._entries.values())
        return round(total / len(self._entries), 1)

    def _load_entry(self, path: Path) -> Optional[SessionEntry]:
        """Load a session file into a SessionEntry."""
        if not path.exists():
            return None
        try:
            with open(path) as f:
                data = json.load(f)
            cookies = data.get("cookies", [])
            site_name = data.get("metadata", {}).get("site_name", path.stem)
            return SessionEntry(
                path=str(path),
                session_id=path.stem,
                site_name=site_name,
                cookie_count=len(cookies),
                is_healthy=True,
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load session {path}: {e}")
            return None
