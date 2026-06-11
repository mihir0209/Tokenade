"""
Tests for Session Loader

Phase 4 tests - must pass before proceeding to Phase 5.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from tokenade.core.browser.manager import BrowserFactory
from tokenade.core.importer.session_loader import SessionLoader


class TestSessionLoaderFileOperations:
    """Test file loading operations."""

    def test_load_file_success(self):
        """Test loading a valid .tokenade file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = SessionLoader()
            package = {
                "version": "2.0",
                "site_name": "google",
                "auth_status": "logged_in",
                "cookies": [
                    {"name": "SID", "value": "abc", "domain": ".google.com"},
                ],
            }
            path = os.path.join(tmpdir, "test.tokenade")
            with open(path, "w") as f:
                json.dump(package, f)

            loaded = loader.load_file(path)
            assert loaded["version"] == "2.0"
            assert loaded["site_name"] == "google"
            assert len(loaded["cookies"]) == 1

    def test_load_file_not_found(self):
        """Test error when file not found."""
        loader = SessionLoader()
        with pytest.raises(FileNotFoundError):
            loader.load_file("/nonexistent/file.tokenade")


class TestSessionLoaderCookieNormalization:
    """Test cookie normalization."""

    def test_normalize_basic_cookie(self):
        """Test normalizing a basic cookie."""
        loader = SessionLoader()
        cookie = {"name": "SID", "value": "abc", "domain": ".google.com"}
        normalized = loader._normalize_cookie(cookie)

        assert normalized["name"] == "SID"
        assert normalized["value"] == "abc"
        assert normalized["domain"] == ".google.com"
        assert normalized["path"] == "/"

    def test_normalize_full_cookie(self):
        """Test normalizing a cookie with all fields."""
        loader = SessionLoader()
        cookie = {
            "name": "SID",
            "value": "abc",
            "domain": ".google.com",
            "path": "/mail",
            "secure": True,
            "httpOnly": True,
            "expires": 1750000000,
            "sameSite": "Lax",
        }
        normalized = loader._normalize_cookie(cookie)

        assert normalized["secure"] is True
        assert normalized["httpOnly"] is True
        assert normalized["expires"] == 1750000000
        assert normalized["sameSite"] == "Lax"

    def test_normalize_no_domain(self):
        """Test normalizing cookie without domain."""
        loader = SessionLoader()
        cookie = {"name": "test", "value": "val"}
        normalized = loader._normalize_cookie(cookie)

        assert normalized["domain"] == ""
        assert normalized["path"] == "/"


class TestSessionLoaderInjectCookies:
    """Test cookie injection."""

    def test_inject_cookies_success(self):
        """Test successful cookie injection."""
        loader = SessionLoader()
        mock_browser = MagicMock()

        cookies = [
            {"name": "SID", "value": "abc", "domain": ".google.com"},
            {"name": "SSID", "value": "def", "domain": ".google.com"},
        ]
        count = loader.inject_cookies(mock_browser, cookies)

        assert count == 2
        assert mock_browser.add_cookies.call_count == 2

    def test_inject_cookies_invalid_skipped(self):
        """Test invalid cookies are skipped."""
        loader = SessionLoader()
        mock_browser = MagicMock()

        cookies = [
            {"name": "SID", "value": "abc", "domain": ".google.com"},
            {"value": "no_name"},  # invalid
            {"name": "SSID", "value": "def", "domain": ".google.com"},
        ]
        count = loader.inject_cookies(mock_browser, cookies)

        assert count == 2
        assert mock_browser.add_cookies.call_count == 2

    def test_inject_cookies_empty(self):
        """Test empty cookies list."""
        loader = SessionLoader()
        mock_browser = MagicMock()

        count = loader.inject_cookies(mock_browser, [])
        assert count == 0
        mock_browser.add_cookies.assert_not_called()

    def test_inject_cookies_browser_error(self):
        """Test graceful handling when browser throws error."""
        loader = SessionLoader()
        mock_browser = MagicMock()
        mock_browser.add_cookies.side_effect = Exception("Cookie rejected")

        cookies = [
            {"name": "SID", "value": "abc", "domain": ".google.com"},
            {"name": "SSID", "value": "def", "domain": ".google.com"},
        ]
        count = loader.inject_cookies(mock_browser, cookies)

        assert count == 0


