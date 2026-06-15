"""Tests for session comparison tool."""

import json
import pytest
from tokenade.core.importer.session_comparator import SessionComparator, DiffResult


@pytest.fixture
def session_a():
    return {
        "version": "2.0",
        "site_name": "example",
        "auth_status": "logged_in",
        "source_device": {"browser": "chrome", "platform": "Linux"},
        "cookies": [
            {"name": "session", "value": "abc", "domain": ".example.com", "path": "/"},
            {"name": "lang", "value": "en", "domain": ".example.com", "path": "/"},
        ],
        "local_storage": {"user": "alice", "theme": "dark"},
    }


@pytest.fixture
def session_b():
    return {
        "version": "2.0",
        "site_name": "example",
        "auth_status": "logged_in",
        "source_device": {"browser": "chrome", "platform": "Linux"},
        "cookies": [
            {"name": "session", "value": "xyz", "domain": ".example.com", "path": "/"},
            {"name": "lang", "value": "en", "domain": ".example.com", "path": "/"},
            {"name": "csrf", "value": "tok", "domain": ".example.com", "path": "/"},
        ],
        "local_storage": {"user": "bob", "lang": "fr"},
    }


class TestSessionComparator:
    def test_identical_sessions(self, session_a):
        comparator = SessionComparator()
        result = comparator.compare(session_a, session_a)
        assert not result.has_changes
        assert len(result.cookies_common) == 2
        assert len(result.cookies_modified) == 0
        assert len(result.cookies_only_in_a) == 0
        assert len(result.cookies_only_in_b) == 0

    def test_cookie_added(self, session_a, session_b):
        comparator = SessionComparator()
        result = comparator.compare(session_a, session_b)
        assert result.has_changes
        assert len(result.cookies_only_in_b) == 1
        assert result.cookies_only_in_b[0]["name"] == "csrf"

    def test_cookie_removed(self, session_a, session_b):
        comparator = SessionComparator()
        result = comparator.compare(session_b, session_a)
        assert result.has_changes
        assert len(result.cookies_only_in_a) == 1
        assert result.cookies_only_in_a[0]["name"] == "csrf"

    def test_cookie_modified(self, session_a, session_b):
        comparator = SessionComparator()
        result = comparator.compare(session_a, session_b)
        assert len(result.cookies_modified) == 1
        assert result.cookies_modified[0]["a"]["value"] == "abc"
        assert result.cookies_modified[0]["b"]["value"] == "xyz"

    def test_localstorage_diff(self, session_a, session_b):
        comparator = SessionComparator()
        result = comparator.compare(session_a, session_b)
        assert "user" in result.localStorage_modified
        assert result.localStorage_modified["user"]["a"] == "alice"
        assert result.localStorage_modified["user"]["b"] == "bob"
        assert "theme" in result.localStorage_only_in_a
        assert "lang" in result.localStorage_only_in_b

    def test_metadata_diff(self, session_a):
        comparator = SessionComparator()
        session_b = {**session_a, "site_name": "other"}
        result = comparator.compare(session_a, session_b)
        assert "site_name" in result.metadata_diffs

    def test_summary(self, session_a, session_b):
        comparator = SessionComparator()
        result = comparator.compare(session_a, session_b)
        summary = result.summary()
        assert "Cookies modified" in summary
        assert "localStorage modified" in summary

    def test_summary_identical(self, session_a):
        comparator = SessionComparator()
        result = comparator.compare(session_a, session_a)
        assert result.summary() == "  Sessions are identical"

    def test_compare_files(self, tmp_path, session_a, session_b):
        file_a = tmp_path / "a.tokenade"
        file_b = tmp_path / "b.tokenade"
        file_a.write_text(json.dumps(session_a))
        file_b.write_text(json.dumps(session_b))

        comparator = SessionComparator()
        result = comparator.compare_files(str(file_a), str(file_b))
        assert result.has_changes

    def test_empty_sessions(self):
        comparator = SessionComparator()
        result = comparator.compare({}, {})
        assert not result.has_changes
