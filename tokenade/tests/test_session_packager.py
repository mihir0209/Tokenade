"""
Tests for Session Packager

Phase 3 tests - must pass before proceeding to Phase 4.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tokenade.core.importer.session_packager import SessionPackager
from tokenade.handlers.base import AuthStatus


class TestSessionPackagerSiteDetection:
    """Test site detection from cookies."""

    def test_detect_google_from_cookies(self):
        """Test Google site detection from critical cookies."""
        packager = SessionPackager()
        cookies = [
            {"name": "SID", "domain": ".google.com", "value": "abc"},
            {"name": "SSID", "domain": ".google.com", "value": "def"},
        ]
        assert packager.detect_site(cookies) == "google"

    def test_detect_github_from_cookies(self):
        """Test GitHub site detection from critical cookies."""
        packager = SessionPackager()
        cookies = [
            {"name": "user_session", "domain": ".github.com", "value": "xyz"},
        ]
        assert packager.detect_site(cookies) == "github"

    def test_detect_unknown_site(self):
        """Test unknown site detection."""
        packager = SessionPackager()
        cookies = [
            {"name": "random_cookie", "domain": "example.com", "value": "x"},
        ]
        assert packager.detect_site(cookies) is None

    def test_detect_empty_cookies(self):
        """Test detection with empty cookies."""
        packager = SessionPackager()
        assert packager.detect_site([]) is None


class TestSessionPackagerAuthStatus:
    """Test auth status inference."""

    def test_infer_google_logged_in(self):
        """Test Google logged_in inference."""
        packager = SessionPackager()
        cookies = [
            {"name": "SID", "domain": ".google.com", "value": "abc"},
            {"name": "SSID", "domain": ".google.com", "value": "def"},
        ]
        status = packager.infer_auth_status(cookies)
        assert status == AuthStatus.LOGGED_IN

    def test_infer_google_logged_out(self):
        """Test Google logged_out inference (no critical cookies)."""
        packager = SessionPackager()
        cookies = [
            {"name": "some_tracking", "domain": ".google.com", "value": "x"},
        ]
        status = packager.infer_auth_status(cookies)
        assert status == AuthStatus.LOGGED_OUT

    def test_infer_github_logged_in(self):
        """Test GitHub logged_in inference."""
        packager = SessionPackager()
        cookies = [
            {"name": "user_session", "domain": ".github.com", "value": "xyz"},
        ]
        status = packager.infer_auth_status(cookies)
        assert status == AuthStatus.LOGGED_IN

    def test_infer_empty_cookies(self):
        """Test empty cookies returns LOGGED_OUT."""
        packager = SessionPackager()
        status = packager.infer_auth_status([])
        assert status == AuthStatus.LOGGED_OUT

    def test_infer_unknown_site(self):
        """Test unknown site returns LOGGED_OUT (default for unrecognized sites)."""
        packager = SessionPackager()
        cookies = [
            {"name": "random", "domain": "example.com", "value": "x"},
        ]
        status = packager.infer_auth_status(cookies)
        assert status == AuthStatus.LOGGED_OUT

    def test_infer_session_expired(self):
        """Test session expired when primary cookie missing."""
        packager = SessionPackager()
        # SSID present but not SID (primary for Google)
        cookies = [
            {"name": "SSID", "domain": ".google.com", "value": "def"},
        ]
        status = packager.infer_auth_status(cookies, site_name="google")
        assert status == AuthStatus.SESSION_EXPIRED


class TestSessionPackagerPackage:
    """Test package creation."""

    def test_package_basic(self):
        """Test basic package creation."""
        packager = SessionPackager()
        cookies = [
            {"name": "SID", "domain": ".google.com", "value": "abc"},
        ]
        package = packager.package(cookies, browser="chrome", profile="Default")

        assert package["version"] == "2.0"
        assert package["site_name"] == "google"
        assert package["auth_status"] == "logged_in"
        assert len(package["cookies"]) == 1
        assert package["source_device"]["browser"] == "chrome"
        assert package["source_device"]["profile"] == "Default"
        assert "created_at" in package
        assert "hostname" in package["source_device"]

    def test_package_with_fingerprint(self):
        """Test package with fingerprint data."""
        packager = SessionPackager()
        cookies = [
            {"name": "SID", "domain": ".google.com", "value": "abc"},
        ]
        fingerprint = {
            "user_agent": "Mozilla/5.0 (X11; Linux x86_64)",
            "screen_width": 1920,
            "screen_height": 1080,
        }
        package = packager.package(cookies, fingerprint=fingerprint)

        assert package["fingerprint"] == fingerprint
        assert package["fingerprint"]["user_agent"] == "Mozilla/5.0 (X11; Linux x86_64)"

    def test_package_with_tokens(self):
        """Test package with tokens."""
        packager = SessionPackager()
        cookies = [
            {"name": "SID", "domain": ".google.com", "value": "abc"},
        ]
        tokens = [
            {"token_type": "access_token", "value": "token123", "domain": "labs.google.com"},
        ]
        package = packager.package(cookies, tokens=tokens)

        assert len(package["tokens"]) == 1
        assert package["tokens"][0]["value"] == "token123"

    def test_package_metadata(self):
        """Test package metadata."""
        packager = SessionPackager()
        cookies = [
            {"name": "SID", "domain": ".google.com", "value": "abc"},
            {"name": "SSID", "domain": ".google.com", "value": "def"},
        ]
        package = packager.package(cookies)

        meta = package["metadata"]
        assert meta["cookie_count"] == 2
        assert meta["critical_cookie_count"] == 2
        assert meta["extraction_method"] == "sqlite_direct"

    def test_package_unknown_site(self):
        """Test package with unknown site cookies."""
        packager = SessionPackager()
        cookies = [
            {"name": "random", "domain": "example.com", "value": "x"},
        ]
        package = packager.package(cookies)

        assert package["site_name"] == "unknown"
        assert package["auth_status"] == "logged_out"

    def test_package_auto_collect_fingerprint(self):
        """Test auto-collecting fingerprint from browser manager."""
        packager = SessionPackager()
        cookies = [
            {"name": "SID", "domain": ".google.com", "value": "abc"},
        ]

        mock_browser = MagicMock()
        mock_fp = MagicMock()
        mock_fp.to_dict.return_value = {"user_agent": "test_ua", "screen_width": 1920}

        with patch("tokenade.core.fingerprint.manager.FingerprintCollector") as MockCollector:
            MockCollector.collect_from_browser.return_value = mock_fp
            package = packager.package(cookies, source_browser_manager=mock_browser)

        assert package["fingerprint"]["user_agent"] == "test_ua"

    def test_package_fingerprint_collection_failure(self):
        """Test graceful handling when fingerprint collection fails."""
        packager = SessionPackager()
        cookies = [
            {"name": "SID", "domain": ".google.com", "value": "abc"},
        ]

        mock_browser = MagicMock()

        with patch("tokenade.core.fingerprint.manager.FingerprintCollector") as MockCollector:
            MockCollector.collect_from_browser.side_effect = Exception("Browser closed")
            package = packager.package(cookies, source_browser_manager=mock_browser)

        assert package["fingerprint"] is None


class TestSessionPackagerSaveLoad:
    """Test save and load operations."""

    def test_save_and_load(self):
        """Test saving and loading a .tokenade file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            packager = SessionPackager()
            cookies = [
                {"name": "SID", "domain": ".google.com", "value": "abc"},
            ]
            package = packager.package(cookies, browser="chrome")

            path = os.path.join(tmpdir, "test.tokenade")
            saved_path = packager.save(package, path)

            assert os.path.exists(saved_path)

            loaded = packager.load(saved_path)
            assert loaded["version"] == "2.0"
            assert loaded["site_name"] == "google"
            assert len(loaded["cookies"]) == 1

    def test_load_file_not_found(self):
        """Test error when file not found."""
        packager = SessionPackager()
        with pytest.raises(FileNotFoundError):
            packager.load("/nonexistent/file.tokenade")

    def test_save_creates_directories(self):
        """Test save creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            packager = SessionPackager()
            package = packager.package([])

            nested_path = os.path.join(tmpdir, "a", "b", "test.tokenade")
            packager.save(package, nested_path)

            assert os.path.exists(nested_path)


class TestSessionPackagerValidation:
    """Test format validation."""

    def test_validate_valid_package(self):
        """Test validation of valid package."""
        packager = SessionPackager()
        package = {
            "version": "2.0",
            "created_at": "2026-06-01T12:00:00Z",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [
                {"name": "SID", "value": "abc", "domain": ".google.com"},
            ],
        }
        assert packager.validate_format(package) is True

    def test_validate_missing_version(self):
        """Test validation fails when version missing."""
        packager = SessionPackager()
        package = {
            "created_at": "2026-06-01T12:00:00Z",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [],
        }
        assert packager.validate_format(package) is False

    def test_validate_missing_cookies(self):
        """Test validation fails when cookies missing."""
        packager = SessionPackager()
        package = {
            "version": "2.0",
            "created_at": "2026-06-01T12:00:00Z",
            "site_name": "google",
            "auth_status": "logged_in",
        }
        assert packager.validate_format(package) is False

    def test_validate_cookies_not_list(self):
        """Test validation fails when cookies is not a list."""
        packager = SessionPackager()
        package = {
            "version": "2.0",
            "created_at": "2026-06-01T12:00:00Z",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": "not_a_list",
        }
        assert packager.validate_format(package) is False

    def test_validate_cookie_missing_name(self):
        """Test validation fails when cookie missing name."""
        packager = SessionPackager()
        package = {
            "version": "2.0",
            "created_at": "2026-06-01T12:00:00Z",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [
                {"value": "abc"},  # missing name
            ],
        }
        assert packager.validate_format(package) is False

    def test_validate_cookie_not_dict(self):
        """Test validation fails when cookie is not a dict."""
        packager = SessionPackager()
        package = {
            "version": "2.0",
            "created_at": "2026-06-01T12:00:00Z",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": ["not_a_dict"],
        }
        assert packager.validate_format(package) is False


class TestSessionPackagerSummary:
    """Test summary generation."""

    def test_summary_basic(self):
        """Test basic summary generation."""
        packager = SessionPackager()
        package = packager.package(
            [{"name": "SID", "domain": ".google.com", "value": "abc"}],
            browser="chrome",
            profile="Default",
        )
        summary = packager.get_summary(package)

        assert "SESSION PACKAGE SUMMARY" in summary
        assert "google" in summary
        assert "chrome" in summary
        assert "Default" in summary
        assert "Cookies: 1" in summary

    def test_summary_with_fingerprint(self):
        """Test summary with fingerprint."""
        packager = SessionPackager()
        package = packager.package(
            [{"name": "SID", "domain": ".google.com", "value": "abc"}],
            fingerprint={
                "user_agent": "Mozilla/5.0 (X11; Linux x86_64)",
                "screen_width": 1920,
                "screen_height": 1080,
            },
        )
        summary = packager.get_summary(package)

        assert "Fingerprint: collected" in summary
        assert "1920x1080" in summary

    def test_summary_without_fingerprint(self):
        """Test summary without fingerprint."""
        packager = SessionPackager()
        package = packager.package(
            [{"name": "SID", "domain": ".google.com", "value": "abc"}],
        )
        summary = packager.get_summary(package)

        assert "Fingerprint: not collected" in summary
