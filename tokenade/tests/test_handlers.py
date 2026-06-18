"""
Unit tests for site handlers (base, Google, GitHub).
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tokenade.handlers.base import (  # noqa: E402
    AuthStatus,
    ExtractedToken,
    HandlerRegistry,
    SessionData,
    TokenType,
)
from tokenade.handlers.google import GoogleHandler  # noqa: E402
from tokenade.handlers.github import GitHubHandler  # noqa: E402


class MockResponse:
    """Mock response object for browser navigation."""

    def __init__(self, status=200, json_data=None):
        self.status = status
        self._json = json_data or {}

    def json(self):
        return self._json


class TestAuthStatus(unittest.TestCase):
    """Test AuthStatus enum."""

    def test_values(self):
        """Test all auth status values."""
        self.assertEqual(AuthStatus.LOGGED_IN.value, "logged_in")
        self.assertEqual(AuthStatus.LOGGED_OUT.value, "logged_out")
        self.assertEqual(AuthStatus.MFA_REQUIRED.value, "mfa_required")
        self.assertEqual(AuthStatus.CAPTCHA_REQUIRED.value, "captcha_required")
        self.assertEqual(AuthStatus.SESSION_EXPIRED.value, "session_expired")
        self.assertEqual(AuthStatus.RATE_LIMITED.value, "rate_limited")
        self.assertEqual(AuthStatus.UNKNOWN.value, "unknown")


class TestExtractedToken(unittest.TestCase):
    """Test ExtractedToken dataclass."""

    def test_creation(self):
        """Test token creation."""
        token = ExtractedToken(
            token_type=TokenType.ACCESS_TOKEN,
            value="abc123",
            expires_at=1234567890,
            scope="read",
            domain="example.com",
        )
        self.assertEqual(token.token_type, TokenType.ACCESS_TOKEN)
        self.assertEqual(token.value, "abc123")
        self.assertEqual(token.expires_at, 1234567890)

    def test_to_dict(self):
        """Test serialization."""
        token = ExtractedToken(
            token_type=TokenType.ACCESS_TOKEN,
            value="abc",
            metadata={"key": "val"},
        )
        data = token.to_dict()
        self.assertEqual(data["token_type"], "access_token")
        self.assertEqual(data["value"], "abc")
        self.assertEqual(data["metadata"], {"key": "val"})

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "token_type": "refresh_token",
            "value": "xyz",
            "expires_at": None,
            "scope": None,
            "domain": "",
            "metadata": {},
        }
        token = ExtractedToken.from_dict(data)
        self.assertEqual(token.token_type, TokenType.REFRESH_TOKEN)
        self.assertEqual(token.value, "xyz")


class TestSessionData(unittest.TestCase):
    """Test SessionData dataclass."""

    def test_creation(self):
        """Test session data creation."""
        session = SessionData(
            site_name="google",
            auth_status=AuthStatus.LOGGED_IN,
        )
        self.assertEqual(session.site_name, "google")
        self.assertEqual(session.auth_status, AuthStatus.LOGGED_IN)
        self.assertEqual(session.tokens, [])
        self.assertEqual(session.cookies, [])

    def test_get_token(self):
        """Test getting token by type."""
        token = ExtractedToken(TokenType.ACCESS_TOKEN, "abc")
        session = SessionData(
            site_name="test",
            auth_status=AuthStatus.LOGGED_IN,
            tokens=[token],
        )
        found = session.get_token(TokenType.ACCESS_TOKEN)
        self.assertEqual(found, token)

    def test_get_token_missing(self):
        """Test getting non-existent token."""
        session = SessionData(
            site_name="test",
            auth_status=AuthStatus.LOGGED_IN,
        )
        found = session.get_token(TokenType.REFRESH_TOKEN)
        self.assertIsNone(found)

    def test_to_dict(self):
        """Test serialization."""
        token = ExtractedToken(TokenType.ACCESS_TOKEN, "abc")
        session = SessionData(
            site_name="google",
            auth_status=AuthStatus.LOGGED_IN,
            tokens=[token],
            cookies=[{"name": "sid"}],
        )
        data = session.to_dict()
        self.assertEqual(data["site_name"], "google")
        self.assertEqual(data["auth_status"], "logged_in")
        self.assertEqual(len(data["tokens"]), 1)
        self.assertEqual(len(data["cookies"]), 1)


class TestHandlerRegistry(unittest.TestCase):
    """Test HandlerRegistry."""

    def setUp(self):
        """Clear registry before each test."""
        HandlerRegistry._handlers.clear()

    def test_register(self):
        """Test registering a handler."""
        HandlerRegistry.register(GoogleHandler)
        self.assertIn("google", HandlerRegistry.list_handlers())

    def test_get(self):
        """Test getting handler by name."""
        HandlerRegistry.register(GoogleHandler)
        handler_class = HandlerRegistry.get("google")
        self.assertEqual(handler_class, GoogleHandler)

    def test_get_missing(self):
        """Test getting non-existent handler."""
        result = HandlerRegistry.get("nonexistent")
        self.assertIsNone(result)

    def test_create(self):
        """Test creating handler instance."""
        HandlerRegistry.register(GoogleHandler)
        mock_browser = MagicMock()
        handler = HandlerRegistry.create("google", mock_browser)
        self.assertIsInstance(handler, GoogleHandler)
        self.assertEqual(handler.browser, mock_browser)

    def test_list_handlers(self):
        """Test listing registered handlers."""
        HandlerRegistry.register(GoogleHandler)
        HandlerRegistry.register(GitHubHandler)
        handlers = HandlerRegistry.list_handlers()
        self.assertIn("google", handlers)
        self.assertIn("github", handlers)


class TestGoogleHandler(unittest.TestCase):
    """Test GoogleHandler with mocked browser."""

    def setUp(self):
        """Set up mocked browser."""
        self.mock_browser = MagicMock()
        self.handler = GoogleHandler(self.mock_browser)

    def test_initial_state(self):
        """Test initial handler state."""
        self.assertEqual(self.handler.SITE_NAME, "google")
        self.assertIsNone(self.handler._access_token)
        self.assertIsNone(self.handler._user_info)

    def test_check_auth_status_logged_in(self):
        """Test auth check when logged in."""
        mock_response = MockResponse(200, {
            "access_token": "token123",
            "expires": "2024-01-01T00:00:00Z",
            "user": {"email": "test@gmail.com"},
        })
        self.mock_browser.navigate.return_value = mock_response

        status = self.handler.check_auth_status()

        self.assertEqual(status, AuthStatus.LOGGED_IN)
        self.assertEqual(self.handler._access_token, "token123")
        self.assertEqual(self.handler._user_info["email"], "test@gmail.com")

    def test_check_auth_status_logged_out(self):
        """Test auth check when logged out."""
        mock_response = MockResponse(200, {})
        self.mock_browser.navigate.return_value = mock_response

        status = self.handler.check_auth_status()

        self.assertEqual(status, AuthStatus.LOGGED_OUT)

    def test_check_auth_status_error(self):
        """Test auth check on error."""
        self.mock_browser.navigate.side_effect = Exception("Network error")

        status = self.handler.check_auth_status()

        self.assertEqual(status, AuthStatus.UNKNOWN)

    def test_check_auth_status_no_browser(self):
        """Test auth check without browser."""
        handler = GoogleHandler(None)
        status = handler.check_auth_status()
        self.assertEqual(status, AuthStatus.UNKNOWN)

    def test_extract_tokens_logged_in(self):
        """Test token extraction when logged in."""
        self.handler._access_token = "token123"
        self.handler._token_expires = "2024-01-01T00:00:00Z"
        self.handler._user_info = {"email": "test@gmail.com"}

        tokens = self.handler.extract_tokens()

        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].token_type, TokenType.ACCESS_TOKEN)
        self.assertEqual(tokens[0].value, "token123")
        self.assertEqual(tokens[0].metadata["user_email"], "test@gmail.com")

    def test_extract_tokens_not_logged_in(self):
        """Test token extraction when not logged in."""
        self.mock_browser.navigate.return_value = MockResponse(200, {})
        tokens = self.handler.extract_tokens()
        self.assertEqual(len(tokens), 0)

    def test_extract_cookies(self):
        """Test cookie extraction."""
        test_cookies = [
            {"name": "SID", "domain": ".google.com"},
            {"name": "HSID", "domain": ".google.com"},
            {"name": "other", "domain": ".example.com"},
        ]
        self.mock_browser.get_cookies.return_value = test_cookies

        cookies = self.handler.extract_cookies()

        self.assertEqual(len(cookies), 2)  # Only Google cookies
        self.assertEqual(cookies[0]["name"], "SID")

    def test_extract_cookies_no_browser(self):
        """Test cookie extraction without browser."""
        handler = GoogleHandler(None)
        cookies = handler.extract_cookies()
        self.assertEqual(cookies, [])

    def test_validate_session_valid(self):
        """Test session validation with valid cookies."""
        cookies = [
            {"name": "SID", "value": "abc"},
            {"name": "HSID", "value": "def"},
        ]
        result = self.handler.validate_session(cookies)
        self.assertTrue(result)

    def test_validate_session_missing_sid(self):
        """Test validation without SID cookie."""
        cookies = [{"name": "HSID", "value": "def"}]
        result = self.handler.validate_session(cookies)
        self.assertFalse(result)

    def test_validate_session_no_critical(self):
        """Test validation with no critical cookies."""
        cookies = [{"name": "random", "value": "xyz"}]
        result = self.handler.validate_session(cookies)
        self.assertFalse(result)

    def test_inject_session(self):
        """Test session injection."""
        session = SessionData(
            site_name="google",
            auth_status=AuthStatus.LOGGED_IN,
            cookies=[{"name": "SID", "value": "abc"}],
        )
        self.mock_browser.navigate.return_value = MockResponse(200, {
            "access_token": "token",
            "user": {"email": "test@gmail.com"},
        })

        result = self.handler.inject_session(session)

        self.assertTrue(result)
        self.mock_browser.add_cookies.assert_called_once()

    def test_inject_session_no_browser(self):
        """Test injection without browser."""
        handler = GoogleHandler(None)
        session = SessionData(site_name="google", auth_status=AuthStatus.LOGGED_IN)
        result = handler.inject_session(session)
        self.assertFalse(result)

    def test_get_session(self):
        """Test getting complete session data."""
        self.mock_browser.navigate.return_value = MockResponse(200, {
            "access_token": "token",
            "user": {"email": "test@gmail.com"},
        })
        self.mock_browser.get_cookies.return_value = [
            {"name": "SID", "domain": ".google.com"},
        ]

        session = self.handler.get_session()

        self.assertEqual(session.site_name, "google")
        self.assertEqual(session.auth_status, AuthStatus.LOGGED_IN)
        self.assertEqual(len(session.tokens), 1)
        self.assertEqual(len(session.cookies), 1)

    def test_save_and_load_session(self):
        """Test session persistence."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name

        try:
            self.handler._session_data = SessionData(
                site_name="google",
                auth_status=AuthStatus.LOGGED_IN,
                tokens=[ExtractedToken(TokenType.ACCESS_TOKEN, "abc")],
                cookies=[{"name": "SID"}],
            )

            # Save
            result = self.handler.save_session(temp_path)
            self.assertTrue(result)

            # Load
            loaded = self.handler.load_session(temp_path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.site_name, "google")
            self.assertEqual(loaded.auth_status, AuthStatus.LOGGED_IN)
            self.assertEqual(len(loaded.tokens), 1)

        finally:
            os.unlink(temp_path)

    def test_save_session_no_data(self):
        """Test saving without session data."""
        result = self.handler.save_session("/tmp/test.json")
        self.assertFalse(result)


