"""Tests for OAuth token refresh engine."""
import json
import time
from unittest.mock import patch, MagicMock

from tokenade.core.refresh.oauth_refresh import (
    OAuthConfig,
    OAuthTokenRefresher,
    CookieToTokenConverter,
    SessionOAuthManager,
    TokenPair,
    RefreshResult,
    KNOWN_OAUTH_CONFIGS,
    get_oauth_config_for_site,
    create_oauth_config,
)


class TestOAuthConfig:
    def test_default_config(self):
        config = OAuthConfig(token_endpoint="https://example.com/token", client_id="test-id")
        assert config.token_endpoint == "https://example.com/token"
        assert config.client_id == "test-id"
        assert config.client_secret == ""
        assert config.scopes == ["openid", "profile", "email"]
        assert config.grant_type == "refresh_token"

    def test_to_dict(self):
        config = OAuthConfig(
            token_endpoint="https://example.com/token",
            client_id="test-id",
            client_secret="secret",
            scopes=["email"],
        )
        d = config.to_dict()
        assert d["token_endpoint"] == "https://example.com/token"
        assert d["client_id"] == "test-id"
        assert d["client_secret"] == "secret"
        assert d["scopes"] == ["email"]

    def test_from_dict(self):
        data = {
            "token_endpoint": "https://example.com/token",
            "client_id": "test-id",
            "client_secret": "secret",
            "scopes": ["repo"],
            "grant_type": "authorization_code",
        }
        config = OAuthConfig.from_dict(data)
        assert config.token_endpoint == "https://example.com/token"
        assert config.client_id == "test-id"
        assert config.scopes == ["repo"]
        assert config.grant_type == "authorization_code"

    def test_from_dict_defaults(self):
        config = OAuthConfig.from_dict({})
        assert config.token_endpoint == ""
        assert config.scopes == ["openid", "profile", "email"]


class TestTokenPair:
    def test_not_expired(self):
        tokens = TokenPair(
            access_token="test-token",
            expires_at=time.time() + 3600,
        )
        assert not tokens.is_expired
        assert tokens.expires_in > 3500

    def test_expired(self):
        tokens = TokenPair(
            access_token="test-token",
            expires_at=time.time() - 100,
        )
        assert tokens.is_expired
        assert tokens.expires_in == 0

    def test_no_expiry(self):
        tokens = TokenPair(access_token="test-token")
        assert not tokens.is_expired
        assert tokens.expires_in is None

    def test_to_tokens_list(self):
        tokens = TokenPair(
            access_token="access-123",
            refresh_token="refresh-456",
            expires_at=1700000000.0,
        )
        lst = tokens.to_tokens_list()
        assert len(lst) == 2
        assert lst[0]["type"] == "access_token"
        assert lst[0]["value"] == "access-123"
        assert lst[0]["expires_at"] == 1700000000.0
        assert lst[1]["type"] == "refresh_token"
        assert lst[1]["value"] == "refresh-456"

    def test_from_tokens_list(self):
        lst = [
            {"type": "access_token", "value": "acc", "expires_at": 1700000000.0},
            {"type": "refresh_token", "value": "ref"},
        ]
        tokens = TokenPair.from_tokens_list(lst)
        assert tokens.access_token == "acc"
        assert tokens.refresh_token == "ref"
        assert tokens.expires_at == 1700000000.0

    def test_from_tokens_list_empty(self):
        tokens = TokenPair.from_tokens_list([])
        assert tokens.access_token == ""
        assert tokens.refresh_token is None


class TestRefreshResult:
    def test_success(self):
        result = RefreshResult(success=True, site_name="google")
        assert result.success
        assert result.site_name == "google"

    def test_failure(self):
        result = RefreshResult(success=False, error="token expired")
        assert not result.success
        assert result.error == "token expired"


