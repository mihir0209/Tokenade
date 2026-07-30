"""Tests for FormatExporter and FormatImporter."""

import json
import pytest

from tokenade.core.importer.format_exporter import FormatExporter
from tokenade.core.importer.format_importer import FormatImporter


@pytest.fixture
def sample_session():
    """A session with varied cookie edge cases."""
    return {
        "version": "2.0",
        "created_at": "2026-01-15T10:30:00Z",
        "source_device": {
            "browser": "chrome",
            "profile": "default",
            "platform": "Linux",
            "hostname": "test-pc",
        },
        "site_name": "example.com",
        "auth_status": "logged_in",
        "cookies": [
            {
                "name": "session_id",
                "value": "abc123def456",
                "domain": ".example.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "Lax",
                "expires": 1800000000,
            },
            {
                "name": "csrf_token",
                "value": "xyz789",
                "domain": ".example.com",
                "path": "/app",
                "secure": True,
                "httpOnly": False,
                "sameSite": "Strict",
                "expires": 1800000000,
            },
            {
                "name": "tracking_id",
                "value": "track123",
                "domain": ".example.com",
                "path": "/",
                "secure": False,
                "httpOnly": False,
                "sameSite": "None",
                "expires": 1900000000,
            },
            {
                "name": "session_cookie",
                "value": "sess_val",
                "domain": "api.example.com",
                "path": "/api",
                "secure": True,
                "httpOnly": True,
                "sameSite": "None",
            },
            {
                "name": "expired_cookie",
                "value": "old_value",
                "domain": ".example.com",
                "path": "/",
                "secure": True,
                "httpOnly": False,
                "sameSite": "Lax",
                "expires": 1000000000,
            },
        ],
        "tokens": [],
        "local_storage": {
            "example.com:theme": "dark",
            "example.com:lang": "en-US",
        },
        "fingerprint": {"user_agent": "Mozilla/5.0"},
        "tls_profile": None,
        "metadata": {
            "cookie_count": 5,
            "critical_cookie_count": 2,
        },
    }


@pytest.fixture
def exporter(sample_session):
    return FormatExporter(sample_session)


class TestPlaywrightStorageState:
    def test_structure(self, exporter):
        result = json.loads(exporter.to_playwright_storagestate())
        assert "cookies" in result
        assert "origins" in result
        assert len(result["cookies"]) == 5

    def test_cookie_fields(self, exporter):
        result = json.loads(exporter.to_playwright_storagestate())
        cookie = result["cookies"][0]
        assert cookie["name"] == "session_id"
        assert cookie["value"] == "abc123def456"
        assert cookie["domain"] == ".example.com"
        assert cookie["path"] == "/"
        assert cookie["httpOnly"] is True
        assert cookie["secure"] is True
        assert cookie["sameSite"] == "Lax"
        assert cookie["expires"] == 1800000000

    def test_session_cookie_expires(self, exporter):
        result = json.loads(exporter.to_playwright_storagestate())
        session_cookie = result["cookies"][3]
        assert session_cookie["name"] == "session_cookie"
        assert session_cookie["expires"] == -1

    def test_samesite_none(self, exporter):
        result = json.loads(exporter.to_playwright_storagestate())
        tracking = result["cookies"][2]
        assert tracking["sameSite"] == "None"

    def test_local_storage(self, exporter):
        result = json.loads(exporter.to_playwright_storagestate())
        assert len(result["origins"]) > 0
        names = [entry["name"] for o in result["origins"] for entry in o["localStorage"]]
        assert "theme" in names
        assert "lang" in names

    def test_no_local_storage(self, exporter):
        result = json.loads(exporter.to_playwright_storagestate(include_local_storage=False))
        assert result["origins"] == []


class TestPuppeteerCookies:
    def test_all_fields(self, exporter):
        cookies = exporter.to_puppeteer_cookies()
        assert len(cookies) == 5
        cookie = cookies[0]
        required = [
            "name", "value", "domain", "path", "expires", "size",
            "httpOnly", "secure", "session", "sameSite",
            "sameSiteCookiePolicy", "priority", "sameParty",
            "sourceScheme", "partitionKey",
        ]
        for field in required:
            assert field in cookie, f"Missing field: {field}"

    def test_session_flag(self, exporter):
        cookies = exporter.to_puppeteer_cookies()
        # session_cookie has no expires -> session=True
        session = [c for c in cookies if c["name"] == "session_cookie"][0]
        assert session["session"] is True
        assert session["expires"] == -1

    def test_non_session(self, exporter):
        cookies = exporter.to_puppeteer_cookies()
        non_session = [c for c in cookies if c["name"] == "session_id"][0]
        assert non_session["session"] is False

    def test_size_computed(self, exporter):
        cookies = exporter.to_puppeteer_cookies()
        sid = [c for c in cookies if c["name"] == "session_id"][0]
        assert sid["size"] == len("abc123def456")

    def test_source_scheme(self, exporter):
        cookies = exporter.to_puppeteer_cookies()
        secure = [c for c in cookies if c["name"] == "session_id"][0]
        assert secure["sourceScheme"] == "Secure"
        insecure = [c for c in cookies if c["name"] == "tracking_id"][0]
        assert insecure["sourceScheme"] == "Unset"


