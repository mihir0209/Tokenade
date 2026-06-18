"""
Comprehensive tests for validator.py — all validation strategies,
SessionValidator auto-detection, weighted voting, error handling.
"""

import time
import unittest
from unittest.mock import MagicMock

from tokenade.core.importer.validator import (
    ValidationResult,
    CSSIndicatorStrategy,
    URLRedirectStrategy,
    APIProbeStrategy,
    PageContentStrategy,
    CookieExpiryStrategy,
    LocalStorageStrategy,
    SessionValidator,
)


class TestValidationResult(unittest.TestCase):
    def test_defaults(self):
        result = ValidationResult(
            strategy="test", valid=True, confidence=0.5, reason="ok"
        )
        self.assertEqual(result.strategy, "test")
        self.assertTrue(result.valid)
        self.assertEqual(result.confidence, 0.5)
        self.assertEqual(result.details, {})

    def test_with_details(self):
        result = ValidationResult(
            strategy="t",
            valid=False,
            confidence=0.9,
            reason="fail",
            details={"k": "v"},
        )
        self.assertEqual(result.details["k"], "v")


class TestCSSIndicatorStrategy(unittest.TestCase):
    def test_name(self):
        strategy = CSSIndicatorStrategy()
        self.assertEqual(strategy.name(), "css_indicator")

    def test_no_config(self):
        strategy = CSSIndicatorStrategy()
        browser = MagicMock()
        result = strategy.validate(browser, {})
        self.assertTrue(result.valid)
        self.assertEqual(result.confidence, 0.0)

    def test_element_not_found(self):
        strategy = CSSIndicatorStrategy()
        browser = MagicMock()
        browser.query_selector.return_value = None
        result = strategy.validate(
            browser, {"login_indicator_css": "a[href='/login']"}
        )
        self.assertTrue(result.valid)
        self.assertEqual(result.confidence, 0.9)

    def test_element_found(self):
        strategy = CSSIndicatorStrategy()
        browser = MagicMock()
        browser.query_selector.return_value = MagicMock()
        result = strategy.validate(
            browser, {"login_indicator_css": "a[href='/login']"}
        )
        self.assertFalse(result.valid)
        self.assertEqual(result.confidence, 0.95)

    def test_query_exception(self):
        strategy = CSSIndicatorStrategy()
        browser = MagicMock()
        browser.query_selector.side_effect = RuntimeError("timeout")
        result = strategy.validate(
            browser, {"login_indicator_css": "a[href='/login']"}
        )
        self.assertTrue(result.valid)


class TestURLRedirectStrategy(unittest.TestCase):
    def test_name(self):
        strategy = URLRedirectStrategy()
        self.assertEqual(strategy.name(), "url_redirect")

    def test_no_config(self):
        strategy = URLRedirectStrategy()
        browser = MagicMock()
        result = strategy.validate(browser, {})
        self.assertTrue(result.valid)
        self.assertEqual(result.confidence, 0.0)

    def test_no_redirect(self):
        strategy = URLRedirectStrategy()
        browser = MagicMock()
        browser.evaluate.return_value = "https://github.com/settings"
        result = strategy.validate(
            browser, {"auth_gated_url": "https://github.com/settings"}
        )
        self.assertTrue(result.valid)
        self.assertEqual(result.confidence, 0.85)

    def test_redirect_to_login(self):
        strategy = URLRedirectStrategy()
        browser = MagicMock()
        browser.evaluate.return_value = "https://github.com/login"
        result = strategy.validate(
            browser, {"auth_gated_url": "https://github.com/settings"}
        )
        self.assertFalse(result.valid)
        self.assertIn("redirected to login", result.reason)

    def test_navigation_exception(self):
        strategy = URLRedirectStrategy()
        browser = MagicMock()
        browser.navigate.side_effect = RuntimeError("timeout")
        result = strategy.validate(
            browser, {"auth_gated_url": "https://github.com/settings"}
        )
        self.assertFalse(result.valid)
        self.assertEqual(result.confidence, 0.5)

    def test_custom_login_patterns(self):
        strategy = URLRedirectStrategy()
        browser = MagicMock()
        browser.evaluate.return_value = "https://example.com/my-login-page"
        result = strategy.validate(
            browser,
            {
                "auth_gated_url": "https://example.com/dashboard",
                "login_page_patterns": ["/my-login-page"],
            },
        )
        self.assertFalse(result.valid)


