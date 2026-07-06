"""
Abstract base classes for Tokenade plugins (API v1.0).

All plugins must subclass PluginBase and implement the required methods.
Plugin types add specific capabilities on top of the base.

Plugin Manifest (plugin.json):
{
    "name": "my-plugin",
    "version": "1.0.0",
    "api_version": "1.0.0",
    "description": "Does something useful",
    "author": "Your Name",
    "type": "session_refresh",
    "entry_point": "plugin.py",
    "entry_class": "MyPlugin",
    "dependencies": []
}
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from tokenade.plugin.api import API_VERSION, PluginResult, PluginConfig


class PluginBase(ABC):
    """Base class for all Tokenade plugins (API v1.0).

    Every plugin MUST:
    - Subclass PluginBase (or a subclass of it)
    - Set API_VERSION = "1.0.0"
    - Set name, version, description

    Lifecycle hooks:
    - on_load(): Called when plugin is loaded
    - on_configure(config): Called with PluginConfig after load
    - on_unload(): Called when plugin is unloaded

    All methods should return PluginResult for consistent error handling.
    """

    API_VERSION: str = "1.0.0"
    name: str = ""
    version: str = "0.0.0"
    description: str = ""
    author: str = ""
    dependencies: List[str] = []

    def __init__(self):
        self._config: Optional[PluginConfig] = None

    def on_load(self) -> None:
        """Called when the plugin is loaded. Override for initialization."""

    def on_unload(self) -> None:
        """Called when the plugin is unloaded. Override for cleanup."""

    def on_configure(self, config: PluginConfig) -> None:
        """Called with PluginConfig after load. Override to validate config."""
        self._config = config

    def get_info(self) -> Dict[str, Any]:
        """Return plugin metadata."""
        return {
            "name": self.name,
            "version": self.version,
            "api_version": self.API_VERSION,
            "description": self.description,
            "author": self.author,
            "dependencies": self.dependencies,
        }

    def get_metadata(self):
        """Return PluginMetadata object."""
        from tokenade.plugin.api import PluginMetadata
        return PluginMetadata(
            name=self.name,
            version=self.version,
            api_version=self.API_VERSION,
            author=self.author,
            description=self.description,
            dependencies=self.dependencies,
        )

    def health_check(self) -> bool:
        """Check if the plugin is healthy. Override for custom checks."""
        return True


class SessionRefreshPlugin(PluginBase):
    """Plugin that can refresh sessions (OAuth2, API tokens, etc.).

    Implement can_refresh() to declare which sessions this plugin handles,
    and refresh() to perform the actual refresh.

    Example:
        class GoogleOAuth2Plugin(SessionRefreshPlugin):
            name = "google-oauth2"
            version = "1.0.0"
            description = "Refresh Google sessions via OAuth2"

            def can_refresh(self, session):
                return any(c.get("domain", "").endswith(".google.com")
                          for c in session.get("cookies", []))

            def refresh(self, session, credentials):
                # Use refresh_token to get new access_token
                return PluginResult(success=True, data={"session": session})
    """

    @abstractmethod
    def can_refresh(self, session: dict) -> bool:
        """Check if this plugin can refresh the given session.

        Args:
            session: The .tokenade session data (cookies, metadata, etc.)

        Returns:
            True if this plugin can handle the session
        """

    @abstractmethod
    def refresh(self, session: dict, credentials: dict) -> PluginResult:
        """Refresh the session.

        Args:
            session: Current session data
            credentials: Plugin-specific credentials

        Returns:
            PluginResult with data={"session": updated_session}
        """

    def get_credentials_args(self) -> List[Dict[str, str]]:
        """Define CLI arguments needed for credentials.

        Returns:
            List of dicts with keys: name, help, required, type
        """
        return []


class SiteHandlerPlugin(PluginBase):
    """Plugin that handles a specific website's extraction/login flow.

    Use this for sites that need custom handling beyond standard cookie export.
    """

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this plugin handles the given URL.

        Args:
            url: The target URL

        Returns:
            True if this plugin can handle the site
        """

    @abstractmethod
    def extract_session(self, _browser_context: Any, url: str) -> dict:
        """Extract session data from a browser context.

        Args:
            browser_context: The browser context (Playwright or CDP)
            url: The target URL

        Returns:
            Session dict with cookies, localStorage, etc.
        """

    @abstractmethod
    def inject_session(self, _browser_context: Any, session: dict) -> bool:
        """Inject session data into a browser context.

        Args:
            browser_context: The browser context
            session: Session data to inject

        Returns:
            True if injection was successful
        """


