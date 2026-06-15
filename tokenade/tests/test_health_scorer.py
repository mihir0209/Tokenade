"""Tests for OWASP-based session health scorer."""

import math
import time
from datetime import datetime, timezone, timedelta

import pytest

from tokenade.core.refresh.health_scorer import SessionHealthScorer, HealthScoreBreakdown


@pytest.fixture
def scorer():
    return SessionHealthScorer()


@pytest.fixture
def perfect_session():
    """Session with high entropy, valid expiry, all security flags, fresh."""
    future = int(time.time()) + 7200
    return {
        "site_name": "example",
        "auth_status": "logged_in",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cookies": [
            {
                "name": "session_id",
                "value": "aB3xY9zK2mNpQ7wR4tL8jF5vC1nG6hD0sE",
                "domain": ".example.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "Lax",
                "expires": future,
            },
            {
                "name": "csrf_token",
                "value": "Xk9mP3nL7qW2rT5yU8jH4vB1cD6fG0aS",
                "domain": ".example.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "Strict",
                "expires": future,
            },
        ],
    }


@pytest.fixture
def empty_session():
    return {"site_name": "example", "auth_status": "unknown", "cookies": []}


class TestPerfectScore:
    def test_perfect_session_scores_high(self, scorer, perfect_session):
        breakdown = scorer.score(perfect_session)
        assert breakdown.total_score >= 80.0
        assert breakdown.entropy_score >= 20.0
        assert breakdown.expiry_score == 25.0
        assert breakdown.flags_score >= 20.0
        assert breakdown.freshness_score >= 20.0

    def test_perfect_session_no_issues(self, scorer, perfect_session):
        breakdown = scorer.score(perfect_session)
        assert len(breakdown.issues) == 0


class TestEntropyScoring:
    def test_high_entropy_token(self, scorer):
        cookies = [
            {
                "name": "sid",
                "value": "aB3xY9zK2mNpQ7wR4tL8jF5vC1nG6hD0sE",
                "domain": ".example.com",
                "path": "/",
            }
        ]
        score = scorer._score_entropy(cookies)
        assert score > 15.0

    def test_low_entropy_token(self, scorer):
        cookies = [{"name": "sid", "value": "abc", "domain": ".example.com", "path": "/"}]
        score = scorer._score_entropy(cookies)
        assert score < 10.0

    def test_empty_value_token(self, scorer):
        cookies = [{"name": "sid", "value": "", "domain": ".example.com", "path": "/"}]
        score = scorer._score_entropy(cookies)
        assert score == 0.0

    def test_empty_cookies_entropy(self, scorer):
        score = scorer._score_entropy([])
        assert score == 0.0

    def test_entropy_estimates_charset_upper_lower_digit(self, scorer):
        assert scorer._estimate_charset_size("Abc1") >= 62
        assert scorer._estimate_charset_size("abc") >= 26
        assert scorer._estimate_charset_size("ABC") >= 26
        assert scorer._estimate_charset_size("123") >= 10

    def test_entropy_estimates_charset_special(self, scorer):
        size = scorer._estimate_charset_size("abc!@#")
        assert size >= 26 + 32

    def test_entropy_multiple_cookies_averaged(self, scorer):
        cookies = [
            {
                "name": "a",
                "value": "aB3xY9zK2mNpQ7wR4tL8jF5vC1nG6hD0sE",
                "domain": ".example.com",
                "path": "/",
            },
            {"name": "b", "value": "abc", "domain": ".example.com", "path": "/"},
        ]
        score = scorer._score_entropy(cookies)
        assert 0.0 < score < 25.0


