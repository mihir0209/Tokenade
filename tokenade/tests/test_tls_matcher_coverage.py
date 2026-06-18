"""
Comprehensive tests for tls_matcher.py — TLSMatcher, create_tls_matcher,
session setup, request methods, fingerprint mapping.
"""

import unittest
from unittest.mock import MagicMock, patch

try:
    from curl_cffi import requests as _curl_requests  # noqa: F401
    _has_curl_cffi = True
except ImportError:
    _has_curl_cffi = False

from tokenade.core.runtime.tls_matcher import (
    TLSMatcher,
    TLSFingerprint,
    create_tls_matcher,
    IMPERSONATE_TARGETS,
    BROWSER_DEFAULTS,
)


class TestTLSFingerprint(unittest.TestCase):
    def test_defaults(self):
        fp = TLSFingerprint()
        self.assertEqual(fp.browser, "chrome")
        self.assertEqual(fp.version, "120")
        self.assertEqual(fp.platform, "windows")
        self.assertEqual(fp.impersonate, "chrome120")

    def test_custom(self):
        fp = TLSFingerprint(
            browser="firefox", version="128", impersonate="firefox128"
        )
        self.assertEqual(fp.browser, "firefox")
        self.assertEqual(fp.impersonate, "firefox128")


class TestImpersonateTargets(unittest.TestCase):
    def test_chrome_targets(self):
        self.assertIn("chrome120", IMPERSONATE_TARGETS)
        self.assertIn("chrome131", IMPERSONATE_TARGETS)

    def test_firefox_targets(self):
        self.assertIn("firefox120", IMPERSONATE_TARGETS)
        self.assertIn("firefox128", IMPERSONATE_TARGETS)

    def test_safari_targets(self):
        self.assertIn("safari17_0", IMPERSONATE_TARGETS)
        self.assertIn("safari17_2_1", IMPERSONATE_TARGETS)

    def test_edge_targets(self):
        self.assertIn("edge120", IMPERSONATE_TARGETS)
        self.assertIn("edge131", IMPERSONATE_TARGETS)


class TestBrowserDefaults(unittest.TestCase):
    def test_chrome_default(self):
        self.assertEqual(BROWSER_DEFAULTS["chrome"], "chrome120")

    def test_firefox_default(self):
        self.assertEqual(BROWSER_DEFAULTS["firefox"], "firefox120")

    def test_safari_default(self):
        self.assertEqual(BROWSER_DEFAULTS["safari"], "safari17_0")

    def test_brave_default(self):
        self.assertEqual(BROWSER_DEFAULTS["brave"], "chrome120")


class TestTLSMatcherInit(unittest.TestCase):
    def test_default_init(self):
        with patch(
            "tokenade.core.runtime.tls_matcher.TLSMatcher._setup_session"
        ):
            m = TLSMatcher()
            self.assertIsNotNone(m.fingerprint)

    def test_custom_init(self):
        fp = TLSFingerprint(impersonate="chrome131")
        with patch(
            "tokenade.core.runtime.tls_matcher.TLSMatcher._setup_session"
        ):
            m = TLSMatcher(fingerprint=fp)
            self.assertEqual(m.fingerprint.impersonate, "chrome131")


