"""Tests for session rotation monitor - login event detection."""

import pytest

from tokenade.core.refresh.rotator import SessionRotationMonitor, LoginEvent


@pytest.fixture
def monitor():
    return SessionRotationMonitor(site_name="github")


@pytest.fixture
def google_monitor():
    return SessionRotationMonitor(site_name="google")


@pytest.fixture
def base_cookies():
    return [
        {"name": "session_id", "value": "abc", "domain": ".example.com", "path": "/"},
        {"name": "lang", "value": "en", "domain": ".example.com", "path": "/"},
    ]


class TestSnapshot:
    def test_snapshot_stores_cookies(self, monitor, base_cookies):
        monitor.snapshot(base_cookies)
        assert monitor._previous_cookies == {"session_id": "abc", "lang": "en"}

    def test_snapshot_empty(self, monitor):
        monitor.snapshot([])
        assert monitor._previous_cookies == {}

    def test_snapshot_overwrites_previous(self, monitor, base_cookies):
        monitor.snapshot(base_cookies)
        new_cookies = [{"name": "new", "value": "v", "domain": ".example.com", "path": "/"}]
        monitor.snapshot(new_cookies)
        assert monitor._previous_cookies == {"new": "v"}


class TestNoChanges:
    def test_identical_cookies_returns_none(self, monitor, base_cookies):
        monitor.snapshot(base_cookies)
        result = monitor.detect_changes(base_cookies)
        assert result is None

    def test_no_changes_after_snapshot(self, monitor):
        cookies = [
            {"name": "a", "value": "1", "domain": ".example.com", "path": "/"},
            {"name": "b", "value": "2", "domain": ".example.com", "path": "/"},
        ]
        monitor.snapshot(cookies)
        assert monitor.detect_changes(cookies) is None

    def test_no_changes_empty_cookies(self, monitor):
        monitor.snapshot([])
        assert monitor.detect_changes([]) is None


class TestAddedCookies:
    def test_detect_added_cookies(self, monitor, base_cookies):
        monitor.snapshot(base_cookies)
        new_cookies = base_cookies + [
            {"name": "new_cookie", "value": "v", "domain": ".example.com", "path": "/"}
        ]
        event = monitor.detect_changes(new_cookies)
        assert event is not None
        assert "new_cookie" in event.cookies_added
        assert event.event_type == "cookie_change"

    def test_added_multiple_cookies(self, monitor):
        monitor.snapshot([])
        cookies = [
            {"name": "a", "value": "1", "domain": ".example.com", "path": "/"},
            {"name": "b", "value": "2", "domain": ".example.com", "path": "/"},
        ]
        event = monitor.detect_changes(cookies)
        assert event is not None
        assert set(event.cookies_added) == {"a", "b"}


class TestRemovedCookies:
    def test_detect_removed_cookies(self, monitor, base_cookies):
        monitor.snapshot(base_cookies)
        remaining = [base_cookies[0]]
        event = monitor.detect_changes(remaining)
        assert event is not None
        assert "lang" in event.cookies_removed

    def test_removed_all_cookies(self, monitor, base_cookies):
        monitor.snapshot(base_cookies)
        event = monitor.detect_changes([])
        assert event is not None
        assert set(event.cookies_removed) == {"session_id", "lang"}


class TestModifiedCookies:
    def test_detect_modified_cookies(self, monitor, base_cookies):
        monitor.snapshot(base_cookies)
        modified = [
            {"name": "session_id", "value": "new_value", "domain": ".example.com", "path": "/"},
            {"name": "lang", "value": "en", "domain": ".example.com", "path": "/"},
        ]
        event = monitor.detect_changes(modified)
        assert event is not None
        assert "session_id" in event.cookies_modified
        assert event.event_type == "token_refresh"


class TestLoginDetection:
    def test_github_auth_cookie_added(self, monitor):
        monitor.snapshot([])
        cookies = [
            {"name": "user_session", "value": "abc", "domain": ".github.com", "path": "/"},
        ]
        event = monitor.detect_changes(cookies)
        assert event is not None
        assert event.event_type == "login"
        assert "user_session" in event.cookies_added

    def test_github_logged_in_added(self, monitor):
        monitor.snapshot([])
        cookies = [
            {"name": "logged_in", "value": "yes", "domain": ".github.com", "path": "/"},
        ]
        event = monitor.detect_changes(cookies)
        assert event is not None
        assert event.event_type == "login"

    def test_google_auth_cookie_added(self, google_monitor):
        google_monitor.snapshot([])
        cookies = [
            {"name": "SID", "value": "abc", "domain": ".google.com", "path": "/"},
        ]
        event = google_monitor.detect_changes(cookies)
        assert event is not None
        assert event.event_type == "login"

    def test_default_auth_cookie_added(self):
        m = SessionRotationMonitor(site_name="mysite")
        m.snapshot([])
        cookies = [
            {"name": "session_id", "value": "abc", "domain": ".mysite.com", "path": "/"},
        ]
        event = m.detect_changes(cookies)
        assert event is not None
        assert event.event_type == "login"

    def test_auth_cookie_modified(self, monitor):
        monitor.snapshot([
            {"name": "user_session", "value": "old", "domain": ".github.com", "path": "/"},
        ])
        cookies = [
            {"name": "user_session", "value": "new", "domain": ".github.com", "path": "/"},
        ]
        event = monitor.detect_changes(cookies)
        assert event is not None
        assert event.event_type == "login"