class ExportFormatPlugin(PluginBase):
    """Plugin that adds a custom export format."""

    @abstractmethod
    def get_format_name(self) -> str:
        """Return the format name (e.g., 'curl', 'python-requests')."""

    @abstractmethod
    def export(self, session: dict, output_path: str) -> str:
        """Export session in the custom format.

        Args:
            session: Session data
            output_path: Where to write the output

        Returns:
            Path to the exported file
        """


class SessionValidatorPlugin(PluginBase):
    """Plugin that validates session health with custom rules."""

    @abstractmethod
    def validate(self, session: dict) -> Dict[str, Any]:
        """Validate a session.

        Args:
            session: Session data to validate

        Returns:
            Dict with keys: valid (bool), score (float 0-100), issues (list of str)
        """


class StealthPlugin(PluginBase):
    """Plugin that provides browser stealth patches.

    Implement get_patches() to return JavaScript injection scripts
    that bypass bot detection systems.

    Example:
        class BasicStealthPlugin(StealthPlugin):
            name = "stealth-basic"
            version = "1.0.0"
            description = "Basic stealth patches"

            def get_patches(self):
                return ["navigator.webdriver = undefined"]
    """

    @abstractmethod
    def get_patches(self) -> List[str]:
        """Return list of JavaScript patches to inject.

        Returns:
            List of JavaScript strings to inject into pages
        """

    def get_tls_config(self) -> Optional[Dict[str, Any]]:
        """Return TLS fingerprint configuration (optional).

        Returns:
            Dict with keys: impersonate, ciphers, extensions, or None
        """
        return None

    def get_browser_args(self) -> List[str]:
        """Return additional browser launch arguments (optional).

        Returns:
            List of Chrome/Firefox command-line arguments
        """
        return []


class ProxyPlugin(PluginBase):
    """Plugin that provides proxy providers.

    Implement get_proxy() to return a proxy for session operations.

    Example:
        class MyProxyPlugin(ProxyPlugin):
            name = "my-proxy"
            version = "1.0.0"
            description = "Custom proxy provider"

            def get_proxy(self, session):
                return {"host": "proxy.example.com", "port": 8080}
    """

    @abstractmethod
    def get_proxy(self, session: Optional[Dict] = None) -> Dict[str, Any]:
        """Get a proxy for the given session.

        Args:
            session: Optional session data for geo-matching

        Returns:
            Dict with keys: host, port, protocol, username (opt), password (opt)
        """

    def check_health(self, proxy: Dict[str, Any]) -> bool:
        """Check if a proxy is healthy.

        Args:
            proxy: Proxy config dict

        Returns:
            True if proxy is healthy
        """
        return True

    def rotate(self) -> Dict[str, Any]:
        """Get the next proxy in rotation.

        Returns:
            Next proxy config dict
        """
        return self.get_proxy()


