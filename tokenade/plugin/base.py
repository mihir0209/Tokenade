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