class TestAPIProbeStrategy(unittest.TestCase):
    def test_name(self):
        strategy = APIProbeStrategy()
        self.assertEqual(strategy.name(), "api_probe")

    def test_no_config(self):
        strategy = APIProbeStrategy()
        browser = MagicMock()
        result = strategy.validate(browser, {})
        self.assertTrue(result.valid)
        self.assertEqual(result.confidence, 0.0)

    def test_api_200(self):
        strategy = APIProbeStrategy()
        browser = MagicMock()
        browser.evaluate_with_arg.return_value = {
            "status": 200,
            "ok": True,
            "redirected": False,
        }
        result = strategy.validate(
            browser, {"api_probe_url": "https://api.github.com/user"}
        )
        self.assertTrue(result.valid)
        self.assertEqual(result.confidence, 0.8)

    def test_api_401(self):
        strategy = APIProbeStrategy()
        browser = MagicMock()
        browser.evaluate_with_arg.return_value = {
            "status": 401,
            "ok": False,
            "redirected": False,
        }
        result = strategy.validate(
            browser, {"api_probe_url": "https://api.github.com/user"}
        )
        self.assertFalse(result.valid)

    def test_api_403(self):
        strategy = APIProbeStrategy()
        browser = MagicMock()
        browser.evaluate_with_arg.return_value = {
            "status": 403,
            "ok": False,
            "redirected": True,
        }
        result = strategy.validate(
            browser, {"api_probe_url": "https://api.github.com/user"}
        )
        self.assertFalse(result.valid)

    def test_api_exception(self):
        strategy = APIProbeStrategy()
        browser = MagicMock()
        browser.evaluate_with_arg.side_effect = RuntimeError("fetch failed")
        result = strategy.validate(
            browser, {"api_probe_url": "https://api.github.com/user"}
        )
        self.assertFalse(result.valid)
        self.assertEqual(result.confidence, 0.3)

    def test_custom_method_and_headers(self):
        strategy = APIProbeStrategy()
        browser = MagicMock()
        browser.evaluate_with_arg.return_value = {
            "status": 200,
            "ok": True,
            "redirected": False,
        }
        result = strategy.validate(
            browser,
            {
                "api_probe_url": "https://api.example.com/data",
                "api_probe_method": "POST",
                "api_probe_headers": {"Content-Type": "application/json"},
            },
        )
        self.assertTrue(result.valid)


class TestPageContentStrategy(unittest.TestCase):
    def test_name(self):
        strategy = PageContentStrategy()
        self.assertEqual(strategy.name(), "page_content")

    def test_no_config(self):
        strategy = PageContentStrategy()
        browser = MagicMock()
        result = strategy.validate(browser, {})
        self.assertTrue(result.valid)
        self.assertEqual(result.confidence, 0.0)

    def test_selector_found(self):
        strategy = PageContentStrategy()
        browser = MagicMock()
        browser.query_selector.return_value = MagicMock()
        result = strategy.validate(
            browser, {"user_content_selectors": ["#user-menu"]}
        )
        self.assertTrue(result.valid)

    def test_selector_not_found(self):
        strategy = PageContentStrategy()
        browser = MagicMock()
        browser.query_selector.return_value = None
        result = strategy.validate(
            browser, {"user_content_selectors": ["#user-menu"]}
        )
        self.assertFalse(result.valid)

    def test_text_pattern_found(self):
        strategy = PageContentStrategy()
        browser = MagicMock()
        browser.evaluate.return_value = "Welcome, John! Your profile is ready."
        result = strategy.validate(
            browser, {"user_content_text": ["Welcome, John"]}
        )
        self.assertTrue(result.valid)

    def test_text_pattern_not_found(self):
        strategy = PageContentStrategy()
        browser = MagicMock()
        browser.evaluate.return_value = "Please sign in"
        result = strategy.validate(
            browser, {"user_content_text": ["Welcome, John"]}
        )
        self.assertFalse(result.valid)

    def test_text_pattern_case_insensitive(self):
        strategy = PageContentStrategy()
        browser = MagicMock()
        browser.evaluate.return_value = "welcome, user"
        result = strategy.validate(
            browser, {"user_content_text": ["WELCOME, USER"]}
        )
        self.assertTrue(result.valid)

    def test_selector_exception(self):
        strategy = PageContentStrategy()
        browser = MagicMock()
        browser.query_selector.side_effect = RuntimeError("timeout")
        result = strategy.validate(
            browser, {"user_content_selectors": ["#el"]}
        )
        self.assertFalse(result.valid)

    def test_text_exception(self):
        strategy = PageContentStrategy()
        browser = MagicMock()
        browser.evaluate.side_effect = RuntimeError("eval failed")
        result = strategy.validate(browser, {"user_content_text": ["text"]})
        self.assertFalse(result.valid)

    def test_null_page_text(self):
        strategy = PageContentStrategy()
        browser = MagicMock()
        browser.evaluate.return_value = None
        result = strategy.validate(browser, {"user_content_text": ["text"]})
        self.assertFalse(result.valid)


