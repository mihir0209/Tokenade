"""Tests for multi-account orchestration (Phase 31)."""
import json
import pytest
from pathlib import Path
from argparse import Namespace
from datetime import datetime, timezone, timedelta

from tokenade.cli.management import (
    cmd_accounts,
    _accounts_list,
    _accounts_status,
    _detect_url_from_cookies,
)


@pytest.fixture
def sessions_dir(tmp_path):
    """Create a temporary directory with multiple session files."""
    sessions = {
        "github.tokenade": {
            "version": "1.0",
            "site_name": "github",
            "auth_status": "logged_in",
            "source_device": {"browser": "brave"},
            "cookies": [
                {"name": "user_session", "value": "abc", "domain": ".github.com"},
                {"name": "logged_in", "value": "yes", "domain": ".github.com"},
            ],
            "local_storage": {},
            "session_storage": {},
            "metadata": {
                "cookie_count": 2,
                "critical_cookie_count": 1,
                "last_refreshed": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            },
        },
        "gmail.tokenade": {
            "version": "1.0",
            "site_name": "google",
            "auth_status": "logged_in",
            "source_device": {"browser": "brave"},
            "cookies": [
                {"name": "SID", "value": "x", "domain": ".google.com"},
                {"name": "HSID", "value": "y", "domain": ".google.com"},
                {"name": "SSID", "value": "z", "domain": ".google.com"},
            ],
            "local_storage": {"key1": "val1"},
            "session_storage": {},
            "metadata": {
                "cookie_count": 3,
                "critical_cookie_count": 2,
                "last_refreshed": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
            },
        },
        "twitter.tokenade": {
            "version": "1.0",
            "site_name": "twitter",
            "auth_status": "logged_in",
            "source_device": {"browser": "chrome"},
            "cookies": [
                {"name": "auth_token", "value": "abc123", "domain": ".twitter.com"},
            ],
            "local_storage": {},
            "session_storage": {},
            "metadata": {
                "cookie_count": 1,
                "critical_cookie_count": 1,
                # No last_refreshed — never refreshed
            },
        },
        "linkedin.tokenade": {
            "version": "1.0",
            "site_name": "linkedin",
            "auth_status": "logged_in",
            "source_device": {"browser": "edge"},
            "cookies": [
                {"name": "li_at", "value": "xyz", "domain": ".linkedin.com"},
            ],
            "local_storage": {},
            "session_storage": {},
            "metadata": {
                "cookie_count": 1,
                "critical_cookie_count": 1,
                "last_refreshed": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
            },
        },
    }

    for name, data in sessions.items():
        (tmp_path / name).write_text(json.dumps(data, indent=2))

    return tmp_path


class TestAccountsList:
    def test_list_all_sessions(self, sessions_dir):
        """Test listing all sessions."""
        args = Namespace(
            accounts_action="list",
            sessions_dir=str(sessions_dir),
            site=None,
            browser=None,
        )
        cmd_accounts(args)

    def test_list_filter_by_site(self, sessions_dir):
        """Test filtering by site name."""
        from tokenade.core.importer.session_manager import SessionManager
        manager = SessionManager(str(sessions_dir))
        args = Namespace(site="github", browser=None)
        _accounts_list(manager, args)

    def test_list_filter_by_browser(self, sessions_dir):
        """Test filtering by browser."""
        from tokenade.core.importer.session_manager import SessionManager
        manager = SessionManager(str(sessions_dir))
        args = Namespace(site=None, browser="brave")
        _accounts_list(manager, args)

    def test_list_empty_dir(self, tmp_path):
        """Test listing in empty directory."""
        from tokenade.core.importer.session_manager import SessionManager
        manager = SessionManager(str(tmp_path))
        args = Namespace(site=None, browser=None)
        _accounts_list(manager, args)

    def test_list_no_match(self, sessions_dir):
        """Test filtering with no matches."""
        from tokenade.core.importer.session_manager import SessionManager
        manager = SessionManager(str(sessions_dir))
        args = Namespace(site="nonexistent", browser=None)
        _accounts_list(manager, args)


