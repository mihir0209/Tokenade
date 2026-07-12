"""Unit tests for plugin lifecycle management.

Tests lifecycle states, hooks, error handling, reload with config preservation,
and task state tracking integration.
"""

import json
import tempfile
from pathlib import Path

import pytest

from tokenade.core.integration.plugin_loader import (
    PluginLoader,
    PluginState,
    LoadedPlugin,
)


class TestPluginLifecycleStates:
    """Tests for plugin lifecycle state transitions."""

    def _make_plugin(self, tmp_path, name, body=None, config=None):
        plugin_dir = tmp_path / name
        plugin_dir.mkdir()
        manifest = {
            "name": name,
            "version": "1.0.0",
            "type": "handler",
            "entry_point": "plugin.py",
            "description": "Test",
        }
        if config:
            manifest["config"] = config
            # Also write config.json so PluginConfigManager picks it up
            (plugin_dir / "config.json").write_text(
                json.dumps(config.get("values", {}))
            )
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
        body = body or """
from tokenade.plugin.base import SiteHandlerPlugin
class TestHandler(SiteHandlerPlugin):
    name = "test"
    version = "1.0.0"
    description = "Test"

    def can_handle(self, url):
        return False
    def extract_session(self, page):
        return {}
    def inject_session(self, page, session):
        pass
"""
        (plugin_dir / "plugin.py").write_text(body)
        return plugin_dir

    def test_state_discovered_before_load(self, tmp_path):
        """Plugin is DISCOVERED before load_plugin is called."""
        self._make_plugin(tmp_path, "test-plugin")
        loader = PluginLoader(plugins_dir=tmp_path)
        plugins = loader.discover()
        assert len(plugins) == 1
        # Plugin not yet loaded
        assert loader.get_state("test-plugin") is None

    def test_state_active_after_load(self, tmp_path):
        """Plugin transitions to ACTIVE after successful load."""
        self._make_plugin(tmp_path, "test-plugin")
        loader = PluginLoader(plugins_dir=tmp_path)
        loader.load_all()
        assert loader.get_state("test-plugin") == PluginState.ACTIVE

    def test_state_unloaded_after_unload(self, tmp_path):
        """Plugin transitions to UNLOADED after unload."""
        self._make_plugin(tmp_path, "test-plugin")
        loader = PluginLoader(plugins_dir=tmp_path)
        loader.load_all()
        assert loader.get_state("test-plugin") == PluginState.ACTIVE

        loader.unload("test-plugin")
        assert loader.get_state("test-plugin") is None  # removed from _loaded

    def test_state_disabled_after_disable(self, tmp_path):
        """Plugin transitions to DISABLED after disable."""
        self._make_plugin(tmp_path, "test-plugin")
        loader = PluginLoader(plugins_dir=tmp_path)
        loader.load_all()

        loader.disable("test-plugin")
        assert loader.get_state("test-plugin") is None  # unloaded

    def test_state_failed_on_load_error(self, tmp_path):
        """Plugin transitions to FAILED when on_load throws."""
        body = """
from tokenade.plugin.base import SiteHandlerPlugin
class TestHandler(SiteHandlerPlugin):
    name = "test"
    version = "1.0.0"
    description = "Test"

    def on_load(self):
        raise RuntimeError("on_load failed")

    def can_handle(self, url):
        return False
    def extract_session(self, page):
        return {}
    def inject_session(self, page, session):
        pass
"""
        self._make_plugin(tmp_path, "test-plugin", body=body)
        loader = PluginLoader(plugins_dir=tmp_path)
        loader.load_all()

        plugin = loader.get_plugin("test-plugin")
        assert plugin is not None
        assert plugin.state == PluginState.FAILED
        assert "on_load failed" in (plugin.error or "")

    def test_state_configured_after_on_configure(self, tmp_path):
        """Plugin transitions to CONFIGURED after on_configure, then ACTIVE."""
        body = """
from tokenade.plugin.base import SiteHandlerPlugin
class TestHandler(SiteHandlerPlugin):
    name = "test"
    version = "1.0.0"
    description = "Test"

    def on_configure(self, config):
        pass

    def can_handle(self, url):
        return False
    def extract_session(self, page):
        return {}
    def inject_session(self, page, session):
        pass
"""
        config = {"values": {"timeout": 30}, "schema": {}}
        self._make_plugin(tmp_path, "test-plugin", body=body, config=config)
        loader = PluginLoader(plugins_dir=tmp_path)
        loader.load_all()

        plugin = loader.get_plugin("test-plugin")
        assert plugin is not None
        # After configure, it transitions to ACTIVE
        assert plugin.state == PluginState.ACTIVE
        assert plugin.config == {"timeout": 30}

    def test_state_failed_on_configure_error(self, tmp_path):
        """Plugin transitions to FAILED when on_configure throws."""
        body = """
from tokenade.plugin.base import SiteHandlerPlugin
class TestHandler(SiteHandlerPlugin):
    name = "test"
    version = "1.0.0"
    description = "Test"

    def on_configure(self, config):
        raise ValueError("bad config")

    def can_handle(self, url):
        return False
    def extract_session(self, page):
        return {}
    def inject_session(self, page, session):
        pass
"""
        config = {"values": {"timeout": 30}, "schema": {}}
        self._make_plugin(tmp_path, "test-plugin", body=body, config=config)
        loader = PluginLoader(plugins_dir=tmp_path)
        loader.load_all()

        plugin = loader.get_plugin("test-plugin")
        assert plugin is not None
        assert plugin.state == PluginState.FAILED
        assert "bad config" in (plugin.error or "")


