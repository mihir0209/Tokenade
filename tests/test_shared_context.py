"""Unit tests for the shared context module.

Tests all namespaces, task tracking, thread safety,
and singleton behavior.
"""

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from tokenade.core.context import (
    ConfigNamespace,
    PluginsNamespace,
    RuntimeNamespace,
    SessionsNamespace,
    SharedContext,
    TaskState,
    TaskTracker,
)


class TestTaskTracker:
    """Tests for TaskTracker."""

    def test_start_task(self):
        tracker = TaskTracker()
        task = tracker.start_task("t1", "my-plugin", "refresh")

        assert task["id"] == "t1"
        assert task["plugin_name"] == "my-plugin"
        assert task["task_type"] == "refresh"
        assert task["state"] == TaskState.PENDING
        assert task["result"] is None

    def test_start_duplicate_task(self):
        tracker = TaskTracker()
        tracker.start_task("t1", "my-plugin", "refresh")

        with pytest.raises(ValueError, match="already exists"):
            tracker.start_task("t1", "my-plugin", "refresh")

    def test_update_task_valid_transition(self):
        tracker = TaskTracker()
        tracker.start_task("t1", "my-plugin", "refresh")

        task = tracker.update_task("t1", TaskState.IN_PROGRESS)
        assert task["state"] == TaskState.IN_PROGRESS

        task = tracker.update_task("t1", TaskState.COMPLETED, result={"ok": True})
        assert task["state"] == TaskState.COMPLETED
        assert task["result"] == {"ok": True}

    def test_update_task_invalid_transition(self):
        tracker = TaskTracker()
        tracker.start_task("t1", "my-plugin", "refresh")
        tracker.update_task("t1", TaskState.IN_PROGRESS)
        tracker.update_task("t1", TaskState.COMPLETED)

        with pytest.raises(ValueError, match="Invalid transition"):
            tracker.update_task("t1", TaskState.PENDING)

    def test_update_task_not_found(self):
        tracker = TaskTracker()

        with pytest.raises(KeyError, match="not found"):
            tracker.update_task("nonexistent", TaskState.IN_PROGRESS)

    def test_get_task(self):
        tracker = TaskTracker()
        tracker.start_task("t1", "my-plugin", "refresh")

        task = tracker.get_task("t1")
        assert task is not None
        assert task["id"] == "t1"

    def test_get_task_not_found(self):
        tracker = TaskTracker()
        assert tracker.get_task("nonexistent") is None

    def test_list_tasks(self):
        tracker = TaskTracker()
        tracker.start_task("t1", "plugin-a", "refresh")
        tracker.start_task("t2", "plugin-b", "export")
        tracker.start_task("t3", "plugin-a", "validate")

        all_tasks = tracker.list_tasks()
        assert len(all_tasks) == 3

        plugin_a_tasks = tracker.list_tasks(plugin_name="plugin-a")
        assert len(plugin_a_tasks) == 2
        assert all(t["plugin_name"] == "plugin-a" for t in plugin_a_tasks)

    def test_abandon_task(self):
        tracker = TaskTracker()
        tracker.start_task("t1", "my-plugin", "refresh")

        task = tracker.abandon_task("t1")
        assert task["state"] == TaskState.FAILED
        assert task["result"] == "abandoned"

    def test_is_task_active(self):
        tracker = TaskTracker()
        tracker.start_task("t1", "my-plugin", "refresh")

        assert tracker.is_task_active("t1") is True

        tracker.update_task("t1", TaskState.IN_PROGRESS)
        assert tracker.is_task_active("t1") is True

        tracker.update_task("t1", TaskState.COMPLETED)
        assert tracker.is_task_active("t1") is False

    def test_is_task_active_not_found(self):
        tracker = TaskTracker()
        assert tracker.is_task_active("nonexistent") is False

    def test_cleanup_completed(self):
        tracker = TaskTracker()
        tracker.start_task("t1", "my-plugin", "refresh")
        tracker.update_task("t1", TaskState.IN_PROGRESS)
        tracker.update_task("t1", TaskState.COMPLETED)

        # Manually set updated_at to old time
        tracker._tasks["t1"]["updated_at"] = datetime.now(timezone.utc) - timedelta(hours=25)

        removed = tracker.cleanup_completed(max_age_hours=24)
        assert removed == 1
        assert tracker.get_task("t1") is None

    def test_thread_safety(self):
        tracker = TaskTracker()
        errors = []

        def add_tasks(prefix, count):
            try:
                for i in range(count):
                    tracker.start_task(f"{prefix}-{i}", "plugin", "task")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=add_tasks, args=(f"t{i}", 10))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(tracker.list_tasks()) == 50


