"""
Abstract base classes for Tokenade plugins.

All plugins must subclass PluginBase and implement the required methods.
Plugin types add specific capabilities on top of the base.

Plugin Manifest (plugin.json):
{
    "name": "my-plugin",
    "version": "1.0.0",
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


class PluginBase(ABC):
    """Base class for all Tokenade plugins.

    Every plugin must subclass this and implement at minimum:
    - name: str
    - version: str
    - description: str

    Optional lifecycle hooks:
    - on_load(): Called when plugin is loaded
    - on_unload(): Called when plugin is unloaded
    """

    name: str = ""
    version: str = "0.0.0"
    description: str = ""
    author: str = ""
    dependencies: List[str] = []

    def on_load(self) -> None:
        """Called when the plugin is loaded. Override for initialization."""

    def on_unload(self) -> None:
        """Called when the plugin is unloaded. Override for cleanup."""

    def get_info(self) -> Dict[str, Any]:
        """Return plugin metadata."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "dependencies": self.dependencies,
        }

    def get_info(self) -> Dict[str, Any]:
        """Return plugin metadata."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "dependencies": self.dependencies,
        }


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
                return session
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
    def refresh(self, session: dict, credentials: dict) -> dict:
        """Refresh the session.

        Args:
            session: Current session data
            credentials: Plugin-specific credentials (client_id, client_secret, tokens, etc.)

        Returns:
            Updated session data with fresh cookies/tokens
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
    def extract_session(self, browser_context: Any, url: str) -> dict:
        """Extract session data from a browser context.

        Args:
            browser_context: The browser context (Playwright or CDP)
            url: The target URL

        Returns:
            Session dict with cookies, localStorage, etc.
        """

    @abstractmethod
    def inject_session(self, browser_context: Any, session: dict) -> bool:
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
              page_url: Optional[str] = None) -> Dict[str, Any]:
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
        return None
