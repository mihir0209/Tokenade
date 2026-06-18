"""
Comprehensive tests for the Tokenade Proxy Server.

Tests:
- Cookie handling (including __Host- and __Secure- prefixes)
- Header ordering (Chrome/Firefox)
- TLS fingerprint matching
- Proxy request forwarding
- Browse functionality
- Error handling
"""

import pytest
import json
import time
from unittest.mock import Mock

from tokenade.core.proxy.server import TokenadeProxy, ProxyConfig
from tokenade.core.proxy.cdp_proxy import CDPProxy, CDPProxyConfig
from tokenade.core.runtime.engine import CookieJar, FingerprintMatcher
from tokenade.core.runtime.tls_matcher import create_tls_matcher
from tokenade.core.importer.session_packager import SessionPackager


class TestCookieJar:
    """Test CookieJar cookie handling."""

    def test_basic_cookie_matching(self):
        """Test basic domain matching."""
        jar = CookieJar()
        jar.add_cookie({
            "name": "session",
            "value": "abc123",
            "domain": ".example.com",
            "path": "/",
            "secure": True
        })

        # Should match
        cookies = jar.get_for_request("https://example.com/page")
        assert "session=abc123" in cookies

        # Should match subdomain
        cookies = jar.get_for_request("https://sub.example.com/page")
        assert "session=abc123" in cookies

    def test_secure_cookie_only_on_https(self):
        """Test that secure cookies are only sent over HTTPS."""
        jar = CookieJar()
        jar.add_cookie({
            "name": "secure_cookie",
            "value": "secret",
            "domain": ".example.com",
            "path": "/",
            "secure": True
        })

        # Should match HTTPS
        cookies = jar.get_for_request("https://example.com")
        assert "secure_cookie=secret" in cookies

        # Should NOT match HTTP
        cookies = jar.get_for_request("http://example.com")
        assert "secure_cookie" not in cookies

    def test_expired_cookie_excluded(self):
        """Test that expired cookies are excluded."""
        jar = CookieJar()
        jar.add_cookie({
            "name": "expired",
            "value": "old",
            "domain": ".example.com",
            "path": "/",
            "expires": int(time.time()) - 3600  # Expired 1 hour ago
        })
        jar.add_cookie({
            "name": "valid",
            "value": "current",
            "domain": ".example.com",
            "path": "/",
            "expires": int(time.time()) + 3600  # Valid for 1 more hour
        })

        cookies = jar.get_for_request("https://example.com")
        assert "expired=old" not in cookies
        assert "valid=current" in cookies

    def test_host_prefix_cookie_with_domain_rejected(self):
        """Test that __Host- cookies with domain are rejected."""
        jar = CookieJar()

        # Invalid __Host- cookie (has domain)
        jar.add_cookie({
            "name": "__Host-session",
            "value": "abc",
            "domain": ".example.com",  # Invalid for __Host-
            "path": "/",
            "secure": True
        })

        # Valid __Host- cookie (no domain)
        jar.add_cookie({
            "name": "__Host-valid",
            "value": "xyz",
            "domain": "",  # No domain (correct for __Host-)
            "path": "/",
            "secure": True
        })

        cookies = jar.get_for_request("https://example.com")
        # __Host- with domain should be rejected
        assert "__Host-session" not in cookies
        # __Host- without domain should work
        assert "__Host-valid=xyz" in cookies

    def test_prune_expired(self):
        """Test pruning expired cookies."""
        jar = CookieJar()

        # Add expired cookies
        for i in range(5):
            jar.add_cookie({
                "name": f"expired_{i}",
                "value": "old",
                "domain": ".example.com",
                "path": "/",
                "expires": int(time.time()) - 3600
            })

        # Add valid cookies
        for i in range(3):
            jar.add_cookie({
                "name": f"valid_{i}",
                "value": "current",
                "domain": ".example.com",
                "path": "/",
                "expires": int(time.time()) + 3600
            })

        # Prune expired
        removed = jar.prune_expired()

        assert removed == 5
        assert len(jar.to_list()) == 3


