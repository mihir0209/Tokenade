"""Tests for fingerprint matcher."""

import pytest
from tokenade.core.runtime.engine import FingerprintMatcher


class TestFingerprintMatcher:
    def test_creation_no_fingerprint(self):
        matcher = FingerprintMatcher(None)
        assert matcher is not None

    def test_creation_with_fingerprint(self):
        fp = {
            "user_agent": "Mozilla/5.0 TestAgent",
            "platform": "Linux",
            "language": "en-US",
        }
        matcher = FingerprintMatcher(fp)
        assert matcher is not None

    def test_get_headers_returns_dict(self):
        matcher = FingerprintMatcher({"user_agent": "Test/1.0", "platform": "Linux"})
        headers = matcher.get_headers("https://example.com")
        assert isinstance(headers, dict)
        assert "user-agent" in headers

    def test_default_ua(self):
        matcher = FingerprintMatcher({})
        headers = matcher.get_headers("https://example.com")
        assert "user-agent" in headers
        assert "Mozilla" in headers["user-agent"]

    def test_custom_ua(self):
        matcher = FingerprintMatcher({"user_agent": "CustomBot/2.0"})
        headers = matcher.get_headers("https://example.com")
        assert headers["user-agent"] == "CustomBot/2.0"

    def test_sec_fetch_headers(self):
        matcher = FingerprintMatcher({"user_agent": "Test/1.0", "platform": "Linux"})
        headers = matcher.get_headers("https://example.com/page")
        assert "sec-fetch-dest" in headers
        assert "sec-fetch-mode" in headers

    def test_accept_header(self):
        matcher = FingerprintMatcher({"user_agent": "Test/1.0", "platform": "Linux"})
        headers = matcher.get_headers("https://example.com/page")
        assert "accept" in headers

    def test_connection_header(self):
        matcher = FingerprintMatcher({"user_agent": "Test/1.0", "platform": "Linux"})
        headers = matcher.get_headers("https://example.com")
        assert headers.get("connection") == "keep-alive"

    def test_platform_header(self):
        matcher = FingerprintMatcher({"user_agent": "Test/1.0", "platform": "Windows"})
        headers = matcher.get_headers("https://example.com")
        assert "sec-ch-ua-platform" in headers

    def test_referer(self):
        matcher = FingerprintMatcher({"user_agent": "Test/1.0", "platform": "Linux"})
        headers = matcher.get_headers("https://example.com/page", referer="https://example.com/")
        assert headers.get("referer") == "https://example.com/"

    def test_api_accept(self):
        matcher = FingerprintMatcher({"user_agent": "Test/1.0", "platform": "Linux"})
        headers = matcher.get_headers("https://example.com/api/data", is_api=True)
        assert "application/json" in headers.get("accept", "")
