"""
Example: Custom Session Refresh Plugin

This plugin demonstrates how to create a session refresh plugin
for a hypothetical "MyService" API that uses API tokens.

To use this plugin:
1. Copy the my_custom_refresh/ directory to ~/.tokenade/plugins/
2. Run: tokenade plugin list
3. Run: tokenade refresh-browser -s myservice.tokenade --plugin my-custom-refresh \\
       --api-key YOUR_API_KEY

Plugin lifecycle:
1. tokenade calls can_refresh() to check if this plugin handles the session
2. If yes, tokenade calls refresh() with the session and credentials
3. The plugin refreshes the token and returns updated session data
"""

import json
import logging
import time
import urllib.request

from tokenade.plugin import SessionRefreshPlugin

logger = logging.getLogger(__name__)


class MyCustomRefreshPlugin(SessionRefreshPlugin):
    """Refresh sessions for MyService using API token rotation.

    This example shows:
    - How to declare which sessions this plugin handles
    - How to refresh tokens via API call
    - How to update session cookies/metadata
    - How to define CLI arguments for credentials
    """

    name = "my-custom-refresh"
    version = "1.0.0"
    description = "Example: Custom session refresh for MyService"
    author = "Tokenade Examples"

    # The API endpoint to rotate tokens
    TOKEN_URL = "https://api.myservice.com/v1/auth/rotate"

    def can_refresh(self, session: dict) -> bool:
        """Check if this session belongs to MyService.

        We check cookie domains and metadata to identify the service.
        """
        cookies = session.get("cookies", [])
        for cookie in cookies:
            domain = cookie.get("domain", "")
            if "myservice.com" in domain:
                return True

        # Also check metadata
        site_name = session.get("site_name", "")
        if site_name == "myservice":
            return True

        return False

    def refresh(self, session: dict, credentials: dict) -> dict:
        """Refresh the session by rotating the API token.

        Args:
            session: Current session with cookies and metadata
            credentials: Must contain 'api_key'

        Returns:
            Updated session with fresh token
        """
        api_key = credentials.get("api_key", "")
        if not api_key:
            raise ValueError("Missing required credential: api_key")

        # Call the API to rotate the token
        new_token = self._rotate_token(api_key)

        # Update session cookies
        cookies = session.get("cookies", [])
        for cookie in cookies:
            if cookie.get("name") == "session_token":
                cookie["value"] = new_token
                cookie["expires"] = int(time.time()) + 86400  # 24 hours
                break

        # Update metadata
        if "metadata" not in session:
            session["metadata"] = {}
        session["metadata"]["last_refreshed"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
        )
        session["metadata"]["refresh_count"] = (
            session["metadata"].get("refresh_count", 0) + 1
        )

        logger.info(f"Refreshed MyService session (token rotated)")
        return session

    def get_credentials_args(self):
        """Define the CLI arguments this plugin needs."""
        return [
            {
                "name": "--api-key",
                "help": "MyService API key for token rotation",
                "required": True,
                "type": str,
            },
        ]

    def _rotate_token(self, api_key: str) -> str:
        """Call the API to rotate the session token.

        In a real plugin, this would make an HTTP request to the
        service's token rotation endpoint.
        """
        # Example API call (disabled for safety):
        # data = json.dumps({"api_key": api_key}).encode()
        # req = urllib.request.Request(self.TOKEN_URL, data=data, headers={
        #     "Content-Type": "application/json",
        #     "Authorization": f"Bearer {api_key}",
        # })
        # with urllib.request.urlopen(req) as resp:
        #     return json.loads(resp.read())["new_token"]

        # For this example, return a placeholder
        return f"rotated_token_{int(time.time())}"
