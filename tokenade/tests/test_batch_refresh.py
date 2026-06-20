"""Tests for batch session refresh."""
import json
import time
import pytest
from pathlib import Path

from tokenade.core.refresh.batch_refresh import (
    BatchRefresher,
    BatchRefreshReport,
    SessionRefreshResult,
)


class TestSessionRefreshResult:
    def test_success(self):
        result = SessionRefreshResult(
            session_file="test.tokenade",
            site_name="google",
            success=True,
            method="oauth",
        )
        assert result.success
        assert result.site_name == "google"

    def test_failure(self):
        result = SessionRefreshResult(
            session_file="test.tokenade",
            site_name="google",
            success=False,
            method="oauth",
            error="token expired",
        )
        assert not result.success
        assert result.error == "token expired"


class TestBatchRefreshReport:
    def test_success_rate(self):
        report = BatchRefreshReport(total=10, succeeded=7, failed=3)
        assert report.success_rate == 0.7

    def test_success_rate_zero(self):
        report = BatchRefreshReport(total=0)
        assert report.success_rate == 0.0

    def test_summary(self):
        report = BatchRefreshReport(
            total=3,
            succeeded=2,
            failed=1,
            oauth_refreshed=1,
            cookie_refreshed=1,
            results=[
                SessionRefreshResult("a.tokenade", "google", True, "oauth"),
                SessionRefreshResult("b.tokenade", "github", True, "cookie"),
                SessionRefreshResult("c.tokenade", "reddit", False, "oauth", error="failed"),
            ],
        )
        summary = report.summary()
        assert "Total: 3" in summary
        assert "Succeeded: 2" in summary
        assert "Failed: 1" in summary
        assert "OAuth refreshed: 1" in summary
        assert "Cookie refreshed: 1" in summary
        assert "66" in summary  # success rate as percentage


class TestBatchRefresher:
    def test_discover_sessions(self, tmp_path):
        # Create test session files
        for name in ["google.tokenade", "github.tokenade", "readme.txt"]:
            (tmp_path / name).write_text("{}")

        batch = BatchRefresher(sessions_dir=str(tmp_path))
        sessions = batch.discover_sessions()

        assert len(sessions) == 2
        names = [s.name for s in sessions]
        assert "google.tokenade" in names
        assert "github.tokenade" in names
        assert "readme.txt" not in names

    def test_discover_empty_dir(self, tmp_path):
        batch = BatchRefresher(sessions_dir=str(tmp_path))
        sessions = batch.discover_sessions()
        assert len(sessions) == 0

    def test_discover_nonexistent_dir(self):
        batch = BatchRefresher(sessions_dir="/nonexistent/path")
        sessions = batch.discover_sessions()
        assert len(sessions) == 0

    def test_refresh_all_no_files(self, tmp_path):
        batch = BatchRefresher(sessions_dir=str(tmp_path))
        report = batch.refresh_all()
        assert report.total == 0
        assert report.succeeded == 0

    def test_refresh_all_skip_not_expired(self, tmp_path):
        session_file = tmp_path / "test.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [],
            "tokens": [
                {"type": "access_token", "value": "acc", "expires_at": time.time() + 3600},
            ],
            "metadata": {},
        }
        session_file.write_text(json.dumps(session_data))

        batch = BatchRefresher(sessions_dir=str(tmp_path))
        report = batch.refresh_all()

        assert report.total == 1
        assert report.succeeded == 1
        assert report.failed == 0

    def test_refresh_all_force(self, tmp_path):
        session_file = tmp_path / "test.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [],
            "tokens": [
                {"type": "access_token", "value": "acc", "expires_at": time.time() + 3600},
            ],
            "oauth_config": {
                "token_endpoint": "https://oauth2.googleapis.com/token",
                "client_id": "test.apps.googleusercontent.com",
            },
            "metadata": {"refresh_count": 0},
        }
        session_file.write_text(json.dumps(session_data))

        batch = BatchRefresher(sessions_dir=str(tmp_path))

        mock_result = type("RefreshResult", (), {
            "success": True,
            "tokens": type("Tokens", (), {
                "access_token": "new-acc",
                "expires_in": 3600,
            })(),
            "error": None,
            "duration_ms": 100.0,
        })()

        with patch("tokenade.core.refresh.oauth_refresh.SessionOAuthManager") as MockManager:
            instance = MockManager.return_value
            instance.refresh.return_value = mock_result
            instance.get_status.return_value = {"has_refresh_token": True}
            report = batch.refresh_all(force=True)

        assert report.total == 1

    def test_refresh_all_with_session_files(self, tmp_path):
        session_file = tmp_path / "test.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [],
            "tokens": [],
            "metadata": {},
        }
        session_file.write_text(json.dumps(session_data))

        batch = BatchRefresher(sessions_dir=str(tmp_path))
        report = batch.refresh_all(session_files=[str(session_file)])

        assert report.total == 1


from unittest.mock import patch
