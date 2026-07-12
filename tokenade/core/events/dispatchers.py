"""
Event dispatchers for the Tokenade event bus.

Provides different dispatch strategies for executing handlers:
- SyncDispatcher: Execute handlers in order, blocking
- AsyncDispatcher: Execute handlers in background threads
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from tokenade.core.events.handlers import EventHandler
from tokenade.core.events.types import Event

logger = logging.getLogger(__name__)


class EventDispatcher:
    """Base dispatcher for executing event handlers.

    Dispatchers are responsible for calling handlers in the correct order
    and handling errors gracefully.
    """

    def __init__(self, executor: Optional[ThreadPoolExecutor] = None):
        """Initialize dispatcher.

        Args:
            executor: Optional thread pool for async dispatch
        """
        self._executor = executor

    def dispatch(self, event: Event, handlers: List[EventHandler]) -> None:
        """Dispatch event to handlers. Default: sync execution.

        Args:
            event: The event to dispatch
            handlers: List of handlers to call (sorted by priority)
        """
        self.dispatch_sync(event, handlers)

    def dispatch_sync(self, event: Event, handlers: List[EventHandler]) -> None:
        """Dispatch event to handlers synchronously.

        Executes handlers in priority order. Blocks until all complete.

        Args:
            event: The event to dispatch
            handlers: List of handlers to call (sorted by priority)
        """
        for handler in handlers:
            self._safe_call(handler, event)

    def dispatch_async(self, event: Event, handlers: List[EventHandler]) -> None:
        """Dispatch event to handlers asynchronously.

        Submits handlers to thread pool for background execution.

        Args:
            event: The event to dispatch
            handlers: List of handlers to call (sorted by priority)
        """
        if not self._executor:
            logger.warning("No executor available for async dispatch, falling back to sync")
            self.dispatch_sync(event, handlers)
            return

        for handler in handlers:
            self._executor.submit(self._safe_call, handler, event)

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


class SyncDispatcher(EventDispatcher):
    """Dispatcher that executes handlers synchronously.

    Always blocks until all handlers complete. Use when ordering
    guarantees are required.
    """

    def dispatch(self, event: Event, handlers: List[EventHandler]) -> None:
        """Dispatch event to handlers synchronously."""
        self.dispatch_sync(event, handlers)


class AsyncDispatcher(EventDispatcher):
    """Dispatcher that executes handlers asynchronously.

    Submits handlers to thread pool for background execution.
    Returns immediately without waiting for handlers to complete.
    """

    def dispatch(self, event: Event, handlers: List[EventHandler]) -> None:
        """Dispatch event to handlers asynchronously."""
        self.dispatch_async(event, handlers)
