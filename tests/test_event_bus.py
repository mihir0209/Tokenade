"""
Unit tests for the Tokenade event bus.
"""

import time
import threading
from unittest.mock import MagicMock, patch

import pytest

from tokenade.core.events import (
    Event,
    EventType,
    Priority,
    EventHandler,
    FunctionHandler,
    AsyncHandler,
    EventBus,
    Trigger,
    CronTrigger,
    IntervalTrigger,
    HealthTrigger,
    ExpiryTrigger,
    EventDispatcher,
    SyncDispatcher,
    AsyncDispatcher,
    Scheduler,
    ScheduledTask,
)


class TestEvent:
    """Tests for Event dataclass."""

    def test_event_creation(self):
        event = Event(event_type=EventType.SESSION_EXPIRED)
        assert event.event_type == EventType.SESSION_EXPIRED
        assert event.data == {}
        assert event.source == ""
        assert event.id is not None
        assert event.timestamp > 0

    def test_event_with_data(self):
        event = Event(
            event_type=EventType.REFRESH_SUCCESS,
            data={"session_id": "abc", "site": "google.com"},
            source="session_ops",
        )
        assert event.data["session_id"] == "abc"
        assert event.source == "session_ops"

    def test_event_to_dict(self):
        event = Event(
            event_type=EventType.PLUGIN_LOADED,
            data={"name": "test-plugin"},
            source="plugin_loader",
        )
        d = event.to_dict()
        assert d["event_type"] == "plugin_loaded"
        assert d["data"]["name"] == "test-plugin"
        assert d["source"] == "plugin_loader"

    def test_event_from_dict(self):
        d = {
            "event_type": "session_expired",
            "data": {"session_id": "abc"},
            "source": "test",
            "id": "test123",
            "timestamp": 1234567890.0,
        }
        event = Event.from_dict(d)
        assert event.event_type == EventType.SESSION_EXPIRED
        assert event.data["session_id"] == "abc"
        assert event.id == "test123"


class TestEventType:
    """Tests for EventType enum."""

    def test_all_event_types_exist(self):
        # Session events
        assert EventType.SESSION_EXPIRED.value == "session_expired"
        assert EventType.SESSION_REFRESHED.value == "session_refreshed"
        assert EventType.SESSION_VALIDATED.value == "session_validated"
        assert EventType.SESSION_EXPORTED.value == "session_exported"

        # Refresh events
        assert EventType.REFRESH_STARTED.value == "refresh_started"
        assert EventType.REFRESH_SUCCESS.value == "refresh_success"
        assert EventType.REFRESH_FAILED.value == "refresh_failed"

        # Plugin events
        assert EventType.PLUGIN_LOADED.value == "plugin_loaded"
        assert EventType.PLUGIN_UNLOADED.value == "plugin_unloaded"
        assert EventType.PLUGIN_ERROR.value == "plugin_error"


class TestPriority:
    """Tests for Priority enum."""

    def test_priority_ordering(self):
        assert Priority.CRITICAL > Priority.HIGH
        assert Priority.HIGH > Priority.NORMAL
        assert Priority.NORMAL > Priority.LOW
        assert Priority.LOW > Priority.BACKGROUND


class TestFunctionHandler:
    """Tests for FunctionHandler."""

    def test_handler_creation(self):
        callback = lambda e: None
        handler = FunctionHandler(callback, priority=Priority.HIGH)
        assert handler.priority == Priority.HIGH

    def test_handler_handle(self):
        received = []
        callback = lambda e: received.append(e)
        handler = FunctionHandler(callback)

        event = Event(event_type=EventType.SESSION_EXPIRED)
        handler.handle(event)

        assert len(received) == 1
        assert received[0] is event