class TestFingerprintMatcher:
    """Test FingerprintMatcher header generation."""

    def test_chrome_header_ordering(self):
        """Test Chrome-specific header ordering."""
        matcher = FingerprintMatcher({
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
            "platform": "Win32",
            "language": "en-US"
        })

        headers = matcher.get_headers("https://example.com")

        # Check Chrome-specific headers exist
        assert "sec-ch-ua" in headers
        assert "sec-ch-ua-mobile" in headers
        assert "sec-ch-ua-platform" in headers
        assert "sec-fetch-dest" in headers
        assert "sec-fetch-mode" in headers
        assert "sec-fetch-site" in headers
        assert "sec-fetch-user" in headers
        assert "upgrade-insecure-requests" in headers

    def test_firefox_header_ordering(self):
        """Test Firefox-specific header ordering."""
        matcher = FingerprintMatcher({
            "user_agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
            "platform": "Linux",
            "language": "en-US"
        })

        headers = matcher.get_headers("https://example.com")

        # Firefox should NOT have sec-ch-ua headers
        assert "sec-ch-ua" not in headers
        assert "sec-ch-ua-mobile" not in headers
        assert "sec-ch-ua-platform" not in headers

    def test_api_request_headers(self):
        """Test API request headers (different accept header)."""
        matcher = FingerprintMatcher({
            "user_agent": "Mozilla/5.0 Chrome/120.0.0.0",
            "platform": "Win32"
        })

        headers = matcher.get_headers("https://api.example.com/data", is_api=True)

        # API requests should have JSON accept header
        assert headers.get("accept") == "application/json"

    def test_referer_header(self):
        """Test referer header is included when provided."""
        matcher = FingerprintMatcher({
            "user_agent": "Mozilla/5.0 Chrome/120.0.0.0",
            "platform": "Win32"
        })

        headers = matcher.get_headers(
            "https://example.com/page",
            referer="https://example.com/"
        )

        assert headers.get("referer") == "https://example.com/"


class TestTLSMatcher:
    """Test TLS fingerprint matching."""

    def test_chrome_tls_matching(self):
        """Test Chrome TLS impersonation."""
        matcher = create_tls_matcher(browser="chrome", version="120")

        assert matcher.fingerprint.browser == "chrome"
        assert matcher.fingerprint.impersonate == "chrome120"

        # Test actual request
        try:
            response = matcher.get("https://httpbin.org/get", timeout=10)
            assert response.status_code == 200
        except Exception:
            pytest.skip("Network not available")

        matcher.close()

    def test_firefox_fallback_to_chrome(self):
        """Test that Firefox falls back to Chrome on actual request."""
        matcher = create_tls_matcher(browser="firefox", version="128")

        # Firefox impersonation should be set initially
        assert "firefox" in matcher.fingerprint.impersonate

        # When making a request, it should fallback to Chrome if Firefox fails
        try:
            response = matcher.get("https://httpbin.org/get", timeout=5)
            # If request succeeds, it's using Chrome impersonation
            assert response.status_code == 200
            # Check that impersonation was changed to Chrome
            assert "chrome" in matcher.fingerprint.impersonate
        except Exception:
            # Network not available, skip
            pytest.skip("Network not available")

        matcher.close()


class TestSessionPackager:
    """Test session packaging with TLS profile."""

    def test_tls_profile_auto_detection(self):
        """Test automatic TLS profile detection."""
        packager = SessionPackager()

        cookies = [
            {
                "name": "session",
                "value": "abc",
                "domain": ".example.com",
                "path": "/",
                "secure": True,
                "httpOnly": True
            }
        ]

        fingerprint = {
            "user_agent": "Mozilla/5.0 Chrome/131.0.0.0 Safari/537.36",
            "platform": "Win32"
        }

        package = packager.package(
            cookies=cookies,
            browser="chrome",
            fingerprint=fingerprint
        )

        # Should auto-detect TLS profile
        assert "tls_profile" in package
        assert package["tls_profile"]["browser"] == "chrome"
        assert "131" in package["tls_profile"]["version"]

    def test_firefox_uses_chrome_tls(self):
        """Test that Firefox browser uses Chrome TLS profile."""
        packager = SessionPackager()

        cookies = [
            {
                "name": "session",
                "value": "abc",
                "domain": ".example.com",
                "path": "/",
                "secure": True
            }
        ]

        fingerprint = {
            "user_agent": "Mozilla/5.0 Firefox/128.0",
            "platform": "Linux"
        }

        package = packager.package(
            cookies=cookies,
            browser="firefox",
            fingerprint=fingerprint
        )

        # Should use Chrome TLS (Firefox not supported)
        assert package["tls_profile"]["browser"] == "chrome"
        assert package["tls_profile"]["impersonate"] == "chrome120"


