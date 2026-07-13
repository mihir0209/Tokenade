"""
Plugin sandbox — isolate plugin execution for safety and reliability.

Design decisions:
- Full-trust in-process by default (matches project policy).
- Failure tracking with configurable auto-disable threshold.
- Timeout-based operation guards using signal.SIGALRM.
- Subprocess isolation for plugin verification/testing.
- All sandbox operations are best-effort — never crash the host.
"""

import logging
import os
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class SandboxTimeout(Exception):
    """Raised when a sandboxed operation exceeds its time limit."""


class SandboxDisabled(Exception):
    """Raised when a plugin is disabled by the sandbox."""


def _timeout_handler(signum, frame):
    raise SandboxTimeout("Plugin operation timed out")


class PluginSandbox:
    """Isolate plugin execution from the host application.

    Provides failure tracking, auto-disable, and timeout guards.
    All operations degrade gracefully — a plugin can never crash the host.

    Usage::

        sandbox = PluginSandbox(max_failures=3, timeout=30)
        loader = PluginLoader(sandbox=sandbox)

        # Manually wrap plugin calls:
        result = sandbox.execute("my-plugin", plugin.solve, captcha_type="recaptcha")
    """

    def __init__(
        self,
        max_failures: int = 3,
        timeout: float = 30.0,
        reset_after: float = 300.0,
        disabled_file: Optional[Path] = None,
    ):
        self.max_failures = max_failures
        self.timeout = timeout
        self.reset_after = reset_after

        self._failure_counts: Dict[str, int] = {}
        self._failure_timestamps: Dict[str, float] = {}
        self._last_errors: Dict[str, str] = {}
        self._disabled: Dict[str, str] = {}

        if disabled_file is None:
            disabled_file = Path.home() / ".tokenade" / "plugins" / ".sandbox_disabled"
        self._disabled_file = disabled_file

        self._load_disabled()

    # ── Core sandbox operations ─────────────────────────────────────────

    def execute(
        self,
        plugin_name: str,
        func: Callable,
        *args: Any,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> Tuple[bool, Any]:
        """Execute a plugin function with timeout and error isolation.

        Returns (success: bool, result_or_error).
        Never raises — all failures are caught and tracked.
        """
        if plugin_name in self._disabled:
            return (False, SandboxDisabled(
                f"Plugin {plugin_name} is sandbox-disabled: {self._disabled[plugin_name]}"
            ))

        effective_timeout = timeout if timeout is not None else self.timeout

        old_handler = signal.signal(signal.SIGALRM, _timeout_handler) if hasattr(signal, "SIGALRM") else None
        try:
            if old_handler is not None and effective_timeout > 0:
                signal.alarm(int(effective_timeout))

            result = func(*args, **kwargs)

            if old_handler is not None:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

            self._on_success(plugin_name)
            return (True, result)

        except SandboxTimeout as e:
            self._on_failure(plugin_name, str(e))
            return (False, e)

        except Exception as e:
            self._on_failure(plugin_name, str(e))
            return (False, e)

        finally:
            if old_handler is not None:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

    def verify_in_subprocess(
        self,
        plugin_path: Path,
        timeout: float = 10.0,
    ) -> Tuple[bool, str]:
        """Verify a plugin by importing it in a subprocess.

        Returns (success: bool, output_or_error: str).
        """
        python = sys.executable
        script = (
            "import importlib.util, sys, json, traceback\n"
            "try:\n"
            f"    spec = importlib.util.spec_from_file_location('plugin', {str(plugin_path)!r})\n"
            "    mod = importlib.util.module_from_spec(spec)\n"
            "    spec.loader.exec_module(mod)\n"
            "    print(json.dumps({'success': True, 'name': getattr(mod, '__name__', 'unknown')}))\n"
            "except Exception as e:\n"
            "    print(json.dumps({'success': False, 'error': str(e), 'traceback': traceback.format_exc()}))\n"
        )

        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = os.pathsep.join(sys.path)

            result = subprocess.run(
                [python, "-c", script],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=str(plugin_path.parent) if plugin_path.parent else None,
            )

            import json
            try:
                data = json.loads(result.stdout.strip() or "{}")
                return (data.get("success", False), result.stdout)
            except json.JSONDecodeError:
                return (False, result.stderr or result.stdout or "No output")

        except subprocess.TimeoutExpired:
            return (False, f"Verification timed out after {timeout}s")
        except Exception as e:
            return (False, str(e))

    # ── Failure tracking ────────────────────────────────────────────────

    def _on_success(self, plugin_name: str) -> None:
        if plugin_name in self._failure_counts:
            self._failure_counts[plugin_name] = 0
            self._failure_timestamps.pop(plugin_name, None)
            self._last_errors.pop(plugin_name, None)
            logger.info("Sandbox: %s failures reset", plugin_name)

    def _on_failure(self, plugin_name: str, error: str) -> None:
        count = self._failure_counts.get(plugin_name, 0) + 1
        self._failure_counts[plugin_name] = count
        self._failure_timestamps[plugin_name] = time.time()
        self._last_errors[plugin_name] = error

        logger.warning(
            "Sandbox: %s failure %d/%d: %s",
            plugin_name, count, self.max_failures, error[:120],
        )

        if count >= self.max_failures:
            self._disabled[plugin_name] = f"Auto-disabled after {count} failures: {error[:80]}"
            self._save_disabled()
            logger.error("Sandbox: %s auto-disabled", plugin_name)

    def _decay_failures(self) -> None:
        """Decay stale failure counts beyond reset_after."""
        now = time.time()
        stale = [
            name
            for name, ts in list(self._failure_timestamps.items())
            if now - ts > self.reset_after
        ]
        for name in stale:
            self._failure_counts.pop(name, None)
            self._failure_timestamps.pop(name, None)
            self._last_errors.pop(name, None)

    # ── Disabled list persistence ───────────────────────────────────────

    def _load_disabled(self) -> None:
        if self._disabled_file.exists():
            try:
                import json
                with open(self._disabled_file) as f:
                    self._disabled = json.load(f)
            except Exception:
                self._disabled = {}

    def _save_disabled(self) -> None:
        try:
            self._disabled_file.parent.mkdir(parents=True, exist_ok=True)
            import json
            with open(self._disabled_file, "w") as f:
                json.dump(self._disabled, f, indent=2)
        except Exception as e:
            logger.error("Failed to save sandbox disabled list: %s", e)

    # ── Public API ──────────────────────────────────────────────────────

    def is_disabled(self, plugin_name: str) -> bool:
        """Check if a plugin has been sandbox-disabled."""
        self._decay_failures()
        return plugin_name in self._disabled

    def get_failure_count(self, plugin_name: str) -> int:
        """Return current failure count for a plugin."""
        self._decay_failures()
        return self._failure_counts.get(plugin_name, 0)

    def get_last_error(self, plugin_name: str) -> Optional[str]:
        """Return the last error message for a plugin."""
        return self._last_errors.get(plugin_name)

    def enable(self, plugin_name: str) -> None:
        """Manually re-enable a sandbox-disabled plugin."""
        self._disabled.pop(plugin_name, None)
        self._failure_counts.pop(plugin_name, None)
        self._failure_timestamps.pop(plugin_name, None)
        self._last_errors.pop(plugin_name, None)
        self._save_disabled()

    def disable(self, plugin_name: str, reason: str = "Manually disabled") -> None:
        """Manually disable a plugin via sandbox."""
        self._disabled[plugin_name] = reason
        self._save_disabled()

    def get_state(self) -> Dict[str, Any]:
        """Return the current sandbox state for debugging."""
        self._decay_failures()
        return {
            "config": {
                "max_failures": self.max_failures,
                "timeout": self.timeout,
                "reset_after": self.reset_after,
            },
            "disabled": dict(self._disabled),
            "failure_counts": dict(self._failure_counts),
            "last_errors": dict(self._last_errors),
        }
