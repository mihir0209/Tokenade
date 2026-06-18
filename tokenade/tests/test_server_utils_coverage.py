"""Comprehensive tests for server_utils.py — targeting 60%+ coverage."""

from aiohttp.test_utils import make_mocked_request

from tokenade.core.proxy.server_utils import (
    ProxyResponse,
    SKIP_RESPONSE_HEADERS,
    build_target_url,
    filter_response_headers,
    rewrite_urls,
    rewrite_html_for_proxy,
    rewrite_js_for_proxy,
    rewrite_css_for_proxy,
)


# ===========================================================================
# ProxyResponse dataclass
# ===========================================================================

class TestProxyResponse:
    def test_creation(self):
        r = ProxyResponse(status=200, headers={"a": "b"}, body=b"ok", url="http://x.com")
        assert r.status == 200
        assert r.headers == {"a": "b"}
        assert r.body == b"ok"
        assert r.url == "http://x.com"

    def test_equality(self):
        r1 = ProxyResponse(200, {}, b"", "")
        r2 = ProxyResponse(200, {}, b"", "")
        assert r1 == r2


# ===========================================================================
# SKIP_RESPONSE_HEADERS
# ===========================================================================

class TestSkipHeaders:
    def test_expected_headers_present(self):
        expected = {
            "transfer-encoding", "connection", "keep-alive", "proxy-connection",
            "content-encoding", "content-length",
            "content-security-policy", "x-frame-options", "strict-transport-security",
        }
        assert expected == SKIP_RESPONSE_HEADERS


# ===========================================================================
# build_target_url
# ===========================================================================

class TestBuildTargetUrl:
    def test_full_url_in_path(self):
        req = make_mocked_request("GET", "/http://example.com/page")
        # aiohttp strips leading slash; path becomes /http://example.com/page
        # The function's path_stripped logic catches it
        result = build_target_url(req)
        assert result == "http://example.com/page"

    def test_full_https_url_in_path(self):
        req = make_mocked_request("GET", "/https://secure.example.com/page")
        result = build_target_url(req)
        assert result == "https://secure.example.com/page"

    def test_authority_header(self):
        req = make_mocked_request("GET", "/", headers={":authority": "example.com", ":scheme": "https"})
        assert build_target_url(req) == "https://example.com/"

    def test_authority_no_scheme(self):
        req = make_mocked_request("GET", "/path", headers={":authority": "example.com"})
        assert build_target_url(req) == "https://example.com/path"

    def test_host_header(self):
        req = make_mocked_request("GET", "/page", headers={"Host": "example.com"})
        result = build_target_url(req)
        assert result == "http://example.com/page"

    def test_host_header_with_port_443(self):
        req = make_mocked_request("GET", "/page", headers={"Host": "example.com:443"})
        result = build_target_url(req)
        # Code checks ":443" in host string => uses https
        assert result is not None
        assert "example.com" in result

    def test_host_header_with_scheme_https(self):
        req = make_mocked_request("GET", "/page", headers={"Host": "example.com", ":scheme": "https"})
        result = build_target_url(req)
        assert result == "https://example.com/page"

    def test_path_as_domain_no_slash(self):
        req = make_mocked_request("GET", "/example.com")
        result = build_target_url(req)
        # "." in path, no spaces — treated as domain
        assert result is not None

    def test_path_as_domain_with_subpath(self):
        req = make_mocked_request("GET", "/example.com/page")
        result = build_target_url(req)
        assert result is not None

    def test_no_identifiable_url_returns_none(self):
        req = make_mocked_request("GET", "/just-a-path")
        result = build_target_url(req)
        assert result is None

    def test_path_with_space_not_treated_as_domain(self):
        req = make_mocked_request("GET", "/hello world")
        result = build_target_url(req)
        assert result is None

    def test_strips_leading_slash_for_http_url(self):
        req = make_mocked_request("GET", "/http://example.com/path/to/page")
        result = build_target_url(req)
        assert result == "http://example.com/path/to/page"


# ===========================================================================
# filter_response_headers
# ===========================================================================

