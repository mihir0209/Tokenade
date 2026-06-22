"""
Tokenade Plugin System — Base classes and registration.

Plugins extend tokenade with new capabilities:
- SessionRefreshPlugin: Refresh sessions (OAuth2, API tokens, etc.)
- SiteHandlerPlugin: Handle specific sites (custom extraction, login flows)
- ExportFormatPlugin: Custom export formats
- SessionValidatorPlugin: Custom validation rules

Usage:
    from tokenade.plugin import SessionRefreshPlugin

    class MyOAuth2Plugin(SessionRefreshPlugin):
        name = "my-oauth2"
        version = "1.0.0"
        description = "OAuth2 refresh for MyService"

        def can_refresh(self, session: dict) -> bool:
            return "myservice.com" in str(session)

        def refresh(self, session: dict, credentials: dict) -> dict:
            # Implement OAuth2 refresh logic
            return session
"""

from tokenade.plugin.base import (
    PluginBase,
    SessionRefreshPlugin,
    SiteHandlerPlugin,
    ExportFormatPlugin,
    SessionValidatorPlugin,
)

__all__ = [
    "PluginBase",
    "SessionRefreshPlugin",
    "SiteHandlerPlugin",
    "ExportFormatPlugin",
    "SessionValidatorPlugin",
]