class TestEventBus:
    """Tests for EventBus."""

    def test_bus_creation(self):
        bus = EventBus()
        assert bus.handler_count() == 0

    def test_register_handler(self):
        bus = EventBus()
        received = []
        bus.on(EventType.SESSION_EXPIRED, lambda e: received.append(e))

        assert bus.handler_count(EventType.SESSION_EXPIRED) == 1

    def test_emit_event(self):
        bus = EventBus()
        received = []
        bus.on(EventType.SESSION_EXPIRED, lambda e: received.append(e))

        bus.emit_sync(EventType.SESSION_EXPIRED, {"session_id": "abc"})

        assert len(received) == 1
        assert received[0].event_type == EventType.SESSION_EXPIRED
        assert received[0].data["session_id"] == "abc"

    def test_priority_ordering(self):
        bus = EventBus()
        order = []

        bus.on(EventType.SESSION_EXPIRED, lambda e: order.append("low"), Priority.LOW)
        bus.on(EventType.SESSION_EXPIRED, lambda e: order.append("high"), Priority.HIGH)
        bus.on(EventType.SESSION_EXPIRED, lambda e: order.append("normal"), Priority.NORMAL)

        bus.emit_sync(EventType.SESSION_EXPIRED)

        assert order == ["high", "normal", "low"]

    def test_handler_failure_does_not_propagate(self):
        bus = EventBus()

        def bad_handler(e):
            raise ValueError("Test error")

        good_received = []
        bus.on(EventType.SESSION_EXPIRED, bad_handler, Priority.HIGH)
        bus.on(EventType.SESSION_EXPIRED, lambda e: good_received.append(e), Priority.LOW)

        # Should not raise
        bus.emit_sync(EventType.SESSION_EXPIRED)

        assert len(good_received) == 1

    def test_off_handler(self):
        bus = EventBus()
        received = []
        callback = lambda e: received.append(e)

        bus.on(EventType.SESSION_EXPIRED, callback)
        assert bus.handler_count(EventType.SESSION_EXPIRED) == 1

        bus.off(EventType.SESSION_EXPIRED, callback)
        assert bus.handler_count(EventType.SESSION_EXPIRED) == 0

    def test_event_history(self):
        bus = EventBus()

        bus.emit_sync(EventType.SESSION_EXPIRED, {"a": 1})
        bus.emit_sync(EventType.REFRESH_SUCCESS, {"b": 2})

        history = bus.get_history()
        assert len(history) == 2
        # Newest first
        assert history[0].event_type == EventType.REFRESH_SUCCESS
        assert history[1].event_type == EventType.SESSION_EXPIRED

    def test_clear_listeners(self):
        bus = EventBus()
        bus.on(EventType.SESSION_EXPIRED, lambda e: None)
        bus.on(EventType.REFRESH_SUCCESS, lambda e: None)

        assert bus.handler_count() == 2

        bus.clear_listeners(EventType.SESSION_EXPIRED)
        assert bus.handler_count() == 1

        bus.clear_listeners()
        assert bus.handler_count() == 0


class TestCronTrigger:
    """Tests for CronTrigger."""

    def test_cron_trigger_creation(self):
        trigger = CronTrigger("*/5 * * * *")
        assert trigger.active is True

    def test_cron_trigger_should_fire(self):
        # Create trigger that should fire immediately (past time)
        trigger = CronTrigger("*/5 * * * *")
        # Reset to past time
        trigger._next_fire = time.time() - 1
        assert trigger.should_fire() is True

    def test_cron_trigger_should_not_fire(self):
        trigger = CronTrigger("*/5 * * * *")
        trigger._next_fire = time.time() + 3600
        assert trigger.should_fire() is False


class TestIntervalTrigger:
    """Tests for IntervalTrigger."""

    def test_interval_trigger_creation(self):
        trigger = IntervalTrigger(300)
        assert trigger.active is True

    def test_interval_trigger_should_fire(self):
        trigger = IntervalTrigger(300)
        trigger._next_fire = time.time() - 1
        assert trigger.should_fire() is True

    def test_interval_trigger_should_not_fire(self):
        trigger = IntervalTrigger(300)
        trigger._next_fire = time.time() + 3600
        assert trigger.should_fire() is False


class TestHealthTrigger:
    """Tests for HealthTrigger."""

    def test_health_trigger_creation(self):
        trigger = HealthTrigger(lambda: True, interval_seconds=60)
        assert trigger.active is True

    def test_health_trigger_should_fire(self):
        trigger = HealthTrigger(lambda: True, interval_seconds=0)
        trigger._next_check = time.time() - 1
        assert trigger.should_fire() is True

    def test_health_trigger_should_not_fire(self):
        trigger = HealthTrigger(lambda: False, interval_seconds=0)
        trigger._next_check = time.time() - 1
        assert trigger.should_fire() is False

    def test_health_trigger_exception(self):
        def bad_check():
            raise RuntimeError("Test error")

        trigger = HealthTrigger(bad_check, interval_seconds=0)
        trigger._next_check = time.time() - 1
        # Should not raise, returns False on error
        assert trigger.should_fire() is False