class TestExpiryScoring:
    def test_all_valid_cookies(self, scorer):
        future = int(time.time()) + 7200
        cookies = [
            {"name": "a", "value": "v", "domain": ".example.com", "path": "/", "expires": future},
            {"name": "b", "value": "v", "domain": ".example.com", "path": "/", "expires": future},
        ]
        assert scorer._score_expiry(cookies) == 25.0

    def test_all_expired_cookies(self, scorer):
        past = int(time.time()) - 3600
        cookies = [
            {"name": "a", "value": "v", "domain": ".example.com", "path": "/", "expires": past},
        ]
        assert scorer._score_expiry(cookies) == 0.0

    def test_some_expired_cookies(self, scorer):
        future = int(time.time()) + 7200
        past = int(time.time()) - 3600
        cookies = [
            {"name": "a", "value": "v", "domain": ".example.com", "path": "/", "expires": future},
            {"name": "b", "value": "v", "domain": ".example.com", "path": "/", "expires": past},
        ]
        assert scorer._score_expiry(cookies) == 10.0

    def test_expiring_soon_cookies(self, scorer):
        soon = int(time.time()) + 1800  # 30 minutes
        cookies = [
            {"name": "a", "value": "v", "domain": ".example.com", "path": "/", "expires": soon},
        ]
        assert scorer._score_expiry(cookies) == 15.0

    def test_session_cookies_are_valid(self, scorer):
        cookies = [
            {"name": "a", "value": "v", "domain": ".example.com", "path": "/", "expires": 0},
            {"name": "b", "value": "v", "domain": ".example.com", "path": "/"},
        ]
        assert scorer._score_expiry(cookies) == 25.0

    def test_millisecond_expiry_converted(self, scorer):
        future_ms = (int(time.time()) + 7200) * 1000
        cookies = [
            {"name": "a", "value": "v", "domain": ".example.com", "path": "/", "expires": future_ms},
        ]
        assert scorer._score_expiry(cookies) == 25.0

    def test_empty_cookies_expiry(self, scorer):
        assert scorer._score_expiry([]) == 0.0


