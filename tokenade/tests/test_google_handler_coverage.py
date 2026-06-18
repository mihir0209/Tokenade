"""
Comprehensive coverage tests for GoogleHandler.
Targets 62% → 90%+ coverage on google.py.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

from tokenade.handlers.google import GoogleHandler
from tokenade.handlers.base import (
    AuthStatus,
    SessionData,
)


class MockResponse:
    def __init__(self, status=200, json_data=None, text=""):
        self.status = status
        self.status_code = status
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


def mock_requests():
    mock = MagicMock()
    return patch.dict(sys.modules, {"requests": mock}), mock


class TestGoogleHandlerCheckAuth(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = GoogleHandler(self.mock_browser)

    def test_no_browser(self):
        handler = GoogleHandler(None)
        self.assertEqual(handler.check_auth_status(), AuthStatus.UNKNOWN)

    def test_non_200_response(self):
        self.mock_browser.navigate.return_value = MockResponse(403)
        self.assertEqual(self.handler.check_auth_status(), AuthStatus.LOGGED_OUT)

    def test_exception(self):
        self.mock_browser.navigate.side_effect = Exception("err")
        self.assertEqual(self.handler.check_auth_status(), AuthStatus.UNKNOWN)


class TestGoogleHandlerExtractTokens(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = GoogleHandler(self.mock_browser)

    def test_not_authenticated(self):
        self.mock_browser.navigate.return_value = MockResponse(200, {})
        self.assertEqual(len(self.handler.extract_tokens()), 0)

    def test_already_has_token(self):
        self.handler._access_token = "existing_token"
        self.handler._token_expires = "2099-01-01T00:00:00Z"
        self.handler._user_info = {"email": "test@gmail.com", "name": "Test"}
        tokens = self.handler.extract_tokens()
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].value, "existing_token")

    def test_token_with_invalid_expiry(self):
        self.handler._access_token = "tok"
        self.handler._token_expires = "not-a-date"
        self.handler._user_info = None
        tokens = self.handler.extract_tokens()
        self.assertEqual(len(tokens), 1)
        self.assertIsNone(tokens[0].expires_at)

    def test_token_no_expiry(self):
        self.handler._access_token = "tok"
        self.handler._token_expires = None
        self.handler._user_info = {}
        tokens = self.handler.extract_tokens()
        self.assertEqual(len(tokens), 1)
        self.assertIsNone(tokens[0].expires_at)

    def test_token_expiry_with_z_suffix(self):
        self.handler._access_token = "tok"
        self.handler._token_expires = "2025-12-31T23:59:59Z"
        self.handler._user_info = {}
        tokens = self.handler.extract_tokens()
        self.assertEqual(len(tokens), 1)
        self.assertIsNotNone(tokens[0].expires_at)


class TestGoogleHandlerExtractCookies(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = GoogleHandler(self.mock_browser)

    def test_no_browser(self):
        handler = GoogleHandler(None)
        self.assertEqual(handler.extract_cookies(), [])

    def test_filters_google_domains(self):
        self.mock_browser.get_cookies.return_value = [
            {"name": "SID", "domain": ".google.com"},
            {"name": "HSID", "domain": ".google.com"},
            {"name": "other", "domain": ".example.com"},
            {"name": "mail_cookie", "domain": "mail.google.com"},
            {"name": "labs_cookie", "domain": "labs.google.com"},
        ]
        cookies = self.handler.extract_cookies()
        self.assertEqual(len(cookies), 4)
        domains = [c["domain"] for c in cookies]
        self.assertNotIn(".example.com", domains)

    def test_exception(self):
        self.mock_browser.get_cookies.side_effect = Exception("err")
        self.assertEqual(self.handler.extract_cookies(), [])


class TestGoogleHandlerValidateSession(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = GoogleHandler(self.mock_browser)

    def test_valid_with_sid(self):
        cookies = [{"name": "SID", "value": "abc"}, {"name": "HSID", "value": "def"}]
        self.assertTrue(self.handler.validate_session(cookies))

    def test_no_critical_cookies(self):
        self.assertFalse(self.handler.validate_session([{"name": "random", "value": "xyz"}]))

    def test_critical_without_sid(self):
        self.assertFalse(self.handler.validate_session([{"name": "HSID", "value": "def"}]))

    def test_empty_cookies(self):
        self.assertFalse(self.handler.validate_session([]))


class TestGoogleHandlerInjectSession(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = GoogleHandler(self.mock_browser)

    def test_inject_no_browser(self):
        handler = GoogleHandler(None)
        session = SessionData(site_name="google", auth_status=AuthStatus.LOGGED_IN)
        self.assertFalse(handler.inject_session(session))

    def test_inject_exception(self):
        self.mock_browser.add_cookies.side_effect = Exception("err")
        session = SessionData(
            site_name="google", auth_status=AuthStatus.LOGGED_IN,
            cookies=[{"name": "SID", "value": "abc"}],
        )
        self.assertFalse(self.handler.inject_session(session))

    def test_inject_success_after_verify(self):
        session = SessionData(
            site_name="google", auth_status=AuthStatus.LOGGED_IN,
            cookies=[{"name": "SID", "value": "abc"}],
        )
        self.mock_browser.navigate.return_value = MockResponse(200, {
            "access_token": "tok", "user": {"email": "test@gmail.com"},
        })
        with patch("time.sleep"):
            self.assertTrue(self.handler.inject_session(session))

    def test_inject_fails_verification(self):
        session = SessionData(
            site_name="google", auth_status=AuthStatus.LOGGED_IN,
            cookies=[{"name": "SID", "value": "abc"}],
        )
        self.mock_browser.navigate.return_value = MockResponse(200, {})
        with patch("time.sleep"):
            self.assertFalse(self.handler.inject_session(session))

    def test_inject_no_cookies(self):
        session = SessionData(
            site_name="google", auth_status=AuthStatus.LOGGED_IN, cookies=[],
        )
        self.mock_browser.navigate.return_value = MockResponse(200, {})
        with patch("time.sleep"):
            self.assertFalse(self.handler.inject_session(session))


class TestGoogleHandlerLogin(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = GoogleHandler(self.mock_browser)

    def test_no_browser_raises(self):
        handler = GoogleHandler(None)
        with self.assertRaises(RuntimeError):
            handler.login("email@test.com", "pass")

    def test_login_exception(self):
        self.mock_browser.navigate.side_effect = Exception("err")
        self.assertEqual(self.handler.login("email@test.com", "pass"), AuthStatus.LOGGED_OUT)

    def test_login_email_not_found(self):
        self.mock_browser.query_selector.side_effect = [None, None]
        self.mock_browser.navigate.return_value = MockResponse(403)
        with patch("time.sleep"):
            status = self.handler.login("email@test.com", "pass")
        self.assertEqual(status, AuthStatus.LOGGED_OUT)

    def test_login_full_flow(self):
        email_input = MagicMock()
        password_input = MagicMock()
        next_btn = MagicMock()
        self.mock_browser.query_selector.side_effect = [
            email_input, next_btn, password_input, next_btn,
        ]
        self.mock_browser.navigate.return_value = MockResponse(200, {
            "access_token": "tok", "user": {"email": "test@gmail.com"},
        })
        with patch("time.sleep"):
            status = self.handler.login("email@test.com", "pass")
        self.assertEqual(status, AuthStatus.LOGGED_IN)


class TestGoogleHandlerTestAPI(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = GoogleHandler(self.mock_browser)

    def test_test_api_success(self):
        ctx, mock_req = mock_requests()
        with ctx:
            mock_req.post.return_value = MockResponse(200, {"images": ["url1"]})
            result = self.handler.test_api("tok123", prompt="a dog")
            self.assertIsNotNone(result)
            self.assertIn("images", result)

    def test_test_api_failure(self):
        ctx, mock_req = mock_requests()
        with ctx:
            mock_req.post.return_value = MockResponse(401, text="unauthorized")
            self.assertIsNone(self.handler.test_api("tok123"))

    def test_test_api_exception(self):
        ctx, mock_req = mock_requests()
        with ctx:
            mock_req.post.side_effect = Exception("network error")
            self.assertIsNone(self.handler.test_api("tok123"))

    def test_test_api_default_prompt(self):
        ctx, mock_req = mock_requests()
        with ctx:
            mock_req.post.return_value = MockResponse(200, {"ok": True})
            result = self.handler.test_api("tok123")
            self.assertIsNotNone(result)
            call_args = mock_req.post.call_args
            payload = call_args[1]["json"]
            self.assertEqual(payload["prompt"], "a cat")


class TestGoogleHandlerGetGmailCookies(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = GoogleHandler(self.mock_browser)

    def test_filters_gmail(self):
        self.mock_browser.get_cookies.return_value = [
            {"name": "SID", "domain": ".google.com"},
            {"name": "mail_cookie", "domain": "mail.google.com"},
            {"name": "labs_cookie", "domain": "labs.google.com"},
        ]
        cookies = self.handler.get_gmail_cookies()
        self.assertEqual(len(cookies), 1)
        self.assertEqual(cookies[0]["domain"], "mail.google.com")


class TestGoogleHandlerGetLabsCookies(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = GoogleHandler(self.mock_browser)

    def test_filters_labs(self):
        self.mock_browser.get_cookies.return_value = [
            {"name": "SID", "domain": ".google.com"},
            {"name": "mail_cookie", "domain": "mail.google.com"},
            {"name": "labs_cookie", "domain": "labs.google.com"},
        ]
        cookies = self.handler.get_labs_cookies()
        self.assertEqual(len(cookies), 1)
        self.assertEqual(cookies[0]["domain"], "labs.google.com")


class TestGoogleHandlerGetSession(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = GoogleHandler(self.mock_browser)

    def test_get_session_not_logged_in(self):
        self.mock_browser.navigate.return_value = MockResponse(200, {})
        session = self.handler.get_session()
        self.assertEqual(session.site_name, "google")
        self.assertEqual(session.auth_status, AuthStatus.LOGGED_OUT)
        self.assertEqual(len(session.tokens), 0)
        self.assertEqual(len(session.cookies), 0)

    def test_get_session_logged_in(self):
        self.mock_browser.navigate.return_value = MockResponse(200, {
            "access_token": "tok", "user": {"email": "test@gmail.com"},
        })
        self.mock_browser.get_cookies.return_value = [
            {"name": "SID", "domain": ".google.com"},
        ]
        session = self.handler.get_session()
        self.assertEqual(session.auth_status, AuthStatus.LOGGED_IN)
        self.assertEqual(len(session.tokens), 1)
        self.assertEqual(len(session.cookies), 1)


if __name__ == "__main__":
    unittest.main()