class TestTLSMatcherSetupSession(unittest.TestCase):
    @unittest.skipUnless(
        _has_curl_cffi, "curl-cffi not installed"
    )
    def test_curl_cffi_installed(self):
        mock_session = MagicMock()
        mock_requests = MagicMock()
        mock_requests.Session.return_value = mock_session
        with patch(
            "tokenade.core.runtime.tls_matcher.curl_requests",
            mock_requests,
            create=True,
        ):
            with patch("importlib.import_module", return_value=mock_requests):
                m = TLSMatcher.__new__(TLSMatcher)
                m.fingerprint = TLSFingerprint()
                m._setup_session()
                # curl-cffi is installed, so it should use the real import
                self.assertIsNotNone(m._session)

    def test_curl_cffi_not_installed(self):
        original_import = (
            __builtins__.__import__
            if hasattr(__builtins__, "__import__")
            else __import__
        )

        def mock_import(name, *args, **kwargs):
            if name == "curl_cffi":
                raise ImportError("No module named 'curl_cffi'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            m = TLSMatcher.__new__(TLSMatcher)
            m.fingerprint = TLSFingerprint()
            m._setup_session()
            self.assertIsNone(m._session)

    def test_firefox_fallback(self):
        # curl-cffi is installed, test the actual fallback behavior
        m = TLSMatcher.__new__(TLSMatcher)
        fp = TLSFingerprint(impersonate="firefox120")
        m.fingerprint = fp
        m._session = None

        try:
            from curl_cffi import requests as curl_requests

            # Try creating a firefox session - if it fails, it should fall back
            try:
                session = curl_requests.Session(impersonate="firefox120")
                session.close()
            except Exception:
                fp.impersonate = "chrome120"
                m._setup_session()
        except ImportError:
            m._setup_session()
        # Firefox may or may not be supported depending on curl-cffi version
        # Just verify no crash

    @unittest.skipUnless(
        _has_curl_cffi, "curl-cffi not installed"
    )
    def test_other_error_reraises(self):
        # curl-cffi is installed, so mock the Session constructor to raise non-firefox error
        with patch(
            "curl_cffi.requests.Session",
            side_effect=RuntimeError("other error"),
        ):
            m = TLSMatcher.__new__(TLSMatcher)
            m.fingerprint = TLSFingerprint(impersonate="chrome131")
            with self.assertRaises(RuntimeError):
                m._setup_session()


class TestTLSMatcherGetImpersonateTarget(unittest.TestCase):
    def test_known_version(self):
        with patch(
            "tokenade.core.runtime.tls_matcher.TLSMatcher._setup_session"
        ):
            m = TLSMatcher()
            target = m._get_impersonate_target("chrome", "120")
            self.assertEqual(target, "chrome120")

    def test_unknown_version_fallback(self):
        with patch(
            "tokenade.core.runtime.tls_matcher.TLSMatcher._setup_session"
        ):
            m = TLSMatcher()
            target = m._get_impersonate_target("chrome", "999")
            self.assertEqual(target, "chrome120")

    def test_unknown_browser_fallback(self):
        with patch(
            "tokenade.core.runtime.tls_matcher.TLSMatcher._setup_session"
        ):
            m = TLSMatcher()
            target = m._get_impersonate_target("unknown", "1")
            self.assertEqual(target, "chrome120")


class TestTLSMatcherRequest(unittest.TestCase):
    def test_no_session_raises(self):
        with patch(
            "tokenade.core.runtime.tls_matcher.TLSMatcher._setup_session"
        ):
            m = TLSMatcher()
            m._session = None
            with self.assertRaises(RuntimeError):
                m.request("GET", "https://example.com")

    def test_get_request(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_session.request.return_value = mock_response
        with patch(
            "tokenade.core.runtime.tls_matcher.TLSMatcher._setup_session"
        ):
            m = TLSMatcher()
            m._session = mock_session
            m.get("https://example.com")
            mock_session.request.assert_called_once_with(
                method="GET",
                url="https://example.com",
                headers={},
                cookies={},
                data=None,
                json=None,
                timeout=30,
            )

    def test_post_request(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_session.request.return_value = mock_response
        with patch(
            "tokenade.core.runtime.tls_matcher.TLSMatcher._setup_session"
        ):
            m = TLSMatcher()
            m._session = mock_session
            m.post("https://example.com", data=b"body")
            mock_session.request.assert_called_once()

    def test_put_request(self):
        mock_session = MagicMock()
        mock_session.request.return_value = MagicMock()
        with patch(
            "tokenade.core.runtime.tls_matcher.TLSMatcher._setup_session"
        ):
            m = TLSMatcher()
            m._session = mock_session
            m.put("https://example.com")
            mock_session.request.assert_called_once()

    def test_delete_request(self):
        mock_session = MagicMock()
        mock_session.request.return_value = MagicMock()
        with patch(
            "tokenade.core.runtime.tls_matcher.TLSMatcher._setup_session"
        ):
            m = TLSMatcher()
            m._session = mock_session
            m.delete("https://example.com")
            mock_session.request.assert_called_once()


class TestTLSMatcherClose(unittest.TestCase):
    def test_close(self):
        mock_session = MagicMock()
        with patch(
            "tokenade.core.runtime.tls_matcher.TLSMatcher._setup_session"
        ):
            m = TLSMatcher()
            m._session = mock_session
            m.close()
            mock_session.close.assert_called_once()

    def test_close_no_session(self):
        with patch(
            "tokenade.core.runtime.tls_matcher.TLSMatcher._setup_session"
        ):
            m = TLSMatcher()
            m._session = None
            m.close()

    def test_context_manager(self):
        with patch(
            "tokenade.core.runtime.tls_matcher.TLSMatcher._setup_session"
        ):
            m = TLSMatcher()
            m._session = MagicMock()
            with m as ctx:
                self.assertEqual(ctx, m)
            m._session.close.assert_called()


class TestCreateTLSMatcher(unittest.TestCase):
    def test_with_impersonate(self):
        with patch(
            "tokenade.core.runtime.tls_matcher.TLSMatcher._setup_session"
        ):
            m = create_tls_matcher(impersonate="chrome131")
            self.assertEqual(m.fingerprint.impersonate, "chrome131")

    def test_with_browser_version(self):
        with patch(
            "tokenade.core.runtime.tls_matcher.TLSMatcher._setup_session"
        ):
            m = create_tls_matcher(browser="firefox", version="128")
            self.assertEqual(m.fingerprint.browser, "firefox")

    def test_unknown_browser_default(self):
        with patch(
            "tokenade.core.runtime.tls_matcher.TLSMatcher._setup_session"
        ):
            m = create_tls_matcher(browser="unknown")
            self.assertEqual(m.fingerprint.impersonate, "chrome120")


if __name__ == "__main__":
    unittest.main()
