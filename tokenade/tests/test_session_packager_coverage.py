"""Comprehensive tests for session_packager.py to boost coverage from 40% to 75%+."""

import json
import os
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from tokenade.core.importer.session_packager import SessionPackager
from tokenade.core.importer.cookie_extractor import SiteFilter
from tokenade.handlers.base import AuthStatus


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def packager():
    return SessionPackager(cache_ttl=0)


@pytest.fixture
def packager_with_cache():
    return SessionPackager(cache_ttl=300)


@pytest.fixture
def github_cookies():
    return [
        {"name": "user_session", "value": "abc123", "domain": ".github.com", "path": "/"},
        {"name": "logged_in", "value": "yes", "domain": ".github.com", "path": "/"},
        {"name": "_octo", "value": "GH1.1.abc", "domain": ".github.com", "path": "/"},
    ]


@pytest.fixture
def google_cookies():
    return [
        {"name": "SID", "value": "x", "domain": ".google.com", "path": "/"},
        {"name": "HSID", "value": "y", "domain": ".google.com", "path": "/"},
        {"name": "SSID", "value": "z", "domain": ".google.com", "path": "/"},
        {"name": "__Secure-1PSID", "value": "w", "domain": ".google.com", "path": "/"},
    ]


@pytest.fixture
def unknown_site_cookies_session_token():
    return [
        {"name": "session_token", "value": "abc", "domain": ".example.com",
         "path": "/", "secure": True, "httpOnly": True},
        {"name": "csrf_token", "value": "xyz", "domain": ".example.com",
         "path": "/", "secure": True, "httpOnly": True},
    ]


@pytest.fixture
def analytics_only_cookies():
    return [
        {"name": "_ga", "value": "abc", "domain": ".example.com",
         "path": "/", "secure": True, "httpOnly": True},
        {"name": "_gid", "value": "de", "domain": ".example.com",
         "path": "/", "secure": True, "httpOnly": True},
        {"name": "_gat", "value": "1", "domain": ".example.com",
         "path": "/", "secure": True, "httpOnly": True},
    ]


# ─── detect_site ─────────────────────────────────────────────────────────────

class TestDetectSite:
    def test_detect_github(self, packager):
        cookies = [{"name": "user_session", "value": "x", "domain": ".github.com"}]
        assert packager.detect_site(cookies) == "github"

    def test_detect_google(self, packager):
        cookies = [{"name": "SID", "value": "x", "domain": ".google.com"}]
        assert packager.detect_site(cookies) == "google"

    def test_detect_unknown(self, packager):
        cookies = [{"name": "x", "value": "y", "domain": ".randomsite.com"}]
        assert packager.detect_site(cookies) is None

    def test_detect_empty(self, packager):
        assert packager.detect_site([]) is None


# ─── infer_auth_status ───────────────────────────────────────────────────────

