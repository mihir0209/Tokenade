"""Example: Session Refresh Plugin

Refreshes sessions using OAuth2 refresh tokens or cookie-based refresh.

Install:
    cp -r my-refresh ~/.tokenade/plugins/my-refresh
    tokenade plugin configure my-refresh --set client_id=XXX client_secret=YYY
"""

from typing import Any, Dict, Optional
from tokenade.plugin.base import SessionRefreshPlugin


class MySessionRefreshPlugin(SessionRefreshPlugin):
    """Example session refresh plugin."""

    name = "my-refresh"
    version = "1.0.0"
    description = "Example session refresh plugin"

    def can_refresh(self, session: Dict[str, Any]) -> bool:
        """Check if this plugin can refresh the given session."""
        # Check if session has a stored refresh token
        return bool(session.get("refresh_token") or session.get("auth_status") == "oauth2")

    def refresh(self, session: Dict[str, Any], credentials: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Refresh the session. Returns updated session dict."""
        # In production: use refresh token to get new access token
        # For the example, just mark it as refreshed
        session["refreshed_by"] = self.name
        session["metadata"] = session.get("metadata", {})
        session["metadata"]["refresh_count"] = session["metadata"].get("refresh_count", 0) + 1
        return session

    def get_credentials_args(self):
        """Return list of required credential arguments."""
        return [
            {"name": "--client-id", "required": False, "description": "OAuth2 client ID"},
            {"name": "--client-secret", "required": False, "description": "OAuth2 client secret"},
        ]