class TestLogoutDetection:
    def test_github_auth_cookie_removed(self, monitor):
        monitor.snapshot([
            {"name": "user_session", "value": "abc", "domain": ".github.com", "path": "/"},
            {"name": "_gh_sess", "value": "de", "domain": ".github.com", "path": "/"},
        ])
        cookies = [
            {"name": "_gh_sess", "value": "de", "domain": ".github.com", "path": "/"},
        ]
        event = monitor.detect_changes(cookies)
        assert event is not None
        assert event.event_type == "logout"
        assert "user_session" in event.cookies_removed

    def test_default_auth_cookie_removed(self):
        m = SessionRotationMonitor(site_name="mysite")
        m.snapshot([
            {"name": "session_id", "value": "abc", "domain": ".mysite.com", "path": "/"},
        ])
        event = m.detect_changes([])
        assert event is not None
        assert event.event_type == "logout"


class TestTokenRefreshDetection:
    def test_non_auth_cookie_modified(self, monitor):
        monitor.snapshot([
            {"name": "preferences", "value": "old", "domain": ".github.com", "path": "/"},
        ])
        cookies = [
            {"name": "preferences", "value": "new", "domain": ".github.com", "path": "/"},
        ]
        event = monitor.detect_changes(cookies)
        assert event is not None
        assert event.event_type == "token_refresh"


class TestCallback:
    def test_callback_fires_on_event(self, monitor, base_cookies):
        events_received = []
        monitor.set_callback(lambda e: events_received.append(e))

        monitor.snapshot([])
        new_cookies = [
            {"name": "user_session", "value": "abc", "domain": ".github.com", "path": "/"},
        ]
        monitor.detect_changes(new_cookies)
        assert len(events_received) == 1
        assert events_received[0].event_type == "login"

    def test_callback_not_fired_on_no_change(self, monitor, base_cookies):
        events_received = []
        monitor.set_callback(lambda e: events_received.append(e))

        monitor.snapshot(base_cookies)
        monitor.detect_changes(base_cookies)
        assert len(events_received) == 0

    def test_callback_exception_handled(self, monitor, base_cookies):
        def bad_callback(e):
            raise RuntimeError("boom")

        monitor.set_callback(bad_callback)
        monitor.snapshot([])
        cookies = [
            {"name": "user_session", "value": "abc", "domain": ".github.com", "path": "/"},
        ]
        # Should not raise
        event = monitor.detect_changes(cookies)
        assert event is not None

    def test_no_callback(self, monitor, base_cookies):
        monitor.snapshot([])
        cookies = [
            {"name": "user_session", "value": "abc", "domain": ".github.com", "path": "/"},
        ]
        event = monitor.detect_changes(cookies)
        assert event is not None


class TestShouldRefresh:
    def test_no_events_no_refresh(self, monitor):
        assert monitor.should_refresh() is False

    def test_single_login_no_refresh(self, monitor):
        monitor.snapshot([])
        monitor.detect_changes([
            {"name": "user_session", "value": "abc", "domain": ".github.com", "path": "/"},
        ])
        assert monitor.should_refresh() is False

    def test_two_logins_triggers_refresh(self, monitor):
        # First login
        monitor.snapshot([])
        monitor.detect_changes([
            {"name": "user_session", "value": "abc", "domain": ".github.com", "path": "/"},
        ])
        # Simulate logout
        monitor.detect_changes([])
        # Second login
        monitor.detect_changes([
            {"name": "user_session", "value": "new", "domain": ".github.com", "path": "/"},
        ])
        assert monitor.should_refresh() is True

    def test_mixed_events_no_refresh(self, monitor):
        monitor.snapshot([])
        # Just a cookie change, not a login
        monitor.detect_changes([
            {"name": "preferences", "value": "v", "domain": ".github.com", "path": "/"},
        ])
        assert monitor.should_refresh() is False