class TestOAuthTokenRefresher:
    def test_refresh_success(self):
        config = OAuthConfig(
            token_endpoint="https://oauth2.example.com/token",
            client_id="test-client",
            client_secret="test-secret",
        )
        refresher = OAuthTokenRefresher(config)

        mock_response = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        with patch.object(refresher, "_make_refresh_request", return_value=mock_response):
            result = refresher.refresh_token("old-refresh-token")

        assert result.success
        assert result.tokens.access_token == "new-access-token"
        assert result.tokens.refresh_token == "new-refresh-token"
        assert result.tokens.expires_in > 3500

    def test_refresh_failure_no_token(self):
        config = OAuthConfig(
            token_endpoint="https://oauth2.example.com/token",
            client_id="test-client",
        )
        refresher = OAuthTokenRefresher(config)

        mock_response = {"error": "invalid_grant"}

        with patch.object(refresher, "_make_refresh_request", return_value=mock_response):
            result = refresher.refresh_token("bad-refresh-token")

        assert not result.success
        assert "No access_token in response" in result.error

    def test_refresh_exception(self):
        config = OAuthConfig(
            token_endpoint="https://oauth2.example.com/token",
            client_id="test-client",
        )
        refresher = OAuthTokenRefresher(config)

        with patch.object(refresher, "_make_refresh_request", side_effect=Exception("Network error")):
            result = refresher.refresh_token("refresh-token")

        assert not result.success
        assert "Network error" in result.error


class TestCookieToTokenConverter:
    def test_build_cookie_header(self):
        config = OAuthConfig(token_endpoint="https://example.com", client_id="test")
        converter = CookieToTokenConverter(config)

        cookies = [
            {"name": "session", "value": "abc123"},
            {"name": "token", "value": "xyz789"},
        ]
        header = converter._build_cookie_header(cookies)
        assert header == "session=abc123; token=xyz789"

    def test_build_cookie_header_empty(self):
        config = OAuthConfig(token_endpoint="https://example.com", client_id="test")
        converter = CookieToTokenConverter(config)
        header = converter._build_cookie_header([])
        assert header == ""


