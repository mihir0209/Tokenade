"""Tests for Safari, Tor Browser, and ADB extractors."""

import struct
import subprocess
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from tokenade.core.importer.safari_extractor import SafariExtractor
from tokenade.core.importer.tor_extractor import TorExtractor
from tokenade.core.importer.adb_extractor import ADBExtractor
from tokenade.core.importer.cookie_extractor import SiteFilter


# ---------------------------------------------------------------------------
# SafariExtractor Tests
# ---------------------------------------------------------------------------
class TestSafariExtractor:
    """Tests for SafariExtractor."""

    def test_platform_check_raises_on_non_macos(self):
        """Test that ImportError is raised on non-macOS platforms."""
        with patch("tokenade.core.importer.safari_extractor.sys") as mock_sys:
            mock_sys.platform = "linux"
            with pytest.raises(ImportError, match="only supported on macOS"):
                SafariExtractor()

    def test_platform_check_accepts_macos(self):
        """Test that SafariExtractor initializes on macOS."""
        with patch("tokenade.core.importer.safari_extractor.sys") as mock_sys:
            mock_sys.platform = "darwin"
            with patch("os.path.exists", return_value=True):
                extractor = SafariExtractor()
                assert extractor.profile_path.endswith("Cookies.binarycookies")

    def test_custom_profile_path(self):
        """Test that custom profile path is used."""
        with patch("tokenade.core.importer.safari_extractor.sys") as mock_sys:
            mock_sys.platform = "darwin"
            extractor = SafariExtractor(profile_path="/tmp/custom.cookies")
            assert extractor.profile_path == "/tmp/custom.cookies"

    def test_extract_returns_empty_when_file_missing(self):
        """Test that extract returns empty list when cookies file is missing."""
        with patch("tokenade.core.importer.safari_extractor.sys") as mock_sys:
            mock_sys.platform = "darwin"
            extractor = SafariExtractor(profile_path="/nonexistent/file")
            cookies = extractor.extract()
            assert cookies == []

    def _build_page(self, cookies):
        """Build a page of cookies in Safari binary format."""
        # Page header (4 bytes) + cookie count (4 bytes)
        page = struct.pack(">I", 0x00000100)
        page += struct.pack(">I", len(cookies))

        # Each cookie entry: 48 bytes header + string data
        # We'll build string data separately and reference offsets
        string_data = b""
        cookie_entries = []

        for cookie in cookies:
            name_bytes = cookie["name"].encode("utf-8") + b"\x00"
            value_bytes = cookie["value"].encode("utf-8") + b"\x00"
            domain_bytes = cookie["domain"].encode("utf-8") + b"\x00"
            path_bytes = cookie["path"].encode("utf-8") + b"\x00"

            # Store relative offsets within string_data
            name_offset = len(string_data)
            string_data += name_bytes
            value_offset = len(string_data)
            string_data += value_bytes
            domain_offset = len(string_data)
            string_data += domain_bytes
            path_offset = len(string_data)
            string_data += path_bytes

            # URL and comment are empty
            url_offset = domain_offset
            comment_offset = path_offset

            flags = 0x1 if cookie.get("secure") else 0x0
            expiry = 9999999999.0  # Mac absolute time

            entry = struct.pack(">I", flags)
            entry += struct.pack(">I", 0)  # padding
            entry += struct.pack(">I", url_offset)
            entry += struct.pack(">I", name_offset)
            entry += struct.pack(">I", value_offset)
            entry += struct.pack(">I", domain_offset)
            entry += struct.pack(">I", path_offset)
            entry += struct.pack(">I", comment_offset)
            entry += struct.pack(">d", expiry)  # expiry as double
            entry += struct.pack(">d", expiry)  # creation as double

            cookie_entries.append(entry)

        # Calculate where string_data starts in the page
        # header(4) + count(4) + offsets_table(num*4) + entries(sum of entry sizes)
        header_size = 4 + 4 + len(cookies) * 4
        entries_size = sum(len(e) for e in cookie_entries)
        strings_start = header_size + entries_size

        # Build offset table (absolute offsets within page)
        cookie_offsets = b""
        offset = header_size
        for entry in cookie_entries:
            cookie_offsets += struct.pack(">I", offset)
            offset += len(entry)

        # Build entries with corrected string offsets
        fixed_entries = b""
        for i, entry in enumerate(cookie_entries):
            # Rebuild entry with absolute string offsets
            cookie = cookies[i]
            name_bytes = cookie["name"].encode("utf-8") + b"\x00"
            value_bytes = cookie["value"].encode("utf-8") + b"\x00"
            domain_bytes = cookie["domain"].encode("utf-8") + b"\x00"
            path_bytes = cookie["path"].encode("utf-8") + b"\x00"

            # Compute absolute offsets
            abs_name = strings_start + sum(len(c["name"].encode("utf-8")) + 1 + len(c["value"].encode("utf-8")) + 1 + len(c["domain"].encode("utf-8")) + 1 + len(c["path"].encode("utf-8")) + 1 for c in cookies[:i])
            abs_value = abs_name + len(name_bytes)
            abs_domain = abs_value + len(value_bytes)
            abs_path = abs_domain + len(domain_bytes)

            flags = 0x1 if cookie.get("secure") else 0x0

            fixed_entry = struct.pack(">I", flags)
            fixed_entry += struct.pack(">I", 0)  # padding
            fixed_entry += struct.pack(">I", abs_domain)  # url uses domain
            fixed_entry += struct.pack(">I", abs_name)
            fixed_entry += struct.pack(">I", abs_value)
            fixed_entry += struct.pack(">I", abs_domain)
            fixed_entry += struct.pack(">I", abs_path)
            fixed_entry += struct.pack(">I", abs_path)  # comment uses path
            fixed_entry += struct.pack(">d", 9999999999.0)  # expiry
            fixed_entry += struct.pack(">d", 9999999999.0)  # creation

            fixed_entries += fixed_entry

        # Assemble page: header + count + offsets + entries + strings
        page += cookie_offsets
        page += fixed_entries
        page += string_data

        return page

    def test_parse_binary_cookies(self, tmp_path):
        """Test parsing a crafted binary cookies file."""
        cookies = [
            {"name": "session", "value": "abc123", "domain": ".example.com", "path": "/"},
        ]

        page_data = self._build_page(cookies)
        page_size = len(page_data)

        header = b"cook"
        num_pages = struct.pack(">I", 1)
        page_sizes = struct.pack(">I", page_size)

        file_path = tmp_path / "Cookies.binarycookies"
        file_path.write_bytes(header + num_pages + page_sizes + page_data)

        with patch("tokenade.core.importer.safari_extractor.sys") as mock_sys:
            mock_sys.platform = "darwin"
            extractor = SafariExtractor(profile_path=str(file_path))
            result = extractor._parse_binary_cookies(str(file_path))

        assert len(result) == 1
        assert result[0]["name"] == "session"
        assert result[0]["value"] == "abc123"
        assert result[0]["domain"] == ".example.com"

    def test_extract_with_site_filter(self, tmp_path):
        """Test that site filtering works."""
        cookies = [
            {"name": "sid", "value": "x", "domain": ".google.com", "path": "/"},
            {"name": "token", "value": "y", "domain": ".github.com", "path": "/"},
        ]

        page_data = self._build_page(cookies)
        page_size = len(page_data)

        header = b"cook"
        num_pages = struct.pack(">I", 1)
        page_sizes = struct.pack(">I", page_size)

        file_path = tmp_path / "Cookies.binarycookies"
        file_path.write_bytes(header + num_pages + page_sizes + page_data)

        with patch("tokenade.core.importer.safari_extractor.sys") as mock_sys:
            mock_sys.platform = "darwin"
            extractor = SafariExtractor(profile_path=str(file_path))
            site_filter = SiteFilter(["google"])
            result = extractor.extract(site_filter=site_filter)

        assert len(result) == 1
        assert result[0]["domain"] == ".google.com"

    def test_extract_invalid_header(self, tmp_path):
        """Test handling of invalid file header."""
        file_path = tmp_path / "bad.cookies"
        file_path.write_bytes(b"xxxx" + b"\x00" * 20)

        with patch("tokenade.core.importer.safari_extractor.sys") as mock_sys:
            mock_sys.platform = "darwin"
            extractor = SafariExtractor(profile_path=str(file_path))
            result = extractor._parse_binary_cookies(str(file_path))

        assert result == []

    def test_extract_too_small_file(self, tmp_path):
        """Test handling of file too small to be valid."""
        file_path = tmp_path / "tiny.cookies"
        file_path.write_bytes(b"co")

        with patch("tokenade.core.importer.safari_extractor.sys") as mock_sys:
            mock_sys.platform = "darwin"
            extractor = SafariExtractor(profile_path=str(file_path))
            result = extractor._parse_binary_cookies(str(file_path))

        assert result == []

    def test_extract_multiple_pages(self, tmp_path):
        """Test parsing multiple pages."""
        page1 = self._build_page([{"name": "a", "value": "1", "domain": ".a.com", "path": "/"}])
        page2 = self._build_page([{"name": "b", "value": "2", "domain": ".b.com", "path": "/"}])

        header = b"cook"
        num_pages = struct.pack(">I", 2)
        page_sizes = struct.pack(">I", len(page1)) + struct.pack(">I", len(page2))

        file_path = tmp_path / "Cookies.binarycookies"
        file_path.write_bytes(header + num_pages + page_sizes + page1 + page2)

        with patch("tokenade.core.importer.safari_extractor.sys") as mock_sys:
            mock_sys.platform = "darwin"
            extractor = SafariExtractor(profile_path=str(file_path))
            result = extractor._parse_binary_cookies(str(file_path))

        assert len(result) == 2
        domains = {c["domain"] for c in result}
        assert ".a.com" in domains
        assert ".b.com" in domains

    def test_read_string_returns_empty_on_bad_offset(self):
        """Test _read_string returns empty string on out-of-bounds offset."""
        result = SafariExtractor._read_string(b"hello", 100)
        assert result == ""

    def test_read_string_parses_null_terminated(self):
        """Test _read_string reads null-terminated string."""
        data = b"\x00\x00hello\x00world\x00"
        result = SafariExtractor._read_string(data, 2)
        assert result == "hello"


