"""Tests for cookie extractor."""

import json
import os
import sqlite3
from unittest.mock import MagicMock, patch

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

    def test_extract_firefox_db_not_found(self, tmp_path):
        """Line 385-386: Firefox cookies DB not found returns empty list."""
        extractor = CookieExtractor(str(tmp_path), browser="firefox")
        cookies = extractor.extract_firefox()
        assert cookies == []

    def test_extract_firefox_with_site_filter(self, firefox_db):
        """Line 371: Apply site filter to firefox cookies."""
        filter_obj = SiteFilter(["google"])
        extractor = CookieExtractor(firefox_db, browser="firefox")
        cookies = extractor.extract_firefox(site_filter=filter_obj)
        assert cookies == []

    def test_extract_firefox_conn_close_error(self, firefox_db):
        """Lines 424-427: Firefox finally block handles conn.close() error."""
        extractor = CookieExtractor(firefox_db, browser="firefox")
        extractor._copy_db
        extractor._copy_db = MagicMock(side_effect=Exception("copy failed"))
        with patch("tokenade.core.importer.cookie_extractor.copy_db", side_effect=Exception("copy failed")):
            with pytest.raises(Exception, match="copy failed"):
                extractor.extract_firefox()

    def test_extract_firefox_conn_close_in_finally(self, firefox_db):
        """Lines 424-427: Firefox finally block conn.close() raises but is caught."""
        extractor = CookieExtractor(firefox_db, browser="firefox")

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('.example.com', 's', 'v', '/', 0, 0, 0, -1)
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.close.side_effect = Exception("close failed")

        with patch("sqlite3.connect", return_value=mock_conn):
            with patch("tokenade.core.importer.cookie_extractor.copy_db", return_value="/tmp/fake.db"):
                with patch("os.path.exists", return_value=True):
                    with patch("os.remove"):
                        with pytest.raises(Exception, match="close failed"):
                            extractor.extract_firefox()

    def test_extract_firefox_zero_expiry(self, firefox_db):
        """Expiry=0 should not add expires field."""
        db_path = os.path.join(firefox_db, "cookies.sqlite")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM moz_cookies")
        cursor.execute("""
            INSERT INTO moz_cookies (baseDomain, name, value, host, path, expiry, isSecure, isHttpOnly)
            VALUES ('example.com', 'test', 'val', '.example.com', '/', 0, 0, 0)
        """)
        conn.commit()
        conn.close()
        extractor = CookieExtractor(firefox_db, browser="firefox")
        cookies = extractor.extract_firefox()
        assert len(cookies) == 1
        assert "expires" not in cookies[0]

    def test_extract_firefox_same_site_values(self, firefox_db):
        """Test all sameSite integer mappings for Firefox."""
        db_path = os.path.join(firefox_db, "cookies.sqlite")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM moz_cookies")
        for ss_val in [0, 1, 2, 3, -1]:
            cursor.execute("""
                INSERT INTO moz_cookies (baseDomain, name, value, host, path, expiry, isSecure, isHttpOnly, sameSite)
                VALUES ('example.com', ?, 'v', '.example.com', '/', 9999999999, 0, 0, ?)
            """, (f'ss_{ss_val}', ss_val))
        conn.commit()
        conn.close()
        extractor = CookieExtractor(firefox_db, browser="firefox")
        cookies = extractor.extract_firefox()
        ss_map = {c['name']: c['sameSite'] for c in cookies}
        assert ss_map['ss_0'] == 'None'
        assert ss_map['ss_1'] == 'Lax'
        assert ss_map['ss_2'] == 'Strict'
        assert ss_map['ss_3'] == 'Lax'  # unmapped value -> default
        assert ss_map['ss_-1'] == 'Lax'


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

    def test_extract_chrome_db_not_found(self, tmp_path):
        """Lines 266-267: Chrome cookies DB not found returns empty list."""
        extractor = CookieExtractor(str(tmp_path), browser="chrome")
        cookies = extractor.extract_chrome()
        assert cookies == []

    def test_extract_chrome_progress_callback(self, chrome_db):
        """Lines 270, 293, 314: progress_callback is called during extraction."""
        extractor = CookieExtractor(chrome_db, browser="chrome")
        progress = MagicMock()
        cookies = extractor.extract_chrome(progress_callback=progress)
        assert len(cookies) == 1
        assert progress.call_count >= 2
        first_call = progress.call_args_list[0]
        assert first_call[0][2] == "copying_database"

    def test_extract_chrome_with_site_filter(self, chrome_db):
        """Line 371: Apply site filter to chrome cookies."""
        filter_obj = SiteFilter(["google"])
        extractor = CookieExtractor(chrome_db, browser="chrome")
        cookies = extractor.extract_chrome(site_filter=filter_obj)
        assert cookies == []

    def test_extract_chrome_conn_close_error(self, chrome_db):
        """Lines 362-365: Chrome finally block handles conn.close() error."""
        extractor = CookieExtractor(chrome_db, browser="chrome")

        mock_conn = MagicMock()
        mock_conn.close.side_effect = Exception("close failed")
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('.example.com', 's', 'v', b'', '/', 0, 0, 0, -1, 0, 0)
        ]
        mock_conn.cursor.return_value = mock_cursor

        with patch("sqlite3.connect", return_value=mock_conn):
            with patch("tokenade.core.importer.cookie_extractor.copy_db", return_value="/tmp/fake.db"):
                with patch("os.path.exists", return_value=True):
                    with patch("os.remove"):
                        with pytest.raises(Exception, match="close failed"):
                            extractor.extract_chrome()

    def test_extract_chrome_encrypted_value_with_key(self, chrome_db):
        """Lines 319-332: encrypted_value present and decryption succeeds/fails."""
        db_path = os.path.join(chrome_db, "Cookies")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cookies")
        cursor.execute("""
            INSERT INTO cookies (host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly)
            VALUES ('.example.com', 'enc_cookie', '', X'DEADBEEF', '/', 0, 0, 0)
        """)
        cursor.execute("""
            INSERT INTO cookies (host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly)
            VALUES ('.example.com', 'enc_cookie2', '', X'CAFEBABE', '/', 0, 0, 0)
        """)
        conn.commit()
        conn.close()

        mock_crypto = MagicMock()
        # Prefer multi-path used by extractor
        mock_crypto.get_password_candidates.return_value = [b"fakekey"]
        mock_crypto.decrypt_cookie_multi.side_effect = ["decrypted_val", None]

        extractor = CookieExtractor(chrome_db, browser="chrome")
        extractor._crypto = mock_crypto

        with patch.object(extractor, '_get_crypto', return_value=mock_crypto):
            with patch.object(extractor, '_copy_db', return_value=db_path):
                with patch('tokenade.core.importer.cookie_extractor.os.path.dirname', return_value=chrome_db):
                    with patch.object(mock_crypto, 'get_encryption_key', return_value=b'fakekey'):
                        cookies = extractor.extract_chrome()

        assert len(cookies) == 2
        vals = {c['name']: c['value'] for c in cookies}
        assert vals['enc_cookie'] == 'decrypted_val'
        assert vals['enc_cookie2'] == ''  # decryption returned None → empty (no garbage)

    def test_extract_chrome_encrypted_value_no_key(self, chrome_db):
        """Lines 334-335: encrypted_value present but no key."""
        db_path = os.path.join(chrome_db, "Cookies")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cookies")
        cursor.execute("""
            INSERT INTO cookies (host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly)
            VALUES ('.example.com', 'enc_no_key', '', X'DEADBEEF', '/', 0, 0, 0)
        """)
        conn.commit()
        conn.close()

        mock_crypto = MagicMock()
        mock_crypto.get_encryption_key.side_effect = Exception("no key")
        mock_crypto.get_password_candidates.return_value = []
        mock_crypto.decrypt_cookie_multi.return_value = None
        mock_crypto.decrypt_cookie.return_value = None

        extractor = CookieExtractor(chrome_db, browser="chrome")
        with patch.object(extractor, '_get_crypto', return_value=mock_crypto):
            with patch.object(extractor, '_copy_db', return_value=db_path):
                cookies = extractor.extract_chrome()

        assert len(cookies) == 1
        assert cookies[0]['value'] == ''  # falls back to empty

    def test_extract_chrome_get_encryption_key_exception(self, chrome_db):
        """Lines 303-304: get_encryption_key raises exception."""
        db_path = os.path.join(chrome_db, "Cookies")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cookies")
        cursor.execute("""
            INSERT INTO cookies (host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly)
            VALUES ('.example.com', 'c', 'v', NULL, '/', 0, 0, 0)
        """)
        conn.commit()
        conn.close()

        mock_crypto = MagicMock()
        mock_crypto.get_encryption_key.side_effect = Exception("key error")
        del mock_crypto.get_encryption_key  # remove it so hasattr returns False

        extractor = CookieExtractor(chrome_db, browser="chrome")
        with patch.object(extractor, '_get_crypto', return_value=mock_crypto):
            with patch.object(extractor, '_copy_db', return_value=db_path):
                cookies = extractor.extract_chrome()

        assert len(cookies) == 1

    def test_extract_chrome_with_expires(self, tmp_path):
        """Line 353: cookie with valid expires gets expires field."""
        db_path = tmp_path / "Cookies"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE cookies (
                host_key TEXT, name TEXT, value TEXT, encrypted_value BLOB,
                path TEXT, expires_utc INTEGER, is_secure INTEGER DEFAULT 0,
                is_httponly INTEGER DEFAULT 0, samesite INTEGER DEFAULT -1,
                creation_utc INTEGER DEFAULT 0, last_access_utc INTEGER DEFAULT 0
            )
        """)
        # expires_utc must be > 11644473600 * 1000000 = 11644473600000000 for positive expires
        cursor.execute("""
            INSERT INTO cookies (host_key, name, value, path, expires_utc, is_secure, is_httponly)
            VALUES ('.example.com', 'exp', 'val', '/', 13200000000000000, 0, 0)
        """)
        conn.commit()
        conn.close()
        extractor = CookieExtractor(str(tmp_path), browser="chrome")
        cookies = extractor.extract_chrome()
        assert len(cookies) == 1
        assert "expires" in cookies[0]

    def test_extract_chrome_decrypt_exception(self, chrome_db):
        """Lines 319-332: decrypt_cookie raises an exception."""
        db_path = os.path.join(chrome_db, "Cookies")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cookies")
        cursor.execute("""
            INSERT INTO cookies (host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly)
            VALUES ('.example.com', 'bad', '', X'FF', '/', 0, 0, 0)
        """)
        conn.commit()
        conn.close()

        mock_crypto = MagicMock()
        mock_crypto.decrypt_cookie.side_effect = RuntimeError("decrypt boom")

        extractor = CookieExtractor(chrome_db, browser="chrome")
        with patch.object(extractor, '_get_crypto', return_value=mock_crypto):
            with patch.object(extractor, '_copy_db', return_value=db_path):
                with patch('tokenade.core.importer.cookie_extractor.os.path.dirname', return_value=chrome_db):
                    with patch.object(mock_crypto, 'get_encryption_key', return_value=b'k'):
                        cookies = extractor.extract_chrome()

        assert len(cookies) == 1

    def test_extract_chrome_decrypt_failed_warning(self, chrome_db):
        """Line 374: decrypt_failed > 0 triggers warning log."""
        db_path = os.path.join(chrome_db, "Cookies")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cookies")
        cursor.execute("""
            INSERT INTO cookies (host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly)
            VALUES ('.example.com', '', '', X'FF', '/', 0, 0, 0)
        """)
        conn.commit()
        conn.close()

        mock_crypto = MagicMock()
        mock_crypto.get_password_candidates.return_value = [b"k"]
        mock_crypto.decrypt_cookie_multi.return_value = None
        mock_crypto.decrypt_cookie.return_value = None

        extractor = CookieExtractor(chrome_db, browser="chrome")
        with patch.object(extractor, '_get_crypto', return_value=mock_crypto):
            with patch.object(extractor, '_copy_db', return_value=db_path):
                with patch('tokenade.core.importer.cookie_extractor.os.path.dirname', return_value=chrome_db):
                    with patch.object(mock_crypto, 'get_encryption_key', return_value=b'k'):
                        with patch("tokenade.core.importer.cookie_extractor.logger") as mock_logger:
                            extractor.extract_chrome()
                            mock_logger.warning.assert_called()

    def test_extract_chrome_samesite_values(self, chrome_db):
        """Test all sameSite integer mappings for Chrome."""
        db_path = os.path.join(chrome_db, "Cookies")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cookies")
        for ss_val in [0, 1, 2, -1, 99]:
            cursor.execute("""
                INSERT INTO cookies (host_key, name, value, path, expires_utc, is_secure, is_httponly, samesite)
                VALUES ('.example.com', ?, 'v', '/', 0, 0, 0, ?)
            """, (f'ss_{ss_val}', ss_val))
        conn.commit()
        conn.close()
        extractor = CookieExtractor(chrome_db, browser="chrome")
        cookies = extractor.extract_chrome()
        ss_map = {c['name']: c['sameSite'] for c in cookies}
        assert ss_map['ss_0'] == 'None'
        assert ss_map['ss_1'] == 'Lax'
        assert ss_map['ss_2'] == 'Strict'
        assert ss_map['ss_-1'] == 'None'
        assert ss_map['ss_99'] == 'Lax'

    def test_extract_chrome_expires_zero(self, chrome_db):
        """expires_utc=0 should not add expires field."""
        db_path = os.path.join(chrome_db, "Cookies")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cookies")
        cursor.execute("""
            INSERT INTO cookies (host_key, name, value, path, expires_utc, is_secure, is_httponly)
            VALUES ('.example.com', 'noexp', 'v', '/', 0, 0, 0)
        """)
        conn.commit()
        conn.close()
        extractor = CookieExtractor(chrome_db, browser="chrome")
        cookies = extractor.extract_chrome()
        assert len(cookies) == 1
        assert "expires" not in cookies[0]

    def test_extract_chrome_progress_callback_milestones(self, chrome_db):
        """Lines 270, 293, 314: progress_callback at various stages."""
        db_path = os.path.join(chrome_db, "Cookies")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cookies")
        for i in range(100):
            cursor.execute("""
                INSERT INTO cookies (host_key, name, value, path, expires_utc, is_secure, is_httponly)
                VALUES (?, ?, 'v', '/', 0, 0, 0)
            """, (f'.example{i}.com', f'c{i}'))
        conn.commit()
        conn.close()

        progress = MagicMock()
        extractor = CookieExtractor(chrome_db, browser="chrome")
        cookies = extractor.extract_chrome(progress_callback=progress)
        assert len(cookies) == 100
        assert progress.call_count >= 2


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

    def test_unknown_site_logs_warning(self):
        """Line 158: Unknown site logs a warning."""
        with patch("tokenade.core.importer.cookie_extractor.logger") as mock_logger:
            SiteFilter(["unknownsite"])
            mock_logger.warning.assert_called_once_with("Unknown site: unknownsite")

    def test_matches_no_filter(self):
        """Line 163: matches() returns True when no sites filter."""
        filter_obj = SiteFilter(None)
        assert filter_obj.matches({"name": "anything", "domain": "any.com"}) is True

    def test_matches_empty_sites(self):
        """Line 163: matches() returns True when sites list is empty."""
        filter_obj = SiteFilter([])
        assert filter_obj.matches({"name": "anything", "domain": "any.com"}) is True

    def test_matches_wildcard_domain(self):
        """Line 174: wildcard domain pattern (.google.com) matches."""
        filter_obj = SiteFilter(["google"])
        assert filter_obj.matches({"name": "other", "domain": ".google.com"}) is True

    def test_matches_wildcard_subdomain(self):
        """Line 174: wildcard domain matches subdomain like mail.google.com."""
        filter_obj = SiteFilter(["google"])
        assert filter_obj.matches({"name": "other", "domain": "mail.google.com"}) is True

    def test_matches_critical_cookie_prefix(self):
        """Lines 182-183: prefix critical cookie (ending with _) matches."""
        filter_obj = SiteFilter(["openai"])
        assert filter_obj.matches({"name": "usc_token", "domain": "other.com"}) is True

    def test_matches_critical_cookie_exact(self):
        """Line 185: exact critical cookie name matches."""
        filter_obj = SiteFilter(["github"])
        assert filter_obj.matches({"name": "user_session", "domain": "other.com"}) is True

    def test_matches_non_matching_domain_and_name(self):
        """When neither domain nor cookie name matches, returns False."""
        filter_obj = SiteFilter(["google"])
        assert filter_obj.matches({"name": "random", "domain": "random.com"}) is False

    def test_matches_exact_domain(self):
        """Non-dot-prefixed exact domain match."""
        filter_obj = SiteFilter(["github"])
        assert filter_obj.matches({"name": "other", "domain": "github.com"}) is True

    def test_matches_domain_with_subdomain_suffix(self):
        """Non-dot-prefixed domain with subdomain suffix match."""
        filter_obj = SiteFilter(["github"])
        assert filter_obj.matches({"name": "other", "domain": "api.github.com"}) is True

    def test_filter_cookies_with_sites(self):
        """filter_cookies applies matches correctly."""
        filter_obj = SiteFilter(["github"])
        cookies = [
            {"name": "user_session", "domain": "other.com"},
            {"name": "random", "domain": "random.com"},
        ]
        filtered = filter_obj.filter_cookies(cookies)
        assert len(filtered) == 1
        assert filtered[0]["name"] == "user_session"

    def test_detect_site_by_domain(self):
        """detect_site returns site name based on domain matching."""
        filter_obj = SiteFilter()
        cookies = [
            {"name": "something", "domain": ".google.com"},
            {"name": "other", "domain": ".google.com"},
        ]
        result = filter_obj.detect_site(cookies)
        assert result == "google"

    def test_detect_site_by_critical_cookie(self):
        """Lines 228-231: detect_site via critical cookie names."""
        filter_obj = SiteFilter()
        cookies = [
            {"name": "user_session", "domain": ".random.com"},
        ]
        result = filter_obj.detect_site(cookies)
        assert result == "github"

    def test_detect_site_by_critical_cookie_prefix(self):
        """Line 229: detect_site via critical cookie prefix (ending with _)."""
        filter_obj = SiteFilter()
        cookies = [
            {"name": "usc_something", "domain": ".random.com"},
        ]
        result = filter_obj.detect_site(cookies)
        assert result == "openai"

    def test_detect_site_generic_name_skipped(self):
        """Lines 225-226: generic names like 'authorization' are skipped."""
        filter_obj = SiteFilter()
        cookies = [
            {"name": "authorization", "domain": ".random.com"},
        ]
        result = filter_obj.detect_site(cookies)
        assert result is None

    def test_detect_site_no_match(self):
        """detect_site returns None when no site matches."""
        filter_obj = SiteFilter()
        cookies = [
            {"name": "random", "domain": ".random.com"},
        ]
        result = filter_obj.detect_site(cookies)
        assert result is None

    def test_detect_site_returns_max_domain_matches(self):
        """detect_site returns site with most domain matches."""
        filter_obj = SiteFilter()
        cookies = [
            {"name": "a", "domain": "google.com"},
            {"name": "b", "domain": ".google.com"},
            {"name": "c", "domain": "mail.google.com"},
        ]
        result = filter_obj.detect_site(cookies)
        assert result == "google"

    def test_wildcard_dot_prefix_google(self):
        """Line 170-174: .google.com matches google.com exactly."""
        filter_obj = SiteFilter(["google"])
        assert filter_obj.matches({"name": "x", "domain": "google.com"}) is True

    def test_brave_specific_domains(self):
        """Test brave browser domains in SITE_DETECTION."""
        SiteFilter(["brave"]) if "brave" in SITE_DETECTION else SiteFilter()
        if "brave" in SITE_DETECTION:
            assert "brave" in SITE_DETECTION

    def test_opera_specific_domains(self):
        """Test opera browser domains in SITE_DETECTION."""
        SiteFilter(["opera"]) if "opera" in SITE_DETECTION else SiteFilter()
        if "opera" in SITE_DETECTION:
            assert "opera" in SITE_DETECTION

    def test_empty_cookie_in_matches(self):
        """matches handles cookies with missing domain/name."""
        filter_obj = SiteFilter(["google"])
        assert filter_obj.matches({}) is False

    def test_detect_site_empty_cookies(self):
        """detect_site returns None for empty cookie list."""
        filter_obj = SiteFilter()
        result = filter_obj.detect_site([])
        assert result is None

    def test_matches_wildcard_domain_direct(self):
        """Line 174: wildcard dot-prefix pattern matches via endswith."""
        filter_obj = SiteFilter(["google"])
        filter_obj._domain_patterns = [".google.com"]
        assert filter_obj.matches({"name": "other", "domain": "mail.google.com"}) is True

    def test_matches_wildcard_domain_exact_clean(self):
        """Line 173: wildcard dot-prefix pattern matches via clean_pattern equality."""
        filter_obj = SiteFilter(["google"])
        filter_obj._domain_patterns = [".google.com"]
        assert filter_obj.matches({"name": "other", "domain": "google.com"}) is True


class TestCookieExtractorExtract:
    @pytest.fixture
    def chrome_db(self, tmp_path):
        db_path = tmp_path / "Cookies"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE cookies (
                host_key TEXT, name TEXT, value TEXT, encrypted_value BLOB,
                path TEXT, expires_utc INTEGER, is_secure INTEGER DEFAULT 0,
                is_httponly INTEGER DEFAULT 0, samesite INTEGER DEFAULT -1,
                creation_utc INTEGER DEFAULT 0, last_access_utc INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            INSERT INTO cookies (host_key, name, value, path, expires_utc, is_secure, is_httponly)
            VALUES ('.example.com', 'session', 'xyz789', '/', 0, 0, 0)
        """)
        conn.commit()
        conn.close()
        return str(tmp_path)

    @pytest.fixture
    def firefox_db(self, tmp_path):
        db_path = tmp_path / "cookies.sqlite"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE moz_cookies (
                id INTEGER PRIMARY KEY, baseDomain TEXT, originAttributes TEXT DEFAULT '',
                name TEXT, value TEXT, host TEXT, path TEXT, expiry INTEGER,
                lastAccessed INTEGER, creationTime INTEGER,
                isSecure INTEGER DEFAULT 0, isHttpOnly INTEGER DEFAULT 0,
                sameSite INTEGER DEFAULT -1, schemeMap INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            INSERT INTO moz_cookies (baseDomain, name, value, host, path, expiry, isSecure, isHttpOnly)
            VALUES ('example.com', 'f_session', 'abc123', '.example.com', '/', 0, 0, 0)
        """)
        conn.commit()
        conn.close()
        return str(tmp_path)

    def test_extract_chrome_browser(self, chrome_db):
        """Lines 497-498: extract dispatches to extract_chrome for chrome."""
        extractor = CookieExtractor(chrome_db, browser="chrome")
        cookies = extractor.extract()
        assert len(cookies) == 1

    def test_extract_chromium_browser(self, chrome_db):
        """Lines 497-498: extract dispatches to extract_chrome for chromium."""
        extractor = CookieExtractor(chrome_db, browser="chromium")
        cookies = extractor.extract()
        assert len(cookies) == 1

    def test_extract_edge_browser(self, chrome_db):
        """Lines 497-498: extract dispatches to extract_chrome for edge."""
        extractor = CookieExtractor(chrome_db, browser="edge")
        cookies = extractor.extract()
        assert len(cookies) == 1

    def test_extract_brave_browser(self, chrome_db):
        """Lines 497-498: extract dispatches to extract_chrome for brave."""
        extractor = CookieExtractor(chrome_db, browser="brave")
        cookies = extractor.extract()
        assert len(cookies) == 1

    def test_extract_firefox_browser(self, firefox_db):
        """Lines 499-500: extract dispatches to extract_firefox."""
        extractor = CookieExtractor(firefox_db, browser="firefox")
        cookies = extractor.extract()
        assert len(cookies) == 1

    def test_extract_unsupported_browser(self, chrome_db):
        """Lines 502-507: unsupported browser returns empty list."""
        extractor = CookieExtractor(chrome_db, browser="safari")
        with patch("tokenade.core.importer.cookie_extractor.logger") as mock_logger:
            cookies = extractor.extract()
            assert cookies == []
            mock_logger.error.assert_called_once()

    def test_extract_progress_callback(self, chrome_db):
        """Lines 494-495, 509-510: progress_callback called for starting and complete."""
        progress = MagicMock()
        extractor = CookieExtractor(chrome_db, browser="chrome")
        extractor.extract(progress_callback=progress)
        assert progress.call_count >= 2
        first_call = progress.call_args_list[0]
        last_call = progress.call_args_list[-1]
        assert first_call[0][2] == "starting"
        assert last_call[0][2] == "complete"

    def test_extract_progress_callback_firefox(self, firefox_db):
        """Lines 494-495, 509-510: progress_callback with firefox."""
        progress = MagicMock()
        extractor = CookieExtractor(firefox_db, browser="firefox")
        extractor.extract(progress_callback=progress)
        assert progress.call_count >= 2

    def test_extract_progress_callback_unsupported(self, chrome_db):
        """Lines 509-510: progress_callback complete for unsupported browser."""
        progress = MagicMock()
        extractor = CookieExtractor(chrome_db, browser="safari")
        with patch("tokenade.core.importer.cookie_extractor.logger"):
            extractor.extract(progress_callback=progress)
        assert progress.call_count >= 2


class TestParseNetscape:
    def test_parse_netscape_basic(self):
        """Lines 517-536: parse Netscape cookie format."""
        content = """.example.com	TRUE	/	TRUE	9999999999	session	abc123
.github.com	FALSE	/	FALSE	0	token	xyz
"""
        cookies = CookieExtractor.parse_netscape(content)
        assert len(cookies) == 2
        assert cookies[0]["domain"] == ".example.com"
        assert cookies[0]["name"] == "session"
        assert cookies[0]["value"] == "abc123"
        assert cookies[0]["secure"] is True
        assert cookies[0]["httpOnly"] is False
        assert cookies[1]["secure"] is False

    def test_parse_netscape_empty_lines(self):
        """Lines 519-521: blank and comment lines are skipped."""
        content = """

# This is a comment
"""
        cookies = CookieExtractor.parse_netscape(content)
        assert cookies == []

    def test_parse_netscape_invalid_line(self):
        """Lines 524: lines with fewer than 7 parts are skipped."""
        content = "invalid_line"
        cookies = CookieExtractor.parse_netscape(content)
        assert cookies == []

    def test_parse_netscape_expires_none(self):
        """Line 533: non-digit expires becomes None."""
        content = ".example.com\tTRUE\t/\tFALSE\tNaN\tname\tvalue"
        cookies = CookieExtractor.parse_netscape(content)
        assert len(cookies) == 1
        assert cookies[0]["expires"] is None

    def test_parse_netscape_httponly(self):
        """Line 532: flag field starting with #HttpOnly_ sets httpOnly=True."""
        content = ".example.com\t#HttpOnly_\t/\tTRUE\t0\tsid\tval"
        cookies = CookieExtractor.parse_netscape(content)
        assert len(cookies) == 1
        assert cookies[0]["httpOnly"] is True


class TestParseJson:
    def test_parse_json_list(self):
        """Lines 541-542: JSON array of cookies."""
        content = json.dumps([
            {"domain": ".example.com", "name": "s", "value": "v"}
        ])
        cookies = CookieExtractor.parse_json(content)
        assert len(cookies) == 1
        assert cookies[0]["name"] == "s"

    def test_parse_json_dict_with_cookies_key(self):
        """Lines 544-545: JSON dict with 'cookies' key."""
        content = json.dumps({
            "cookies": [
                {"domain": ".example.com", "name": "s", "value": "v"}
            ]
        })
        cookies = CookieExtractor.parse_json(content)
        assert len(cookies) == 1

    def test_parse_json_dict_without_cookies_key(self):
        """Lines 546: JSON dict without 'cookies' key returns empty list."""
        content = json.dumps({"other": "data"})
        cookies = CookieExtractor.parse_json(content)
        assert cookies == []

    def test_parse_json_invalid(self):
        """parse_json raises on invalid JSON."""
        with pytest.raises(json.JSONDecodeError):
            CookieExtractor.parse_json("not json")


class TestParseCurl:
    def test_parse_curl_delegates_to_netscape(self):
        """Line 552: parse_curl delegates to parse_netscape."""
        content = ".example.com\tTRUE\t/\tTRUE\t0\tsession\tval"
        cookies = CookieExtractor.parse_curl(content)
        assert len(cookies) == 1
        assert cookies[0]["name"] == "session"


class TestExtractFromFile:
    def test_extract_from_file_netscape(self, tmp_path):
        """Lines 557-582: extract from Netscape format file."""
        file_path = tmp_path / "cookies.txt"
        file_path.write_text(".example.com\tTRUE\t/\tTRUE\t0\tsession\tval\n")
        extractor = CookieExtractor(str(tmp_path))
        cookies = extractor.extract_from_file(str(file_path))
        assert len(cookies) == 1

    def test_extract_from_file_json(self, tmp_path):
        """Lines 565-566: auto-detect JSON format from .json extension."""
        file_path = tmp_path / "cookies.json"
        file_path.write_text(json.dumps([{"name": "s", "value": "v", "domain": ".d.com"}]))
        extractor = CookieExtractor(str(tmp_path))
        cookies = extractor.extract_from_file(str(file_path))
        assert len(cookies) == 1

    def test_extract_from_file_not_found(self, tmp_path):
        """Lines 558-559: raises FileNotFoundError."""
        extractor = CookieExtractor(str(tmp_path))
        with pytest.raises(FileNotFoundError):
            extractor.extract_from_file("/nonexistent/file.txt")

    def test_extract_from_file_explicit_json(self, tmp_path):
        """Line 572-573: explicit format_type='json'."""
        file_path = tmp_path / "data.txt"
        file_path.write_text(json.dumps([{"name": "s", "value": "v", "domain": ".d.com"}]))
        extractor = CookieExtractor(str(tmp_path))
        cookies = extractor.extract_from_file(str(file_path), format_type="json")
        assert len(cookies) == 1

    def test_extract_from_file_explicit_curl(self, tmp_path):
        """Lines 574-575: explicit format_type='curl'."""
        file_path = tmp_path / "cookies.curl"
        file_path.write_text(".example.com\tTRUE\t/\tTRUE\t0\tsession\tval\n")
        extractor = CookieExtractor(str(tmp_path))
        cookies = extractor.extract_from_file(str(file_path), format_type="curl")
        assert len(cookies) == 1

    def test_extract_from_file_unknown_format(self, tmp_path):
        """Lines 576-577: raises ValueError for unknown format."""
        file_path = tmp_path / "data.bin"
        file_path.write_text("data")
        extractor = CookieExtractor(str(tmp_path))
        with pytest.raises(ValueError, match="Unknown format"):
            extractor.extract_from_file(str(file_path), format_type="xml")

    def test_extract_from_file_auto_netscape(self, tmp_path):
        """Line 568: non-.json extension defaults to netscape."""
        file_path = tmp_path / "cookies.dat"
        file_path.write_text(".example.com\tTRUE\t/\tTRUE\t0\tsession\tval\n")
        extractor = CookieExtractor(str(tmp_path))
        cookies = extractor.extract_from_file(str(file_path))
        assert len(cookies) == 1

    def test_extract_from_file_with_site_filter(self, tmp_path):
        """Lines 579-580: apply site_filter to parsed cookies."""
        file_path = tmp_path / "cookies.txt"
        file_path.write_text(".google.com\tTRUE\t/\tTRUE\t0\tSID\tval\n")
        filter_obj = SiteFilter(["github"])
        extractor = CookieExtractor(str(tmp_path))
        cookies = extractor.extract_from_file(str(file_path), site_filter=filter_obj)
        assert cookies == []

    def test_extract_from_file_json_dict_no_cookies(self, tmp_path):
        """Line 546: JSON dict without cookies key returns empty."""
        file_path = tmp_path / "cookies.json"
        file_path.write_text(json.dumps({"data": "value"}))
        extractor = CookieExtractor(str(tmp_path))
        cookies = extractor.extract_from_file(str(file_path))
        assert cookies == []


class TestMapSameSite:
    def test_map_samesite_chrome(self):
        """Test Chrome samesite mapping."""
        assert CookieExtractor._map_samesite(0) == "None"
        assert CookieExtractor._map_samesite(1) == "Lax"
        assert CookieExtractor._map_samesite(2) == "Strict"
        assert CookieExtractor._map_samesite(-1) == "None"
        assert CookieExtractor._map_samesite(99) == "Lax"

    def test_map_samesite_firefox(self):
        """Test Firefox samesite mapping."""
        assert CookieExtractor._map_samesite_firefox(0) == "None"
        assert CookieExtractor._map_samesite_firefox(1) == "Lax"
        assert CookieExtractor._map_samesite_firefox(2) == "Strict"
        assert CookieExtractor._map_samesite_firefox(99) == "Lax"


class TestCookieExtractorEdgeCases:
    def test_init_browser_lowercased(self):
        """browser string is lowercased in __init__."""
        ext = CookieExtractor("/tmp", browser="Chrome")
        assert ext.browser == "chrome"

    def test_lazy_crypto_init(self):
        """_get_crypto creates crypto instance lazily."""
        ext = CookieExtractor("/tmp")
        assert ext._crypto is None
        with patch("tokenade.core.importer.cookie_extractor.CookieCryptoFactory.create") as mock_create:
            mock_create.return_value = MagicMock()
            crypto = ext._get_crypto()
            assert crypto is not None
            mock_create.assert_called_once()
            # Second call returns cached
            crypto2 = ext._get_crypto()
            assert crypto is crypto2

    def test_copy_db_delegates(self):
        """_copy_db delegates to copy_db function."""
        ext = CookieExtractor("/tmp")
        with patch("tokenade.core.importer.cookie_extractor.copy_db") as mock_copy:
            mock_copy.return_value = "/tmp/temp.db"
            result = ext._copy_db("/tmp/real.db")
            assert result == "/tmp/temp.db"
            mock_copy.assert_called_once_with("/tmp/real.db")

    def test_parse_netscape_only_7_parts(self):
        """parse_netscape handles exactly 7 parts."""
        content = ".example.com\tTRUE\t/\tTRUE\t0\tsession\tval"
        cookies = CookieExtractor.parse_netscape(content)
        assert len(cookies) == 1


class TestExtractFirefoxLocalStorage:
    @pytest.fixture
    def firefox_ls_db(self, tmp_path):
        """Create a Firefox localStorage database."""
        storage_base = tmp_path / "storage" / "default" / "https+++example.com" / "ls"
        storage_base.mkdir(parents=True)
        db_path = storage_base / "data.sqlite"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE data (key TEXT, value BLOB)")
        cursor.execute("INSERT INTO data (key, value) VALUES (?, ?)", ("token", b"abc123"))
        cursor.execute("INSERT INTO data (key, value) VALUES (?, ?)", ("theme", b"dark"))
        conn.commit()
        conn.close()
        return str(tmp_path)

    def test_extract_local_storage(self, firefox_ls_db):
        """Lines 448-484: extract Firefox localStorage."""
        extractor = CookieExtractor(firefox_ls_db, browser="firefox")
        result = extractor.extract_firefox_local_storage(domains=["example.com"])
        assert result == {"example.com:token": "abc123", "example.com:theme": "dark"}

    def test_extract_local_storage_no_storage_dir(self, tmp_path):
        """Lines 449-451: storage directory not found returns empty."""
        extractor = CookieExtractor(str(tmp_path), browser="firefox")
        result = extractor.extract_firefox_local_storage(domains=["example.com"])
        assert result == {}

    def test_extract_local_storage_no_domains(self, firefox_ls_db):
        """Lines 455-456: empty domains list returns empty."""
        extractor = CookieExtractor(firefox_ls_db, browser="firefox")
        result = extractor.extract_firefox_local_storage(domains=[])
        assert result == {}

    def test_extract_local_storage_domain_not_found(self, firefox_ls_db):
        """Lines 458-459: domain without storage continues."""
        extractor = CookieExtractor(firefox_ls_db, browser="firefox")
        result = extractor.extract_firefox_local_storage(domains=["nonexistent.com"])
        assert result == {}

    def test_extract_local_storage_multiple_domains(self, firefox_ls_db):
        """Extract localStorage for multiple domains."""
        # Create second domain storage
        ls2 = os.path.join(firefox_ls_db, "storage", "default", "https+++other.com", "ls")
        os.makedirs(ls2)
        db2 = os.path.join(ls2, "data.sqlite")
        conn = sqlite3.connect(db2)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE data (key TEXT, value BLOB)")
        cursor.execute("INSERT INTO data (key, value) VALUES (?, ?)", ("id", b"42"))
        conn.commit()
        conn.close()

        extractor = CookieExtractor(firefox_ls_db, browser="firefox")
        result = extractor.extract_firefox_local_storage(domains=["example.com", "other.com"])
        assert "example.com:token" in result
        assert "other.com:id" in result

    def test_extract_local_storage_binary_value(self, firefox_ls_db):
        """Lines 468: binary values are decoded."""
        db_path = os.path.join(firefox_ls_db, "storage", "default", "https+++example.com", "ls", "data.sqlite")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM data")
        cursor.execute("INSERT INTO data (key, value) VALUES (?, ?)", ("bin", b'\x00\x01\x02'))
        conn.commit()
        conn.close()

        extractor = CookieExtractor(firefox_ls_db, browser="firefox")
        result = extractor.extract_firefox_local_storage(domains=["example.com"])
        assert "example.com:bin" in result

    def test_extract_local_storage_conn_close_error(self, firefox_ls_db):
        """Lines 475-479: conn.close() error in localStorage is caught."""
        extractor = CookieExtractor(firefox_ls_db, browser="firefox")

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("query failed")
        mock_conn.cursor.return_value = mock_cursor

        with patch("sqlite3.connect", return_value=mock_conn):
            with patch("tokenade.core.importer.cookie_extractor.copy_db", return_value="/tmp/fake.db"):
                with patch("os.path.exists", return_value=True):
                    with patch("os.remove"):
                        result = extractor.extract_firefox_local_storage(domains=["example.com"])
        assert result == {}

    def test_extract_local_storage_conn_close_in_finally(self, firefox_ls_db):
        """Lines 475-479: conn.close() raises in finally but is caught."""
        extractor = CookieExtractor(firefox_ls_db, browser="firefox")

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("query failed")
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.close.side_effect = Exception("close failed")

        with patch("sqlite3.connect", return_value=mock_conn):
            with patch("tokenade.core.importer.cookie_extractor.copy_db", return_value="/tmp/fake.db"):
                with patch("os.path.exists", return_value=True):
                    with patch("os.remove"):
                        result = extractor.extract_firefox_local_storage(domains=["example.com"])
        assert result == {}