class TestNetscape:
    def test_header(self, exporter):
        result = exporter.to_netscape()
        assert result.startswith("# Netscape HTTP Cookie File")
        assert "# http://curl.haxx.se/rfc/cookie_spec.html" in result

    def test_tab_separated(self, exporter):
        lines = exporter.to_netscape().strip().split("\n")
        data_lines = [line for line in lines if not line.startswith("#") and line.strip()]
        assert len(data_lines) == 5

    def test_fields(self, exporter):
        lines = exporter.to_netscape().strip().split("\n")
        data_lines = [line for line in lines if not line.startswith("#") and line.strip()]
        parts = data_lines[0].split("\t")
        assert len(parts) == 7
        domain, tailmatch, path, secure, expires, name, value = parts
        assert domain == ".example.com"
        assert tailmatch == "TRUE"
        assert secure in ("TRUE", "FALSE")
        assert name == "session_id"

    def test_tailmatch_false_for_bare_domain(self, exporter):
        lines = exporter.to_netscape().strip().split("\n")
        data_lines = [line for line in lines if not line.startswith("#") and line.strip()]
        api_line = [line for line in data_lines if "api.example.com" in line][0]
        parts = api_line.split("\t")
        assert parts[1] == "FALSE"

    def test_secure_flag(self, exporter):
        lines = exporter.to_netscape().strip().split("\n")
        data_lines = [line for line in lines if not line.startswith("#") and line.strip()]
        tracking_line = [line for line in data_lines if "tracking_id" in line][0]
        parts = tracking_line.split("\t")
        assert parts[3] == "FALSE"


class TestCookieHeader:
    def test_format(self, exporter):
        header = exporter.to_cookie_header()
        assert "session_id=abc123def456" in header
        assert "csrf_token=xyz789" in header
        assert "; " in header

    def test_count(self, exporter):
        header = exporter.to_cookie_header()
        pairs = header.split("; ")
        assert len(pairs) == 5

    def test_empty_session(self):
        exporter = FormatExporter({"cookies": []})
        assert exporter.to_cookie_header() == ""


class TestToJson:
    def test_roundtrip_structure(self, exporter, sample_session):
        result = json.loads(exporter.to_json())
        assert result["version"] == sample_session["version"]
        assert result["site_name"] == sample_session["site_name"]
        assert len(result["cookies"]) == len(sample_session["cookies"])


class TestRequestsDict:
    def test_flat_dict(self, exporter):
        result = exporter.to_requests_dict()
        assert isinstance(result, dict)
        assert result["session_id"] == "abc123def456"
        assert result["csrf_token"] == "xyz789"
        assert len(result) == 5


class TestFormatImporterPlaywright:
    def test_import(self, exporter, tmp_path):
        state_json = exporter.to_playwright_storagestate()
        p = tmp_path / "state.json"
        p.write_text(state_json)

        session = FormatImporter.from_playwright_storagestate(str(p))
        assert session["version"] == "3.0"
        assert len(session["cookies"]) == 5

    def test_cookie_fields_preserved(self, exporter, tmp_path):
        state_json = exporter.to_playwright_storagestate()
        p = tmp_path / "state.json"
        p.write_text(state_json)

        session = FormatImporter.from_playwright_storagestate(str(p))
        cookie = session["cookies"][0]
        assert cookie["name"] == "session_id"
        assert cookie["value"] == "abc123def456"
        assert cookie["secure"] is True
        assert cookie["httpOnly"] is True

    def test_local_storage_imported(self, exporter, tmp_path):
        state_json = exporter.to_playwright_storagestate()
        p = tmp_path / "state.json"
        p.write_text(state_json)

        session = FormatImporter.from_playwright_storagestate(str(p))
        assert len(session["storage"]["local"]["https://example.com"]) == 2

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            FormatImporter.from_playwright_storagestate("/nonexistent/path.json")