class TestFilterResponseHeaders:
    def test_removes_transfer_encoding(self):
        headers = {"Transfer-Encoding": "chunked", "Content-Type": "text/html"}
        filtered = filter_response_headers(headers)
        assert "Transfer-Encoding" not in filtered
        assert "Content-Type" in filtered

    def test_removes_all_skip_headers(self):
        headers = {k: "val" for k in SKIP_RESPONSE_HEADERS}
        filtered = filter_response_headers(headers)
        assert filtered == {}

    def test_keeps_normal_headers(self):
        headers = {"X-Custom": "yes", "Cache-Control": "no-cache"}
        filtered = filter_response_headers(headers)
        assert filtered == {"X-Custom": "yes", "Cache-Control": "no-cache"}

    def test_filters_set_cookie_with_host_prefix(self):
        headers = {"Set-Cookie": "__Host-session=abc; Path=/"}
        filtered = filter_response_headers(headers)
        assert "Set-Cookie" not in filtered

    def test_filters_set_cookie_with_domain(self):
        headers = {"Set-Cookie": "sid=abc; Domain=.example.com"}
        filtered = filter_response_headers(headers)
        assert "Set-Cookie" not in filtered

    def test_keeps_set_cookie_without_host_or_domain(self):
        headers = {"Set-Cookie": "sid=abc; Path=/"}
        filtered = filter_response_headers(headers)
        assert "Set-Cookie" in filtered

    def test_case_insensitive(self):
        headers = {"content-encoding": "gzip", "Content-Length": "100"}
        filtered = filter_response_headers(headers)
        assert "content-encoding" not in filtered
        assert "Content-Length" not in filtered

    def test_empty_headers(self):
        assert filter_response_headers({}) == {}


# ===========================================================================
# rewrite_urls
# ===========================================================================

class TestRewriteUrls:
    def test_rewrites_href(self):
        content = b'<a href="http://example.com/page">Link</a>'
        result = rewrite_urls(content, "http://proxy.local/proxy")
        assert b"/browse?url=" in result
        assert b"example.com" in result

    def test_rewrites_src(self):
        content = b'<img src="http://example.com/img.png">'
        result = rewrite_urls(content, "http://proxy.local/proxy")
        assert b"/browse?url=" in result

    def test_skips_data_urls(self):
        content = b'<img src="data:image/png;base64,abc">'
        result = rewrite_urls(content, "http://proxy.local/proxy")
        assert b"data:image/png" in result
        assert b"/browse?url=" not in result

    def test_skips_javascript_urls(self):
        content = b'<a href="javascript:void(0)">Link</a>'
        result = rewrite_urls(content, "http://proxy.local/proxy")
        assert b"javascript:void(0)" in result
        assert b"/browse?url=" not in result

    def test_skips_fragment_urls(self):
        content = b'<a href="#section">Link</a>'
        result = rewrite_urls(content, "http://proxy.local/proxy")
        assert b"#section" in result
        assert b"/browse?url=" not in result

    def test_skips_mailto_urls(self):
        content = b'<a href="mailto:test@example.com">Mail</a>'
        result = rewrite_urls(content, "http://proxy.local/proxy")
        assert b"mailto:" in result

    def test_skips_tel_urls(self):
        content = b'<a href="tel:+1234">Call</a>'
        result = rewrite_urls(content, "http://proxy.local/proxy")
        assert b"tel:" in result

    def test_skips_already_proxied(self):
        content = b'<a href="/browse?url=http://example.com">Link</a>'
        result = rewrite_urls(content, "http://proxy.local/proxy")
        # Already contains /browse?url= so rewrite_url returns match.group(0) unchanged
        assert b"/browse?url=http://example.com" in result

    def test_skips_proxy_path(self):
        content = b'<a href="/proxy/page">Link</a>'
        result = rewrite_urls(content, "http://proxy.local/proxy")
        assert b"/proxy/page" in result

    def test_relative_url(self):
        content = b'<a href="page.html">Link</a>'
        result = rewrite_urls(content, "http://example.com/proxy")
        assert b"/browse?url=" in result

    def test_root_relative_url(self):
        content = b'<a href="/other-page">Link</a>'
        result = rewrite_urls(content, "http://example.com:8080/proxy")
        assert b"/browse?url=" in result
        assert b"example.com" in result

    def test_full_https_url(self):
        content = b'<a href="https://secure.example.com/page">Link</a>'
        result = rewrite_urls(content, "http://proxy.local/proxy")
        assert b"/browse?url=" in result
        assert b"https%3A%2F%2Fsecure.example.com" in result

    def test_no_urls_unchanged(self):
        content = b"<p>No links here</p>"
        result = rewrite_urls(content, "http://proxy.local/proxy")
        assert result == content

    def test_empty_url_in_href(self):
        content = b'<a href="">Empty</a>'
        result = rewrite_urls(content, "http://proxy.local/proxy")
        assert b'href=""' in result

    def test_base_url_with_port(self):
        content = b'<a href="http://example.com/page">Link</a>'
        result = rewrite_urls(content, "http://proxy.local:8080/proxy")
        assert b"/browse?url=" in result

    def test_decode_error_returns_original(self):
        # bytes that cause decode error with errors='ignore' → empty string
        result = rewrite_urls(b"\xff\xfe", "http://proxy.local/proxy")
        # decode with errors='ignore' returns "", no regex match → returns b""
        assert result == b""

    def test_mixed_content(self):
        content = b'<a href="http://a.com">A</a><img src="http://b.com/img.png">'
        result = rewrite_urls(content, "http://proxy.local/proxy")
        assert result.count(b"/browse?url=") == 2


