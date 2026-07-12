"""
Event bus for the Tokenade event system.

Provides pub/sub event dispatch with priority ordering,
sync/async handler support, and thread safety.

The event bus is core infrastructure — it works without plugins.
Plugins can register handlers to extend behavior.
"""

import logging
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from tokenade.core.events.handlers import EventHandler, FunctionHandler
from tokenade.core.events.types import Event, EventType, Priority

logger = logging.getLogger(__name__)


class EventBus:
    """Core event bus for pub/sub event dispatch.

    Features:
    - Priority-based handler ordering (higher = runs first)
    - Sync by default, async opt-in
    - Thread-safe handler registration and emission
    - Handler failures are caught and logged, never propagate

    Example:
        bus = EventBus()
        bus.on(EventType.SESSION_EXPIRED, lambda e: print(e.data))
        bus.emit(EventType.SESSION_EXPIRED, {"session_id": "abc"})
    """

    def __init__(self, max_workers: int = 4):
        self._listeners: Dict[EventType, List[EventHandler]] = defaultdict(list)
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._event_history: List[Event] = []
        self._max_history = 100

    def on(
        self,
        event_type: EventType,
        callback: Callable[[Event], None],
        priority: int = Priority.NORMAL,
    ) -> None:
        """Register a listener for an event type.

        Args:
            event_type: The event type to listen for
            callback: Function to call when event is emitted
            priority: Handler priority (higher = runs first)
        """
        handler = FunctionHandler(callback, priority)
        self.on_handler(event_type, handler)

    def on_handler(self, event_type: EventType, handler: EventHandler) -> None:
        """Register a handler for an event type.

        If the handler is an AsyncHandler, it automatically gets
        access to the bus's shared thread pool executor.

        Args:
            event_type: The event type to listen for
            handler: The handler instance
        """
        with self._lock:
            # Pass the shared executor to AsyncHandler instances
            from tokenade.core.events.handlers import AsyncHandler
            if isinstance(handler, AsyncHandler) and handler._executor is None:
                handler.set_bus_executor(self._executor)

            self._listeners[event_type].append(handler)
            # Sort by priority (higher first)
            self._listeners[event_type].sort(
                key=lambda h: h.get_priority(), reverse=True
            )
        logger.debug(
            f"Registered handler {type(handler).__name__} for {event_type.value} "
            f"(priority={handler.get_priority()})"
        )

    def off(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        """Unregister a listener for an event type.

        Args:
            event_type: The event type to stop listening for
            callback: The callback to remove
        """
        with self._lock:
            handlers = self._listeners.get(event_type, [])
            self._listeners[event_type] = [
                h for h in handlers
                if not (isinstance(h, FunctionHandler) and h._callback == callback)
            ]

    def off_handler(self, event_type: EventType, handler: EventHandler) -> None:
        """Unregister a handler for an event type.

        Args:
            event_type: The event type to stop listening for
            handler: The handler to remove
        """
        with self._lock:
            handlers = self._listeners.get(event_type, [])
            self._listeners[event_type] = [h for h in handlers if h is not handler]

    def emit(
        self,
        event_type: EventType,
        data: Optional[Dict[str, Any]] = None,
        source: str = "",
    ) -> Event:
        """Emit an event. Non-blocking — runs handlers in background threads.

        Args:
            event_type: The event type to emit
            data: Event data payload
            source: Source of the event (e.g., "plugin_loader", "session_ops")

        Returns:
            The emitted Event object
        """
        event = Event(
            event_type=event_type,
            data=data or {},
            source=source,
        )

        # Store in history
        with self._lock:
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]

        # Dispatch to handlers
        handlers = self._listeners.get(event_type, [])
        if not handlers:
            logger.debug(f"No handlers for {event_type.value}")
            return event

        for handler in handlers:
            self._executor.submit(self._safe_call, handler, event)

        logger.debug(
            f"Emitted {event_type.value} to {len(handlers)} handlers "
            f"(id={event.id})"
        )
        return event

    def emit_sync(
        self,
        event_type: EventType,
        data: Optional[Dict[str, Any]] = None,
        source: str = "",
    ) -> Event:
        """Emit an event synchronously. Blocks until all handlers complete.

        Use this when you need to ensure all handlers have processed
        the event before continuing.

        Args:
            event_type: The event type to emit
            data: Event data payload
            source: Source of the event

        Returns:
            The emitted Event object
        """
        event = Event(
            event_type=event_type,
            data=data or {},
            source=source,
        )

        # Store in history
        with self._lock:
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]

        # Dispatch to handlers synchronously
        handlers = self._listeners.get(event_type, [])
        for handler in handlers:
            self._safe_call(handler, event)

        return event

    def get_listeners(self, event_type: EventType) -> List[EventHandler]:
        """Get all handlers registered for an event type.

        Args:
            event_type: The event type

        Returns:
            List of handlers (sorted by priority)
        """
        return list(self._listeners.get(event_type, []))

    def get_history(self, limit: int = 50) -> List[Event]:
        """Get recent event history.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of recent events (newest first)
        """
        with self._lock:
            return list(reversed(self._event_history[-limit:]))

    def clear_listeners(self, event_type: Optional[EventType] = None) -> None:
        """Clear handlers for an event type or all event types.

        Args:
            event_type: If provided, clear only this event type.
                       If None, clear all.
        """
        with self._lock:
            if event_type is None:
                self._listeners.clear()
            else:
                self._listeners.pop(event_type, None)

    def handler_count(self, event_type: Optional[EventType] = None) -> int:
        """Count handlers for an event type or all event types.

        Args:
            event_type: If provided, count only this event type.
                       If None, count all.

        Returns:
            Number of handlers
        """
        with self._lock:
            if event_type is None:
                return sum(len(handlers) for handlers in self._listeners.values())
            return len(self._listeners.get(event_type, []))

    def _safe_call(self, handler: EventHandler, event: Event) -> None:
        """Call a handler with error catching.

        Handler failures are logged but never propagate.
        """
        try:
            handler.handle(event)
        except Exception as e:
            logger.warning(
                f"Handler {type(handler).__name__} failed for "
                f"{event.event_type.value}: {e}"
            )

    def shutdown(self) -> None:
        """Shutdown the event bus executor.

        Call this when the application is shutting down.
        """
        self._executor.shutdown(wait=False)
