"""
Plugin loader for Tokenade.

Discovers, loads, and executes plugins from ~/.tokenade/plugins/.
Plugins can be site handlers, export formats, or validation rules.

Emits events through the core event bus:
- PLUGIN_LOADED: When a plugin is successfully loaded
- PLUGIN_UNLOADED: When a plugin is unloaded
- PLUGIN_ERROR: When a plugin fails to load

Integrates with shared context for plugin registration and health.

Plugin lifecycle states:
  DISCOVERED → LOADED → CONFIGURED → ACTIVE → DISABLED → UNLOADED
                     ↓
                   FAILED
"""
import enum
import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class PluginState(enum.Enum):
    """Lifecycle states for a plugin."""

    DISCOVERED = "discovered"
    LOADED = "loaded"
    CONFIGURED = "configured"
    ACTIVE = "active"
    DISABLED = "disabled"
    UNLOADED = "unloaded"
    FAILED = "failed"


# Module-level event bus instance for plugin loader events.
# Initialized lazily to avoid import issues.
_event_bus = None


def _get_event_bus() -> Any:
    """Get or create the module-level event bus.

    Returns None if the event bus module is not available (graceful degradation).
    """
    global _event_bus
    if _event_bus is None:
        try:
            from tokenade.core.events.bus import EventBus
            _event_bus = EventBus()
        except ImportError:
            logger.debug("Event bus not available — plugin events disabled")
            return None
    return _event_bus


def _get_shared_context() -> Any:
    """Get the shared context singleton.

    Returns None if the context module is not available (graceful degradation).
    """
    try:
        from tokenade.core.context import SharedContext
        return SharedContext()
    except ImportError:
        logger.debug("Shared context not available — context integration disabled")
        return None


def _emit_event(event_type_name: str, data: dict, source: str = "plugin_loader") -> None:
    """Emit an event through the event bus (graceful, no-op if unavailable)."""
    bus = _get_event_bus()
    if bus is None:
        return
    try:
        from tokenade.core.events.types import EventType
        event_type = getattr(EventType, event_type_name, None)
        if event_type is not None:
            bus.emit(event_type, data=data, source=source)
    except Exception as e:
        logger.debug(f"Failed to emit {event_type_name} event: {e}")


DEFAULT_PLUGINS_DIR = Path.home() / ".tokenade" / "plugins"

# Optional process-wide loader for site_config discovery (set by CLI on first use).
_shared_loader: Optional["PluginLoader"] = None


def get_shared_loader() -> Optional["PluginLoader"]:
    """Return the process-wide PluginLoader if one was registered."""
    return _shared_loader


def set_shared_loader(loader: Optional["PluginLoader"]) -> None:
    """Register a process-wide PluginLoader (CLI / daemon)."""
    global _shared_loader
    _shared_loader = loader


def get_or_create_shared_loader(plugins_dir: Path = DEFAULT_PLUGINS_DIR) -> "PluginLoader":
    """Return shared loader, creating and loading plugins if needed."""
    global _shared_loader
    if _shared_loader is None:
        _shared_loader = PluginLoader(plugins_dir)
        try:
            _shared_loader.load_all()
        except Exception as e:
            logger.debug("Shared plugin load failed: %s", e)
    return _shared_loader


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
    state: PluginState = PluginState.DISCOVERED
    config: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def is_active(self) -> bool:
        return self.state == PluginState.ACTIVE