class CaptchaPlugin(PluginBase):
    """Plugin that solves CAPTCHAs.

    Implement solve() to solve a specific CAPTCHA type.

    Example:
        class TwoCaptchaPlugin(CaptchaPlugin):
            name = "captcha-2captcha"
            version = "1.0.0"
            description = "2Captcha integration"

            def get_supported_types(self):
                return ["recaptcha_v2", "hcaptcha", "turnstile"]

            def solve(self, captcha_type, site_key, page_url):
                # Call 2Captcha API
                return {"success": True, "token": "..."}
    """

    @abstractmethod
    def get_supported_types(self) -> List[str]:
        """Return list of supported CAPTCHA types.

        Returns:
            List of CAPTCHA type strings (e.g., "recaptcha_v2", "hcaptcha", "turnstile")
        """

    @abstractmethod
    def solve(self, captcha_type: str, site_key: Optional[str] = None,
              _page_url: Optional[str] = None) -> Dict[str, Any]:
        """Solve a CAPTCHA.

        Args:
            captcha_type: Type of CAPTCHA (e.g., "recaptcha_v2")
            site_key: Site key from the CAPTCHA widget
            page_url: URL of the page with the CAPTCHA

        Returns:
            Dict with keys: success (bool), token (str), error (str, optional)
        """

    def get_balance(self) -> Optional[float]:
        """Get remaining balance for paid CAPTCHA services (optional).

        Returns:
            Balance amount or None if not applicable
        """


class ProxyProviderPlugin(PluginBase):
    """Plugin for commercial proxy providers (AnyIP, BrightData, etc.).

    Providers implement this to integrate their proxy service with Tokenade.
    Users install via: tokenade plugin install anyip-proxy

    Example:
        class AnyIPProxyPlugin(ProxyProviderPlugin):
            API_VERSION = "1.0.0"
            name = "anyip-proxy"
            version = "1.0.0"
            description = "AnyIP residential proxy"
            author = "AnyIP Inc."
            supports_sticky = True
            supports_rotation = True
            countries = ["US", "UK", "DE"]

            def get_proxy(self, options=None):
                return PluginResult(success=True, data={
                    "host": "proxy.anyip.io", "port": 1080,
                    "protocol": "http", "username": "user", "password": "pass"
                })

            def rotate(self, session_id=None):
                return PluginResult(success=True, data={
                    "host": "proxy2.anyip.io", "port": 1080,
                    "protocol": "http", "username": "user", "password": "pass"
                })
    """

    supports_sticky: bool = False
    supports_rotation: bool = False
    countries: List[str] = []
    website: str = ""

    @abstractmethod
    def get_proxy(self, options: Optional[Dict[str, Any]] = None) -> PluginResult:
        """Get a proxy.

        Args:
            options: Provider-specific options (country, session_id, etc.)

        Returns:
            PluginResult with data={"host", "port", "protocol", "username", "password"}
        """

    @abstractmethod
    def rotate(self, session_id: Optional[str] = None) -> PluginResult:
        """Rotate to a new proxy.

        Args:
            session_id: Optional session ID for sticky rotation

        Returns:
            PluginResult with new proxy config
        """

    def check_health(self, proxy: Dict[str, Any]) -> PluginResult:
        """Check if a proxy is healthy.

        Args:
            proxy: Proxy config dict

        Returns:
            PluginResult with data={"healthy": bool, "latency_ms": float}
        """
        return PluginResult(success=True, data={"healthy": True, "latency_ms": 0})

    def get_provider_info(self) -> Dict[str, Any]:
        """Return provider information."""
        return {
            "provider": self.name,
            "website": self.website,
            "supports_sticky": self.supports_sticky,
            "supports_rotation": self.supports_rotation,
            "countries": self.countries,
        }


class NotificationPlugin(PluginBase):
    """Plugin for notification providers (Slack, Discord, Email, etc.).

    Providers implement this to send notifications on session events.

    Example:
        class SlackNotifyPlugin(NotificationPlugin):
            API_VERSION = "1.0.0"
            name = "slack-notify"
            version = "1.0.0"
            description = "Slack notifications"
            author = "Tokenade Team"

            def send(self, event, data):
                # Send Slack message
                return PluginResult(success=True)

            def get_supported_events(self):
                return ["session_expired", "refresh_failed", "refresh_success"]
    """

    @abstractmethod
    def send(self, event: str, data: Dict[str, Any]) -> PluginResult:
        """Send a notification.

        Args:
            event: Event type (session_expired, refresh_failed, etc.)
            data: Event data

        Returns:
            PluginResult
        """

    @abstractmethod
    def get_supported_events(self) -> List[str]:
        """Return list of supported event types."""
        return None
