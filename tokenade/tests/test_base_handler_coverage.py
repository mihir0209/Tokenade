"""
Comprehensive coverage tests for base.py (SiteHandler, HandlerRegistry, etc.).
Targets 87% → 95%+ coverage on base.py.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock

from tokenade.handlers.base import (
    AuthStatus,
    TokenType,
    ExtractedToken,
    SessionData,
    SiteHandler,
    HandlerRegistry,
)


class ConcreteHandler(SiteHandler):
    """Concrete implementation for testing abstract base."""

    SITE_NAME = "test_site"
    DOMAINS = ["test.com"]
    LOGIN_URL = "https://test.com/login"
    DASHBOARD_URL = "https://test.com/dashboard"
    CRITICAL_COOKIES = ["session_id"]

    def check_auth_status(self):
        return AuthStatus.LOGGED_IN

    def extract_tokens(self):
        return [ExtractedToken(TokenType.ACCESS_TOKEN, "tok123")]

    def extract_cookies(self):
        return [{"name": "session_id", "value": "abc"}]

    def validate_session(self, cookies):
        return True

    def inject_session(self, session_data):
        return True


class TestAuthStatus(unittest.TestCase):
    def test_all_values(self):
        self.assertEqual(AuthStatus.UNKNOWN.value, "unknown")
        self.assertEqual(AuthStatus.LOGGED_IN.value, "logged_in")
        self.assertEqual(AuthStatus.LOGGED_OUT.value, "logged_out")
        self.assertEqual(AuthStatus.MFA_REQUIRED.value, "mfa_required")
        self.assertEqual(AuthStatus.CAPTCHA_REQUIRED.value, "captcha_required")
        self.assertEqual(AuthStatus.SESSION_EXPIRED.value, "session_expired")
        self.assertEqual(AuthStatus.RATE_LIMITED.value, "rate_limited")
        self.assertEqual(AuthStatus.ERROR.value, "error")
        self.assertEqual(AuthStatus.NEEDS_2FA.value, "needs_2fa")


class TestTokenType(unittest.TestCase):
    def test_all_values(self):
        self.assertEqual(TokenType.ACCESS_TOKEN.value, "access_token")
        self.assertEqual(TokenType.REFRESH_TOKEN.value, "refresh_token")
        self.assertEqual(TokenType.SESSION_COOKIE.value, "session_cookie")
        self.assertEqual(TokenType.BEARER_TOKEN.value, "bearer_token")
        self.assertEqual(TokenType.API_KEY.value, "api_key")
        self.assertEqual(TokenType.CSRF_TOKEN.value, "csrf_token")


class TestExtractedToken(unittest.TestCase):
    def test_creation_defaults(self):
        token = ExtractedToken(token_type=TokenType.ACCESS_TOKEN, value="abc")
        self.assertIsNone(token.expires_at)
        self.assertIsNone(token.scope)
        self.assertEqual(token.domain, "")
        self.assertEqual(token.metadata, {})

    def test_to_dict_full(self):
        token = ExtractedToken(
            token_type=TokenType.REFRESH_TOKEN,
            value="xyz",
            expires_at=1700000000,
            scope="read write",
            domain="example.com",
            metadata={"key": "val"},
        )
        d = token.to_dict()
        self.assertEqual(d["token_type"], "refresh_token")
        self.assertEqual(d["value"], "xyz")
        self.assertEqual(d["expires_at"], 1700000000)
        self.assertEqual(d["scope"], "read write")
        self.assertEqual(d["domain"], "example.com")
        self.assertEqual(d["metadata"], {"key": "val"})

    def test_from_dict_partial(self):
        data = {"token_type": "api_key", "value": "key123"}
        token = ExtractedToken.from_dict(data)
        self.assertEqual(token.token_type, TokenType.API_KEY)
        self.assertEqual(token.value, "key123")
        self.assertIsNone(token.expires_at)
        self.assertEqual(token.domain, "")

    def test_roundtrip(self):
        original = ExtractedToken(
            token_type=TokenType.CSRF_TOKEN,
            value="csrf",
            expires_at=999,
            scope="s",
            domain="d.com",
            metadata={"k": "v"},
        )
        restored = ExtractedToken.from_dict(original.to_dict())
        self.assertEqual(original.token_type, restored.token_type)
        self.assertEqual(original.value, restored.value)
        self.assertEqual(original.expires_at, restored.expires_at)
        self.assertEqual(original.scope, restored.scope)
        self.assertEqual(original.domain, restored.domain)
        self.assertEqual(original.metadata, restored.metadata)


class TestSessionData(unittest.TestCase):
    def test_creation_defaults(self):
        session = SessionData(site_name="test", auth_status=AuthStatus.LOGGED_OUT)
        self.assertEqual(session.tokens, [])
        self.assertEqual(session.cookies, [])
        self.assertIsNone(session.fingerprint)
        self.assertIsNone(session.extracted_at)

    def test_get_token_found(self):
        token = ExtractedToken(TokenType.ACCESS_TOKEN, "tok")
        session = SessionData(
            site_name="test",
            auth_status=AuthStatus.LOGGED_IN,
            tokens=[token],
        )
        self.assertEqual(session.get_token(TokenType.ACCESS_TOKEN), token)

    def test_get_token_not_found(self):
        session = SessionData(site_name="test", auth_status=AuthStatus.LOGGED_IN)
        self.assertIsNone(session.get_token(TokenType.ACCESS_TOKEN))

    def test_get_token_wrong_type(self):
        token = ExtractedToken(TokenType.REFRESH_TOKEN, "ref")
        session = SessionData(
            site_name="test",
            auth_status=AuthStatus.LOGGED_IN,
            tokens=[token],
        )
        self.assertIsNone(session.get_token(TokenType.ACCESS_TOKEN))

    def test_to_dict_full(self):
        token = ExtractedToken(TokenType.ACCESS_TOKEN, "tok")
        session = SessionData(
            site_name="google",
            auth_status=AuthStatus.LOGGED_IN,
            tokens=[token],
            cookies=[{"name": "sid", "value": "abc"}],
            fingerprint={"canvas": "hash"},
            extracted_at="2024-01-01T00:00:00Z",
        )
        d = session.to_dict()
        self.assertEqual(d["site_name"], "google")
        self.assertEqual(d["auth_status"], "logged_in")
        self.assertEqual(len(d["tokens"]), 1)
        self.assertEqual(len(d["cookies"]), 1)
        self.assertEqual(d["fingerprint"], {"canvas": "hash"})
        self.assertEqual(d["extracted_at"], "2024-01-01T00:00:00Z")


class TestSiteHandler(unittest.TestCase):
    def test_init(self):
        handler = ConcreteHandler()
        self.assertIsNone(handler.browser)
        self.assertEqual(handler.config, {})
        self.assertIsNone(handler._session_data)

    def test_init_with_args(self):
        mock_browser = MagicMock()
        handler = ConcreteHandler(mock_browser, {"key": "val"})
        self.assertEqual(handler.browser, mock_browser)
        self.assertEqual(handler.config, {"key": "val"})

    def test_get_session(self):
        handler = ConcreteHandler()
        session = handler.get_session()
        self.assertEqual(session.site_name, "test_site")
        self.assertEqual(session.auth_status, AuthStatus.LOGGED_IN)
        self.assertEqual(len(session.tokens), 1)
        self.assertEqual(len(session.cookies), 1)

    def test_save_and_load_session(self):
        handler = ConcreteHandler()
        handler._session_data = SessionData(
            site_name="test_site",
            auth_status=AuthStatus.LOGGED_IN,
            tokens=[ExtractedToken(TokenType.ACCESS_TOKEN, "tok")],
            cookies=[{"name": "sid", "value": "abc"}],
            fingerprint={"fp": "val"},
            extracted_at="2024-01-01",
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            result = handler.save_session(path)
            self.assertTrue(result)

            handler2 = ConcreteHandler()
            loaded = handler2.load_session(path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.site_name, "test_site")
            self.assertEqual(loaded.auth_status, AuthStatus.LOGGED_IN)
            self.assertEqual(len(loaded.tokens), 1)
            self.assertEqual(loaded.fingerprint, {"fp": "val"})
        finally:
            os.unlink(path)

    def test_save_session_no_data(self):
        handler = ConcreteHandler()
        result = handler.save_session("/tmp/nonexistent.json")
        self.assertFalse(result)

    def test_save_session_exception(self):
        handler = ConcreteHandler()
        handler._session_data = SessionData(
            site_name="test", auth_status=AuthStatus.LOGGED_IN
        )
        result = handler.save_session("/nonexistent/path/deep/file.json")
        self.assertFalse(result)

    def test_load_session_exception(self):
        handler = ConcreteHandler()
        result = handler.load_session("/nonexistent/file.json")
        self.assertIsNone(result)

    def test_navigate_no_browser(self):
        handler = ConcreteHandler(None)
        with self.assertRaises(RuntimeError):
            handler._navigate("https://example.com")

    def test_navigate_with_browser(self):
        mock_browser = MagicMock()
        mock_browser.navigate.return_value = MockResponse(200)
        handler = ConcreteHandler(mock_browser)
        handler._navigate("https://example.com")
        mock_browser.navigate.assert_called_once_with(
            "https://example.com", wait_until="networkidle", timeout=30000
        )

    def test_evaluate_no_browser(self):
        handler = ConcreteHandler(None)
        with self.assertRaises(RuntimeError):
            handler._evaluate("() => 1")

    def test_evaluate_with_browser(self):
        mock_browser = MagicMock()
        mock_browser.evaluate.return_value = "result"
        handler = ConcreteHandler(mock_browser)
        result = handler._evaluate("() => 1")
        self.assertEqual(result, "result")

    def test_get_cookies_no_browser(self):
        handler = ConcreteHandler(None)
        with self.assertRaises(RuntimeError):
            handler._get_cookies()

    def test_get_cookies_with_browser(self):
        mock_browser = MagicMock()
        mock_browser.get_cookies.return_value = [{"name": "sid"}]
        handler = ConcreteHandler(mock_browser)
        cookies = handler._get_cookies(["https://example.com"])
        self.assertEqual(len(cookies), 1)

    def test_add_cookies_no_browser(self):
        handler = ConcreteHandler(None)
        with self.assertRaises(RuntimeError):
            handler._add_cookies([{"name": "sid"}])

    def test_add_cookies_with_browser(self):
        mock_browser = MagicMock()
        handler = ConcreteHandler(mock_browser)
        handler._add_cookies([{"name": "sid", "value": "abc"}])
        mock_browser.add_cookies.assert_called_once()


class MockResponse:
    def __init__(self, status=200, json_data=None):
        self.status = status
        self._json = json_data or {}

    def json(self):
        return self._json


class TestHandlerRegistry(unittest.TestCase):
    def setUp(self):
        HandlerRegistry._handlers.clear()

    def test_register_and_get(self):
        HandlerRegistry.register(ConcreteHandler)
        self.assertIn("test_site", HandlerRegistry.list_handlers())
        cls = HandlerRegistry.get("test_site")
        self.assertEqual(cls, ConcreteHandler)

    def test_get_missing(self):
        self.assertIsNone(HandlerRegistry.get("nonexistent"))

    def test_create(self):
        HandlerRegistry.register(ConcreteHandler)
        mock_browser = MagicMock()
        handler = HandlerRegistry.create("test_site", mock_browser, {"k": "v"})
        self.assertIsInstance(handler, ConcreteHandler)
        self.assertEqual(handler.browser, mock_browser)

    def test_create_missing(self):
        result = HandlerRegistry.create("nonexistent")
        self.assertIsNone(result)

    def test_list_handlers_empty(self):
        self.assertEqual(HandlerRegistry.list_handlers(), [])

    def test_list_handlers_multiple(self):
        class _SecondHandler(SiteHandler):
            SITE_NAME = "second_site"
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

        HandlerRegistry.register(ConcreteHandler)
        HandlerRegistry.register(_SecondHandler)
        handlers = HandlerRegistry.list_handlers()
        self.assertEqual(len(handlers), 2)
        self.assertIn("test_site", handlers)
        self.assertIn("second_site", handlers)

    def test_register_overwrite(self):
        HandlerRegistry.register(ConcreteHandler)
        HandlerRegistry.register(ConcreteHandler)
        self.assertEqual(len(HandlerRegistry.list_handlers()), 1)


class TestSiteHandlerGetSessionNotLoggedIn(unittest.TestCase):
    def test_no_tokens_or_cookies_when_logged_out(self):
        class LoggedOutHandler(SiteHandler):
            SITE_NAME = "lo"

            def check_auth_status(self):
                return AuthStatus.LOGGED_OUT

            def extract_tokens(self):
                return [ExtractedToken(TokenType.ACCESS_TOKEN, "should_not_appear")]

            def extract_cookies(self):
                return [{"name": "should_not", "value": "appear"}]

            def validate_session(self, cookies):
                return False

            def inject_session(self, session_data):
                return False

        handler = LoggedOutHandler()
        session = handler.get_session()
        self.assertEqual(session.auth_status, AuthStatus.LOGGED_OUT)
        self.assertEqual(len(session.tokens), 0)
        self.assertEqual(len(session.cookies), 0)


if __name__ == "__main__":
    unittest.main()