class PluginLoader:
    """Discover, load, and manage plugins."""

    def __init__(self, plugins_dir: Path = DEFAULT_PLUGINS_DIR, sandbox: Any = None, lazy: bool = False) -> None:
        self.plugins_dir = plugins_dir
        self.sandbox = sandbox
        self.lazy = lazy
        self._loaded: Dict[str, LoadedPlugin] = {}
        self._handlers: Dict[str, Any] = {}
        self._exporters: Dict[str, Any] = {}
        self._validators: Dict[str, Any] = {}
        self._refreshers: Dict[str, Any] = {}
        self._stealths: Dict[str, Any] = {}
        self._proxies: Dict[str, Any] = {}
        self._captchas: Dict[str, Any] = {}
        self._notifications: Dict[str, Any] = {}
        self._challenge_detectors: Dict[str, Any] = {}
        self._challenge_solvers: Dict[str, Any] = {}
        self._egress_providers: Dict[str, Any] = {}
        self._fingerprint_oracles: Dict[str, Any] = {}
        self._disabled: set = set()
        self._discovery_cache: Optional[List[Dict]] = None
        self._discovery_cache_time: float = 0.0
        self._cache_ttl: float = 60.0  # Cache discovery for 60s
        self._load_disabled_list()

    def discover(self, use_cache: bool = True) -> List[Dict]:
        """Discover all installed plugins.
        
        Args:
            use_cache: If True, return cached results if available and fresh.
        """
        import time as _time

        # Return cache if fresh
        if use_cache and self._discovery_cache is not None:
            age = _time.time() - self._discovery_cache_time
            if age < self._cache_ttl:
                logger.debug("Using cached plugin discovery (age: %.1fs)", age)
                return self._discovery_cache

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

        # Update cache
        self._discovery_cache = plugins
        self._discovery_cache_time = _time.time()

        return plugins

    def get_manifest(self, name: str) -> Optional[Dict]:
        """Read one installed plugin manifest without scanning all plugins.

        Looks up ``~/.tokenade/plugins/<name>/plugin.json`` (or this loader's
        plugins_dir). Returns None if the plugin is not installed.
        """
        plugin_dir = self.plugins_dir / name
        manifest_path = plugin_dir / "plugin.json"
        if not manifest_path.is_file():
            return None
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            meta["_path"] = str(plugin_dir)
            return meta
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read plugin manifest %s: %s", manifest_path, e)
            return None

    def _dependencies_of(self, meta: Dict) -> List[str]:
        """Return declared plugin dependency names from a manifest."""
        deps = meta.get("dependencies") or []
        if not isinstance(deps, list):
            return []
        return [d for d in deps if isinstance(d, str) and d.strip()]

    def _load_with_dependencies(
        self, name: str, _resolving: Optional[set] = None
    ) -> Optional[LoadedPlugin]:
        """Load a plugin after recursively loading its declared dependencies.

        Dependencies are loaded first so ``on_load`` hooks can bind to their
        instances. Missing or cyclic dependencies are logged and do not block
        loading the dependent plugin itself.
        """
        if name in self._loaded:
            return self._loaded[name]
        if _resolving is None:
            _resolving = set()
        if name in _resolving:
            logger.error(
                "Circular plugin dependency detected involving: %s",
                sorted(_resolving | {name}),
            )
            return None
        meta = self.get_manifest(name)
        if meta is None:
            logger.error("Plugin not installed: %s", name)
            return None
        _resolving.add(name)
        for dep in self._dependencies_of(meta):
            try:
                self._load_with_dependencies(dep, _resolving)
            except Exception as e:
                logger.error(f"Failed to load dependency {dep} of {name}: {e}")
        _resolving.discard(name)
        return self.load_plugin(meta)

    def load_by_name(self, name: str) -> Optional[LoadedPlugin]:
        """Load a single installed plugin by name (O(1) path lookup).

        Declared ``dependencies`` are loaded first (recursively). Prefer this
        over discover()+filter for programmatic use.
        """
        return self._load_with_dependencies(name)

    def load_all(self) -> int:
        """Load all discovered plugins. Returns count loaded.

        Plugins are loaded in dependency order (dependencies first) so
        ``on_load`` hooks can bind to prerequisite plugin instances.
        """
        plugins = self.discover()
        loaded = 0

        ordered: List[Dict] = []
        seen: set = set()
        visiting: set = set()

        def _visit(meta: Dict) -> None:
            name = meta.get("name", "")
            if not name or name in seen:
                return
            if name in visiting:
                logger.error(
                    "Circular plugin dependency detected involving: %s",
                    sorted(visiting | {name}),
                )
                return
            visiting.add(name)
            for dep in self._dependencies_of(meta):
                dep_meta = next((m for m in plugins if m.get("name") == dep), None)
                if dep_meta is None:
                    logger.warning(f"Plugin {name} depends on missing plugin: {dep}")
                    continue
                _visit(dep_meta)
            visiting.discard(name)
            seen.add(name)
            ordered.append(meta)

        for meta in plugins:
            _visit(meta)

        for meta in ordered:
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

        # Check sandbox status
        if self.sandbox and self.sandbox.is_disabled(name):
            logger.warning("Plugin %s is sandbox-disabled", name)
            return None

        plugin_dir = Path(meta.get("_path", self.plugins_dir / name))

        # Security validation
        try:
            from tokenade.core.integration.plugin_security import validate_plugin_security
            is_safe, msg = validate_plugin_security(plugin_dir)
            if not is_safe:
                logger.error(f"Plugin {name} failed security validation: {msg}")
                return None
            if msg:
                logger.warning(f"Plugin {name} security warning: {msg}")
        except Exception as e:
            logger.error(f"Plugin {name} security check failed: {e}")
            return None

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
            # Auto-discover: look for class that subclasses the target type
            from tokenade.plugin.base import PLUGIN_TYPE_BASE_CLASSES
            target_classes = PLUGIN_TYPE_BASE_CLASSES.get(plugin_type, ())
            for target_cls in target_classes:
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, target_cls)
                        and attr is not target_cls
                    ):
                        entry_class = attr
                        break
                if entry_class:
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

        # Bind plugin directory so SiteHandlerPlugin can load site_config.json
        try:
            if hasattr(instance, "set_plugin_dir"):
                instance.set_plugin_dir(plugin_dir)
        except Exception as e:
            logger.debug(f"Plugin {name}: set_plugin_dir failed: {e}")

        # Check API version
        from tokenade.plugin.api import API_VERSION
        plugin_api_version = getattr(instance, "API_VERSION", None)
        if plugin_api_version is None:
            logger.debug(f"Plugin {name}: no API_VERSION (legacy mode)")
        elif plugin_api_version != API_VERSION:
            logger.warning(
                f"Plugin {name}: API version {plugin_api_version} "
                f"!= expected {API_VERSION} — loading anyway"
            )

        # Call on_load lifecycle hook
        try:
            if hasattr(instance, 'on_load'):
                instance.on_load()
        except Exception as e:
            logger.error(f"Plugin {name}: on_load() failed: {e}", exc_info=True)
            if self.sandbox:
                self.sandbox._on_failure(name, str(e))
            _emit_event(
                "PLUGIN_ERROR",
                {"plugin_name": name, "error": str(e), "hook": "on_load"},
            )
            loaded = LoadedPlugin(
                name=name,
                version=meta.get("version", "0.0.0"),
                description=meta.get("description", ""),
                plugin_type=plugin_type,
                module=module,
                entry_class=entry_class,
                instance=instance,
                state=PluginState.FAILED,
                error=str(e),
            )
            self._loaded[name] = loaded
            return loaded

        loaded = LoadedPlugin(
            name=name,
            version=meta.get("version", "0.0.0"),
            description=meta.get("description", ""),
            plugin_type=plugin_type,
            module=module,
            entry_class=entry_class,
            instance=instance,
            state=PluginState.LOADED,
        )

        self._loaded[name] = loaded

        # T3.1/T5.2/T7.4: Wire on_configure() with PluginConfigManager.
        # Configuration validation runs before registration and event
        # publishing so an unconfigured or failed plugin is never exposed
        # as available to consumers.
        ctx = _get_shared_context()
        configuration_valid = True
        try:
            from tokenade.core.integration.plugin_config import PluginConfigManager
            from tokenade.plugin.api import PluginConfig

            config_mgr = PluginConfigManager(plugins_dir=self.plugins_dir)
            schema = config_mgr.get_schema(name) or meta.get("config", {}).get("schema", {})
            full_config = config_mgr.get_full_config(name)

            # If neither schema nor config exists, skip on_configure
            if not schema and not full_config:
                pass
            elif hasattr(instance, "on_configure"):
                plugin_config = PluginConfig(schema=schema, values=full_config)
                errors = plugin_config.validate()
                if errors:
                    configuration_valid = False
                    loaded.config = full_config
                    logger.debug(
                        "Plugin %s is loaded but not configured: %s", name, errors
                    )
                else:
                    instance.on_configure(plugin_config)
                    loaded.config = full_config
                    loaded.state = PluginState.CONFIGURED
                    logger.debug(f"Plugin {name}: on_configure() called")
                    if ctx:
                        ctx.plugins.set_config(name, full_config)
            else:
                loaded.config = full_config
        except Exception as e:
            logger.error(f"Plugin {name}: on_configure() failed: {e}", exc_info=True)
            _emit_event(
                "PLUGIN_ERROR",
                {"plugin_name": name, "error": str(e), "hook": "on_configure"},
            )
            loaded.state = PluginState.FAILED
            loaded.error = str(e)
            return loaded

        if not configuration_valid:
            return loaded

        # Register by type
        if plugin_type == "handler":
            # Prefer site_config.json "name", then manifest site_name, then plugin name
            site_name = meta.get("site_name") or name
            if hasattr(instance, "get_site_config"):
                try:
                    sc = instance.get_site_config() or {}
                    if sc.get("name"):
                        site_name = sc["name"]
                except Exception:
                    pass
            self._handlers[site_name] = instance
            # Also index by plugin name for --plugin google-handler lookups
            if name and name not in self._handlers:
                self._handlers[name] = instance
        elif plugin_type == "export_format":
            format_name = meta.get("format_name", name)
            self._exporters[format_name] = instance
        elif plugin_type == "validator":
            rule_name = meta.get("rule_name", name)
            self._validators[rule_name] = instance
        elif plugin_type == "session_refresh":
            self._refreshers[name] = instance
        elif plugin_type == "stealth":
            self._stealths[name] = instance
        elif plugin_type == "proxy":
            self._proxies[name] = instance
        elif plugin_type == "notification":
            self._notifications[name] = instance
        elif plugin_type == "captcha":
            self._captchas[name] = instance
        elif plugin_type == "challenge_detector":
            self._challenge_detectors[name] = instance
        elif plugin_type == "challenge_solver":
            self._challenge_solvers[name] = instance
        elif plugin_type == "egress_provider":
            self._egress_providers[name] = instance
        elif plugin_type == "fingerprint_oracle":
            self._fingerprint_oracles[name] = instance
        else:
            logger.warning(
                f"Plugin {name}: unknown type '{plugin_type}' — loaded but not typed-registered"
            )

        logger.info(f"Loaded plugin: {name} v{loaded.version} ({plugin_type})")

        # Emit event through event bus
        bus = _get_event_bus()
        if bus:
            try:
                from tokenade.core.events.types import EventType
                bus.emit(
                    EventType.PLUGIN_LOADED,
                    data={
                        "plugin_name": name,
                        "plugin_type": plugin_type,
                        "version": loaded.version,
                    },
                    source="plugin_loader",
                )
            except Exception as e:
                logger.debug(f"Failed to emit PLUGIN_LOADED event: {e}")

        # Register in shared context
        ctx = _get_shared_context()
        if ctx:
            try:
                ctx.plugins.register(
                    name,
                    {
                        "version": loaded.version,
                        "type": plugin_type,
                        "enabled": True,
                    },
                )
            except Exception as e:
                logger.debug(f"Failed to register plugin in shared context: {e}")

        # Transition to ACTIVE after all wiring succeeds
        loaded.state = PluginState.ACTIVE

        # T3.5b: Wire proxy plugins to ProxyManager (if available)
        if plugin_type == "proxy":
            try:
                from tokenade.core.proxy.manager import ProxyManager
                # Get or create a shared ProxyManager
                from tokenade.core.proxy.manager import ProxyManager as PM
                # The ProxyManager is typically created by the CLI/daemon.
                # We emit an event so any ProxyManager listening can register this plugin.
                bus = _get_event_bus()
                if bus:
                    from tokenade.core.events.types import EventType
                    bus.emit(
                        EventType.PLUGIN_LOADED,
                        data={
                            "plugin_name": name,
                            "plugin_type": plugin_type,
                            "version": loaded.version,
                            "instance": instance,
                        },
                        source="plugin_loader",
                    )
            except Exception as e:
                logger.debug(f"Failed to wire proxy plugin to ProxyManager: {e}")

        # T3.5: Wire captcha plugins to CaptchaManager via adapter
        if plugin_type == "captcha":
            try:
                from tokenade.core.browser.captcha import PluginCaptchaSolver
                # Create adapter and store it for later registration by CaptchaManager
                adapter = PluginCaptchaSolver(instance)
                if not hasattr(self, "_captcha_adapters"):
                    self._captcha_adapters = {}
                self._captcha_adapters[name] = adapter
                logger.debug(f"Plugin {name}: CaptchaPlugin adapter created")
            except Exception as e:
                logger.debug(f"Failed to create CaptchaPlugin adapter: {e}")

        return loaded

    def unload(self, name: str) -> bool:
        """Unload a plugin."""
        if name not in self._loaded:
            return False

        plugin = self._loaded.pop(name)

        # Call on_unload lifecycle hook before removal
        try:
            if hasattr(plugin.instance, "on_unload"):
                plugin.instance.on_unload()
        except Exception as e:
            logger.error(f"Plugin {name}: on_unload() failed: {e}", exc_info=True)
            _emit_event(
                "PLUGIN_ERROR",
                {"plugin_name": name, "error": str(e), "hook": "on_unload"},
            )

        plugin.state = PluginState.UNLOADED

        # Remove from type registries
        if plugin.plugin_type == "handler":
            self._handlers = {k: v for k, v in self._handlers.items() if v is not plugin.instance}
        elif plugin.plugin_type == "export_format":
            self._exporters = {k: v for k, v in self._exporters.items() if v is not plugin.instance}
        elif plugin.plugin_type == "validator":
            self._validators = {k: v for k, v in self._validators.items() if v is not plugin.instance}
        elif plugin.plugin_type == "session_refresh":
            self._refreshers = {k: v for k, v in self._refreshers.items() if v is not plugin.instance}
        elif plugin.plugin_type == "stealth":
            self._stealths = {k: v for k, v in self._stealths.items() if v is not plugin.instance}
        elif plugin.plugin_type == "proxy":
            self._proxies = {k: v for k, v in self._proxies.items() if v is not plugin.instance}
        elif plugin.plugin_type == "notification":
            self._notifications = {
                k: v for k, v in self._notifications.items() if v is not plugin.instance
            }
        elif plugin.plugin_type == "captcha":
            self._captchas = {k: v for k, v in self._captchas.items() if v is not plugin.instance}
        elif plugin.plugin_type == "challenge_detector":
            self._challenge_detectors = {
                k: v for k, v in self._challenge_detectors.items() if v is not plugin.instance
            }
        elif plugin.plugin_type == "challenge_solver":
            self._challenge_solvers = {
                k: v for k, v in self._challenge_solvers.items() if v is not plugin.instance
            }
        elif plugin.plugin_type == "egress_provider":
            self._egress_providers = {
                k: v for k, v in self._egress_providers.items() if v is not plugin.instance
            }
        elif plugin.plugin_type == "fingerprint_oracle":
            self._fingerprint_oracles = {
                k: v for k, v in self._fingerprint_oracles.items() if v is not plugin.instance
            }

        logger.info(f"Unloaded plugin: {name}")

        # Emit event through event bus
        bus = _get_event_bus()
        if bus:
            try:
                from tokenade.core.events.types import EventType
                bus.emit(
                    EventType.PLUGIN_UNLOADED,
                    data={
                        "plugin_name": name,
                        "plugin_type": plugin.plugin_type,
                    },
                    source="plugin_loader",
                )
            except Exception as e:
                logger.debug(f"Failed to emit PLUGIN_UNLOADED event: {e}")

        # Unregister from shared context
        ctx = _get_shared_context()
        if ctx:
            try:
                ctx.plugins.unregister(name)
            except Exception as e:
                logger.debug(f"Failed to unregister plugin from shared context: {e}")

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

    def get_refresher(self, name: str) -> Optional[Any]:
        """Get a session refresh plugin by name."""
        return self._refreshers.get(name)

    def get_stealth(self, name: str) -> Optional[Any]:
        """Get a stealth plugin by name."""
        return self._stealths.get(name)

    def get_proxy_plugin(self, name: str) -> Optional[Any]:
        """Get a proxy plugin by name."""
        return self._proxies.get(name)

    def get_captcha(self, name: str) -> Optional[Any]:
        """Get a captcha plugin by name."""
        return self._captchas.get(name)

    def get_challenge_detector(self, name: str) -> Optional[Any]:
        """Get a challenge detector plugin by name."""
        return self._challenge_detectors.get(name)

    def get_challenge_solver(self, name: str) -> Optional[Any]:
        """Get a challenge solver plugin by name."""
        return self._challenge_solvers.get(name)

    def get_refresher_for_session(self, session: dict) -> Optional[Any]:
        """Find the first refresh plugin that can handle this session."""
        for name, refresher in self._refreshers.items():
            try:
                if refresher.can_refresh(session):
                    return refresher
            except Exception as e:
                logger.warning(f"Plugin {name}.can_refresh() failed: {e}")
        return None

    def list_handlers(self) -> Dict[str, Any]:
        """List all loaded handler plugins."""
        return dict(self._handlers)

    def list_exporters(self) -> Dict[str, Any]:
        """List all loaded exporter plugins."""
        return dict(self._exporters)

    def list_validators(self) -> Dict[str, Any]:
        """List all loaded validator plugins."""
        return dict(self._validators)

    def list_refreshers(self) -> Dict[str, Any]:
        """List all loaded session refresh plugins."""
        return dict(self._refreshers)

    def list_stealths(self) -> Dict[str, Any]:
        """List all loaded stealth plugins."""
        return dict(self._stealths)

    def list_proxy_plugins(self) -> Dict[str, Any]:
        """List all loaded proxy plugins."""
        return dict(self._proxies)

    def list_captchas(self) -> Dict[str, Any]:
        """List all loaded captcha plugins."""
        return dict(self._captchas)

    def list_challenge_detectors(self) -> Dict[str, Any]:
        """List all loaded challenge detector plugins."""
        return dict(self._challenge_detectors)

    def list_challenge_solvers(self) -> Dict[str, Any]:
        """List all loaded challenge solver plugins."""
        return dict(self._challenge_solvers)

    def get_egress_provider(self, name: str) -> Optional[Any]:
        """Get an egress provider plugin by name."""
        return self._egress_providers.get(name)

    def list_egress_providers(self) -> Dict[str, Any]:
        """List all loaded egress provider plugins."""
        return dict(self._egress_providers)

    def get_fingerprint_oracle(self, name: str) -> Optional[Any]:
        """Get a fingerprint oracle plugin by name."""
        return self._fingerprint_oracles.get(name)

    def list_fingerprint_oracles(self) -> Dict[str, Any]:
        """List all loaded fingerprint oracle plugins."""
        return dict(self._fingerprint_oracles)

    def list_all(self) -> List[LoadedPlugin]:
        """List all loaded plugins."""
        return list(self._loaded.values())

    def get_state(self, name: str) -> Optional[PluginState]:
        """Get the lifecycle state of a plugin.

        Returns None if plugin not found.
        """
        plugin = self._loaded.get(name)
        return plugin.state if plugin else None

    def is_disabled(self, name: str) -> bool:
        """Whether a discovered plugin has been administratively disabled."""
        return name in self._disabled

    def get_plugin(self, name: str) -> Optional[LoadedPlugin]:
        """Get a LoadedPlugin by name.

        Returns None if not found.
        """
        return self._loaded.get(name)

    def get_captcha_adapter(self, name: str) -> Any:
        """Get a CaptchaPlugin adapter (PluginCaptchaSolver) by name.

        Returns None if no adapter exists.
        """
        return getattr(self, "_captcha_adapters", {}).get(name)

    def list_captcha_adapters(self) -> Dict[str, Any]:
        """List all captcha adapters."""
        return dict(getattr(self, "_captcha_adapters", {}))

    def wire_proxy_manager(self, manager: Any) -> int:
        """Wire all loaded proxy plugins to a ProxyManager.

        Args:
            manager: ProxyManager instance (must have register_plugin method)

        Returns:
            Number of plugins registered
        """
        count = 0
        for name, plugin in self._proxies.items():
            try:
                manager.register_plugin(plugin)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to wire proxy plugin {name}: {e}")
        return count

    def reload(self, name: str) -> Optional[LoadedPlugin]:
        """Reload a plugin. Preserves config across reload."""
        preserved_config = {}
        if name in self._loaded:
            preserved_config = self._loaded[name].config or {}

        self.unload(name)

        manifest_path = self.plugins_dir / name / "plugin.json"
        if not manifest_path.exists():
            return None

        with open(manifest_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        meta["_path"] = str(self.plugins_dir / name)

        # Inject preserved config so on_configure() uses it
        if preserved_config and "config" not in meta:
            meta["config"] = {"values": preserved_config}

        loaded = self.load_plugin(meta)
        if loaded and not loaded.config:
            loaded.config = preserved_config
        return loaded

    def _load_disabled_list(self) -> None:
        """Load the list of disabled plugins."""
        disabled_file = self.plugins_dir / ".disabled"
        if disabled_file.exists():
            try:
                with open(disabled_file, "r") as f:
                    self._disabled = set(line.strip() for line in f if line.strip())
            except Exception:
                self._disabled = set()

    def _save_disabled_list(self) -> None:
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
            self._loaded[name].state = PluginState.ACTIVE
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
            self._loaded[name].state = PluginState.DISABLED
            self.unload(name)
        logger.info(f"Plugin disabled: {name}")
        return True

    def discover_names(self) -> set:
        """Get names of all discovered plugins."""
        names = set()
        for meta in self.discover():
            names.add(meta.get("name", ""))
        return names
