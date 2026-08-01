"""Tests for session health checker and refresher."""

import json
import time
import threading
import pytest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch, MagicMock

from tokenade.core.refresh.health_checker import (
    SessionHealthChecker,
    SessionHealth,
    SessionRefresher,
    SessionProbe,
    RefreshResult,
    generate_health_report,
)


def _start_probe_server(status_code):
    class ProbeHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status_code)
            if 300 <= status_code < 400:
                self.send_header("Location", "/login")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format, *args):
            return

    httpd = HTTPServer(("127.0.0.1", 0), ProbeHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread


class TestSessionHealthChecker:
    def setup_method(self):
        self.checker = SessionHealthChecker()

    def test_check_session_valid(self, tmp_path):
        session_file = tmp_path / "valid.session"
        session = {
            "cookies": [
                {"name": "sid", "domain": ".example.com", "expires": time.time() + 172800},
                {"name": "token", "domain": ".example.com", "expires": time.time() + 259200},
            ],
            "auth_status": "logged_in",
        }
        session_file.write_text(json.dumps(session))
        health = self.checker.check_session(str(session_file))
        assert health.healthy is True
        assert health.health_score == 1.0
        assert health.expires_in is None
        assert health.last_checked is not None

    def test_check_session_no_cookies_key(self, tmp_path):
        session_file = tmp_path / "no_cookies.session"
        session_file.write_text(json.dumps({"auth_status": "logged_in"}))
        health = self.checker.check_session(str(session_file))
        assert health.healthy is False
        assert health.health_score == 0.0
        assert "No cookies in session" in health.issues
        assert "Export session with cookies" in health.recommendations

    def test_check_session_empty_cookies(self, tmp_path):
        session_file = tmp_path / "empty.session"
        session_file.write_text(json.dumps({"cookies": [], "auth_status": "logged_in"}))
        health = self.checker.check_session(str(session_file))
        assert health.healthy is False
        assert "Empty cookie list" in health.issues
        assert "Re-export session from browser" in health.recommendations

    def test_check_session_expired_cookies(self, tmp_path):
        session_file = tmp_path / "expired.session"
        session = {
            "cookies": [
                {"name": "expired1", "domain": ".example.com", "expires": time.time() - 3600},
                {"name": "expired2", "domain": ".example.com", "expires": time.time() - 7200},
                {"name": "valid", "domain": ".example.com", "expires": time.time() + 172800},
            ],
            "auth_status": "logged_in",
        }
        session_file.write_text(json.dumps(session))
        health = self.checker.check_session(str(session_file))
        assert "2 expired cookies" in health.issues
        assert "Re-export session from browser" in health.recommendations

    def test_check_session_expiring_soon(self, tmp_path):
        session_file = tmp_path / "expiring.session"
        session = {
            "cookies": [
                {"name": "soon", "domain": ".example.com", "expires": time.time() + 3600},
                {"name": "valid", "domain": ".example.com", "expires": time.time() + 86400 * 7},
            ],
            "auth_status": "logged_in",
        }
        session_file.write_text(json.dumps(session))
        health = self.checker.check_session(str(session_file))
        assert "1 cookies expiring soon" in health.issues
        assert health.expires_in is not None
        assert health.expires_in > 0

    def test_check_session_millisecond_expiry(self, tmp_path):
        session_file = tmp_path / "ms.session"
        ms_expiry = (time.time() + 172800) * 1000
        session = {
            "cookies": [
                {"name": "ms_cookie", "domain": ".example.com", "expires": ms_expiry},
            ],
            "auth_status": "logged_in",
        }
        session_file.write_text(json.dumps(session))
        health = self.checker.check_session(str(session_file))
        assert health.healthy is True

    def test_check_session_not_logged_in(self, tmp_path):
        session_file = tmp_path / "not_logged.session"
        session = {
            "cookies": [
                {"name": "sid", "domain": ".example.com", "expires": time.time() + 172800},
            ],
            "auth_status": "anonymous",
        }
        session_file.write_text(json.dumps(session))
        health = self.checker.check_session(str(session_file))
        assert "Auth status: anonymous" in health.issues
        assert "Re-login and re-export session" in health.recommendations

    def test_check_session_auth_status_unknown(self, tmp_path):
        session_file = tmp_path / "unknown_auth.session"
        session = {
            "cookies": [
                {"name": "sid", "domain": ".example.com", "expires": time.time() + 172800},
            ],
        }
        session_file.write_text(json.dumps(session))
        health = self.checker.check_session(str(session_file))
        assert "Auth status: unknown" in health.issues

    def test_check_session_expired_and_expiring(self, tmp_path):
        session_file = tmp_path / "mixed.session"
        session = {
            "cookies": [
                {"name": "expired", "domain": ".example.com", "expires": time.time() - 100},
                {"name": "expiring", "domain": ".example.com", "expires": time.time() + 3600},
                {"name": "valid", "domain": ".example.com", "expires": time.time() + 86400 * 7},
            ],
            "auth_status": "logged_in",
        }
        session_file.write_text(json.dumps(session))
        health = self.checker.check_session(str(session_file))
        assert not health.healthy
        assert health.expires_in is not None

    def test_check_session_session_cookie_no_expiry(self, tmp_path):
        session_file = tmp_path / "session_cookie.session"
        session = {
            "cookies": [
                {"name": "session_only", "domain": ".example.com", "expires": 0},
                {"name": "no_expires", "domain": ".example.com"},
            ],
            "auth_status": "logged_in",
        }
        session_file.write_text(json.dumps(session))
        health = self.checker.check_session(str(session_file))
        assert health.healthy is True
        assert health.health_score == 1.0

    def test_check_session_nonexistent_file(self):
        health = self.checker.check_session("/nonexistent/path.session")
        assert health.healthy is False
        assert health.health_score == 0.0
        assert "Failed to read session" in health.issues[0]

    def test_check_session_invalid_json(self, tmp_path):
        session_file = tmp_path / "invalid.session"
        session_file.write_text("not json {{{")
        health = self.checker.check_session(str(session_file))
        assert health.healthy is False

    def test_check_session_health_score_calculation(self, tmp_path):
        session_file = tmp_path / "score.session"
        session = {
            "cookies": [
                {"name": "valid1", "domain": ".example.com", "expires": time.time() + 172800},
                {"name": "valid2", "domain": ".example.com", "expires": time.time() + 172800},
                {"name": "expired", "domain": ".example.com", "expires": time.time() - 100},
            ],
            "auth_status": "logged_in",
        }
        session_file.write_text(json.dumps(session))
        health = self.checker.check_session(str(session_file))
        assert health.health_score == pytest.approx(2 / 3, abs=0.01)

    def test_check_session_healthy_if_only_expiring_soon(self, tmp_path):
        session_file = tmp_path / "only_expiring.session"
        session = {
            "cookies": [
                {"name": "expiring", "domain": ".example.com", "expires": time.time() + 3600},
            ],
            "auth_status": "logged_in",
        }
        session_file.write_text(json.dumps(session))
        health = self.checker.check_session(str(session_file))
        assert health.healthy is True


class TestCheckMultiple:
    def test_check_multiple(self, tmp_path):
        checker = SessionHealthChecker()
        for name in ["s1", "s2"]:
            f = tmp_path / f"{name}.session"
            f.write_text(json.dumps({
                "cookies": [{"name": "c", "domain": ".x.com", "expires": time.time() + 172800}],
                "auth_status": "logged_in",
            }))
        results = checker.check_multiple([str(tmp_path / "s1.session"), str(tmp_path / "s2.session")])
        assert len(results) == 2
        for health in results.values():
            assert health.healthy is True


class TestGenerateHealthReport:
    def test_report_healthy(self):
        health = SessionHealth(
            healthy=True, health_score=1.0, expires_in=7200,
            issues=[], recommendations=[], last_checked="2025-01-01T00:00:00",
        )
        report = generate_health_report(health)
        assert "HEALTHY" in report
        assert "100.0%" in report
        assert "2h 0m" in report

    def test_report_unhealthy(self):
        health = SessionHealth(
            healthy=False, health_score=0.5, expires_in=None,
            issues=["expired cookies"], recommendations=["re-export"],
            last_checked="2025-01-01T00:00:00",
        )
        report = generate_health_report(health)
        assert "UNHEALTHY" in report
        assert "50.0%" in report
        assert "expired cookies" in report
        assert "re-export" in report

    def test_report_no_expiry(self):
        health = SessionHealth(
            healthy=True, health_score=1.0, expires_in=None,
            issues=[], recommendations=[], last_checked="2025-01-01T00:00:00",
        )
        report = generate_health_report(health)
        assert "Expires In" not in report


class TestSessionRefresher:
    def test_refresh_exception_handling(self, tmp_path):
        refresher = SessionRefresher()
        session_file = tmp_path / "nonexistent.session"
        result = refresher.refresh(str(session_file), "chrome")
        assert result.success is False
        assert result.error is not None

    def test_refresh_result_dataclass(self):
        result = RefreshResult(
            success=True, session_file="test", cookies_refreshed=5,
            cookies_total=10, error=None,
        )
        assert result.success is True
        assert result.cookies_refreshed == 5

    def test_refresh_no_profile_found(self, tmp_path):
        session_file = tmp_path / "test.session"
        session_file.write_text(json.dumps({
            "cookies": [{"name": "c", "domain": ".x.com", "expires": time.time() + 86400}],
            "auth_status": "logged_in",
            "metadata": {"exported_at": "2025-01-01"},
        }))
        refresher = SessionRefresher()
        with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery") as mock_disc:
            mock_instance = MagicMock()
            mock_instance.discover_all.return_value = {"chrome": []}
            mock_disc.return_value = mock_instance
            result = refresher.refresh(str(session_file), "chrome")
            assert result.success is False
            assert "No profile found for chrome" in result.error

    def test_refresh_with_custom_browser_path(self, tmp_path):
        session_file = tmp_path / "test.session"
        session_file.write_text(json.dumps({
            "cookies": [{"name": "c", "domain": ".x.com", "expires": time.time() + 86400}],
            "auth_status": "logged_in",
            "metadata": {},
        }))
        refresher = SessionRefresher()
        with patch("tokenade.core.importer.cookie_extractor.CookieExtractor") as mock_ext, \
                patch("tokenade.core.importer.session_packager.SessionPackager") as mock_pack:
            mock_extractor = MagicMock()
            mock_extractor.extract.return_value = [
                {"name": "c", "value": "v", "domain": ".x.com"},
            ]
            mock_ext.return_value = mock_extractor

            mock_packager = MagicMock()
            mock_packager.package.return_value = {
                "cookies": [],
                "metadata": {},
            }
            mock_pack.return_value = mock_packager

            result = refresher.refresh(
                str(session_file), "chrome",
                source_browser_path="/custom/path",
            )
            assert result.success is True

    def test_refresh_no_matching_cookies(self, tmp_path):
        session_file = tmp_path / "test.session"
        session_file.write_text(json.dumps({
            "cookies": [{"name": "c", "domain": ".example.com", "expires": time.time() + 86400}],
            "auth_status": "logged_in",
            "metadata": {},
        }))
        refresher = SessionRefresher()
        with patch("tokenade.core.importer.cookie_extractor.CookieExtractor") as mock_ext:
            mock_extractor = MagicMock()
            mock_extractor.extract.return_value = [
                {"name": "c", "value": "v", "domain": ".nomatch.com"},
            ]
            mock_ext.return_value = mock_extractor
            result = refresher.refresh(
                str(session_file), "chrome",
                source_browser_path="/custom/path",
            )
            assert result.success is False
            assert "No matching cookies found" in result.error

    def test_refresh_with_site_config_domains(self, tmp_path):
        session_file = tmp_path / "test.session"
        session_file.write_text(json.dumps({
            "cookies": [{"name": "c", "domain": ".example.com", "expires": time.time() + 86400}],
            "auth_status": "logged_in",
            "metadata": {},
        }))
        refresher = SessionRefresher()
        with patch("tokenade.core.importer.cookie_extractor.CookieExtractor") as mock_ext, \
                patch("tokenade.core.importer.session_packager.SessionPackager") as mock_pack:
            mock_extractor = MagicMock()
            mock_extractor.extract.return_value = [
                {"name": "c", "value": "v", "domain": ".example.com"},
            ]
            mock_ext.return_value = mock_extractor

            mock_packager = MagicMock()
            mock_packager.package.return_value = {
                "cookies": [],
                "metadata": {},
            }
            mock_pack.return_value = mock_packager

            result = refresher.refresh(
                str(session_file), "chrome",
                source_browser_path="/custom/path",
                site_config={"domains": [".example.com", ".api.example.com"]},
            )
            assert result.success is True

    def test_refresh_with_matching_profile_name(self, tmp_path):
        session_file = tmp_path / "test.session"
        session_file.write_text(json.dumps({
            "cookies": [{"name": "c", "domain": ".example.com", "expires": time.time() + 86400}],
            "auth_status": "logged_in",
            "metadata": {},
        }))
        refresher = SessionRefresher()
        with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery") as mock_disc, \
                patch("tokenade.core.importer.cookie_extractor.CookieExtractor") as mock_ext, \
                patch("tokenade.core.importer.session_packager.SessionPackager") as mock_pack:
            mock_profile = MagicMock()
            mock_profile.browser = "chrome"
            mock_profile.name = "Default"
            mock_profile.path = "/path/to/profile"
            mock_instance = MagicMock()
            mock_instance.discover_all.return_value = {"chrome": [mock_profile]}
            mock_disc.return_value = mock_instance

            mock_extractor = MagicMock()
            mock_extractor.extract.return_value = [
                {"name": "c", "value": "v", "domain": ".example.com"},
            ]
            mock_ext.return_value = mock_extractor

            mock_packager = MagicMock()
            mock_packager.package.return_value = {
                "cookies": [],
                "metadata": {},
            }
            mock_pack.return_value = mock_packager

            result = refresher.refresh(
                str(session_file), "chrome",
                source_profile="Default",
            )
            assert result.success is True

    def test_refresh_filters_dot_domains(self, tmp_path):
        session_file = tmp_path / "test.session"
        session_file.write_text(json.dumps({
            "cookies": [{"name": "c", "domain": ".example.com", "expires": time.time() + 86400}],
            "auth_status": "logged_in",
            "metadata": {},
        }))
        refresher = SessionRefresher()
        with patch("tokenade.core.importer.cookie_extractor.CookieExtractor") as mock_ext, \
                patch("tokenade.core.importer.session_packager.SessionPackager") as mock_pack:
            mock_extractor = MagicMock()
            mock_extractor.extract.return_value = [
                {"name": "c", "value": "v", "domain": "example.com"},
                {"name": "c2", "value": "v2", "domain": "sub.example.com"},
            ]
            mock_ext.return_value = mock_extractor

            mock_packager = MagicMock()
            mock_packager.package.return_value = {
                "cookies": [],
                "metadata": {},
            }
            mock_pack.return_value = mock_packager

            result = refresher.refresh(
                str(session_file), "chrome",
                source_browser_path="/custom/path",
            )
            assert result.success is True

    def test_refresh_preserves_metadata(self, tmp_path):
        session_file = tmp_path / "test.session"
        session_file.write_text(json.dumps({
            "cookies": [{"name": "c", "domain": ".x.com", "expires": time.time() + 86400}],
            "auth_status": "logged_in",
            "metadata": {"exported_at": "2025-01-01", "profile": "Default"},
            "local_storage": {"key": "value"},
        }))
        refresher = SessionRefresher()
        with patch("tokenade.core.importer.cookie_extractor.CookieExtractor") as mock_ext, \
                patch("tokenade.core.importer.session_packager.SessionPackager") as mock_pack:
            mock_extractor = MagicMock()
            mock_extractor.extract.return_value = [
                {"name": "c", "value": "v", "domain": ".x.com"},
            ]
            mock_ext.return_value = mock_extractor

            mock_packager = MagicMock()
            mock_packager.package.return_value = {
                "cookies": [],
                "metadata": {},
            }
            mock_pack.return_value = mock_packager

            result = refresher.refresh(
                str(session_file), "chrome",
                source_browser_path="/custom/path",
            )
            assert result.success is True
            call_args = mock_packager.package.call_args
            assert call_args[1]["local_storage"] == {"key": "value"}

            save_call_args = mock_packager.save.call_args
            saved_session = save_call_args[0][0]
            assert saved_session["metadata"]["refreshed_from"] == str(session_file)
            assert saved_session["metadata"]["original_exported_at"] == "2025-01-01"


class TestSessionProbe:
    def test_probe_redirect_to_login_is_invalid(self, tmp_path):
        httpd, thread = _start_probe_server(302)
        session_file = tmp_path / "session.tokenade"
        session_file.write_text(json.dumps({
            "cookies": [{"name": "sid", "value": "abc", "domain": "127.0.0.1", "path": "/"}],
            "metadata": {
                "site_handler": {
                    "session_check_url": f"http://127.0.0.1:{httpd.server_port}/settings/profile"
                }
            },
        }))

        try:
            assert SessionProbe.probe(str(session_file), timeout=2) is False
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

    def test_probe_200_is_valid(self, tmp_path):
        httpd, thread = _start_probe_server(200)
        session_file = tmp_path / "session.tokenade"
        session_file.write_text(json.dumps({
            "cookies": [{"name": "sid", "value": "abc", "domain": "127.0.0.1", "path": "/"}],
            "metadata": {
                "site_handler": {
                    "session_check_url": f"http://127.0.0.1:{httpd.server_port}/settings/profile"
                }
            },
        }))

        try:
            assert SessionProbe.probe(str(session_file), timeout=2) is True
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

    def test_probe_ignores_validate_url_without_session_check_url(self, tmp_path):
        httpd, thread = _start_probe_server(200)
        session_file = tmp_path / "session.tokenade"
        session_file.write_text(json.dumps({
            "cookies": [{"name": "sid", "value": "abc", "domain": "127.0.0.1", "path": "/"}],
            "metadata": {
                "site_handler": {
                    "validate_url": f"http://127.0.0.1:{httpd.server_port}/dashboard"
                }
            },
        }))

        try:
            assert SessionProbe.probe(str(session_file), timeout=2) is None
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)