class TestFlagsScoring:
    def test_all_flags_present(self, scorer):
        cookies = [
            {
                "name": "sid",
                "value": "v",
                "domain": ".example.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "Lax",
            }
        ]
        score = scorer._score_flags(cookies)
        assert score >= 20.0

    def test_no_flags_present(self, scorer):
        cookies = [
            {
                "name": "sid",
                "value": "v",
                "domain": ".example.com",
                "path": "/",
                "secure": False,
                "httpOnly": False,
                "sameSite": "",
            }
        ]
        score = scorer._score_flags(cookies)
        assert score < 15.0

    def test_httponly_only(self, scorer):
        cookies = [
            {
                "name": "sid",
                "value": "v",
                "domain": ".example.com",
                "path": "/",
                "httpOnly": True,
                "secure": False,
                "sameSite": "",
            }
        ]
        score = scorer._score_flags(cookies)
        assert 5.0 < score < 20.0

    def test_samesite_lax(self, scorer):
        cookies = [
            {
                "name": "sid",
                "value": "v",
                "domain": ".example.com",
                "path": "/",
                "sameSite": "Lax",
            }
        ]
        score = scorer._score_flags(cookies)
        assert score > 5.0

    def test_samesite_strict(self, scorer):
        cookies = [
            {
                "name": "sid",
                "value": "v",
                "domain": ".example.com",
                "path": "/",
                "sameSite": "Strict",
            }
        ]
        score = scorer._score_flags(cookies)
        assert score > 5.0

    def test_samesite_none(self, scorer):
        cookies = [
            {
                "name": "sid",
                "value": "v",
                "domain": ".example.com",
                "path": "/",
                "sameSite": "None",
            }
        ]
        score = scorer._score_flags(cookies)
        assert score > 0.0

    def test_specific_domain_bonus(self, scorer):
        cookies = [
            {
                "name": "sid",
                "value": "v",
                "domain": "example.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            }
        ]
        score = scorer._score_flags(cookies)
        assert score > 15.0

    def test_broad_domain_less_bonus(self, scorer):
        cookies_broad = [
            {
                "name": "sid",
                "value": "v",
                "domain": ".example.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            }
        ]
        cookies_specific = [
            {
                "name": "sid",
                "value": "v",
                "domain": "example.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            }
        ]
        broad = scorer._score_flags(cookies_broad)
        specific = scorer._score_flags(cookies_specific)
        assert specific >= broad

    def test_empty_cookies_flags(self, scorer):
        assert scorer._score_flags([]) == 0.0

    def test_multiple_cookies_averaged(self, scorer):
        cookies = [
            {
                "name": "a",
                "value": "v",
                "domain": ".example.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            },
            {
                "name": "b",
                "value": "v",
                "domain": ".example.com",
                "path": "/",
                "httpOnly": False,
                "secure": False,
                "sameSite": "",
            },
        ]
        score = scorer._score_flags(cookies)
        assert 5.0 < score < 25.0


class TestFreshnessScoring:
    def test_fresh_session(self, scorer):
        session = {"created_at": datetime.now(timezone.utc).isoformat()}
        assert scorer._score_freshness(session) == 25.0

    def test_session_2_hours_old(self, scorer):
        created = datetime.now(timezone.utc) - timedelta(hours=2)
        session = {"created_at": created.isoformat()}
        assert scorer._score_freshness(session) == 20.0

    def test_session_6_hours_old(self, scorer):
        created = datetime.now(timezone.utc) - timedelta(hours=6)
        session = {"created_at": created.isoformat()}
        assert scorer._score_freshness(session) == 15.0

    def test_session_12_hours_old(self, scorer):
        created = datetime.now(timezone.utc) - timedelta(hours=12)
        session = {"created_at": created.isoformat()}
        assert scorer._score_freshness(session) == 10.0

    def test_session_3_days_old(self, scorer):
        created = datetime.now(timezone.utc) - timedelta(days=3)
        session = {"created_at": created.isoformat()}
        assert scorer._score_freshness(session) == 5.0

    def test_no_created_at(self, scorer):
        session = {}
        assert scorer._score_freshness(session) == 12.5

    def test_invalid_created_at(self, scorer):
        session = {"created_at": "not-a-date"}
        assert scorer._score_freshness(session) == 12.5

    def test_z_suffix_timestamp(self, scorer):
        session = {"created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        assert scorer._score_freshness(session) == 25.0


class TestCriticalCookies:
    def test_github_all_critical_present(self, scorer):
        session = {
            "site_name": "github",
            "cookies": [
                {"name": "logged_in", "value": "v", "domain": ".github.com", "path": "/"},
                {"name": "user_session", "value": "v", "domain": ".github.com", "path": "/"},
                {"name": "_gh_sess", "value": "v", "domain": ".github.com", "path": "/"},
            ],
        }
        breakdown = HealthScoreBreakdown()
        scorer._check_critical_cookies(session, breakdown)
        assert len(breakdown.issues) == 0

    def test_github_missing_critical(self, scorer):
        session = {
            "site_name": "github",
            "cookies": [
                {"name": "logged_in", "value": "v", "domain": ".github.com", "path": "/"},
            ],
        }
        breakdown = HealthScoreBreakdown()
        scorer._check_critical_cookies(session, breakdown)
        assert len(breakdown.issues) > 0
        assert "Missing critical cookies" in breakdown.issues[0]
        assert len(breakdown.recommendations) > 0

    def test_unknown_site_no_critical_check(self, scorer):
        session = {
            "site_name": "mysite",
            "cookies": [{"name": "c", "value": "v", "domain": ".mysite.com", "path": "/"}],
        }
        breakdown = HealthScoreBreakdown()
        scorer._check_critical_cookies(session, breakdown)
        assert len(breakdown.issues) == 0


class TestAuthStatusCheck:
    def test_logged_in(self, scorer):
        session = {"auth_status": "logged_in"}
        breakdown = HealthScoreBreakdown()
        scorer._check_auth_status(session, breakdown)
        assert len(breakdown.issues) == 0

    def test_logged_out(self, scorer):
        session = {"auth_status": "logged_out"}
        breakdown = HealthScoreBreakdown()
        scorer._check_auth_status(session, breakdown)
        assert len(breakdown.issues) > 0
        assert "logged_out" in breakdown.issues[0]

    def test_unknown_auth(self, scorer):
        session = {}
        breakdown = HealthScoreBreakdown()
        scorer._check_auth_status(session, breakdown)
        assert len(breakdown.issues) > 0
        assert "unknown" in breakdown.issues[0]


class TestEmptySession:
    def test_empty_cookies_zero_score(self, scorer, empty_session):
        breakdown = scorer.score(empty_session)
        assert breakdown.total_score == 0.0
        assert len(breakdown.issues) > 0

    def test_no_cookies_key(self, scorer):
        breakdown = scorer.score({"site_name": "example"})
        assert breakdown.total_score == 0.0


class TestMixedCookieStates:
    def test_mixed_valid_expired_session_cookies(self, scorer):
        future = int(time.time()) + 7200
        past = int(time.time()) - 3600
        session = {
            "site_name": "example",
            "auth_status": "logged_in",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "cookies": [
                {
                    "name": "valid",
                    "value": "aB3xY9zK2mNpQ7wR4tL8jF5vC1nG6hD0sE",
                    "domain": ".example.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                    "sameSite": "Lax",
                    "expires": future,
                },
                {
                    "name": "expired",
                    "value": "short",
                    "domain": ".example.com",
                    "path": "/",
                    "secure": False,
                    "httpOnly": False,
                    "sameSite": "",
                    "expires": past,
                },
                {
                    "name": "session_cookie",
                    "value": "aB3xY9zK2mNpQ7wR4tL8jF5vC1nG6hD0sE",
                    "domain": ".example.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                    "sameSite": "Lax",
                },
            ],
        }
        breakdown = scorer.score(session)
        assert 0.0 < breakdown.total_score < 100.0
        assert breakdown.expiry_score == 10.0  # some expired

    def test_mixed_flags_cookies(self, scorer):
        session = {
            "site_name": "example",
            "auth_status": "logged_in",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "cookies": [
                {
                    "name": "secure_cookie",
                    "value": "aB3xY9zK2mNpQ7wR4tL8jF5vC1nG6hD0sE",
                    "domain": ".example.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                    "sameSite": "Lax",
                    "expires": int(time.time()) + 7200,
                },
                {
                    "name": "insecure_cookie",
                    "value": "aB3xY9zK2mNpQ7wR4tL8jF5vC1nG6hD0sE",
                    "domain": ".example.com",
                    "path": "/",
                    "secure": False,
                    "httpOnly": False,
                    "sameSite": "",
                    "expires": int(time.time()) + 7200,
                },
            ],
        }
        breakdown = scorer.score(session)
        assert 0.0 < breakdown.flags_score < 25.0


class TestScoreComposition:
    def test_total_equals_sum_of_parts(self, scorer, perfect_session):
        breakdown = scorer.score(perfect_session)
        expected = (
            breakdown.entropy_score
            + breakdown.expiry_score
            + breakdown.flags_score
            + breakdown.freshness_score
        )
        assert breakdown.total_score == pytest.approx(expected, abs=0.01)

    def test_score_range(self, scorer, perfect_session):
        breakdown = scorer.score(perfect_session)
        assert 0.0 <= breakdown.total_score <= 100.0
        assert 0.0 <= breakdown.entropy_score <= 25.0
        assert 0.0 <= breakdown.expiry_score <= 25.0
        assert 0.0 <= breakdown.flags_score <= 25.0
        assert 0.0 <= breakdown.freshness_score <= 25.0


class TestHealthScoreBreakdownDataclass:
    def test_default_values(self):
        b = HealthScoreBreakdown()
        assert b.total_score == 0.0
        assert b.entropy_score == 0.0
        assert b.expiry_score == 0.0
        assert b.flags_score == 0.0
        assert b.freshness_score == 0.0
        assert b.issues == []
        assert b.recommendations == []