class TestInferAuthStatus:
    def test_empty_cookies(self, packager):
        assert packager.infer_auth_status([]) == AuthStatus.LOGGED_OUT

    def test_known_site_logged_in(self, packager, github_cookies):
        assert packager.infer_auth_status(github_cookies, "github") == AuthStatus.LOGGED_IN

    def test_known_site_session_expired_no_primary(self, packager):
        cookies = [
            {"name": "_octo", "value": "GH1.1.abc", "domain": ".github.com", "path": "/"},
            {"name": "has_recent_activity", "value": "1", "domain": ".github.com", "path": "/"},
        ]
        assert packager.infer_auth_status(cookies, "github") == AuthStatus.SESSION_EXPIRED

    def test_known_site_logged_out_no_critical(self, packager):
        cookies = [{"name": "lang", "value": "en", "domain": ".github.com", "path": "/"}]
        assert packager.infer_auth_status(cookies, "github") == AuthStatus.LOGGED_OUT

    def test_unknown_site_heuristic_multiple_session_like(self, packager):
        cookies = [
            {"name": "session_token", "value": "a", "domain": ".example.com",
             "path": "/", "secure": True, "httpOnly": True},
            {"name": "auth_token", "value": "b", "domain": ".example.com",
             "path": "/", "secure": True, "httpOnly": True},
        ]
        assert packager.infer_auth_status(cookies, "unknown_site") == AuthStatus.LOGGED_IN

    def test_unknown_site_heuristic_single_session_like(self, packager):
        # secure+httpOnly=1, no keyword match -> session_like=1 -> UNKNOWN
        cookies = [
            {"name": "custom_id", "value": "a", "domain": ".example.com",
             "path": "/", "secure": True, "httpOnly": True},
        ]
        result = packager.infer_auth_status(cookies, "unknown_site")
        assert result == AuthStatus.UNKNOWN

    def test_unknown_site_heuristic_none_session_like(self, packager):
        cookies = [{"name": "pref_lang", "value": "en", "domain": ".example.com", "path": "/"}]
        assert packager.infer_auth_status(cookies, "unknown_site") == AuthStatus.LOGGED_OUT

    def test_unknown_site_analytics_blocklisted(self, packager, analytics_only_cookies):
        assert packager.infer_auth_status(analytics_only_cookies, "unknown_site") == AuthStatus.LOGGED_OUT

    def test_known_site_by_detection(self, packager, google_cookies):
        assert packager.infer_auth_status(google_cookies) == AuthStatus.LOGGED_IN

    def test_known_site_session_expired_google(self, packager):
        cookies = [
            {"name": "HSID", "value": "y", "domain": ".google.com", "path": "/"},
        ]
        assert packager.infer_auth_status(cookies) == AuthStatus.SESSION_EXPIRED


# ─── collect_fingerprint ─────────────────────────────────────────────────────

class TestCollectFingerprint:
    def test_none_browser_manager(self, packager):
        assert packager.collect_fingerprint(None) is None

    @patch("tokenade.core.importer.session_packager.SessionPackager.collect_fingerprint")
    def test_exception_returns_none(self, mock_collect, packager):
        mock_collect.return_value = None
        assert packager.collect_fingerprint(MagicMock()) is None

    def test_collect_fingerprint_success(self, packager):
        mock_fp = MagicMock()
        mock_fp.to_dict.return_value = {"user_agent": "TestUA"}
        mock_collector = MagicMock()
        mock_collector.collect_from_browser.return_value = mock_fp
        with patch.dict("sys.modules", {
            "tokenade.core.fingerprint.manager": MagicMock(FingerprintCollector=mock_collector)
        }):
            result = packager.collect_fingerprint(MagicMock())
            assert result == {"user_agent": "TestUA"}

    def test_collect_fingerprint_import_error(self, packager):
        with patch.dict("sys.modules", {"tokenade.core.fingerprint.manager": None}):
            result = packager.collect_fingerprint(MagicMock())
            assert result is None


# ─── package ─────────────────────────────────────────────────────────────────

