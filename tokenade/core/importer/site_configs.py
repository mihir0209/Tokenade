"""
Site configuration resolution — plugin-backed only.

Sprint 0: site configs live in each site-handler plugin as ``site_config.json``
at the plugin root. There is no built-in Python catalog and no repo-root
``site_configs/`` directory.

Public API (stable):
  - get_site_config(site_name) -> dict
  - list_sites() -> list[str]
  - list_site_configs() -> dict[str, dict]
  - config_from_plugin_instance(instance) -> dict
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_PLUGINS_DIR = Path.home() / ".tokenade" / "plugins"

# Canonical field names expected by core (export, health, proxy, loader).
_SITE_CONFIG_KEYS = (
    "name",
    "domains",
    "critical_cookies",
    "login_url",
    "dashboard_url",
    "validate_url",
    "session_check_url",
    "login_indicator_css",
    "logged_in_selectors",
    "logged_out_selectors",
    "wait_seconds",
    "critical_storage",
    "localStorage_keys",
    "preferred_plugin",
)


def normalize_site_config(raw: Dict[str, Any], *, plugin_name: str = "") -> Dict[str, Any]:
    """Normalize a site_config.json dict into the core shape."""
    if not isinstance(raw, dict):
        return {}

    cfg: Dict[str, Any] = {}
    name = (raw.get("name") or "").strip()
    if name:
        cfg["name"] = name

    domains = raw.get("domains")
    if isinstance(domains, list):
        cfg["domains"] = [str(d) for d in domains if d]
    else:
        cfg["domains"] = []

    critical = raw.get("critical_cookies")
    if isinstance(critical, list):
        cfg["critical_cookies"] = [str(c) for c in critical if c]
    else:
        cfg["critical_cookies"] = []

    for key in (
        "login_url",
        "dashboard_url",
        "validate_url",
        "session_check_url",
        "login_indicator_css",
    ):
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            cfg[key] = val.strip()

    # Aliases: validate_url defaults to dashboard_url
    if "validate_url" not in cfg and cfg.get("dashboard_url"):
        cfg["validate_url"] = cfg["dashboard_url"]

    for key in ("logged_in_selectors", "logged_out_selectors"):
        val = raw.get(key)
        if isinstance(val, list):
            cfg[key] = [str(s) for s in val if s]
        else:
            cfg[key] = []

    # login_indicator_css (legacy single selector) → logged_out_selectors
    if cfg.get("login_indicator_css") and not cfg.get("logged_out_selectors"):
        cfg["logged_out_selectors"] = [cfg["login_indicator_css"]]

    wait = raw.get("wait_seconds", 5)
    try:
        wait_i = int(wait)
        cfg["wait_seconds"] = wait_i if wait_i > 0 else 5
    except (TypeError, ValueError):
        cfg["wait_seconds"] = 5

    storage = raw.get("critical_storage")
    if isinstance(storage, dict):
        cfg["critical_storage"] = storage
    else:
        cfg["critical_storage"] = {"local": {}, "session": {}}

    ls_keys = raw.get("localStorage_keys")
    if isinstance(ls_keys, list):
        cfg["localStorage_keys"] = [str(k) for k in ls_keys if k]

    preferred = raw.get("preferred_plugin") or plugin_name
    if preferred:
        cfg["preferred_plugin"] = preferred

    # Preserve unknown keys for plugin-specific extensions
    for key, val in raw.items():
        if key not in cfg and key not in ("_path", "_plugin"):
            cfg[key] = val

    return cfg


def load_site_config_file(path: Path, *, plugin_name: str = "") -> Dict[str, Any]:
    """Load and normalize a site_config.json file. Empty dict on failure."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.debug("Failed to read site config %s: %s", path, e)
        return {}
    return normalize_site_config(data, plugin_name=plugin_name)


def config_from_plugin_instance(instance: Any) -> Dict[str, Any]:
    """Build a site config dict from a SiteHandlerPlugin instance."""
    if instance is None:
        return {}

    if hasattr(instance, "get_site_config"):
        try:
            cfg = instance.get_site_config()
            if isinstance(cfg, dict) and (cfg.get("domains") or cfg.get("name")):
                plugin_name = getattr(instance, "name", "") or ""
                return normalize_site_config(cfg, plugin_name=plugin_name)
        except Exception as e:
            logger.debug("get_site_config() failed on %s: %s", type(instance), e)

    plugin_name = getattr(instance, "name", "") or ""
    raw: Dict[str, Any] = {"name": "", "preferred_plugin": plugin_name}

    # Infer site name from plugin name (google-handler → google)
    if plugin_name.endswith("-handler"):
        raw["name"] = plugin_name[: -len("-handler")]
    elif plugin_name:
        raw["name"] = plugin_name

    for method, key in (
        ("get_export_domains", "domains"),
        ("get_critical_cookies", "critical_cookies"),
        ("get_login_url", "login_url"),
        ("get_dashboard_url", "dashboard_url"),
        ("get_session_check_url", "session_check_url"),
        ("get_logged_in_selectors", "logged_in_selectors"),
        ("get_logged_out_selectors", "logged_out_selectors"),
        ("get_critical_storage", "critical_storage"),
    ):
        if hasattr(instance, method):
            try:
                raw[key] = getattr(instance, method)()
            except Exception:
                pass

    if raw.get("dashboard_url") and not raw.get("validate_url"):
        raw["validate_url"] = raw["dashboard_url"]

    # Prefer first logged_out selector as login_indicator_css for older callers
    los = raw.get("logged_out_selectors") or []
    if isinstance(los, list) and los and not raw.get("login_indicator_css"):
        raw["login_indicator_css"] = los[0]

    return normalize_site_config(raw, plugin_name=plugin_name)


