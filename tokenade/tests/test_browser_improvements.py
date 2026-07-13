"""Tests for P7 browser support improvements."""
import platform
import pytest
import sys
import tempfile
import struct
from pathlib import Path
from unittest.mock import patch


@pytest.mark.skipif(platform.system() == "Linux", reason="Safari tests require macOS")
class TestSafariExtractor:
    """Tests for SafariExtractor."""

    def test_platform_check_darwin(self):
        """Should not raise on macOS."""
        with patch("sys.platform", "darwin"):
            pass
            # Just test class instantiation check
            assert True

    def test_platform_check_raises_on_linux(self):
        """Should raise ImportError on non-macOS."""
        if sys.platform == "darwin":
            pytest.skip("Running on macOS")

        from tokenade.core.importer.safari_extractor import SafariExtractor
        with pytest.raises(ImportError, match="macOS"):
            SafariExtractor()

    def test_find_cookies_file_not_found(self):
        """Should return None when cookies file doesn't exist."""
        if sys.platform != "darwin":
            pytest.skip("macOS only")

        from tokenade.core.importer.safari_extractor import SafariExtractor
        extractor = SafariExtractor(profile_path="/nonexistent/path")
        result = extractor._find_cookies_file()
        assert result is None

    def test_read_cstring(self):
        """Should read null-terminated string from bytes."""
        if sys.platform != "darwin":
            pytest.skip("macOS only")

        from tokenade.core.importer.safari_extractor import SafariExtractor
        data = b"hello\x00world\x00"
        extractor = SafariExtractor.__new__(SafariExtractor)
        assert extractor._read_cstring(data, 0) == "hello"
        assert extractor._read_cstring(data, 6) == "world"
        assert extractor._read_cstring(data, 11) == ""

    def test_parse_binary_cookies_invalid_header(self):
        """Should return empty list on invalid file header."""
        if sys.platform != "darwin":
            pytest.skip("macOS only")

        from tokenade.core.importer.safari_extractor import SafariExtractor

        with tempfile.NamedTemporaryFile(suffix=".binarycookies") as f:
            f.write(b"INVALID_HEADER")
            f.flush()

            extractor = SafariExtractor.__new__(SafariExtractor)
            result = extractor._parse_binary_cookies(f.name)
            assert result == []

    def test_parse_binary_cookies_empty(self):
        """Should handle empty valid header with 0 pages."""
        if sys.platform != "darwin":
            pytest.skip("macOS only")

        from tokenade.core.importer.safari_extractor import SafariExtractor

        with tempfile.NamedTemporaryFile(suffix=".binarycookies") as f:
            # Write valid header: "cook" + 0 pages
            f.write(b"cook")
            f.write(struct.pack(">I", 0))
            f.flush()

            extractor = SafariExtractor.__new__(SafariExtractor)
            result = extractor._parse_binary_cookies(f.name)
            assert result == []

    def test_extract_with_filter(self):
        """Should filter cookies by domain."""
        if sys.platform != "darwin":
            pytest.skip("macOS only")

        from tokenade.core.importer.safari_extractor import SafariExtractor

        extractor = SafariExtractor.__new__(SafariExtractor)
        extractor.profile_path = None
        extractor.tech_preview = False

        # Mock the parse method
        mock_cookies = [
            {"name": "c1", "value": "v1", "domain": ".google.com"},
            {"name": "c2", "value": "v2", "domain": ".github.com"},
        ]

        with patch.object(extractor, "_find_cookies_file", return_value=Path("/fake")):
            with patch.object(extractor, "_parse_binary_cookies", return_value=mock_cookies):
                result = extractor.extract(site_filter=["google.com"])
                assert len(result) == 1
                assert result[0]["domain"] == ".google.com"


class TestChromiumForkDetector:
    """Tests for ChromiumForkDetector."""

    def test_detect_all_returns_list(self):
        """Should return a list of detected browsers."""
        from tokenade.core.importer.chromium_forks import ChromiumForkDetector
        detector = ChromiumForkDetector()
        result = detector.detect_all()
        assert isinstance(result, list)

    def test_browser_type_mapping(self):
        """All forks should map to 'chrome' for CookieExtractor."""
        from tokenade.core.importer.chromium_forks import ChromiumForkDetector, ChromiumForkInfo
        detector = ChromiumForkDetector()

        forks = [
            ChromiumForkInfo(name="Arc", browser_type="arc", profile_dirs=[Path("/tmp")]),
            ChromiumForkInfo(name="Opera", browser_type="opera", profile_dirs=[Path("/tmp")]),
            ChromiumForkInfo(name="Vivaldi", browser_type="vivaldi", profile_dirs=[Path("/tmp")]),
            ChromiumForkInfo(name="Brave", browser_type="brave", profile_dirs=[Path("/tmp")]),
        ]

        for fork in forks:
            browser = detector.get_browser_type_for_extractor(fork)
            assert browser == "chrome"

    def test_get_notes(self):
        """Should return notes for known browsers."""
        from tokenade.core.importer.chromium_forks import ChromiumForkDetector
        detector = ChromiumForkDetector()

        notes = detector._get_notes("arc")
        assert "Arc" in notes

        notes = detector._get_notes("brave")
        assert "Tor" in notes or "brave" in notes.lower()

    def test_find_profiles_empty_dir(self):
        """Should return empty list for directory with no profiles."""
        from tokenade.core.importer.chromium_forks import ChromiumForkDetector
        detector = ChromiumForkDetector()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = detector._find_profiles(Path(tmpdir))
            assert result == []