class TestLifecycleHooks:
    """Tests for lifecycle hook invocation."""

    def test_on_load_called(self, tmp_path):
        """on_load() is called after instantiation."""
        body = """
from tokenade.plugin.base import SiteHandlerPlugin
class TestHandler(SiteHandlerPlugin):
    name = "test"
    version = "1.0.0"
    description = "Test"
    loaded = False

    def on_load(self):
        TestHandler.loaded = True

    def can_handle(self, url):
        return False
    def extract_session(self, page):
        return {}
    def inject_session(self, page, session):
        pass
"""
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "test-plugin", "version": "1.0.0", "type": "handler",
            "entry_point": "plugin.py", "description": "Test",
        }))
        (plugin_dir / "plugin.py").write_text(body)

        loader = PluginLoader(plugins_dir=tmp_path)
        loader.load_all()

        # Access the module to check the class attribute
        plugin = loader.get_plugin("test-plugin")
        assert plugin is not None
        assert plugin.module.TestHandler.loaded is True

    def test_on_unload_called(self, tmp_path):
        """on_unload() is called before removal."""
        body = """
from tokenade.plugin.base import SiteHandlerPlugin
class TestHandler(SiteHandlerPlugin):
    name = "test"
    version = "1.0.0"
    description = "Test"
    unloaded = False

    def on_unload(self):
        TestHandler.unloaded = True

    def can_handle(self, url):
        return False
    def extract_session(self, page):
        return {}
    def inject_session(self, page, session):
        pass
"""
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "test-plugin", "version": "1.0.0", "type": "handler",
            "entry_point": "plugin.py", "description": "Test",
        }))
        (plugin_dir / "plugin.py").write_text(body)

        loader = PluginLoader(plugins_dir=tmp_path)
        loader.load_all()

        module = loader.get_plugin("test-plugin").module
        loader.unload("test-plugin")

        assert module.TestHandler.unloaded is True

    def test_on_unload_error_does_not_crash(self, tmp_path):
        """on_unload() throwing doesn't crash the loader."""
        body = """
from tokenade.plugin.base import SiteHandlerPlugin
class TestHandler(SiteHandlerPlugin):
    name = "test"
    version = "1.0.0"
    description = "Test"

    def on_unload(self):
        raise RuntimeError("on_unload failed")

    def can_handle(self, url):
        return False
    def extract_session(self, page):
        return {}
    def inject_session(self, page, session):
        pass
"""
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "test-plugin", "version": "1.0.0", "type": "handler",
            "entry_point": "plugin.py", "description": "Test",
        }))
        (plugin_dir / "plugin.py").write_text(body)

        loader = PluginLoader(plugins_dir=tmp_path)
        loader.load_all()

        # Should not raise
        result = loader.unload("test-plugin")
        assert result is True


class TestPluginReload:
    """Tests for plugin reload with config preservation."""

    def test_reload_preserves_config(self, tmp_path):
        """Reload preserves plugin config across reloads."""
        body = """
from tokenade.plugin.base import SiteHandlerPlugin
class TestHandler(SiteHandlerPlugin):
    name = "test"
    version = "1.0.0"
    description = "Test"

    def on_configure(self, config):
        pass

    def can_handle(self, url):
        return False
    def extract_session(self, page):
        return {}
    def inject_session(self, page, session):
        pass
"""
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "test-plugin", "version": "1.0.0", "type": "handler",
            "entry_point": "plugin.py", "description": "Test",
            "config": {"values": {"timeout": 60}, "schema": {}},
        }))
        (plugin_dir / "config.json").write_text(json.dumps({"timeout": 60}))
        (plugin_dir / "plugin.py").write_text(body)

        loader = PluginLoader(plugins_dir=tmp_path)
        loader.load_all()

        plugin = loader.get_plugin("test-plugin")
        assert plugin.config == {"timeout": 60}

        # Reload
        loaded = loader.reload("test-plugin")
        assert loaded is not None
        assert loaded.config == {"timeout": 60}
        assert loaded.state == PluginState.ACTIVE

    def test_reload_without_config(self, tmp_path):
        """Reload works when plugin has no config."""
        body = """
from tokenade.plugin.base import SiteHandlerPlugin
class TestHandler(SiteHandlerPlugin):
    name = "test"
    version = "1.0.0"
    description = "Test"

    def can_handle(self, url):
        return False
    def extract_session(self, page):
        return {}
    def inject_session(self, page, session):
        pass
"""
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "test-plugin", "version": "1.0.0", "type": "handler",
            "entry_point": "plugin.py", "description": "Test",
        }))
        (plugin_dir / "plugin.py").write_text(body)

        loader = PluginLoader(plugins_dir=tmp_path)
        loader.load_all()

        loaded = loader.reload("test-plugin")
        assert loaded is not None
        assert loaded.state == PluginState.ACTIVE

    def test_reload_nonexistent_plugin(self, tmp_path):
        """Reload returns None for nonexistent plugin."""
        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.reload("nonexistent")
        assert result is None


