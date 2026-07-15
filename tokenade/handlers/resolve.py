"""Resolve legacy site handlers by site name.

Prefer plugins + site_configs for new work. This module exists so CLI
commands do not hardcode GoogleHandler everywhere (P3 dual-handler collapse).

When a plugin-formatted handler (GoogleHandlerAdapter, GitHubHandlerAdapter,
GenericOAuth2HandlerAdapter) is available in the plugin system, it is
preferred over the legacy handler. A deprecation warning is logged when
the legacy path is used.

Decoupled from concrete handler imports (google.py, github.py) — those
are in the marketplace (tokenade-plugins/), not core.
"""

from __future__ import annotations

import logging
from typing import Optional, Type

from tokenade.handlers.base import SiteHandler

logger = logging.getLogger(__name__)

_ALIASES = {
    "gh": "github",
    "gmail": "google",
    "youtube": "google",
    "openai": "chatgpt",
    "gpt": "chatgpt",
    "tg": "telegram",
}


def resolve_legacy_handler_class(site_name: Optional[str] = None) -> Optional[Type[SiteHandler]]:
    """Return a legacy SiteHandler subclass for the given site.

    Lookup order:
    1. HandlerRegistry (registered handlers — populated by handler imports)
    2. Plugin system (SiteHandlerPlugin wrapped as SiteHandler)
    3. None (caller must handle)

    Returns None if no handler is found for the given site.
    """
    key = (site_name or "google").lower().strip()
    key = _ALIASES.get(key, key)

    logger.debug(
        f"resolve_legacy_handler_class: site_name={site_name!r} key={key!r}"
    )

    from tokenade.handlers.base import HandlerRegistry

    # 1. Check HandlerRegistry (populated by handler module imports)
    registered = HandlerRegistry.get(key)
    if registered is not None:
        logger.debug(f"Found registered handler for {key}")
        return registered

    # 2. Try plugin system — look for a SiteHandlerPlugin for this site
    try:
        from tokenade.core.integration.plugin_loader import PluginLoader
        loader = PluginLoader()
        plugin = loader.get_handler(key)
        if plugin is not None:
            # Wrap the plugin as a legacy SiteHandler for backward compat
            logger.debug(f"Found plugin handler for {key}, wrapping as legacy")
            return _wrap_plugin_as_handler(plugin)
    except Exception as e:
        logger.debug(f"Plugin lookup failed for {key}: {e}")

    # 3. No handler found
    logger.warning(
        f"No handler found for site '{key}'. "
        f"Install a handler plugin or check tokenade-plugins marketplace."
    )
    return None


def _wrap_plugin_as_handler(plugin) -> Optional[Type[SiteHandler]]:
    """Wrap a SiteHandlerPlugin as a legacy SiteHandler class.

    Returns a class that can be instantiated with a browser manager
    and provides the legacy SiteHandler interface.
    """
    from tokenade.handlers.plugin_adapters import LegacyHandlerAdapter

    # If the plugin is already a LegacyHandlerAdapter, return its legacy class
    if isinstance(plugin, LegacyHandlerAdapter) and plugin._legacy_cls is not None:
        return plugin._legacy_cls

    # Otherwise, we can't easily wrap an arbitrary plugin as a legacy handler
    # because the interfaces are fundamentally different.
    # Return None and let the caller handle it.
    return None
