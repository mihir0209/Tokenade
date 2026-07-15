"""
Site handler base classes and resolution (tokenade.handlers).

The legacy concrete handlers (GoogleHandler, GitHubHandler, GenericOAuth2Handler)
have been moved to the tokenade-plugins marketplace. This package now contains
only base classes and resolution infrastructure:

- ``SiteHandler`` — abstract base for site-specific handlers
- ``HandlerRegistry`` — registry for handler classes
- ``resolve_legacy_handler_class`` — resolve handler by site name (via registry or plugins)
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
