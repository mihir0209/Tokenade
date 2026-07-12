"""
Trigger types for the Tokenade scheduler.

Defines different trigger mechanisms for scheduling events:
- CronTrigger: Fire on cron schedule
- IntervalTrigger: Fire at regular intervals
- HealthTrigger: Fire when health check returns True
- ExpiryTrigger: Fire when expiry check returns True
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class Trigger(ABC):
    """Base class for all triggers.

    Triggers determine when a scheduled event should fire.
    Each trigger type implements should_fire() with its own logic.
    """

    def __init__(self):
        self._last_fired: float = 0
        self._active = True

    @property
    def active(self) -> bool:
        """Whether this trigger is active."""
        return self._active

    @active.setter
    def active(self, value: bool) -> None:
        """Enable or disable this trigger."""
        self._active = value

    @property
    def last_fired(self) -> float:
        """Timestamp of last fire."""
        return self._last_fired

    @abstractmethod
    def should_fire(self) -> bool:
        """Check if this trigger should fire now.

        Returns:
            True if the trigger should fire
        """

    def reset(self) -> None:
        """Reset trigger state after firing."""
        self._last_fired = time.time()

    def can_fire(self) -> bool:
        """Check if trigger is active and ready to fire.

        Returns:
            True if trigger is active and should_fire() returns True
        """
        if not self._active:
            return False
        return self.should_fire()


class CronTrigger(Trigger):
    """Fire on a cron-like schedule.

    Supports simple cron expressions:
    - "*/5 * * * *" — Every 5 minutes
    - "0 */6 * * *" — Every 6 hours
    - "0 9 * * 1-5" — Weekdays at 9am

    Uses croniter library if available, otherwise falls back to
    simple interval-based scheduling.

    Example:
        trigger = CronTrigger("*/30 * * * *")  # Every 30 minutes
    """

    def __init__(self, cron_expr: str, interval_seconds: Optional[float] = None):
        """Initialize cron trigger.

        Args:
            cron_expr: Cron expression (e.g., "*/5 * * * *")
            interval_seconds: Fallback interval if croniter not available
        """
        super().__init__()
        self._cron_expr = cron_expr
        self._interval_seconds = interval_seconds
        self._next_fire: float = 0
        self._croniter = None

        # Try to import croniter
        try:
            from croniter import croniter
            self._croniter = croniter(cron_expr, time.time())
            self._next_fire = self._croniter.get_next(float)
        except ImportError:
            # Fallback to interval-based scheduling
            if interval_seconds is None:
                # Parse simple cron expressions
                self._interval_seconds = self._parse_simple_cron(cron_expr)
            self._next_fire = time.time() + (self._interval_seconds or 300)
        except Exception as e:
            logger.warning(f"Failed to parse cron expression '{cron_expr}': {e}")
            self._interval_seconds = interval_seconds or 300
            self._next_fire = time.time() + self._interval_seconds

    def should_fire(self) -> bool:
        """Check if current time has passed the next fire time."""
        return time.time() >= self._next_fire

    def reset(self) -> None:
        """Update next fire time after firing."""
        super().reset()
        if self._croniter:
            self._next_fire = self._croniter.get_next(float)
        else:
            self._next_fire = time.time() + (self._interval_seconds or 300)

    def _parse_simple_cron(self, expr: str) -> float:
        """Parse simple cron expressions to interval seconds.

        Handles:
        - "*/N * * * *" → N * 60 seconds
        - "0 */N * * *" → N * 3600 seconds
        - "0 0 * * *" → 86400 seconds
        """
        parts = expr.split()
        if len(parts) != 5:
            return 300  # Default 5 minutes

        minute, hour, _, _, _ = parts

        if minute.startswith("*/"):
            try:
                return int(minute[2:]) * 60
            except ValueError:
                return 300

        if hour.startswith("*/"):
            try:
                return int(hour[2:]) * 3600
            except ValueError:
                return 3600

        # Default: daily
        return 86400


class IntervalTrigger(Trigger):
    """Fire at regular intervals.

    Example:
        trigger = IntervalTrigger(300)  # Every 5 minutes
    """

    def __init__(self, interval_seconds: float):
        """Initialize interval trigger.

        Args:
            interval_seconds: Time between fires in seconds
        """
        super().__init__()
        self._interval_seconds = interval_seconds
        self._next_fire: float = time.time() + interval_seconds

    def should_fire(self) -> bool:
        """Check if current time has passed the next fire time."""
        return time.time() >= self._next_fire

    def reset(self) -> None:
        """Update next fire time after firing."""
        super().reset()
        self._next_fire = time.time() + self._interval_seconds


class HealthTrigger(Trigger):
    """Fire when a health check function returns True.

    Polls the health check function at a configurable interval.
    Fires when the function returns True (indicating action needed).

    Example:
        trigger = HealthTrigger(
            health_check_fn=lambda: check_token_expiry("session1") < 3600,
            interval_seconds=60
        )
    """

    def __init__(
        self,
        health_check_fn: Callable[[], bool],
        interval_seconds: float = 60,
    ):
        """Initialize health trigger.

        Args:
            health_check_fn: Function that returns True when action needed
            interval_seconds: How often to check (in seconds)
        """
        super().__init__()
        self._health_check_fn = health_check_fn
        self._interval_seconds = interval_seconds
        self._next_check: float = time.time() + interval_seconds

    def should_fire(self) -> bool:
        """Check if health check returns True and interval has elapsed."""
        if time.time() < self._next_check:
            return False

        self._next_check = time.time() + self._interval_seconds

        try:
            return self._health_check_fn()
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    def reset(self) -> None:
        """Reset after firing."""
        super().reset()
        self._next_check = time.time() + self._interval_seconds


class ExpiryTrigger(Trigger):
    """Fire when an expiry check function returns True.

    Similar to HealthTrigger but specifically for expiry detection.
    Polls the expiry check function at a configurable interval.

    Example:
        trigger = ExpiryTrigger(
            expiry_check_fn=lambda: is_token_expired("session1"),
            interval_seconds=300
        )
    """

    def __init__(
        self,
        expiry_check_fn: Callable[[], bool],
        interval_seconds: float = 300,
    ):
        """Initialize expiry trigger.

        Args:
            expiry_check_fn: Function that returns True when expired
            interval_seconds: How often to check (in seconds)
        """
        super().__init__()
        self._expiry_check_fn = expiry_check_fn
        self._interval_seconds = interval_seconds
        self._next_check: float = time.time() + interval_seconds

    def should_fire(self) -> bool:
        """Check if expiry check returns True and interval has elapsed."""
        if time.time() < self._next_check:
            return False

        self._next_check = time.time() + self._interval_seconds

        try:
            return self._expiry_check_fn()
        except Exception as e:
            logger.warning(f"Expiry check failed: {e}")
            return False

    def reset(self) -> None:
        """Reset after firing."""
        super().reset()
        self._next_check = time.time() + self._interval_seconds
