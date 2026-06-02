"""
Google Handler - Extract and manage Google service tokens.

Handles Google Labs/Whisk API tokens, Gmail sessions, and
general Google authentication cookies.
"""

import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging

from .base import SiteHandler, AuthStatus, TokenType, ExtractedToken, SessionData

logger = logging.getLogger(__name__)


class GoogleHandler(SiteHandler):
    """
    Handler for Google services (Labs, Gmail, etc.)
    
    Extracts OAuth tokens from Google Labs and manages
    cross-platform session transfer.
    """
    
    SITE_NAME = "google"
    DOMAINS = [
        "google.com",
        "accounts.google.com",
        "mail.google.com",
        "labs.google.com",
        "myaccount.google.com",
    ]
    LOGIN_URL = "https://accounts.google.com/signin"
    DASHBOARD_URL = "https://labs.google/fx/tools/flow"
    SESSION_CHECK_URL = "https://labs.google/fx/api/auth/session"
    
    CRITICAL_COOKIES = [
        "SID", "SSID", "APISID", "SAPISID", "HSID",
        "__Secure-1PSID", "__Secure-3PSID",
        "__Secure-1PAPISID", "__Secure-3PAPISID",
        "OSID", "__Secure-OSID",
        "__Host-GAPS", "COMPASS",
    ]
    
    def __init__(self, browser_manager=None, config: Optional[Dict] = None):
        super().__init__(browser_manager, config)
        self._access_token: Optional[str] = None
        self._token_expires: Optional[str] = None
        self._user_info: Optional[Dict] = None
    
    def check_auth_status(self) -> AuthStatus:
        """Check Google authentication status via Labs API."""
        if not self.browser:
            logger.error("Browser manager not set")
            return AuthStatus.UNKNOWN
        
        try:
            response = self._navigate(
                self.SESSION_CHECK_URL,
                wait_until="networkidle",
                timeout=15000
            )
            
            if response.status != 200:
                logger.debug(f"Session check returned status: {response.status}")
                return AuthStatus.LOGGED_OUT
            
            session_data = response.json()
            
            if "access_token" in session_data:
                self._access_token = session_data["access_token"]
                self._token_expires = session_data.get("expires", "")
                self._user_info = session_data.get("user", {})
                logger.info(f"Authenticated as: {self._user_info.get('email', 'unknown')}")
                return AuthStatus.LOGGED_IN
            
            return AuthStatus.LOGGED_OUT
            
        except Exception as e:
            logger.error(f"Auth check failed: {e}")
            return AuthStatus.UNKNOWN
    
    def extract_tokens(self) -> List[ExtractedToken]:
        """Extract OAuth tokens from current session."""
        tokens = []
        
        # Check auth first if we don't have token
        if not self._access_token:
            status = self.check_auth_status()
            if status != AuthStatus.LOGGED_IN:
                logger.warning("Not authenticated, no tokens to extract")
                return tokens
        
        if self._access_token:
            # Parse expires
            expires_at = None
            if self._token_expires:
                try:
                    dt = datetime.fromisoformat(self._token_expires.replace("Z", "+00:00"))
                    expires_at = int(dt.timestamp())
                except:
                    pass
            
            tokens.append(ExtractedToken(
                token_type=TokenType.ACCESS_TOKEN,
                value=self._access_token,
                expires_at=expires_at,
                scope="https://www.googleapis.com/auth/userinfo.email",
                domain="labs.google.com",
                metadata={
                    "user_email": self._user_info.get("email") if self._user_info else None,
                    "user_name": self._user_info.get("name") if self._user_info else None,
                    "expires_iso": self._token_expires,
                }
            ))
        
        logger.info(f"Extracted {len(tokens)} tokens")
        return tokens
    
    def extract_cookies(self) -> List[Dict]:
        """Extract all Google-related cookies."""
        if not self.browser:
            return []
        
        try:
            all_cookies = self._get_cookies()
            
            # Filter for Google domains
            google_cookies = [
                c for c in all_cookies
                if any(domain in c.get("domain", "") for domain in self.DOMAINS)
            ]
            
            logger.info(f"Extracted {len(google_cookies)} Google cookies")
            return google_cookies
            
        except Exception as e:
            logger.error(f"Cookie extraction failed: {e}")
            return []
    
    def validate_session(self, cookies: List[Dict]) -> bool:
        """
        Validate if cookies maintain a valid Google session.
        
        Checks for critical authentication cookies.
        """
        cookie_names = {c.get("name", "") for c in cookies}
        
        # Check for at least one critical auth cookie
        has_critical = any(name in cookie_names for name in self.CRITICAL_COOKIES)
        
        if not has_critical:
            logger.warning("No critical authentication cookies found")
            return False
        
        # Check for SID (primary session cookie)
        if "SID" not in cookie_names:
            logger.warning("SID cookie missing - session likely invalid")
            return False
        
        logger.info("Session validation passed")
        return True
    
    def inject_session(self, session_data: SessionData) -> bool:
        """
        Inject Google session into browser.
        
        Uses Playwright's add_cookies which handles encryption
        automatically on the target platform.
        """
        if not self.browser:
            logger.error("Browser manager not set")
            return False
        
        try:
            # Inject cookies
            if session_data.cookies:
                self._add_cookies(session_data.cookies)
                logger.info(f"Injected {len(session_data.cookies)} cookies")
            
            # Verify injection
            time.sleep(2)
            status = self.check_auth_status()
            
            if status == AuthStatus.LOGGED_IN:
                logger.info("Session injection successful")
                return True
            else:
                logger.warning(f"Session injection failed - status: {status.value}")
                return False
                
        except Exception as e:
            logger.error(f"Session injection failed: {e}")
            return False
    
    def login(self, email: str, password: str, headless: bool = False) -> AuthStatus:
        """
        Perform automated login.
        
        Args:
            email: Google account email
            password: Account password
            headless: Run in headless mode
            
        Returns:
            AuthStatus after login attempt
        """
        if not self.browser:
            raise RuntimeError("Browser manager not set")
        
        try:
            # Navigate to login
            self._navigate(self.LOGIN_URL, wait_until="networkidle")
            time.sleep(2)
            
            # Enter email
            email_input = self.browser.query_selector('input[type="email"]', timeout=15000)
            if email_input:
                email_input.fill(email)
                
                next_btn = self.browser.query_selector('button:has-text("Next")', timeout=5000)
                if next_btn:
                    next_btn.click()
                time.sleep(3)
            
            # Enter password
            password_input = self.browser.query_selector('input[type="password"]', timeout=15000)
            if password_input:
                password_input.fill(password)
                
                next_btn = self.browser.query_selector('button:has-text("Next")', timeout=5000)
                if next_btn:
                    next_btn.click()
                time.sleep(5)
            
            # Check for 2FA
            time.sleep(10)
            
            # Verify login
            return self.check_auth_status()
            
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return AuthStatus.LOGGED_OUT
    
    def test_api(self, token: str, prompt: str = "a cat") -> Optional[Dict]:
        """
        Test token by calling Google Whisk API.
        
        Args:
            token: OAuth access token
            prompt: Image generation prompt
            
        Returns:
            API response or None if failed
        """
        import requests
        
        url = "https://labs.google/fx/api/image/generate"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        
        payload = {
            "prompt": prompt,
            "aspectRatio": "1:1",
            "safetyFilter": "BLOCK_NONE",
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                logger.info("API test successful")
                return data
            else:
                logger.error(f"API test failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"API request failed: {e}")
            return None
    
    def get_gmail_cookies(self) -> List[Dict]:
        """Get Gmail-specific cookies."""
        all_cookies = self.extract_cookies()
        return [c for c in all_cookies if "mail.google" in c.get("domain", "")]
    
    def get_labs_cookies(self) -> List[Dict]:
        """Get Google Labs-specific cookies."""
        all_cookies = self.extract_cookies()
        return [c for c in all_cookies if "labs.google" in c.get("domain", "")]


# Register handler
from .base import HandlerRegistry
HandlerRegistry.register(GoogleHandler)
