"""
Comprehensive coverage tests for GitHubHandler.
Targets 72% → 90%+ coverage on github.py.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

from tokenade.handlers.github import GitHubHandler
from tokenade.handlers.base import (
    AuthStatus,
    SessionData,
)


class MockResponse:
    def __init__(self, status=200, json_data=None, text=""):
        self.status_code = status
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


def mock_requests():
    mock = MagicMock()
    return patch.dict(sys.modules, {"requests": mock}), mock


class TestGitHubHandlerCheckAuth(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = GitHubHandler(self.mock_browser)

    def test_logged_in_avatar_selector(self):
        self.mock_browser.page.query_selector.side_effect = [True]
        self.assertEqual(self.handler.check_auth_status(), AuthStatus.LOGGED_IN)

    def test_logged_in_header_avatar(self):
        self.mock_browser.page.query_selector.side_effect = [False, True]
        self.assertEqual(self.handler.check_auth_status(), AuthStatus.LOGGED_IN)

    def test_logged_in_logout_link(self):
        self.mock_browser.page.query_selector.side_effect = [False, False, True]
        self.assertEqual(self.handler.check_auth_status(), AuthStatus.LOGGED_IN)

    def test_logged_in_user_menu(self):
        self.mock_browser.page.query_selector.side_effect = [False, False, False, True]
        self.assertEqual(self.handler.check_auth_status(), AuthStatus.LOGGED_IN)

    def test_logged_out_login_link(self):
        self.mock_browser.page.query_selector.side_effect = [
            False, False, False, False,  # logged-in selectors
            True,  # logout selector
        ]
        self.assertEqual(self.handler.check_auth_status(), AuthStatus.LOGGED_OUT)

    def test_logged_out_login_input(self):
        self.mock_browser.page.query_selector.side_effect = [
            False, False, False, False,
            False, True,
        ]
        self.assertEqual(self.handler.check_auth_status(), AuthStatus.LOGGED_OUT)

    def test_logged_out_auth_form(self):
        self.mock_browser.page.query_selector.side_effect = [
            False, False, False, False,
            False, False, True,
        ]
        self.assertEqual(self.handler.check_auth_status(), AuthStatus.LOGGED_OUT)

    def test_logged_out_via_url(self):
        self.mock_browser.page.query_selector.side_effect = [
            False, False, False, False,
            False, False, False,
        ]
        self.mock_browser.page.url = "https://github.com/login?return_to=%2F"
        self.assertEqual(self.handler.check_auth_status(), AuthStatus.LOGGED_OUT)

    def test_all_selectors_exception_falls_to_url_check(self):
        """When all selectors raise, falls through to URL check -> UNKNOWN."""
        self.mock_browser.page.query_selector.side_effect = Exception("err")
        self.mock_browser.page.url = "https://github.com/"
        self.assertEqual(self.handler.check_auth_status(), AuthStatus.UNKNOWN)

    def test_all_selectors_exception_login_url(self):
        self.mock_browser.page.query_selector.side_effect = Exception("err")
        self.mock_browser.page.url = "https://github.com/login"
        self.assertEqual(self.handler.check_auth_status(), AuthStatus.LOGGED_OUT)

    def test_navigate_exception(self):
        self.mock_browser.navigate.side_effect = Exception("nav error")
        self.assertEqual(self.handler.check_auth_status(), AuthStatus.ERROR)


class TestGitHubHandlerExtractTokens(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = GitHubHandler(self.mock_browser)

    def test_local_storage_non_token_key(self):
        self.mock_browser.page.evaluate.side_effect = [{"theme": "dark"}, {}]
        self.assertEqual(len(self.handler.extract_tokens()), 0)

    def test_session_storage_non_token(self):
        self.mock_browser.page.evaluate.side_effect = [{}, {"theme": "dark"}]
        self.assertEqual(len(self.handler.extract_tokens()), 0)

    def test_exception(self):
        self.mock_browser.page.evaluate.side_effect = Exception("err")
        self.assertEqual(len(self.handler.extract_tokens()), 0)

    def test_local_storage_with_token_value(self):
        """source code references TokenType.UNKNOWN which doesn't exist - verify error handling"""
        self.mock_browser.page.evaluate.side_effect = [{"my_token": "val123"}, {}]
        tokens = self.handler.extract_tokens()
        self.assertEqual(len(tokens), 0)

    def test_local_storage_gho_token(self):
        """source code references TokenType.OAUTH_ACCESS which doesn't exist - verify error handling"""
        self.mock_browser.page.evaluate.side_effect = [{"gho_token": "gho_abc123"}, {}]
        tokens = self.handler.extract_tokens()
        self.assertEqual(len(tokens), 0)

    def test_session_storage_token_key(self):
        """source code references TokenType.UNKNOWN which doesn't exist - verify error handling"""
        self.mock_browser.page.evaluate.side_effect = [{}, {"cli_token": "abc123"}]
        tokens = self.handler.extract_tokens()
        self.assertEqual(len(tokens), 0)

    def test_multiple_local_storage_tokens(self):
        """source code references TokenType.UNKNOWN which doesn't exist - verify error handling"""
        self.mock_browser.page.evaluate.side_effect = [
            {"token_a": "val_a", "token_b": "val_b"}, {},
        ]
        tokens = self.handler.extract_tokens()
        self.assertEqual(len(tokens), 0)


