"""
Comprehensive coverage tests for GenericOAuth2Handler and subclasses.
Targets 0% → 80%+ coverage on generic_oauth.py.
"""

import sys
import time
import unittest
from unittest.mock import MagicMock, patch

from tokenade.handlers.generic_oauth import (
    OAuth2Config,
    GenericOAuth2Handler,
    DiscordOAuth2Handler,
    RedditOAuth2Handler,
)
from tokenade.handlers.base import (
    AuthStatus,
    ExtractedToken,
    SessionData,
    TokenType,
)


class MockResponse:
    def __init__(self, status=200, json_data=None, text=""):
        self.status_code = status
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


def mock_requests():
    """Return a context manager that mocks 'requests' in sys.modules."""
    mock = MagicMock()
    return patch.dict(sys.modules, {"requests": mock}), mock


class TestOAuth2Config(unittest.TestCase):
    def test_defaults(self):
        cfg = OAuth2Config(
            client_id="id", client_secret="secret",
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
        )
        self.assertEqual(cfg.redirect_uri, "http://localhost:8080/callback")
        self.assertEqual(cfg.scopes, ["openid", "profile", "email"])
        self.assertTrue(cfg.pkce_enabled)
        self.assertTrue(cfg.refresh_token_enabled)

    def test_custom_values(self):
        cfg = OAuth2Config(
            client_id="id", client_secret="secret",
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            redirect_uri="https://my.app/cb",
            scopes=["read", "write"],
            pkce_enabled=False,
            refresh_token_enabled=False,
        )
        self.assertEqual(cfg.redirect_uri, "https://my.app/cb")
        self.assertEqual(cfg.scopes, ["read", "write"])
        self.assertFalse(cfg.pkce_enabled)
        self.assertFalse(cfg.refresh_token_enabled)


