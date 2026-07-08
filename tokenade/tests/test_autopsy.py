"""Tests for Phase 57 — Session Forensics (Autopsy)."""

import json
import time
from pathlib import Path

import pytest

from tokenade.core.forensics.autopsy import (
    SessionAutopsy,
    AutopsyReport,
    CookieEvidence,
)


# ─── Helper ─────────────────────────────────────────────────

def _make_session_file(tmp_path, name="test", site="github",
                       auth="logged_in", cookies=None,
                       created_at=None):
    """Create a session file with custom cookies."""
    from datetime import datetime, timezone
    now = int(time.time())
    if created_at is None:
        # Fresh by default so "old_session" does not dominate cause-of-death
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if cookies is None:
        cookies = [
            {
                "name": "session_id",
                "value": "abc",
                "domain": ".github.com",
                "path": "/",
                "expires": now + 86400 * 30,
                "secure": True,
            },
            {
                "name": "user_session",
                "value": "xyz",
                "domain": ".github.com",
                "path": "/",
                "expires": now + 86400 * 30,
                "secure": True,
            },
        ]
    session = {
        "version": "2.0",
        "site_name": site,
        "auth_status": auth,
        "created_at": created_at,
        "cookies": cookies,
    }
    path = tmp_path / f"{name}.tokenade"
    path.write_text(json.dumps(session))
    return str(path)


def _cookie(name, domain=".example.com", expires=None, session_cookie=False):
    """Helper to create a cookie dict."""
    now = int(time.time())
    if session_cookie:
        exp = 0
    elif expires == "past":
        exp = now - 3600
    elif expires == "soon":
        exp = now + 1800  # 30 min
    elif expires == "future":
        exp = now + 86400 * 30
    else:
        exp = now + 86400 * 30
    return {
        "name": name,
        "value": "val",
        "domain": domain,
        "path": "/",
        "expires": exp,
        "secure": True,
    }


# ─── CookieEvidence Tests ──────────────────────────────────

class TestCookieEvidence:
    def test_defaults(self):
        e = CookieEvidence(
            name="sid", domain=".example.com",
            status="valid", expires_at="2026-12-01T00:00:00Z",
        )
        assert e.is_critical is False
        assert e.probable_cause == ""

    def test_critical_cookie(self):
        e = CookieEvidence(
            name="user_session", domain=".github.com",
            status="expired", expires_at="2026-01-01T00:00:00Z",
            is_critical=True, probable_cause="expired 100h ago",
        )
        assert e.is_critical is True


# ─── AutopsyReport Tests ──────────────────────────────────

class TestAutopsyReport:
    def test_empty_report(self):
        r = AutopsyReport(session_file="test.tokenade")
        assert r.cause_of_death == "unknown"
        assert r.confidence == "low"
        assert r.cookie_count == 0

    def test_to_text(self):
        r = AutopsyReport(
            session_file="test.tokenade",
            cause_of_death="natural_expiry",
            confidence="high",
            site_name="github",
            auth_status="session_expired",
            cookie_count=10,
            expired_count=8,
            critical_present=3,
            critical_missing=1,
        )
        text = r.to_text()
        assert "SESSION AUTOPSY REPORT" in text
        assert "NATURAL_EXPIRY" in text
        assert "github" in text

    def test_to_json(self):
        r = AutopsyReport(
            session_file="test.tokenade",
            cause_of_death="server_revocation",
            confidence="high",
            site_name="google",
        )
        j = json.loads(r.to_json())
        assert j["cause_of_death"] == "server_revocation"
        assert j["site_name"] == "google"

    def test_to_json_with_cookies(self):
        r = AutopsyReport(
            session_file="test.tokenade",
            cookie_evidence=[
                CookieEvidence(
                    name="sid", domain=".example.com",
                    status="expired", expires_at="2026-01-01",
                    is_critical=True,
                ),
            ],
        )
        j = json.loads(r.to_json())
        assert len(j["cookies"]) == 1
        assert j["cookies"][0]["is_critical"] is True


# ─── SessionAutopsy Tests ──────────────────────────────────