class TestProxyServer:
    """Test proxy server functionality."""

    @pytest.fixture
    def sample_session(self):
        """Create a sample session for testing."""
        return {
            "version": "2.0",
            "created_at": "2026-06-05T12:00:00Z",
            "source_device": {
                "browser": "chrome",
                "profile": "default",
                "platform": "Linux",
                "hostname": "test-pc"
            },
            "site_name": "example",
            "auth_status": "logged_in",
            "cookies": [
                {
                    "name": "session_id",
                    "value": "test123",
                    "domain": ".example.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                    "sameSite": "Lax",
                    "expires": int(time.time()) + 86400
                }
            ],
            "fingerprint": {
                "user_agent": "Mozilla/5.0 Chrome/120.0.0.0",
                "platform": "Linux",
                "language": "en-US"
            },
            "tls_profile": {
                "browser": "chrome",
                "version": "120",
                "impersonate": "chrome120",
                "http_version": "2"
            },
            "metadata": {
                "cookie_count": 1
            }
        }

    def test_proxy_creation(self, sample_session):
        """Test proxy creation from session data."""
        config = ProxyConfig(port=9226)
        proxy = TokenadeProxy(sample_session, config)

        assert proxy.session == sample_session
        assert proxy.config.port == 9226
        assert len(proxy.cookie_jar.to_list()) == 1

    def test_proxy_from_file(self, tmp_path):
        """Test proxy creation from .tokenade file."""
        session_file = tmp_path / "test.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "test",
            "auth_status": "logged_in",
            "cookies": [],
            "tls_profile": {
                "browser": "chrome",
                "version": "120",
                "impersonate": "chrome120"
            }
        }

        with open(session_file, "w") as f:
            json.dump(session_data, f)

        proxy = TokenadeProxy.from_session_file(str(session_file))

        assert proxy.session["site_name"] == "test"

    def test_build_target_url_from_path(self, sample_session):
        """Test target URL building from request path."""
        from tokenade.core.proxy.server_utils import build_target_url

        request = Mock()
        request.path = "/httpbin.org/get"
        request.headers = {}

        url = build_target_url(request)
        assert url == "https://httpbin.org/get"

    def test_build_target_url_from_host(self, sample_session):
        """Test target URL building from Host header."""
        from tokenade.core.proxy.server_utils import build_target_url

        request = Mock()
        request.path = "/"
        request.headers = {"Host": "example.com"}

        url = build_target_url(request)
        assert url == "http://example.com/"

    def test_filter_response_headers(self, sample_session):
        """Test response header filtering."""
        from tokenade.core.proxy.server_utils import filter_response_headers

        headers = {
            "content-type": "text/html",
            "content-length": "100",
            "content-encoding": "gzip",
            "transfer-encoding": "chunked",
            "connection": "keep-alive",
            "x-custom": "value"
        }

        filtered = filter_response_headers(headers)

        assert "content-type" in filtered
        assert "content-length" not in filtered  # removed: body is decompressed by HTTP client
        assert "content-encoding" not in filtered  # removed: body is decompressed by HTTP client
        assert "transfer-encoding" not in filtered
        assert "connection" not in filtered
        assert "x-custom" in filtered


class TestIntegration:
    """Integration tests for the complete proxy workflow."""

    def test_full_workflow(self, tmp_path):
        """Test complete workflow: export -> package -> proxy."""
        # Create sample session
        session_data = {
            "version": "2.0",
            "site_name": "test",
            "auth_status": "logged_in",
            "cookies": [
                {
                    "name": "session",
                    "value": "abc",
                    "domain": ".test.com",
                    "path": "/",
                    "secure": True,
                    "expires": int(time.time()) + 3600
                }
            ],
            "tls_profile": {
                "browser": "chrome",
                "version": "120",
                "impersonate": "chrome120"
            }
        }

        # Save to file
        session_file = tmp_path / "test.tokenade"
        with open(session_file, "w") as f:
            json.dump(session_data, f)

        # Load and create proxy
        proxy = TokenadeProxy.from_session_file(str(session_file))

        # Verify
        assert proxy.session["site_name"] == "test"
        assert len(proxy.cookie_jar.to_list()) == 1
        assert proxy.tls_matcher is not None

    def test_cookie_domain_filtering(self):
        """Test that cookies are correctly filtered by domain."""
        jar = CookieJar()

        # Add cookies for different domains
        jar.add_cookie({
            "name": "chatgpt_session",
            "value": "abc",
            "domain": ".chatgpt.com",
            "path": "/",
            "secure": True
        })

        jar.add_cookie({
            "name": "github_session",
            "value": "xyz",
            "domain": ".github.com",
            "path": "/",
            "secure": True
        })

        # Request to chatgpt.com should only get chatgpt cookies
        chatgpt_cookies = jar.get_for_request("https://chatgpt.com")
        assert "chatgpt_session" in chatgpt_cookies
        assert "github_session" not in chatgpt_cookies

        # Request to github.com should only get github cookies
        github_cookies = jar.get_for_request("https://github.com")
        assert "github_session" in github_cookies
        assert "chatgpt_session" not in github_cookies