class TestGenericOAuth2Handler(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = GenericOAuth2Handler(self.mock_browser)

    def test_init_with_config(self):
        config = {"oauth_config": {
            "client_id": "id", "client_secret": "secret",
            "authorization_endpoint": "https://auth.example.com/authorize",
            "token_endpoint": "https://auth.example.com/token",
        }}
        handler = GenericOAuth2Handler(config=config)
        self.assertIsNotNone(handler.oauth_config)
        self.assertEqual(handler.oauth_config.client_id, "id")

    def test_init_without_config(self):
        handler = GenericOAuth2Handler()
        self.assertIsNone(handler.oauth_config)

    def test_set_oauth_config(self):
        cfg = OAuth2Config(
            client_id="id", client_secret="secret",
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
        )
        self.handler.set_oauth_config(cfg)
        self.assertEqual(self.handler.oauth_config, cfg)
        self.assertIn("auth.example.com", self.handler.DOMAINS)
        self.assertEqual(self.handler.LOGIN_URL, "https://auth.example.com/authorize")

    def test_check_auth_status_no_browser(self):
        handler = GenericOAuth2Handler(None)
        self.assertEqual(handler.check_auth_status(), AuthStatus.ERROR)

    def test_check_auth_status_token_found_valid(self):
        self.mock_browser.evaluate.return_value = "valid_token"
        with patch.object(self.handler, "_validate_token", return_value=True):
            status = self.handler.check_auth_status()
        self.assertEqual(status, AuthStatus.LOGGED_IN)
        self.assertEqual(self.handler._access_token, "valid_token")

    def test_check_auth_status_token_expired_can_refresh(self):
        self.mock_browser.evaluate.return_value = "expired_token"
        self.handler._refresh_token = "refresh123"
        self.handler.oauth_config = OAuth2Config(
            client_id="id", client_secret="secret",
            authorization_endpoint="https://a.com/auth",
            token_endpoint="https://a.com/token",
            refresh_token_enabled=True,
        )
        with patch.object(self.handler, "_validate_token", return_value=False):
            status = self.handler.check_auth_status()
        self.assertEqual(status, AuthStatus.SESSION_EXPIRED)

    def test_check_auth_status_token_expired_no_refresh(self):
        self.mock_browser.evaluate.return_value = "expired_token"
        self.handler._refresh_token = None
        with patch.object(self.handler, "_validate_token", return_value=False):
            status = self.handler.check_auth_status()
        self.assertEqual(status, AuthStatus.LOGGED_OUT)

    def test_check_auth_status_token_expired_refresh_disabled(self):
        self.mock_browser.evaluate.return_value = "expired_token"
        self.handler._refresh_token = "ref123"
        self.handler.oauth_config = OAuth2Config(
            client_id="id", client_secret="secret",
            authorization_endpoint="https://a.com/auth",
            token_endpoint="https://a.com/token",
            refresh_token_enabled=False,
        )
        with patch.object(self.handler, "_validate_token", return_value=False):
            status = self.handler.check_auth_status()
        self.assertEqual(status, AuthStatus.LOGGED_OUT)

    def test_check_auth_status_no_token_session_cookies(self):
        self.mock_browser.evaluate.return_value = None
        self.mock_browser.get_cookies.return_value = [
            {"name": "session", "value": "abc"},
            {"name": "other", "value": "xyz"},
        ]
        status = self.handler.check_auth_status()
        self.assertEqual(status, AuthStatus.LOGGED_IN)

    def test_check_auth_status_no_token_no_cookies(self):
        self.mock_browser.evaluate.return_value = None
        self.mock_browser.get_cookies.return_value = []
        status = self.handler.check_auth_status()
        self.assertEqual(status, AuthStatus.LOGGED_OUT)

    def test_check_auth_status_exception(self):
        self.mock_browser.evaluate.side_effect = Exception("JS error")
        status = self.handler.check_auth_status()
        self.assertEqual(status, AuthStatus.ERROR)

    def test_extract_tokens_no_browser(self):
        handler = GenericOAuth2Handler(None)
        self.assertEqual(handler.extract_tokens(), [])

    def test_extract_tokens_with_all(self):
        self.mock_browser.evaluate.side_effect = [
            {"key": "access_token", "value": "acc123"},
            "ref456",
            1700000000,
        ]
        tokens = self.handler.extract_tokens()
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0].token_type, TokenType.ACCESS_TOKEN)
        self.assertEqual(tokens[0].value, "acc123")
        self.assertEqual(tokens[1].token_type, TokenType.REFRESH_TOKEN)
        self.assertEqual(tokens[1].value, "ref456")
        self.assertEqual(tokens[0].expires_at, 1700000000)

    def test_extract_tokens_access_only(self):
        self.mock_browser.evaluate.side_effect = [
            {"key": "oauth_token", "value": "tok789"}, None, None,
        ]
        tokens = self.handler.extract_tokens()
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].token_type, TokenType.ACCESS_TOKEN)

    def test_extract_tokens_none_found(self):
        self.mock_browser.evaluate.side_effect = [None, None, None]
        tokens = self.handler.extract_tokens()
        self.assertEqual(len(tokens), 0)

    def test_extract_tokens_exception(self):
        self.mock_browser.evaluate.side_effect = Exception("JS error")
        tokens = self.handler.extract_tokens()
        self.assertEqual(len(tokens), 0)

    def test_extract_cookies_no_browser(self):
        handler = GenericOAuth2Handler(None)
        self.assertEqual(handler.extract_cookies(), [])

    def test_extract_cookies_filters_oauth(self):
        self.mock_browser.get_cookies.return_value = [
            {"name": "session", "value": "a"},
            {"name": "oauth_state", "value": "b"},
            {"name": "random", "value": "c"},
            {"name": "auth_token", "value": "d"},
            {"name": "pkce_verifier", "value": "e"},
        ]
        cookies = self.handler.extract_cookies()
        names = [c["name"] for c in cookies]
        self.assertIn("session", names)
        self.assertIn("oauth_state", names)
        self.assertIn("auth_token", names)
        self.assertIn("pkce_verifier", names)
        self.assertNotIn("random", names)

    def test_extract_cookies_exception(self):
        self.mock_browser.get_cookies.side_effect = Exception("cookie error")
        self.assertEqual(self.handler.extract_cookies(), [])

    def test_validate_session_empty(self):
        self.assertFalse(self.handler.validate_session([]))

    def test_validate_session_has_critical(self):
        self.assertTrue(self.handler.validate_session([{"name": "session", "value": "abc"}]))

    def test_validate_session_no_critical(self):
        self.assertFalse(self.handler.validate_session([{"name": "random", "value": "xyz"}]))

    def test_inject_session_no_browser(self):
        handler = GenericOAuth2Handler(None)
        session = SessionData(site_name="test", auth_status=AuthStatus.LOGGED_IN)
        self.assertFalse(handler.inject_session(session))

    def test_inject_session_success(self):
        session = SessionData(
            site_name="test", auth_status=AuthStatus.LOGGED_IN,
            cookies=[{"name": "session", "value": "abc"}],
            tokens=[
                ExtractedToken(TokenType.ACCESS_TOKEN, "acc123"),
                ExtractedToken(TokenType.REFRESH_TOKEN, "ref456"),
            ],
        )
        result = self.handler.inject_session(session)
        self.assertTrue(result)
        self.mock_browser.add_cookies.assert_called_once()

    def test_inject_session_exception(self):
        self.mock_browser.add_cookies.side_effect = Exception("inject error")
        session = SessionData(
            site_name="test", auth_status=AuthStatus.LOGGED_IN,
            cookies=[{"name": "session", "value": "abc"}],
        )
        self.assertFalse(self.handler.inject_session(session))

    def test_inject_session_no_cookies(self):
        session = SessionData(
            site_name="test", auth_status=AuthStatus.LOGGED_IN,
            tokens=[ExtractedToken(TokenType.ACCESS_TOKEN, "acc")],
        )
        self.assertTrue(self.handler.inject_session(session))

    def test_refresh_access_token_no_refresh_token(self):
        self.assertIsNone(self.handler.refresh_access_token())

    def test_refresh_access_token_no_config(self):
        self.handler._refresh_token = "ref123"
        self.assertIsNone(self.handler.refresh_access_token())

    def test_refresh_access_token_success(self):
        ctx, mock_req = mock_requests()
        with ctx:
            self.handler._refresh_token = "ref123"
            self.handler.oauth_config = OAuth2Config(
                client_id="id", client_secret="secret",
                authorization_endpoint="https://a.com/auth",
                token_endpoint="https://a.com/token",
            )
            mock_req.post.return_value = MockResponse(200, {
                "access_token": "new_token", "expires_in": 7200,
            })
            result = self.handler.refresh_access_token()
            self.assertEqual(result, "new_token")
            self.assertEqual(self.handler._access_token, "new_token")

    def test_refresh_access_token_failure(self):
        ctx, mock_req = mock_requests()
        with ctx:
            self.handler._refresh_token = "ref123"
            self.handler.oauth_config = OAuth2Config(
                client_id="id", client_secret="secret",
                authorization_endpoint="https://a.com/auth",
                token_endpoint="https://a.com/token",
            )
            mock_req.post.return_value = MockResponse(400)
            self.assertIsNone(self.handler.refresh_access_token())

    def test_refresh_access_token_exception(self):
        ctx, mock_req = mock_requests()
        with ctx:
            self.handler._refresh_token = "ref123"
            self.handler.oauth_config = OAuth2Config(
                client_id="id", client_secret="secret",
                authorization_endpoint="https://a.com/auth",
                token_endpoint="https://a.com/token",
            )
            mock_req.post.side_effect = Exception("network error")
            self.assertIsNone(self.handler.refresh_access_token())

    def test_validate_token_expired(self):
        self.handler._token_expires_at = int(time.time()) - 100
        self.assertFalse(self.handler._validate_token("token"))

    def test_validate_token_valid_no_expiry(self):
        self.handler._token_expires_at = None
        self.assertTrue(self.handler._validate_token("token"))

    def test_validate_token_valid_future_expiry(self):
        self.handler._token_expires_at = int(time.time()) + 3600
        self.assertTrue(self.handler._validate_token("token"))

    def test_validate_token_introspection_active(self):
        ctx, mock_req = mock_requests()
        with ctx:
            self.handler._token_expires_at = None
            self.handler.oauth_config = OAuth2Config(
                client_id="id", client_secret="secret",
                authorization_endpoint="https://a.com/auth",
                token_endpoint="https://a.com/token",
            )
            self.handler.oauth_config.introspection_endpoint = "https://a.com/introspect"
            mock_req.post.return_value = MockResponse(200, {"active": True})
            self.assertTrue(self.handler._validate_token("token"))

    def test_validate_token_introspection_inactive(self):
        ctx, mock_req = mock_requests()
        with ctx:
            self.handler._token_expires_at = None
            self.handler.oauth_config = OAuth2Config(
                client_id="id", client_secret="secret",
                authorization_endpoint="https://a.com/auth",
                token_endpoint="https://a.com/token",
            )
            self.handler.oauth_config.introspection_endpoint = "https://a.com/introspect"
            mock_req.post.return_value = MockResponse(200, {"active": False})
            self.assertFalse(self.handler._validate_token("token"))

    def test_validate_token_introspection_error(self):
        ctx, mock_req = mock_requests()
        with ctx:
            self.handler._token_expires_at = None
            self.handler.oauth_config = OAuth2Config(
                client_id="id", client_secret="secret",
                authorization_endpoint="https://a.com/auth",
                token_endpoint="https://a.com/token",
            )
            self.handler.oauth_config.introspection_endpoint = "https://a.com/introspect"
            mock_req.post.side_effect = Exception("network error")
            self.assertTrue(self.handler._validate_token("token"))

    def test_build_authorization_url_no_config(self):
        handler = GenericOAuth2Handler()
        with self.assertRaises(ValueError):
            handler.build_authorization_url()

    def test_build_authorization_url_with_pkce(self):
        cfg = OAuth2Config(
            client_id="myid", client_secret="mysecret",
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            pkce_enabled=True,
        )
        self.handler.set_oauth_config(cfg)
        url = self.handler.build_authorization_url(state="mystate")
        self.assertIn("client_id=myid", url)
        self.assertIn("state=mystate", url)
        self.assertIn("code_challenge=", url)
        self.assertIn("code_challenge_method=S256", url)
        self.assertIn("response_type=code", url)
        self.assertTrue(hasattr(self.handler, "_pkce_verifier"))

    def test_build_authorization_url_without_pkce(self):
        cfg = OAuth2Config(
            client_id="myid", client_secret="mysecret",
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            pkce_enabled=False,
        )
        self.handler.set_oauth_config(cfg)
        url = self.handler.build_authorization_url()
        self.assertIn("client_id=myid", url)
        self.assertNotIn("code_challenge", url)