class TestSessionAutopsy:
    def test_file_not_found(self, tmp_path):
        autopsy = SessionAutopsy(str(tmp_path / "missing.tokenade"))
        report = autopsy.analyze()
        assert report.cause_of_death == "unknown"
        assert report.confidence == "high"
        assert "not found" in report.recommendations[0].lower()

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "bad.tokenade"
        p.write_text("not json {{{")
        autopsy = SessionAutopsy(str(p))
        report = autopsy.analyze()
        assert "Invalid JSON" in report.recommendations[0]

    def test_healthy_session(self, tmp_path):
        path = _make_session_file(tmp_path, auth="logged_in")
        autopsy = SessionAutopsy(path)
        report = autopsy.analyze()
        # Healthy session — no clear cause of death
        assert report.cookie_count == 2
        assert report.expired_count == 0
        assert report.auth_status == "logged_in"

    def test_natural_expiry(self, tmp_path):
        """Most cookies expired = natural_expiry."""
        now = int(time.time())
        cookies = [
            _cookie("c1", expires="past"),
            _cookie("c2", expires="past"),
            _cookie("c3", expires="past"),
            _cookie("c4", expires="future"),
        ]
        path = _make_session_file(
            tmp_path, site="github", auth="logged_in",
            cookies=cookies,
        )
        autopsy = SessionAutopsy(path)
        report = autopsy.analyze()
        assert report.cause_of_death == "natural_expiry"
        assert report.expired_count == 3

    def test_server_revocation(self, tmp_path):
        """Auth status bad but no expired cookies = server revocation."""
        cookies = [
            _cookie("user_session", expires="future"),
            _cookie("__Host-device_id", expires="future"),
            _cookie("has_recent_activity", expires="future"),
        ]
        path = _make_session_file(
            tmp_path, site="github", auth="session_expired",
            cookies=cookies,
        )
        autopsy = SessionAutopsy(path)
        report = autopsy.analyze()
        assert report.cause_of_death == "server_revocation"

    def test_missing_critical(self, tmp_path):
        """Critical cookies missing = missing_critical."""
        # Only non-critical cookies present
        cookies = [
            _cookie("theme", expires="future"),
            _cookie("lang", expires="future"),
        ]
        path = _make_session_file(
            tmp_path, site="github", auth="logged_in",
            cookies=cookies,
        )
        autopsy = SessionAutopsy(path)
        report = autopsy.analyze()
        assert report.critical_missing > 0
        assert report.cause_of_death == "missing_critical"

    def test_mixed_signals(self, tmp_path):
        """Multiple issues = mixed_signals."""
        cookies = [
            _cookie("c1", expires="past"),
            _cookie("theme", expires="future"),
        ]
        path = _make_session_file(
            tmp_path, site="github", auth="session_expired",
            cookies=cookies,
        )
        autopsy = SessionAutopsy(path)
        report = autopsy.analyze()
        assert report.cause_of_death == "mixed_signals"

    def test_google_critical_cookies(self, tmp_path):
        """Test with Google site and critical cookies."""
        cookies = [
            _cookie("__Secure-1PSID", domain=".google.com", expires="past"),
            _cookie("__Secure-3PSID", domain=".google.com", expires="past"),
            _cookie("SID", domain=".google.com", expires="past"),
        ]
        path = _make_session_file(
            tmp_path, site="google", auth="session_expired",
            cookies=cookies,
        )
        autopsy = SessionAutopsy(path)
        report = autopsy.analyze()
        assert report.site_name == "google"
        assert report.critical_present == 3

    def test_session_age(self, tmp_path):
        """Old session triggers session_age cause."""
        cookies = [
            _cookie("user_session", expires="future"),
            _cookie("__Host-device_id", expires="future"),
            _cookie("__Host-user_session_same_site", expires="future"),
            _cookie("has_recent_activity", expires="future"),
        ]
        path = _make_session_file(
            tmp_path, site="github", auth="logged_in",
            cookies=cookies,
            created_at="2026-01-01T00:00:00Z",  # Very old
        )
        autopsy = SessionAutopsy(path)
        report = autopsy.analyze()
        assert report.session_age_hours > 100

    def test_timeline(self, tmp_path):
        """Timeline should include creation and expiry events."""
        cookies = [
            _cookie("c1", expires="past"),
        ]
        path = _make_session_file(
            tmp_path, cookies=cookies,
            created_at="2026-07-01T00:00:00Z",
        )
        autopsy = SessionAutopsy(path)
        report = autopsy.analyze()
        assert len(report.timeline) >= 2
        assert any("created" in e for e in report.timeline)

    def test_recommendations_natural_expiry(self, tmp_path):
        now = int(time.time())
        cookies = [_cookie("c1", expires="past"), _cookie("c2", expires="past")]
        path = _make_session_file(tmp_path, cookies=cookies)
        autopsy = SessionAutopsy(path)
        report = autopsy.analyze()
        assert any("Re-export" in r for r in report.recommendations)

    def test_recommendations_server_revocation(self, tmp_path):
        cookies = [_cookie("user_session", expires="future")]
        path = _make_session_file(
            tmp_path, site="github", auth="session_expired",
            cookies=cookies,
        )
        autopsy = SessionAutopsy(path)
        report = autopsy.analyze()
        assert any("Re-login" in r for r in report.recommendations)

    def test_compare_sessions(self, tmp_path):
        """Compare dead vs live session."""
        dead = _make_session_file(
            tmp_path, "dead", cookies=[
                _cookie("c1", expires="past"),
                _cookie("c2", expires="future"),
            ],
        )
        live = _make_session_file(
            tmp_path, "live", cookies=[
                _cookie("c1", expires="future"),
                _cookie("c2", expires="future"),
                _cookie("c3", expires="future"),
            ],
        )
        autopsy1 = SessionAutopsy(dead)
        autopsy2 = SessionAutopsy(live)
        r1 = autopsy1.analyze()
        r2 = autopsy2.analyze()
        assert r1.cookie_count < r2.cookie_count

    def test_session_cookie(self, tmp_path):
        """Session cookies (no expiry) should be classified as 'session'."""
        cookies = [
            _cookie("sess", session_cookie=True),
            _cookie("valid", expires="future"),
        ]
        path = _make_session_file(tmp_path, cookies=cookies)
        autopsy = SessionAutopsy(path)
        report = autopsy.analyze()
        session_cookies = [
            e for e in report.cookie_evidence if e.status == "session"
        ]
        assert len(session_cookies) == 1
        assert session_cookies[0].name == "sess"


# ─── CLI Parser Tests ──────────────────────────────────────

class TestAutopsyCLIParser:
    def test_autopsy_parser(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["autopsy", "-s", "dead.tokenade"])
        assert a.session == "dead.tokenade"

    def test_autopsy_compare(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args([
            "autopsy", "-s", "dead.tokenade",
            "-c", "live.tokenade",
        ])
        assert a.compare == "live.tokenade"

    def test_autopsy_json(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args([
            "autopsy", "-s", "dead.tokenade", "--format", "json",
        ])
        assert a.format == "json"

    def test_autopsy_help(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        with pytest.raises(SystemExit):
            p.parse_args(["autopsy", "--help"])
