"""
Tests for Cookie Extractor

Phase 2 tests - must pass before proceeding to Phase 3.
"""

import json
import os
import sqlite3
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from tokenade.core.importer.cookie_extractor import (
    CookieExtractor, SiteFilter, SITE_DETECTION
)


class TestSiteFilter:
    """Test site-specific cookie filtering."""

    def test_no_filter_accepts_all(self):
        """Test that no filter accepts all cookies."""
        f = SiteFilter()
        cookies = [
            {"name": "SID", "domain": ".google.com"},
            {"name": "user_session", "domain": ".github.com"},
        ]
        assert f.filter_cookies(cookies) == cookies

    def test_filter_google_only(self):
        """Test filtering for Google cookies only."""
        f = SiteFilter(["google"])
        cookies = [
            {"name": "SID", "domain": ".google.com", "value": "x"},
            {"name": "SSID", "domain": "accounts.google.com", "value": "y"},
            {"name": "user_session", "domain": ".github.com", "value": "z"},
            {"name": "random", "domain": "example.com", "value": "w"},
        ]
        result = f.filter_cookies(cookies)
        assert len(result) == 2
        assert result[0]["name"] == "SID"
        assert result[1]["name"] == "SSID"

    def test_filter_github_only(self):
        """Test filtering for GitHub cookies only."""
        f = SiteFilter(["github"])
        cookies = [
            {"name": "SID", "domain": ".google.com"},
            {"name": "user_session", "domain": ".github.com"},
            {"name": "__Host-user_session_same_site", "domain": "github.com"},
        ]
        result = f.filter_cookies(cookies)
        assert len(result) == 2
        assert result[0]["name"] == "user_session"

    def test_filter_multiple_sites(self):
        """Test filtering for multiple sites."""
        f = SiteFilter(["google", "github"])
        cookies = [
            {"name": "SID", "domain": ".google.com"},
            {"name": "user_session", "domain": ".github.com"},
            {"name": "reddit_session", "domain": ".reddit.com"},
        ]
        result = f.filter_cookies(cookies)
        assert len(result) == 2

    def test_filter_critical_cookie_match(self):
        """Test that critical cookie names match even with different domains."""
        f = SiteFilter(["google"])
        cookies = [
            {"name": "SID", "domain": "some-cdn.com"},  # SID is critical for Google
        ]
        result = f.filter_cookies(cookies)
        assert len(result) == 1

    def test_filter_wildcard_domain(self):
        """Test wildcard domain matching."""
        f = SiteFilter(["google"])
        cookies = [
            {"name": "a", "domain": "mail.google.com"},
            {"name": "b", "domain": "accounts.google.com"},
            {"name": "c", "domain": "google.com"},
            {"name": "d", "domain": "notgoogle.com"},
        ]
        result = f.filter_cookies(cookies)
        assert len(result) == 3

    def test_detect_site_google(self):
        """Test Google site detection."""
        f = SiteFilter()
        cookies = [
            {"name": "SID", "domain": ".google.com"},
            {"name": "SSID", "domain": ".google.com"},
        ]
        assert f.detect_site(cookies) == "google"

    def test_detect_site_github(self):
        """Test GitHub site detection."""
        f = SiteFilter()
        cookies = [
            {"name": "user_session", "domain": ".github.com"},
        ]
        assert f.detect_site(cookies) == "github"

    def test_detect_site_unknown(self):
        """Test unknown site detection."""
        f = SiteFilter()
        cookies = [
            {"name": "random", "domain": "example.com"},
        ]
        assert f.detect_site(cookies) is None

    def test_unknown_site_warning(self):
        """Test warning for unknown site in filter."""
        f = SiteFilter(["nonexistent"])
        assert f.sites == ["nonexistent"]
        assert f._domain_patterns == []


