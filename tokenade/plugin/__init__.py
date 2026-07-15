"""
Tokenade Plugin System — Base classes and registration.

Plugins extend tokenade with new capabilities:
- SessionRefreshPlugin: Refresh sessions (OAuth2, API tokens, etc.)
- SiteHandlerPlugin: Handle specific sites (custom extraction, login flows)
- ExportFormatPlugin: Custom export formats
- SessionValidatorPlugin: Custom validation rules
- ProxyProviderPlugin: Commercial proxy providers (AnyIP, BrightData, etc.)
- NotificationPlugin: Notification providers (Slack, Discord, Email, etc.)
- StealthPlugin: Browser stealth patches
- CaptchaPlugin: CAPTCHA solving

Usage:
    from tokenade.plugin import SessionRefreshPlugin, PluginResult

    class MyOAuth2Plugin(SessionRefreshPlugin):
        API_VERSION = "1.0.0"
        name = "my-oauth2"
        version = "1.0.0"
        description = "OAuth2 refresh for MyService"

        def can_refresh(self, session: dict) -> bool:
            return "myservice.com" in str(session)

        def refresh(self, session: dict, credentials: dict) -> PluginResult:
            return PluginResult(success=True, data={"session": session})
"""

from tokenade.plugin.base import (
    PluginBase,
    SessionRefreshPlugin,
    SiteHandlerPlugin,
    ExportFormatPlugin,
    SessionValidatorPlugin,
    ProxyProviderPlugin,
    NotificationPlugin,
    StealthPlugin,
    CaptchaPlugin,
)
from tokenade.plugin.oauth_automation import OAuthAutomationPlugin
from tokenade.plugin.api import (
    API_VERSION,
    PluginResult,
    PluginConfig,
    PluginMetadata,
)
from tokenade.core.integration.plugin_loader import (
    PluginLoader,
    LoadedPlugin,
    get_or_create_shared_loader,
)

__all__ = [
    "PluginBase",
    "SessionRefreshPlugin",
    "SiteHandlerPlugin",
    "ExportFormatPlugin",
    "SessionValidatorPlugin",
    "ProxyProviderPlugin",
    "NotificationPlugin",
    "StealthPlugin",
    "CaptchaPlugin",
    "OAuthAutomationPlugin",
    "API_VERSION",
    "PluginResult",
    "PluginConfig",
    "PluginMetadata",
    "PluginLoader",
    "LoadedPlugin",
    "get_or_create_shared_loader",
]