class TestSessionLoaderApplyFingerprint:
    """Test fingerprint application."""

    def test_apply_fingerprint_success(self):
        """Test successful fingerprint application."""
        loader = SessionLoader()
        mock_browser = MagicMock()
        fingerprint = {
            "user_agent": "Mozilla/5.0",
            "screen_width": 1920,
            "screen_height": 1080,
        }

        with patch("tokenade.core.importer.session_loader.inject_stealth_script") as mock_inject:
            result = loader.apply_fingerprint(mock_browser, fingerprint, "maximum")
            assert result is True
            mock_inject.assert_called_once()

    def test_apply_fingerprint_none(self):
        """Test no fingerprint returns True."""
        loader = SessionLoader()
        mock_browser = MagicMock()

        result = loader.apply_fingerprint(mock_browser, None)
        assert result is True

    def test_apply_fingerprint_failure(self):
        """Test graceful handling when injection fails."""
        loader = SessionLoader()
        mock_browser = MagicMock()
        fingerprint = {"user_agent": "test"}

        with patch("tokenade.core.importer.session_loader.inject_stealth_script") as mock_inject:
            mock_inject.side_effect = Exception("Injection failed")
            result = loader.apply_fingerprint(mock_browser, fingerprint)
            assert result is False


class TestSessionLoaderValidateSession:
    """Test session validation."""

    def _make_config(self, name, critical_cookies=None):
        return {"name": name, "critical_cookies": critical_cookies or [], "domains": []}

    def test_validate_google_logged_in(self):
        """Test Google session validation - logged in."""
        loader = SessionLoader()
        mock_browser = MagicMock()
        mock_browser.get_cookies.return_value = [
            {"name": "SID", "value": "abc", "domain": ".google.com"},
            {"name": "SSID", "value": "def", "domain": ".google.com"},
        ]

        config = self._make_config("google", ["SID", "SSID"])
        result = loader.validate_session(mock_browser, config)
        assert result["valid"] is True
        assert result["auth_status"] == "logged_in"
        assert result["cookies_present"] == 2

    def test_validate_google_logged_out(self):
        """Test Google session validation - logged out."""
        loader = SessionLoader()
        mock_browser = MagicMock()
        mock_browser.get_cookies.return_value = [
            {"name": "some_tracking", "value": "x", "domain": ".google.com"},
        ]

        config = self._make_config("google", ["SID", "SSID"])
        result = loader.validate_session(mock_browser, config)
        assert result["valid"] is False
        assert result["auth_status"] == "logged_out"

    def test_validate_google_session_expired(self):
        """Test Google session validation - session expired."""
        loader = SessionLoader()
        mock_browser = MagicMock()
        mock_browser.get_cookies.return_value = [
            {"name": "SSID", "value": "def", "domain": ".google.com"},
        ]

        config = self._make_config("google", ["SID", "SSID"])
        result = loader.validate_session(mock_browser, config)
        assert result["valid"] is False
        assert result["auth_status"] == "session_expired"

    def test_validate_unknown_site(self):
        """Test validation for unknown site."""
        loader = SessionLoader()
        mock_browser = MagicMock()
        mock_browser.get_cookies.return_value = [
            {"name": "random", "value": "x"},
        ]

        config = self._make_config("unknown_site")
        result = loader.validate_session(mock_browser, config)
        assert result["valid"] is True  # Any cookies present = valid
        assert result["auth_status"] == "logged_in"

    def test_validate_no_cookies(self):
        """Test validation with no cookies."""
        loader = SessionLoader()
        mock_browser = MagicMock()
        mock_browser.get_cookies.return_value = []

        config = self._make_config("google", ["SID"])
        result = loader.validate_session(mock_browser, config)
        assert result["valid"] is False
        assert result["auth_status"] == "logged_out"

    def test_validate_browser_error(self):
        """Test validation when browser throws error."""
        loader = SessionLoader()
        mock_browser = MagicMock()
        mock_browser.get_cookies.side_effect = Exception("Browser closed")

        config = self._make_config("google")
        result = loader.validate_session(mock_browser, config)
        assert result["valid"] is False
        assert "error" in result