class TestCookieExtractorChrome:
    """Test Chrome cookie extraction."""

    def _create_chrome_db(self, db_path: str, cookies_data: list):
        """Helper to create a mock Chrome cookies database."""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE cookies (
                host_key TEXT, name TEXT, value TEXT,
                encrypted_value BLOB, path TEXT,
                expires_utc INTEGER, is_secure INTEGER,
                is_httponly INTEGER, samesite INTEGER,
                creation_utc INTEGER, last_access_utc INTEGER
            )
        """)
        for cookie in cookies_data:
            cursor.execute("""
                INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, cookie)
        conn.commit()
        conn.close()

    def test_extract_chrome_no_db(self):
        """Test extraction when no cookies DB exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = CookieExtractor(tmpdir, "chrome")
            result = extractor.extract_chrome()
            assert result == []

    def test_extract_chrome_plain_cookies(self):
        """Test extracting unencrypted Chrome cookies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "Cookies")
            self._create_chrome_db(db_path, [
                (".google.com", "SID", "abc123", b"", "/",
                 0, 1, 0, 1, 0, 0),
                (".google.com", "SSID", "def456", b"", "/",
                 0, 1, 1, 1, 0, 0),
                (".github.com", "user_session", "xyz789", b"", "/",
                 0, 1, 0, 2, 0, 0),
            ])

            extractor = CookieExtractor(tmpdir, "chrome")
            cookies = extractor.extract_chrome()

            assert len(cookies) == 3
            # Find by name since ORDER BY host_key, name sorts alphabetically
            by_name = {c["name"]: c for c in cookies}
            assert "SID" in by_name
            assert by_name["SID"]["value"] == "abc123"
            assert by_name["SID"]["domain"] == ".google.com"
            assert by_name["SID"]["secure"] is True
            assert by_name["SID"]["httpOnly"] is False
            assert by_name["SID"]["sameSite"] == "Lax"
            assert by_name["SSID"]["httpOnly"] is True
            assert by_name["SSID"]["sameSite"] == "Lax"
            assert by_name["user_session"]["sameSite"] == "Strict"

    def test_extract_chrome_with_site_filter(self):
        """Test Chrome extraction with site filter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "Cookies")
            self._create_chrome_db(db_path, [
                (".google.com", "SID", "abc", b"", "/", 0, 1, 0, 1, 0, 0),
                (".github.com", "user_session", "xyz", b"", "/", 0, 1, 0, 2, 0, 0),
            ])

            extractor = CookieExtractor(tmpdir, "chrome")
            site_filter = SiteFilter(["google"])
            cookies = extractor.extract_chrome(site_filter)

            assert len(cookies) == 1
            assert cookies[0]["name"] == "SID"

    def test_extract_chrome_expires(self):
        """Test Chrome cookie with expiry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "Cookies")
            # Chrome time: microseconds since 1601-01-01
            # 132000000000000000 = ~2018-01-01
            chrome_time = 132000000000000000
            self._create_chrome_db(db_path, [
                (".google.com", "SID", "abc", b"", "/",
                 chrome_time, 1, 0, 1, 0, 0),
            ])

            extractor = CookieExtractor(tmpdir, "chrome")
            cookies = extractor.extract_chrome()

            assert "expires" in cookies[0]
            assert cookies[0]["expires"] > 0