class TestAccountsStatus:
    def test_status_all_sessions(self, sessions_dir):
        """Test status of all sessions."""
        from tokenade.core.importer.session_manager import SessionManager
        manager = SessionManager(str(sessions_dir))
        args = Namespace(site=None)
        _accounts_status(manager, args)

    def test_status_filter_by_site(self, sessions_dir):
        """Test status filtered by site."""
        from tokenade.core.importer.session_manager import SessionManager
        manager = SessionManager(str(sessions_dir))
        args = Namespace(site="google")
        _accounts_status(manager, args)

    def test_status_empty_dir(self, tmp_path):
        """Test status in empty directory."""
        from tokenade.core.importer.session_manager import SessionManager
        manager = SessionManager(str(tmp_path))
        args = Namespace(site=None)
        _accounts_status(manager, args)

    def test_status_never_refreshed(self, tmp_path):
        """Test status for session never refreshed."""
        session = {
            "version": "1.0",
            "site_name": "test",
            "cookies": [{"name": "c", "value": "v", "domain": ".test.com"}],
            "metadata": {},
        }
        (tmp_path / "test.tokenade").write_text(json.dumps(session))

        from tokenade.core.importer.session_manager import SessionManager
        manager = SessionManager(str(tmp_path))
        args = Namespace(site=None)
        _accounts_status(manager, args)


class TestDetectUrlFromCookies:
    def test_github(self):
        cookies = [{"domain": ".github.com"}]
        assert _detect_url_from_cookies(cookies) == "https://github.com"

    def test_google(self):
        cookies = [{"domain": ".google.com"}]
        assert _detect_url_from_cookies(cookies) == "https://mail.google.com"

    def test_gmail(self):
        cookies = [{"domain": ".gmail.com"}]
        assert _detect_url_from_cookies(cookies) == "https://mail.google.com"

    def test_twitter(self):
        cookies = [{"domain": ".twitter.com"}]
        assert _detect_url_from_cookies(cookies) == "https://x.com"

    def test_x_com(self):
        cookies = [{"domain": ".x.com"}]
        assert _detect_url_from_cookies(cookies) == "https://x.com"

    def test_linkedin(self):
        cookies = [{"domain": ".linkedin.com"}]
        assert _detect_url_from_cookies(cookies) == "https://www.linkedin.com"

    def test_reddit(self):
        cookies = [{"domain": ".reddit.com"}]
        assert _detect_url_from_cookies(cookies) == "https://www.reddit.com"

    def test_facebook(self):
        cookies = [{"domain": ".facebook.com"}]
        assert _detect_url_from_cookies(cookies) == "https://www.facebook.com"

    def test_unknown_domain(self):
        cookies = [{"domain": ".example.com"}]
        assert _detect_url_from_cookies(cookies) == "https://example.com"

    def test_empty_cookies(self):
        assert _detect_url_from_cookies([]) is None

    def test_no_domain(self):
        cookies = [{"domain": ""}]
        assert _detect_url_from_cookies(cookies) is None


class TestAccountsRefresh:
    def test_refresh_empty_dir(self, tmp_path):
        """Test refresh in empty directory."""
        args = Namespace(
            accounts_action="refresh",
            sessions_dir=str(tmp_path),
            site=None,
            browser="chrome",
            files=None,
            port=9222,
            visible=False,
            headless=True,
            wait=8,
            yes=True,
        )
        cmd_accounts(args)

    def test_refresh_no_match(self, sessions_dir):
        """Test refresh with no matching sessions."""
        args = Namespace(
            accounts_action="refresh",
            sessions_dir=str(sessions_dir),
            site="nonexistent",
            browser="chrome",
            files=None,
            port=9222,
            visible=False,
            headless=True,
            wait=8,
            yes=True,
        )
        cmd_accounts(args)


class TestAccountsIntegration:
    def test_full_flow_list_status(self, sessions_dir):
        """Test list then status flow."""
        from tokenade.core.importer.session_manager import SessionManager
        manager = SessionManager(str(sessions_dir))

        # List
        sessions = manager.list_sessions()
        assert len(sessions) == 4

        # Status
        args = Namespace(site=None)
        _accounts_status(manager, args)

    def test_site_filtering_consistency(self, sessions_dir):
        """Test that site filtering works consistently across list and status."""
        from tokenade.core.importer.session_manager import SessionManager
        manager = SessionManager(str(sessions_dir))

        all_sessions = manager.list_sessions()
        github_sessions = [s for s in all_sessions if "github" in s.site_name.lower()]

        assert len(github_sessions) == 1
        assert github_sessions[0].site_name == "github"

    def test_metadata_fields_present(self, sessions_dir):
        """Test that all expected metadata fields are present."""
        from tokenade.core.importer.session_packager import SessionPackager
        packager = SessionPackager()

        for f in sessions_dir.glob("*.tokenade"):
            session = packager.load(str(f))
            assert "cookies" in session
            assert "metadata" in session
            assert "cookie_count" in session["metadata"]