class TestCookieExpiryStrategy(unittest.TestCase):
    def test_name(self):
        strategy = CookieExpiryStrategy()
        self.assertEqual(strategy.name(), "cookie_expiry")

    def test_no_critical_cookies_with_cookies(self):
        strategy = CookieExpiryStrategy()
        browser = MagicMock()
        browser.get_cookies.return_value = [{"name": "sid", "value": "v"}]
        result = strategy.validate(browser, {})
        self.assertTrue(result.valid)
        self.assertEqual(result.confidence, 0.3)

    def test_no_critical_cookies_no_cookies(self):
        strategy = CookieExpiryStrategy()
        browser = MagicMock()
        browser.get_cookies.return_value = []
        result = strategy.validate(browser, {})
        self.assertFalse(result.valid)

    def test_critical_all_present(self):
        strategy = CookieExpiryStrategy()
        browser = MagicMock()
        browser.get_cookies.return_value = [
            {"name": "sid", "value": "v", "expires": time.time() + 3600},
            {"name": "token", "value": "t", "expires": time.time() + 7200},
        ]
        result = strategy.validate(
            browser, {"critical_cookies": ["sid", "token"]}
        )
        self.assertTrue(result.valid)
        self.assertEqual(result.details["status"], "logged_in")

    def test_critical_missing_all(self):
        strategy = CookieExpiryStrategy()
        browser = MagicMock()
        browser.get_cookies.return_value = [{"name": "other", "value": "v"}]
        result = strategy.validate(
            browser, {"critical_cookies": ["sid", "token"]}
        )
        self.assertFalse(result.valid)
        self.assertEqual(result.details["status"], "logged_out")

    def test_critical_missing_some(self):
        strategy = CookieExpiryStrategy()
        browser = MagicMock()
        browser.get_cookies.return_value = [
            {"name": "sid", "value": "v", "expires": time.time() + 3600},
        ]
        result = strategy.validate(
            browser, {"critical_cookies": ["sid", "token"]}
        )
        self.assertFalse(result.valid)
        self.assertEqual(result.details["status"], "session_expired")

    def test_critical_expired(self):
        strategy = CookieExpiryStrategy()
        browser = MagicMock()
        browser.get_cookies.return_value = [
            {"name": "sid", "value": "v", "expires": time.time() - 100},
        ]
        result = strategy.validate(browser, {"critical_cookies": ["sid"]})
        self.assertFalse(result.valid)
        self.assertIn("sid", result.details["expired"])

    def test_exception(self):
        strategy = CookieExpiryStrategy()
        browser = MagicMock()
        browser.get_cookies.side_effect = RuntimeError("db locked")
        result = strategy.validate(browser, {"critical_cookies": ["sid"]})
        self.assertFalse(result.valid)
        self.assertIn("error", result.details)


class TestLocalStorageStrategy(unittest.TestCase):
    def test_name(self):
        strategy = LocalStorageStrategy()
        self.assertEqual(strategy.name(), "local_storage")

    def test_no_config(self):
        strategy = LocalStorageStrategy()
        browser = MagicMock()
        result = strategy.validate(browser, {})
        self.assertTrue(result.valid)
        self.assertEqual(result.confidence, 0.0)

    def test_key_found(self):
        strategy = LocalStorageStrategy()
        browser = MagicMock()
        browser.evaluate.return_value = "some-token-value"
        result = strategy.validate(
            browser, {"localStorage_keys": ["auth_token"]}
        )
        self.assertTrue(result.valid)

    def test_key_not_found(self):
        strategy = LocalStorageStrategy()
        browser = MagicMock()
        browser.evaluate.return_value = None
        result = strategy.validate(
            browser, {"localStorage_keys": ["auth_token"]}
        )
        self.assertFalse(result.valid)

    def test_multiple_keys_partial(self):
        strategy = LocalStorageStrategy()
        browser = MagicMock()
        browser.evaluate.side_effect = ["token", None]
        result = strategy.validate(
            browser, {"localStorage_keys": ["auth_token", "refresh_token"]}
        )
        self.assertTrue(result.valid)
        self.assertIn("auth_token", result.details["found"])

    def test_exception(self):
        strategy = LocalStorageStrategy()
        browser = MagicMock()
        # The inner try/except swallows per-key errors, so simulate
        # the outer try block failing by passing a non-iterable as keys
        result = strategy.validate(browser, {"localStorage_keys": 42})
        self.assertFalse(result.valid)  # outer except catches TypeError
        self.assertEqual(result.confidence, 0.2)


