"""
Scheduler for the Tokenade event system.

Provides time-based, health-based, and expiry-based event scheduling.
Uses the EventBus to emit events when triggers fire.

The scheduler is core infrastructure — it works without plugins.
Plugins can register custom triggers with the scheduler.
"""

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from tokenade.core.events.bus import EventBus
from tokenade.core.events.triggers import (
    CronTrigger,
    ExpiryTrigger,
    HealthTrigger,
    IntervalTrigger,
    Trigger,
)
from tokenade.core.events.types import Event, EventType

logger = logging.getLogger(__name__)


class ScheduledTask:
    """A scheduled task that fires an event when its trigger activates."""

    def __init__(
        self,
        name: str,
        event_type: EventType,
        data: Dict[str, Any],
        trigger: Trigger,
        event_bus: EventBus,
        source: str = "scheduler",
    ):
        self.name = name
        self.event_type = event_type
        self.data = data
        self.trigger = trigger
        self.event_bus = event_bus
        self.source = source
        self._fired_count = 0
        self._last_fired: float = 0
        self._error_count = 0

    @property
    def fired_count(self) -> int:
        """Number of times this task has fired."""
        return self._fired_count

    @property
    def last_fired(self) -> float:
        """Timestamp of last fire."""
        return self._last_fired

    @property
    def error_count(self) -> int:
        """Number of errors during execution."""
        return self._error_count

    def check_and_fire(self) -> bool:
        """Check trigger and fire event if needed.

        Returns:
            True if event was fired
        """
        if not self.trigger.can_fire():
            return False

        try:
            self.event_bus.emit(
                event_type=self.event_type,
                data=self.data,
                source=self.source,
            )
            self.trigger.reset()
            self._fired_count += 1
            self._last_fired = time.time()
            logger.info(f"Scheduled task '{self.name}' fired ({self.event_type.value})")
            return True
        except Exception as e:
            self._error_count += 1
            logger.error(f"Scheduled task '{self.name}' failed: {e}")
            return False


class Scheduler:
    """Scheduler for time-based, health-based, and expiry-based events.

    Uses the EventBus to emit events when triggers fire.
    Runs in a background thread, checking triggers at a configurable interval.

    Example:
        scheduler = Scheduler(event_bus)
        scheduler.add_cron_task(
            name="google-refresh",
            event_type=EventType.REFRESH_SUCCESS,
            data={"session_id": "abc"},
            cron_expr="0 */6 * * *"
        )
        scheduler.start()
    """

    def __init__(
        self,
        event_bus: EventBus,
        check_interval: float = 10,
    ):
        """Initialize scheduler.

        Args:
            event_bus: The event bus to emit events through
            check_interval: How often to check triggers (in seconds)
        """
        self._event_bus = event_bus
        self._check_interval = check_interval
        self._tasks: Dict[str, ScheduledTask] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        """Whether the scheduler is running."""
        return self._running

    def add_cron_task(
        self,
        name: str,
        event_type: EventType,
        data: Dict[str, Any],
        cron_expr: str,
        source: str = "scheduler",
    ) -> None:
        """Add a cron-based scheduled task.

        Args:
            name: Task name (must be unique)
            event_type: Event type to emit
            data: Event data payload
            cron_expr: Cron expression (e.g., "0 */6 * * *")
            source: Event source identifier
        """
        trigger = CronTrigger(cron_expr)
        task = ScheduledTask(
            name=name,
            event_type=event_type,
            data=data,
            trigger=trigger,
            event_bus=self._event_bus,
            source=source,
        )
        with self._lock:
            self._tasks[name] = task
        logger.info(f"Added cron task: {name} ({cron_expr})")

    def add_interval_task(
        self,
        name: str,
        event_type: EventType,
        data: Dict[str, Any],
        interval_seconds: float,
        source: str = "scheduler",
    ) -> None:
        """Add an interval-based scheduled task.

        Args:
            name: Task name (must be unique)
            event_type: Event type to emit
            data: Event data payload
            interval_seconds: Time between fires (in seconds)
            source: Event source identifier
        """
        trigger = IntervalTrigger(interval_seconds)
        task = ScheduledTask(
            name=name,
            event_type=event_type,
            data=data,
            trigger=trigger,
            event_bus=self._event_bus,
            source=source,
        )
        with self._lock:
            self._tasks[name] = task
        logger.info(f"Added interval task: {name} (every {interval_seconds}s)")

    def add_health_task(
        self,
        name: str,
        event_type: EventType,
        data: Dict[str, Any],
        health_check_fn: Callable[[], bool],
        check_interval: float = 60,
        source: str = "scheduler",
    ) -> None:
        """Add a health-based scheduled task.

        Args:
            name: Task name (must be unique)
            event_type: Event type to emit
            data: Event data payload
            health_check_fn: Function that returns True when action needed
            check_interval: How often to check (in seconds)
            source: Event source identifier
        """
        trigger = HealthTrigger(health_check_fn, check_interval)
        task = ScheduledTask(
            name=name,
            event_type=event_type,
            data=data,
            trigger=trigger,
            event_bus=self._event_bus,
            source=source,
        )
        with self._lock:
            self._tasks[name] = task
        logger.info(f"Added health task: {name}")

    def add_expiry_task(
        self,
        name: str,
        event_type: EventType,
        data: Dict[str, Any],
        expiry_check_fn: Callable[[], bool],
        check_interval: float = 300,
        source: str = "scheduler",
    ) -> None:
        """Add an expiry-based scheduled task.

        Args:
            name: Task name (must be unique)
            event_type: Event type to emit
            data: Event data payload
            expiry_check_fn: Function that returns True when expired
            check_interval: How often to check (in seconds)
            source: Event source identifier
        """
        trigger = ExpiryTrigger(expiry_check_fn, check_interval)
        task = ScheduledTask(
            name=name,
            event_type=event_type,
            data=data,
            trigger=trigger,
            event_bus=self._event_bus,
            source=source,
        )
        with self._lock:
            self._tasks[name] = task
        logger.info(f"Added expiry task: {name}")

    def remove_task(self, name: str) -> bool:
        """Remove a scheduled task.

        Args:
            name: Task name to remove

        Returns:
            True if task was removed, False if not found
        """
        with self._lock:
            if name in self._tasks:
                del self._tasks[name]
                logger.info(f"Removed task: {name}")
                return True
            return False

    def get_task(self, name: str) -> Optional[ScheduledTask]:
        """Get a scheduled task by name.

        Args:
            name: Task name

        Returns:
            ScheduledTask or None
        """
        return self._tasks.get(name)

    def get_tasks(self) -> List[ScheduledTask]:
        """Get all scheduled tasks.

        Returns:
            List of all tasks
        """
        return list(self._tasks.values())

    def start(self) -> None:
        """Start the scheduler in a background thread."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run,
            name="tokenade-scheduler",
            daemon=True,
        )
        self._thread.start()
        logger.info("Scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Scheduler stopped")

    def _run(self) -> None:
        """Main scheduler loop. Runs in background thread."""
        while self._running:
            try:
                with self._lock:
                    tasks = list(self._tasks.values())

                for task in tasks:
                    task.check_and_fire()

            except Exception as e:
                logger.error(f"Scheduler error: {e}")

            time.sleep(self._check_interval)
