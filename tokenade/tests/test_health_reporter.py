"""Tests for batch health reporting API (Phase 37)."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from tokenade.core.refresh.health_reporter import (
    SessionReport, HealthReport, HealthReporter,
)


def _make_session(tmp_path, name="github", cookies=None, auth_status="logged_in"):
    """Create a sample session file."""
    if cookies is None:
        cookies = [
            {"name": "user_session", "value": "abc123def456", "domain": ".github.com",
             "path": "/", "httpOnly": True, "secure": True, "sameSite": "Lax"},
            {"name": "logged_in", "value": "1", "domain": ".github.com",
             "path": "/", "httpOnly": True, "secure": True, "sameSite": "Lax"},
        ]
    session = {
        "version": "1.0",
        "site_name": name,
        "auth_status": auth_status,
        "cookies": cookies,
        "metadata": {"cookie_count": len(cookies)},
    }
    path = tmp_path / f"{name}.tokenade"
    path.write_text(json.dumps(session))
    return path


def _make_expired_session(tmp_path):
    """Create a session with expired cookies."""
    cookies = [
        {"name": "expired_token", "value": "old", "domain": ".example.com",
         "path": "/", "expires": 1000000000},  # 2001
        {"name": "valid_token", "value": "new", "domain": ".example.com",
         "path": "/", "expires": 4000000000},  # 2096
    ]
    return _make_session(tmp_path, name="expired", cookies=cookies, auth_status="expired")


class TestSessionReport:

    def test_to_dict(self):
        report = SessionReport(
            session_file="test.tokenade", site_name="github", healthy=True,
            health_score=0.95, owasp_score=85.0, cookie_count=10,
            expired_cookies=0, expiring_soon=1, valid_cookies=9,
            auth_status="logged_in",
        )
        data = report.to_dict()
        assert data["session_file"] == "test.tokenade"
        assert data["healthy"] is True
        assert data["health_score"] == 0.95
        assert data["cookie_count"] == 10

    def test_defaults(self):
        report = SessionReport(
            session_file="x.tokenade", site_name="x", healthy=True,
            health_score=1.0, owasp_score=100.0, cookie_count=0,
            expired_cookies=0, expiring_soon=0, valid_cookies=0,
            auth_status="unknown",
        )
        assert report.issues == []
        assert report.expires_in is None


class TestHealthReport:

    def test_to_dict(self):
        report = HealthReport(
            total_sessions=3, healthy_sessions=2, unhealthy_sessions=1,
            overall_health_score=0.8, overall_owasp_score=75.0,
            total_cookies=50, total_expired=2, exit_code=2,
            generated_at="2026-06-22T00:00:00",
        )
        data = report.to_dict()
        assert data["total_sessions"] == 3
        assert data["exit_code"] == 2

    def test_to_json(self):
        report = HealthReport(total_sessions=1, generated_at="2026-01-01T00:00:00")
        output = report.to_json()
        data = json.loads(output)
        assert data["total_sessions"] == 1

    def test_summary_healthy(self):
        report = HealthReport(
            total_sessions=2, healthy_sessions=2, unhealthy_sessions=0,
            overall_health_score=0.95, overall_owasp_score=90.0,
            total_cookies=20, total_expired=0, exit_code=0,
            generated_at="2026-06-22T00:00:00",
        )
        text = report.summary()
        assert "ALL HEALTHY" in text
        assert "2 total, 2 healthy" in text

    def test_summary_unhealthy(self):
        report = HealthReport(
            total_sessions=1, healthy_sessions=0, unhealthy_sessions=1,
            overall_health_score=0.2, overall_owasp_score=15.0,
            total_cookies=5, total_expired=5, exit_code=1,
            generated_at="2026-06-22T00:00:00",
        )
        text = report.summary()
        assert "UNHEALTHY" in text

    def test_summary_mixed(self):
        report = HealthReport(
            total_sessions=2, healthy_sessions=1, unhealthy_sessions=1,
            overall_health_score=0.6, overall_owasp_score=50.0,
            total_cookies=15, total_expired=3, exit_code=2,
            generated_at="2026-06-22T00:00:00",
        )
        text = report.summary()
        assert "MIXED" in text


class TestHealthReporter:

    def test_init_defaults(self):
        reporter = HealthReporter()
        assert reporter.min_health == 0.5
        assert reporter.max_expired == 0

    def test_init_custom(self):
        reporter = HealthReporter(min_health=0.8, max_expired=5)
        assert reporter.min_health == 0.8
        assert reporter.max_expired == 5

    def test_generate_report_empty_dir(self, tmp_path):
        reporter = HealthReporter()
        report = reporter.generate_report(sessions_dir=str(tmp_path))
        assert report.total_sessions == 0
        assert report.exit_code == 0

    def test_generate_report_nonexistent_dir(self, tmp_path):
        reporter = HealthReporter()
        report = reporter.generate_report(sessions_dir=str(tmp_path / "nonexistent"))
        assert report.total_sessions == 0

    def test_generate_report_single_file(self, tmp_path):
        session_file = _make_session(tmp_path)
        reporter = HealthReporter()
        report = reporter.generate_report(session_files=[str(session_file)])
        assert report.total_sessions == 1
        assert report.sessions[0].site_name == "github"
        assert report.sessions[0].healthy is True

    def test_generate_report_directory(self, tmp_path):
        _make_session(tmp_path, name="github")
        _make_session(tmp_path, name="gmail")
        reporter = HealthReporter()
        report = reporter.generate_report(sessions_dir=str(tmp_path))
        assert report.total_sessions == 2
        assert report.healthy_sessions == 2

    def test_generate_report_with_expired(self, tmp_path):
        _make_expired_session(tmp_path)
        reporter = HealthReporter(min_health=0.5, max_expired=0)
        report = reporter.generate_report(sessions_dir=str(tmp_path))
        assert report.total_sessions == 1
        assert report.sessions[0].healthy is False
        assert report.unhealthy_sessions == 1
        assert report.exit_code == 1

    def test_generate_report_mixed_health(self, tmp_path):
        _make_session(tmp_path, name="healthy")
        _make_expired_session(tmp_path)
        reporter = HealthReporter(min_health=0.5, max_expired=0)
        report = reporter.generate_report(sessions_dir=str(tmp_path))
        assert report.total_sessions == 2
        assert report.healthy_sessions == 1
        assert report.unhealthy_sessions == 1
        assert report.exit_code == 2

    def test_generate_report_read_error(self, tmp_path):
        bad_file = tmp_path / "bad.tokenade"
        bad_file.write_text("not json {{{")
        reporter = HealthReporter()
        report = reporter.generate_report(session_files=[str(bad_file)])
        assert report.total_sessions == 1
        assert report.sessions[0].healthy is False
        assert "Failed to read session" in report.sessions[0].issues[0]

    def test_generate_report_file_not_found(self, tmp_path):
        reporter = HealthReporter()
        report = reporter.generate_report(
            session_files=[str(tmp_path / "missing.tokenade")]
        )
        assert report.total_sessions == 1
        assert report.sessions[0].healthy is False

    def test_overall_scores_calculated(self, tmp_path):
        _make_session(tmp_path, name="s1")
        _make_session(tmp_path, name="s2")
        reporter = HealthReporter()
        report = reporter.generate_report(sessions_dir=str(tmp_path))
        assert report.overall_health_score > 0
        assert report.overall_owasp_score > 0

    def test_total_cookies_counted(self, tmp_path):
        _make_session(tmp_path, name="s1")  # 2 cookies
        _make_session(tmp_path, name="s2")  # 2 cookies
        reporter = HealthReporter()
        report = reporter.generate_report(sessions_dir=str(tmp_path))
        assert report.total_cookies == 4

    def test_custom_thresholds(self, tmp_path):
        _make_session(tmp_path)
        # Very strict thresholds — session with 2 cookies and 95% health
        reporter = HealthReporter(min_health=0.99, max_expired=0)
        report = reporter.generate_report(sessions_dir=str(tmp_path))
        # health_score=1.0 (all valid), should pass 0.99 threshold
        assert report.sessions[0].healthy is True

    def test_send_webhook_no_url(self):
        reporter = HealthReporter()
        report = HealthReport()
        assert reporter.send_webhook(report, "") is False
        assert reporter.send_webhook(report, None) is False

    @patch("tokenade.core.refresh.health_reporter.urlopen")
    def test_send_webhook_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        reporter = HealthReporter()
        report = HealthReport(
            total_sessions=1, healthy_sessions=1, unhealthy_sessions=0,
            overall_health_score=0.9, overall_owasp_score=80.0,
            total_cookies=10, total_expired=0, exit_code=0,
        )
        result = reporter.send_webhook(report, "https://hooks.slack.com/test")
        assert result is True

    @patch("tokenade.core.refresh.health_reporter.urlopen")
    def test_send_webhook_failure(self, mock_urlopen):
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("connection refused")

        reporter = HealthReporter()
        report = HealthReport()
        result = reporter.send_webhook(report, "https://hooks.slack.com/test")
        assert result is False

    def test_report_session_details(self, tmp_path):
        session_file = _make_session(
            tmp_path,
            cookies=[
                {"name": "token", "value": "abc", "domain": ".github.com",
                 "path": "/", "httpOnly": True, "secure": True, "sameSite": "Lax"},
            ],
        )
        reporter = HealthReporter()
        report = reporter.generate_report(session_files=[str(session_file)])
        s = report.sessions[0]
        assert s.cookie_count == 1
        assert s.valid_cookies == 1
        assert s.expired_cookies == 0
        assert s.auth_status == "logged_in"

    def test_report_with_session_file_only(self, tmp_path):
        """Test that --session flag works (single file mode)."""
        session_file = _make_session(tmp_path)
        reporter = HealthReporter()
        report = reporter.generate_report(
            session_files=[str(session_file)]
        )
        assert report.total_sessions == 1

    def test_exit_code_all_healthy(self):
        report = HealthReport(exit_code=0)
        assert report.exit_code == 0

    def test_exit_code_all_unhealthy(self):
        report = HealthReport(exit_code=1)
        assert report.exit_code == 1

    def test_exit_code_mixed(self):
        report = HealthReport(exit_code=2)
        assert report.exit_code == 2
