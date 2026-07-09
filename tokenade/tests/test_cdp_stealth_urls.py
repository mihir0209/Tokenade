"""URL safety and site URL helpers for cdp_stealth."""

import unittest
from unittest.mock import patch


class TestIsSafeUrlExceptionPath(unittest.TestCase):
    """Lines 39-41: is_safe_url returns False when exception occurs."""

    def test_is_safe_url_type_error_on_parse(self):
        from tokenade.core.proxy.cdp_stealth import is_safe_url

        with patch("tokenade.core.proxy.cdp_stealth.urlparse", side_effect=TypeError("bad url")):
            result = is_safe_url(12345)

        self.assertFalse(result)

    def test_is_safe_url_value_error_on_parse(self):
        from tokenade.core.proxy.cdp_stealth import is_safe_url

        with patch("tokenade.core.proxy.cdp_stealth.urlparse", side_effect=ValueError("parse error")):
            result = is_safe_url("ftp://bad")

        self.assertFalse(result)


class TestGetSiteUrlKnownSite(unittest.TestCase):
    """Line 215: get_site_url returns SITE_URLS lookup for known site."""

    def test_known_site_returns_url(self):
        from tokenade.core.proxy.cdp_stealth import get_site_url

        session = {"site_name": "github"}
        with patch("tokenade.core.importer.site_configs.get_site_config", return_value=None):
            result = get_site_url(session)

        self.assertEqual(result, "https://github.com")

    def test_known_site_case_insensitive(self):
        from tokenade.core.proxy.cdp_stealth import get_site_url

        session = {"site_name": "Reddit"}
        with patch("tokenade.core.importer.site_configs.get_site_config", return_value=None):
            result = get_site_url(session)

        self.assertEqual(result, "https://www.reddit.com")


if __name__ == "__main__":
    unittest.main()