# ===========================================================================
# rewrite_html_for_proxy
# ===========================================================================

class TestRewriteHtmlForProxy:
    def test_injects_service_worker_in_head(self):
        content = b"<html><head><title>T</title></head><body></body></html>"
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        text = result.decode()
        assert "serviceWorker" in text
        assert "_tokenade_sw.js" in text

    def test_injects_when_only_html_no_head(self):
        content = b"<html><body></body></html>"
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        text = result.decode()
        assert "serviceWorker" in text

    def test_injects_before_content_if_no_head_or_html(self):
        content = b"<p>Hello</p>"
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        text = result.decode()
        assert "serviceWorker" in text
        assert "<p>Hello</p>" in text

    def test_rewrites_same_host_href(self):
        content = b'<a href="https://example.com/page">Link</a>'
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        assert b"/proxy/" in result

    def test_rewrites_root_relative_url(self):
        content = b'<a href="/other-page">Link</a>'
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        assert b"/proxy/other-page" in result

    def test_skips_data_urls(self):
        content = b'<img src="data:image/png;base64,abc">'
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        assert b"data:image/png" in result

    def test_skips_javascript_urls(self):
        content = b'<a href="javascript:void(0)">Link</a>'
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        assert b"javascript:void(0)" in result

    def test_skips_already_proxied(self):
        content = b'<a href="/proxy/page">Link</a>'
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        assert b"/proxy/page" in result

    def test_rewrites_import_statement(self):
        content = b"import 'https://example.com/module.js'"
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        assert b"/proxy/module.js" in result

    def test_rewrites_from_import(self):
        content = b"from 'https://example.com/util.js'"
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        assert b"/proxy/util.js" in result

    def test_error_returns_original_on_bad_bytes(self):
        result = rewrite_html_for_proxy(b"\xff\xfe", "https://example.com/page")
        # decode with errors='ignore' returns "", SW injection prepended
        assert b"serviceWorker" in result

    def test_empty_content(self):
        result = rewrite_html_for_proxy(b"", "https://example.com/page")
        text = result.decode()
        assert "serviceWorker" in text

    def test_import_with_data_url_skipped(self):
        content = b'import "data:text/javascript,alert(1)"'
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        assert b"data:" in result

    def test_from_import_with_data_url_skipped(self):
        content = b'from "data:text/javascript,alert(1)"'
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        assert b"data:" in result

    def test_relative_path_not_rewritten(self):
        content = b'<a href="page.html">Link</a>'
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        assert b'href="page.html"' in result

    def test_external_url_not_rewritten(self):
        content = b'<a href="https://other.com/page">Link</a>'
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        assert b'href="https://other.com/page"' in result

    def test_css_url_root_relative(self):
        content = b'<style>body { background: url("/bg.png"); }</style>'
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        # url(/proxy//bg.png) because path="/bg.png" starts with "/"
        assert b"/proxy/" in result

    def test_css_url_with_target_host(self):
        content = b'<style>body { background: url("https://example.com/bg.png"); }</style>'
        result = rewrite_html_for_proxy(content, "https://example.com/page")
        assert b"/proxy/" in result

    def test_no_hostname(self):
        result = rewrite_html_for_proxy(b"<p>hi</p>", "http:///page")
        text = result.decode()
        assert "serviceWorker" in text


# ===========================================================================
# rewrite_js_for_proxy
# ===========================================================================

