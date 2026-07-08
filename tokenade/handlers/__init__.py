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

- JSON under `site_configs/` for domains + critical cookies + selectors
- `SiteHandlerPlugin` in plugins for non-trivial extract/inject/verify

Legacy classes remain for backward compatibility and may emit
DeprecationWarning when instantiated. They will be thin adapters or
removed once CLI call sites migrate to plugins/site_configs.
"""

from tokenade.handlers.base import (  # noqa: F401
    SiteHandler,
    HandlerRegistry,
    SessionData,
    ExtractedToken,
    AuthStatus,
    TokenType,
)

__all__ = [
    "SiteHandler",
    "HandlerRegistry",
    "SessionData",
    "ExtractedToken",
    "AuthStatus",
    "TokenType",
]
