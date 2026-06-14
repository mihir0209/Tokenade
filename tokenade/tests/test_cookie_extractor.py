"""Tests for cookie extractor."""

import os
import sqlite3
import tempfile
import pytest
from tokenade.core.importer.cookie_extractor import CookieExtractor, SiteFilter, SITE_DETECTION


class TestCookieExtractorFirefox:
    @pytest.fixture
    def firefox_db(self, tmp_path):
        """Create a minimal Firefox cookies.sqlite DB."""
        db_path = tmp_path / "cookies.sqlite"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE moz_cookies (
                id INTEGER PRIMARY KEY,
                baseDomain TEXT,
                originAttributes TEXT DEFAULT '',
                name TEXT,
                value TEXT,
                host TEXT,
                path TEXT,
                expiry INTEGER,
                lastAccessed INTEGER,
                creationTime INTEGER,
                isSecure INTEGER DEFAULT 0,
                isHttpOnly INTEGER DEFAULT 0,
                sameSite INTEGER DEFAULT -1,
                schemeMap INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            INSERT INTO moz_cookies (baseDomain, name, value, host, path, expiry, isSecure, isHttpOnly)
            VALUES ('example.com', 'session', 'abc123', '.example.com', '/', 9999999999, 1, 1)
        """)
        cursor.execute("""
            INSERT INTO moz_cookies (baseDomain, name, value, host, path, expiry, isSecure, isHttpOnly)
            VALUES ('example.com', 'lang', 'en', '.example.com', '/', 9999999999, 0, 0)
        """)
        conn.commit()
        conn.close()
        return str(tmp_path)

    def test_extract_firefox(self, firefox_db):
        extractor = CookieExtractor(firefox_db, browser="firefox")
        cookies = extractor.extract_firefox()
        assert len(cookies) == 2
        names = {c["name"] for c in cookies}
        assert "session" in names
        assert "lang" in names

    def test_extract_no_filter(self, firefox_db):
        extractor = CookieExtractor(firefox_db, browser="firefox")
        cookies = extractor.extract_firefox(site_filter=None)
        assert len(cookies) == 2

    def test_cookie_fields(self, firefox_db):
        extractor = CookieExtractor(firefox_db, browser="firefox")
        cookies = extractor.extract_firefox()
        session = [c for c in cookies if c["name"] == "session"][0]
        assert session["domain"] == ".example.com"
        assert session["path"] == "/"
        assert session["secure"] is True
        assert session["httpOnly"] is True


class TestCookieExtractorChrome:
    @pytest.fixture
    def chrome_db(self, tmp_path):
        """Create a minimal Chrome Cookies DB."""
        db_path = tmp_path / "Cookies"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE cookies (
                host_key TEXT,
                name TEXT,
                value TEXT,
                encrypted_value BLOB,
                path TEXT,
                expires_utc INTEGER,
                is_secure INTEGER DEFAULT 0,
                is_httponly INTEGER DEFAULT 0,
                samesite INTEGER DEFAULT -1,
                creation_utc INTEGER DEFAULT 0,
                last_access_utc INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            INSERT INTO cookies (host_key, name, value, path, expires_utc, is_secure, is_httponly)
            VALUES ('.example.com', 'session', 'xyz789', '/', 9999999999000000, 1, 1)
        """)
        conn.commit()
        conn.close()
        return str(tmp_path)

    def test_extract_chrome(self, chrome_db):
        extractor = CookieExtractor(chrome_db, browser="chrome")
        cookies = extractor.extract_chrome()
        assert len(cookies) == 1
        assert cookies[0]["name"] == "session"
        assert cookies[0]["value"] == "xyz789"


class TestSiteFilter:
    def test_filters_by_google(self):
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

    def test_site_detection_has_expected_sites(self):
        expected = ["google", "openai", "github", "discord", "reddit"]
        for site in expected:
            assert site in SITE_DETECTION
            assert "domains" in SITE_DETECTION[site]
            assert "critical_cookies" in SITE_DETECTION[site]
