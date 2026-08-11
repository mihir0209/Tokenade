"""
Session Analytics — Track usage events, generate reports.

Records export, load, refresh, health_check, and proxy events.
Provides usage reports and session lifetime metrics.
"""

import json
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class SessionEvent:
    """A recorded session event."""

    timestamp: float
    session_id: str
    event_type: (
        str  # export, load, refresh, health_check, proxy_start, proxy_stop, error
    )
    metadata: Dict = field(default_factory=dict)


class SessionAnalytics:
    """Track and report on session usage patterns."""

    EVENT_TYPES = (
        "export",
        "load",
        "refresh",
        "health_check",
        "proxy_start",
        "proxy_stop",
        "error",
    )

    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = Path(storage_dir or "~/.tokenade/analytics").expanduser()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._events_file = self.storage_dir / "events.jsonl"
        self._sessions_file = self.storage_dir / "sessions.json"

    def record_event(
        self,
        session_id: str,
        event_type: str,
        metadata: Optional[Dict] = None,
    ):
        """Deprecated identifying writer; use tokenade.core.analytics.LocalAnalytics."""
        raise RuntimeError(
            "SessionAnalytics is disabled because its legacy schema stores identifiers and arbitrary metadata"
        )
        event = SessionEvent(
            timestamp=time.time(),
            session_id=session_id,
            event_type=event_type,
            metadata=metadata or {},
        )
        self._append_event(event)

    def get_events(
        self,
        session_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
        since: Optional[float] = None,
    ) -> List[Dict]:
        """Query recorded events with optional filters."""
        events = self._load_events()

        if session_id:
            events = [e for e in events if e["session_id"] == session_id]
        if event_type:
            events = [e for e in events if e["event_type"] == event_type]
        if since:
            events = [e for e in events if e["timestamp"] >= since]

        return events[-limit:]

    def get_usage_report(self, days: int = 30) -> Dict:
        """Generate a usage report for the last N days."""
        cutoff = time.time() - (days * 86400)
        events = [e for e in self._load_events() if e["timestamp"] >= cutoff]

        if not events:
            return {
                "period_days": days,
                "total_events": 0,
                "total_sessions": 0,
                "events_by_type": {},
                "top_sessions": [],
                "daily_activity": {},
                "avg_session_lifetime_hours": 0.0,
            }

        sessions = set(e["session_id"] for e in events)
        events_by_type = Counter(e["event_type"] for e in events)
        top_sessions = Counter(e["session_id"] for e in events).most_common(10)

        # Daily activity
        daily_activity = {}
        for e in events:
            day = time.strftime("%Y-%m-%d", time.localtime(e["timestamp"]))
            daily_activity[day] = daily_activity.get(day, 0) + 1

        # Session lifetimes
        lifetimes = self._calculate_lifetimes(events)

        return {
            "period_days": days,
            "total_events": len(events),
            "total_sessions": len(sessions),
            "events_by_type": dict(events_by_type),
            "top_sessions": [
                {"session_id": sid, "event_count": count} for sid, count in top_sessions
            ],
            "daily_activity": daily_activity,
            "avg_session_lifetime_hours": round(
                sum(lifetimes.values()) / len(lifetimes) / 3600, 1
            )
            if lifetimes
            else 0.0,
        }

    def get_session_analytics(self, session_id: str) -> Dict:
        """Get analytics for a specific session."""
        events = self.get_events(session_id=session_id, limit=10000)
        if not events:
            return {"session_id": session_id, "total_events": 0}

        events_by_type = Counter(e["event_type"] for e in events)
        first_event = events[0]["timestamp"]
        last_event = events[-1]["timestamp"]

        return {
            "session_id": session_id,
            "total_events": len(events),
            "first_seen": first_event,
            "last_seen": last_event,
            "events_by_type": dict(events_by_type),
            "lifespan_hours": round((last_event - first_event) / 3600, 1),
        }

    def cleanup(self, max_age_days: int = 90):
        raise RuntimeError(
            "SessionAnalytics is disabled; use LocalAnalytics cleanup/delete commands"
        )

    def _append_event(self, event: SessionEvent):
        raise RuntimeError("Legacy identifying analytics persistence is disabled")

    def _load_events(self) -> List[Dict]:
        """Load all events from the events file."""
        if not self._events_file.exists():
            return []
        events = []
        try:
            with open(self._events_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        events.append(json.loads(line))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load analytics events: {e}")
        return events

    def _save_events(self, events: List[Dict]):
        raise RuntimeError("Legacy identifying analytics persistence is disabled")

    def _calculate_lifetimes(self, events: List[Dict]) -> Dict[str, float]:
        """Calculate session lifetimes from first to last event."""
        sessions: Dict[str, List[float]] = {}
        for e in events:
            sid = e["session_id"]
            sessions.setdefault(sid, []).append(e["timestamp"])

        lifetimes = {}
        for sid, timestamps in sessions.items():
            if len(timestamps) >= 2:
                lifetimes[sid] = max(timestamps) - min(timestamps)

        return lifetimes