class TestGitHubHandler(unittest.TestCase):
    """Test GitHubHandler with mocked browser."""

    def setUp(self):
        """Set up mocked browser."""
        self.mock_browser = MagicMock()
        self.handler = GitHubHandler(self.mock_browser)

    def test_initial_state(self):
        """Test initial handler state."""
        self.assertEqual(self.handler.SITE_NAME, "github")
        self.assertEqual(self.handler.LOGIN_URL, "https://github.com/login")

    def test_check_auth_status_logged_in(self):
        """Test auth check when logged in."""
        self.mock_browser.page.query_selector.return_value = True
        self.mock_browser.page.url = "https://github.com/"

        status = self.handler.check_auth_status()

        self.assertEqual(status, AuthStatus.LOGGED_IN)

    def test_check_auth_status_logged_out(self):
        """Test auth check when logged out."""
        # All 4 logged_in selectors return False, then first logout selector returns True
        self.mock_browser.page.query_selector.side_effect = [
            False, False, False, False,  # logged_in selectors
            True,  # first logout selector
        ]
        self.mock_browser.page.url = "https://github.com/login"

        status = self.handler.check_auth_status()

        self.assertEqual(status, AuthStatus.LOGGED_OUT)

    def test_check_auth_status_no_browser(self):
        """Test auth check without browser."""
        handler = GitHubHandler(None)
        status = handler.check_auth_status()
        self.assertEqual(status, AuthStatus.ERROR)

    def test_extract_cookies(self):
        """Test cookie extraction."""
        test_cookies = [
            {"name": "user_session", "domain": ".github.com"},
            {"name": "__Host-user_session_same_site", "domain": ".github.com"},
            {"name": "other", "domain": ".example.com"},
        ]
        self.mock_browser.get_cookies.return_value = test_cookies

        cookies = self.handler.extract_cookies()

        self.assertEqual(len(cookies), 2)
        self.assertEqual(cookies[0]["name"], "user_session")

    def test_validate_session_valid(self):
        """Test validation with valid cookies."""
        cookies = [
            {"name": "user_session", "value": "abc"},
            {"name": "__Host-user_session_same_site", "value": "def"},
        ]
        result = self.handler.validate_session(cookies)
        self.assertTrue(result)

    def test_validate_session_missing_critical(self):
        """Test validation missing critical cookies."""
        cookies = [{"name": "random", "value": "xyz"}]
        result = self.handler.validate_session(cookies)
        self.assertFalse(result)

    def test_validate_session_empty_session(self):
        """Test validation with empty session value."""
        cookies = [
            {"name": "user_session", "value": ""},
            {"name": "__Host-user_session_same_site", "value": "def"},
        ]
        result = self.handler.validate_session(cookies)
        self.assertFalse(result)

    def test_inject_session(self):
        """Test session injection."""
        session = SessionData(
            site_name="github",
            auth_status=AuthStatus.LOGGED_IN,
            cookies=[{"name": "user_session", "value": "abc"}],
        )
        self.mock_browser.page.query_selector.return_value = True

        result = self.handler.inject_session(session)

        self.assertTrue(result)

    def test_inject_session_failed(self):
        """Test failed session injection."""
        session = SessionData(
            site_name="github",
            auth_status=AuthStatus.LOGGED_IN,
            cookies=[{"name": "user_session", "value": "abc"}],
        )
        self.mock_browser.page.query_selector.return_value = False

        result = self.handler.inject_session(session)

        self.assertFalse(result)

    def test_login_success(self):
        """Test automated login."""
        # No 2FA, then logged in on auth check
        self.mock_browser.page.query_selector.side_effect = [
            None,  # 2FA check
            True,  # logged_in selector in check_auth_status
        ]
        self.mock_browser.page.url = "https://github.com/"

        status = self.handler.login("user", "pass")

        self.assertEqual(status, AuthStatus.LOGGED_IN)
        self.mock_browser.page.fill.assert_any_call("input[name='login']", "user")
        self.mock_browser.page.fill.assert_any_call("input[name='password']", "pass")

    def test_login_2fa_required(self):
        """Test login with 2FA required."""
        self.mock_browser.page.query_selector.return_value = True  # 2FA input found

        status = self.handler.login("user", "pass", headless=True)

        self.assertEqual(status, AuthStatus.NEEDS_2FA)

    def test_test_api(self):
        """Test GitHub API validation."""
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "login": "testuser",
                "name": "Test User",
            }

            result = self.handler.test_api()

            self.assertIsNotNone(result)
            self.assertEqual(result["login"], "testuser")

    def test_test_api_failure(self):
        """Test API validation failure."""
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 401

            result = self.handler.test_api()

            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
