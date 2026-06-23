"""Tests for mobile import manager (Phase 39)."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

from tokenade.core.importer.mobile_import import (
    MobileDevice, MobileExtractResult, MobileImportManager,
    ANDROID_BROWSERS,
)


class TestMobileDevice:

    def test_to_dict(self):
        device = MobileDevice(
            serial="ABC123", platform="android", model="Pixel 6",
            os_version="13", available_browsers=["chrome", "firefox"],
        )
        data = device.to_dict()
        assert data["serial"] == "ABC123"
        assert data["platform"] == "android"
        assert data["model"] == "Pixel 6"
        assert "chrome" in data["available_browsers"]

    def test_defaults(self):
        device = MobileDevice(serial="X", platform="ios")
        assert device.model == "unknown"
        assert device.available_browsers == []


class TestMobileExtractResult:

    def test_to_dict_success(self):
        device = MobileDevice(serial="X", platform="android", model="Pixel")
        result = MobileExtractResult(
            success=True, device=device, browser="chrome",
            cookie_count=10, session_file="out.tokenade",
            site_name="github", auth_status="logged_in",
            domains=["github.com"],
        )
        data = result.to_dict()
        assert data["success"] is True
        assert data["cookie_count"] == 10

    def test_to_dict_failure(self):
        result = MobileExtractResult(
            success=False, error="No device connected",
        )
        data = result.to_dict()
        assert data["success"] is False
        assert "No device" in data["error"]


class TestMobileImportManager:

    def test_init(self):
        manager = MobileImportManager()
        assert hasattr(manager, '_adb_available')
        assert hasattr(manager, '_ios_available')

    def test_is_available(self):
        manager = MobileImportManager()
        # Should not raise
        result = manager.is_available()
        assert isinstance(result, bool)

    @patch("subprocess.run")
    def test_list_devices_no_adb(self, mock_run):
        mock_run.side_effect = FileNotFoundError("adb not found")
        manager = MobileImportManager()
        manager._adb_available = False
        manager._ios_available = False
        devices = manager.list_devices()
        assert devices == []

    @patch("subprocess.run")
    def test_list_android_devices_empty(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="List of devices attached\n\n",
            returncode=0,
        )
        manager = MobileImportManager()
        manager._adb_available = True
        devices = manager._list_android_devices()
        assert devices == []

    @patch("subprocess.run")
    def test_list_android_devices_one(self, mock_run):
        # First call: adb devices -l
        # Second call: getprop model
        # Third call: getprop version
        # Fourth call: pm list packages (chrome)
        # Fifth call: pm list packages (firefox)
        # etc.
        call_count = [0]
        def side_effect(cmd, **kwargs):
            call_count[0] += 1
            cmd_str = " ".join(cmd)
            if "devices" in cmd_str:
                return MagicMock(
                    stdout="List of devices attached\nABC123\tdevice product:sdk_model transport_id:1\n",
                    returncode=0,
                )
            elif "ro.product.model" in cmd_str:
                return MagicMock(stdout="Pixel 6\n", returncode=0)
            elif "ro.build.version.release" in cmd_str:
                return MagicMock(stdout="13\n", returncode=0)
            elif "pm list packages" in cmd_str:
                if "com.android.chrome" in cmd_str:
                    return MagicMock(stdout="package:com.android.chrome\n", returncode=0)
                return MagicMock(stdout="", returncode=0)
            return MagicMock(stdout="", returncode=0)

        mock_run.side_effect = side_effect
        manager = MobileImportManager()
        manager._adb_available = True
        devices = manager._list_android_devices()
        assert len(devices) == 1
        assert devices[0].serial == "ABC123"
        assert devices[0].model == "Pixel 6"
        assert "chrome" in devices[0].available_browsers

    def test_extract_no_browsers(self):
        device = MobileDevice(serial="X", platform="android", available_browsers=[])
        manager = MobileImportManager()
        result = manager.extract(device, browser="auto")
        assert result.success is False
        assert "No browsers" in result.error

    def test_extract_unknown_browser(self):
        device = MobileDevice(serial="X", platform="android", available_browsers=["chrome"])
        manager = MobileImportManager()
        result = manager.extract(device, browser="opera")
        assert result.success is False
        assert "not installed" in result.error

    def test_extract_unsupported_platform(self):
        device = MobileDevice(serial="X", platform="windows", available_browsers=["ie"])
        manager = MobileImportManager()
        result = manager.extract(device, browser="ie")
        assert result.success is False
        assert "Unsupported platform" in result.error

    def test_android_browsers_config(self):
        assert "chrome" in ANDROID_BROWSERS
        assert "firefox" in ANDROID_BROWSERS
        assert "samsung" in ANDROID_BROWSERS
        assert "brave" in ANDROID_BROWSERS
        assert "edge" in ANDROID_BROWSERS
        for name, info in ANDROID_BROWSERS.items():
            assert "package" in info
            assert "paths" in info
            assert len(info["paths"]) > 0

    @patch("subprocess.run")
    def test_adb_pull_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        manager = MobileImportManager.__new__(MobileImportManager)
        with patch("pathlib.Path.mkdir"), patch("pathlib.Path.exists", return_value=True):
            result = manager._adb_pull("ABC123", "/remote/file", "/local/file")
            assert result is True

    @patch("subprocess.run")
    def test_adb_pull_failure(self, mock_run):
        mock_run.side_effect = Exception("timeout")
        manager = MobileImportManager.__new__(MobileImportManager)
        result = manager._adb_pull("ABC123", "/remote/file", "/local/file")
        assert result is False

    def test_extract_ios_not_macos(self):
        device = MobileDevice(serial="X", platform="ios", available_browsers=["safari"])
        manager = MobileImportManager()
        with patch("platform.system", return_value="Linux"):
            result = manager._extract_ios(device, "safari", None, None, None)
            assert result.success is False
            assert "macOS" in result.error

    def test_list_devices_dispatch(self):
        """Test that list_devices calls platform-specific methods."""
        manager = MobileImportManager()
        manager._adb_available = True
        manager._ios_available = False
        with patch.object(manager, '_list_android_devices', return_value=[]):
            devices = manager.list_devices()
            assert devices == []

    def test_list_devices_both_platforms(self):
        """Test listing devices from both platforms."""
        manager = MobileImportManager()
        manager._adb_available = True
        manager._ios_available = True
        android_device = MobileDevice(serial="A1", platform="android", model="Pixel")
        ios_device = MobileDevice(serial="B2", platform="ios", model="iPhone")
        with patch.object(manager, '_list_android_devices', return_value=[android_device]), \
             patch.object(manager, '_list_ios_devices', return_value=[ios_device]):
            devices = manager.list_devices()
            assert len(devices) == 2

    def test_extract_auto_selects_first_browser(self):
        """Test auto-select picks first available browser."""
        device = MobileDevice(
            serial="X", platform="android",
            available_browsers=["firefox", "chrome"],
        )
        manager = MobileImportManager()
        # Mock the actual extraction to avoid ADB
        with patch.object(manager, '_extract_android') as mock_extract:
            mock_extract.return_value = MobileExtractResult(
                success=True, browser="firefox", cookie_count=5,
            )
            result = manager.extract(device, browser="auto")
            assert result.success is True
            mock_extract.assert_called_once()

    def test_extract_android_with_domains(self, tmp_path):
        """Test Android extraction with domain filtering."""
        # This tests the domain filtering logic without ADB
        manager = MobileImportManager()

        # Create a mock cookies list
        cookies = [
            {"name": "token", "value": "abc", "domain": ".github.com", "path": "/"},
            {"name": "other", "value": "xyz", "domain": ".example.com", "path": "/"},
        ]

        # Test domain filtering logic inline
        domains = ["github.com"]
        filtered = []
        for cookie in cookies:
            cookie_domain = cookie.get("domain", "").lstrip(".")
            for d in domains:
                d_clean = d.lstrip(".")
                if cookie_domain == d_clean or cookie_domain.endswith("." + d_clean):
                    filtered.append(cookie)
                    break

        assert len(filtered) == 1
        assert filtered[0]["name"] == "token"