class TestExpiryTrigger:
    """Tests for ExpiryTrigger."""

    def test_expiry_trigger_creation(self):
        trigger = ExpiryTrigger(lambda: True, interval_seconds=300)
        assert trigger.active is True

    def test_expiry_trigger_should_fire(self):
        trigger = ExpiryTrigger(lambda: True, interval_seconds=0)
        trigger._next_check = time.time() - 1
        assert trigger.should_fire() is True

    def test_expiry_trigger_should_not_fire(self):
        trigger = ExpiryTrigger(lambda: False, interval_seconds=0)
        trigger._next_check = time.time() - 1
        assert trigger.should_fire() is False


class TestScheduler:
    """Tests for Scheduler."""

    def test_scheduler_creation(self):
        bus = EventBus()
        scheduler = Scheduler(bus)
        assert scheduler.is_running is False
        assert len(scheduler.get_tasks()) == 0

    def test_add_cron_task(self):
        bus = EventBus()
        scheduler = Scheduler(bus)
        scheduler.add_cron_task(
            name="test-task",
            event_type=EventType.SESSION_EXPIRED,
            data={"session_id": "abc"},
            cron_expr="*/5 * * * *",
        )
        assert len(scheduler.get_tasks()) == 1
        assert scheduler.get_task("test-task") is not None

    def test_add_interval_task(self):
        bus = EventBus()
        scheduler = Scheduler(bus)
        scheduler.add_interval_task(
            name="test-task",
            event_type=EventType.HEALTH_CHECK,
            data={},
            interval_seconds=60,
        )
        assert len(scheduler.get_tasks()) == 1

    def test_remove_task(self):
        bus = EventBus()
        scheduler = Scheduler(bus)
        scheduler.add_cron_task(
            name="test-task",
            event_type=EventType.SESSION_EXPIRED,
            data={},
            cron_expr="*/5 * * * *",
        )
        assert scheduler.remove_task("test-task") is True
        assert len(scheduler.get_tasks()) == 0

    def test_remove_nonexistent_task(self):
        bus = EventBus()
        scheduler = Scheduler(bus)
        assert scheduler.remove_task("nonexistent") is False

    def test_start_stop(self):
        bus = EventBus()
        scheduler = Scheduler(bus, check_interval=0.1)
        scheduler.start()
        assert scheduler.is_running is True

        time.sleep(0.2)
        scheduler.stop()
        assert scheduler.is_running is False

    def test_task_fires(self):
        bus = EventBus()
        received = []
        bus.on(EventType.SESSION_EXPIRED, lambda e: received.append(e))

        scheduler = Scheduler(bus, check_interval=0.1)
        scheduler.add_interval_task(
            name="test-task",
            event_type=EventType.SESSION_EXPIRED,
            data={"test": True},
            interval_seconds=0.1,
        )
        scheduler.start()
        time.sleep(0.3)
        scheduler.stop()

        assert len(received) >= 1
        assert received[0].data["test"] is True


class TestSyncDispatcher:
    """Tests for SyncDispatcher."""

    def test_sync_dispatch(self):
        order = []

        class TestHandler(EventHandler):
            def handle(self, event):
                order.append(self.name)

        h1 = TestHandler()
        h1.name = "handler1"
        h2 = TestHandler()
        h2.name = "handler2"

        dispatcher = SyncDispatcher()
        event = Event(event_type=EventType.SESSION_EXPIRED)
        dispatcher.dispatch_sync(event, [h1, h2])

        assert order == ["handler1", "handler2"]


class TestAsyncDispatcher:
    """Tests for AsyncDispatcher."""

    def test_async_dispatch(self):
        from concurrent.futures import ThreadPoolExecutor

        received = []

        class TestHandler(EventHandler):
            def handle(self, event):
                received.append(event)

        executor = ThreadPoolExecutor(max_workers=2)
        dispatcher = AsyncDispatcher(executor)
        event = Event(event_type=EventType.SESSION_EXPIRED)

        dispatcher.dispatch_async(event, [TestHandler()])
        time.sleep(0.1)

        assert len(received) == 1
        executor.shutdown(wait=False)
