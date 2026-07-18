"""
Integration tests for Session Import/Export feature.

Tests the full donor → receiver workflow end-to-end.
"""

import os
import tempfile
from unittest.mock import MagicMock, patch


from tokenade.core.importer.cookie_extractor import SiteFilter
from tokenade.core.importer.session_packager import SessionPackager
from tokenade.core.importer.session_loader import SessionLoader


class TestExportLoadRoundtrip:
    """Test full export → load roundtrip."""

    def test_export_load_roundtrip(self):
        """Test full export → load roundtrip with validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Step 1: Create mock cookies (include all Google critical cookies)
            cookies = [
                {"name": "SID", "value": "abc123", "domain": ".google.com", "path": "/", "secure": True},
                {"name": "SSID", "value": "def456", "domain": ".google.com", "path": "/", "secure": True},
                {"name": "APISID", "value": "ghi789", "domain": ".google.com", "path": "/", "secure": True},
                {"name": "SAPISID", "value": "jkl012", "domain": ".google.com", "path": "/", "secure": True},
                {"name": "HSID", "value": "mno345", "domain": ".google.com", "path": "/", "secure": True},
                {"name": "__Secure-1PSID", "value": "pqr678", "domain": ".google.com", "path": "/", "secure": True},
                {"name": "__Secure-3PSID", "value": "stu901", "domain": ".google.com", "path": "/", "secure": True},
                {"name": "__Secure-1PAPISID", "value": "vwx234", "domain": ".google.com", "path": "/", "secure": True},
                {"name": "__Secure-3PAPISID", "value": "yza567", "domain": ".google.com", "path": "/", "secure": True},
                {"name": "OSID", "value": "bcd890", "domain": ".google.com", "path": "/", "secure": True},
                {"name": "__Secure-OSID", "value": "efg123", "domain": ".google.com", "path": "/", "secure": True},
                {"name": "__Host-GAPS", "value": "hij456", "domain": ".google.com", "path": "/", "secure": True},
                {"name": "COMPASS", "value": "klm789", "domain": ".google.com", "path": "/", "secure": True},
                {"name": "NID", "value": "nop012", "domain": ".google.com", "path": "/", "secure": True},
            ]

            # Step 2: Package (export)
            packager = SessionPackager()
            package = packager.package(
                cookies=cookies,
                browser="chrome",
                profile="Default",
            )

            tokenade_path = os.path.join(tmpdir, "google_session.tokenade")
            packager.save(package, tokenade_path)

            # Step 3: Load
            mock_browser = MagicMock()
            mock_browser.get_cookies.return_value = cookies
            # Mock navigate/evaluate/query_selector for validation
            mock_browser.navigate.return_value = None
            mock_browser.evaluate.return_value = None
            mock_browser.query_selector.return_value = None  # No login indicator = logged in

            loader = SessionLoader()

            with patch.object(loader, "fp_manager"):
                with patch("tokenade.core.browser.manager.BrowserFactory.create", return_value=mock_browser):
                    with patch("tokenade.core.importer.site_configs.get_site_config", return_value=None):
                        result = loader.load(tokenade_path, validate=True)

            # Step 4: Verify
            assert result["success"] is True
            assert result["cookies_total"] == 14
            assert result["cookies_injected"] == 14
            assert result["validation"]["valid"] is True
            assert result["validation"]["auth_status"] == "logged_in"
            assert result["site_name"] == "google"

    def test_export_load_site_specific_only(self):
        """Test that only specified site cookies are exported."""
        with tempfile.TemporaryDirectory():
            # Mixed cookies from multiple sites
            cookies = [
                {"name": "SID", "value": "abc", "domain": ".google.com", "path": "/"},
                {"name": "SSID", "value": "de", "domain": ".google.com", "path": "/"},
                {"name": "user_session", "value": "xyz", "domain": ".github.com", "path": "/"},
                {"name": "random", "value": "x", "domain": "example.com", "path": "/"},
            ]

            # Filter for Google only
            site_filter = SiteFilter(["google"])
            google_cookies = site_filter.filter_cookies(cookies)

            assert len(google_cookies) == 2
            assert all(c["domain"] == ".google.com" for c in google_cookies)

            # Package and verify
            packager = SessionPackager()
            package = packager.package(google_cookies)
            assert package["site_name"] == "google"
            assert len(package["cookies"]) == 2

    def test_load_with_fingerprint_spoofing(self):
        """Test load with fingerprint matching and stealth."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cookies = [
                {"name": "SID", "value": "abc", "domain": ".google.com", "path": "/"},
            ]

            fingerprint = {
                "user_agent": "Mozilla/5.0 (X11; Linux x86_64)",
                "screen_width": 1920,
                "screen_height": 1080,
                "platform": "Linux x86_64",
            }

            packager = SessionPackager()
            package = packager.package(cookies, fingerprint=fingerprint)

            tokenade_path = os.path.join(tmpdir, "test.tokenade")
            packager.save(package, tokenade_path)

            mock_browser = MagicMock()
            mock_browser.get_cookies.return_value = cookies
            mock_browser.navigate.return_value = None
            mock_browser.evaluate.return_value = None
            mock_browser.query_selector.return_value = None

            loader = SessionLoader()

            with patch.object(loader, "fp_manager"):
                with patch("tokenade.core.browser.manager.BrowserFactory.create", return_value=mock_browser):
                    with patch("tokenade.core.importer.site_configs.get_site_config", return_value=None):
                        with patch("tokenade.core.importer.session_loader.inject_stealth_script") as mock_inject:
                            result = loader.load(tokenade_path, validate=True)

            assert result["success"] is True
            mock_inject.assert_called_once()


