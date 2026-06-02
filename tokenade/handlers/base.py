"""
Base Site Handler - Abstract interface for site-specific token extraction.

Each site (Google, GitHub, etc.) may use different authentication flows,
cookie structures, and anti-bot measures. Handlers encapsulate
site-specific logic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
import logging
import json

logger = logging.getLogger(__name__)


class AuthStatus(Enum):
    """Authentication status enumeration."""
    UNKNOWN = "unknown"
    LOGGED_IN = "logged_in"
    LOGGED_OUT = "logged_out"
    MFA_REQUIRED = "mfa_required"
    CAPTCHA_REQUIRED = "captcha_required"
    SESSION_EXPIRED = "session_expired"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"
    NEEDS_2FA = "needs_2fa"


class TokenType(Enum):
    """Types of tokens that can be extracted."""
    ACCESS_TOKEN = "access_token"
    REFRESH_TOKEN = "refresh_token"
    SESSION_COOKIE = "session_cookie"
    BEARER_TOKEN = "bearer_token"
    API_KEY = "api_key"
    CSRF_TOKEN = "csrf_token"


@dataclass
class ExtractedToken:
    """Standardized token representation."""
    token_type: TokenType
    value: str
    expires_at: Optional[int] = None  # Unix timestamp
    scope: Optional[str] = None
    domain: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "token_type": self.token_type.value,
            "value": self.value,
            "expires_at": self.expires_at,
            "scope": self.scope,
            "domain": self.domain,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ExtractedToken":
        return cls(
            token_type=TokenType(data["token_type"]),
            value=data["value"],
            expires_at=data.get("expires_at"),
            scope=data.get("scope"),
            domain=data.get("domain", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class SessionData:
    """Complete session data for a site."""
    site_name: str
    auth_status: AuthStatus
    tokens: List[ExtractedToken] = field(default_factory=list)
    cookies: List[Dict] = field(default_factory=list)
    fingerprint: Optional[Dict] = None
    extracted_at: Optional[str] = None
    
    def get_token(self, token_type: TokenType) -> Optional[ExtractedToken]:
        """Get first token of specific type."""
        for token in self.tokens:
            if token.token_type == token_type:
                return token
        return None
    
    def to_dict(self) -> Dict:
        return {
            "site_name": self.site_name,
            "auth_status": self.auth_status.value,
            "tokens": [t.to_dict() for t in self.tokens],
            "cookies": self.cookies,
            "fingerprint": self.fingerprint,
            "extracted_at": self.extracted_at,
        }


class SiteHandler(ABC):
    """
    Abstract base class for site-specific handlers.
    
    Each handler knows:
    - How to navigate and authenticate on the site
    - How to extract tokens/cookies
    - How to validate session status
    - Site-specific anti-bot measures
    """
    
    # Site identification
    SITE_NAME: str = ""
    DOMAINS: List[str] = []
    LOGIN_URL: str = ""
    DASHBOARD_URL: str = ""
    
    # Critical cookies for session
    CRITICAL_COOKIES: List[str] = []
    
    def __init__(self, browser_manager=None, config: Optional[Dict] = None):
        self.browser = browser_manager
        self.config = config or {}
        self._session_data: Optional[SessionData] = None
    
    @abstractmethod
    def check_auth_status(self) -> AuthStatus:
        """
        Check if user is authenticated.
        
        Returns:
            AuthStatus indicating current authentication state
        """
        pass
    
    @abstractmethod
    def extract_tokens(self) -> List[ExtractedToken]:
        """
        Extract all available tokens from current session.
        
        Returns:
            List of ExtractedToken objects
        """
        pass
    
    @abstractmethod
    def extract_cookies(self) -> List[Dict]:
        """
        Extract session cookies for this site.
        
        Returns:
            List of cookie dictionaries in Playwright format
        """
        pass
    
    @abstractmethod
    def validate_session(self, cookies: List[Dict]) -> bool:
        """
        Validate if given cookies would maintain a valid session.
        
        Args:
            cookies: List of cookies to validate
            
        Returns:
            True if session is valid
        """
        pass
    
    @abstractmethod
    def inject_session(self, session_data: SessionData) -> bool:
        """
        Inject session data (cookies + tokens) into browser.
        
        Args:
            session_data: SessionData to inject
            
        Returns:
            True if injection was successful
        """
        pass
    
    def get_session(self) -> SessionData:
        """
        Get complete session data (auth check + extract everything).
        
        Returns:
            SessionData with all available information
        """
        auth_status = self.check_auth_status()
        tokens = self.extract_tokens() if auth_status == AuthStatus.LOGGED_IN else []
        cookies = self.extract_cookies() if auth_status == AuthStatus.LOGGED_IN else []
        
        self._session_data = SessionData(
            site_name=self.SITE_NAME,
            auth_status=auth_status,
            tokens=tokens,
            cookies=cookies,
        )
        
        return self._session_data
    
    def save_session(self, path: str) -> bool:
        """Save session to file."""
        if not self._session_data:
            logger.warning("No session data to save")
            return False
        
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(self._session_data.to_dict(), f, indent=2)
            logger.info(f"Session saved: {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            return False
    
    def load_session(self, path: str) -> Optional[SessionData]:
        """Load session from file."""
        try:
            with open(path, "r") as f:
                data = json.load(f)
            
            self._session_data = SessionData(
                site_name=data["site_name"],
                auth_status=AuthStatus(data["auth_status"]),
                tokens=[ExtractedToken.from_dict(t) for t in data.get("tokens", [])],
                cookies=data.get("cookies", []),
                fingerprint=data.get("fingerprint"),
                extracted_at=data.get("extracted_at"),
            )
            
            logger.info(f"Session loaded: {path}")
            return self._session_data
            
        except Exception as e:
            logger.error(f"Failed to load session: {e}")
            return None
    
    def _navigate(self, url: str, wait_until: str = "networkidle", timeout: int = 30000):
        """Helper to navigate browser."""
        if not self.browser:
            raise RuntimeError("Browser manager not set")
        return self.browser.navigate(url, wait_until=wait_until, timeout=timeout)
    
    def _evaluate(self, expression: str):
        """Helper to evaluate JS."""
        if not self.browser:
            raise RuntimeError("Browser manager not set")
        return self.browser.evaluate(expression)
    
    def _get_cookies(self, urls: Optional[List[str]] = None) -> List[Dict]:
        """Helper to get cookies."""
        if not self.browser:
            raise RuntimeError("Browser manager not set")
        return self.browser.get_cookies(urls)
    
    def _add_cookies(self, cookies: List[Dict]):
        """Helper to add cookies."""
        if not self.browser:
            raise RuntimeError("Browser manager not set")
        self.browser.add_cookies(cookies)


class HandlerRegistry:
    """Registry for site handlers."""
    
    _handlers: Dict[str, type] = {}
    
    @classmethod
    def register(cls, handler_class: type):
        """Register a handler class."""
        cls._handlers[handler_class.SITE_NAME.lower()] = handler_class
        logger.info(f"Registered handler: {handler_class.SITE_NAME}")
    
    @classmethod
    def get(cls, site_name: str) -> Optional[type]:
        """Get handler class by site name."""
        return cls._handlers.get(site_name.lower())
    
    @classmethod
    def list_handlers(cls) -> List[str]:
        """List all registered handlers."""
        return list(cls._handlers.keys())
    
    @classmethod
    def create(cls, site_name: str, browser_manager=None, config: Optional[Dict] = None) -> Optional[SiteHandler]:
        """Create handler instance."""
        handler_class = cls.get(site_name)
        if handler_class:
            return handler_class(browser_manager, config)
        return None
