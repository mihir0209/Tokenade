"""
Tests for TLS/JA3 fingerprint matching.
"""

import pytest
from unittest.mock import MagicMock
from tokenade.core.runtime.tls_matcher import TLSMatcher, TLSFingerprint, create_tls_matcher


def _has_curl_cffi():
    try:
        import curl_cffi.requests  # noqa: F401
        return True
    except ImportError:
        return False


class TestTLSFingerprint:
    """Test TLSFingerprint dataclass."""

    def test_default_fingerprint(self):
        fp = TLSFingerprint()
        assert fp.browser == "chrome"
        assert fp.version == "120"
        assert fp.platform == "windows"
        assert fp.impersonate == "chrome120"

    def test_custom_fingerprint(self):
        fp = TLSFingerprint(
            browser="firefox",
            version="120",
            impersonate="firefox120"
        )
        assert fp.browser == "firefox"
        assert fp.version == "120"
        assert fp.impersonate == "firefox120"


class TestTLSMatcher:
    """Test TLSMatcher class."""

    def test_init_default(self):
        matcher = TLSMatcher()
        assert matcher.fingerprint.browser == "chrome"
        assert matcher.fingerprint.impersonate == "chrome120"

    def test_init_custom(self):
        fp = TLSFingerprint(browser="firefox", impersonate="firefox120")
        matcher = TLSMatcher(fp)
        assert matcher.fingerprint.browser == "firefox"
        assert matcher.fingerprint.impersonate == "firefox120"

    def test_get_impersonate_target_known(self):
        matcher = TLSMatcher()
        target = matcher._get_impersonate_target("chrome", "120")
        assert target == "chrome120"

    def test_get_impersonate_target_unknown(self):
        matcher = TLSMatcher()
        target = matcher._get_impersonate_target("unknown", "1.0")
        assert target == "chrome120"  # Default fallback

    def test_request_with_mock(self):
        matcher = TLSMatcher()
        mock_session = MagicMock()
        matcher._session = mock_session

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"test"
        mock_session.request.return_value = mock_response

        response = matcher.get("https://example.com")

        assert response.status_code == 200
        mock_session.request.assert_called_once()

    def test_close(self):
        matcher = TLSMatcher()
        matcher._session = MagicMock()
        matcher.close()
        matcher._session.close.assert_called_once()

    def test_context_manager(self):
        with TLSMatcher() as matcher:
            assert matcher is not None


class TestCreateTLSMatcher:
    """Test create_tls_matcher factory function."""

    def test_default_chrome(self):
        matcher = create_tls_matcher()
        assert matcher.fingerprint.browser == "chrome"
        assert matcher.fingerprint.impersonate == "chrome120"

    def test_firefox(self):
        matcher = create_tls_matcher(browser="firefox", version="120")
        assert matcher.fingerprint.browser == "firefox"
        assert matcher.fingerprint.impersonate == "firefox120"

    def test_custom_impersonate(self):
        matcher = create_tls_matcher(impersonate="chrome131")
        assert matcher.fingerprint.impersonate == "chrome131"

    def test_brave_uses_chrome(self):
        matcher = create_tls_matcher(browser="brave")
        assert matcher.fingerprint.browser == "brave"
        assert matcher.fingerprint.impersonate == "chrome120"


class TestTLSMatcherIntegration:
    """Integration tests for TLS matcher (requires curl-cffi)."""

    @pytest.mark.skipif(
        not _has_curl_cffi(),
        reason="curl-cffi not installed"
    )
    def test_tls_matcher_init(self):
        matcher = TLSMatcher()
        assert matcher._session is not None

    @pytest.mark.skipif(
        not _has_curl_cffi(),
        reason="curl-cffi not installed"
    )
    def test_tls_get_request(self):
        matcher = TLSMatcher()
        response = matcher.get("https://httpbin.org/get")
        # httpbin may return 503 if unavailable, but the request should succeed
        assert response.status_code in [200, 503]