class TestFormatImporterNetscape:
    def test_import(self, exporter, tmp_path):
        netscape = exporter.to_netscape()
        p = tmp_path / "cookies.txt"
        p.write_text(netscape)

        session = FormatImporter.from_netscape(str(p))
        assert len(session["cookies"]) == 5

    def test_cookie_fields(self, exporter, tmp_path):
        netscape = exporter.to_netscape()
        p = tmp_path / "cookies.txt"
        p.write_text(netscape)

        session = FormatImporter.from_netscape(str(p))
        cookie = session["cookies"][0]
        assert cookie["name"] == "session_id"
        assert cookie["value"] == "abc123def456"
        assert cookie["secure"] is True

    def test_skip_comments(self, tmp_path):
        content = (
            "# Netscape HTTP Cookie File\n"
            "# This is a comment\n"
            ".example.com\tTRUE\t/\tTRUE\t0\tsid\tval123\n"
        )
        p = tmp_path / "cookies.txt"
        p.write_text(content)

        session = FormatImporter.from_netscape(str(p))
        assert len(session["cookies"]) == 1
        assert session["cookies"][0]["name"] == "sid"


class TestFormatImporterCookieHeader:
    def test_import(self):
        header = "session_id=abc123; csrf_token=xyz789; lang=en"
        session = FormatImporter.from_cookie_header(header, domain=".example.com")
        assert len(session["cookies"]) == 3
        assert session["cookies"][0]["name"] == "session_id"
        assert session["cookies"][0]["domain"] == ".example.com"

    def test_empty_header(self):
        session = FormatImporter.from_cookie_header("")
        assert len(session["cookies"]) == 0

    def test_whitespace(self):
        header = "  sid=val1 ;  token=val2  "
        session = FormatImporter.from_cookie_header(header)
        assert len(session["cookies"]) == 2


class TestFormatImporterJson:
    def test_import_array(self, exporter, tmp_path):
        p = tmp_path / "cookies.json"
        p.write_text(json.dumps(exporter.cookies))

        session = FormatImporter.from_json(str(p))
        assert len(session["cookies"]) == 5

    def test_import_object_with_cookies_key(self, exporter, tmp_path):
        p = tmp_path / "cookies.json"
        p.write_text(json.dumps({"cookies": exporter.cookies}))

        session = FormatImporter.from_json(str(p))
        assert len(session["cookies"]) == 5


class TestDetectFormat:
    def test_playwright(self, exporter, tmp_path):
        p = tmp_path / "state.json"
        p.write_text(exporter.to_playwright_storagestate())
        assert FormatImporter.detect_format(str(p)) == "playwright"

    def test_netscape(self, exporter, tmp_path):
        p = tmp_path / "cookies.txt"
        p.write_text(exporter.to_netscape())
        assert FormatImporter.detect_format(str(p)) == "netscape"

    def test_json(self, exporter, tmp_path):
        p = tmp_path / "cookies.json"
        p.write_text(json.dumps(exporter.cookies))
        assert FormatImporter.detect_format(str(p)) == "json"

    def test_unknown(self, tmp_path):
        p = tmp_path / "data.bin"
        p.write_text("some random binary data \x00\x01\x02")
        assert FormatImporter.detect_format(str(p)) == "unknown"

    def test_nonexistent(self):
        assert FormatImporter.detect_format("/nonexistent/file.txt") == "unknown"


class TestRoundTrip:
    def test_export_playwright_then_import(self, sample_session, tmp_path):
        exporter = FormatExporter(sample_session)
        state_json = exporter.to_playwright_storagestate()
        p = tmp_path / "state.json"
        p.write_text(state_json)

        imported = FormatImporter.from_playwright_storagestate(str(p))

        original_names = {c["name"] for c in sample_session["cookies"]}
        imported_names = {c["name"] for c in imported["cookies"]}
        assert original_names == imported_names

        for orig, imp in zip(sample_session["cookies"], imported["cookies"]):
            assert orig["name"] == imp["name"]
            assert orig["value"] == imp["value"]
            assert orig["domain"] == imp["domain"]

    def test_export_netscape_then_import(self, sample_session, tmp_path):
        exporter = FormatExporter(sample_session)
        netscape = exporter.to_netscape()
        p = tmp_path / "cookies.txt"
        p.write_text(netscape)

        imported = FormatImporter.from_netscape(str(p))

        original_names = {c["name"] for c in sample_session["cookies"]}
        imported_names = {c["name"] for c in imported["cookies"]}
        assert original_names == imported_names

    def test_export_json_then_import(self, sample_session, tmp_path):
        exporter = FormatExporter(sample_session)
        p = tmp_path / "cookies.json"
        p.write_text(exporter.to_json())

        imported = FormatImporter.from_json(str(p))

        assert len(imported["cookies"]) == len(sample_session["cookies"])
        for orig, imp in zip(sample_session["cookies"], imported["cookies"]):
            assert orig["name"] == imp["name"]
            assert orig["value"] == imp["value"]