# ---------------------------------------------------------------------------
# TorExtractor Tests
# ---------------------------------------------------------------------------
class TestTorExtractor:
    """Tests for TorExtractor."""

    def test_find_tor_profile_linux(self, tmp_path):
        """Test profile discovery on Linux."""
        profile_dir = tmp_path / "profile.default"
        profile_dir.mkdir()
        cookies_db = profile_dir / "cookies.sqlite"
        cookies_db.touch()

        linux_path = str(profile_dir)
        with patch("tokenade.core.importer.tor_extractor.platform") as mock_platform:
            mock_platform.system.return_value = "Linux"
            with patch.dict(
                "tokenade.core.importer.tor_extractor.TOR_PROFILE_PATHS",
                {"Linux": [linux_path]},
            ):
                extractor = TorExtractor()
                assert extractor.profile_path == linux_path

    def test_find_tor_profile_darwin(self, tmp_path):
        """Test profile discovery on macOS."""
        profile_dir = tmp_path / "profile.default"
        profile_dir.mkdir()
        cookies_db = profile_dir / "cookies.sqlite"
        cookies_db.touch()

        darwin_path = str(profile_dir)
        with patch("tokenade.core.importer.tor_extractor.platform") as mock_platform:
            mock_platform.system.return_value = "Darwin"
            with patch.dict(
                "tokenade.core.importer.tor_extractor.TOR_PROFILE_PATHS",
                {"Darwin": [darwin_path]},
            ):
                extractor = TorExtractor()
                assert extractor.profile_path == darwin_path

    def test_find_tor_profile_windows(self, tmp_path):
        """Test profile discovery on Windows."""
        profile_dir = tmp_path / "profile.default"
        profile_dir.mkdir()
        cookies_db = profile_dir / "cookies.sqlite"
        cookies_db.touch()

        win_path = str(profile_dir)
        with patch("tokenade.core.importer.tor_extractor.platform") as mock_platform:
            mock_platform.system.return_value = "Windows"
            with patch.dict(
                "tokenade.core.importer.tor_extractor.TOR_PROFILE_PATHS",
                {"Windows": [win_path]},
            ):
                extractor = TorExtractor()
                assert extractor.profile_path == win_path

    def test_find_tor_profile_not_found(self):
        """Test fallback when Tor Browser is not found."""
        with patch("tokenade.core.importer.tor_extractor.platform") as mock_platform:
            mock_platform.system.return_value = "Linux"
            with patch.dict(
                "tokenade.core.importer.tor_extractor.TOR_PROFILE_PATHS",
                {"Linux": ["/nonexistent/path"]},
            ):
                with patch("os.path.exists", return_value=False):
                    extractor = TorExtractor()
                    assert extractor.profile_path is None

    def test_extract_delegates_to_cookie_extractor(self, tmp_path):
        """Test that extract delegates to CookieExtractor with firefox browser."""
        # Create a minimal Firefox cookies.sqlite
        db_path = tmp_path / "cookies.sqlite"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE moz_cookies (
                id INTEGER PRIMARY KEY,
                baseDomain TEXT,
                originAttributes TEXT DEFAULT '',
                name TEXT,
                value TEXT,
                host TEXT,
                path TEXT,
                expiry INTEGER,
                lastAccessed INTEGER,
                creationTime INTEGER,
                isSecure INTEGER DEFAULT 0,
                isHttpOnly INTEGER DEFAULT 0,
                sameSite INTEGER DEFAULT -1,
                schemeMap INTEGER DEFAULT 0
            )
        """)
        cursor.execute(
            "INSERT INTO moz_cookies (baseDomain, name, value, host, path, expiry) "
            "VALUES ('example.com', 'test', 'val', '.example.com', '/', 9999999999)"
        )
        conn.commit()
        conn.close()

        extractor = TorExtractor(profile_path=str(tmp_path))
        cookies = extractor.extract()

        assert len(cookies) == 1
        assert cookies[0]["name"] == "test"
        assert cookies[0]["value"] == "val"

    def test_extract_returns_empty_when_no_profile(self):
        """Test that extract returns empty when no profile found."""
        extractor = TorExtractor(profile_path=None)
        with patch.object(extractor, "_find_tor_profile", return_value=None):
            extractor.profile_path = None
            cookies = extractor.extract()
            assert cookies == []

    def test_extract_returns_empty_when_path_missing(self, tmp_path):
        """Test that extract returns empty when profile path does not exist."""
        extractor = TorExtractor(profile_path=str(tmp_path / "nonexistent"))
        cookies = extractor.extract()
        assert cookies == []

    def test_extract_with_site_filter(self, tmp_path):
        """Test that site filtering is applied."""
        db_path = tmp_path / "cookies.sqlite"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE moz_cookies (
                id INTEGER PRIMARY KEY,
                baseDomain TEXT,
                originAttributes TEXT DEFAULT '',
                name TEXT,
                value TEXT,
                host TEXT,
                path TEXT,
                expiry INTEGER,
                lastAccessed INTEGER,
                creationTime INTEGER,
                isSecure INTEGER DEFAULT 0,
                isHttpOnly INTEGER DEFAULT 0,
                sameSite INTEGER DEFAULT -1,
                schemeMap INTEGER DEFAULT 0
            )
        """)
        cursor.execute(
            "INSERT INTO moz_cookies (baseDomain, name, value, host, path, expiry) "
            "VALUES ('google.com', 'SID', 'x', '.google.com', '/', 9999999999)"
        )
        cursor.execute(
            "INSERT INTO moz_cookies (baseDomain, name, value, host, path, expiry) "
            "VALUES ('github.com', 'token', 'y', '.github.com', '/', 9999999999)"
        )
        conn.commit()
        conn.close()

        extractor = TorExtractor(profile_path=str(tmp_path))
        site_filter = SiteFilter(["google"])
        cookies = extractor.extract(site_filter=site_filter)

        assert len(cookies) == 1
        assert cookies[0]["name"] == "SID"


