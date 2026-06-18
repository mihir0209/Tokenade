"""
Plugin loader for Tokenade.

Discovers, loads, and executes plugins from ~/.tokenade/plugins/.
Plugins can be site handlers, export formats, or validation rules.
"""
import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DEFAULT_PLUGINS_DIR = Path.home() / ".tokenade" / "plugins"


@dataclass
class LoadedPlugin:
    """A loaded plugin with its module and metadata."""
    name: str
    version: str
    description: str
    plugin_type: str
    module: Any
    entry_class: Any
    instance: Any = None
    enabled: bool = True


class PluginLoader:
    """Discover, load, and manage plugins."""

    def __init__(self, plugins_dir: Path = DEFAULT_PLUGINS_DIR):
        self.plugins_dir = plugins_dir
        self._loaded: Dict[str, LoadedPlugin] = {}
        self._handlers: Dict[str, Any] = {}
        self._exporters: Dict[str, Any] = {}
        self._validators: Dict[str, Any] = {}
        self._disabled: set = set()
        self._load_disabled_list()

    def discover(self) -> List[Dict]:
        """Discover all installed plugins."""
        plugins = []
        if not self.plugins_dir.exists():
            return plugins

        for plugin_dir in sorted(self.plugins_dir.iterdir()):
            if not plugin_dir.is_dir() or plugin_dir.name.startswith("."):
                continue

            manifest_path = plugin_dir / "plugin.json"
            if not manifest_path.exists():
                continue

            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                meta["_path"] = str(plugin_dir)
                plugins.append(meta)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read plugin manifest {manifest_path}: {e}")

        return plugins

    def load_all(self) -> int:
        """Load all discovered plugins. Returns count loaded."""
        plugins = self.discover()
        loaded = 0

        for meta in plugins:
            name = meta.get("name", "")
            if name in self._disabled:
                logger.debug(f"Skipping disabled plugin: {name}")
                continue
            try:
                result = self.load_plugin(meta)
                if result is not None:
                    loaded += 1
            except Exception as e:
                logger.error(f"Failed to load plugin {name}: {e}", exc_info=True)

        logger.info(f"Loaded {loaded}/{len(plugins)} plugins")
        return loaded

    def load_plugin(self, meta: Dict) -> Optional[LoadedPlugin]:
        """Load a single plugin from its manifest."""
        name = meta.get("name", "")
        if name in self._loaded:
            return self._loaded[name]

        plugin_dir = Path(meta.get("_path", self.plugins_dir / name))
        entry_point = meta.get("entry_point", "")
        plugin_type = meta.get("type", "handler")

        if not entry_point:
            logger.error(f"Plugin {name} has no entry_point")
            return None

        # Load the module
        module_path = plugin_dir / entry_point
        if not module_path.exists():
            logger.error(f"Plugin {name} entry point not found: {module_path}")
            return None

        try:
            spec = importlib.util.spec_from_file_location(
                f"tokenade_plugin_{name}",
                str(module_path),
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error(f"Failed to import plugin {name}: {e}", exc_info=True)
            return None

        # Find the entry class
        entry_class_name = meta.get("entry_class", "")
        entry_class = None

        if entry_class_name:
            entry_class = getattr(module, entry_class_name, None)
        else:
            # Auto-discover: look for class that matches plugin type
            type_class_map = {
                "handler": "SiteHandler",
                "export_format": "ExportFormat",
                "validator": "SessionValidator",
            }
            target_name = type_class_map.get(plugin_type, "")
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and attr_name == target_name:
                    entry_class = attr
                    break

        if not entry_class:
            logger.error(f"Plugin {name}: no entry class found")
            return None

        # Instantiate
        try:
            instance = entry_class()
        except Exception as e:
            logger.error(f"Plugin {name}: failed to instantiate: {e}", exc_info=True)
            return None

        loaded = LoadedPlugin(
            name=name,
            version=meta.get("version", "0.0.0"),
            description=meta.get("description", ""),
            plugin_type=plugin_type,
            module=module,
            entry_class=entry_class,
            instance=instance,
        )

        self._loaded[name] = loaded

        # Register by type
        if plugin_type == "handler":
            site_name = meta.get("site_name", name)
            self._handlers[site_name] = instance
        elif plugin_type == "export_format":
            format_name = meta.get("format_name", name)
            self._exporters[format_name] = instance
        elif plugin_type == "validator":
            rule_name = meta.get("rule_name", name)
            self._validators[rule_name] = instance

        logger.info(f"Loaded plugin: {name} v{loaded.version} ({plugin_type})")
        return loaded

    def unload(self, name: str) -> bool:
        """Unload a plugin."""
        if name not in self._loaded:
            return False

        plugin = self._loaded.pop(name)

        # Remove from type registries
        if plugin.plugin_type == "handler":
            self._handlers = {k: v for k, v in self._handlers.items() if v is not plugin.instance}
        elif plugin.plugin_type == "export_format":
            self._exporters = {k: v for k, v in self._exporters.items() if v is not plugin.instance}
        elif plugin.plugin_type == "validator":
            self._validators = {k: v for k, v in self._validators.items() if v is not plugin.instance}

        logger.info(f"Unloaded plugin: {name}")
        return True

    def get_handler(self, site_name: str) -> Optional[Any]:
        """Get a site handler plugin by name."""
        return self._handlers.get(site_name)

    def get_exporter(self, format_name: str) -> Optional[Any]:
        """Get an export format plugin by name."""
        return self._exporters.get(format_name)

    def get_validator(self, rule_name: str) -> Optional[Any]:
        """Get a validator plugin by name."""
        return self._validators.get(rule_name)

    def list_handlers(self) -> Dict[str, Any]:
        """List all loaded handler plugins."""
        return dict(self._handlers)

    def list_exporters(self) -> Dict[str, Any]:
        """List all loaded exporter plugins."""
        return dict(self._exporters)

    def list_validators(self) -> Dict[str, Any]:
        """List all loaded validator plugins."""
        return dict(self._validators)

    def list_all(self) -> List[LoadedPlugin]:
        """List all loaded plugins."""
        return list(self._loaded.values())

    def reload(self, name: str) -> Optional[LoadedPlugin]:
        """Reload a plugin."""
        self.unload(name)

        manifest_path = self.plugins_dir / name / "plugin.json"
        if not manifest_path.exists():
            return None

        with open(manifest_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        meta["_path"] = str(self.plugins_dir / name)

        return self.load_plugin(meta)

    def _load_disabled_list(self):
        """Load the list of disabled plugins."""
        disabled_file = self.plugins_dir / ".disabled"
        if disabled_file.exists():
            try:
                with open(disabled_file, "r") as f:
                    self._disabled = set(line.strip() for line in f if line.strip())
            except Exception:
                self._disabled = set()

    def _save_disabled_list(self):
        """Save the list of disabled plugins."""
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        disabled_file = self.plugins_dir / ".disabled"
        with open(disabled_file, "w") as f:
            for name in sorted(self._disabled):
                f.write(f"{name}\n")

    def enable(self, name: str) -> bool:
        """Enable a disabled plugin."""
        if name not in self._disabled:
            return True
        self._disabled.discard(name)
        self._save_disabled_list()
        # Reload if already loaded
        if name in self._loaded:
            self._loaded[name].enabled = True
        logger.info(f"Plugin enabled: {name}")
        return True

    def disable(self, name: str) -> bool:
        """Disable a plugin without uninstalling."""
        if name not in self._loaded and name not in self.discover_names():
            return False
        self._disabled.add(name)
        self._save_disabled_list()
        # Unload if currently loaded
        if name in self._loaded:
            self._loaded[name].enabled = False
            self.unload(name)
        logger.info(f"Plugin disabled: {name}")
        return True

    def discover_names(self) -> set:
        """Get names of all discovered plugins."""
        names = set()
        for meta in self.discover():
            names.add(meta.get("name", ""))
        return names
