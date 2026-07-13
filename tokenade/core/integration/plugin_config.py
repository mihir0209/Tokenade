"""Plugin configuration manager.

Handles loading, saving, validating, and deleting plugin config files.
Config files are stored as JSON in `~/.tokenade/plugins/<name>/config.json`.

Schema is read from the plugin manifest (`plugin.json`) under `config.schema` key.
User config overrides are stored in `config.json` in the plugin directory.

Global settings from `~/.tokenade/config.json` under `plugins` key are
merged with plugin-specific config. Plugin-specific overrides global.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from tokenade.plugin.api import PluginConfig

logger = logging.getLogger(__name__)

DEFAULT_PLUGINS_DIR = Path.home() / ".tokenade" / "plugins"
GLOBAL_CONFIG_PATH = Path.home() / ".tokenade" / "config.json"


class PluginConfigManager:
    """Manages plugin configuration files.

    Example:
        mgr = PluginConfigManager()
        mgr.save_config("my-plugin", {"timeout": 60})
        config = mgr.load_config("my-plugin")
        errors = mgr.validate_config("my-plugin", config)
    """

    def __init__(
        self,
        plugins_dir: Path = DEFAULT_PLUGINS_DIR,
        global_config_path: Path = GLOBAL_CONFIG_PATH,
    ) -> None:
        self._plugins_dir = Path(plugins_dir)
        self._global_config_path = Path(global_config_path)

    def _get_plugin_dir(self, plugin_name: str) -> Path:
        return self._plugins_dir / plugin_name

    def _get_config_path(self, plugin_name: str) -> Path:
        return self._get_plugin_dir(plugin_name) / "config.json"

    def _get_manifest_path(self, plugin_name: str) -> Path:
        return self._get_plugin_dir(plugin_name) / "plugin.json"

    def has_config(self, plugin_name: str) -> bool:
        """Check if a plugin has a user config file.

        Args:
            plugin_name: Plugin name

        Returns:
            True if config.json exists
        """
        return self._get_config_path(plugin_name).exists()

    def load_config(self, plugin_name: str) -> Dict[str, Any]:
        """Load user config for a plugin.

        Returns empty dict if no config file exists.

        Args:
            plugin_name: Plugin name

        Returns:
            Config dict (values only)
        """
        path = self._get_config_path(plugin_name)
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load config for {plugin_name}: {e}")
            return {}

    def save_config(self, plugin_name: str, config: Dict[str, Any]) -> bool:
        """Save user config for a plugin.

        Validates config against schema before saving.
        Config is stored as JSON.

        Args:
            plugin_name: Plugin name
            config: Config values to save

        Returns:
            True if saved successfully, False otherwise
        """
        # Validate before saving
        errors = self.validate_config(plugin_name, config)
        if errors:
            logger.warning(
                f"Config for {plugin_name} has validation errors: {errors}"
            )

        path = self._get_config_path(plugin_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            return True
        except OSError as e:
            logger.error(f"Failed to save config for {plugin_name}: {e}")
            return False

    def delete_config(self, plugin_name: str) -> bool:
        """Delete user config for a plugin.

        Args:
            plugin_name: Plugin name

        Returns:
            True if deleted, False if not found
        """
        path = self._get_config_path(plugin_name)
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError as e:
            logger.error(f"Failed to delete config for {plugin_name}: {e}")
            return False

    def get_schema(self, plugin_name: str) -> Dict[str, Any]:
        """Get the config schema from the plugin manifest.

        Args:
            plugin_name: Plugin name

        Returns:
            Schema dict (empty if no schema)
        """
        manifest_path = self._get_manifest_path(plugin_name)
        if not manifest_path.exists():
            return {}
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            config_section = manifest.get("config", {})
            return config_section.get("schema", {})
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                f"Failed to read manifest for {plugin_name}: {e}"
            )
            return {}

    def get_defaults(self, plugin_name: str) -> Dict[str, Any]:
        """Get default config values from schema.

        Args:
            plugin_name: Plugin name

        Returns:
            Dict of default values
        """
        schema = self.get_schema(plugin_name)
        defaults = {}
        for key, spec in schema.items():
            if "default" in spec:
                defaults[key] = spec["default"]
        return defaults

    def validate_config(
        self, plugin_name: str, config: Dict[str, Any]
    ) -> List[str]:
        """Validate config against plugin's schema.

        Args:
            plugin_name: Plugin name
            config: Config values to validate

        Returns:
            List of error messages (empty if valid)
        """
        schema = self.get_schema(plugin_name)
        if not schema:
            return []  # No schema — anything is valid

        plugin_config = PluginConfig(schema=schema, values=config)
        return plugin_config.validate()

    def get_full_config(self, plugin_name: str) -> Dict[str, Any]:
        """Get merged config: defaults + global + user config.

        Order of precedence (later overrides earlier):
        1. Schema defaults
        2. Global config (from ~/.tokenade/config.json)
        3. User config (from plugin dir/config.json)

        Args:
            plugin_name: Plugin name

        Returns:
            Merged config dict
        """
        # 1. Schema defaults
        config = self.get_defaults(plugin_name)

        # 2. Global config
        global_config = self._load_global_plugin_config(plugin_name)
        config.update(global_config)

        # 3. User config (highest priority)
        user_config = self.load_config(plugin_name)
        config.update(user_config)

        return config

    def _load_global_config(self) -> Dict[str, Any]:
        """Load global config from ~/.tokenade/config.json.

        Returns:
            Global config dict (empty if not found)
        """
        if not self._global_config_path.exists():
            return {}
        try:
            with open(self._global_config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load global config: {e}")
            return {}

    def _load_global_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        """Load global config section for a specific plugin.

        Global config format:
            {
                "plugins": {
                    "my-plugin": {"timeout": 60}
                }
            }

        Args:
            plugin_name: Plugin name

        Returns:
            Plugin-specific global config (empty if not found)
        """
        global_config = self._load_global_config()
        plugins_section = global_config.get("plugins", {})
        return plugins_section.get(plugin_name, {})

    def save_global_config(self, global_config: Dict[str, Any]) -> bool:
        """Save global config.

        Args:
            global_config: Global config dict

        Returns:
            True if saved successfully
        """
        self._global_config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._global_config_path, "w", encoding="utf-8") as f:
                json.dump(global_config, f, indent=2)
            return True
        except OSError as e:
            logger.error(f"Failed to save global config: {e}")
            return False

    def set_global_plugin_config(
        self, plugin_name: str, config: Dict[str, Any]
    ) -> bool:
        """Set global config for a specific plugin.

        Args:
            plugin_name: Plugin name
            config: Plugin config to set globally

        Returns:
            True if saved successfully
        """
        global_config = self._load_global_config()
        if "plugins" not in global_config:
            global_config["plugins"] = {}
        global_config["plugins"][plugin_name] = config
        return self.save_global_config(global_config)