class TestSessionOAuthManager:
    def test_load_and_save(self, tmp_path):
        session_file = tmp_path / "test.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [],
            "tokens": [
                {"type": "access_token", "value": "acc", "expires_at": time.time() + 3600},
                {"type": "refresh_token", "value": "ref"},
            ],
            "oauth_config": {
                "token_endpoint": "https://oauth2.googleapis.com/token",
                "client_id": "test.apps.googleusercontent.com",
                "client_secret": "GOCSPX-test",
            },
            "metadata": {"refresh_count": 0},
        }
        session_file.write_text(json.dumps(session_data))

        manager = SessionOAuthManager(str(session_file))
        assert manager.has_oauth_config()
        assert manager.get_refresh_token() == "ref"
        assert manager.get_access_token() == "acc"
        assert not manager.needs_refresh()

    def test_needs_refresh_expired_token(self, tmp_path):
        session_file = tmp_path / "test.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [],
            "tokens": [
                {"type": "access_token", "value": "acc", "expires_at": time.time() - 100},
            ],
            "metadata": {},
        }
        session_file.write_text(json.dumps(session_data))

        manager = SessionOAuthManager(str(session_file))
        assert manager.needs_refresh()

    def test_update_tokens(self, tmp_path):
        session_file = tmp_path / "test.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [],
            "tokens": [
                {"type": "access_token", "value": "old-acc", "expires_at": 100},
            ],
            "metadata": {"refresh_count": 2},
        }
        session_file.write_text(json.dumps(session_data))

        manager = SessionOAuthManager(str(session_file))
        new_tokens = TokenPair(
            access_token="new-acc",
            refresh_token="new-ref",
            expires_at=time.time() + 3600,
        )
        manager.update_tokens(new_tokens)
        manager.save()

        manager2 = SessionOAuthManager(str(session_file))
        assert manager2.get_access_token() == "new-acc"
        assert manager2.get_refresh_token() == "new-ref"
        assert manager2.session["metadata"]["refresh_count"] == 3

    def test_get_status(self, tmp_path):
        session_file = tmp_path / "test.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [],
            "tokens": [
                {"type": "access_token", "value": "acc", "expires_at": time.time() + 3600},
                {"type": "refresh_token", "value": "ref"},
            ],
            "oauth_config": {
                "token_endpoint": "https://oauth2.googleapis.com/token",
                "client_id": "test.apps.googleusercontent.com",
            },
            "metadata": {"refresh_count": 5},
        }
        session_file.write_text(json.dumps(session_data))

        manager = SessionOAuthManager(str(session_file))
        status = manager.get_status()
        assert status["has_oauth_config"]
        assert status["has_refresh_token"]
        assert status["has_access_token"]
        assert not status["access_token_expired"]
        assert status["refresh_count"] == 5

    def test_refresh_with_config(self, tmp_path):
        session_file = tmp_path / "test.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [],
            "tokens": [
                {"type": "access_token", "value": "old-acc", "expires_at": 100},
                {"type": "refresh_token", "value": "old-ref"},
            ],
            "oauth_config": {
                "token_endpoint": "https://oauth2.googleapis.com/token",
                "client_id": "test.apps.googleusercontent.com",
                "client_secret": "GOCSPX-test",
            },
            "metadata": {"refresh_count": 0},
        }
        session_file.write_text(json.dumps(session_data))

        manager = SessionOAuthManager(str(session_file))
        mock_result = RefreshResult(
            success=True,
            tokens=TokenPair(
                access_token="new-acc",
                refresh_token="new-ref",
                expires_at=time.time() + 3600,
            ),
            refreshed_at="2026-01-01T00:00:00Z",
        )

        with patch.object(OAuthTokenRefresher, "refresh_token", return_value=mock_result):
            result = manager.refresh()

        assert result.success
        assert manager.get_access_token() == "new-acc"

    def test_no_oauth_config(self, tmp_path):
        session_file = tmp_path / "test.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [],
            "tokens": [],
            "metadata": {},
        }
        session_file.write_text(json.dumps(session_data))

        manager = SessionOAuthManager(str(session_file))
        assert not manager.has_oauth_config()
        result = manager.refresh()
        assert not result.success
        assert "No OAuth config" in result.error

    def test_no_refresh_token(self, tmp_path):
        session_file = tmp_path / "test.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [],
            "tokens": [
                {"type": "access_token", "value": "acc", "expires_at": 100},
            ],
            "oauth_config": {
                "token_endpoint": "https://oauth2.googleapis.com/token",
                "client_id": "test.apps.googleusercontent.com",
            },
            "metadata": {},
        }
        session_file.write_text(json.dumps(session_data))

        manager = SessionOAuthManager(str(session_file))
        result = manager.refresh()
        assert not result.success
        assert "No refresh token" in result.error


class TestKnownOAuthConfigs:
    def test_google_config(self):
        config = get_oauth_config_for_site("google")
        assert config is not None
        assert "googleapis.com" in config.token_endpoint

    def test_github_config(self):
        config = get_oauth_config_for_site("github")
        assert config is not None
        assert "github.com" in config.token_endpoint

    def test_unknown_site(self):
        config = get_oauth_config_for_site("unknown-site")
        assert config is None


class TestCreateOAuthConfig:
    def test_with_preconfigured_site(self):
        config = create_oauth_config("google", client_id="my-client-id")
        assert config.client_id == "my-client-id"
        assert "googleapis.com" in config.token_endpoint

    def test_with_custom_endpoint(self):
        config = create_oauth_config(
            "custom",
            client_id="my-id",
            token_endpoint="https://custom.com/token",
        )
        assert config.token_endpoint == "https://custom.com/token"
        assert config.client_id == "my-id"

    def test_with_custom_scopes(self):
        config = create_oauth_config(
            "google",
            client_id="my-id",
            scopes=["email", "calendar"],
        )
        assert config.scopes == ["email", "calendar"]