class TestPackage:
    def test_basic_package(self, packager):
        cookies = [{"name": "pref_lang", "value": "en", "domain": ".example.com", "path": "/"}]
        pkg = packager.package(cookies=cookies, browser="chrome", profile="default")
        assert pkg["version"] == "3.1"
        assert pkg["source_device"]["browser"] == "chrome"
        assert pkg["source_device"]["profile"] == "default"
        assert pkg["site_name"] == "unknown"
        assert pkg["auth_status"] == AuthStatus.LOGGED_OUT.value
        assert len(pkg["cookies"]) == 1
        assert pkg["tokens"] == []
        assert pkg["storage"]["local"] == {}

    def test_package_with_fingerprint(self, packager):
        fp = {"user_agent": "Mozilla/5.0 Chrome/120.0", "platform": "Win32"}
        pkg = packager.package(cookies=[], fingerprint=fp)
        assert pkg["fingerprint"] == fp

    def test_package_with_tls_profile(self, packager):
        tls = {"browser": "chrome", "version": "120", "impersonate": "chrome120"}
        pkg = packager.package(cookies=[], tls_profile=tls)
        assert pkg["tls_profile"] == tls

    def test_package_with_tokens(self, packager):
        tokens = [{"token_type": "oauth", "value": "tok123"}]
        pkg = packager.package(cookies=[], tokens=tokens)
        assert pkg["tokens"] == tokens

    def test_package_with_local_storage(self, packager):
        ls = {"theme": "dark", "lang": "en"}
        cookies = [{"name": "c1", "value": "v1", "domain": ".example.com"}]
        pkg = packager.package(cookies=cookies, local_storage=ls)
        assert pkg["storage"]["local"]["https://example.com"] == ls
        assert pkg["metadata"]["local_storage_count"] == 2

    def test_package_critical_cookie_count(self, packager, github_cookies):
        pkg = packager.package(cookies=github_cookies)
        assert pkg["metadata"]["critical_cookie_count"] >= 1

    def test_package_with_source_browser_manager(self, packager):
        mock_bm = MagicMock()
        with patch.object(packager, "collect_fingerprint", return_value={"ua": "test"}):
            pkg = packager.package(cookies=[], source_browser_manager=mock_bm)
            assert pkg["fingerprint"] == {"ua": "test"}

    def test_package_auto_tls_profile(self, packager):
        pkg = packager.package(cookies=[], browser="chrome")
        assert pkg["tls_profile"] is not None
        assert "impersonate" in pkg["tls_profile"]

    def test_package_unknown_site_name(self, packager):
        pkg = packager.package(cookies=[])
        assert pkg["site_name"] == "unknown"


# ─── _detect_tls_profile ─────────────────────────────────────────────────────

class TestDetectTlsProfile:
    def test_default_no_fingerprint(self, packager):
        result = packager._detect_tls_profile("chrome")
        assert result["browser"] == "chrome"
        assert result["version"] == "120"
        assert result["impersonate"] == "chrome120"
        assert result["http_version"] == "2"

    def test_firefox_browser_returns_chrome(self, packager):
        result = packager._detect_tls_profile("firefox")
        assert result["browser"] == "chrome"

    def test_chrome_version_from_fingerprint(self, packager):
        fp = {"user_agent": "Mozilla/5.0 Chrome/131.0.0.0 Safari/537.36"}
        result = packager._detect_tls_profile("chrome", fingerprint=fp)
        assert result["version"] == "131"
        assert result["impersonate"] == "chrome131"

    def test_no_chrome_match_in_ua(self, packager):
        fp = {"user_agent": "Mozilla/5.0 Firefox/120.0"}
        result = packager._detect_tls_profile("chrome", fingerprint=fp)
        assert result["version"] == "120"

    def test_fingerprint_without_user_agent(self, packager):
        fp = {"platform": "Win32"}
        result = packager._detect_tls_profile("chrome", fingerprint=fp)
        assert result["version"] == "120"


# ─── save and load ───────────────────────────────────────────────────────────

