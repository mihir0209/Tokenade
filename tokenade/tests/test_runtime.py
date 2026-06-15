"""
Unit tests for runtime engine module.
"""

import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch, mock_open

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tokenade.core.runtime.engine import (
    CookieJar,
    RuntimeConfig,
    RuntimeEngine,
    SessionValidator,
    create_engine_from_session,
)


class MockResponse:
    """Mock requests.Response."""
    def __init__(self, status_code=200, json_data=None, cookies=None, content=b"test"):
        self.status_code = status_code
        self._json = json_data or {}
        self.cookies = cookies or {}
        self.content = content
        self.headers = {"content-type": "application/json"}
    
    def json(self):
        return self._json


class TestRuntimeConfig(unittest.TestCase):
    """Test RuntimeConfig dataclass."""

    def test_defaults(self):
        """Test default configuration."""
        config = RuntimeConfig()
        self.assertEqual(config.timeout, 30)
        self.assertEqual(config.retries, 3)
        self.assertEqual(config.backoff_factor, 0.5)
        self.assertEqual(config.rate_limit, 0)
        self.assertTrue(config.verify_ssl)
        self.assertIsNone(config.proxy)
        self.assertEqual(config.custom_headers, {})
        self.assertEqual(config.cookies, [])
        self.assertEqual(config.tokens, [])
        self.assertIsNone(config.fingerprint)
        self.assertEqual(config.user_agent, "")

    def test_custom_values(self):
        """Test custom configuration."""
        config = RuntimeConfig(
            timeout=60,
            retries=5,
            proxy="http://proxy:8080",
            user_agent="CustomAgent/1.0",
        )
        self.assertEqual(config.timeout, 60)
        self.assertEqual(config.retries, 5)
        self.assertEqual(config.proxy, "http://proxy:8080")
        self.assertEqual(config.user_agent, "CustomAgent/1.0")


class TestCookieJar(unittest.TestCase):
    """Test CookieJar."""

    def setUp(self):
        """Create fresh CookieJar."""
        self.jar = CookieJar()

    def test_add_and_get(self):
        """Test adding and retrieving cookies."""
        cookie = {
            "name": "session",
            "value": "abc123",
            "domain": ".example.com",
            "path": "/",
        }
        self.jar.add_cookie(cookie)
        
        cookies = self.jar.to_list()
        self.assertEqual(len(cookies), 1)
        self.assertEqual(cookies[0]["name"], "session")

    def test_get_empty(self):
        """Test getting cookies for unknown domain."""
        cookie_str = self.jar.get_for_request("https://unknown.com")
        self.assertEqual(cookie_str, "")

    def test_clear(self):
        """Test clearing cookies."""
        self.jar.add_cookie({"name": "test", "value": "1", "domain": ".example.com"})
        self.jar.clear()
        self.assertEqual(self.jar.to_list(), [])

    def test_get_for_request(self):
        """Test formatting cookies for HTTP request."""
        self.jar.add_cookie({"name": "a", "value": "1", "domain": ".example.com"})
        self.jar.add_cookie({"name": "b", "value": "2", "domain": ".example.com"})
        
        cookie_str = self.jar.get_for_request("https://example.com/path")
        self.assertIn("a=1", cookie_str)
        self.assertIn("b=2", cookie_str)

    def test_get_for_request_no_match(self):
        """Test no cookies match domain."""
        self.jar.add_cookie({"name": "a", "value": "1", "domain": ".other.com"})
        cookie_str = self.jar.get_for_request("https://example.com")
        self.assertEqual(cookie_str, "")

    def test_add_invalid_cookie(self):
        """Test adding cookie without required fields - should not raise."""
        # The actual implementation doesn't validate, just stores
        self.jar.add_cookie({"name": "test"})
        cookies = self.jar.to_list()
        self.assertEqual(len(cookies), 1)
        self.assertEqual(cookies[0]["name"], "test")