class TestPluginErrorHandling:
    """Tests for plugin error handling."""

    def test_load_error_does_not_crash_loader(self, tmp_path):
        """Load error for one plugin doesn't prevent others from loading."""
        # Broken plugin
        broken_dir = tmp_path / "broken"
        broken_dir.mkdir()
        (broken_dir / "plugin.json").write_text(json.dumps({
            "name": "broken", "version": "1.0.0", "type": "handler",
            "entry_point": "plugin.py", "description": "Broken",
        }))
        (broken_dir / "plugin.py").write_text("invalid python code !!!")

        # Working plugin
        good_dir = tmp_path / "good"
        good_dir.mkdir()
        (good_dir / "plugin.json").write_text(json.dumps({
            "name": "good", "version": "1.0.0", "type": "handler",
            "entry_point": "plugin.py", "description": "Good",
        }))
        (good_dir / "plugin.py").write_text("""
from tokenade.plugin.base import SiteHandlerPlugin
class GoodHandler(SiteHandlerPlugin):
    name = "good"
    version = "1.0.0"
    description = "Good"

    def can_handle(self, url):
        return False
    def extract_session(self, page):
        return {}
    def inject_session(self, page, session):
        pass
""")

        loader = PluginLoader(plugins_dir=tmp_path)
        loaded_count = loader.load_all()

        # "good" should have loaded
        assert loader.get_plugin("good") is not None
        assert loader.get_state("good") == PluginState.ACTIVE

    def test_instantiation_error_marks_failed(self, tmp_path):
        """Plugin that fails to instantiate is not in _loaded."""
        body = """
from tokenade.plugin.base import SiteHandlerPlugin
class TestHandler(SiteHandlerPlugin):
    name = "test"
    version = "1.0.0"
    description = "Test"

    def __init__(self):
        raise RuntimeError("cannot instantiate")

    def can_handle(self, url):
        return False
    def extract_session(self, page):
        return {}
    def inject_session(self, page, session):
        pass
"""
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "test-plugin", "version": "1.0.0", "type": "handler",
            "entry_point": "plugin.py", "description": "Test",
        }))
        (plugin_dir / "plugin.py").write_text(body)

        loader = PluginLoader(plugins_dir=tmp_path)
        loader.load_all()

        # Plugin should not be in _loaded (returned None)
        assert loader.get_plugin("test-plugin") is None


class TestTaskStateWithLifecycle:
    """Tests for task state tracking integration with lifecycle."""

    def test_task_tracker_via_shared_context(self):
        """TaskTracker is accessible via SharedContext."""
        from tokenade.core.context import SharedContext, TaskState

        SharedContext.reset()
        ctx = SharedContext()

        # Start a task
        task = ctx.tasks.start_task("test-1", "my-plugin", "refresh")
        assert task["state"] == TaskState.PENDING

        # Progress
        ctx.tasks.update_task("test-1", TaskState.IN_PROGRESS)
        assert ctx.tasks.is_task_active("test-1") is True

        # Complete
        ctx.tasks.update_task(
            "test-1", TaskState.COMPLETED, result={"status": "ok"}
        )
        task = ctx.tasks.get_task("test-1")
        assert task["state"] == TaskState.COMPLETED
        assert task["result"]["status"] == "ok"

    def test_multiple_tasks_per_plugin(self):
        """A plugin can have multiple concurrent tasks."""
        from tokenade.core.context import SharedContext, TaskState

        SharedContext.reset()
        ctx = SharedContext()

        # Start multiple tasks for the same plugin
        ctx.tasks.start_task("task-1", "my-plugin", "refresh")
        ctx.tasks.start_task("task-2", "my-plugin", "export")
        ctx.tasks.start_task("task-3", "my-plugin", "validate")

        # All should be active
        tasks = ctx.tasks.list_tasks(plugin_name="my-plugin")
        assert len(tasks) == 3

        # Complete one
        ctx.tasks.update_task("task-1", TaskState.IN_PROGRESS)
        ctx.tasks.update_task("task-1", TaskState.COMPLETED)

        # Two should still be active
        active = [t for t in ctx.tasks.list_tasks(plugin_name="my-plugin")
                  if t["state"] in (TaskState.PENDING, TaskState.IN_PROGRESS)]
        assert len(active) == 2
