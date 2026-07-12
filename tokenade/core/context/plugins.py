"""Plugins namespace for shared context.

Stores plugin registration info, config, and health status.
Thread-safe for concurrent access.
"""

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class PluginsNamespace:
    """Namespace for plugin-related shared state.

    Stores:
    - Plugin info (name, version, type, enabled, loaded_at)
    - Plugin config (plugin-specific dictionary)
    - Plugin health (boolean)

    Thread-safe: all operations are locked.

    Example:
        plugins = PluginsNamespace()
        plugins.register("my-plugin", {"version": "1.0.0", "type": "handler"})
        plugins.set_config("my-plugin", {"timeout": 30})
        plugins.set_health("my-plugin", True)
    """

    def __init__(self):
        self._plugins: Dict[str, Dict[str, Any]] = {}
        self._config: Dict[str, Dict[str, Any]] = {}
        self._health: Dict[str, bool] = {}
        self._lock = threading.RLock()

    def register(self, name: str, plugin_info: Dict[str, Any]) -> None:
        """Register a plugin.

        Args:
            name: Plugin identifier
            plugin_info: Plugin metadata (version, type, enabled, etc.)
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            self._plugins[name] = {
                "name": name,
                "version": plugin_info.get("version", "0.0.0"),
                "type": plugin_info.get("type", "unknown"),
                "enabled": plugin_info.get("enabled", True),
                "loaded_at": now,
                "metadata": plugin_info.get("metadata", {}),
            }

    def unregister(self, name: str) -> bool:
        """Unregister a plugin.

        Args:
            name: Plugin identifier

        Returns:
            True if unregistered, False if not found
        """
        with self._lock:
            deleted = name in self._plugins
            self._plugins.pop(name, None)
            self._config.pop(name, None)
            self._health.pop(name, None)
            return deleted

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        """Get plugin info.

        Args:
            name: Plugin identifier

        Returns:
            Plugin info dict, or None if not found
        """
        with self._lock:
            info = self._plugins.get(name)
            return dict(info) if info else None

    def list(self) -> List[str]:
        """List all registered plugin names.

        Returns:
            List of plugin identifiers
        """
        with self._lock:
            return list(self._plugins.keys())

    def is_loaded(self, name: str) -> bool:
        """Check if a plugin is registered.

        Args:
            name: Plugin identifier

        Returns:
            True if registered
        """
        with self._lock:
            return name in self._plugins

    def set_config(self, name: str, config: Dict[str, Any]) -> None:
        """Set plugin configuration.

        Args:
            name: Plugin identifier
            config: Configuration dict
        """
        with self._lock:
            self._config[name] = dict(config)

    def get_config(self, name: str) -> Dict[str, Any]:
        """Get plugin configuration.

        Args:
            name: Plugin identifier

        Returns:
            Configuration dict (empty if not set)
        """
        with self._lock:
            return dict(self._config.get(name, {}))

    def set_health(self, name: str, healthy: bool) -> None:
        """Set plugin health status.

        Args:
            name: Plugin identifier
            healthy: True if healthy, False if unhealthy
        """
        with self._lock:
            self._health[name] = healthy

    def get_health(self, name: str) -> Optional[bool]:
        """Get plugin health status.

        Args:
            name: Plugin identifier

        Returns:
            True if healthy, False if unhealthy, None if not set
        """
        with self._lock:
            return self._health.get(name)

    def set_version(self, name: str, version: str) -> None:
        """Update plugin version.

        Args:
            name: Plugin identifier
            version: New version string
        """
        with self._lock:
            if name in self._plugins:
                self._plugins[name]["version"] = version

    def get_version(self, name: str) -> Optional[str]:
        """Get plugin version.

        Args:
            name: Plugin identifier

        Returns:
            Version string, or None if not found
        """
        with self._lock:
            info = self._plugins.get(name)
            return info["version"] if info else None

    def count(self) -> int:
        """Get the number of registered plugins.

        Returns:
            Number of plugins
        """
        with self._lock:
            return len(self._plugins)