def discover_plugin_site_configs(
    plugins_dir: Optional[Path] = None,
) -> Dict[str, Dict[str, Any]]:
    """Scan plugins_dir for handler plugins with site_config.json.

    Returns map of site key (lowercase name) → normalized config.
    When multiple plugins claim the same site name, the first wins (sorted by path).
    """
    root = Path(plugins_dir) if plugins_dir is not None else DEFAULT_PLUGINS_DIR
    by_site: Dict[str, Dict[str, Any]] = {}

    if not root.is_dir():
        return by_site

    for plugin_dir in sorted(root.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name.startswith("."):
            continue

        manifest_path = plugin_dir / "plugin.json"
        if not manifest_path.is_file():
            continue

        try:
            meta = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        plugin_type = (meta.get("type") or "").lower()
        if plugin_type and plugin_type not in ("handler", "site_handler", ""):
            continue

        plugin_name = meta.get("name") or plugin_dir.name
        site_path = plugin_dir / "site_config.json"
        if site_path.is_file():
            cfg = load_site_config_file(site_path, plugin_name=plugin_name)
            if cfg:
                cfg["_plugin"] = plugin_name
                cfg["_path"] = str(site_path)
                _index_site(by_site, cfg, plugin_name, meta)

        # Multi-catalog plugins (generic-handler) keep per-site JSONs under sites/*.json.
        # Each file is a normal site config — pick them up so SessionProbe / health
        # checks resolve session_check_url without an active handler instance.
        if plugin_type in ("handler", "site_handler", ""):
            sites_dir = plugin_dir / "sites"
            if sites_dir.is_dir():
                for site_path in sorted(sites_dir.glob("*.json")):
                    try:
                        site_cfg = json.loads(site_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError) as e:
                        logger.debug("Failed to load %s: %s", site_path, e)
                        continue
                    if not isinstance(site_cfg, dict):
                        continue
                    site_cfg = normalize_site_config(site_cfg, plugin_name=plugin_name)
                    site_cfg["_plugin"] = plugin_name
                    site_cfg["_path"] = str(site_path)
                    site_cfg.setdefault("preferred_plugin", plugin_name)
                    _index_site(by_site, site_cfg, plugin_name, meta)

    return by_site


def _index_site(
    by_site: Dict[str, Dict[str, Any]],
    cfg: Dict[str, Any],
    plugin_name: str,
    meta: Dict[str, Any],
) -> None:
    """Register a single site config under all its index keys (first-wins)."""
    keys = set()
    if cfg.get("name"):
        keys.add(str(cfg["name"]).lower())
    site_name = meta.get("site_name")
    if site_name:
        keys.add(str(site_name).lower())
    if plugin_name.endswith("-handler"):
        keys.add(plugin_name[: -len("-handler")].lower())
    keys.add(plugin_name.lower())

    for key in keys:
        if key and key not in by_site:
            by_site[key] = dict(cfg)


def _configs_from_loaded_handlers() -> Dict[str, Dict[str, Any]]:
    """Merge configs from already-loaded PluginLoader handlers (if any)."""
    by_site: Dict[str, Dict[str, Any]] = {}
    try:
        from tokenade.core.integration.plugin_loader import get_shared_loader

        loader = get_shared_loader()
        if loader is None:
            return by_site
        for site_key, instance in loader.list_handlers().items():
            cfg = config_from_plugin_instance(instance)
            if not cfg:
                continue
            keys = {str(site_key).lower()}
            if cfg.get("name"):
                keys.add(str(cfg["name"]).lower())
            preferred = cfg.get("preferred_plugin") or getattr(instance, "name", "")
            if preferred:
                keys.add(str(preferred).lower())
                if str(preferred).endswith("-handler"):
                    keys.add(str(preferred)[: -len("-handler")].lower())
            for key in keys:
                if key and key not in by_site:
                    by_site[key] = cfg
    except Exception as e:
        logger.debug("Could not read loaded handlers for site configs: %s", e)
    return by_site


def list_site_configs(plugins_dir: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """All known site configs (filesystem plugins + loaded instances)."""
    merged = discover_plugin_site_configs(plugins_dir)
    for key, cfg in _configs_from_loaded_handlers().items():
        if key not in merged:
            merged[key] = cfg
    return merged


def get_site_config(site_name: str, plugins_dir: Optional[Path] = None) -> dict:
    """Get config for a site by name (plugin site_config.json / handler instance).

    Returns empty dict if unknown. Always a dict (callers use .get).
    """
    if not site_name:
        return {}
    key = site_name.lower().strip()
    configs = list_site_configs(plugins_dir)
    if key in configs:
        return dict(configs[key])

    # Fuzzy: site_name contained in config name or vice versa
    for name, cfg in configs.items():
        if key in name or name in key:
            return dict(cfg)
    return {}


def list_sites(plugins_dir: Optional[Path] = None) -> list:
    """List available site config names (sorted, unique primary names)."""
    configs = list_site_configs(plugins_dir)
    names = set()
    for key, cfg in configs.items():
        primary = (cfg.get("name") or key or "").lower()
        if primary:
            names.add(primary)
    return sorted(names)
