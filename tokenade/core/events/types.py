"""
Event types and data structures for the Tokenade event bus.

Defines all event types, the Event dataclass, and priority levels
for handler execution ordering.
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Dict, Optional


class EventType(Enum):
    """All event types in the Tokenade event system.

    Core events are emitted by the system itself.
    Plugin events are emitted by the plugin lifecycle.
    Custom events can be defined by plugins.
    """

    # Session events
    SESSION_EXPIRED = "session_expired"
    SESSION_REFRESHED = "session_refreshed"
    SESSION_VALIDATED = "session_validated"
    SESSION_EXPORTED = "session_exported"

    # Refresh events
    REFRESH_STARTED = "refresh_started"
    REFRESH_SUCCESS = "refresh_success"
    REFRESH_FAILED = "refresh_failed"

    # Proxy events
    PROXY_ROTATED = "proxy_rotated"
    PROXY_FAILED = "proxy_failed"

    # CAPTCHA events
    CAPTCHA_DETECTED = "captcha_detected"
    CAPTCHA_SOLVED = "captcha_solved"
    CAPTCHA_FAILED = "captcha_failed"

    # Export events
    EXPORT_STARTED = "export_started"
    EXPORT_COMPLETED = "export_completed"
    EXPORT_FAILED = "export_failed"

    # Health events
    HEALTH_CHECK = "health_check"
    HEALTH_DEGRADED = "health_degraded"
    HEALTH_RECOVERED = "health_recovered"

    # Scheduler events
    SCHEDULED_TASK_FIRED = "scheduled_task_fired"
    SCHEDULED_TASK_COMPLETED = "scheduled_task_completed"
    SCHEDULED_TASK_FAILED = "scheduled_task_failed"

    # Plugin events
    PLUGIN_LOADED = "plugin_loaded"
    PLUGIN_UNLOADED = "plugin_unloaded"
    PLUGIN_ERROR = "plugin_error"


class Priority(IntEnum):
    """Handler execution priority.

    Higher values execute first. Core handlers use fixed priorities.
    Plugin handlers use configurable priorities (default 0).
    """

    CRITICAL = 100
    HIGH = 75
    NORMAL = 50
    LOW = 25
    BACKGROUND = 0


@dataclass
class Event:
    """Event payload with metadata.

    All events emitted through the EventBus are wrapped in this dataclass.
    """

    event_type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "event_type": self.event_type.value,
            "data": self.data,
            "source": self.source,
            "id": self.id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """Create event from dictionary."""
        return cls(
            event_type=EventType(data["event_type"]),
            data=data.get("data", {}),
            source=data.get("source", ""),
            id=data.get("id", uuid.uuid4().hex[:12]),
            timestamp=data.get("timestamp", time.time()),
        )
