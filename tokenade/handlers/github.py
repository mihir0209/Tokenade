"""
GitHub Handler - Site handler for GitHub authentication.

Demonstrates the extensibility of the handler pattern.
GitHub uses standard session cookies (user_session, __Host-*) which are
less fingerprint-sensitive than Google, making it a good Level 2 example.
"""

import logging
from typing import Dict, List, Optional

from tokenade.handlers.base import (
    AuthStatus,
    ExtractedToken,
    SessionData,
    SiteHandler,
    TokenType,
)

logger = logging.getLogger(__name__)


class GitHubHandler(SiteHandler):
    """
    Handler for GitHub authentication.

    GitHub uses standard session cookies:
    - user_session: Primary session identifier
    - __Host-user_session_same_site: Same-site session
    - __Host-device_id: Device identifier
    - has_recent_activity: Activity flag

    These cookies are less fingerprint-sensitive than Google,
    making GitHub a good example of a Level 2 (OAuth/simple cookie) site.
    """

    SITE_NAME = "github"
    DOMAINS = ["github.com", ".github.com"]
    LOGIN_URL = "https://github.com/login"
    DASHBOARD_URL = "https://github.com/"
    API_BASE = "https://api.github.com"

    # Critical cookies for GitHub session
    CRITICAL_COOKIES = [
        "user_session",
        "__Host-user_session_same_site",
    ]

    def check_auth_status(self) -> AuthStatus:
        """
        Check if user is logged into GitHub.

        Strategy:
        1. Navigate to dashboard
        2. Check for user-specific elements (avatar, username)
        3. Check for login form (indicates logged out)
        """
        try:
            self.browser.navigate(self.DASHBOARD_URL)
            self.browser.wait_for_load()

            # Check for logged-in indicators
            logged_in_selectors = [
                "img.avatar",
                "[data-testid='header-avatar']",
                ".Header-link[href='/logout']",
                "button[aria-label='Open user navigation menu']",
            ]

            for selector in logged_in_selectors:
                try:
                    if self.browser.page.query_selector(selector):
                        logger.info("GitHub: Logged in detected")
                        return AuthStatus.LOGGED_IN
                except Exception:
                    continue

            # Check for logged-out indicators
            logout_selectors = [
                "a[href='/login']",
                "input[name='login']",
                ".auth-form-body",
            ]

            for selector in logout_selectors:
                try:
                    if self.browser.page.query_selector(selector):
                        logger.info("GitHub: Login page detected (logged out)")
                        return AuthStatus.LOGGED_OUT
                except Exception:
                    continue

            # Check URL redirect
            current_url = self.browser.page.url
            if "/login" in current_url:
                return AuthStatus.LOGGED_OUT

            return AuthStatus.UNKNOWN

        except Exception as e:
            logger.error(f"GitHub auth check failed: {e}")
            return AuthStatus.ERROR

    def extract_tokens(self) -> List[ExtractedToken]:
        """
        Extract GitHub tokens from browser storage.

        GitHub stores:
        - OAuth tokens in localStorage (gho_* for GitHub Apps)
        - Session cookies (primary auth mechanism)
        """
        tokens = []

        try:
            # Check localStorage for OAuth tokens
            local_storage = self.browser.page.evaluate("""
                () => {
                    const items = {};
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        items[key] = localStorage.getItem(key);
                    }
                    return items;
                }
            """)

            for key, value in local_storage.items():
                if "token" in key.lower() or value.startswith("gho_"):
                    token_type = TokenType.OAUTH_ACCESS if value.startswith("gho_") else TokenType.UNKNOWN
                    tokens.append(ExtractedToken(
                        token_type=token_type,
                        value=value,
                        source="localStorage",
                        metadata={"key": key},
                    ))

            # Check for GitHub CLI token in session storage
            session_storage = self.browser.page.evaluate("""
                () => {
                    const items = {};
                    for (let i = 0; i < sessionStorage.length; i++) {
                        const key = sessionStorage.key(i);
                        items[key] = sessionStorage.getItem(key);
                    }
                    return items;
                }
            """)

            for key, value in session_storage.items():
                if "token" in key.lower():
                    tokens.append(ExtractedToken(
                        token_type=TokenType.UNKNOWN,
                        value=value,
                        source="sessionStorage",
                        metadata={"key": key},
                    ))

        except Exception as e:
            logger.error(f"GitHub token extraction failed: {e}")

        return tokens

    def extract_cookies(self) -> List[Dict]:
        """
        Extract GitHub session cookies.

        Returns all github.com cookies, prioritizing session cookies.
        """
        all_cookies = self.browser.get_cookies()
        github_cookies = [
            c for c in all_cookies
            if "github.com" in c.get("domain", "")
        ]

        # Sort: critical cookies first
        def priority(cookie):
            name = cookie.get("name", "")
            if name in self.CRITICAL_COOKIES:
                return 0
            elif name.startswith("__Host-"):
                return 1
            elif "session" in name.lower():
                return 2
            return 3

        github_cookies.sort(key=priority)
        logger.info(f"GitHub: Extracted {len(github_cookies)} cookies")
        return github_cookies

    def validate_session(self, cookies: List[Dict]) -> bool:
        """
        Validate GitHub session by checking critical cookies.

        GitHub requires:
        - user_session: Primary session token
        - __Host-user_session_same_site: CSRF protection
        """
        cookie_names = {c.get("name") for c in cookies}

        missing = [name for name in self.CRITICAL_COOKIES if name not in cookie_names]
        if missing:
            logger.warning(f"GitHub: Missing critical cookies: {missing}")
            return False

        # Check session cookie has value
        for cookie in cookies:
            if cookie.get("name") == "user_session":
                if not cookie.get("value"):
                    logger.warning("GitHub: user_session is empty")
                    return False
                break

        logger.info("GitHub: Session validation passed")
        return True

    def inject_session(self, session_data: SessionData) -> bool:
        """
        Inject GitHub session cookies into browser.

        GitHub cookies are less fingerprint-sensitive than Google,
        so fingerprint matching is optional but recommended.
        """
        try:
            # Navigate to GitHub to set domain context
            self.browser.navigate("https://github.com")
            self.browser.wait_for_load()

            # Inject cookies
            injected = 0
            for cookie in session_data.cookies:
                try:
                    # Ensure domain is set for GitHub
                    cookie_dict = dict(cookie)
                    if "domain" not in cookie_dict or not cookie_dict["domain"]:
                        cookie_dict["domain"] = ".github.com"

                    self.browser.set_cookie(cookie_dict)
                    injected += 1
                except Exception as e:
                    logger.warning(f"GitHub: Failed to inject cookie {cookie.get('name')}: {e}")

            logger.info(f"GitHub: Injected {injected}/{len(session_data.cookies)} cookies")

            # Verify by navigating to dashboard
            self.browser.navigate(self.DASHBOARD_URL)
            self.browser.wait_for_load()

            # Check auth status
            auth_status = self.check_auth_status()
            if auth_status == AuthStatus.LOGGED_IN:
                logger.info("GitHub: Session injection successful")
                return True
            else:
                logger.warning(f"GitHub: Session injection failed, status={auth_status}")
                return False

        except Exception as e:
            logger.error(f"GitHub: Session injection error: {e}")
            return False

    def login(self, username: str, password: str, headless: bool = True) -> AuthStatus:
        """
        Automated GitHub login.

        Args:
            username: GitHub username or email
            password: GitHub password
            headless: Whether to run headless

        Returns:
            AuthStatus after login attempt
        """
        try:
            self.browser.navigate(self.LOGIN_URL)
            self.browser.wait_for_load()

            # Fill login form
            self.browser.page.fill("input[name='login']", username)
            self.browser.page.fill("input[name='password']", password)

            # Click sign in
            self.browser.page.click("input[name='commit']")
            self.browser.wait_for_load()

            # Check for 2FA
            if self.browser.page.query_selector("input[name='otp']"):
                logger.info("GitHub: 2FA required")
                if not headless:
                    print("\n🔐 GitHub 2FA required!")
                    otp = input("Enter 2FA code: ").strip()
                    self.browser.page.fill("input[name='otp']", otp)
                    self.browser.page.click("button[type='submit']")
                    self.browser.wait_for_load()
                else:
                    return AuthStatus.NEEDS_2FA

            # Check result
            return self.check_auth_status()

        except Exception as e:
            logger.error(f"GitHub login failed: {e}")
            return AuthStatus.ERROR

    def test_api(self, token: Optional[str] = None) -> Optional[Dict]:
        """
        Test GitHub API with session.

        Uses the session cookies to make an authenticated API request.
        """
        try:
            import requests

            # Get cookies from browser
            cookies = self.browser.get_cookies()
            cookie_dict = {c["name"]: c["value"] for c in cookies if "github" in c.get("domain", "")}

            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "Tokenade-GitHub-Test/1.0",
            }

            if token:
                headers["Authorization"] = f"token {token}"

            response = requests.get(
                f"{self.API_BASE}/user",
                headers=headers,
                cookies=cookie_dict,
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                logger.info(f"GitHub API: Authenticated as {data.get('login')}")
                return {
                    "login": data.get("login"),
                    "name": data.get("name"),
                    "email": data.get("email"),
                    "type": data.get("type"),
                }
            else:
                logger.warning(f"GitHub API: Status {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"GitHub API test failed: {e}")
            return None


# Register handler
from .base import HandlerRegistry  # noqa: E402
HandlerRegistry.register(GitHubHandler)