class TestSessionsNamespace:
    """Tests for SessionsNamespace."""

    def test_set_and_get(self):
        ns = SessionsNamespace()
        ns.set("s1", {"cookies": {"a": "b"}, "site": "example.com"})

        data = ns.get("s1")
        assert data is not None
        assert data["cookies"] == {"a": "b"}
        assert data["site"] == "example.com"

    def test_get_not_found(self):
        ns = SessionsNamespace()
        assert ns.get("nonexistent") is None

    def test_delete(self):
        ns = SessionsNamespace()
        ns.set("s1", {"data": True})
        assert ns.delete("s1") is True
        assert ns.get("s1") is None

    def test_delete_not_found(self):
        ns = SessionsNamespace()
        assert ns.delete("nonexistent") is False

    def test_list(self):
        ns = SessionsNamespace()
        ns.set("s1", {"data": 1})
        ns.set("s2", {"data": 2})

        sessions = ns.list()
        assert "s1" in sessions
        assert "s2" in sessions

    def test_exists(self):
        ns = SessionsNamespace()
        ns.set("s1", {"data": True})

        assert ns.exists("s1") is True
        assert ns.exists("s2") is False

    def test_health(self):
        ns = SessionsNamespace()
        ns.set("s1", {"data": True})

        assert ns.get_health("s1") is None

        ns.set_health("s1", 85.0)
        assert ns.get_health("s1") == 85.0

    def test_health_invalid_score(self):
        ns = SessionsNamespace()
        with pytest.raises(ValueError, match="must be 0-100"):
            ns.set_health("s1", 150.0)

    def test_metadata(self):
        ns = SessionsNamespace()
        ns.set("s1", {"data": True, "source": "cli"})

        meta = ns.get_metadata("s1")
        assert meta["source"] == "cli"
        assert "created_at" in meta
        assert "updated_at" in meta

    def test_count(self):
        ns = SessionsNamespace()
        ns.set("s1", {"data": 1})
        ns.set("s2", {"data": 2})
        assert ns.count() == 2

    def test_clear(self):
        ns = SessionsNamespace()
        ns.set("s1", {"data": 1})
        ns.set("s2", {"data": 2})
        count = ns.clear()
        assert count == 2
        assert ns.count() == 0