class TestCLIRoundtrip:
    """Test CLI export and load commands together."""

    def test_export_load_cli_integration(self):
        """Test CLI export and load commands together."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a mock .tokenade file
            cookies = [
                {"name": "SID", "value": "abc", "domain": ".google.com", "path": "/"},
            ]
            packager = SessionPackager()
            package = packager.package(cookies, browser="chrome")
            tokenade_path = os.path.join(tmpdir, "google_session.tokenade")
            packager.save(package, tokenade_path)

            # Verify file exists and is valid
            assert os.path.exists(tokenade_path)

            loaded = packager.load(tokenade_path)
            assert loaded["version"] == "3.0"
            assert loaded["site_name"] == "google"
            assert len(loaded["cookies"]) == 1

            # Test load via SessionLoader
            mock_browser = MagicMock()
            mock_browser.get_cookies.return_value = cookies
            mock_browser.navigate.return_value = None
            mock_browser.evaluate.return_value = None
            mock_browser.query_selector.return_value = None

            loader = SessionLoader()
            with patch.object(loader, "fp_manager"):
                with patch("tokenade.core.browser.manager.BrowserFactory.create", return_value=mock_browser):
                    with patch("tokenade.core.importer.site_configs.get_site_config", return_value=None):
                        result = loader.load(tokenade_path, validate=True)

            assert result["success"] is True
            assert result["cookies_injected"] == 1


class TestSiteDetectionIntegration:
    """Test site detection across the full pipeline."""

    def test_google_detection_pipeline(self):
        """Test Google detection through full pipeline."""
        cookies = [
            {"name": "SID", "value": "abc", "domain": ".google.com"},
            {"name": "SSID", "value": "de", "domain": ".google.com"},
        ]

        packager = SessionPackager()
        site = packager.detect_site(cookies)
        assert site == "google"

        package = packager.package(cookies)
        assert package["site_name"] == "google"
        assert package["auth_status"] == "logged_in"

    def test_github_detection_pipeline(self):
        """Test GitHub detection through full pipeline."""
        cookies = [
            {"name": "user_session", "value": "xyz", "domain": ".github.com"},
        ]

        packager = SessionPackager()
        site = packager.detect_site(cookies)
        assert site == "github"

        package = packager.package(cookies)
        assert package["site_name"] == "github"
        assert package["auth_status"] == "logged_in"


class TestAuthStatusIntegration:
    """Test auth status inference across pipeline."""

    def test_logged_in_status_preserved(self):
        """Test logged_in status is preserved through export/load."""
        cookies = [
            {"name": "SID", "value": "abc", "domain": ".google.com"},
        ]

        packager = SessionPackager()
        package = packager.package(cookies)
        assert package["auth_status"] == "logged_in"

        # Save and reload
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.tokenade")
            packager.save(package, path)
            loaded = packager.load(path)
            assert loaded["auth_status"] == "logged_in"

    def test_logged_out_status_preserved(self):
        """Test logged_out status is preserved through export/load."""
        cookies = [
            {"name": "some_tracking", "value": "x", "domain": ".google.com"},
        ]

        packager = SessionPackager()
        package = packager.package(cookies)
        assert package["auth_status"] == "logged_out"


class TestFormatValidation:
    """Test .tokenade format validation."""

    def test_valid_format(self):
        """Test valid .tokenade format passes validation."""
        packager = SessionPackager()
        package = packager.package([
            {"name": "SID", "value": "abc", "domain": ".google.com"},
        ])
        assert packager.validate_format(package) is True

    def test_invalid_format_missing_version(self):
        """Test invalid format fails validation."""
        packager = SessionPackager()
        package = {
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [],
        }
        assert packager.validate_format(package) is False

    def test_file_format_structure(self):
        """Test .tokenade file structure matches spec."""
        packager = SessionPackager()
        package = packager.package(
            [{"name": "SID", "value": "abc", "domain": ".google.com"}],
            browser="chrome",
            profile="Default",
            fingerprint={"user_agent": "test"},
        )

        # Check all required fields per spec
        assert "version" in package
        assert "created_at" in package
        assert "source_device" in package
        assert "site_name" in package
        assert "auth_status" in package
        assert "cookies" in package
        assert "tokens" in package
        assert "fingerprint" in package
        assert "metadata" in package

        # Check source_device fields
        source = package["source_device"]
        assert "browser" in source
        assert "profile" in source
        assert "platform" in source
        assert "hostname" in source

        # Check metadata fields
        meta = package["metadata"]
        assert "extraction_method" in meta
        assert "cookie_count" in meta
        assert "critical_cookie_count" in meta
