"""Shared context for the Tokenade ecosystem.

Core owns it. Plugins read/write through provided API.
4 namespaces: Sessions, Plugins, Config, Runtime.

Thread-safe singleton — one instance per application.
"""

import threading
from typing import List, Optional

from tokenade.core.context.config import ConfigNamespace
from tokenade.core.context.plugins import PluginsNamespace
from tokenade.core.context.runtime import RuntimeNamespace
from tokenade.core.context.sessions import SessionsNamespace
from tokenade.core.context.tasks import TaskTracker


class SharedContext:
    """Shared context for core ↔ plugin communication.

    Core creates and manages the context. Plugins access it through
    the provided namespace APIs. Thread-safe singleton.

    Namespaces:
    - sessions: Session data, health scores, metadata
    - plugins: Plugin registration, config, health
    - config: User preferences, registry URL, settings
    - runtime: Active proxy, solved CAPTCHAs, timestamps

    Example:
        ctx = SharedContext()
        ctx.sessions.set("s1", {"cookies": {...}})
        ctx.config.set_registry_url("https://registry.dev")
        proxy = ctx.runtime.get_active_proxy()
    """

    _instance: Optional["SharedContext"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "SharedContext":
        """Singleton pattern — one instance per application."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self):
        """Initialize the shared context (once only)."""
        if self._initialized:
            return
        self._initialized = True

        self._sessions = SessionsNamespace()
        self._plugins = PluginsNamespace()
        self._config = ConfigNamespace()
        self._runtime = RuntimeNamespace()
        self._tasks = TaskTracker()

    @property
    def sessions(self) -> SessionsNamespace:
        """Access the sessions namespace."""
        return self._sessions

    @property
    def plugins(self) -> PluginsNamespace:
        """Access the plugins namespace."""
        return self._plugins

    @property
    def config(self) -> ConfigNamespace:
        """Access the config namespace."""
        return self._config

    @property
    def runtime(self) -> RuntimeNamespace:
        """Access the runtime namespace."""
        return self._runtime

    @property
    def tasks(self) -> TaskTracker:
        """Access the task tracker."""
        return self._tasks

    def get_namespace(self, name: str):
        """Get a namespace by name.

        Args:
            name: Namespace name ("sessions", "plugins", "config", "runtime")

        Returns:
            The namespace instance

        Raises:
            KeyError: If namespace not found
        """
        namespaces = {
            "sessions": self._sessions,
            "plugins": self._plugins,
            "config": self._config,
            "runtime": self._runtime,
            "tasks": self._tasks,
        }
        ns = namespaces.get(name)
        if ns is None:
            raise KeyError(f"Namespace '{name}' not found")
        return ns

    def list_namespaces(self) -> List[str]:
        """List all available namespace names.

        Returns:
            List of namespace names
        """
        return ["sessions", "plugins", "config", "runtime", "tasks"]

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing only).

        WARNING: Only call in tests. This destroys the shared context.
        """
        with cls._instance_lock:
            cls._instance = None