class TestPluginsNamespace:
    """Tests for PluginsNamespace."""

    def test_register_and_get(self):
        ns = PluginsNamespace()
        ns.register("p1", {"version": "1.0.0", "type": "handler"})

        info = ns.get("p1")
        assert info is not None
        assert info["version"] == "1.0.0"
        assert info["type"] == "handler"

    def test_unregister(self):
        ns = PluginsNamespace()
        ns.register("p1", {"version": "1.0.0"})
        assert ns.unregister("p1") is True
        assert ns.get("p1") is None

    def test_unregister_not_found(self):
        ns = PluginsNamespace()
        assert ns.unregister("nonexistent") is False

    def test_list(self):
        ns = PluginsNamespace()
        ns.register("p1", {"version": "1.0.0"})
        ns.register("p2", {"version": "2.0.0"})

        plugins = ns.list()
        assert "p1" in plugins
        assert "p2" in plugins

    def test_is_loaded(self):
        ns = PluginsNamespace()
        ns.register("p1", {"version": "1.0.0"})

        assert ns.is_loaded("p1") is True
        assert ns.is_loaded("p2") is False

    def test_config(self):
        ns = PluginsNamespace()
        ns.set_config("p1", {"timeout": 30, "retries": 3})

        config = ns.get_config("p1")
        assert config["timeout"] == 30
        assert config["retries"] == 3

    def test_config_not_found(self):
        ns = PluginsNamespace()
        assert ns.get_config("nonexistent") == {}

    def test_health(self):
        ns = PluginsNamespace()
        ns.register("p1", {"version": "1.0.0"})

        assert ns.get_health("p1") is None

        ns.set_health("p1", True)
        assert ns.get_health("p1") is True

        ns.set_health("p1", False)
        assert ns.get_health("p1") is False

    def test_version(self):
        ns = PluginsNamespace()
        ns.register("p1", {"version": "1.0.0"})

        assert ns.get_version("p1") == "1.0.0"

        ns.set_version("p1", "2.0.0")
        assert ns.get_version("p1") == "2.0.0"

    def test_count(self):
        ns = PluginsNamespace()
        ns.register("p1", {"version": "1.0.0"})
        ns.register("p2", {"version": "2.0.0"})
        assert ns.count() == 2


class TestConfigNamespace:
    """Tests for ConfigNamespace."""

    def test_get_set(self):
        ns = ConfigNamespace()
        ns.set("theme", "dark")
        assert ns.get("theme") == "dark"

    def test_get_default(self):
        ns = ConfigNamespace()
        assert ns.get("missing", "default") == "default"

    def test_delete(self):
        ns = ConfigNamespace()
        ns.set("theme", "dark")
        assert ns.delete("theme") is True
        assert ns.get("theme") is None

    def test_delete_not_found(self):
        ns = ConfigNamespace()
        assert ns.delete("missing") is False

    def test_list(self):
        ns = ConfigNamespace()
        ns.set("a", 1)
        ns.set("b", 2)

        keys = ns.list()
        assert "a" in keys
        assert "b" in keys

    def test_exists(self):
        ns = ConfigNamespace()
        ns.set("a", 1)

        assert ns.exists("a") is True
        assert ns.exists("b") is False

    def test_registry_url(self):
        ns = ConfigNamespace()
        assert ns.get_registry_url() == "https://registry.tokenade.dev"

        ns.set_registry_url("https://custom.registry.dev")
        assert ns.get_registry_url() == "https://custom.registry.dev"

    def test_notification_settings(self):
        ns = ConfigNamespace()
        settings = ns.get_notification_settings()
        assert settings["enabled"] is True

        ns.set_notification_settings({"on_expiry": False})
        settings = ns.get_notification_settings()
        assert settings["on_expiry"] is False

    def test_scheduler_settings(self):
        ns = ConfigNamespace()
        settings = ns.get_scheduler_settings()
        assert settings["check_interval_minutes"] == 60

        ns.set_scheduler_settings({"check_interval_minutes": 30})
        settings = ns.get_scheduler_settings()
        assert settings["check_interval_minutes"] == 30

    def test_clear(self):
        ns = ConfigNamespace()
        ns.set("a", 1)
        ns.set("b", 2)
        count = ns.clear()
        assert count == 2
        assert ns.get("a") is None