class TestCookieExtractorFirefox:
    """Test Firefox cookie extraction."""

    def _create_firefox_db(self, db_path: str, cookies_data: list):
        """Helper to create a mock Firefox cookies database."""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE moz_cookies (
                host TEXT, name TEXT, value TEXT, path TEXT,
                expiry INTEGER, isSecure INTEGER, isHttpOnly INTEGER, sameSite INTEGER
            )
        """)
        for cookie in cookies_data:
            cursor.execute("""
                INSERT INTO moz_cookies VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, cookie)
        conn.commit()
        conn.close()

    def test_extract_firefox_no_db(self):
        """Test extraction when no cookies DB exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = CookieExtractor(tmpdir, "firefox")
            result = extractor.extract_firefox()
            assert result == []

    def test_extract_firefox_plain_cookies(self):
        """Test extracting Firefox cookies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "cookies.sqlite")
            self._create_firefox_db(db_path, [
                (".google.com", "SID", "abc123", "/", 0, 1, 0, 0),
                (".github.com", "user_session", "xyz789", "/", 0, 1, 0, 1),
            ])

            extractor = CookieExtractor(tmpdir, "firefox")
            cookies = extractor.extract_firefox()

            assert len(cookies) == 2
            # ORDER BY host, name sorts alphabetically: .github.com before .google.com
            by_name = {c["name"]: c for c in cookies}
            assert "SID" in by_name
            assert by_name["SID"]["value"] == "abc123"
            assert by_name["SID"]["sameSite"] == "None"
            assert by_name["user_session"]["sameSite"] == "Lax"

    def test_extract_firefox_with_filter(self):
        """Test Firefox extraction with site filter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "cookies.sqlite")
            self._create_firefox_db(db_path, [
                (".google.com", "SID", "abc", "/", 0, 1, 0, 0),
                (".github.com", "user_session", "xyz", "/", 0, 1, 0, 1),
            ])

            extractor = CookieExtractor(tmpdir, "firefox")
            site_filter = SiteFilter(["github"])
            cookies = extractor.extract_firefox(site_filter)

            assert len(cookies) == 1
            assert cookies[0]["name"] == "user_session"


class TestCookieExtractorFormats:
    """Test cookie file format parsers."""

    def test_parse_netscape(self):
        """Test Netscape cookies.txt parsing."""
        content = """# Netscape HTTP Cookie File
.google.com	TRUE	/	TRUE	0	SID	abc123
.github.com	TRUE	/	TRUE	0	user_session	xyz789
"""
        cookies = CookieExtractor.parse_netscape(content)
        assert len(cookies) == 2
        assert cookies[0]["domain"] == ".google.com"
        assert cookies[0]["name"] == "SID"
        assert cookies[0]["value"] == "abc123"
        assert cookies[0]["secure"] is True

    def test_parse_netscape_empty_lines(self):
        """Test Netscape parser with empty lines and comments."""
        content = """# Comment

# Another comment
.example.com	TRUE	/	FALSE	1234567890	name	value
"""
        cookies = CookieExtractor.parse_netscape(content)
        assert len(cookies) == 1
        assert cookies[0]["name"] == "name"

    def test_parse_json_list(self):
        """Test JSON list format."""
        content = json.dumps([
            {"name": "SID", "domain": ".google.com", "value": "abc"},
            {"name": "user_session", "domain": ".github.com", "value": "xyz"},
        ])
        cookies = CookieExtractor.parse_json(content)
        assert len(cookies) == 2
        assert cookies[0]["name"] == "SID"

    def test_parse_json_dict(self):
        """Test JSON dict format with cookies key."""
        content = json.dumps({
            "cookies": [
                {"name": "SID", "domain": ".google.com", "value": "abc"},
            ]
        })
        cookies = CookieExtractor.parse_json(content)
        assert len(cookies) == 1

    def test_extract_from_file_netscape(self):
        """Test extracting from Netscape file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(".google.com\tTRUE\t/\tTRUE\t0\tSID\tabc123\n")
            path = f.name

        try:
            extractor = CookieExtractor("/tmp", "chrome")
            cookies = extractor.extract_from_file(path, "netscape")
            assert len(cookies) == 1
            assert cookies[0]["name"] == "SID"
        finally:
            os.unlink(path)

    def test_extract_from_file_json(self):
        """Test extracting from JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(json.dumps([{"name": "SID", "domain": ".google.com", "value": "abc"}]))
            path = f.name

        try:
            extractor = CookieExtractor("/tmp", "chrome")
            cookies = extractor.extract_from_file(path, "auto")
            assert len(cookies) == 1
            assert cookies[0]["name"] == "SID"
        finally:
            os.unlink(path)

    def test_extract_from_file_with_filter(self):
        """Test file extraction with site filter."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(""".google.com\tTRUE\t/\tTRUE\t0\tSID\tabc123
