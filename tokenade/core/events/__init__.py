"""
Tokenade Event Bus — Core infrastructure for event-driven plugin system.

This module provides the event bus, scheduler, and related types
for the Tokenade plugin ecosystem.

The event bus is core infrastructure — it works without plugins.
Plugins can register handlers to extend behavior.

Usage:
    from tokenade.core.events import EventBus, EventType

    bus = EventBus()
    bus.on(EventType.SESSION_EXPIRED, lambda e: print(e.data))
    bus.emit(EventType.SESSION_EXPIRED, {"session_id": "abc"})
"""

from tokenade.core.events.types import Event, EventType, Priority
from tokenade.core.events.handlers import (
    EventHandler,
    FunctionHandler,
    AsyncHandler,
)
from tokenade.core.events.bus import EventBus
from tokenade.core.events.triggers import (
    Trigger,
    CronTrigger,
    IntervalTrigger,
    HealthTrigger,
    ExpiryTrigger,
)
from tokenade.core.events.dispatchers import (
    EventDispatcher,
    SyncDispatcher,
    AsyncDispatcher,
)
from tokenade.core.events.scheduler import Scheduler, ScheduledTask

__all__ = [
    # Types
    "Event",
    "EventType",
    "Priority",
    # Handlers
    "EventHandler",
    "FunctionHandler",
    "AsyncHandler",
    # Bus
    "EventBus",
    # Triggers
    "Trigger",
    "CronTrigger",
    "IntervalTrigger",
    "HealthTrigger",
    "ExpiryTrigger",
    # Dispatchers
    "EventDispatcher",
    "SyncDispatcher",
    "AsyncDispatcher",
    # Scheduler
    "Scheduler",
    "ScheduledTask",
]
