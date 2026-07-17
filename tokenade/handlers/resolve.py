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
        loader.load_all()
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


def resolve_legacy_handler_class_for_session(session_data: dict) -> Optional[Type[SiteHandler]]:
    """Resolve a legacy handler using embedded Site Handler metadata first."""
    metadata = session_data.get("metadata") or {}
    site_handler = metadata.get("site_handler") or {}
    if isinstance(site_handler, dict):
        plugin_name = site_handler.get("plugin_name") or site_handler.get("handler_name")
        if plugin_name:
            handler_cls = resolve_legacy_handler_class(str(plugin_name))
            if handler_cls is not None:
                return handler_cls

    return resolve_legacy_handler_class(session_data.get("site_name"))


def _wrap_plugin_as_handler(plugin) -> Optional[Type[SiteHandler]]:
    """Wrap a SiteHandlerPlugin as a legacy SiteHandler class.

    Returns a class that can be instantiated with a browser manager
    and provides the legacy SiteHandler interface.
    """
    from tokenade.handlers.plugin_adapters import LegacyHandlerAdapter

    # If the plugin is already a LegacyHandlerAdapter, return its legacy class
    if isinstance(plugin, LegacyHandlerAdapter) and plugin._legacy_cls is not None:
        return plugin._legacy_cls

    site_config = plugin.get_site_config() if hasattr(plugin, "get_site_config") else {}
    site_name = site_config.get("name") or getattr(plugin, "name", "plugin")
    domains = (
        plugin.get_export_domains()
        if hasattr(plugin, "get_export_domains")
        else site_config.get("domains", [])
    )
    critical_cookies = (
        plugin.get_critical_cookies()
        if hasattr(plugin, "get_critical_cookies")
        else site_config.get("critical_cookies", [])
    )

    class PluginLegacyHandler(SiteHandler):
        SITE_NAME = str(site_name).replace("-handler", "")
        DOMAINS = list(domains or [])
        LOGIN_URL = str(site_config.get("login_url") or "")
        DASHBOARD_URL = str(
            site_config.get("dashboard_url") or site_config.get("validate_url") or ""
        )
        CRITICAL_COOKIES = list(critical_cookies or [])

        def __init__(self, browser_manager=None, config=None):
            super().__init__(browser_manager, config)
            self._plugin = plugin

        def _context(self):
            return getattr(self.browser, "_context", None) or self.browser

        def check_auth_status(self) -> AuthStatus:
            cookies = self.extract_cookies()
            if not cookies:
                return AuthStatus.LOGGED_OUT
            return AuthStatus.LOGGED_IN if self.validate_session(cookies) else AuthStatus.UNKNOWN

        def extract_tokens(self) -> list:
            return []

        def extract_cookies(self) -> list:
            if self.browser and hasattr(self.browser, "get_cookies"):
                return self.browser.get_cookies()
            context = self._context()
            if context and hasattr(context, "cookies"):
                return context.cookies()
            return []

        def validate_session(self, cookies: list) -> bool:
            session = self._session_data.to_dict() if self._session_data else {}
            session["cookies"] = cookies
            try:
                result = self._plugin.validate(session)
                data = getattr(result, "data", {}) or {}
                return bool(getattr(result, "success", False) and data.get("valid", False))
            except Exception:
                return False

        def inject_session(self, session_data) -> bool:
            self._session_data = session_data
            session = session_data.to_dict() if hasattr(session_data, "to_dict") else dict(session_data)
            context = self._context()
            try:
                result = self._plugin.inject_session(context, session)
                if getattr(result, "success", False):
                    return True
            except Exception:
                pass
            if self.browser and hasattr(self.browser, "add_cookies"):
                self.browser.add_cookies(session.get("cookies", []))
                return True
            return False

    PluginLegacyHandler.__name__ = f"{plugin.__class__.__name__}LegacyHandler"
    return PluginLegacyHandler