.github.com\tTRUE\t/\tTRUE\t0\tuser_session\txyz789
""")
            path = f.name

        try:
            extractor = CookieExtractor("/tmp", "chrome")
            site_filter = SiteFilter(["google"])
            cookies = extractor.extract_from_file(path, "netscape", site_filter)
            assert len(cookies) == 1
            assert cookies[0]["name"] == "SID"
        finally:
            os.unlink(path)

    def test_extract_from_file_not_found(self):
        """Test error when file not found."""
        extractor = CookieExtractor("/tmp", "chrome")
        with pytest.raises(FileNotFoundError):
            extractor.extract_from_file("/nonexistent/file.txt")

    def test_extract_from_file_unknown_format(self):
        """Test error for unknown format."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test")
            path = f.name

        try:
            extractor = CookieExtractor("/tmp", "chrome")
            with pytest.raises(ValueError):
                extractor.extract_from_file(path, "unknown")
        finally:
            os.unlink(path)


class TestCookieExtractorDispatch:
    """Test browser type dispatch."""

    def test_extract_chrome_dispatch(self):
        """Test dispatch to Chrome extractor."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "Cookies")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE cookies (
                    host_key TEXT, name TEXT, value TEXT,
                    encrypted_value BLOB, path TEXT,
                    expires_utc INTEGER, is_secure INTEGER,
                    is_httponly INTEGER, samesite INTEGER,
                    creation_utc INTEGER, last_access_utc INTEGER
                )
            """)
            cursor.execute("""
                INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (".google.com", "SID", "abc", b"", "/", 0, 1, 0, 1, 0, 0))
            conn.commit()
            conn.close()

            extractor = CookieExtractor(tmpdir, "chrome")
            cookies = extractor.extract()
            assert len(cookies) == 1

    def test_extract_firefox_dispatch(self):
        """Test dispatch to Firefox extractor."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "cookies.sqlite")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE moz_cookies (
                    host TEXT, name TEXT, value TEXT, path TEXT,
                    expiry INTEGER, isSecure INTEGER, isHttpOnly INTEGER, sameSite INTEGER
                )
            """)
            cursor.execute("""
                INSERT INTO moz_cookies VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (".google.com", "SID", "abc", "/", 0, 1, 0, 0))
            conn.commit()
            conn.close()

            extractor = CookieExtractor(tmpdir, "firefox")
            cookies = extractor.extract()
            assert len(cookies) == 1

    def test_extract_unsupported_browser(self):
        """Test unsupported browser returns empty."""
        extractor = CookieExtractor("/tmp", "safari")
        cookies = extractor.extract()
        assert cookies == []

    def test_extract_edge_uses_chrome(self):
        """Test Edge uses Chrome extraction logic."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "Cookies")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE cookies (
                    host_key TEXT, name TEXT, value TEXT,
                    encrypted_value BLOB, path TEXT,
                    expires_utc INTEGER, is_secure INTEGER,
                    is_httponly INTEGER, samesite INTEGER,
                    creation_utc INTEGER, last_access_utc INTEGER
                )
            """)
            cursor.execute("""
                INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (".google.com", "SID", "abc", b"", "/", 0, 1, 0, 1, 0, 0))
            conn.commit()
            conn.close()

            extractor = CookieExtractor(tmpdir, "edge")
            cookies = extractor.extract()
            assert len(cookies) == 1


class TestSamesiteMapping:
    """Test SameSite value mapping."""

    def test_chrome_samesite_mapping(self):
        """Test Chrome SameSite integer mapping."""
        assert CookieExtractor._map_samesite(0) == "None"
        assert CookieExtractor._map_samesite(1) == "Lax"
        assert CookieExtractor._map_samesite(2) == "Strict"
        assert CookieExtractor._map_samesite(-1) == "None"
        assert CookieExtractor._map_samesite(99) == "Lax"  # Default

    def test_firefox_samesite_mapping(self):
        """Test Firefox SameSite integer mapping."""
        assert CookieExtractor._map_samesite_firefox(0) == "None"
        assert CookieExtractor._map_samesite_firefox(1) == "Lax"
        assert CookieExtractor._map_samesite_firefox(2) == "Strict"
        assert CookieExtractor._map_samesite_firefox(99) == "Lax"  # Default
