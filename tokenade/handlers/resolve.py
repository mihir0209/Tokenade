"""Resolve legacy site handlers by site name.

Prefer plugins + site_configs for new work. This module exists so CLI
commands do not hardcode GoogleHandler everywhere (P3 dual-handler collapse).
"""

from __future__ import annotations

from typing import Optional, Type

from tokenade.handlers.base import SiteHandler


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