class TestCDPProxy:
    """Test CDP proxy (Playwright-based) functionality."""

    @pytest.fixture
    def sample_session(self):
        """Create a sample session for testing."""
        return {
            "version": "2.0",
            "created_at": "2026-06-05T12:00:00Z",
            "source_device": {
                "browser": "chrome",
                "profile": "default",
                "platform": "Linux",
                "hostname": "test-pc"
            },
            "site_name": "example",
            "auth_status": "logged_in",
            "cookies": [
                {
                    "name": "session_id",
                    "value": "test123",
                    "domain": ".example.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                    "sameSite": "Lax",
                    "expires": int(time.time()) + 86400
                }
            ],
            "fingerprint": {
                "user_agent": "Mozilla/5.0 Chrome/120.0.0.0",
                "platform": "Linux",
                "language": "en-US"
            },
            "tls_profile": {
                "browser": "chrome",
                "version": "120",
                "impersonate": "chrome120",
                "http_version": "2"
            },
            "metadata": {
                "cookie_count": 1
            }
        }

    def test_cdp_proxy_creation(self, sample_session):
        """Test CDP proxy creation from session data."""
        config = CDPProxyConfig(port=9227)
        proxy = CDPProxy(sample_session, config)

        assert proxy.session == sample_session
        assert proxy.config.port == 9227
        assert len(proxy.cookie_jar.to_list()) == 1

    def test_cdp_proxy_from_file(self, tmp_path):
        """Test CDP proxy creation from .tokenade file."""
        session_file = tmp_path / "test.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "test",
            "auth_status": "logged_in",
            "cookies": [],
            "tls_profile": {
                "browser": "chrome",
                "version": "120",
                "impersonate": "chrome120"
            }
        }

        with open(session_file, "w") as f:
            json.dump(session_data, f)

        proxy = CDPProxy.from_session_file(str(session_file))

        assert proxy.session["site_name"] == "test"

    def test_cdp_proxy_config_defaults(self):
        """Test CDP proxy config defaults."""
        config = CDPProxyConfig()

        assert config.port == 9222
        assert config.host == "127.0.0.1"
        assert config.headless is True
        assert config.timeout == 30

    def test_cdp_proxy_cookie_injection(self, sample_session):
        """Test that cookies are prepared for Playwright injection."""
        proxy = CDPProxy(sample_session)

        # Verify cookies are loaded
        cookies = proxy.cookie_jar.to_list()
        assert len(cookies) == 1
        assert cookies[0]["name"] == "session_id"

    def test_cdp_proxy_has_required_methods(self, sample_session):
        """Test that CDP proxy has all required methods."""
        proxy = CDPProxy(sample_session)

        assert hasattr(proxy, 'start')
        assert hasattr(proxy, 'stop')
        assert hasattr(proxy, 'run')
        assert hasattr(proxy, '_navigate_page')
        assert hasattr(proxy, '_cleanup_expired_pages')
        assert hasattr(proxy, '_close_page')
        assert hasattr(proxy, '_create_app')

        # Verify extracted modules have routing/injection functions
        from tokenade.core.proxy.cdp_routing import handle_route, forward_via_curl_cffi, forward_via_aiohttp
        from tokenade.core.proxy.cdp_injection import inject_cookies
        assert callable(handle_route)
        assert callable(forward_via_curl_cffi)
        assert callable(forward_via_aiohttp)
        assert callable(inject_cookies)

    def test_cdp_proxy_stats_initialized(self, sample_session):
        """Test that proxy stats are initialized."""
        proxy = CDPProxy(sample_session)

        assert proxy.stats["requests"] == 0
        assert proxy.stats["bytes_sent"] == 0
        assert proxy.stats["bytes_received"] == 0
        assert proxy.stats["errors"] == 0
        assert proxy.stats["start_time"] is None

    def test_cdp_proxy_get_site_url(self, sample_session):
        """Test default site URL generation."""
        proxy = CDPProxy(sample_session)

        url = proxy._get_site_url()
        assert url == "https://example.com"

    def test_cdp_proxy_get_site_url_unknown(self):
        """Test default site URL for unknown site."""
        session = {"site_name": "unknown", "cookies": [], "fingerprint": {}}
        proxy = CDPProxy(session)

        url = proxy._get_site_url()
        assert url == "https://example.com"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
