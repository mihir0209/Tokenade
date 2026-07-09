"""Advanced validator edge/API paths (unique branches).

Dataclass smoke tests duplicated in test_advanced_validator.py were removed.
Formerly test_advanced_validator_coverage.
"""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from tokenade.core.importer.advanced_validator import (
    ValidationResult, ValidationRule, AdvancedValidator,
    load_validation_rules, create_example_rules,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rule(rule_type="js", name="test_rule", config=None, timeout=5):
    return ValidationRule(name=name, type=rule_type, config=config or {}, timeout=timeout)


def _session(cookies=None):
    return {"cookies": cookies or [], "site_name": "example"}


# ---------------------------------------------------------------------------
# Playwright mock factories
# ---------------------------------------------------------------------------

class _FakePage:
    def __init__(self, evaluate_result=None, screenshot_bytes=b"\x89PNG", text_content="hello"):
        self._evaluate_result = evaluate_result
        self._screenshot_bytes = screenshot_bytes
        self._text_content = text_content
        self.goto_url = None
        self.goto_opts = {}
        self._element = MagicMock()
        self._element.text_content = AsyncMock(return_value=text_content)

    async def goto(self, url, **kwargs):
        self.goto_url = url
        self.goto_opts = kwargs

    async def evaluate(self, code):
        return self._evaluate_result

    async def screenshot(self, **kwargs):
        return self._screenshot_bytes

    async def query_selector(self, selector):
        return self._element


class _FakeBrowserType:
    def __init__(self, browser=None):
        self._browser = browser

    async def launch(self, **kwargs):
        return self._browser


class _FakeContext:
    def __init__(self, page=None):
        self._page = page or _FakePage()
        self._cookies_added = []

    async def add_cookies(self, cookies):
        self._cookies_added = cookies

    async def new_page(self):
        return self._page


class _FakeBrowser:
    def __init__(self, context=None):
        self._context = context or _FakeContext()
        self._closed = False

    async def new_context(self, **kwargs):
        return self._context

    async def close(self):
        self._closed = True


class AsyncContextManager:
    def __init__(self, obj):
        self._obj = obj

    async def __aenter__(self):
        return self._obj

    async def __aexit__(self, *args):
        pass


class _FakePlaywright:
    def __init__(self, browser=None):
        self._browser = browser or _FakeBrowser()
        self.chromium = _FakeBrowserType(self._browser)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _make_pw_mock(page=None):
    ctx = _FakeContext(page)
    brk = _FakeBrowser(ctx)
    pw = _FakePlaywright(brk)

    def factory():
        return pw

    return factory, pw, brk, ctx


def _mock_async_playwright(factory_or_exception):
    if isinstance(factory_or_exception, Exception):
        return patch("playwright.async_api.async_playwright", side_effect=factory_or_exception)
    return patch("playwright.async_api.async_playwright", factory_or_exception)


# ---------------------------------------------------------------------------
# Tests: _validate_js
# ---------------------------------------------------------------------------

class TestValidateJs:
    @pytest.mark.asyncio
    async def test_js_passes(self):
        page = _FakePage(evaluate_result=True)
        factory, pw, brk, ctx = _make_pw_mock(page=page)

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            rule = _make_rule("js", config={"script": "return true"})
            result = await v.validate_rules(_session(), [rule], "https://example.com")

        assert len(result) == 1
        assert result[0].passed is True
        assert result[0].duration_ms is not None

    @pytest.mark.asyncio
    async def test_js_fails(self):
        page = _FakePage(evaluate_result=False)
        factory, pw, brk, ctx = _make_pw_mock(page=page)

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            rule = _make_rule("js", config={"script": "return false"})
            result = await v.validate_rules(_session(), [rule], "https://example.com")

        assert result[0].passed is False
        assert "failed" in result[0].message.lower()

    @pytest.mark.asyncio
    async def test_js_uses_site_url_from_session(self):
        page = _FakePage(evaluate_result=True)
        factory, pw, brk, ctx = _make_pw_mock(page=page)

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            rule = _make_rule("js")
            sess = _session(cookies=[{"domain": ".mysite.com", "name": "s", "value": "1"}])
            await v.validate_rules(sess, [rule])

        assert "mysite.com" in page.goto_url

    @pytest.mark.asyncio
    async def test_js_with_cookies(self):
        page = _FakePage(evaluate_result=True)
        factory, pw, brk, ctx = _make_pw_mock(page=page)
        cookies = [{"name": "sid", "value": "abc", "domain": ".example.com", "path": "/"}]

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            rule = _make_rule("js", config={"script": "return true"})
            await v.validate_rules(_session(cookies=cookies), [rule], "https://example.com")

        assert len(ctx._cookies_added) == 1
        assert ctx._cookies_added[0]["name"] == "sid"

    @pytest.mark.asyncio
    async def test_js_playwright_error(self):
        with _mock_async_playwright(RuntimeError("pw crash")):
            v = AdvancedValidator()
            rule = _make_rule("js")
            result = await v.validate_rules(_session(), [rule], "https://example.com")

        assert result[0].passed is False
        assert "error" in result[0].message.lower()

    @pytest.mark.asyncio
    async def test_js_default_script(self):
        page = _FakePage(evaluate_result=True)
        factory, pw, brk, ctx = _make_pw_mock(page=page)

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            rule = _make_rule("js", config={})
            result = await v.validate_rules(_session(), [rule], "https://example.com")

        assert result[0].passed is True


# ---------------------------------------------------------------------------
# Tests: _validate_screenshot
# ---------------------------------------------------------------------------

class TestValidateScreenshot:
    @pytest.mark.asyncio
    async def test_screenshot_new_baseline(self, tmp_path):
        page = _FakePage(screenshot_bytes=b"imgdata123")
        factory, pw, brk, ctx = _make_pw_mock(page=page)

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            v._baseline_dir = tmp_path
            rule = _make_rule("screenshot", config={"baseline": "test_bl"})
            result = await v.validate_rules(_session(), [rule], "https://example.com")

        assert result[0].passed is True
        assert "baseline" in result[0].message.lower()

    @pytest.mark.asyncio
    async def test_screenshot_differs_from_baseline(self, tmp_path):
        bl = tmp_path / "diff.png"
        bl.write_bytes(b"old_img")
        page = _FakePage(screenshot_bytes=b"new_img")
        factory, pw, brk, ctx = _make_pw_mock(page=page)

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            v._baseline_dir = tmp_path
            rule = _make_rule("screenshot", config={"baseline": "diff"})
            result = await v.validate_rules(_session(), [rule], "https://example.com")

        assert result[0].passed is False
        assert "differs" in result[0].message.lower()

    @pytest.mark.asyncio
    async def test_screenshot_update_baseline(self, tmp_path):
        bl = tmp_path / "upd.png"
        bl.write_bytes(b"old")
        page = _FakePage(screenshot_bytes=b"new")
        factory, pw, brk, ctx = _make_pw_mock(page=page)

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            v._baseline_dir = tmp_path
            rule = _make_rule("screenshot", config={"baseline": "upd", "update_baseline": True})
            result = await v.validate_rules(_session(), [rule], "https://example.com")

        assert result[0].passed is True
        assert bl.read_bytes() == b"new"

    @pytest.mark.asyncio
    async def test_screenshot_playwright_error(self):
        with _mock_async_playwright(RuntimeError("pw crash")):
            v = AdvancedValidator()
            rule = _make_rule("screenshot")
            result = await v.validate_rules(_session(), [rule], "https://example.com")

        assert result[0].passed is False
        assert "error" in result[0].message.lower()

    @pytest.mark.asyncio
    async def test_screenshot_with_cookies(self, tmp_path):
        page = _FakePage(screenshot_bytes=b"imgdata")
        factory, pw, brk, ctx = _make_pw_mock(page=page)
        cookies = [{"name": "sid", "value": "1", "domain": ".example.com", "path": "/"}]

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            v._baseline_dir = tmp_path
            rule = _make_rule("screenshot", config={"baseline": "cookies_bl"})
            result = await v.validate_rules(_session(cookies=cookies), [rule], "https://example.com")

        assert result[0].passed is True
        assert len(ctx._cookies_added) == 1

    @pytest.mark.asyncio
    async def test_screenshot_update_existing_baseline(self, tmp_path):
        bl = tmp_path / "existing.png"
        bl.write_bytes(b"old_data")
        page = _FakePage(screenshot_bytes=b"new_data")
        factory, pw, brk, ctx = _make_pw_mock(page=page)

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            v._baseline_dir = tmp_path
            rule = _make_rule("screenshot", config={"baseline": "existing", "update_baseline": True})
            result = await v.validate_rules(_session(), [rule], "https://example.com")

        assert result[0].passed is True
        assert bl.read_bytes() == b"new_data"

    @pytest.mark.asyncio
    async def test_screenshot_uses_site_url_from_session(self, tmp_path):
        page = _FakePage(screenshot_bytes=b"img")
        factory, pw, brk, ctx = _make_pw_mock(page=page)
        cookies = [{"domain": ".mysite.com", "name": "s", "value": "1"}]

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            v._baseline_dir = tmp_path
            rule = _make_rule("screenshot", config={"baseline": "sess_bl"})
            await v.validate_rules(_session(cookies=cookies), [rule])

        assert "mysite.com" in page.goto_url


# ---------------------------------------------------------------------------
# Tests: _validate_api
# ---------------------------------------------------------------------------

class _FakeAioResponse:
    def __init__(self, status=200, text="ok", headers=None):
        self.status = status
        self._text = text
        self.headers = headers or {}

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _FakeAioSession:
    def __init__(self, resp=None):
        self._resp = resp or _FakeAioResponse()

    def get(self, url, **kwargs):
        return AsyncContextManager(self._resp)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _make_aio_mock(resp=None):
    sess = _FakeAioSession(resp)

    def factory():
        return AsyncContextManager(sess)

    return factory


def _mock_aiohttp_session(factory):
    return patch("aiohttp.ClientSession", factory)


class TestValidateApi:
    @pytest.mark.asyncio
    async def test_api_passes(self):
        resp = _FakeAioResponse(200, "all good")
        factory = _make_aio_mock(resp)

        with _mock_aiohttp_session(factory):
            v = AdvancedValidator()
            rule = _make_rule("api", config={"url": "https://api.example.com/health"})
            result = await v.validate_rules(_session(), [rule])

        assert result[0].passed is True

    @pytest.mark.asyncio
    async def test_api_wrong_status(self):
        resp = _FakeAioResponse(500, "error")
        factory = _make_aio_mock(resp)

        with _mock_aiohttp_session(factory):
            v = AdvancedValidator()
            rule = _make_rule("api", config={"url": "https://api.example.com/health", "status": 200})
            result = await v.validate_rules(_session(), [rule])

        assert result[0].passed is False
        assert "500" in result[0].message

    @pytest.mark.asyncio
    async def test_api_body_string_match(self):
        resp = _FakeAioResponse(200, '{"status":"ok"}')
        factory = _make_aio_mock(resp)

        with _mock_aiohttp_session(factory):
            v = AdvancedValidator()
            rule = _make_rule("api", config={"url": "https://api.example.com", "body": "ok"})
            result = await v.validate_rules(_session(), [rule])

        assert result[0].passed is True

    @pytest.mark.asyncio
    async def test_api_body_string_missing(self):
        resp = _FakeAioResponse(200, "nothing here")
        factory = _make_aio_mock(resp)

        with _mock_aiohttp_session(factory):
            v = AdvancedValidator()
            rule = _make_rule("api", config={"url": "https://api.example.com", "body": "expected"})
            result = await v.validate_rules(_session(), [rule])

        assert result[0].passed is False

    @pytest.mark.asyncio
    async def test_api_body_dict_match(self):
        resp = _FakeAioResponse(200, '{"key":"val","num":42}')
        factory = _make_aio_mock(resp)

        with _mock_aiohttp_session(factory):
            v = AdvancedValidator()
            rule = _make_rule("api", config={"url": "https://api.example.com", "body": {"key": "val", "num": 42}})
            result = await v.validate_rules(_session(), [rule])

        assert result[0].passed is True

    @pytest.mark.asyncio
    async def test_api_body_dict_mismatch(self):
        resp = _FakeAioResponse(200, '{"key":"other"}')
        factory = _make_aio_mock(resp)

        with _mock_aiohttp_session(factory):
            v = AdvancedValidator()
            rule = _make_rule("api", config={"url": "https://api.example.com", "body": {"key": "val"}})
            result = await v.validate_rules(_session(), [rule])

        assert result[0].passed is False
        assert "mismatch" in result[0].message.lower()

    @pytest.mark.asyncio
    async def test_api_body_dict_invalid_json(self):
        resp = _FakeAioResponse(200, "not json at all")
        factory = _make_aio_mock(resp)

        with _mock_aiohttp_session(factory):
            v = AdvancedValidator()
            rule = _make_rule("api", config={"url": "https://api.example.com", "body": {"key": "val"}})
            result = await v.validate_rules(_session(), [rule])

        assert result[0].passed is False
        assert "json" in result[0].message.lower()

    @pytest.mark.asyncio
    async def test_api_no_url(self):
        v = AdvancedValidator()
        rule = _make_rule("api", config={})
        result = await v.validate_rules(_session(), [rule])
        assert result[0].passed is False

    @pytest.mark.asyncio
    async def test_api_with_cookies(self):
        resp = _FakeAioResponse(200, "ok")
        factory = _make_aio_mock(resp)

        with _mock_aiohttp_session(factory):
            v = AdvancedValidator()
            cookies = [{"name": "sid", "value": "abc", "domain": ".example.com"}]
            rule = _make_rule("api", config={"url": "https://api.example.com"})
            result = await v.validate_rules(_session(cookies=cookies), [rule])

        assert result[0].passed is True

    @pytest.mark.asyncio
    async def test_api_exception(self):
        with patch("aiohttp.ClientSession", side_effect=RuntimeError("net err")):
            v = AdvancedValidator()
            rule = _make_rule("api", config={"url": "https://api.example.com"})
            result = await v.validate_rules(_session(), [rule])

        assert result[0].passed is False
        assert "error" in result[0].message.lower()

    @pytest.mark.asyncio
    async def test_api_with_headers(self):
        resp = _FakeAioResponse(200, "ok")
        factory = _make_aio_mock(resp)

        with _mock_aiohttp_session(factory):
            v = AdvancedValidator()
            rule = _make_rule("api", config={"url": "https://api.example.com", "headers": {"X-Custom": "val"}})
            result = await v.validate_rules(_session(), [rule])

        assert result[0].passed is True


# ---------------------------------------------------------------------------
# Tests: _validate_url
# ---------------------------------------------------------------------------

class TestValidateUrl:
    @pytest.mark.asyncio
    async def test_url_no_redirect_expected_none(self):
        resp = _FakeAioResponse(200)
        factory = _make_aio_mock(resp)

        with _mock_aiohttp_session(factory):
            v = AdvancedValidator()
            rule = _make_rule("url", config={"url": "https://example.com", "redirect": False})
            result = await v.validate_rules(_session(), [rule])

        assert result[0].passed is True

    @pytest.mark.asyncio
    async def test_url_redirect_expected_but_none(self):
        resp = _FakeAioResponse(200)
        factory = _make_aio_mock(resp)

        with _mock_aiohttp_session(factory):
            v = AdvancedValidator()
            rule = _make_rule("url", config={"url": "https://example.com", "redirect": True})
            result = await v.validate_rules(_session(), [rule])

        assert result[0].passed is False
        assert "redirect" in result[0].message.lower()

    @pytest.mark.asyncio
    async def test_url_redirect_correct(self):
        resp = _FakeAioResponse(302, headers={"location": "https://new.example.com"})
        factory = _make_aio_mock(resp)

        with _mock_aiohttp_session(factory):
            v = AdvancedValidator()
            rule = _make_rule("url", config={
                "url": "https://old.example.com",
                "redirect": True,
                "redirect_to": "new.example.com",
            })
            result = await v.validate_rules(_session(), [rule])

        assert result[0].passed is True
        assert "new.example.com" in result[0].message

    @pytest.mark.asyncio
    async def test_url_redirect_wrong_target(self):
        resp = _FakeAioResponse(301, headers={"location": "https://wrong.example.com"})
        factory = _make_aio_mock(resp)

        with _mock_aiohttp_session(factory):
            v = AdvancedValidator()
            rule = _make_rule("url", config={
                "url": "https://old.example.com",
                "redirect": True,
                "redirect_to": "correct.example.com",
            })
            result = await v.validate_rules(_session(), [rule])

        assert result[0].passed is False
        assert "wrong" in result[0].message.lower() or "redirect" in result[0].message.lower()

    @pytest.mark.asyncio
    async def test_url_unexpected_redirect(self):
        resp = _FakeAioResponse(307, headers={"location": "https://other.example.com"})
        factory = _make_aio_mock(resp)

        with _mock_aiohttp_session(factory):
            v = AdvancedValidator()
            rule = _make_rule("url", config={"url": "https://example.com", "redirect": False})
            result = await v.validate_rules(_session(), [rule])

        assert result[0].passed is False
        assert "unexpected" in result[0].message.lower()

    @pytest.mark.asyncio
    async def test_url_no_url(self):
        v = AdvancedValidator()
        rule = _make_rule("url", config={})
        result = await v.validate_rules(_session(), [rule])
        assert result[0].passed is False

    @pytest.mark.asyncio
    async def test_url_uses_site_url(self):
        resp = _FakeAioResponse(200)
        factory = _make_aio_mock(resp)

        with _mock_aiohttp_session(factory):
            v = AdvancedValidator()
            rule = _make_rule("url", config={"redirect": False})
            result = await v.validate_rules(_session(), [rule], "https://site.example.com")

        assert result[0].passed is True

    @pytest.mark.asyncio
    async def test_url_exception(self):
        with patch("aiohttp.ClientSession", side_effect=RuntimeError("net err")):
            v = AdvancedValidator()
            rule = _make_rule("url", config={"url": "https://example.com"})
            result = await v.validate_rules(_session(), [rule])

        assert result[0].passed is False
        assert "error" in result[0].message.lower()

    @pytest.mark.asyncio
    async def test_url_redirect_301(self):
        resp = _FakeAioResponse(301, headers={"location": "https://dest.example.com"})
        factory = _make_aio_mock(resp)

        with _mock_aiohttp_session(factory):
            v = AdvancedValidator()
            rule = _make_rule("url", config={"url": "https://src.example.com", "redirect": True})
            result = await v.validate_rules(_session(), [rule])

        assert result[0].passed is True

    @pytest.mark.asyncio
    async def test_url_redirect_303(self):
        resp = _FakeAioResponse(303, headers={"location": "https://dest.example.com"})
        factory = _make_aio_mock(resp)

        with _mock_aiohttp_session(factory):
            v = AdvancedValidator()
            rule = _make_rule("url", config={"url": "https://src.example.com", "redirect": True})
            result = await v.validate_rules(_session(), [rule])

        assert result[0].passed is True

    @pytest.mark.asyncio
    async def test_url_redirect_308(self):
        resp = _FakeAioResponse(308, headers={"location": "https://dest.example.com"})
        factory = _make_aio_mock(resp)

        with _mock_aiohttp_session(factory):
            v = AdvancedValidator()
            rule = _make_rule("url", config={"url": "https://src.example.com", "redirect": True})
            result = await v.validate_rules(_session(), [rule])

        assert result[0].passed is True


# ---------------------------------------------------------------------------
# Tests: _validate_element
# ---------------------------------------------------------------------------

class TestValidateElement:
    @pytest.mark.asyncio
    async def test_element_found(self):
        page = _FakePage()
        page._element = MagicMock()
        page._element.text_content = AsyncMock(return_value="Welcome")
        factory, pw, brk, ctx = _make_pw_mock(page=page)

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            rule = _make_rule("element", config={"selector": "#login"})
            result = await v.validate_rules(_session(), [rule], "https://example.com")

        assert result[0].passed is True

    @pytest.mark.asyncio
    async def test_element_not_found(self):
        page = _FakePage()
        page.query_selector = AsyncMock(return_value=None)
        factory, pw, brk, ctx = _make_pw_mock(page=page)

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            rule = _make_rule("element", config={"selector": "#missing"})
            result = await v.validate_rules(_session(), [rule], "https://example.com")

        assert result[0].passed is False
        assert "not found" in result[0].message.lower()

    @pytest.mark.asyncio
    async def test_element_should_not_exist_found(self):
        page = _FakePage()
        element_mock = MagicMock()
        page.query_selector = AsyncMock(return_value=element_mock)
        factory, pw, brk, ctx = _make_pw_mock(page=page)

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            rule = _make_rule("element", config={"selector": "#popup", "exists": False})
            result = await v.validate_rules(_session(), [rule], "https://example.com")

        assert result[0].passed is False
        assert "should not exist" in result[0].message.lower()

    @pytest.mark.asyncio
    async def test_element_should_not_exist_absent(self):
        page = _FakePage()
        page.query_selector = AsyncMock(return_value=None)
        factory, pw, brk, ctx = _make_pw_mock(page=page)

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            rule = _make_rule("element", config={"selector": "#popup", "exists": False})
            result = await v.validate_rules(_session(), [rule], "https://example.com")

        assert result[0].passed is True
        assert "absent" in result[0].message.lower()

    @pytest.mark.asyncio
    async def test_element_text_mismatch(self):
        page = _FakePage()
        page._element = MagicMock()
        page._element.text_content = AsyncMock(return_value="Actual Text")
        factory, pw, brk, ctx = _make_pw_mock(page=page)

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            rule = _make_rule("element", config={"selector": "#title", "text": "Expected Text"})
            result = await v.validate_rules(_session(), [rule], "https://example.com")

        assert result[0].passed is False
        assert "text" in result[0].message.lower()

    @pytest.mark.asyncio
    async def test_element_text_match(self):
        page = _FakePage()
        page._element = MagicMock()
        page._element.text_content = AsyncMock(return_value="Expected Text")
        factory, pw, brk, ctx = _make_pw_mock(page=page)

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            rule = _make_rule("element", config={"selector": "#title", "text": "Expected"})
            result = await v.validate_rules(_session(), [rule], "https://example.com")

        assert result[0].passed is True

    @pytest.mark.asyncio
    async def test_element_no_selector(self):
        page = _FakePage()
        factory, pw, brk, ctx = _make_pw_mock(page=page)

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            rule = _make_rule("element", config={})
            result = await v.validate_rules(_session(), [rule], "https://example.com")

        assert result[0].passed is False
        assert "selector" in result[0].message.lower()

    @pytest.mark.asyncio
    async def test_element_with_cookies(self):
        page = _FakePage()
        factory, pw, brk, ctx = _make_pw_mock(page=page)
        cookies = [{"name": "sid", "value": "1", "domain": ".example.com", "path": "/"}]

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            rule = _make_rule("element", config={"selector": "#main"})
            result = await v.validate_rules(_session(cookies=cookies), [rule], "https://example.com")

        assert result[0].passed is True
        assert len(ctx._cookies_added) == 1

    @pytest.mark.asyncio
    async def test_element_playwright_error(self):
        with _mock_async_playwright(RuntimeError("pw crash")):
            v = AdvancedValidator()
            rule = _make_rule("element", config={"selector": "#x"})
            result = await v.validate_rules(_session(), [rule], "https://example.com")

        assert result[0].passed is False
        assert "error" in result[0].message.lower()

    @pytest.mark.asyncio
    async def test_element_uses_site_url_from_session(self):
        page = _FakePage()
        factory, pw, brk, ctx = _make_pw_mock(page=page)
        cookies = [{"domain": ".mysite.com", "name": "s", "value": "1"}]

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            rule = _make_rule("element", config={"selector": "#el"})
            await v.validate_rules(_session(cookies=cookies), [rule])

        assert "mysite.com" in page.goto_url

    @pytest.mark.asyncio
    async def test_element_text_none_content(self):
        page = _FakePage()
        page._element = MagicMock()
        page._element.text_content = AsyncMock(return_value=None)
        factory, pw, brk, ctx = _make_pw_mock(page=page)

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            rule = _make_rule("element", config={"selector": "#title", "text": "Expected"})
            result = await v.validate_rules(_session(), [rule], "https://example.com")

        assert result[0].passed is False
        assert "text" in result[0].message.lower()


# ---------------------------------------------------------------------------
# Tests: validate_rules exception path and timing
# ---------------------------------------------------------------------------

class TestValidateRulesException:
    @pytest.mark.asyncio
    async def test_rule_that_raises_inside_dispatch(self):
        v = AdvancedValidator()
        rule = _make_rule("js")
        with patch.object(v, "_validate_js", side_effect=RuntimeError("boom")):
            results = await v.validate_rules(_session(), [rule], "https://example.com")

        assert len(results) == 1
        assert results[0].passed is False
        assert "failed" in results[0].message.lower()

    @pytest.mark.asyncio
    async def test_multiple_rules_mixed(self):
        page = _FakePage(evaluate_result=True)
        factory, pw, brk, ctx = _make_pw_mock(page=page)

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            rules = [
                _make_rule("js", name="js_pass", config={"script": "return true"}),
                _make_rule("cookie", name="cookie_fail", config={"name": "missing"}),
            ]
            results = await v.validate_rules(_session(), rules, "https://example.com")

        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is False

    @pytest.mark.asyncio
    async def test_duration_ms_recorded(self):
        page = _FakePage(evaluate_result=True)
        factory, pw, brk, ctx = _make_pw_mock(page=page)

        with _mock_async_playwright(factory):
            v = AdvancedValidator()
            rule = _make_rule("js", config={"script": "return true"})
            results = await v.validate_rules(_session(), [rule], "https://example.com")

        assert results[0].duration_ms is not None
        assert results[0].duration_ms >= 0

    @pytest.mark.asyncio
    async def test_unknown_rule_type(self):
        v = AdvancedValidator()
        rule = _make_rule("unknown_type")
        results = await v.validate_rules(_session(), [rule])
        assert len(results) == 1
        assert results[0].passed is False
        assert "unknown rule type" in results[0].message.lower()


# ---------------------------------------------------------------------------
# Tests: _validate_cookie through full path
# ---------------------------------------------------------------------------

class TestValidateCookieFullPath:
    @pytest.mark.asyncio
    async def test_cookie_found_through_validate_rules(self):
        v = AdvancedValidator()
        cookies = [{"name": "SID", "value": "abc", "domain": ".google.com"}]
        rule = _make_rule("cookie", config={"name": "SID"})
        results = await v.validate_rules(_session(cookies=cookies), [rule])
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_cookie_not_found_through_validate_rules(self):
        v = AdvancedValidator()
        rule = _make_rule("cookie", config={"name": "MISSING"})
        results = await v.validate_rules(_session(), [rule])
        assert results[0].passed is False

    @pytest.mark.asyncio
    async def test_cookie_wrong_value_through_validate_rules(self):
        v = AdvancedValidator()
        cookies = [{"name": "SID", "value": "abc", "domain": ".google.com"}]
        rule = _make_rule("cookie", config={"name": "SID", "value": "wrong"})
        results = await v.validate_rules(_session(cookies=cookies), [rule])
        assert results[0].passed is False

    @pytest.mark.asyncio
    async def test_cookie_should_not_exist_found_through_validate_rules(self):
        v = AdvancedValidator()
        cookies = [{"name": "SID", "value": "abc", "domain": ".google.com"}]
        rule = _make_rule("cookie", config={"name": "SID", "exists": False})
        results = await v.validate_rules(_session(cookies=cookies), [rule])
        assert results[0].passed is False

    @pytest.mark.asyncio
    async def test_cookie_should_not_exist_absent_through_validate_rules(self):
        v = AdvancedValidator()
        rule = _make_rule("cookie", config={"name": "SID", "exists": False})
        results = await v.validate_rules(_session(), [rule])
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_cookie_domain_filter_through_validate_rules(self):
        v = AdvancedValidator()
        cookies = [
            {"name": "SID", "value": "a", "domain": ".google.com"},
            {"name": "SID", "value": "b", "domain": ".other.com"},
        ]
        rule = _make_rule("cookie", config={"name": "SID", "domain": ".other.com"})
        results = await v.validate_rules(_session(cookies=cookies), [rule])
        assert results[0].passed is True
        assert results[0].details["value"] == "b"

    @pytest.mark.asyncio
    async def test_cookie_no_name_through_validate_rules(self):
        v = AdvancedValidator()
        rule = _make_rule("cookie", config={})
        results = await v.validate_rules(_session(), [rule])
        assert results[0].passed is False
        assert "no cookie name" in results[0].message.lower()


# ---------------------------------------------------------------------------
# Tests: _get_site_url edge cases
# ---------------------------------------------------------------------------

class TestGetSiteUrl:
    def test_empty_session(self):
        v = AdvancedValidator()
        url = v._get_site_url({})
        assert url == "https://www.unknown.com"

    def test_longest_domain_not_shortest(self):
        v = AdvancedValidator()
        session = {"cookies": [
            {"domain": ".verylongdomainname.com"},
            {"domain": ".short.com"},
        ]}
        url = v._get_site_url(session)
        assert url == "https://short.com"

    def test_domains_with_leading_dots_stripped(self):
        v = AdvancedValidator()
        session = {"cookies": [{"domain": "...example.com"}]}
        url = v._get_site_url(session)
        assert url == "https://example.com"


# ---------------------------------------------------------------------------
# Tests: _get_cookie_header edge cases
# ---------------------------------------------------------------------------

class TestGetCookieHeader:
    def test_subdomain_match(self):
        v = AdvancedValidator()
        session = {"cookies": [{"name": "t", "value": "1", "domain": ".example.com"}]}
        header = v._get_cookie_header(session, "https://sub.example.com/path")
        assert "t=1" in header

    def test_no_match(self):
        v = AdvancedValidator()
        session = {"cookies": [{"name": "t", "value": "1", "domain": ".other.com"}]}
        header = v._get_cookie_header(session, "https://example.com")
        assert header == ""

    def test_cookie_without_name_skipped(self):
        v = AdvancedValidator()
        session = {"cookies": [{"name": "", "value": "1", "domain": ".example.com"}]}
        header = v._get_cookie_header(session, "https://example.com")
        assert header == ""

    def test_exact_hostname_match(self):
        v = AdvancedValidator()
        session = {"cookies": [{"name": "a", "value": "b", "domain": "example.com"}]}
        header = v._get_cookie_header(session, "https://example.com/x")
        assert "a=b" in header

    def test_multiple_cookies(self):
        v = AdvancedValidator()
        session = {"cookies": [
            {"name": "a", "value": "1", "domain": ".example.com"},
            {"name": "b", "value": "2", "domain": ".example.com"},
        ]}
        header = v._get_cookie_header(session, "https://example.com")
        assert "a=1" in header
        assert "b=2" in header

    def test_no_hostname(self):
        v = AdvancedValidator()
        session = {"cookies": [{"name": "a", "value": "1", "domain": ".example.com"}]}
        header = v._get_cookie_header(session, "https://")
        assert header == ""


# ---------------------------------------------------------------------------
# Tests: _prepare_cookies edge cases
# ---------------------------------------------------------------------------

class TestPrepareCookies:
    def test_valid_same_site_values(self):
        v = AdvancedValidator()
        cookies = [
            {"name": "a", "value": "1", "domain": ".x.com", "sameSite": "strict"},
            {"name": "b", "value": "2", "domain": ".x.com", "sameSite": "lax"},
            {"name": "c", "value": "3", "domain": ".x.com", "sameSite": "none"},
        ]
        pw = v._prepare_cookies(cookies)
        assert pw[0]["sameSite"] == "Strict"
        assert pw[1]["sameSite"] == "Lax"
        assert pw[2]["sameSite"] == "None"

    def test_no_expiry(self):
        v = AdvancedValidator()
        cookies = [{"name": "a", "value": "1", "domain": ".x.com"}]
        pw = v._prepare_cookies(cookies)
        assert "expires" not in pw[0]

    def test_normal_expiry(self):
        v = AdvancedValidator()
        cookies = [{"name": "a", "value": "1", "domain": ".x.com", "expires": 1700000000}]
        pw = v._prepare_cookies(cookies)
        assert pw[0]["expires"] == 1700000000

    def test_missing_fields(self):
        v = AdvancedValidator()
        cookies = [{}]
        pw = v._prepare_cookies(cookies)
        assert pw[0]["name"] == ""
        assert pw[0]["value"] == ""
        assert pw[0]["domain"] == ""
        assert pw[0]["path"] == "/"

    def test_secure_cookie(self):
        v = AdvancedValidator()
        cookies = [{"name": "a", "value": "1", "domain": ".x.com", "secure": True}]
        pw = v._prepare_cookies(cookies)
        assert pw[0]["secure"] is True

    def test_httpOnly_cookie(self):
        v = AdvancedValidator()
        cookies = [{"name": "a", "value": "1", "domain": ".x.com", "httpOnly": True}]
        pw = v._prepare_cookies(cookies)
        assert pw[0]["httpOnly"] is True

    def test_expires_large_timestamp_divides_by_1000(self):
        v = AdvancedValidator()
        cookies = [{"name": "a", "value": "1", "domain": ".x.com", "expires": 1700000000000}]
        pw = v._prepare_cookies(cookies)
        assert pw[0]["expires"] == 1700000000.0

    def test_expires_small_timestamp_no_divide(self):
        v = AdvancedValidator()
        cookies = [{"name": "a", "value": "1", "domain": ".x.com", "expires": 1700000000}]
        pw = v._prepare_cookies(cookies)
        assert pw[0]["expires"] == 1700000000

    def test_sameSite_invalid_falls_back_to_lax(self):
        v = AdvancedValidator()
        cookies = [{"name": "a", "value": "1", "domain": ".x.com", "sameSite": "invalid"}]
        pw = v._prepare_cookies(cookies)
        assert pw[0]["sameSite"] == "Lax"

    def test_no_secure_no_httponly(self):
        v = AdvancedValidator()
        cookies = [{"name": "a", "value": "1", "domain": ".x.com"}]
        pw = v._prepare_cookies(cookies)
        assert "secure" not in pw[0]
        assert "httpOnly" not in pw[0]

    def test_expires_zero(self):
        v = AdvancedValidator()
        cookies = [{"name": "a", "value": "1", "domain": ".x.com", "expires": 0}]
        pw = v._prepare_cookies(cookies)
        assert "expires" not in pw[0]

    def test_multiple_cookies(self):
        v = AdvancedValidator()
        cookies = [
            {"name": "a", "value": "1", "domain": ".x.com"},
            {"name": "b", "value": "2", "domain": ".y.com"},
        ]
        pw = v._prepare_cookies(cookies)
        assert len(pw) == 2
        assert pw[0]["name"] == "a"
        assert pw[1]["name"] == "b"


# ---------------------------------------------------------------------------
# Tests: load_validation_rules / create_example_rules
# ---------------------------------------------------------------------------

class TestLoadAndCreateRules:
    def test_load_full_config(self, tmp_path):
        rules_file = tmp_path / "rules.json"
        rules_file.write_text(json.dumps([
            {"name": "r1", "type": "screenshot", "config": {"baseline": "x"}, "timeout": 10},
        ]))
        rules = load_validation_rules(str(rules_file))
        assert rules[0].type == "screenshot"
        assert rules[0].config == {"baseline": "x"}
        assert rules[0].timeout == 10

    def test_create_example_rules_types(self):
        rules = create_example_rules()
        type_set = {r.type for r in rules}
        assert type_set == {"js", "url", "cookie", "api"}

    def test_create_example_rules_have_names(self):
        rules = create_example_rules()
        for r in rules:
            assert r.name


# ---------------------------------------------------------------------------
# Tests: ValidationRule dataclass
# ---------------------------------------------------------------------------

class TestValidationRule:
    def test_custom_values(self):
        r = ValidationRule(name="custom", type="api", config={"url": "x"}, timeout=10)
        assert r.config == {"url": "x"}
        assert r.timeout == 10
