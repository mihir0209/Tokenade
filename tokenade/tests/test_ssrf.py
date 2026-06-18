"""Tests for SSRF protection."""

from tokenade.core.proxy.cdp_proxy import _is_safe_url


class TestSSRFProtection:
    def test_blocks_localhost(self):
        assert not _is_safe_url("http://localhost/admin")
        assert not _is_safe_url("http://127.0.0.1/admin")

    def test_blocks_private_10(self):
        assert not _is_safe_url("http://10.0.0.1/admin")
        assert not _is_safe_url("http://10.255.255.255/admin")
        assert not _is_safe_url("http://10.1.2.3:8080/secret")

    def test_blocks_private_172(self):
        assert not _is_safe_url("http://172.16.0.1/admin")
        assert not _is_safe_url("http://172.31.255.255/admin")
        assert not _is_safe_url("http://172.20.10.5/secret")

    def test_blocks_private_192(self):
        assert not _is_safe_url("http://192.168.1.1/admin")
        assert not _is_safe_url("http://192.168.0.0/secret")

    def test_blocks_link_local(self):
        assert not _is_safe_url("http://169.254.169.254/metadata")
        assert not _is_safe_url("http://169.254.0.1/admin")

    def test_blocks_loopback(self):
        assert not _is_safe_url("http://[::1]/admin")
        assert not _is_safe_url("http://[::1]:8080/admin")

    def test_blocks_metadata(self):
        assert not _is_safe_url("http://metadata.google.internal/computeMetadata/v1/")

    def test_blocks_zero(self):
        assert not _is_safe_url("http://0.0.0.0/admin")

    def test_allows_public(self):
        assert _is_safe_url("https://example.com")
        assert _is_safe_url("https://chatgpt.com")
        assert _is_safe_url("https://github.com/login")
        assert _is_safe_url("https://web.telegram.org")

    def test_allows_public_with_path(self):
        assert _is_safe_url("https://example.com/path/to/resource?q=1")

    def test_blocks_invalid_urls(self):
        assert not _is_safe_url("")
        assert not _is_safe_url("not-a-url")

    def test_blocks_private_ipv6(self):
        assert not _is_safe_url("http://[fc00::1]/admin")
        assert not _is_safe_url("http://[::1]/admin")
