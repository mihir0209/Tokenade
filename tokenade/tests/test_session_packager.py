"""Tests for session packager."""

import pytest
from tokenade.core.importer.session_packager import SessionPackager, AuthStatus


class TestSessionPackager:
    @pytest.fixture
    def packager(self):
        return SessionPackager()

    def test_package_cookies(self, packager):
        cookies = [
            {"name": "session", "value": "abc", "domain": ".example.com", "path": "/"},
            {"name": "lang", "value": "en", "domain": ".example.com", "path": "/"},
        ]
        package = packager.package(
            cookies=cookies,
            browser="firefox",
            profile="default",
        )
        assert package["version"] == "3.1"
        assert len(package["cookies"]) == 2
        assert package["source_device"]["browser"] == "firefox"

    def test_package_with_local_storage(self, packager):
        cookies = [{"name": "session", "value": "abc", "domain": ".example.com", "path": "/"}]
        ls = {"user": "alice", "theme": "dark"}
        package = packager.package(
            cookies=cookies,
            browser="chrome",
            profile="default",
            local_storage=ls,
        )
        assert package["storage"]["local"]["https://example.com"] == ls

    def test_package_merges_site_handler_metadata(self, packager):
        cookies = [{"name": "session", "value": "abc", "domain": ".example.com", "path": "/"}]
        package = packager.package(
            cookies=cookies,
            metadata={
                "extraction_method": "site_handler",
                "site_handler": {
                    "plugin_name": "example-handler",
                    "plugin_version": "1.2.3",
                    "storage_origins": ["https://example.com"],
                },
            },
        )

        assert package["metadata"]["extraction_method"] == "site_handler"
        assert package["metadata"]["cookie_count"] == 1
        assert package["metadata"]["site_handler"]["plugin_name"] == "example-handler"
        assert package["metadata"]["site_handler"]["plugin_version"] == "1.2.3"
        assert package["metadata"]["site_handler"]["storage_origins"] == ["https://example.com"]

    def test_infer_auth_status_known_site(self, packager):
        # GitHub with critical cookie
        cookies = [
            {"name": "user_session", "value": "abc", "domain": ".github.com", "path": "/"},
        ]
        status = packager.infer_auth_status(cookies, "github")
        assert status == AuthStatus.LOGGED_IN

    def test_infer_auth_status_known_site_expired(self, packager):
        # GitHub without critical cookie
        cookies = [
            {"name": "_octo", "value": "abc", "domain": ".github.com", "path": "/"},
        ]
        status = packager.infer_auth_status(cookies, "github")
        assert status == AuthStatus.LOGGED_OUT

    def test_infer_auth_status_unknown_site(self, packager):
        cookies = [
            {"name": "session_token", "value": "abc", "domain": ".example.com",
             "path": "/", "secure": True, "httpOnly": True},
        ]
        status = packager.infer_auth_status(cookies, "example")
        assert status in (AuthStatus.LOGGED_IN, AuthStatus.UNKNOWN)

    def test_infer_auth_status_empty(self, packager):
        status = packager.infer_auth_status([])
        assert status == AuthStatus.LOGGED_OUT

    def test_infer_auth_status_analytics_only(self, packager):
        # Only analytics cookies should not be "logged in"
        cookies = [
            {"name": "_ga", "value": "abc", "domain": ".example.com", "path": "/",
             "secure": True, "httpOnly": True},
            {"name": "_gid", "value": "de", "domain": ".example.com", "path": "/",
             "secure": True, "httpOnly": True},
        ]
        status = packager.infer_auth_status(cookies, "example")
        assert status != AuthStatus.LOGGED_IN

    def test_save_and_load(self, packager, tmp_path):
        cookies = [
            {"name": "session", "value": "abc", "domain": ".example.com", "path": "/"},
        ]
        package = packager.package(cookies=cookies, browser="chrome", profile="default")
        output = str(tmp_path / "test.tokenade")
        saved = packager.save(package, output)
        loaded = packager.load(saved)
        assert loaded["version"] == "3.1"
        assert len(loaded["cookies"]) == 1

    def test_validate_format_valid(self, packager):
        package = {
            "version": "2.0",
            "created_at": "2025-01-01T00:00:00Z",
            "site_name": "test",
            "auth_status": "unknown",
            "cookies": [],
        }
        assert packager.validate_format(package) is True

    def test_validate_format_missing_version(self, packager):
        package = {"created_at": "x", "site_name": "test", "auth_status": "unknown", "cookies": []}
        assert packager.validate_format(package) is False

    def test_validate_format_bad_version(self, packager):
        package = {"version": 123, "created_at": "x", "site_name": "test", "auth_status": "unknown", "cookies": []}
        # validate_format only checks field existence, not type
        assert packager.validate_format(package) is True