class TestDiscordOAuth2Handler(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = DiscordOAuth2Handler(self.mock_browser, {"client_id": "id", "client_secret": "secret"})

    def test_init_defaults(self):
        handler = DiscordOAuth2Handler()
        self.assertEqual(handler.SITE_NAME, "discord")
        self.assertIn("discord.com", handler.DOMAINS)
        self.assertIn("discordapp.com", handler.DOMAINS)

    def test_check_auth_status_no_browser(self):
        handler = DiscordOAuth2Handler(None)
        self.assertEqual(handler.check_auth_status(), AuthStatus.ERROR)

    def test_check_auth_status_logged_in(self):
        ctx, mock_req = mock_requests()
        with ctx:
            self.mock_browser.evaluate.return_value = "discord_token_abc"
            mock_req.get.return_value = MockResponse(200)
            status = self.handler.check_auth_status()
        self.assertEqual(status, AuthStatus.LOGGED_IN)
        self.assertEqual(self.handler._access_token, "discord_token_abc")

    def test_check_auth_status_401(self):
        ctx, mock_req = mock_requests()
        with ctx:
            self.mock_browser.evaluate.return_value = "discord_token_abc"
            mock_req.get.return_value = MockResponse(401)
            status = self.handler.check_auth_status()
        self.assertEqual(status, AuthStatus.LOGGED_OUT)

    def test_check_auth_status_no_token(self):
        self.mock_browser.evaluate.return_value = None
        status = self.handler.check_auth_status()
        self.assertEqual(status, AuthStatus.LOGGED_OUT)

    def test_check_auth_status_exception(self):
        self.mock_browser.evaluate.side_effect = Exception("err")
        status = self.handler.check_auth_status()
        self.assertEqual(status, AuthStatus.ERROR)

    def test_extract_tokens_no_browser(self):
        handler = DiscordOAuth2Handler(None)
        self.assertEqual(handler.extract_tokens(), [])

    def test_extract_tokens_with_token(self):
        self.mock_browser.evaluate.return_value = "gho_discord_token"
        tokens = self.handler.extract_tokens()
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].token_type, TokenType.BEARER_TOKEN)
        self.assertEqual(tokens[0].value, "gho_discord_token")

    def test_extract_tokens_no_token(self):
        self.mock_browser.evaluate.return_value = None
        self.assertEqual(self.handler.extract_tokens(), [])

    def test_extract_tokens_exception(self):
        self.mock_browser.evaluate.side_effect = Exception("err")
        self.assertEqual(self.handler.extract_tokens(), [])

    def test_inject_session_no_browser(self):
        handler = DiscordOAuth2Handler(None)
        self.assertFalse(handler.inject_session(
            SessionData(site_name="discord", auth_status=AuthStatus.LOGGED_IN)))

    def test_inject_session_success(self):
        session = SessionData(
            site_name="discord", auth_status=AuthStatus.LOGGED_IN,
            tokens=[ExtractedToken(TokenType.BEARER_TOKEN, "tok")],
            cookies=[{"name": "auth", "value": "abc"}],
        )
        self.assertTrue(self.handler.inject_session(session))

    def test_inject_session_with_access_token(self):
        session = SessionData(
            site_name="discord", auth_status=AuthStatus.LOGGED_IN,
            tokens=[ExtractedToken(TokenType.ACCESS_TOKEN, "tok")],
        )
        self.assertTrue(self.handler.inject_session(session))

    def test_inject_session_exception(self):
        self.mock_browser.evaluate.side_effect = Exception("err")
        session = SessionData(
            site_name="discord", auth_status=AuthStatus.LOGGED_IN,
            tokens=[ExtractedToken(TokenType.BEARER_TOKEN, "tok")],
        )
        self.assertFalse(self.handler.inject_session(session))