class TestRuntimeEngineTokens(unittest.TestCase):
    """Test RuntimeEngine token handling."""

    def test_tokens_dict(self):
        """Test tokens are stored as dict."""
        config = RuntimeConfig(tokens=[
            {"token_type": "oauth", "value": "token123"},
            {"token_type": "refresh", "value": "refresh456"},
        ])
        
        with patch("requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            engine = RuntimeEngine(config)
            
            self.assertEqual(engine.tokens["oauth"]["value"], "token123")
            self.assertEqual(engine.tokens["refresh"]["value"], "refresh456")
            engine.close()

    def test_tokens_empty(self):
        """Test empty tokens list."""
        config = RuntimeConfig()
        
        with patch("requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            engine = RuntimeEngine(config)
            
            self.assertEqual(engine.tokens, {})
            engine.close()


class TestRuntimeEngine(unittest.TestCase):
    """Test RuntimeEngine with mocked HTTP."""

    def setUp(self):
        """Set up engine with mocked session."""
        self.config = RuntimeConfig(
            timeout=10,
            retries=2,
            rate_limit=0,
            use_tls_match=False,
        )
        
        with patch("requests.Session") as mock_session_class:
            self.mock_session = MagicMock()
            mock_session_class.return_value = self.mock_session
            self.engine = RuntimeEngine(self.config)
            self.engine._session = self.mock_session

    def tearDown(self):
        """Clean up engine."""
        self.engine.close()

    def test_initial_state(self):
        """Test initial engine state."""
        self.assertIsNotNone(self.engine.cookie_jar)
        self.assertIsNotNone(self.engine.tokens)
        self.assertIsNotNone(self.engine.fingerprint)
        self.assertEqual(self.engine.config.timeout, 10)

    def test_request_get(self):
        """Test GET request."""
        mock_response = MockResponse(200, {"data": "test"})
        self.mock_session.request.return_value = mock_response

        response = self.engine.get("https://api.example.com/data")

        self.assertEqual(response.status_code, 200)
        self.mock_session.request.assert_called_once()
        call_args = self.mock_session.request.call_args
        self.assertEqual(call_args[1]["method"], "GET")
        self.assertEqual(call_args[1]["url"], "https://api.example.com/data")

    def test_request_post(self):
        """Test POST request."""
        mock_response = MockResponse(201, {"id": 123})
        self.mock_session.request.return_value = mock_response

        response = self.engine.post(
            "https://api.example.com/create",
            json_data={"name": "test"},
        )

        self.assertEqual(response.status_code, 201)
        call_args = self.mock_session.request.call_args
        self.assertEqual(call_args[1]["method"], "POST")

    def test_request_with_cookies(self):
        """Test request includes cookies."""
        self.engine.cookie_jar.add_cookie({
            "name": "session",
            "value": "abc",
            "domain": ".example.com",
            "path": "/",
        })
        
        mock_response = MockResponse(200)
        self.mock_session.request.return_value = mock_response

        self.engine.get("https://example.com/page")

        call_args = self.mock_session.request.call_args
        headers = call_args[1]["headers"]
        self.assertIn("cookie", headers)
        self.assertIn("session=abc", headers["cookie"])

    def test_request_updates_cookie_jar(self):
        """Test response cookies update jar."""
        from http.cookiejar import Cookie
        
        mock_response = MockResponse(200)
        mock_cookie = MagicMock()
        mock_cookie.name = "new_cookie"
        mock_cookie.value = "new_value"
        mock_cookie.domain = ".example.com"
        mock_cookie.path = "/"
        mock_cookie.secure = True
        mock_response.cookies = [mock_cookie]
        
        self.mock_session.request.return_value = mock_response

        self.engine.get("https://example.com/page")

        cookies = self.engine.cookie_jar.to_list()
        self.assertTrue(any(c["name"] == "new_cookie" for c in cookies))

    def test_rate_limiting(self):
        """Test rate limiting between requests."""
        config = RuntimeConfig(rate_limit=0.1)
        
        with patch("requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            engine = RuntimeEngine(config)
            engine._session = mock_session
            engine._tls_matcher = None
            
            mock_session.request.return_value = MockResponse(200)
            
            start = time.time()
            engine.get("https://example.com/1")
            engine.get("https://example.com/2")
            elapsed = time.time() - start
            
            self.assertGreaterEqual(elapsed, 0.1)
            engine.close()

    def test_context_manager(self):
        """Test context manager protocol."""
        with patch("requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            
            with RuntimeEngine(self.config) as engine:
                self.assertIsNotNone(engine)
            
            mock_session.close.assert_called_once()

    def test_put_request(self):
        """Test PUT request."""
        mock_response = MockResponse(200)
        self.mock_session.request.return_value = mock_response

        response = self.engine.put("https://api.example.com/update", data={"key": "val"})

        self.assertEqual(response.status_code, 200)
        call_args = self.mock_session.request.call_args
        self.assertEqual(call_args[1]["method"], "PUT")

    def test_delete_request(self):
        """Test DELETE request."""
        mock_response = MockResponse(204)
        self.mock_session.request.return_value = mock_response

        response = self.engine.delete("https://api.example.com/item/1")

        self.assertEqual(response.status_code, 204)
        call_args = self.mock_session.request.call_args
        self.assertEqual(call_args[1]["method"], "DELETE")

    def test_custom_headers(self):
        """Test custom headers are applied."""
        config = RuntimeConfig(custom_headers={"X-Custom": "value"}, use_tls_match=False)
        
        with patch("requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            engine = RuntimeEngine(config)
            engine._session = mock_session
            
            mock_session.request.return_value = MockResponse(200)
            engine.get("https://example.com")
            
            call_args = mock_session.request.call_args
            headers = call_args[1]["headers"]
            self.assertEqual(headers["X-Custom"], "value")
            engine.close()

    def test_proxy_config(self):
        """Test proxy configuration."""
        config = RuntimeConfig(proxy="http://proxy:8080")
        
        with patch("requests.Session") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session
            engine = RuntimeEngine(config)
            
            self.assertEqual(engine._session.proxies["http"], "http://proxy:8080")
            engine.close()


class TestSessionValidator(unittest.TestCase):
    """Test SessionValidator."""

    def setUp(self):
        """Set up validator with mocked engine."""
        self.mock_engine = MagicMock()
        self.validator = SessionValidator(self.mock_engine)

    def test_validate_google_session_valid(self):
        """Test valid Google session."""
        mock_response = MockResponse(200, {
            "result": {"data": [{"id": 1}, {"id": 2}]},
        })
        self.mock_engine.get.return_value = mock_response

        result = self.validator.validate_google_session()

        self.assertTrue(result["valid"])
        self.assertEqual(result["projects"], 2)
        self.assertEqual(result["status_code"], 200)

    def test_validate_google_session_unauthorized(self):
        """Test unauthorized Google session."""
        mock_response = MockResponse(401)
        self.mock_engine.get.return_value = mock_response

        result = self.validator.validate_google_session()

        self.assertFalse(result["valid"])
        self.assertEqual(result["status_code"], 401)
        self.assertIn("Authentication failed", result["error"])

    def test_validate_google_session_error(self):
        """Test Google validation with exception."""
        self.mock_engine.get.side_effect = Exception("Network error")

        result = self.validator.validate_google_session()

        self.assertFalse(result["valid"])
        self.assertIn("Network error", result["error"])

    def test_validate_github_session_valid(self):
        """Test valid GitHub session."""
        mock_response = MockResponse(200, {
            "login": "testuser",
            "name": "Test User",
        })
        self.mock_engine.get.return_value = mock_response
        self.mock_engine.tokens = {"oauth_access": {"value": "token123"}}

        result = self.validator.validate_github_session()

        self.assertTrue(result["valid"])
        self.assertEqual(result["login"], "testuser")

    def test_validate_github_session_invalid_token(self):
        """Test GitHub session with invalid token."""
        mock_response = MockResponse(401)
        self.mock_engine.get.return_value = mock_response
        self.mock_engine.tokens = {}

        result = self.validator.validate_github_session()

        self.assertFalse(result["valid"])
        self.assertIn("Token expired", result["error"])

    def test_validate_generic_success(self):
        """Test generic validation success."""
        mock_response = MockResponse(200, content=b"OK")
        self.mock_engine.get.return_value = mock_response

        result = self.validator.validate_generic("https://example.com")

        self.assertTrue(result["valid"])
        self.assertEqual(result["status_code"], 200)

    def test_validate_generic_failure(self):
        """Test generic validation failure."""
        mock_response = MockResponse(500)
        self.mock_engine.get.return_value = mock_response

        result = self.validator.validate_generic("https://example.com")

        self.assertFalse(result["valid"])
        self.assertEqual(result["status_code"], 500)

    def test_validate_generic_custom_codes(self):
        """Test generic validation with custom success codes."""
        mock_response = MockResponse(201)
        self.mock_engine.get.return_value = mock_response

        result = self.validator.validate_generic(
            "https://example.com",
            success_codes=[200, 201],
        )

        self.assertTrue(result["valid"])


class TestCreateEngineFromSession(unittest.TestCase):
    """Test create_engine_from_session factory."""

    def test_create_from_session_file(self):
        """Test creating engine from session file."""
        session_data = {
            "fingerprint": {
                "user_agent": "Mozilla/5.0",
                "headers": {"accept": "text/html"},
            },
            "cookies": [{"name": "sid", "value": "abc"}],
            "tokens": [{"type": "oauth", "value": "token"}],
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(session_data, f)
            temp_path = f.name

        try:
            with patch("requests.Session") as mock_session_class:
                mock_session = MagicMock()
                mock_session_class.return_value = mock_session
                
                engine = create_engine_from_session(temp_path)
                
                self.assertEqual(engine.config.user_agent, "Mozilla/5.0")
                self.assertEqual(len(engine.cookie_jar.to_list()), 1)
                engine.close()
        finally:
            os.unlink(temp_path)

    def test_create_from_missing_file(self):
        """Test creating from non-existent file."""
        with self.assertRaises(FileNotFoundError):
            create_engine_from_session("/nonexistent/session.json")


if __name__ == "__main__":
    unittest.main()
