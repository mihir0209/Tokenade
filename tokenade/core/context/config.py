"""Config namespace for shared context.

Stores user preferences, registry URL, notification settings,
and scheduler settings.
Thread-safe for concurrent access.
"""

import threading
from typing import Any, Dict, List, Optional


class ConfigNamespace:
    """Namespace for configuration-related shared state.

    Stores:
    - Registry URL
    - Notification settings
    - Scheduler settings
    - General config keys

    Thread-safe: all operations are locked.

    Example:
        config = ConfigNamespace()
        config.set_registry_url("https://registry.tokenade.dev")
        config.set("theme", "dark")
        url = config.get_registry_url()
    """

    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._registry_url: str = "https://registry.tokenade.dev"
        self._notification_settings: Dict[str, Any] = {
            "enabled": True,
            "on_expiry": True,
            "on_failure": True,
            "on_success": False,
        }
        self._scheduler_settings: Dict[str, Any] = {
            "enabled": True,
            "check_interval_minutes": 60,
            "health_check_interval_minutes": 30,
        }
        self._lock = threading.RLock()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value.

        Args:
            key: Config key
            default: Default value if key not found

        Returns:
            Config value, or default
        """
        with self._lock:
            return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a config value.

        Args:
            key: Config key
            value: Config value
        """
        with self._lock:
            self._config[key] = value

    def delete(self, key: str) -> bool:
        """Delete a config value.

        Args:
            key: Config key

        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            deleted = key in self._config
            self._config.pop(key, None)
            return deleted

    def list(self) -> List[str]:
        """List all config keys.

        Returns:
            List of config keys
        """
        with self._lock:
            return list(self._config.keys())

    def exists(self, key: str) -> bool:
        """Check if a config key exists.

        Args:
            key: Config key

        Returns:
            True if key exists
        """
        with self._lock:
            return key in self._config

    def get_registry_url(self) -> str:
        """Get the plugin registry URL.

        Returns:
            Registry URL
        """
        with self._lock:
            return self._registry_url

    def set_registry_url(self, url: str) -> None:
        """Set the plugin registry URL.

        Args:
            url: New registry URL
        """
        with self._lock:
            self._registry_url = url

    def get_notification_settings(self) -> Dict[str, Any]:
        """Get notification settings.

        Returns:
            Notification settings dict
        """
        with self._lock:
            return dict(self._notification_settings)

    def set_notification_settings(self, settings: Dict[str, Any]) -> None:
        """Set notification settings.

        Args:
            settings: Notification settings dict
        """
        with self._lock:
            self._notification_settings.update(settings)

    def get_scheduler_settings(self) -> Dict[str, Any]:
        """Get scheduler settings.

        Returns:
            Scheduler settings dict
        """
        with self._lock:
            return dict(self._scheduler_settings)

    def set_scheduler_settings(self, settings: Dict[str, Any]) -> None:
        """Set scheduler settings.

        Args:
            settings: Scheduler settings dict
        """
        with self._lock:
            self._scheduler_settings.update(settings)

    def clear(self) -> int:
        """Clear all custom config values (keeps system defaults).

        Returns:
            Number of keys removed
        """
        with self._lock:
            count = len(self._config)
            self._config.clear()
            return count
