"""Tests for site filter."""

from tokenade.core.importer.cookie_extractor import SiteFilter


class TestSiteFilter:
    def test_filters_by_site(self):
        filter_obj = SiteFilter(["google"])
        cookies = [
            {"name": "SID", "domain": ".google.com", "value": "x"},
            {"name": "session", "domain": ".github.com", "value": "y"},
            {"name": "NID", "domain": ".google.com", "value": "z"},
        ]
        filtered = filter_obj.filter_cookies(cookies)
        assert len(filtered) == 2
        assert all("google" in c["domain"] for c in filtered)

    def test_no_filter(self):
        filter_obj = SiteFilter(None)
        cookies = [
            {"name": "SID", "domain": ".google.com", "value": "x"},
            {"name": "session", "domain": ".github.com", "value": "y"},
        ]
        filtered = filter_obj.filter_cookies(cookies)
        assert len(filtered) == 2

    def test_empty_filter(self):
        filter_obj = SiteFilter([])
        cookies = [{"name": "SID", "domain": ".google.com", "value": "x"}]
        filtered = filter_obj.filter_cookies(cookies)
        assert len(filtered) == 1

    def test_case_insensitive(self):
        filter_obj = SiteFilter(["Google"])
        cookies = [{"name": "SID", "domain": ".google.com", "value": "x"}]
        filtered = filter_obj.filter_cookies(cookies)
        assert len(filtered) == 1

    def test_multiple_sites(self):
        filter_obj = SiteFilter(["google", "github"])
        cookies = [
            {"name": "SID", "domain": ".google.com", "value": "x"},
            {"name": "session", "domain": ".github.com", "value": "y"},
            {"name": "other", "domain": ".example.com", "value": "z"},
        ]
        filtered = filter_obj.filter_cookies(cookies)
        assert len(filtered) == 2

    def test_subdomain_match(self):
        filter_obj = SiteFilter(["google"])
        cookies = [
            {"name": "SID", "domain": ".google.com", "value": "x"},
            {"name": "NID", "domain": "accounts.google.com", "value": "y"},
        ]
        filtered = filter_obj.filter_cookies(cookies)
        assert len(filtered) == 2

    def test_exact_domain_match(self):
        filter_obj = SiteFilter(["github"])
        cookies = [
            {"name": "session", "domain": ".github.com", "value": "x"},
            {"name": "other", "domain": "github.com", "value": "y"},
        ]
        filtered = filter_obj.filter_cookies(cookies)
        assert len(filtered) == 2