class TestRedditOAuth2Handler(unittest.TestCase):
    def setUp(self):
        self.mock_browser = MagicMock()
        self.handler = RedditOAuth2Handler(self.mock_browser, {"client_id": "id", "client_secret": "secret"})

    def test_init_defaults(self):
        handler = RedditOAuth2Handler()
        self.assertEqual(handler.SITE_NAME, "reddit")
        self.assertIn("reddit.com", handler.DOMAINS)

    def test_check_auth_status_no_browser(self):
        handler = RedditOAuth2Handler(None)
        self.assertEqual(handler.check_auth_status(), AuthStatus.ERROR)

    def test_check_auth_status_session_cookie(self):
        self.mock_browser.get_cookies.return_value = [{"name": "reddit_session", "value": "abc"}]
        self.assertEqual(self.handler.check_auth_status(), AuthStatus.LOGGED_IN)

    def test_check_auth_status_token_in_localstorage(self):
        self.mock_browser.get_cookies.return_value = []
        self.mock_browser.evaluate.return_value = "reddit_tok"
        self.assertEqual(self.handler.check_auth_status(), AuthStatus.LOGGED_IN)

    def test_check_auth_status_no_token(self):
        self.mock_browser.get_cookies.return_value = []
        self.mock_browser.evaluate.return_value = None
        self.assertEqual(self.handler.check_auth_status(), AuthStatus.LOGGED_OUT)

    def test_check_auth_status_exception(self):
        self.mock_browser.get_cookies.side_effect = Exception("err")
        self.assertEqual(self.handler.check_auth_status(), AuthStatus.ERROR)

    def test_extract_tokens_no_browser(self):
        handler = RedditOAuth2Handler(None)
        self.assertEqual(handler.extract_tokens(), [])

    def test_extract_tokens_with_tokens(self):
        self.mock_browser.evaluate.side_effect = ["reddit_tok", "reddit_refresh"]
        tokens = self.handler.extract_tokens()
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0].token_type, TokenType.BEARER_TOKEN)
        self.assertEqual(tokens[1].token_type, TokenType.REFRESH_TOKEN)

    def test_extract_tokens_bearer_only(self):
        self.mock_browser.evaluate.side_effect = ["bearer_tok", None]
        tokens = self.handler.extract_tokens()
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].token_type, TokenType.BEARER_TOKEN)

    def test_extract_tokens_none(self):
        self.mock_browser.evaluate.side_effect = [None, None]
        self.assertEqual(self.handler.extract_tokens(), [])

    def test_extract_tokens_exception(self):
        self.mock_browser.evaluate.side_effect = Exception("err")
        self.assertEqual(self.handler.extract_tokens(), [])

    def test_inject_session_no_browser(self):
        handler = RedditOAuth2Handler(None)
        self.assertFalse(handler.inject_session(
            SessionData(site_name="reddit", auth_status=AuthStatus.LOGGED_IN)))

    def test_inject_session_with_cookies_and_tokens(self):
        session = SessionData(
            site_name="reddit", auth_status=AuthStatus.LOGGED_IN,
            cookies=[{"name": "session", "value": "abc"}],
            tokens=[
                ExtractedToken(TokenType.BEARER_TOKEN, "bearer"),
                ExtractedToken(TokenType.REFRESH_TOKEN, "refresh"),
            ],
        )
        self.assertTrue(self.handler.inject_session(session))

    def test_inject_session_exception(self):
        self.mock_browser.add_cookies.side_effect = Exception("err")
        session = SessionData(
            site_name="reddit", auth_status=AuthStatus.LOGGED_IN,
            cookies=[{"name": "session", "value": "abc"}],
        )
        self.assertFalse(self.handler.inject_session(session))

    def test_inject_session_empty_tokens(self):
        session = SessionData(
            site_name="reddit", auth_status=AuthStatus.LOGGED_IN, tokens=[],
        )
        self.assertTrue(self.handler.inject_session(session))


if __name__ == "__main__":
    unittest.main()
