"""Tests for server_utils.py uncovered lines: 36, 89, 111-113, 167,
172-174, 185, 190-192, 227-229, 251-253.
"""

from unittest.mock import patch, MagicMock

from tokenade.core.proxy.server_utils import (
    build_target_url,
    rewrite_urls,
    rewrite_html_for_proxy,
    rewrite_js_for_proxy,
    rewrite_css_for_proxy,
)


# ---------------------------------------------------------------------------
# Line 36: build_target_url when path starts with http:// or https://
# ---------------------------------------------------------------------------

class TestBuildTargetUrlLine36:
    def test_path_starts_with_http(self):
        """Path directly starts with http:// (line 36 return path)."""
        req = MagicMock()
        req.path = "http://example.com/page"
        req.headers = {}
        result = build_target_url(req)
        assert result == "http://example.com/page"

    def test_path_starts_with_https(self):
        """Path directly starts with https:// (line 36 return path)."""
        req = MagicMock()
        req.path = "https://secure.example.com/page?q=1"
        req.headers = {}
        result = build_target_url(req)
        assert result == "https://secure.example.com/page?q=1"


# ---------------------------------------------------------------------------
# Line 89: rewrite_url empty url fallback (dead code but tested for completeness)
# ---------------------------------------------------------------------------

class TestRewriteUrlsLine89:
    def test_empty_href_not_matched_by_regex(self):
        """href="" does not match the regex, so rewrite_url is never called."""
        content = b'<a href="">Empty</a>'
        result = rewrite_urls(content, "http://proxy.local/proxy")
        assert b'href=""' in result

    def test_space_only_href_not_matched(self):
        """href=" " matches regex but url is truthy (space)."""
        content = b'<a href=" ">\xc2\xa0</a>'
        result = rewrite_urls(content, "http://proxy.local/proxy")
        assert b"/browse?url=" in result


# ---------------------------------------------------------------------------
# Lines 111-113: rewrite_urls exception handler
# ---------------------------------------------------------------------------

class TestRewriteUrlsException:
    def test_exception_returns_original_content(self):
        """Exception in rewrite_urls returns original content (lines 111-113)."""
        with patch("tokenade.core.proxy.server_utils.re.sub", side_effect=RuntimeError("regex fail")):
            content = b'<a href="http://example.com/page">Link</a>'
            result = rewrite_urls(content, "http://proxy.local/proxy")
            assert result == content

    def test_exception_with_empty_content(self):
        """Exception with empty content returns empty bytes."""
        with patch("tokenade.core.proxy.server_utils.re.sub", side_effect=RuntimeError("fail")):
            result = rewrite_urls(b"", "http://proxy.local/proxy")
            assert result == b""


# ---------------------------------------------------------------------------
# Line 167: rewrite_html_for_proxy import with /proxy/ URL
# ---------------------------------------------------------------------------

class TestRewriteHtmlLine167:
    def test_import_with_proxy_url_skipped(self):
        """import with /proxy/ URL is not rewritten (line 167)."""
        content = b"import '/proxy/module.js'"
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        text = result.decode()
        assert "import '/proxy/module.js'" in text

    def test_from_import_with_proxy_url_skipped(self):
        """from '/proxy/...' is not rewritten (line 167)."""
        content = b"from '/proxy/utils.js'"
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        text = result.decode()
        assert "from '/proxy/utils.js'" in text


# ---------------------------------------------------------------------------
# Lines 172-174: rewrite_html_for_proxy import root-relative and external
# ---------------------------------------------------------------------------

class TestRewriteHtmlLines172_174:
    def test_import_root_relative_rewritten(self):
        """import with root-relative URL gets rewritten (lines 172-173)."""
        content = b"import '/module.js'"
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        assert b"/proxy/module.js" in result

    def test_from_import_root_relative_rewritten(self):
        """from with root-relative URL gets rewritten (lines 172-173)."""
        content = b"from '/utils.js'"
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        assert b"/proxy/utils.js" in result

    def test_import_external_url_not_rewritten(self):
        """import with external URL is not rewritten (line 174)."""
        content = b"import 'https://other.com/module.js'"
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        text = result.decode()
        assert "https://other.com/module.js" in text
        assert "/proxy/" not in text.split("import")[1]

    def test_from_import_external_url_not_rewritten(self):
        """from with external URL is not rewritten (line 174)."""
        content = b"from 'https://other.com/util.js'"
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        text = result.decode()
        assert "https://other.com/util.js" in text


# ---------------------------------------------------------------------------
# Line 185: rewrite_html_for_proxy CSS url() with external URL
# ---------------------------------------------------------------------------

class TestRewriteHtmlLine185:
    def test_css_url_external_not_rewritten(self):
        """CSS url() with external URL is not rewritten (line 185)."""
        content = b'<style>body { background: url("https://other.com/bg.png"); }</style>'
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        text = result.decode()
        assert "https://other.com/bg.png" in text
        assert "url(\"https://other.com/bg.png\")" in text


# ---------------------------------------------------------------------------
# Lines 190-192: rewrite_html_for_proxy exception handler
# ---------------------------------------------------------------------------

class TestRewriteHtmlException:
    def test_exception_returns_original_content(self):
        """Exception in rewrite_html_for_proxy returns original (lines 190-192)."""
        with patch("tokenade.core.proxy.server_utils.urlparse", side_effect=RuntimeError("parse fail")):
            content = b"<html><head></head><body></body></html>"
            result = rewrite_html_for_proxy(content, "https://example.com/page")
            assert result == content

    def test_exception_with_simple_content(self):
        """Exception with simple HTML returns original."""
        with patch("tokenade.core.proxy.server_utils.urlparse", side_effect=RuntimeError("fail")):
            content = b"<p>Hello</p>"
            result = rewrite_html_for_proxy(content, "https://example.com/page")
            assert result == content


# ---------------------------------------------------------------------------
# Lines 227-229: rewrite_js_for_proxy exception handler
# ---------------------------------------------------------------------------

class TestRewriteJsException:
    def test_exception_returns_original_content(self):
        """Exception in rewrite_js_for_proxy returns original (lines 227-229)."""
        with patch("tokenade.core.proxy.server_utils.urlparse", side_effect=RuntimeError("parse fail")):
            content = b'import "https://example.com/module.js"'
            result = rewrite_js_for_proxy(content, "https://example.com/page")
            assert result == content

    def test_exception_with_empty_content(self):
        """Exception with empty content returns empty bytes."""
        with patch("tokenade.core.proxy.server_utils.urlparse", side_effect=RuntimeError("fail")):
            result = rewrite_js_for_proxy(b"", "https://example.com/page")
            assert result == b""


# ---------------------------------------------------------------------------
# Lines 251-253: rewrite_css_for_proxy exception handler
# ---------------------------------------------------------------------------

class TestRewriteCssException:
    def test_exception_returns_original_content(self):
        """Exception in rewrite_css_for_proxy returns original (lines 251-253)."""
        with patch("tokenade.core.proxy.server_utils.urlparse", side_effect=RuntimeError("parse fail")):
            content = b'body { background: url("https://example.com/bg.png"); }'
            result = rewrite_css_for_proxy(content, "https://example.com/page")
            assert result == content

    def test_exception_with_empty_content(self):
        """Exception with empty content returns empty bytes."""
        with patch("tokenade.core.proxy.server_utils.urlparse", side_effect=RuntimeError("fail")):
            result = rewrite_css_for_proxy(b"", "https://example.com/page")
            assert result == b""