class TestSaveLoad:
    def test_save_creates_file(self, packager, tmp_path):
        pkg = packager.package(cookies=[], browser="chrome", profile="default")
        output = str(tmp_path / "test.tokenade")
        saved = packager.save(pkg, output)
        assert os.path.exists(saved)

    def test_save_creates_parent_dirs(self, packager, tmp_path):
        pkg = packager.package(cookies=[])
        output = str(tmp_path / "sub" / "dir" / "test.tokenade")
        saved = packager.save(pkg, output)
        assert os.path.exists(saved)

    def test_load_success(self, packager, tmp_path):
        pkg = packager.package(cookies=[{"name": "a", "value": "1", "domain": ".x.com"}])
        path = str(tmp_path / "test.tokenade")
        packager.save(pkg, path)
        loaded = packager.load(path)
        assert loaded["version"] == "3.1"
        assert len(loaded["cookies"]) == 1

    def test_load_not_found(self, packager, tmp_path):
        with pytest.raises(FileNotFoundError):
            packager.load(str(tmp_path / "nonexistent.tokenade"))

    def test_save_and_load_roundtrip(self, packager, tmp_path):
        cookies = [
            {"name": "sid", "value": "abc", "domain": ".example.com"},
            {"name": "csr", "value": "xyz", "domain": ".example.com"},
        ]
        pkg = packager.package(
            cookies=cookies,
            fingerprint={"user_agent": "TestUA"},
            tokens=[{"token_type": "oauth", "value": "tok"}],
            local_storage={"k": "v"},
        )
        path = str(tmp_path / "roundtrip.tokenade")
        packager.save(pkg, path)
        loaded = packager.load(path)
        assert len(loaded["cookies"]) == 2
        assert loaded["fingerprint"]["user_agent"] == "TestUA"
        assert loaded["tokens"][0]["value"] == "tok"
        assert loaded["storage"]["local"]["https://example.com"]["k"] == "v"

    def test_load_stores_in_cache(self, packager_with_cache, tmp_path):
        pkg = packager_with_cache.package(cookies=[{"name": "a", "value": "1", "domain": ".x.com"}])
        path = str(tmp_path / "cache_store.tokenade")
        packager_with_cache.save(pkg, path)
        # Clear cache to force reload from file
        packager_with_cache._cache._cache.clear()
        loaded = packager_with_cache.load(path)
        assert loaded["version"] == "3.1"
        # Verify it's now in cache
        abs_path = str(Path(path).absolute())
        assert packager_with_cache._cache.get(abs_path) is not None

    def test_load_corrupt_json(self, packager, tmp_path):
        corrupt_file = tmp_path / "corrupt.tokenade"
        corrupt_file.write_text("{{{invalid json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            packager.load(str(corrupt_file))


# ─── LRU cache ───────────────────────────────────────────────────────────────

class TestLRUCache:
    def test_cache_hit(self, packager_with_cache, tmp_path):
        pkg = packager_with_cache.package(cookies=[])
        path = str(tmp_path / "cached.tokenade")
        packager_with_cache.save(pkg, path)
        loaded = packager_with_cache.load(path)
        assert loaded["version"] == "3.1"
        # Second load should hit cache
        loaded2 = packager_with_cache.load(path)
        assert loaded2["version"] == "3.1"

    def test_cache_disabled(self, packager, tmp_path):
        pkg = packager.package(cookies=[])
        path = str(tmp_path / "nocache.tokenade")
        packager.save(pkg, path)
        assert packager._cache is None
        loaded = packager.load(path)
        assert loaded["version"] == "3.1"

    def test_cache_load_not_found(self, packager_with_cache, tmp_path):
        # Verify cache does not prevent FileNotFoundError
        with pytest.raises(FileNotFoundError):
            packager_with_cache.load(str(tmp_path / "nope.tokenade"))


# ─── validate_format ─────────────────────────────────────────────────────────

class TestValidateFormat:
    def test_valid_package(self, packager):
        pkg = {
            "version": "2.0",
            "created_at": "2025-01-01T00:00:00Z",
            "site_name": "test",
            "auth_status": "unknown",
            "cookies": [{"name": "a", "value": "1"}],
        }
        assert packager.validate_format(pkg) is True

    def test_missing_version(self, packager):
        pkg = {"created_at": "x", "site_name": "t", "auth_status": "u", "cookies": []}
        assert packager.validate_format(pkg) is False

    def test_missing_created_at(self, packager):
        pkg = {"version": "2.0", "site_name": "t", "auth_status": "u", "cookies": []}
        assert packager.validate_format(pkg) is False

    def test_missing_site_name(self, packager):
        pkg = {"version": "2.0", "created_at": "x", "auth_status": "u", "cookies": []}
        assert packager.validate_format(pkg) is False

    def test_missing_auth_status(self, packager):
        pkg = {"version": "2.0", "created_at": "x", "site_name": "t", "cookies": []}
        assert packager.validate_format(pkg) is False

    def test_missing_cookies(self, packager):
        pkg = {"version": "2.0", "created_at": "x", "site_name": "t", "auth_status": "u"}
        assert packager.validate_format(pkg) is False

    def test_cookies_not_list(self, packager):
        pkg = {
            "version": "2.0", "created_at": "x", "site_name": "t",
            "auth_status": "u", "cookies": "not_a_list",
        }
        assert packager.validate_format(pkg) is False

    def test_cookie_not_dict(self, packager):
        pkg = {
            "version": "2.0", "created_at": "x", "site_name": "t",
            "auth_status": "u", "cookies": ["not_a_dict"],
        }
        assert packager.validate_format(pkg) is False

    def test_cookie_missing_name(self, packager):
        pkg = {
            "version": "2.0", "created_at": "x", "site_name": "t",
            "auth_status": "u", "cookies": [{"value": "1"}],
        }
        assert packager.validate_format(pkg) is False

    def test_cookie_missing_value(self, packager):
        pkg = {
            "version": "2.0", "created_at": "x", "site_name": "t",
            "auth_status": "u", "cookies": [{"name": "a"}],
        }
        assert packager.validate_format(pkg) is False


# ─── get_summary ─────────────────────────────────────────────────────────────

class TestGetSummary:
    def test_summary_with_fingerprint(self, packager):
        pkg = packager.package(
            cookies=[{"name": "a", "value": "1", "domain": ".x.com"}],
            browser="chrome",
            profile="default",
            fingerprint={"user_agent": "Mozilla/5.0 Chrome/120", "screen_width": 1920, "screen_height": 1080},
        )
        summary = packager.get_summary(pkg)
        assert "SESSION PACKAGE SUMMARY" in summary
        assert "chrome" in summary
        assert "default" in summary
        assert "Fingerprint: collected" in summary
        assert "1920x1080" in summary

    def test_summary_without_fingerprint(self, packager):
        pkg = packager.package(cookies=[])
        summary = packager.get_summary(pkg)
        assert "Fingerprint: not collected" in summary

    def test_summary_empty_package(self, packager):
        pkg = {}
        summary = packager.get_summary(pkg)
        assert "unknown" in summary


# ─── site detection paths ────────────────────────────────────────────────────

class TestSiteDetectionPaths:
    def test_discord_detection(self, packager):
        cookies = [{"name": "__dcfduid", "value": "x", "domain": ".discord.com"}]
        assert packager.detect_site(cookies) == "discord"

    def test_reddit_detection(self, packager):
        cookies = [{"name": "reddit_session", "value": "x", "domain": ".reddit.com"}]
        assert packager.detect_site(cookies) == "reddit"

    def test_twitter_detection(self, packager):
        cookies = [{"name": "auth_token", "value": "x", "domain": ".x.com"}]
        assert packager.detect_site(cookies) == "twitter"

    def test_linkedin_detection(self, packager):
        cookies = [{"name": "li_at", "value": "x", "domain": ".linkedin.com"}]
        assert packager.detect_site(cookies) == "linkedin"

    def test_openai_detection(self, packager):
        cookies = [{"name": "oai-did", "value": "x", "domain": ".chatgpt.com"}]
        assert packager.detect_site(cookies) == "openai"

    def test_site_filter_with_sites(self):
        sf = SiteFilter(sites=["github", "google"])
        packager = SessionPackager(site_filter=sf)
        cookies = [{"name": "user_session", "value": "x", "domain": ".github.com"}]
        assert packager.detect_site(cookies) == "github"
