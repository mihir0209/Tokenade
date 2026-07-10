"""
Legacy site handlers (tokenade.handlers).

P1 honesty note
---------------
There are **two** site-handler systems in Tokenade:

1. **Legacy** (this package): `SiteHandler` / `GoogleHandler` / `GitHubHandler`
   Used by older CLI paths (`tokenade transfer`, some `session.py` flows).

2. **Plugin** (`tokenade.plugin.SiteHandlerPlugin` + tokenade-plugins repo):
   Preferred extension path for new sites and marketplace installs.

Do **not** add new site logic here. Prefer:

- `SiteHandlerPlugin` + **`site_config.json`** in the plugin root
  (domains, critical cookies, URLs — loaded by the base class)

Legacy classes remain for backward compatibility and may emit
DeprecationWarning when instantiated.
"""

from tokenade.handlers.base import (  # noqa: F401
    SiteHandler,
    HandlerRegistry,
    SessionData,
    ExtractedToken,
    AuthStatus,
    TokenType,
)
from tokenade.handlers.resolve import resolve_legacy_handler_class  # noqa: F401

__all__ = [
    "SiteHandler",
    "HandlerRegistry",
    "SessionData",
    "ExtractedToken",
    "AuthStatus",
    "TokenType",
    "resolve_legacy_handler_class",
]