# ---------------------------------------------------------------------------
# ADBExtractor Tests
# ---------------------------------------------------------------------------
class TestADBExtractor:
    """Tests for ADBExtractor."""

    def test_is_available_when_adb_missing(self):
        """Test is_available returns False when adb is not installed."""
        extractor = ADBExtractor()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert extractor.is_available() is False

    def test_is_available_when_adb_present(self):
        """Test is_available returns True when device is connected."""
        extractor = ADBExtractor()
        mock_result = MagicMock()
        mock_result.stdout = "List of devices attached\nABC123\tdevice\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            assert extractor.is_available() is True

    def test_is_available_when_no_devices(self):
        """Test is_available returns False when no devices connected."""
        extractor = ADBExtractor()
        mock_result = MagicMock()
        mock_result.stdout = "List of devices attached\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            assert extractor.is_available() is False

    def test_list_devices(self):
        """Test listing connected devices."""
        extractor = ADBExtractor()
        devices_output = "List of devices attached\nABC123\tdevice product:sdk_model\n"
        model_output = "Pixel 6\n"
        version_output = "13\n"

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if "devices" in cmd:
                result.stdout = devices_output
            elif "ro.product.model" in cmd:
                result.stdout = model_output
            elif "ro.build.version.release" in cmd:
                result.stdout = version_output
            else:
                result.stdout = ""
            return result

        with patch("subprocess.run", side_effect=mock_run):
            devices = extractor.list_devices()

        assert len(devices) == 1
        assert devices[0]["serial"] == "ABC123"
        assert devices[0]["model"] == "Pixel 6"
        assert devices[0]["android_version"] == "13"

    def test_list_devices_empty(self):
        """Test listing devices when none are connected."""
        extractor = ADBExtractor()
        mock_result = MagicMock()
        mock_result.stdout = "List of devices attached\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            devices = extractor.list_devices()

        assert devices == []

    def test_list_devices_offline(self):
        """Test that offline devices are filtered out."""
        extractor = ADBExtractor()
        mock_result = MagicMock()
        mock_result.stdout = (
            "List of devices attached\n"
            "ABC123\tdevice\n"
            "DEF456\toffline\n"
        )
        mock_result.returncode = 0

        model_result = MagicMock()
        model_result.stdout = "Pixel 6\n"
        model_result.returncode = 0

        version_result = MagicMock()
        version_result.stdout = "13\n"
        version_result.returncode = 0

        def mock_run(cmd, **kwargs):
            if "devices" in cmd:
                return mock_result
            return model_result if "model" in cmd else version_result

        with patch("subprocess.run", side_effect=mock_run):
            devices = extractor.list_devices()

        assert len(devices) == 1
        assert devices[0]["serial"] == "ABC123"

    def test_run_adb_includes_device_id(self):
        """Test that _run_adb includes device_id when specified."""
        extractor = ADBExtractor(device_id="ABC123")
        mock_result = MagicMock()
        mock_result.stdout = "ok\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_sub:
            extractor._run_adb(["shell", "echo", "ok"])

            call_args = mock_sub.call_args[0][0]
            assert "-s" in call_args
            assert "ABC123" in call_args

    def test_run_adb_without_device_id(self):
        """Test that _run_adb omits -s when no device_id."""
        extractor = ADBExtractor()
        mock_result = MagicMock()
        mock_result.stdout = "ok\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_sub:
            extractor._run_adb(["devices"])

            call_args = mock_sub.call_args[0][0]
            assert "-s" not in call_args

    def test_run_adb_command_failure(self):
        """Test that _run_adb raises on command failure."""
        extractor = ADBExtractor()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error: device not found"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(subprocess.SubprocessError, match="ADB command failed"):
                extractor._run_adb(["devices"])

    def test_run_adb_adb_not_installed(self):
        """Test that _run_adb raises FileNotFoundError when adb missing."""
        extractor = ADBExtractor()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(FileNotFoundError):
                extractor._run_adb(["devices"])

    def test_pull_file(self):
        """Test _pull_file calls adb pull correctly."""
        extractor = ADBExtractor()
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_sub:
            extractor._pull_file("/remote/file", "/local/file")

            call_args = mock_sub.call_args[0][0]
            assert call_args == ["adb", "pull", "/remote/file", "/local/file"]

    def test_extract_chrome_cookies_pulls_and_parses(self, tmp_path):
        """Test extract_chrome_cookies pulls DB and parses it."""
        # Create a mock Chrome cookies DB
        db_path = tmp_path / "Cookies"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE cookies (
                host_key TEXT,
                name TEXT,
                value TEXT,
                encrypted_value BLOB,
                path TEXT,
                expires_utc INTEGER,
                is_secure INTEGER DEFAULT 0,
                is_httponly INTEGER DEFAULT 0,
                samesite INTEGER DEFAULT -1,
                creation_utc INTEGER DEFAULT 0,
                last_access_utc INTEGER DEFAULT 0
            )
        """)
        cursor.execute(
            "INSERT INTO cookies (host_key, name, value, path, expires_utc) "
            "VALUES ('.example.com', 'sid', 'xyz', '/', 9999999999000000)"
        )
        conn.commit()
        conn.close()

        extractor = ADBExtractor()

        # Mock _pull_file to copy our test DB
        def mock_pull(remote, local):
            import shutil
            shutil.copy2(str(db_path), local)

        with patch.object(extractor, "_pull_file", side_effect=mock_pull):
            with patch.object(extractor, "_run_adb", return_value=""):
                cookies = extractor.extract_chrome_cookies(
                    "/data/data/com.android.chrome/app_chrome/Default"
                )

        assert len(cookies) == 1
        assert cookies[0]["name"] == "sid"
        assert cookies[0]["value"] == "xyz"

    def test_extract_firefox_cookies_pulls_and_parses(self, tmp_path):
        """Test extract_firefox_cookies pulls DB and parses it."""
        db_path = tmp_path / "cookies.sqlite"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE moz_cookies (
                id INTEGER PRIMARY KEY,
                baseDomain TEXT,
                originAttributes TEXT DEFAULT '',
                name TEXT,
                value TEXT,
                host TEXT,
                path TEXT,
                expiry INTEGER,
                lastAccessed INTEGER,
                creationTime INTEGER,
                isSecure INTEGER DEFAULT 0,
                isHttpOnly INTEGER DEFAULT 0,
                sameSite INTEGER DEFAULT -1,
                schemeMap INTEGER DEFAULT 0
            )
        """)
        cursor.execute(
            "INSERT INTO moz_cookies (baseDomain, name, value, host, path, expiry) "
            "VALUES ('example.com', 'test', 'val', '.example.com', '/', 9999999999)"
        )
        conn.commit()
        conn.close()

        extractor = ADBExtractor()

        def mock_pull(remote, local):
            import shutil
            shutil.copy2(str(db_path), local)

        with patch.object(extractor, "_pull_file", side_effect=mock_pull):
            with patch.object(extractor, "_run_adb", return_value=""):
                cookies = extractor.extract_firefox_cookies(
                    "/data/data/org.mozilla.firefox/files/mozilla/profile.default"
                )

        assert len(cookies) == 1
        assert cookies[0]["name"] == "test"
        assert cookies[0]["value"] == "val"

    def test_extract_chrome_returns_empty_on_pull_failure(self):
        """Test extract_chrome_cookies returns empty when pull fails."""
        extractor = ADBExtractor()
        with patch.object(
            extractor, "_pull_file", side_effect=subprocess.SubprocessError("fail")
        ):
            cookies = extractor.extract_chrome_cookies("/remote/path")
            assert cookies == []

    def test_extract_chrome_returns_empty_on_missing_file(self):
        """Test extract_chrome_cookies returns empty when file not found after pull."""
        extractor = ADBExtractor()
        with patch.object(extractor, "_pull_file", return_value=None):
            cookies = extractor.extract_chrome_cookies("/remote/path")
            assert cookies == []

    def test_device_specific_extraction(self, tmp_path):
        """Test extraction with a specific device ID."""
        db_path = tmp_path / "Cookies"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE cookies (
                host_key TEXT,
                name TEXT,
                value TEXT,
                encrypted_value BLOB,
                path TEXT,
                expires_utc INTEGER,
                is_secure INTEGER DEFAULT 0,
                is_httponly INTEGER DEFAULT 0,
                samesite INTEGER DEFAULT -1,
                creation_utc INTEGER DEFAULT 0,
                last_access_utc INTEGER DEFAULT 0
            )
        """)
        cursor.execute(
            "INSERT INTO cookies (host_key, name, value, path, expires_utc) "
            "VALUES ('.test.com', 'id', '123', '/', 9999999999000000)"
        )
        conn.commit()
        conn.close()

        extractor = ADBExtractor(device_id="SPECIFIC_DEVICE")

        def mock_pull(remote, local):
            import shutil
            shutil.copy2(str(db_path), local)

        with patch.object(extractor, "_pull_file", side_effect=mock_pull):
            with patch.object(extractor, "_run_adb", return_value=""):
                cookies = extractor.extract_chrome_cookies("/remote/path")

        assert len(cookies) == 1
        assert cookies[0]["name"] == "id"