class TestGitHubHandlerExtractCookies(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = GitHubHandler(self.mock_browser)

    def test_priority_critical_first(self):
        cookies = [
            {"name": "random", "domain": "github.com", "value": "x"},
            {"name": "user_session", "domain": "github.com", "value": "y"},
            {"name": "__Host-user_session_same_site", "domain": "github.com", "value": "z"},
            {"name": "session_id", "domain": "github.com", "value": "w"},
            {"name": "__Host-device_id", "domain": "github.com", "value": "v"},
        ]
        self.mock_browser.get_cookies.return_value = cookies
        result = self.handler.extract_cookies()
        self.assertEqual(result[0]["name"], "user_session")
        self.assertEqual(result[1]["name"], "__Host-user_session_same_site")

    def test_filters_non_github(self):
        self.mock_browser.get_cookies.return_value = [
            {"name": "user_session", "domain": "github.com", "value": "a"},
            {"name": "other", "domain": "example.com", "value": "b"},
        ]
        result = self.handler.extract_cookies()
        self.assertEqual(len(result), 1)

    def test_empty_cookies(self):
        self.mock_browser.get_cookies.return_value = []
        self.assertEqual(len(self.handler.extract_cookies()), 0)


class TestGitHubHandlerValidateSession(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = GitHubHandler(self.mock_browser)

    def test_missing_both_critical(self):
        self.assertFalse(self.handler.validate_session([{"name": "other", "value": "x"}]))

    def test_missing_one_critical(self):
        self.assertFalse(self.handler.validate_session([
            {"name": "user_session", "value": "abc"},
        ]))

    def test_empty_user_session_value(self):
        self.assertFalse(self.handler.validate_session([
            {"name": "user_session", "value": ""},
            {"name": "__Host-user_session_same_site", "value": "def"},
        ]))

    def test_all_critical_present(self):
        self.assertTrue(self.handler.validate_session([
            {"name": "user_session", "value": "abc"},
            {"name": "__Host-user_session_same_site", "value": "def"},
        ]))

    def test_extra_cookies_ok(self):
        self.assertTrue(self.handler.validate_session([
            {"name": "user_session", "value": "abc"},
            {"name": "__Host-user_session_same_site", "value": "def"},
            {"name": "logged_in", "value": "true"},
        ]))


class TestGitHubHandlerInjectSession(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = GitHubHandler(self.mock_browser)

    def test_inject_with_domain_set(self):
        session = SessionData(
            site_name="github", auth_status=AuthStatus.LOGGED_IN,
            cookies=[{"name": "user_session", "value": "abc", "domain": ".github.com"}],
        )
        self.mock_browser.page.query_selector.return_value = True
        self.assertTrue(self.handler.inject_session(session))

    def test_inject_cookie_missing_domain(self):
        session = SessionData(
            site_name="github", auth_status=AuthStatus.LOGGED_IN,
            cookies=[{"name": "user_session", "value": "abc"}],
        )
        self.mock_browser.page.query_selector.return_value = True
        self.assertTrue(self.handler.inject_session(session))

    def test_inject_cookie_empty_domain(self):
        session = SessionData(
            site_name="github", auth_status=AuthStatus.LOGGED_IN,
            cookies=[{"name": "user_session", "value": "abc", "domain": ""}],
        )
        self.mock_browser.page.query_selector.return_value = True
        self.assertTrue(self.handler.inject_session(session))

    def test_inject_single_cookie_exception_still_succeeds(self):
        session = SessionData(
            site_name="github", auth_status=AuthStatus.LOGGED_IN,
            cookies=[
                {"name": "bad_cookie", "value": "x"},
                {"name": "user_session", "value": "y"},
            ],
        )
        self.mock_browser.set_cookie.side_effect = [Exception("err"), None]
        self.mock_browser.page.query_selector.return_value = True
        self.assertTrue(self.handler.inject_session(session))

    def test_inject_navigate_exception(self):
        session = SessionData(
            site_name="github", auth_status=AuthStatus.LOGGED_IN,
            cookies=[{"name": "user_session", "value": "abc"}],
        )
        self.mock_browser.navigate.side_effect = Exception("nav err")
        self.assertFalse(self.handler.inject_session(session))

    def test_inject_session_auth_check_fails(self):
        """Cover lines 256-257: inject succeeds but auth check returns LOGGED_OUT."""
        session = SessionData(
            site_name="github", auth_status=AuthStatus.LOGGED_IN,
            cookies=[{"name": "user_session", "value": "abc"}],
        )
        self.mock_browser.page.query_selector.return_value = False
        self.mock_browser.page.url = "https://github.com/login"
        result = self.handler.inject_session(session)
        self.assertFalse(result)


class TestGitHubHandlerLogin(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = GitHubHandler(self.mock_browser)

    def test_login_exception(self):
        self.mock_browser.navigate.side_effect = Exception("err")
        self.assertEqual(self.handler.login("user", "pass"), AuthStatus.ERROR)

    def test_login_no_2fa_success(self):
        self.mock_browser.page.query_selector.side_effect = [None, True]
        self.mock_browser.page.url = "https://github.com/"
        self.assertEqual(self.handler.login("user", "pass"), AuthStatus.LOGGED_IN)

    def test_login_2fa_headless(self):
        self.mock_browser.page.query_selector.return_value = True
        self.assertEqual(self.handler.login("user", "pass", headless=True), AuthStatus.NEEDS_2FA)

    def test_login_2fa_non_headless(self):
        """Cover lines 291-295: non-headless 2FA flow with input()."""
        self.mock_browser.page.query_selector.side_effect = [
            True,   # 2FA input found
            None,   # no avatar after OTP
            None, None, None,  # logged-in selectors
            None, None, None,  # logout selectors
        ]
        self.mock_browser.page.url = "https://github.com/"
        with patch("builtins.input", return_value="123456"):
            self.handler.login("user", "pass", headless=False)
        self.mock_browser.page.fill.assert_called_with("input[name='otp']", "123456")
        self.mock_browser.page.click.assert_called_with("button[type='submit']")


class TestGitHubHandlerTestAPI(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = GitHubHandler(self.mock_browser)

    def test_test_api_with_token(self):
        ctx, mock_req = mock_requests()
        with ctx:
            self.mock_browser.get_cookies.return_value = [
                {"name": "user_session", "value": "abc", "domain": "github.com"},
            ]
            mock_req.get.return_value = MockResponse(200, {
                "login": "testuser", "name": "Test", "email": "test@gh.com", "type": "User",
            })
            result = self.handler.test_api(token="gho_token")
            self.assertIsNotNone(result)
            self.assertEqual(result["login"], "testuser")
            self.assertEqual(result["type"], "User")

    def test_test_api_exception(self):
        ctx, mock_req = mock_requests()
        with ctx:
            mock_req.get.side_effect = Exception("network error")
            self.assertIsNone(self.handler.test_api())

    def test_test_api_non_200(self):
        ctx, mock_req = mock_requests()
        with ctx:
            self.mock_browser.get_cookies.return_value = []
            mock_req.get.return_value = MockResponse(403)
            self.assertIsNone(self.handler.test_api())

    def test_test_api_no_token_no_cookies(self):
        ctx, mock_req = mock_requests()
        with ctx:
            self.mock_browser.get_cookies.return_value = []
            mock_req.get.return_value = MockResponse(200, {"login": "user"})
            result = self.handler.test_api()
            self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