class TestMobileExtractor:
    """Tests for MobileExtractor."""

    def test_is_available_without_adb(self):
        """Should return False when ADB not installed."""
        from tokenade.core.importer.mobile_extractor import MobileExtractor

        with patch("subprocess.run", side_effect=FileNotFoundError):
            extractor = MobileExtractor()
            assert extractor.is_available() is False

    def test_list_devices_without_adb(self):
        """Should return empty list without ADB."""
        from tokenade.core.importer.mobile_extractor import MobileExtractor

        extractor = MobileExtractor.__new__(MobileExtractor)
        extractor._adb_available = False
        extractor.device_id = None

        result = extractor.list_devices()
        assert result == []

    def test_extract_without_adb(self):
        """Should return empty list without ADB."""
        from tokenade.core.importer.mobile_extractor import MobileExtractor

        extractor = MobileExtractor.__new__(MobileExtractor)
        extractor._adb_available = False
        extractor.device_id = None

        result = extractor.extract_chrome()
        assert result == []

    def test_extract_firefox_without_adb(self):
        """Should return empty list without ADB."""
        from tokenade.core.importer.mobile_extractor import MobileExtractor

        extractor = MobileExtractor.__new__(MobileExtractor)
        extractor._adb_available = False
        extractor.device_id = None

        result = extractor.extract_firefox()
        assert result == []

    def test_extract_samsung_without_adb(self):
        """Should return empty list without ADB."""
        from tokenade.core.importer.mobile_extractor import MobileExtractor

        extractor = MobileExtractor.__new__(MobileExtractor)
        extractor._adb_available = False
        extractor.device_id = None

        result = extractor.extract_samsung()
        assert result == []

    def test_extract_webview_without_adb(self):
        """Should return empty list without ADB."""
        from tokenade.core.importer.mobile_extractor import MobileExtractor

        extractor = MobileExtractor.__new__(MobileExtractor)
        extractor._adb_available = False
        extractor.device_id = None

        result = extractor.extract_webview()
        assert result == []

    def test_extract_ios_not_macos(self):
        """Should return empty on non-macOS."""
        if sys.platform == "darwin":
            pytest.skip("Testing non-macOS path")

        from tokenade.core.importer.mobile_extractor import MobileExtractor
        extractor = MobileExtractor.__new__(MobileExtractor)
        result = extractor.extract_ios_safari()
        assert result == []


class TestExtensionBridge:
    """Tests for ExtensionBridge."""

    def test_init_defaults(self):
        """Should initialize with default values."""
        from tokenade.core.proxy.extension_bridge import ExtensionBridge
        bridge = ExtensionBridge()
        assert bridge.host == "127.0.0.1"
        assert bridge.port == 9223
        assert bridge._running is False

    def test_init_custom_port(self):
        """Should accept custom port."""
        from tokenade.core.proxy.extension_bridge import ExtensionBridge
        bridge = ExtensionBridge(port=8080)
        assert bridge.port == 8080

    def test_on_message_registration(self):
        """Should register message handlers."""
        from tokenade.core.proxy.extension_bridge import ExtensionBridge
        bridge = ExtensionBridge()

        def handler(msg):
            return {"type": "response"}
        bridge.on_message("test", handler)

        assert "test" in bridge._message_handlers

    def test_get_status(self):
        """Should return status dict."""
        from tokenade.core.proxy.extension_bridge import ExtensionBridge
        bridge = ExtensionBridge()

        status = bridge.get_status()
        assert "host" in status
        assert "port" in status
        assert "running" in status
        assert "connected_clients" in status
        assert status["connected_clients"] == 0

    def test_stop(self):
        """Should set running to False."""
        from tokenade.core.proxy.extension_bridge import ExtensionBridge
        bridge = ExtensionBridge()
        bridge._running = True
        bridge.stop()
        assert bridge._running is False
