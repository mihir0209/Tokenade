"""
OAuth 2.0 Token Refresh Engine.

Provides automated OAuth 2.0 token refresh using cookies transferred
from a legitimate browser session. This is the core mechanism that enables
cross-platform cookie portability without manual re-authentication.

The flow:
1. Export cookies from legitimate browser (Linux/macOS/Windows)
2. Transfer .tokenade file to target machine
3. Use cookies to authenticate and obtain OAuth tokens
4. When tokens expire, use refresh_token + token_endpoint to renew
5. Inject refreshed tokens/cookies into automated tool (Playwright/CDP)

This solves the fundamental paradox:
- Automated tools can't log into Google/Microsoft/etc.
- But cookies from a legitimate browser ARE the login
- OAuth refresh tokens let us维持 the session indefinitely
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


@dataclass
class OAuthConfig:
    """OAuth 2.0 configuration for a site."""
    token_endpoint: str
    client_id: str
    client_secret: str = ""
    scopes: List[str] = field(default_factory=lambda: ["openid", "profile", "email"])
    redirect_uri: str = "http://localhost:8080/callback"
    grant_type: str = "refresh_token"
    extra_params: Dict[str, str] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    use_client_secret_basic: bool = False

    def to_dict(self) -> Dict:
        return {
            "token_endpoint": self.token_endpoint,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scopes": self.scopes,
            "redirect_uri": self.redirect_uri,
            "grant_type": self.grant_type,
            "extra_params": self.extra_params,
            "headers": self.headers,
            "use_client_secret_basic": self.use_client_secret_basic,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "OAuthConfig":
        return cls(
            token_endpoint=data.get("token_endpoint", ""),
            client_id=data.get("client_id", ""),
            client_secret=data.get("client_secret", ""),
            scopes=data.get("scopes", ["openid", "profile", "email"]),
            redirect_uri=data.get("redirect_uri", "http://localhost:8080/callback"),
            grant_type=data.get("grant_type", "refresh_token"),
            extra_params=data.get("extra_params", {}),
            headers=data.get("headers", {}),
            use_client_secret_basic=data.get("use_client_secret_basic", False),
        )


@dataclass
class TokenPair:
    """Access and refresh token pair."""
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[float] = None
    token_type: str = "Bearer"
    scope: Optional[str] = None
    raw_response: Dict = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at

    @property
    def expires_in(self) -> Optional[int]:
        if self.expires_at is None:
            return None
        return max(0, int(self.expires_at - time.time()))

    def to_tokens_list(self) -> List[Dict]:
        """Convert to .tokenade tokens list format."""
        tokens = []
        if self.access_token:
            tokens.append({
                "type": "access_token",
                "value": self.access_token,
                "expires_at": self.expires_at,
            })
        if self.refresh_token:
            tokens.append({
                "type": "refresh_token",
                "value": self.refresh_token,
                "expires_at": None,
            })
        return tokens

    @classmethod
    def from_tokens_list(cls, tokens: List[Dict]) -> "TokenPair":
        """Create from .tokenade tokens list format."""
        access_token = ""
        refresh_token = None
        expires_at = None

        for t in tokens:
            if t.get("type") == "access_token":
                access_token = t.get("value", "")
                expires_at = t.get("expires_at")
            elif t.get("type") == "refresh_token":
                refresh_token = t.get("value")

        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )


@dataclass
class RefreshResult:
    """Result of an OAuth token refresh operation."""
    success: bool
    tokens: Optional[TokenPair] = None
    error: Optional[str] = None
    status_code: Optional[int] = None
    response_body: Optional[Dict] = None
    refreshed_at: Optional[str] = None
    site_name: str = ""
    duration_ms: float = 0.0


class OAuthTokenRefresher:
    """
    Refreshes OAuth 2.0 tokens using stored refresh tokens.

    Usage:
        config = OAuthConfig(
            token_endpoint="https://oauth2.googleapis.com/token",
            client_id="xxx.apps.googleusercontent.com",
            client_secret="GOCSPX-...",
        )
        refresher = OAuthTokenRefresher(config)
        result = refresher.refresh_token(old_refresh_token="1//0g...")
    """

    def __init__(self, config: OAuthConfig, timeout: float = 30.0):
        self.config = config
        self.timeout = timeout

    def refresh_token(self, old_refresh_token: str) -> RefreshResult:
        """
        Refresh an OAuth token using a refresh token.

        Args:
            old_refresh_token: The current refresh token

        Returns:
            RefreshResult with new tokens or error
        """
        start_time = time.time()

        try:
            response_data = self._make_refresh_request(old_refresh_token)

            if "access_token" not in response_data:
                return RefreshResult(
                    success=False,
                    error=f"No access_token in response: {response_data.get('error', 'unknown')}",
                    status_code=response_data.get("_status_code"),
                    response_body=response_data,
                    site_name=self.config.client_id,
                    duration_ms=(time.time() - start_time) * 1000,
                )

            new_refresh_token = response_data.get("refresh_token", old_refresh_token)
            expires_in = response_data.get("expires_in", 3600)

            tokens = TokenPair(
                access_token=response_data["access_token"],
                refresh_token=new_refresh_token,
                expires_at=time.time() + expires_in if expires_in else None,
                token_type=response_data.get("token_type", "Bearer"),
                scope=response_data.get("scope"),
                raw_response=response_data,
            )

            logger.info(f"OAuth token refreshed successfully (expires in {expires_in}s)")

            return RefreshResult(
                success=True,
                tokens=tokens,
                status_code=200,
                response_body=response_data,
                refreshed_at=datetime.now(timezone.utc).isoformat(),
                duration_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"OAuth token refresh failed: {e}")
            return RefreshResult(
                success=False,
                error=str(e),
                site_name=self.config.client_id,
                duration_ms=(time.time() - start_time) * 1000,
            )

    def _make_refresh_request(self, refresh_token: str) -> Dict:
        """Make the HTTP request to refresh the token."""
        import urllib.request
        import urllib.error

        data = {
            "grant_type": self.config.grant_type,
            "refresh_token": refresh_token,
            "client_id": self.config.client_id,
        }

        if self.config.client_secret:
            data["client_secret"] = self.config.client_secret

        if self.config.scopes:
            data["scope"] = " ".join(self.config.scopes)

        data.update(self.config.extra_params)

        encoded_data = urlencode(data).encode("utf-8")

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        headers.update(self.config.headers)

        req = urllib.request.Request(
            self.config.token_endpoint,
            data=encoded_data,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))
                response_data["_status_code"] = resp.status
                return response_data
        except urllib.error.HTTPError as e:
            body = {}
            try:
                body = json.loads(e.read().decode("utf-8"))
            except Exception:
                pass
            body["_status_code"] = e.code
            return body


class CookieToTokenConverter:
    """
    Converts browser cookies into OAuth tokens by authenticating
    to the token endpoint using the cookies.

    This is for platforms where:
    1. You have valid browser cookies
    2. You need an OAuth access_token for API access
    3. The platform supports cookie-based auth at the token endpoint

    Usage:
        converter = CookieToTokenConverter(config)
        result = converter.exchange_cookies(cookies)
    """

    def __init__(self, config: OAuthConfig, timeout: float = 30.0):
        self.config = config
        self.timeout = timeout

    def exchange_cookies(self, cookies: List[Dict]) -> RefreshResult:
        """
        Exchange browser cookies for OAuth tokens.

        Args:
            cookies: List of browser cookies

        Returns:
            RefreshResult with tokens or error
        """
        start_time = time.time()

        try:
            cookie_header = self._build_cookie_header(cookies)
            response_data = self._make_request_with_cookies(cookie_header)

            if "access_token" not in response_data:
                return RefreshResult(
                    success=False,
                    error=f"Cookie exchange failed: {response_data.get('error', 'unknown')}",
                    status_code=response_data.get("_status_code"),
                    response_body=response_data,
                    duration_ms=(time.time() - start_time) * 1000,
                )

            expires_in = response_data.get("expires_in", 3600)
            tokens = TokenPair(
                access_token=response_data["access_token"],
                refresh_token=response_data.get("refresh_token"),
                expires_at=time.time() + expires_in if expires_in else None,
                token_type=response_data.get("token_type", "Bearer"),
                scope=response_data.get("scope"),
                raw_response=response_data,
            )

            return RefreshResult(
                success=True,
                tokens=tokens,
                status_code=200,
                response_body=response_data,
                refreshed_at=datetime.now(timezone.utc).isoformat(),
                duration_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Cookie-to-token exchange failed: {e}")
            return RefreshResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )

    def _build_cookie_header(self, cookies: List[Dict]) -> str:
        """Build Cookie header from cookie list."""
        parts = []
        for cookie in cookies:
            name = cookie.get("name", "")
            value = cookie.get("value", "")
            if name:
                parts.append(f"{name}={value}")
        return "; ".join(parts)

    def _make_request_with_cookies(self, cookie_header: str) -> Dict:
        """Make HTTP request with cookies."""
        import urllib.request
        import urllib.error

        headers = {
            "Cookie": cookie_header,
            "Accept": "application/json",
        }
        headers.update(self.config.headers)

        req = urllib.request.Request(
            self.config.token_endpoint,
            headers=headers,
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))
                response_data["_status_code"] = resp.status
                return response_data
        except urllib.error.HTTPError as e:
            body = {}
            try:
                body = json.loads(e.read().decode("utf-8"))
            except Exception:
                pass
            body["_status_code"] = e.code
            return body


class SessionOAuthManager:
    """
    Manages OAuth tokens within a .tokenade session file.

    Handles:
    - Loading/storing OAuth config from session metadata
    - Extracting refresh tokens from session
    - Updating session with new tokens
    - Checking if refresh is needed

    Usage:
        manager = SessionOAuthManager("google.tokenade")
        if manager.has_oauth_config():
            if manager.needs_refresh():
                result = manager.refresh()
    """

    def __init__(self, session_file: str):
        self.session_file = Path(session_file)
        self._session: Optional[Dict] = None

    def load(self) -> Dict:
        """Load the session file."""
        if self._session is None:
            with open(self.session_file) as f:
                self._session = json.load(f)
        return self._session

    def save(self):
        """Save the session file."""
        if self._session is not None:
            with open(self.session_file, "w") as f:
                json.dump(self._session, f, indent=2)

    @property
    def session(self) -> Dict:
        return self.load()

    def has_oauth_config(self) -> bool:
        """Check if session has OAuth configuration."""
        return "oauth_config" in self.session

    def get_oauth_config(self) -> Optional[OAuthConfig]:
        """Get OAuth config from session."""
        config_data = self.session.get("oauth_config")
        if config_data:
            return OAuthConfig.from_dict(config_data)
        return None

    def set_oauth_config(self, config: OAuthConfig):
        """Set OAuth config in session."""
        self.session["oauth_config"] = config.to_dict()

    def get_refresh_token(self) -> Optional[str]:
        """Extract refresh token from session tokens."""
        tokens = self.session.get("tokens", [])
        for t in tokens:
            if t.get("type") == "refresh_token":
                return t.get("value")
        return None

    def get_access_token(self) -> Optional[str]:
        """Extract access token from session tokens."""
        tokens = self.session.get("tokens", [])
        for t in tokens:
            if t.get("type") == "access_token":
                return t.get("value")
        return None

    def needs_refresh(self) -> bool:
        """Check if tokens need refreshing."""
        tokens = self.session.get("tokens", [])
        token_pair = TokenPair.from_tokens_list(tokens)
        return token_pair.is_expired

    def get_token_expiry(self) -> Optional[float]:
        """Get access token expiry timestamp."""
        tokens = self.session.get("tokens", [])
        for t in tokens:
            if t.get("type") == "access_token":
                return t.get("expires_at")
        return None

    def update_tokens(self, tokens: TokenPair):
        """Update session with new tokens."""
        existing = self.session.get("tokens", [])
        new_tokens = tokens.to_tokens_list()

        merged = []
        seen_types = set()
        for t in new_tokens:
            merged.append(t)
            seen_types.add(t.get("type"))

        for t in existing:
            if t.get("type") not in seen_types:
                merged.append(t)

        self.session["tokens"] = merged

        meta = self.session.get("metadata", {})
        meta["last_refreshed_at"] = datetime.now(timezone.utc).isoformat()
        meta["refresh_count"] = meta.get("refresh_count", 0) + 1
        self.session["metadata"] = meta

    def refresh(self) -> RefreshResult:
        """
        Refresh OAuth tokens using stored refresh token.

        Returns:
            RefreshResult with new tokens or error
        """
        config = self.get_oauth_config()
        if not config:
            return RefreshResult(
                success=False,
                error="No OAuth config in session",
                site_name=self.session.get("site_name", "unknown"),
            )

        refresh_token = self.get_refresh_token()
        if not refresh_token:
            return RefreshResult(
                success=False,
                error="No refresh token in session",
                site_name=self.session.get("site_name", "unknown"),
            )

        refresher = OAuthTokenRefresher(config)
        result = refresher.refresh_token(refresh_token)

        if result.success and result.tokens:
            self.update_tokens(result.tokens)
            self.save()
            result.site_name = self.session.get("site_name", "unknown")

        return result

    def get_status(self) -> Dict:
        """Get current token status."""
        tokens = self.session.get("tokens", [])
        token_pair = TokenPair.from_tokens_list(tokens)
        config = self.get_oauth_config()

        return {
            "has_oauth_config": config is not None,
            "has_refresh_token": self.get_refresh_token() is not None,
            "has_access_token": self.get_access_token() is not None,
            "access_token_expired": token_pair.is_expired,
            "expires_in": token_pair.expires_in,
            "expires_at": token_pair.expires_at,
            "refresh_count": self.session.get("metadata", {}).get("refresh_count", 0),
            "site_name": self.session.get("site_name", "unknown"),
        }


# Pre-configured OAuth configs for known sites
KNOWN_OAUTH_CONFIGS: Dict[str, OAuthConfig] = {
    "google": OAuthConfig(
        token_endpoint="https://oauth2.googleapis.com/token",
        client_id="",  # User must provide
        client_secret="",
        scopes=["openid", "email", "profile"],
    ),
    "github": OAuthConfig(
        token_endpoint="https://github.com/login/oauth/access_token",
        client_id="",
        client_secret="",
        scopes=["repo", "read:user"],
        headers={"Accept": "application/json"},
    ),
    "discord": OAuthConfig(
        token_endpoint="https://discord.com/api/oauth2/token",
        client_id="",
        client_secret="",
        scopes=["identify", "email", "guilds"],
    ),
    "reddit": OAuthConfig(
        token_endpoint="https://www.reddit.com/api/v1/access_token",
        client_id="",
        client_secret="",
        scopes=["identity", "read"],
        use_client_secret_basic=True,
    ),
}


def get_oauth_config_for_site(site_name: str) -> Optional[OAuthConfig]:
    """Get pre-configured OAuth config for a known site."""
    return KNOWN_OAUTH_CONFIGS.get(site_name.lower())


def create_oauth_config(
    site_name: str,
    client_id: str,
    client_secret: str = "",
    token_endpoint: str = "",
    scopes: Optional[List[str]] = None,
) -> OAuthConfig:
    """
    Create an OAuth config, using pre-configured defaults if available.

    Args:
        site_name: Site name (e.g., "google", "github")
        client_id: OAuth client ID
        client_secret: OAuth client secret
        token_endpoint: Token endpoint URL (overrides pre-configured)
        scopes: OAuth scopes (overrides pre-configured)

    Returns:
        OAuthConfig
    """
    base = get_oauth_config_for_site(site_name) or OAuthConfig(
        token_endpoint="",
        client_id="",
    )

    return OAuthConfig(
        token_endpoint=token_endpoint or base.token_endpoint,
        client_id=client_id or base.client_id,
        client_secret=client_secret or base.client_secret,
        scopes=scopes or base.scopes,
        redirect_uri=base.redirect_uri,
        grant_type=base.grant_type,
        extra_params=base.extra_params,
        headers=base.headers,
        use_client_secret_basic=base.use_client_secret_basic,
    )