class TestSessionLoaderLoad:
    """Test complete load workflow."""

    def test_load_success(self):
        """Test successful load workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = SessionLoader()
            package = {
                "version": "2.0",
                "site_name": "google",
                "auth_status": "logged_in",
                "cookies": [
                    {"name": "SID", "value": "abc", "domain": ".google.com"},
                ],
            }
            path = os.path.join(tmpdir, "test.tokenade")
            with open(path, "w") as f:
                json.dump(package, f)

            mock_browser = MagicMock()
            mock_browser.get_cookies.return_value = [
                {"name": "SID", "value": "abc", "domain": ".google.com"},
            ]

            with patch.object(loader, "fp_manager") as mock_fp_manager:
                with patch.object(BrowserFactory, "create", return_value=mock_browser):
                    result = loader.load(path, validate=True)

            assert result["success"] is True
            assert result["cookies_total"] == 1
            assert result["cookies_injected"] == 1
            assert result["validation"]["valid"] is True

    def test_load_no_validate(self):
        """Test load without validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = SessionLoader()
            package = {
                "version": "2.0",
                "site_name": "google",
                "cookies": [
                    {"name": "SID", "value": "abc", "domain": ".google.com"},
                ],
            }
            path = os.path.join(tmpdir, "test.tokenade")
            with open(path, "w") as f:
                json.dump(package, f)

            mock_browser = MagicMock()

            with patch.object(BrowserFactory, "create", return_value=mock_browser):
                result = loader.load(path, validate=False)

            assert result["success"] is True
            assert result["validation"] == {}

    def test_load_with_target_fingerprint(self):
        """Test load with target fingerprint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = SessionLoader()
            package = {
                "version": "2.0",
                "site_name": "google",
                "cookies": [
                    {"name": "SID", "value": "abc", "domain": ".google.com"},
                ],
            }
            path = os.path.join(tmpdir, "test.tokenade")
            with open(path, "w") as f:
                json.dump(package, f)

            mock_browser = MagicMock()
            mock_browser.get_cookies.return_value = [
                {"name": "SID", "value": "abc", "domain": ".google.com"},
            ]

            mock_fp = MagicMock()
            mock_fp.to_dict.return_value = {"user_agent": "test_ua"}

            with patch.object(loader.fp_manager, "load", return_value=mock_fp):
                with patch.object(BrowserFactory, "create", return_value=mock_browser):
                    result = loader.load(path, target_fp_name="my_vps", validate=True)

            assert result["success"] is True

    def test_load_file_not_found(self):
        """Test load with missing file."""
        loader = SessionLoader()
        result = loader.load("/nonexistent.tokenade")

        assert result["success"] is False
        assert "No such file" in result["error"] or "not found" in result["error"].lower()

    def test_load_browser_launch_failure(self):
        """Test load when browser launch fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = SessionLoader()
            package = {
                "version": "2.0",
                "site_name": "google",
                "cookies": [],
            }
            path = os.path.join(tmpdir, "test.tokenade")
            with open(path, "w") as f:
                json.dump(package, f)

            with patch.object(BrowserFactory, "create", side_effect=Exception("Launch failed")):
                result = loader.load(path)

            assert result["success"] is False
            assert "Launch failed" in result["error"]

    def test_load_with_profile_dir(self):
        """Test load with custom profile directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = SessionLoader()
            package = {
                "version": "2.0",
                "site_name": "google",
                "cookies": [
                    {"name": "SID", "value": "abc", "domain": ".google.com"},
                ],
            }
            path = os.path.join(tmpdir, "test.tokenade")
            with open(path, "w") as f:
                json.dump(package, f)

            mock_browser = MagicMock()

            with patch.object(BrowserFactory, "create", return_value=mock_browser) as mock_create:
                result = loader.load(path, profile_dir="browser_data/loaded", validate=False)

            assert result["success"] is True
            # Verify profile_dir was passed to BrowserConfig
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs.get("user_data_dir") == "browser_data/loaded"


class TestSessionLoaderClose:
    """Test cleanup."""

    def test_close_browser(self):
        """Test closing browser."""
        loader = SessionLoader()
        mock_browser = MagicMock()
        loader._browser = mock_browser

        loader.close()
        mock_browser.close.assert_called_once()
        assert loader._browser is None

    def test_close_no_browser(self):
        """Test close when no browser active."""
        loader = SessionLoader()
        loader.close()  # Should not raise

    def test_close_browser_error(self):
        """Test close when browser close fails."""
        loader = SessionLoader()
        mock_browser = MagicMock()
        mock_browser.close.side_effect = Exception("Already closed")
        loader._browser = mock_browser

        loader.close()  # Should not raise


class TestSessionLoaderLastResult:
    """Test last result tracking."""

    def test_get_last_result(self):
        """Test getting last result."""
        loader = SessionLoader()
        assert loader.get_last_result() is None

        loader._last_result = {"success": True}
        assert loader.get_last_result()["success"] is True
