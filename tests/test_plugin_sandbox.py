"""Tests for plugin sandbox."""
import json
import sys
import tempfile
import time
from pathlib import Path

import pytest

from tokenade.core.integration.plugin_sandbox import PluginSandbox, SandboxTimeout, SandboxDisabled


class TestPluginSandbox:
    """Unit tests for PluginSandbox."""

    @pytest.fixture
    def sandbox(self, tmp_path):
        disabled_file = tmp_path / ".sandbox_disabled"
        return PluginSandbox(max_failures=3, timeout=5.0, disabled_file=disabled_file)

    def test_execute_success(self, sandbox):
        success, result = sandbox.execute("test-plugin", lambda: 42)
        assert success
        assert result == 42

    def test_execute_failure(self, sandbox):
        def failing():
            raise ValueError("test error")

        success, error = sandbox.execute("test-plugin", failing)
        assert not success
        assert "test error" in str(error)

    def test_failure_tracking(self, sandbox):
        def failing():
            raise RuntimeError("boom")

        assert sandbox.get_failure_count("bad-plugin") == 0

        for i in range(3):
            sandbox.execute("bad-plugin", failing)
            assert sandbox.get_failure_count("bad-plugin") == i + 1

        assert sandbox.is_disabled("bad-plugin")
        assert "bad-plugin" in sandbox._disabled

    def test_auto_disable_threshold(self, sandbox):
        def failing():
            raise RuntimeError("boom")

        for i in range(3):
            sandbox.execute("auto-bad", failing)

        assert sandbox.is_disabled("auto-bad")
        assert sandbox.get_failure_count("auto-bad") == 3
        assert sandbox.get_last_error("auto-bad") is not None

    def test_disabled_blocks_execution(self, sandbox):
        def failing():
            raise RuntimeError("boom")

        for _ in range(3):
            sandbox.execute("blocked", failing)

        success, error = sandbox.execute("blocked", lambda: 42)
        assert not success
        assert isinstance(error, SandboxDisabled)

    def test_manual_enable(self, sandbox):
        def failing():
            raise RuntimeError("boom")

        for _ in range(3):
            sandbox.execute("revivable", failing)

        assert sandbox.is_disabled("revivable")
        sandbox.enable("revivable")
        assert not sandbox.is_disabled("revivable")
        assert sandbox.get_failure_count("revivable") == 0

    def test_manual_disable(self, sandbox):
        sandbox.disable("manual-block", "testing")
        assert sandbox.is_disabled("manual-block")

        success, error = sandbox.execute("manual-block", lambda: 42)
        assert not success

    def test_success_resets_failures(self, sandbox):
        def failing():
            raise RuntimeError("boom")

        sandbox.execute("resettable", failing)
        assert sandbox.get_failure_count("resettable") == 1

        sandbox.execute("resettable", lambda: 42)
        assert sandbox.get_failure_count("resettable") == 0

    def test_custom_max_failures(self, tmp_path):
        sandbox = PluginSandbox(max_failures=5, disabled_file=tmp_path / ".disabled")
        def failing():
            raise RuntimeError("boom")

        for i in range(4):
            sandbox.execute("custom", failing)
            assert not sandbox.is_disabled("custom")

        sandbox.execute("custom", failing)
        assert sandbox.is_disabled("custom")

    def test_get_state(self, sandbox):
        def failing():
            raise RuntimeError("boom")

        sandbox.execute("state-test", failing)
        state = sandbox.get_state()

        assert "config" in state
        assert state["config"]["max_failures"] == 3
        assert "failure_counts" in state
        assert state["failure_counts"]["state-test"] == 1

    def test_disabled_persistence(self, tmp_path):
        disabled_file = tmp_path / "sandbox_disabled.json"
        sandbox = PluginSandbox(max_failures=2, disabled_file=disabled_file)

        def failing():
            raise RuntimeError("boom")

        sandbox.execute("persistent", failing)
        sandbox.execute("persistent", failing)
        assert sandbox.is_disabled("persistent")

        # Create a new sandbox with same file — should load disabled state
        sandbox2 = PluginSandbox(max_failures=2, disabled_file=disabled_file)
        assert sandbox2.is_disabled("persistent")

    def test_decay_stale_failures(self, sandbox):
        def failing():
            raise RuntimeError("boom")

        sandbox.execute("decay-test", failing)
        assert sandbox.get_failure_count("decay-test") == 1

        # Artificially age the timestamp
        sandbox._failure_timestamps["decay-test"] = time.time() - sandbox.reset_after - 1
        sandbox._decay_failures()
        assert sandbox.get_failure_count("decay-test") == 0

    def test_verify_in_subprocess(self, sandbox, tmp_path):
        plugin_dir = tmp_path / "test_plugin"
        plugin_dir.mkdir()
        plugin_file = plugin_dir / "plugin.py"
        plugin_file.write_text("""
class TestPlugin:
    name = "test-sandbox-plugin"
    version = "1.0.0"
""")

        success, output = sandbox.verify_in_subprocess(plugin_file, timeout=10)
        assert success
        assert "success" in output.lower()

    def test_verify_in_subprocess_failure(self, sandbox, tmp_path):
        plugin_file = tmp_path / "bad_plugin.py"
        plugin_file.write_text("this is not valid python syntax !@#$%^")

        success, output = sandbox.verify_in_subprocess(plugin_file, timeout=10)
        assert not success

    def test_arguments_passed_through(self, sandbox):
        def adder(a, b):
            return a + b

        success, result = sandbox.execute("args-test", adder, 3, 4)
        assert success
        assert result == 7

    def test_kwargs_passed_through(self, sandbox):
        def kwarg_func(**kwargs):
            return kwargs

        success, result = sandbox.execute("kwargs-test", kwarg_func, x=1, y=2)
        assert success
        assert result == {"x": 1, "y": 2}
