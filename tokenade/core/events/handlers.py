"""
Base handler classes for the Tokenade event bus.

Defines the interface for event handlers and provides
sync/async implementations.
"""

import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from tokenade.core.events.types import Event, Priority

logger = logging.getLogger(__name__)


class EventHandler(ABC):
    """Base class for all event handlers.

    Handlers process events emitted through the EventBus.
    All handlers are sync by default. Use AsyncHandler for background execution.
    """

    def __init__(self, priority: int = Priority.NORMAL):
        self._priority = priority

    @property
    def priority(self) -> int:
        """Handler execution priority (higher = runs first)."""
        return self._priority

    @abstractmethod
    def handle(self, event: Event) -> None:
        """Handle an event.

        Args:
            event: The event to process
        """

    def get_priority(self) -> int:
        """Return handler priority for ordering."""
        return self._priority


class FunctionHandler(EventHandler):
    """Handler that wraps a plain function.

    Convenience class for registering simple callbacks without
    creating a full handler subclass.

    Example:
        handler = FunctionHandler(lambda e: print(e.data))
        bus.on(EventType.SESSION_EXPIRED, handler)
    """

    def __init__(
        self,
        callback: Callable[[Event], None],
        priority: int = Priority.NORMAL,
    ):
        super().__init__(priority)
        self._callback = callback

    def handle(self, event: Event) -> None:
        """Call the wrapped function."""
        self._callback(event)


class AsyncHandler(EventHandler):
    """Handler that runs in a background thread.

    Use for handlers that:
    - Make network calls (webhooks, API requests)
    - Perform long-running operations
    - Should not block the event bus

    If no executor is provided, uses the EventBus's shared executor.

    Example:
        class NotificationHandler(AsyncHandler):
            def handle_async(self, event):
                send_email(event.data)
    """

    def __init__(
        self,
        executor: Optional[ThreadPoolExecutor] = None,
        priority: int = Priority.NORMAL,
    ):
        super().__init__(priority)
        self._executor = executor
        self._bus_executor: Optional[ThreadPoolExecutor] = None

    def set_bus_executor(self, executor: ThreadPoolExecutor) -> None:
        """Set the EventBus's shared executor (called by EventBus on registration)."""
        self._bus_executor = executor

    def handle(self, event: Event) -> None:
        """Submit handler to thread pool for background execution.

        Uses provided executor, or falls back to EventBus's shared executor.
        """
        executor = self._executor or self._bus_executor
        if executor:
            executor.submit(self._safe_handle_async, event)
        else:
            # No executor available — run in current thread (blocking)
            self._safe_handle_async(event)

    def _safe_handle_async(self, event: Event) -> None:
        """Call handle_async with error catching."""
        try:
            self.handle_async(event)
        except Exception as e:
            logger.warning(
                f"Async handler {type(self).__name__} failed for {event.event_type.value}: {e}"
            )

    @abstractmethod
    def handle_async(self, event: Event) -> None:
        """Handle an event in a background thread.

        Override this method instead of handle() for async handlers.

        Args:
            event: The event to process
        """