class TestRuntimeNamespace:
    """Tests for RuntimeNamespace."""

    def test_active_proxy(self):
        ns = RuntimeNamespace()
        assert ns.get_active_proxy() is None

        ns.set_active_proxy({"host": "127.0.0.1", "port": 8080})
        proxy = ns.get_active_proxy()
        assert proxy["host"] == "127.0.0.1"
        assert proxy["port"] == 8080

    def test_clear_active_proxy(self):
        ns = RuntimeNamespace()
        ns.set_active_proxy({"host": "127.0.0.1"})
        ns.set_active_proxy(None)
        assert ns.get_active_proxy() is None

    def test_solved_captcha(self):
        ns = RuntimeNamespace()
        ns.set_solved_captcha("c1", {"type": "recaptcha", "solution": "abc"})

        solution = ns.get_solved_captcha("c1")
        assert solution is not None
        assert solution["type"] == "recaptcha"

    def test_solved_captcha_expiry(self):
        ns = RuntimeNamespace()
        # Set with 0 second TTL
        ns.set_solved_captcha("c1", {"solution": "abc"}, ttl_seconds=0)

        # Should be expired immediately
        time.sleep(0.01)
        solution = ns.get_solved_captcha("c1")
        assert solution is None

    def test_clear_expired_captchas(self):
        ns = RuntimeNamespace()
        ns.set_solved_captcha("c1", {"solution": "a"}, ttl_seconds=0)
        ns.set_solved_captcha("c2", {"solution": "b"}, ttl_seconds=300)

        time.sleep(0.01)
        removed = ns.clear_expired_captchas()
        assert removed == 1
        assert ns.get_solved_captcha("c1") is None
        assert ns.get_solved_captcha("c2") is not None

    def test_refresh_timestamp(self):
        ns = RuntimeNamespace()
        assert ns.get_refresh_timestamp("s1") is None

        now = datetime.now(timezone.utc)
        ns.set_refresh_timestamp("s1", now)
        assert ns.get_refresh_timestamp("s1") == now

    def test_clear_refresh_timestamp(self):
        ns = RuntimeNamespace()
        ns.set_refresh_timestamp("s1")
        assert ns.clear_refresh_timestamp("s1") is True
        assert ns.get_refresh_timestamp("s1") is None

    def test_task_refs(self):
        ns = RuntimeNamespace()
        ns.set_task_ref("t1", "my-plugin")
        assert ns.get_task_ref("t1") == "my-plugin"

        assert ns.clear_task_ref("t1") is True
        assert ns.get_task_ref("t1") is None

    def test_count_captchas(self):
        ns = RuntimeNamespace()
        ns.set_solved_captcha("c1", {"solution": "a"})
        ns.set_solved_captcha("c2", {"solution": "b"})
        assert ns.count_captchas() == 2


class TestSharedContext:
    """Tests for SharedContext singleton."""

    def test_singleton(self):
        SharedContext.reset()
        ctx1 = SharedContext()
        ctx2 = SharedContext()
        assert ctx1 is ctx2

    def test_namespaces(self):
        SharedContext.reset()
        ctx = SharedContext()

        assert isinstance(ctx.sessions, SessionsNamespace)
        assert isinstance(ctx.plugins, PluginsNamespace)
        assert isinstance(ctx.config, ConfigNamespace)
        assert isinstance(ctx.runtime, RuntimeNamespace)
        assert isinstance(ctx.tasks, TaskTracker)

    def test_get_namespace(self):
        SharedContext.reset()
        ctx = SharedContext()

        assert ctx.get_namespace("sessions") is ctx.sessions
        assert ctx.get_namespace("plugins") is ctx.plugins
        assert ctx.get_namespace("config") is ctx.config
        assert ctx.get_namespace("runtime") is ctx.runtime
        assert ctx.get_namespace("tasks") is ctx.tasks

    def test_get_namespace_not_found(self):
        SharedContext.reset()
        ctx = SharedContext()

        with pytest.raises(KeyError, match="not found"):
            ctx.get_namespace("nonexistent")

    def test_list_namespaces(self):
        SharedContext.reset()
        ctx = SharedContext()

        ns_list = ctx.list_namespaces()
        assert "sessions" in ns_list
        assert "plugins" in ns_list
        assert "config" in ns_list
        assert "runtime" in ns_list
        assert "tasks" in ns_list

    def test_reset(self):
        SharedContext.reset()
        ctx1 = SharedContext()
        SharedContext.reset()
        ctx2 = SharedContext()
        assert ctx1 is not ctx2