class TestSessionValidator(unittest.TestCase):
    def test_empty_strategies_falls_to_autodetect(self):
        # Empty list is falsy, so falls to auto-detect which always includes cookie_expiry
        validator = SessionValidator(strategies=[])
        browser = MagicMock()
        browser.get_cookies.return_value = []
        result = validator.validate(browser, {})
        self.assertIn("cookie_expiry", result["strategies_run"])

    def test_auto_detect_css(self):
        validator = SessionValidator()
        browser = MagicMock()
        browser.query_selector.return_value = None
        result = validator.validate(
            browser,
            {
                "login_indicator_css": "a[href='/login']",
                "critical_cookies": ["sid"],
            },
        )
        self.assertIn("css_indicator", result["strategies_run"])
        self.assertIn("cookie_expiry", result["strategies_run"])

    def test_auto_detect_url_redirect(self):
        validator = SessionValidator()
        browser = MagicMock()
        browser.evaluate.return_value = "https://example.com/dashboard"
        result = validator.validate(
            browser,
            {
                "auth_gated_url": "https://example.com/dashboard",
                "critical_cookies": ["sid"],
            },
        )
        self.assertIn("url_redirect", result["strategies_run"])

    def test_auto_detect_api_probe(self):
        validator = SessionValidator()
        browser = MagicMock()
        browser.evaluate_with_arg.return_value = {
            "status": 200,
            "ok": True,
            "redirected": False,
        }
        result = validator.validate(
            browser,
            {
                "api_probe_url": "https://api.example.com/user",
                "critical_cookies": ["sid"],
            },
        )
        self.assertIn("api_probe", result["strategies_run"])

    def test_auto_detect_page_content(self):
        validator = SessionValidator()
        browser = MagicMock()
        browser.query_selector.return_value = MagicMock()
        result = validator.validate(
            browser,
            {
                "user_content_selectors": ["#user"],
                "critical_cookies": ["sid"],
            },
        )
        self.assertIn("page_content", result["strategies_run"])

    def test_auto_detect_local_storage(self):
        validator = SessionValidator()
        browser = MagicMock()
        browser.evaluate.return_value = "token"
        result = validator.validate(
            browser,
            {
                "localStorage_keys": ["auth"],
                "critical_cookies": ["sid"],
            },
        )
        self.assertIn("local_storage", result["strategies_run"])

    def test_explicit_strategies(self):
        validator = SessionValidator(
            strategies=["css_indicator", "cookie_expiry"]
        )
        browser = MagicMock()
        browser.query_selector.return_value = None
        browser.get_cookies.return_value = [
            {"name": "sid", "value": "v", "expires": time.time() + 3600}
        ]
        result = validator.validate(
            browser,
            {
                "login_indicator_css": "a[href='/login']",
                "critical_cookies": ["sid"],
            },
        )
        self.assertEqual(len(result["strategies_run"]), 2)

    def test_unknown_strategy_skipped(self):
        validator = SessionValidator(strategies=["nonexistent"])
        browser = MagicMock()
        result = validator.validate(browser, {})
        self.assertEqual(result["strategies_run"], [])

    def test_weighted_majority_valid(self):
        validator = SessionValidator(
            strategies=["css_indicator", "cookie_expiry"]
        )
        browser = MagicMock()
        browser.query_selector.return_value = None
        browser.get_cookies.return_value = [
            {"name": "sid", "value": "v", "expires": time.time() + 3600}
        ]
        result = validator.validate(
            browser,
            {
                "login_indicator_css": "a[href='/login']",
                "critical_cookies": ["sid"],
            },
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["auth_status"], "logged_in")

    def test_weighted_majority_invalid(self):
        validator = SessionValidator(strategies=["cookie_expiry"])
        browser = MagicMock()
        browser.get_cookies.return_value = []
        result = validator.validate(browser, {"critical_cookies": ["sid"]})
        self.assertFalse(result["valid"])
        self.assertEqual(result["auth_status"], "logged_out")

    def test_session_expired_status(self):
        validator = SessionValidator(strategies=["cookie_expiry"])
        browser = MagicMock()
        browser.get_cookies.return_value = [{"name": "other", "value": "v"}]
        result = validator.validate(
            browser, {"critical_cookies": ["sid", "token"]}
        )
        self.assertFalse(result["valid"])
        self.assertEqual(result["auth_status"], "logged_out")

    def test_strategy_error_captured(self):
        validator = SessionValidator(strategies=["css_indicator"])
        browser = MagicMock()
        browser.query_selector.side_effect = RuntimeError("crash")
        result = validator.validate(browser, {"login_indicator_css": "#el"})
        self.assertIn("css_indicator", result["strategies_run"])

    def test_all_strategies_skip(self):
        validator = SessionValidator(strategies=[])
        browser = MagicMock()
        result = validator.validate(browser, {})
        self.assertFalse(result["valid"])


if __name__ == "__main__":
    unittest.main()
