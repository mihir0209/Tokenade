"""FormatImporter, SessionHealthChecker helpers, SessionLoader normalize, fingerprint helpers.

Formerly test_coverage_boost — primary suite for FormatImporter (no other dedicated file).
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tokenade.core.importer.format_importer import FormatImporter
from tokenade.core.refresh.health_checker import (
    SessionHealthChecker, SessionHealth, RefreshResult, generate_health_report,
)
from tokenade.core.importer.session_loader import SessionLoader
from tokenade.core.fingerprint.manager import BrowserFingerprint, FingerprintManager


# ============================================================
# FormatImporter
# ============================================================

class TestFormatImporterCookieHeader:
    def test_empty_header(self):
        result = FormatImporter.from_cookie_header("")
        assert result["cookies"] == []
        assert result["metadata"]["extraction_method"] == "import_cookie_header"

    def test_none_header(self):
        result = FormatImporter.from_cookie_header(None)
        assert result["cookies"] == []

    def test_whitespace_header(self):
        result = FormatImporter.from_cookie_header("   ")
        assert result["cookies"] == []

    def test_single_cookie(self):
        result = FormatImporter.from_cookie_header("session=abc123", domain=".github.com")
        cookies = result["cookies"]
        assert len(cookies) == 1
        assert cookies[0]["name"] == "session"
        assert cookies[0]["value"] == "abc123"
        assert cookies[0]["domain"] == ".github.com"

    def test_multiple_cookies(self):
        result = FormatImporter.from_cookie_header("a=1; b=2; c=3")
        assert len(result["cookies"]) == 3
        assert result["cookies"][0]["name"] == "a"
        assert result["cookies"][2]["name"] == "c"

    def test_value_with_equals(self):
        result = FormatImporter.from_cookie_header("token=abc=def=ghi")
        assert result["cookies"][0]["value"] == "abc=def=ghi"

    def test_empty_pair(self):
        result = FormatImporter.from_cookie_header("; ; a=1")
        assert len(result["cookies"]) == 1

    def test_pair_without_equals(self):
        result = FormatImporter.from_cookie_header("badpair; a=1")
        assert len(result["cookies"]) == 1

    def test_domain_applied(self):
        result = FormatImporter.from_cookie_header("x=1", domain="example.com")
        assert result["cookies"][0]["domain"] == "example.com"


class TestFormatImporterPlaywright:
    def test_basic_import(self, tmp_path):
        data = {
            "cookies": [
                {"name": "sid", "value": "abc", "domain": ".test.com", "path": "/",
                 "secure": True, "httpOnly": True, "sameSite": "Strict", "expires": 1893456000},
            ],
            "origins": [
                {"origin": "https://test.com", "localStorage": [{"name": "key", "value": "val"}]}
            ],
        }
        f = tmp_path / "state.json"
        f.write_text(json.dumps(data))

        result = FormatImporter.from_playwright_storagestate(str(f))
        assert len(result["cookies"]) == 1
        assert result["cookies"][0]["name"] == "sid"
        assert result["cookies"][0]["expires"] == 1893456000
        assert result["local_storage"]["test.com:key"] == "val"

    def test_missing_expires(self, tmp_path):
        data = {"cookies": [{"name": "a", "value": "b", "domain": ".x.com"}]}
        f = tmp_path / "state.json"
        f.write_text(json.dumps(data))

        result = FormatImporter.from_playwright_storagestate(str(f))
        assert "expires" not in result["cookies"][0]

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            FormatImporter.from_playwright_storagestate("/nonexistent/file.json")


class TestFormatImporterNetscape:
    def test_basic_import(self, tmp_path):
        content = "# Netscape HTTP Cookie File\n"
        content += ".example.com\tTRUE\t/\tTRUE\t1893456000\tsession\tabc123\n"
        content += ".example.com\tTRUE\t/api\tFALSE\t0\ttoken\txyz\n"
        f = tmp_path / "cookies.txt"
        f.write_text(content)

        result = FormatImporter.from_netscape(str(f))
        assert len(result["cookies"]) == 2
        assert result["cookies"][0]["name"] == "session"
        assert result["cookies"][0]["secure"] is True
        assert result["cookies"][0]["expires"] == 1893456000
        assert result["cookies"][1]["name"] == "token"

    def test_httponly_prefix(self, tmp_path):
        # Netscape #HttpOnly_ domain prefix is a real extension — parse as httpOnly
        content = (
            ".example.com\tTRUE\t/\tTRUE\t0\tsid\tval\n"
            "#HttpOnly_.example.com\tTRUE\t/\tTRUE\t0\thsid\thval\n"
        )
        f = tmp_path / "cookies.txt"
        f.write_text(content)

        result = FormatImporter.from_netscape(str(f))
        assert len(result["cookies"]) == 2
        by_name = {c["name"]: c for c in result["cookies"]}
        assert by_name["sid"]["httpOnly"] is False
        assert by_name["hsid"]["httpOnly"] is True
        assert by_name["hsid"]["domain"] == ".example.com"

    def test_comments_skipped(self, tmp_path):
        content = "# comment\n# another comment\n.example.com\tTRUE\t/\tTRUE\t0\ta\t1\n"
        f = tmp_path / "cookies.txt"
        f.write_text(content)

        result = FormatImporter.from_netscape(str(f))
        assert len(result["cookies"]) == 1

    def test_invalid_expires(self, tmp_path):
        content = ".example.com\tTRUE\t/\tTRUE\tinvalid\ta\t1\n"
        f = tmp_path / "cookies.txt"
        f.write_text(content)

        result = FormatImporter.from_netscape(str(f))
        assert "expires" not in result["cookies"][0]

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            FormatImporter.from_netscape("/nonexistent/file.txt")


class TestFormatImporterJson:
    def test_list_input(self, tmp_path):
        data = [{"name": "a", "value": "1", "domain": ".x.com"}]
        f = tmp_path / "cookies.json"
        f.write_text(json.dumps(data))

        result = FormatImporter.from_json(str(f))
        assert len(result["cookies"]) == 1
        assert result["cookies"][0]["name"] == "a"

    def test_dict_with_cookies(self, tmp_path):
        data = {"cookies": [{"name": "a", "value": "1"}]}
        f = tmp_path / "cookies.json"
        f.write_text(json.dumps(data))

        result = FormatImporter.from_json(str(f))
        assert len(result["cookies"]) == 1

    def test_single_cookie_dict(self, tmp_path):
        data = {"name": "a", "value": "1", "domain": ".x.com"}
        f = tmp_path / "cookies.json"
        f.write_text(json.dumps(data))

        result = FormatImporter.from_json(str(f))
        assert len(result["cookies"]) == 1

    def test_empty_list(self, tmp_path):
        f = tmp_path / "cookies.json"
        f.write_text("[]")

        result = FormatImporter.from_json(str(f))
        assert result["cookies"] == []

    def test_with_expires(self, tmp_path):
        data = [{"name": "a", "value": "1", "expires": 1893456000}]
        f = tmp_path / "cookies.json"
        f.write_text(json.dumps(data))

        result = FormatImporter.from_json(str(f))
        assert result["cookies"][0]["expires"] == 1893456000

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            FormatImporter.from_json("/nonexistent/file.json")


class TestFormatImporterDetectFormat:
    def test_detect_playwright(self, tmp_path):
        data = {"cookies": [], "origins": []}
        f = tmp_path / "file.json"
        f.write_text(json.dumps(data))
        assert FormatImporter.detect_format(str(f)) == "playwright"

    def test_detect_json_list(self, tmp_path):
        f = tmp_path / "file.json"
        f.write_text('[{"name": "a"}]')
        assert FormatImporter.detect_format(str(f)) == "json"

    def test_detect_json_dict(self, tmp_path):
        f = tmp_path / "file.json"
        f.write_text('{"cookies": []}')
        assert FormatImporter.detect_format(str(f)) == "json"

    def test_detect_netscape_header(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tTRUE\t0\ta\t1\n")
        assert FormatImporter.detect_format(str(f)) == "netscape"

    def test_detect_curl_header(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("# curl\n.example.com\tTRUE\t/\tTRUE\t0\ta\t1\n")
        assert FormatImporter.detect_format(str(f)) in ("netscape", "curl")

    def test_detect_netscape_tab_separated(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text(".example.com\tTRUE\t/\tTRUE\t0\ta\t1\n")
        assert FormatImporter.detect_format(str(f)) == "netscape"

    def test_detect_unknown(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("just some random text\nnot a cookie file")
        assert FormatImporter.detect_format(str(f)) == "unknown"

    def test_detect_nonexistent(self):
        assert FormatImporter.detect_format("/nonexistent/file") == "unknown"


class TestFormatImporterBuildSession:
    def test_build_session(self):
        cookies = [{"name": "a", "value": "1"}]
        result = FormatImporter._build_session(cookies, {"k": "v"}, "test_format")
        assert result["version"] in ("2.0", "3.0")
        assert result["cookies"] == cookies
        assert result["local_storage"] == {"k": "v"}
        assert result["metadata"]["extraction_method"] == "import_test_format"
        assert result["metadata"]["cookie_count"] == 1
        assert result["metadata"]["local_storage_count"] == 1


class TestFormatImporterConvertFile:
    def test_convert_json_array(self, tmp_path):
        data = [
            {
                "domain": ".claude.ai",
                "name": "sessionKey",
                "value": "sk-test",
                "path": "/",
                "httpOnly": True,
                "expires": 1893456000,
                "secure": True,
            },
            {
                "domain": "claude.ai",
                "name": "cf_clearance",
                "value": "x",
                "path": "/",
                "expires": 1893456000,
                "secure": True,
            },
        ]
        src = tmp_path / "sample_cookie.txt"
        src.write_text(json.dumps(data))
        out = tmp_path / "out.tokenade"
        result = FormatImporter.convert_file(str(src), str(out), format_hint="auto")
        assert result["success"] is True
        assert result["cookie_count"] == 2
        assert result["format"] == "json"
        assert Path(result["output_path"]).exists()
        saved = json.loads(Path(result["output_path"]).read_text())
        assert len(saved["cookies"]) == 2
        assert saved["cookies"][0]["name"] == "sessionKey"

    def test_convert_expirationDate_alias(self, tmp_path):
        data = [{"name": "a", "value": "1", "domain": ".x.com", "expirationDate": 1893456000}]
        src = tmp_path / "c.json"
        src.write_text(json.dumps(data))
        out = tmp_path / "c.tokenade"
        result = FormatImporter.convert_file(str(src), str(out))
        assert result["success"] is True
        saved = json.loads(Path(out).read_text())
        assert saved["cookies"][0]["expires"] == 1893456000

    def test_convert_missing_file(self, tmp_path):
        result = FormatImporter.convert_file(str(tmp_path / "nope"), str(tmp_path / "o.tokenade"))
        assert result["success"] is False
        assert "not found" in (result.get("error") or "").lower()

    def test_convert_empty_cookies(self, tmp_path):
        src = tmp_path / "empty.json"
        src.write_text("[]")
        result = FormatImporter.convert_file(str(src), str(tmp_path / "o.tokenade"))
        assert result["success"] is False

    def test_convert_har(self, tmp_path):
        har = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "cookies": [
                                {"name": "sid", "value": "abc", "domain": ".ex.com", "path": "/"},
                            ],
                            "headers": [],
                        },
                        "response": {"cookies": [], "headers": []},
                    }
                ]
            }
        }
        src = tmp_path / "a.har"
        src.write_text(json.dumps(har))
        out = tmp_path / "h.tokenade"
        result = FormatImporter.convert_file(str(src), str(out), format_hint="auto")
        assert result["success"] is True
        assert result["format"] == "har"
        assert result["cookie_count"] == 1

    def test_convert_header_file(self, tmp_path):
        src = tmp_path / "h.txt"
        src.write_text("Cookie: a=1; b=2\n")
        out = tmp_path / "h.tokenade"
        result = FormatImporter.convert_file(
            str(src), str(out), format_hint="header", domain=".ex.com",
        )
        assert result["success"] is True
        saved = json.loads(Path(out).read_text())
        assert len(saved["cookies"]) == 2
        assert saved["cookies"][0]["domain"] == ".ex.com"

    def test_convert_csv(self, tmp_path):
        src = tmp_path / "c.csv"
        src.write_text("name,value,domain,path,secure\nsid,abc,.ex.com,/,true\n")
        out = tmp_path / "c.tokenade"
        result = FormatImporter.convert_file(str(src), str(out), format_hint="csv")
        assert result["success"] is True
        assert result["cookie_count"] == 1

    def test_convert_set_cookie(self, tmp_path):
        src = tmp_path / "sc.txt"
        src.write_text("Set-Cookie: session=xyz; Path=/; Secure; HttpOnly; Domain=.ex.com\n")
        out = tmp_path / "sc.tokenade"
        result = FormatImporter.convert_file(str(src), str(out), format_hint="set-cookie")
        assert result["success"] is True
        saved = json.loads(Path(out).read_text())
        assert saved["cookies"][0]["name"] == "session"
        assert saved["cookies"][0]["secure"] is True
        assert saved["cookies"][0]["httpOnly"] is True


# ============================================================
# Health Checker
# ============================================================

class TestSessionHealthChecker:
    def test_check_healthy_session(self, tmp_path):
        session_file = tmp_path / "session.json"
        session_file.write_text(json.dumps({
            "cookies": [
                {"name": "sid", "value": "abc", "expires": int(time.time()) + 86400 * 7},
            ],
            "auth_status": "logged_in",
        }))

        checker = SessionHealthChecker()
        health = checker.check_session(str(session_file))
        assert health.healthy is True
        assert health.health_score == 1.0

    def test_check_expired_cookies(self, tmp_path):
        session_file = tmp_path / "session.json"
        session_file.write_text(json.dumps({
            "cookies": [
                {"name": "old", "value": "abc", "expires": int(time.time()) - 3600},
                {"name": "new", "value": "xyz", "expires": int(time.time()) + 86400},
            ],
            "auth_status": "logged_in",
        }))

        checker = SessionHealthChecker()
        health = checker.check_session(str(session_file))
        assert health.health_score < 1.0
        assert any("expired" in i for i in health.issues)

    def test_check_expiring_soon(self, tmp_path):
        session_file = tmp_path / "session.json"
        session_file.write_text(json.dumps({
            "cookies": [
                {"name": "soon", "value": "abc", "expires": int(time.time()) + 3600},
            ],
            "auth_status": "logged_in",
        }))

        checker = SessionHealthChecker()
        health = checker.check_session(str(session_file))
        assert health.expires_in is not None
        assert health.expires_in > 0

    def test_check_no_cookies_key(self, tmp_path):
        session_file = tmp_path / "session.json"
        session_file.write_text(json.dumps({"auth_status": "logged_in"}))

        checker = SessionHealthChecker()
        health = checker.check_session(str(session_file))
        assert health.healthy is False
        assert health.health_score == 0.0

    def test_check_empty_cookies(self, tmp_path):
        session_file = tmp_path / "session.json"
        session_file.write_text(json.dumps({"cookies": [], "auth_status": "logged_in"}))

        checker = SessionHealthChecker()
        health = checker.check_session(str(session_file))
        assert health.healthy is False

    def test_check_not_logged_in(self, tmp_path):
        session_file = tmp_path / "session.json"
        session_file.write_text(json.dumps({
            "cookies": [{"name": "a", "value": "b"}],
            "auth_status": "unknown",
        }))

        checker = SessionHealthChecker()
        health = checker.check_session(str(session_file))
        assert any("auth" in i.lower() for i in health.issues)

    def test_check_session_cookie_no_expiry(self, tmp_path):
        session_file = tmp_path / "session.json"
        session_file.write_text(json.dumps({
            "cookies": [{"name": "a", "value": "b"}],
            "auth_status": "logged_in",
        }))

        checker = SessionHealthChecker()
        health = checker.check_session(str(session_file))
        assert health.health_score == 1.0

    def test_check_invalid_file(self, tmp_path):
        session_file = tmp_path / "bad.json"
        session_file.write_text("not json {{{")

        checker = SessionHealthChecker()
        health = checker.check_session(str(session_file))
        assert health.healthy is False

    def test_check_milliseconds_expires(self, tmp_path):
        session_file = tmp_path / "session.json"
        ms_expires = (int(time.time()) + 86400 * 7) * 1000  # 7 days from now in ms
        session_file.write_text(json.dumps({
            "cookies": [{"name": "a", "value": "b", "expires": ms_expires}],
            "auth_status": "logged_in",
        }))

        checker = SessionHealthChecker()
        health = checker.check_session(str(session_file))
        assert health.health_score == 1.0

    def test_check_multiple(self, tmp_path):
        for i in range(3):
            f = tmp_path / f"session_{i}.json"
            f.write_text(json.dumps({
                "cookies": [{"name": "a", "value": "b"}],
                "auth_status": "logged_in",
            }))

        checker = SessionHealthChecker()
        files = [str(tmp_path / f"session_{i}.json") for i in range(3)]
        results = checker.check_multiple(files)
        assert len(results) == 3
        assert all(h.healthy for h in results.values())


class TestGenerateHealthReport:
    def test_healthy_report(self):
        health = SessionHealth(
            healthy=True, health_score=1.0, expires_in=86400,
            issues=[], recommendations=[], last_checked="2025-01-01T00:00:00"
        )
        report = generate_health_report(health)
        assert "HEALTHY" in report
        assert "100.0%" in report
        assert "24h 0m" in report

    def test_unhealthy_report(self):
        health = SessionHealth(
            healthy=False, health_score=0.5, issues=["2 expired cookies"],
            recommendations=["Re-export"], last_checked="2025-01-01T00:00:00"
        )
        report = generate_health_report(health)
        assert "UNHEALTHY" in report
        assert "expired" in report


class TestRefreshResult:
    def test_dataclass(self):
        r = RefreshResult(success=True, session_file="s.tokenade", cookies_refreshed=5, cookies_total=10)
        assert r.error is None
        r2 = RefreshResult(success=False, session_file="s.tokenade", cookies_refreshed=0, cookies_total=0, error="fail")
        assert r2.error == "fail"


# ============================================================
# Session Loader Helpers
# ============================================================

class TestSessionLoaderNormalizeCookie:
    def setup_method(self):
        self.loader = SessionLoader(fp_manager=MagicMock())

    def test_basic_cookie(self):
        cookie = {"name": "a", "value": "1", "domain": ".x.com", "path": "/"}
        result = self.loader._normalize_cookie(cookie)
        assert result["name"] == "a"
        assert result["value"] == "1"
        assert result["domain"] == ".x.com"

    def test_firefox_milliseconds(self):
        cookie = {"name": "a", "value": "1", "expires": 1893456000000}
        result = self.loader._normalize_cookie(cookie)
        assert result["expires"] < 1893456000000  # Converted to seconds

    def test_seconds_expires(self):
        cookie = {"name": "a", "value": "1", "expires": 1893456000}
        result = self.loader._normalize_cookie(cookie)
        assert result["expires"] == 1893456000

    def test_session_cookie_no_expires(self):
        cookie = {"name": "a", "value": "1"}
        result = self.loader._normalize_cookie(cookie)
        assert "expires" not in result

    def test_samesite_none_forces_secure(self):
        cookie = {"name": "a", "value": "1", "sameSite": "None", "secure": False}
        result = self.loader._normalize_cookie(cookie)
        assert result["secure"] is True

    def test_secure_preserved(self):
        cookie = {"name": "a", "value": "1", "secure": True}
        result = self.loader._normalize_cookie(cookie)
        assert result["secure"] is True

    def test_httponly_preserved(self):
        cookie = {"name": "a", "value": "1", "httpOnly": True}
        result = self.loader._normalize_cookie(cookie)
        assert result["httpOnly"] is True

    def test_samesite_preserved(self):
        cookie = {"name": "a", "value": "1", "sameSite": "Strict"}
        result = self.loader._normalize_cookie(cookie)
        assert result["sameSite"] == "Strict"


class TestSessionLoaderLoadFile:
    def test_load_existing(self, tmp_path):
        f = tmp_path / "session.json"
        f.write_text(json.dumps({"cookies": []}))

        loader = SessionLoader(fp_manager=MagicMock())
        result = loader.load_file(str(f))
        assert result["cookies"] == []

    def test_load_missing(self):
        loader = SessionLoader(fp_manager=MagicMock())
        with pytest.raises(FileNotFoundError):
            loader.load_file("/nonexistent/file.json")

    def test_get_last_result(self):
        loader = SessionLoader(fp_manager=MagicMock())
        assert loader.get_last_result() is None


class TestSessionLoaderInjectCookies:
    def test_empty_cookies(self):
        mock_browser = MagicMock()
        loader = SessionLoader(fp_manager=MagicMock())
        count = loader.inject_cookies(mock_browser, [])
        assert count == 0

    def test_valid_cookies(self):
        mock_browser = MagicMock()
        loader = SessionLoader(fp_manager=MagicMock())
        cookies = [{"name": "a", "value": "1", "domain": ".x.com"}]
        count = loader.inject_cookies(mock_browser, cookies)
        assert count == 1
        mock_browser.add_cookies.assert_called_once()

    def test_invalid_cookie_skipped(self):
        mock_browser = MagicMock()
        loader = SessionLoader(fp_manager=MagicMock())
        cookies = [{"domain": ".x.com"}]  # Missing name/value
        count = loader.inject_cookies(mock_browser, cookies)
        assert count == 0

    def test_mixed_valid_invalid(self):
        mock_browser = MagicMock()
        loader = SessionLoader(fp_manager=MagicMock())
        cookies = [
            {"name": "a", "value": "1"},
            {"domain": ".x.com"},  # invalid
            {"name": "b", "value": "2"},
        ]
        count = loader.inject_cookies(mock_browser, cookies)
        assert count == 2


class TestSessionLoaderInjectLocalStorage:
    def test_empty(self):
        mock_browser = MagicMock()
        loader = SessionLoader(fp_manager=MagicMock())
        count = loader.inject_local_storage(mock_browser, {})
        assert count == 0

    def test_with_origin(self):
        mock_browser = MagicMock()
        mock_browser.evaluate.return_value = 2
        loader = SessionLoader(fp_manager=MagicMock())
        count = loader.inject_local_storage(mock_browser, {"a": "1", "b": "2"}, origin="https://x.com")
        assert count == 2
        mock_browser.navigate.assert_called_once()

    def test_without_origin(self):
        mock_browser = MagicMock()
        mock_browser.evaluate.return_value = 1
        loader = SessionLoader(fp_manager=MagicMock())
        count = loader.inject_local_storage(mock_browser, {"k": "v"})
        assert count == 1
        mock_browser.navigate.assert_not_called()


class TestSessionLoaderApplyFingerprint:
    def test_no_fingerprint(self):
        mock_browser = MagicMock()
        loader = SessionLoader(fp_manager=MagicMock())
        result = loader.apply_fingerprint(mock_browser, None)
        assert result is True

    def test_with_fingerprint(self):
        mock_browser = MagicMock()
        loader = SessionLoader(fp_manager=MagicMock())
        fp = {"user_agent": "Mozilla/5.0"}
        result = loader.apply_fingerprint(mock_browser, fp)
        assert result is True


# ============================================================
# Fingerprint Manager
# ============================================================

class TestBrowserFingerprint:
    def test_defaults(self):
        fp = BrowserFingerprint()
        assert fp.screen_width == 1920
        assert fp.language == "en-US"
        assert fp.hardware_concurrency == 4

    def test_to_dict(self):
        fp = BrowserFingerprint(user_agent="TestAgent/1.0")
        d = fp.to_dict()
        assert d["user_agent"] == "TestAgent/1.0"
        assert "screen_width" in d

    def test_to_json_roundtrip(self):
        fp = BrowserFingerprint(user_agent="TestAgent/1.0", screen_width=1366)
        json_str = fp.to_json()
        fp2 = BrowserFingerprint.from_json(json_str)
        assert fp2.user_agent == "TestAgent/1.0"
        assert fp2.screen_width == 1366

    def test_from_dict(self):
        fp = BrowserFingerprint.from_dict({"user_agent": "X", "language": "fr"})
        assert fp.user_agent == "X"
        assert fp.language == "fr"

    def test_from_dict_empty(self):
        fp = BrowserFingerprint.from_dict({})
        assert fp.user_agent == ""

    def test_to_playwright_context(self):
        fp = BrowserFingerprint(
            viewport_width=1280, viewport_height=720,
            screen_width=1920, screen_height=1080,
            user_agent="Test/1.0", language="de", timezone="Europe/Berlin",
            device_pixel_ratio=2.0, max_touch_points=5,
        )
        ctx = fp.to_playwright_context()
        assert ctx["viewport"] == {"width": 1280, "height": 720}
        assert ctx["screen"] == {"width": 1920, "height": 1080}
        assert ctx["user_agent"] == "Test/1.0"
        assert ctx["locale"] == "de"
        assert ctx["timezone_id"] == "Europe/Berlin"
        assert ctx["device_scale_factor"] == 2.0
        assert ctx["has_touch"] is True


class TestFingerprintManager:
    def test_save_and_load(self, tmp_path):
        manager = FingerprintManager(storage_dir=str(tmp_path))
        fp = BrowserFingerprint(user_agent="Test/1.0", screen_width=1366)
        manager.save("test-fp", fp)

        loaded = manager.load("test-fp")
        assert loaded is not None
        assert loaded.user_agent == "Test/1.0"
        assert loaded.screen_width == 1366

    def test_list(self, tmp_path):
        manager = FingerprintManager(storage_dir=str(tmp_path))
        manager.save("fp-a", BrowserFingerprint(user_agent="A"))
        manager.save("fp-b", BrowserFingerprint(user_agent="B"))

        names = manager.list()
        assert "fp-a" in names
        assert "fp-b" in names

    def test_delete(self, tmp_path):
        manager = FingerprintManager(storage_dir=str(tmp_path))
        manager.save("fp-a", BrowserFingerprint(user_agent="A"))
        assert manager.delete("fp-a") is True
        assert manager.load("fp-a") is None

    def test_delete_nonexistent(self, tmp_path):
        manager = FingerprintManager(storage_dir=str(tmp_path))
        assert manager.delete("nonexistent") is False

    def test_load_nonexistent(self, tmp_path):
        manager = FingerprintManager(storage_dir=str(tmp_path))
        assert manager.load("nonexistent") is None

    def test_apply_to_config(self, tmp_path):
        manager = FingerprintManager(storage_dir=str(tmp_path))
        fp = BrowserFingerprint(user_agent="Test/1.0", viewport_width=1280, viewport_height=720)
        manager.save("my-fp", fp)

        config = {"browser": "chromium"}
        result = manager.apply_to_config("my-fp", config)
        assert result["user_agent"] == "Test/1.0"
        assert result["viewport"]["width"] == 1280

    def test_apply_to_config_missing(self, tmp_path):
        manager = FingerprintManager(storage_dir=str(tmp_path))
        config = {"browser": "chromium"}
        result = manager.apply_to_config("missing", config)
        assert result == config

    def test_compare_identical(self):
        fp1 = BrowserFingerprint(user_agent="A", screen_width=1920)
        fp2 = BrowserFingerprint(user_agent="A", screen_width=1920)
        manager = FingerprintManager()
        diff = manager.compare(fp1, fp2)
        assert diff == {}

    def test_compare_different(self):
        fp1 = BrowserFingerprint(user_agent="A", screen_width=1920)
        fp2 = BrowserFingerprint(user_agent="B", screen_width=1366)
        manager = FingerprintManager()
        diff = manager.compare(fp1, fp2)
        assert "user_agent" in diff
        assert "screen_width" in diff