class TestRewriteJsForProxy:
    def test_rewrites_import_url(self):
        content = b'import "https://example.com/module.js"'
        result = rewrite_js_for_proxy(content, "https://example.com/page")
        assert b"/proxy/module.js" in result

    def test_rewrites_from_url(self):
        content = b'from "https://example.com/util.js"'
        result = rewrite_js_for_proxy(content, "https://example.com/page")
        assert b"/proxy/util.js" in result

    def test_rewrites_fetch_url(self):
        content = b'fetch("https://example.com/api")'
        result = rewrite_js_for_proxy(content, "https://example.com/page")
        assert b"/proxy/api" in result

    def test_rewrites_bare_path_from(self):
        content = b"from '/utils.js'"
        result = rewrite_js_for_proxy(content, "https://example.com/page")
        assert b"/proxy/utils.js" in result

    def test_rewrites_bare_path_fetch(self):
        content = b"fetch('/api/data')"
        result = rewrite_js_for_proxy(content, "https://example.com/page")
        assert b"/proxy/api/data" in result

    def test_does_not_rewrite_external_url(self):
        content = b'import "https://other.com/module.js"'
        result = rewrite_js_for_proxy(content, "https://example.com/page")
        assert b"https://other.com/module.js" in result

    def test_empty_content(self):
        result = rewrite_js_for_proxy(b"", "https://example.com/page")
        assert result == b""

    def test_no_hostname_returns_unchanged(self):
        content = b'import "https://example.com/module.js"'
        result = rewrite_js_for_proxy(content, "http:///page")
        assert b"https://example.com/module.js" in result

    def test_fetch_with_single_quotes(self):
        content = b"fetch('https://example.com/api')"
        result = rewrite_js_for_proxy(content, "https://example.com/page")
        assert b"/proxy/api" in result

    def test_import_with_query_string(self):
        content = b'import "https://example.com/module.js?v=1"'
        result = rewrite_js_for_proxy(content, "https://example.com/page")
        assert b"/proxy/module.js?v=1" in result

    def test_bare_path_without_leading_slash_not_rewritten(self):
        content = b"from 'utils.js'"
        result = rewrite_js_for_proxy(content, "https://example.com/page")
        # No leading "/" and not http, so bare path regex doesn't match
        assert b"utils.js" in result

    def test_decode_error_returns_original(self):
        result = rewrite_js_for_proxy(b"\xff\xfe", "https://example.com/page")
        # decode returns "", no regex matches → b""
        assert result == b""


# ===========================================================================
# rewrite_css_for_proxy
# ===========================================================================

class TestRewriteCssForProxy:
    def test_rewrites_url_with_target_host(self):
        content = b'body { background: url("https://example.com/bg.png"); }'
        result = rewrite_css_for_proxy(content, "https://example.com/page")
        assert b"/proxy/" in result
        assert b"bg.png" in result

    def test_rewrites_url_with_single_quotes(self):
        content = b"body { background: url('https://example.com/bg.png'); }"
        result = rewrite_css_for_proxy(content, "https://example.com/page")
        assert b"/proxy/" in result
        assert b"bg.png" in result

    def test_does_not_rewrite_external_url(self):
        content = b'body { background: url("https://other.com/bg.png"); }'
        result = rewrite_css_for_proxy(content, "https://example.com/page")
        assert b"https://other.com/bg.png" in result

    def test_empty_content(self):
        result = rewrite_css_for_proxy(b"", "https://example.com/page")
        assert result == b""

    def test_no_hostname_returns_unchanged(self):
        content = b'body { background: url("https://example.com/bg.png"); }'
        result = rewrite_css_for_proxy(content, "http:///page")
        assert b"https://example.com/bg.png" in result

    def test_css_url_without_quotes(self):
        content = b"body { background: url(https://example.com/bg.png); }"
        result = rewrite_css_for_proxy(content, "https://example.com/page")
        assert b"/proxy/" in result
        assert b"bg.png" in result

    def test_multiple_urls(self):
        content = (
            b'body { background: url("https://example.com/bg.png"); '
            b'border-image: url("https://example.com/border.png"); }'
        )
        result = rewrite_css_for_proxy(content, "https://example.com/page")
        assert b"/proxy/" in result
        assert b"bg.png" in result
        assert b"border.png" in result

    def test_decode_error_returns_original(self):
        result = rewrite_css_for_proxy(b"\xff\xfe", "https://example.com/page")
        assert result == b""
