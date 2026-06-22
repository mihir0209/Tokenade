"""
OAuth2 Session Refresh Plugin for Tokenade.

Refreshes sessions using OAuth2 authorization code + refresh token flow.
Supports Google, GitHub, and custom OAuth2 providers.

Usage:
    tokenade refresh-browser -s google.tokenade --plugin oauth2 \\
        --client-id XXX --client-secret YYY --refresh-token ZZZ

Or programmatically:
    from tokenade.plugin.oauth2.plugin import OAuth2Plugin
    plugin = OAuth2Plugin()
    if plugin.can_refresh(session):
        new_session = plugin.refresh(session, credentials)
"""

import json
import logging
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Provider configurations
PROVIDERS = {
    "google": {
        "token_url": "https://oauth2.googleapis.com/token",
        "revoke_url": "https://oauth2.googleapis.com/revoke",
        "scopes": ["openid", "email", "profile"],
        "cookie_domains": [".google.com", "accounts.google.com"],
        "token_field": "access_token",
        "refresh_field": "refresh_token",
    },
    "github": {
        "token_url": "https://github.com/login/oauth/access_token",
        "revoke_url": None,
        "scopes": ["read:user", "user:email"],
        "cookie_domains": [".github.com", "github.com"],
        "token_field": "access_token",
        "refresh_field": "refresh_token",
    },
}


class OAuth2Plugin:
    """OAuth2 session refresh plugin.

    Refreshes OAuth2 tokens and updates session cookies/tokens.
    """

    name = "oauth2"
    version = "1.0.0"
    description = "OAuth2 session refresh for Google, GitHub, and custom providers"
    author = "Tokenade"

    def can_refresh(self, session: dict) -> bool:
        """Check if this session has OAuth2 tokens that can be refreshed.

        Looks for refresh_token in session metadata or cookies.
        """
        # Check metadata for refresh_token
        metadata = session.get("metadata", {})
        if metadata.get("refresh_token"):
            return True
        if metadata.get("oauth2_refresh_token"):
            return True

        # Check cookies for known OAuth2 tokens
        cookies = session.get("cookies", [])
        for cookie in cookies:
            name = cookie.get("name", "")
            domain = cookie.get("domain", "")
            # Google refresh token cookie
            if name == "token" and ".google.com" in domain:
                return True
            # GitHub OAuth token
            if name == "oauth_token" and "github.com" in domain:
                return True

        return False

    def refresh(self, session: dict, credentials: dict) -> dict:
        """Refresh the OAuth2 session.

        Args:
            session: Current session data
            credentials: Must contain:
                - client_id: OAuth2 client ID
                - client_secret: OAuth2 client secret
                - refresh_token: OAuth2 refresh token
                - provider: Optional, auto-detected if not specified

        Returns:
            Updated session with fresh tokens

        Raises:
            ValueError: If required credentials are missing
            RuntimeError: If token refresh fails
        """
        client_id = credentials.get("client_id", "")
        client_secret = credentials.get("client_secret", "")
        refresh_token = credentials.get("refresh_token", "")
        provider = credentials.get("provider", self._detect_provider(session))

        if not client_id:
            raise ValueError("Missing required credential: client_id")
        if not client_secret:
            raise ValueError("Missing required credential: client_secret")
        if not refresh_token:
            raise ValueError("Missing required credential: refresh_token")

        if not provider:
            raise ValueError("Cannot detect OAuth2 provider. Specify 'provider' in credentials.")

        provider_config = PROVIDERS.get(provider)
        if not provider_config:
            # Custom provider — use credentials for URLs
            token_url = credentials.get("token_url", "")
            if not token_url:
                raise ValueError(f"Unknown provider '{provider}' and no token_url specified")
            provider_config = {
                "token_url": token_url,
                "cookie_domains": credentials.get("cookie_domains", []),
            }

        # Refresh the token
        token_data = self._exchange_refresh_token(
            token_url=provider_config["token_url"],
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            scopes=provider_config.get("scopes", []),
        )

        new_access_token = token_data.get("access_token", "")
        new_refresh_token = token_data.get("refresh_token", refresh_token)
        expires_in = token_data.get("expires_in", 3600)

        if not new_access_token:
            raise RuntimeError(f"Token refresh failed: {token_data}")

        # Update session metadata
        if "metadata" not in session:
            session["metadata"] = {}

        session["metadata"]["access_token"] = new_access_token
        session["metadata"]["refresh_token"] = new_refresh_token
        session["metadata"]["token_expires_at"] = int(time.time()) + expires_in
        session["metadata"]["token_type"] = token_data.get("token_type", "Bearer")
        session["metadata"]["last_refreshed"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
        )

        # Update cookies with new token
        self._update_token_cookie(session, provider, new_access_token, provider_config)

        logger.info(f"OAuth2 token refreshed for {provider} (expires in {expires_in}s)")
        return session

    def get_credentials_args(self) -> List[Dict[str, str]]:
        """Define CLI arguments needed for OAuth2 credentials."""
        return [
            {
                "name": "--client-id",
                "help": "OAuth2 client ID",
                "required": True,
                "type": str,
            },
            {
                "name": "--client-secret",
                "help": "OAuth2 client secret",
                "required": True,
                "type": str,
            },
            {
                "name": "--refresh-token",
                "help": "OAuth2 refresh token",
                "required": True,
                "type": str,
            },
            {
                "name": "--provider",
                "help": "OAuth2 provider (google, github, or custom)",
                "required": False,
                "type": str,
                "default": "",
            },
        ]

    def _detect_provider(self, session: dict) -> Optional[str]:
        """Auto-detect the OAuth2 provider from session cookies."""
        cookies = session.get("cookies", [])
        domains = {c.get("domain", "") for c in cookies}

        for domain in domains:
            if ".google.com" in domain or "accounts.google.com" in domain:
                return "google"
            if "github.com" in domain:
                return "github"

        return None

    def _exchange_refresh_token(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        scopes: List[str],
    ) -> dict:
        """Exchange a refresh token for a new access token."""
        data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }).encode("utf-8")

        req = urllib.request.Request(
            token_url,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Token refresh failed (HTTP {e.code}): {body}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Token refresh request failed: {e}") from e

    def _update_token_cookie(
        self,
        session: dict,
        provider: str,
        access_token: str,
        provider_config: dict,
    ) -> None:
        """Update or add the OAuth2 token cookie in the session."""
        cookies = session.get("cookies", [])
        cookie_domains = provider_config.get("cookie_domains", [])

        # Find and update existing token cookie
        updated = False
        for cookie in cookies:
            if provider == "google" and cookie.get("name") == "token":
                cookie["value"] = access_token
                cookie["expires"] = int(time.time()) + 3600
                updated = True
                break
            elif provider == "github" and cookie.get("name") == "oauth_token":
                cookie["value"] = access_token
                cookie["expires"] = int(time.time()) + 3600
                updated = True
                break

        # If no existing cookie, create one
        if not updated and cookie_domains:
            new_cookie = {
                "name": "token" if provider == "google" else "oauth_token",
                "value": access_token,
                "domain": cookie_domains[0],
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "Lax",
                "expires": int(time.time()) + 3600,
            }
            cookies.append(new_cookie)
            session["cookies"] = cookies
