"""Tests for TLS matcher."""

from tokenade.core.runtime.tls_matcher import TLSMatcher, create_tls_matcher


class TestTLSMatcher:
    def test_create_chrome(self):
        matcher = create_tls_matcher(browser="chrome", version="120")
        assert isinstance(matcher, TLSMatcher)

    def test_create_firefox(self):
        matcher = create_tls_matcher(browser="firefox", version="120")
        assert isinstance(matcher, TLSMatcher)

    def test_create_with_impersonate(self):
        matcher = create_tls_matcher(browser="chrome", version="120", impersonate="chrome120")
        assert isinstance(matcher, TLSMatcher)

    def test_has_fingerprint(self):
        matcher = create_tls_matcher(browser="chrome", version="120")
        assert hasattr(matcher, 'fingerprint')

    def test_has_request_method(self):
        matcher = create_tls_matcher(browser="chrome", version="120")
        assert callable(getattr(matcher, 'request', None))


class TestCreateTLSMatcher:
    def test_default(self):
        matcher = create_tls_matcher()
        assert isinstance(matcher, TLSMatcher)

    def test_custom_version(self):
        matcher = create_tls_matcher(version="131")
        assert isinstance(matcher, TLSMatcher)

    def test_create_edge(self):
        matcher = create_tls_matcher(browser="edge", version="120")
        assert isinstance(matcher, TLSMatcher)
