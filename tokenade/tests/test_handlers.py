"""
Unit tests for site handler base classes and registry.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tokenade.handlers.base import (  # noqa: E402
    AuthStatus,
    ExtractedToken,
    HandlerRegistry,
    SessionData,
    TokenType,
    SiteHandler,
)


class _MockHandler(SiteHandler):
    """Minimal handler for registry tests."""
    SITE_NAME = "mock_site"

    def check_auth_status(self):
        return AuthStatus.UNKNOWN

    def extract_tokens(self):
        return []

    def extract_cookies(self):
        return []

    def validate_session(self, cookies):
        return True

    def inject_session(self, session_data):
        return True


class TestAuthStatus(unittest.TestCase):
    """Test AuthStatus enum."""

    def test_values(self):
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
        session = SessionData(
            site_name="google",
            auth_status=AuthStatus.LOGGED_IN,
        )
        self.assertEqual(session.site_name, "google")
        self.assertEqual(session.auth_status, AuthStatus.LOGGED_IN)
        self.assertEqual(session.tokens, [])
        self.assertEqual(session.cookies, [])

    def test_get_token(self):
        token = ExtractedToken(TokenType.ACCESS_TOKEN, "abc")
        session = SessionData(
            site_name="test",
            auth_status=AuthStatus.LOGGED_IN,
            tokens=[token],
        )
        found = session.get_token(TokenType.ACCESS_TOKEN)
        self.assertEqual(found, token)

    def test_get_token_missing(self):
        session = SessionData(
            site_name="test",
            auth_status=AuthStatus.LOGGED_IN,
        )
        found = session.get_token(TokenType.REFRESH_TOKEN)
        self.assertIsNone(found)

    def test_to_dict(self):
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
        HandlerRegistry._handlers.clear()

    def test_register(self):
        HandlerRegistry.register(_MockHandler)
        self.assertIn("mock_site", HandlerRegistry.list_handlers())

    def test_get(self):
        HandlerRegistry.register(_MockHandler)
        handler_class = HandlerRegistry.get("mock_site")
        self.assertEqual(handler_class, _MockHandler)

    def test_get_missing(self):
        result = HandlerRegistry.get("nonexistent")
        self.assertIsNone(result)

    def test_create(self):
        HandlerRegistry.register(_MockHandler)
        mock_browser = MagicMock()
        handler = HandlerRegistry.create("mock_site", mock_browser)
        self.assertIsInstance(handler, _MockHandler)
        self.assertEqual(handler.browser, mock_browser)

    def test_list_handlers(self):
        HandlerRegistry.register(_MockHandler)
        handlers = HandlerRegistry.list_handlers()
        self.assertIn("mock_site", handlers)


if __name__ == "__main__":
    unittest.main()
