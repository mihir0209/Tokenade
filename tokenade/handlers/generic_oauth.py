"""
Generic OAuth2 Handler - Reusable handler for OAuth2-based sites.

Supports any OAuth2 provider with configurable endpoints and scopes.
"""

import json
import logging
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode, parse_qs, urlparse

from .base import SiteHandler, AuthStatus, TokenType, ExtractedToken, SessionData

logger = logging.getLogger(__name__)


class OAuth2Config:
    """Configuration for OAuth2 flows."""
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        authorization_endpoint: str,
        token_endpoint: str,
        redirect_uri: str = "http://localhost:8080/callback",
        scopes: List[str] = None,
        pkce_enabled: bool = True,
        refresh_token_enabled: bool = True,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.authorization_endpoint = authorization_endpoint
        self.token_endpoint = token_endpoint
        self.redirect_uri = redirect_uri
        self.scopes = scopes or ["openid", "profile", "email"]
        self.pkce_enabled = pkce_enabled
        self.refresh_token_enabled = refresh_token_enabled


class GenericOAuth2Handler(SiteHandler):
    """
    Generic OAuth2 handler that can be configured for any OAuth2 provider.
    
    Supports:
    - Authorization Code flow (with optional PKCE)
    - Refresh token rotation
    - Token validation via introspection
    """
    
    SITE_NAME = "generic_oauth"
    DOMAINS = []
    LOGIN_URL = ""
    DASHBOARD_URL = ""
    
    # OAuth2-specific critical cookies
    CRITICAL_COOKIES = ["session", "oauth_state", "pkce_verifier"]
    
    def __init__(self, browser_manager=None, config: Optional[Dict] = None):
        super().__init__(browser_manager, config)
        self.oauth_config: Optional[OAuth2Config] = None
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expires_at: Optional[int] = None
        
        if config and "oauth_config" in config:
            self.oauth_config = OAuth2Config(**config["oauth_config"])
    
    def set_oauth_config(self, config: OAuth2Config):
        """Set OAuth2 configuration."""
        self.oauth_config = config
        self.DOMAINS = [urlparse(config.authorization_endpoint).netloc]
        self.LOGIN_URL = config.authorization_endpoint
    
    def check_auth_status(self) -> AuthStatus:
        """Check if user has valid OAuth2 tokens."""
        if not self.browser:
            return AuthStatus.ERROR
        
        try:
            # Check for access token in localStorage/sessionStorage
            token = self._evaluate("""
                () => {
                    // Check multiple storage locations
                    const locations = [
                        localStorage.getItem('access_token'),
                        localStorage.getItem('oauth_token'),
                        sessionStorage.getItem('access_token'),
                        sessionStorage.getItem('oauth_token'),
                    ];
                    return locations.find(t => t !== null) || null;
                }
            """)
            
            if token:
                self._access_token = token
                
                # Validate token by making a test request
                if self._validate_token(token):
                    return AuthStatus.LOGGED_IN
                else:
                    # Token exists but may be expired
                    if self._refresh_token and self.oauth_config and self.oauth_config.refresh_token_enabled:
                        return AuthStatus.SESSION_EXPIRED  # Can refresh
                    return AuthStatus.LOGGED_OUT
            
            # Check for session cookies
            cookies = self._get_cookies()
            session_cookies = [c for c in cookies if c.get("name") in self.CRITICAL_COOKIES]
            
            if session_cookies:
                return AuthStatus.LOGGED_IN
            
            return AuthStatus.LOGGED_OUT
            
        except Exception as e:
            logger.error(f"Auth check failed: {e}")
            return AuthStatus.ERROR
    
    def extract_tokens(self) -> List[ExtractedToken]:
        """Extract OAuth2 tokens from browser storage."""
        tokens = []
        
        if not self.browser:
            return tokens
        
        try:
            # Extract access token
            access_token = self._evaluate("""
                () => {
                    const keys = ['access_token', 'oauth_token', 'token'];
                    for (const key of keys) {
                        const val = localStorage.getItem(key) || sessionStorage.getItem(key);
                        if (val) return { key, value: val };
                    }
                    return null;
                }
            """)
            
            if access_token:
                tokens.append(ExtractedToken(
                    token_type=TokenType.ACCESS_TOKEN,
                    value=access_token["value"],
                    domain=self.DOMAINS[0] if self.DOMAINS else "",
                    metadata={"storage_key": access_token["key"]},
                ))
                self._access_token = access_token["value"]
            
            # Extract refresh token
            refresh_token = self._evaluate("""
                () => {
                    const val = localStorage.getItem('refresh_token') || sessionStorage.getItem('refresh_token');
                    return val;
                }
            """)
            
            if refresh_token:
                tokens.append(ExtractedToken(
                    token_type=TokenType.REFRESH_TOKEN,
                    value=refresh_token,
                    domain=self.DOMAINS[0] if self.DOMAINS else "",
                ))
                self._refresh_token = refresh_token
            
            # Extract token expiry
            expires_at = self._evaluate("""
                () => {
                    const val = localStorage.getItem('expires_at') || sessionStorage.getItem('expires_at');
                    return val ? parseInt(val) : null;
                }
            """)
            
            if expires_at and tokens:
                tokens[0].expires_at = expires_at
                self._token_expires_at = expires_at
            
        except Exception as e:
            logger.error(f"Token extraction failed: {e}")
        
        return tokens
    
    def extract_cookies(self) -> List[Dict]:
        """Extract session cookies."""
        if not self.browser:
            return []
        
        try:
            all_cookies = self._get_cookies()
            # Filter for OAuth-related cookies
            oauth_cookies = [
                c for c in all_cookies 
                if any(keyword in c.get("name", "").lower() for keyword in 
                       ["session", "oauth", "auth", "token", "state", "pkce"])
            ]
            return oauth_cookies
        except Exception as e:
            logger.error(f"Cookie extraction failed: {e}")
            return []
    
    def validate_session(self, cookies: List[Dict]) -> bool:
        """Validate OAuth2 session by checking token validity."""
        if not cookies:
            return False
        
        # Check for critical cookies
        cookie_names = {c.get("name", "") for c in cookies}
        has_critical = any(name in cookie_names for name in self.CRITICAL_COOKIES)
        
        return has_critical
    
    def inject_session(self, session_data: SessionData) -> bool:
        """Inject OAuth2 session into browser."""
        if not self.browser:
            logger.error("Browser manager not set")
            return False
        
        try:
            # Inject cookies
            if session_data.cookies:
                self._add_cookies(session_data.cookies)
                logger.info(f"Injected {len(session_data.cookies)} cookies")
            
            # Inject tokens into storage
            for token in session_data.tokens:
                if token.token_type == TokenType.ACCESS_TOKEN:
                    self._evaluate(f"""
                        () => {{
                            localStorage.setItem('access_token', '{token.value}');
                            sessionStorage.setItem('access_token', '{token.value}');
                        }}
                    """)
                    logger.info("Injected access token into storage")
                
                elif token.token_type == TokenType.REFRESH_TOKEN:
                    self._evaluate(f"""
                        () => {{
                            localStorage.setItem('refresh_token', '{token.value}');
                        }}
                    """)
                    logger.info("Injected refresh token into storage")
            
            return True
            
        except Exception as e:
            logger.error(f"Session injection failed: {e}")
            return False
    
    def refresh_access_token(self) -> Optional[str]:
        """Refresh access token using refresh token."""
        if not self._refresh_token or not self.oauth_config:
            logger.warning("No refresh token or OAuth config available")
            return None
        
        try:
            import requests
            
            response = requests.post(
                self.oauth_config.token_endpoint,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                    "client_id": self.oauth_config.client_id,
                    "client_secret": self.oauth_config.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            
            if response.status_code == 200:
                data = response.json()
                new_token = data.get("access_token")
                if new_token:
                    self._access_token = new_token
                    self._token_expires_at = int(time.time()) + data.get("expires_in", 3600)
                    logger.info("Access token refreshed successfully")
                    return new_token
            
            logger.error(f"Token refresh failed: {response.status_code}")
            return None
            
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return None
    
    def _validate_token(self, token: str) -> bool:
        """Validate token by checking expiry or making introspection request."""
        # Simple expiry check
        if self._token_expires_at and time.time() > self._token_expires_at:
            return False
        
        # If we have an introspection endpoint, use it
        if self.oauth_config and hasattr(self.oauth_config, 'introspection_endpoint'):
            try:
                import requests
                response = requests.post(
                    self.oauth_config.introspection_endpoint,
                    data={"token": token},
                    auth=(self.oauth_config.client_id, self.oauth_config.client_secret),
                    timeout=10,
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("active", False)
            except Exception:
                pass
        
        # Default: assume valid if not expired
        return True
    
    def build_authorization_url(self, state: Optional[str] = None) -> str:
        """Build OAuth2 authorization URL."""
        if not self.oauth_config:
            raise ValueError("OAuth config not set")
        
        params = {
            "client_id": self.oauth_config.client_id,
            "redirect_uri": self.oauth_config.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.oauth_config.scopes),
        }
        
        if state:
            params["state"] = state
        
        if self.oauth_config.pkce_enabled:
            import secrets
            import hashlib
            import base64
            
            # Generate PKCE verifier
            verifier = base64.urlsafe_b64encode(
                secrets.token_bytes(32)
            ).decode('utf-8').rstrip('=')
            
            challenge = base64.urlsafe_b64encode(
                hashlib.sha256(verifier.encode()).digest()
            ).decode('utf-8').rstrip('=')
            
            params["code_challenge"] = challenge
            params["code_challenge_method"] = "S256"
            
            # Store verifier
            self._pkce_verifier = verifier
        
        return f"{self.oauth_config.authorization_endpoint}?{urlencode(params)}"


# Pre-configured handlers for common OAuth2 providers

class DiscordOAuth2Handler(GenericOAuth2Handler):
    """Discord OAuth2 handler."""
    
    SITE_NAME = "discord"
    DOMAINS = ["discord.com", "discordapp.com"]
    LOGIN_URL = "https://discord.com/login"
    DASHBOARD_URL = "https://discord.com/channels/@me"
    
    CRITICAL_COOKIES = ["__dcfduid", "__sdcfduid", "authorization", "session"]
    
    def __init__(self, browser_manager=None, config: Optional[Dict] = None):
        super().__init__(browser_manager, config)
        self.oauth_config = OAuth2Config(
            client_id=config.get("client_id", "") if config else "",
            client_secret=config.get("client_secret", "") if config else "",
            authorization_endpoint="https://discord.com/api/oauth2/authorize",
            token_endpoint="https://discord.com/api/oauth2/token",
            redirect_uri="http://localhost:8080/callback",
            scopes=["identify", "email", "guilds"],
            pkce_enabled=True,
        )
    
    def check_auth_status(self) -> AuthStatus:
        """Check Discord auth status via API."""
        if not self.browser:
            return AuthStatus.ERROR
        
        try:
            # Discord stores token in localStorage
            token = self._evaluate("""
                () => {
                    const token = localStorage.getItem('token');
                    return token;
                }
            """)
            
            if token:
                # Validate by checking user info
                import requests
                response = requests.get(
                    "https://discord.com/api/v10/users/@me",
                    headers={"Authorization": token},
                    timeout=10,
                )
                
                if response.status_code == 200:
                    self._access_token = token
                    return AuthStatus.LOGGED_IN
                elif response.status_code == 401:
                    return AuthStatus.LOGGED_OUT
            
            return AuthStatus.LOGGED_OUT
            
        except Exception as e:
            logger.error(f"Discord auth check failed: {e}")
            return AuthStatus.ERROR
    
    def extract_tokens(self) -> List[ExtractedToken]:
        """Extract Discord token from localStorage."""
        tokens = []
        
        if not self.browser:
            return tokens
        
        try:
            token = self._evaluate("""
                () => {
                    return localStorage.getItem('token');
                }
            """)
            
            if token:
                tokens.append(ExtractedToken(
                    token_type=TokenType.BEARER_TOKEN,
                    value=token,
                    domain="discord.com",
                ))
                self._access_token = token
            
        except Exception as e:
            logger.error(f"Discord token extraction failed: {e}")
        
        return tokens
    
    def inject_session(self, session_data: SessionData) -> bool:
        """Inject Discord session."""
        if not self.browser:
            return False
        
        try:
            # Inject token into localStorage
            for token in session_data.tokens:
                if token.token_type in (TokenType.BEARER_TOKEN, TokenType.ACCESS_TOKEN):
                    self._evaluate(f"""
                        () => {{
                            localStorage.setItem('token', '{token.value}');
                            // Trigger Discord's auth state update
                            window.dispatchEvent(new Event('storage'));
                        }}
                    """)
                    logger.info("Injected Discord token")
            
            # Inject cookies
            if session_data.cookies:
                self._add_cookies(session_data.cookies)
            
            return True
            
        except Exception as e:
            logger.error(f"Discord session injection failed: {e}")
            return False


class RedditOAuth2Handler(GenericOAuth2Handler):
    """Reddit OAuth2 handler."""
    
    SITE_NAME = "reddit"
    DOMAINS = ["reddit.com", "www.reddit.com"]
    LOGIN_URL = "https://www.reddit.com/login"
    DASHBOARD_URL = "https://www.reddit.com"
    
    CRITICAL_COOKIES = ["reddit_session", "token", "refresh_token"]
    
    def __init__(self, browser_manager=None, config: Optional[Dict] = None):
        super().__init__(browser_manager, config)
        self.oauth_config = OAuth2Config(
            client_id=config.get("client_id", "") if config else "",
            client_secret=config.get("client_secret", "") if config else "",
            authorization_endpoint="https://www.reddit.com/api/v1/authorize",
            token_endpoint="https://www.reddit.com/api/v1/access_token",
            redirect_uri="http://localhost:8080/callback",
            scopes=["identity", "read", "submit"],
            pkce_enabled=False,  # Reddit uses standard auth code flow
        )
    
    def check_auth_status(self) -> AuthStatus:
        """Check Reddit auth status."""
        if not self.browser:
            return AuthStatus.ERROR
        
        try:
            # Check for Reddit session cookie
            cookies = self._get_cookies(["https://www.reddit.com"])
            session_cookie = next(
                (c for c in cookies if c.get("name") == "reddit_session"),
                None
            )
            
            if session_cookie:
                return AuthStatus.LOGGED_IN
            
            # Check for token in localStorage
            token = self._evaluate("""
                () => {
                    return localStorage.getItem('token') || 
                           localStorage.getItem('accessToken');
                }
            """)
            
            if token:
                return AuthStatus.LOGGED_IN
            
            return AuthStatus.LOGGED_OUT
            
        except Exception as e:
            logger.error(f"Reddit auth check failed: {e}")
            return AuthStatus.ERROR
    
    def extract_tokens(self) -> List[ExtractedToken]:
        """Extract Reddit tokens."""
        tokens = []
        
        if not self.browser:
            return tokens
        
        try:
            # Extract bearer token
            token = self._evaluate("""
                () => {
                    return localStorage.getItem('token') || 
                           localStorage.getItem('accessToken') ||
                           localStorage.getItem('reddit_token');
                }
            """)
            
            if token:
                tokens.append(ExtractedToken(
                    token_type=TokenType.BEARER_TOKEN,
                    value=token,
                    domain="reddit.com",
                ))
            
            # Extract refresh token
            refresh = self._evaluate("""
                () => {
                    return localStorage.getItem('refreshToken') ||
                           localStorage.getItem('refresh_token');
                }
            """)
            
            if refresh:
                tokens.append(ExtractedToken(
                    token_type=TokenType.REFRESH_TOKEN,
                    value=refresh,
                    domain="reddit.com",
                ))
            
        except Exception as e:
            logger.error(f"Reddit token extraction failed: {e}")
        
        return tokens
    
    def inject_session(self, session_data: SessionData) -> bool:
        """Inject Reddit session."""
        if not self.browser:
            return False
        
        try:
            # Inject cookies
            if session_data.cookies:
                self._add_cookies(session_data.cookies)
            
            # Inject tokens
            for token in session_data.tokens:
                if token.token_type == TokenType.BEARER_TOKEN:
                    self._evaluate(f"""
                        () => {{
                            localStorage.setItem('token', '{token.value}');
                            localStorage.setItem('accessToken', '{token.value}');
                        }}
                    """)
                elif token.token_type == TokenType.REFRESH_TOKEN:
                    self._evaluate(f"""
                        () => {{
                            localStorage.setItem('refreshToken', '{token.value}');
                            localStorage.setItem('refresh_token', '{token.value}');
                        }}
                    """)
            
            return True
            
        except Exception as e:
            logger.error(f"Reddit session injection failed: {e}")
            return False
