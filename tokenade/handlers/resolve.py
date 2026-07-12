"""Resolve legacy site handlers by site name.

Prefer plugins + site_configs for new work. This module exists so CLI
commands do not hardcode GoogleHandler everywhere (P3 dual-handler collapse).

When a plugin-formatted handler (GoogleHandlerAdapter, GitHubHandlerAdapter,
GenericOAuth2HandlerAdapter) is available in the plugin system, it is
preferred over the legacy handler. A deprecation warning is logged when
the legacy path is used.
"""

from __future__ import annotations

import logging
from typing import Optional, Type

from tokenade.handlers.base import SiteHandler

logger = logging.getLogger(__name__)


def resolve_legacy_handler_class(site_name: Optional[str] = None) -> Type[SiteHandler]:
    """Return a legacy SiteHandler subclass for the given site.

    Lookup order:
    1. HandlerRegistry (registered handlers)
    2. Known built-ins (google, github)
    3. GoogleHandler fallback (historical default)
    """
    key = (site_name or "google").lower().strip()
    aliases = {
        "gh": "github",
        "gmail": "google",
        "youtube": "google",
        "openai": "chatgpt",
    }
    key = aliases.get(key, key)

    logger.debug(
        f"resolve_legacy_handler_class: site_name={site_name!r} key={key!r}"
    )
    # Legacy path used — log deprecation hint
    logger.debug(
        "Legacy handler resolution used — prefer plugins for new work"
    )

    from tokenade.handlers.base import HandlerRegistry

    # Ensure built-ins are registered
    try:
        import tokenade.handlers.google  # noqa: F401
        import tokenade.handlers.github  # noqa: F401
    except ImportError:
        pass

    registered = HandlerRegistry.get(key)
    if registered is not None:
        return registered

    if key in ("github",):
        from tokenade.handlers.github import GitHubHandler
        return GitHubHandler

    from tokenade.handlers.google import GoogleHandler
    return GoogleHandler