class TestEventHistory:
    def test_events_stored(self, monitor, base_cookies):
        monitor.snapshot([])
        new_cookies = [
            {"name": "user_session", "value": "abc", "domain": ".github.com", "path": "/"},
        ]
        monitor.detect_changes(new_cookies)
        events = monitor.get_events()
        assert len(events) == 1
        assert events[0].event_type == "login"

    def test_multiple_events_stored(self, monitor):
        monitor.snapshot([])
        monitor.detect_changes([
            {"name": "user_session", "value": "abc", "domain": ".github.com", "path": "/"},
        ])
        monitor.detect_changes([])
        events = monitor.get_events()
        assert len(events) == 2

    def test_clear_events(self, monitor):
        monitor.snapshot([])
        monitor.detect_changes([
            {"name": "user_session", "value": "abc", "domain": ".github.com", "path": "/"},
        ])
        assert len(monitor.get_events()) == 1
        monitor.clear_events()
        assert len(monitor.get_events()) == 0

    def test_get_events_returns_copy(self, monitor):
        monitor.snapshot([])
        monitor.detect_changes([
            {"name": "user_session", "value": "abc", "domain": ".github.com", "path": "/"},
        ])
        events = monitor.get_events()
        events.clear()
        assert len(monitor.get_events()) == 1


class TestLoginEventDataclass:
    def test_fields(self):
        event = LoginEvent(
            timestamp="2026-01-01T00:00:00Z",
            site_name="github",
            event_type="login",
            cookies_added=["user_session"],
            cookies_removed=[],
            cookies_modified=[],
        )
        assert event.timestamp == "2026-01-01T00:00:00Z"
        assert event.site_name == "github"
        assert event.event_type == "login"
        assert event.cookies_added == ["user_session"]
        assert event.cookies_removed == []
        assert event.cookies_modified == []

    def test_defaults(self):
        event = LoginEvent(
            timestamp="2026-01-01T00:00:00Z",
            site_name="test",
            event_type="login",
        )
        assert event.cookies_added == []
        assert event.cookies_removed == []
        assert event.cookies_modified == []


class TestAuthCookiePatterns:
    def test_github_patterns(self, monitor):
        patterns = monitor._get_auth_cookie_names()
        assert "user_session" in patterns
        assert "_gh_sess" in patterns
        assert "logged_in" in patterns

    def test_google_patterns(self, google_monitor):
        patterns = google_monitor._get_auth_cookie_names()
        assert "SID" in patterns
        assert "HSID" in patterns

    def test_default_patterns(self):
        m = SessionRotationMonitor(site_name="mysite")
        patterns = m._get_auth_cookie_names()
        assert "session_id" in patterns
        assert "token" in patterns
        assert "auth" in patterns

    def test_unknown_site_uses_default(self):
        m = SessionRotationMonitor(site_name="random_site_xyz")
        patterns = m._get_auth_cookie_names()
        assert "session_id" in patterns


class TestEdgeCases:
    def test_complex_mixed_changes(self, monitor):
        monitor.snapshot([
            {"name": "keep", "value": "same", "domain": ".github.com", "path": "/"},
            {"name": "modify", "value": "old", "domain": ".github.com", "path": "/"},
            {"name": "remove_me", "value": "v", "domain": ".github.com", "path": "/"},
        ])
        event = monitor.detect_changes([
            {"name": "keep", "value": "same", "domain": ".github.com", "path": "/"},
            {"name": "modify", "value": "new", "domain": ".github.com", "path": "/"},
            {"name": "add_me", "value": "v", "domain": ".github.com", "path": "/"},
        ])
        assert event is not None
        assert "add_me" in event.cookies_added
        assert "remove_me" in event.cookies_removed
        assert "modify" in event.cookies_modified

    def test_event_timestamp_is_iso(self, monitor):
        monitor.snapshot([])
        event = monitor.detect_changes([
            {"name": "session_id", "value": "abc", "domain": ".github.com", "path": "/"},
        ])
        assert event is not None
        # Verify it's a valid ISO format
        from datetime import datetime
        datetime.fromisoformat(event.timestamp)

    def test_detect_changes_updates_previous(self, monitor):
        monitor.snapshot([])
        new_cookies = [
            {"name": "session_id", "value": "abc", "domain": ".github.com", "path": "/"},
        ]
        monitor.detect_changes(new_cookies)
        # Now calling again with same cookies should return None
        assert monitor.detect_changes(new_cookies) is None

    def test_cookie_name_with_empty_string(self, monitor):
        monitor.snapshot([{"name": "", "value": "v", "domain": ".github.com", "path": "/"}])
        event = monitor.detect_changes([{"name": "", "value": "new", "domain": ".github.com", "path": "/"}])
        assert event is not None
        assert "" in event.cookies_modified
