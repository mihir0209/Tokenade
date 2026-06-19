import asyncio
import concurrent.futures
import unittest
from unittest.mock import MagicMock, AsyncMock

from tokenade.core.proxy.cdp_injection import inject_cookies, inject_local_storage, inject_stealth_script


def _make_proxy():
    proxy = MagicMock()
    proxy._context = AsyncMock()
    proxy.session = {"cookies": [], "local_storage": {}}
    proxy._pages = {}
    return proxy


def _run_async(coro):
    with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result(timeout=10)


class TestInjectCookiesCoverage(unittest.TestCase):
    def test_inject_cookies_with_expired_timestamp(self):
        proxy = _make_proxy()
        proxy.session = {"cookies": [
            {"name": "sid", "value": "v", "domain": ".example.com",
             "path": "/", "secure": True, "httpOnly": True,
             "sameSite": "lax", "expires": 1700000000000}
        ]}
        _run_async(inject_cookies(proxy))
        proxy._context.add_cookies.assert_called_once()
        cookie = proxy._context.add_cookies.call_args[0][0][0]
        self.assertAlmostEqual(cookie["expires"], 1700000000.0)
        self.assertTrue(cookie["secure"])
        self.assertTrue(cookie["httpOnly"])
        self.assertEqual(cookie["sameSite"], "Lax")

    def test_inject_cookies_with_normal_expires(self):
        proxy = _make_proxy()
        proxy.session = {"cookies": [
            {"name": "sid", "value": "v", "domain": ".example.com",
             "path": "/", "secure": False, "httpOnly": False,
             "sameSite": "strict", "expires": 1700000000}
        ]}
        _run_async(inject_cookies(proxy))
        proxy._context.add_cookies.assert_called_once()
        cookie = proxy._context.add_cookies.call_args[0][0][0]
        self.assertEqual(cookie["expires"], 1700000000.0)

    def test_inject_cookies_no_context(self):
        proxy = _make_proxy()
        proxy._context = None
        proxy.session = {"cookies": [
            {"name": "sid", "value": "v", "domain": ".example.com",
             "path": "/", "secure": True, "httpOnly": False,
             "sameSite": "lax", "expires": 1700000000}
        ]}
        _run_async(inject_cookies(proxy))
        proxy._context = None
        # Should not raise, returns early

    def test_inject_cookies_exception_per_cookie(self):
        proxy = _make_proxy()
        proxy.session = {"cookies": [
            {"name": "bad", "value": "v", "domain": ".example.com",
             "path": "/", "secure": True, "httpOnly": True,
             "sameSite": "Lax", "expires": 1700000000000},
            {"name": "good", "value": "v2", "domain": ".example.com",
             "path": "/", "secure": False, "httpOnly": False,
             "sameSite": "none", "expires": 1700000000}
        ]}
        # Make cookie.get raise on first cookie's "name" key — tricky because get is called
        # many times. Instead, we test that if processing one cookie fails, the rest still work.
        # We'll make the first cookie's domain cause an issue by making it not a string.
        # Actually, the try/except is per-cookie, so let's make a cookie dict that raises
        # when iterated for sameSite.lower(). Easiest: mock the cookie itself.
        bad_cookie = MagicMock()
        bad_cookie.get.side_effect = Exception("process error")
        proxy.session = {"cookies": [bad_cookie, {
            "name": "good", "value": "v2", "domain": ".example.com",
            "path": "/", "secure": False, "httpOnly": False,
            "sameSite": "none", "expires": 1700000000}
        ]}
        _run_async(inject_cookies(proxy))
        # Only good cookie should be added
        proxy._context.add_cookies.assert_called_once()
        cookies_added = proxy._context.add_cookies.call_args[0][0]
        self.assertEqual(len(cookies_added), 1)
        self.assertEqual(cookies_added[0]["name"], "good")

    def test_inject_cookies_same_site_variants(self):
        proxy = _make_proxy()
        proxy.session = {"cookies": [
            {"name": "a", "value": "1", "domain": ".a.com",
             "path": "/", "sameSite": "strict"},
            {"name": "b", "value": "2", "domain": ".b.com",
             "path": "/", "sameSite": "lax"},
            {"name": "c", "value": "3", "domain": ".c.com",
             "path": "/", "sameSite": "none"},
            {"name": "d", "value": "4", "domain": ".d.com",
             "path": "/", "sameSite": ""},
        ]}
        _run_async(inject_cookies(proxy))
        proxy._context.add_cookies.assert_called_once()
        cookies = proxy._context.add_cookies.call_args[0][0]
        self.assertEqual(len(cookies), 4)
        # strict, lax, none get capitalized; empty stays omitted
        self.assertEqual(cookies[0]["sameSite"], "Strict")
        self.assertEqual(cookies[1]["sameSite"], "Lax")
        self.assertEqual(cookies[2]["sameSite"], "None")
        self.assertNotIn("sameSite", cookies[3])

    def test_inject_cookies_secure_httponly(self):
        proxy = _make_proxy()
        proxy.session = {"cookies": [
            {"name": "a", "value": "1", "domain": ".a.com",
             "path": "/", "secure": True, "httpOnly": True},
            {"name": "b", "value": "2", "domain": ".b.com",
             "path": "/", "secure": False, "httpOnly": False},
        ]}
        _run_async(inject_cookies(proxy))
        proxy._context.add_cookies.assert_called_once()
        cookies = proxy._context.add_cookies.call_args[0][0]
        self.assertTrue(cookies[0]["secure"])
        self.assertTrue(cookies[0]["httpOnly"])
        self.assertNotIn("secure", cookies[1])
        self.assertNotIn("httpOnly", cookies[1])


class TestInjectLocalStorageCoverage(unittest.TestCase):
    def test_inject_local_storage_nested_dict(self):
        proxy = _make_proxy()
        proxy.session = {"local_storage": {
            "https://example.com": {"key1": "val1", "key2": "val2"},
            "https://other.com": "simple_string"
        }}
        page = AsyncMock()
        _run_async(inject_local_storage(proxy, page))
        page.evaluate.assert_called_once()
        js = page.evaluate.call_args[0][0]
        self.assertIn("key1", js)
        self.assertIn("key2", js)
        self.assertIn("simple_string", js)

    def test_inject_local_storage_empty(self):
        proxy = _make_proxy()
        proxy.session = {"local_storage": {}}
        page = AsyncMock()
        _run_async(inject_local_storage(proxy, page))
        page.evaluate.assert_not_called()


class TestInjectStealthScriptCoverage(unittest.TestCase):
    def test_inject_stealth_script_no_context(self):
        proxy = _make_proxy()
        proxy._context = None
        _run_async(inject_stealth_script(proxy))
        # Should return immediately, no error

    def test_inject_stealth_script_with_pages(self):
        proxy = _make_proxy()
        page1 = AsyncMock()
        page2 = AsyncMock()
        proxy._pages = {"p1": page1, "p2": page2}
        _run_async(inject_stealth_script(proxy))
        page1.evaluate.assert_called_once()
        page2.evaluate.assert_called_once()
        proxy._context.add_init_script.assert_called_once()


if __name__ == "__main__":
    unittest.main()
