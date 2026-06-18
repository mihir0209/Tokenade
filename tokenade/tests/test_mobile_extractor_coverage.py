"""Comprehensive tests for mobile_extractor.py to boost coverage from 36% to 70%+."""

import subprocess
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch


from tokenade.core.importer.mobile_extractor import MobileExtractor


def _completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# __init__ & _check_adb
# ---------------------------------------------------------------------------

class TestInit:
    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    def test_adb_available(self, mock_run):
        mock_run.return_value = _completed(stdout="Android Debug Bridge version 1.0\n")
        ext = MobileExtractor()
        assert ext._adb_available is True

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run",
           side_effect=FileNotFoundError)
    def test_adb_not_found(self, _mock):
        ext = MobileExtractor()
        assert ext._adb_available is False

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run",
           side_effect=subprocess.TimeoutExpired(cmd="adb", timeout=5))
    def test_adb_timeout(self, _mock):
        ext = MobileExtractor()
        assert ext._adb_available is False

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    def test_adb_nonzero_returncode(self, mock_run):
        mock_run.return_value = _completed(returncode=1)
        ext = MobileExtractor()
        assert ext._adb_available is False

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    def test_device_id_stored(self, mock_run):
        mock_run.return_value = _completed()
        ext = MobileExtractor(device_id="ABC123")
        assert ext.device_id == "ABC123"


class TestIsAvailable:
    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    def test_returns_adb_status(self, mock_run):
        mock_run.return_value = _completed()
        ext = MobileExtractor()
        assert ext.is_available() is True

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run",
           side_effect=FileNotFoundError)
    def test_returns_false_when_adb_missing(self, _mock):
        ext = MobileExtractor()
        assert ext.is_available() is False


class TestListDevices:
    @patch("tokenade.core.importer.mobile_extractor.subprocess.run",
           side_effect=FileNotFoundError)
    def test_no_adb_returns_empty(self, _mock):
        ext = MobileExtractor()
        assert ext.list_devices() == []

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    def test_single_device(self, mock_run):
        mock_run.return_value = _completed(
            stdout="List of devices attached\nSERIAL123  device product:samsung model:SM_G960F\n\n"
        )
        ext = MobileExtractor()
        ext._adb_available = True
        devices = ext.list_devices()
        assert len(devices) == 1
        assert devices[0]["serial"] == "SERIAL123"
        assert devices[0]["status"] == "device"

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    def test_offline_device_skipped(self, mock_run):
        mock_run.return_value = _completed(
            stdout="List of devices attached\nSERIAL1  offline\nSERIAL2  device\n\n"
        )
        ext = MobileExtractor()
        ext._adb_available = True
        devices = ext.list_devices()
        assert len(devices) == 1
        assert devices[0]["serial"] == "SERIAL2"

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    def test_empty_line_skipped(self, mock_run):
        mock_run.return_value = _completed(stdout="List of devices attached\n\n\n")
        ext = MobileExtractor()
        ext._adb_available = True
        devices = ext.list_devices()
        assert devices == []

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    def test_exception_returns_empty(self, mock_run):
        mock_run.side_effect = [FileNotFoundError(), Exception("adb crashed")]
        ext = MobileExtractor()
        assert ext.list_devices() == []


class TestGetDeviceProp:
    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = _completed(stdout="SM_G960F\n")
        ext = MobileExtractor()
        result = ext._get_device_prop("SERIAL", "ro.product.model")
        assert result == "SM_G960F"

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    def test_failure_returns_unknown(self, mock_run):
        mock_run.side_effect = [FileNotFoundError(), Exception("fail")]
        ext = MobileExtractor()
        result = ext._get_device_prop("SERIAL", "ro.product.model")
        assert result == "unknown"


class TestBrowserExtractors:
    @patch("tokenade.core.importer.mobile_extractor.subprocess.run",
           side_effect=FileNotFoundError)
    def test_chrome_no_adb(self, _mock):
        ext = MobileExtractor()
        assert ext.extract_chrome() == []

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run",
           side_effect=FileNotFoundError)
    def test_firefox_no_adb(self, _mock):
        ext = MobileExtractor()
        assert ext.extract_firefox() == []

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run",
           side_effect=FileNotFoundError)
    def test_samsung_no_adb(self, _mock):
        ext = MobileExtractor()
        assert ext.extract_samsung() == []

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run",
           side_effect=FileNotFoundError)
    def test_webview_no_adb(self, _mock):
        ext = MobileExtractor()
        assert ext.extract_webview() == []


# ---------------------------------------------------------------------------
# _extract_via_adb
# ---------------------------------------------------------------------------

class TestExtractViaAdb:
    def test_adb_not_available(self):
        ext = MobileExtractor()
        ext._adb_available = False
        result = ext._extract_via_adb(
            paths=["/data/data/com.android.chrome/app_chrome/Default/Cookies"],
            browser="chrome", profile="Default",
        )
        assert result == []

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    @patch.object(MobileExtractor, "_pull_file", return_value=True)
    @patch.object(MobileExtractor, "_extract_from_file", return_value=[{"name": "test", "value": "val"}])
    @patch("pathlib.Path.exists", return_value=True)
    def test_wildcard_path_matching(self, mock_exists, mock_extract, mock_pull, mock_run):
        mock_run.return_value = _completed(returncode=0, stdout="Cookies\nCookies-journal\n")
        ext = MobileExtractor()
        ext._adb_available = True
        paths = ["/data/data/org.mozilla.firefox/files/mozilla/*.default*/cookies.sqlite"]
        result = ext._extract_via_adb(paths=paths, browser="firefox", profile="default")
        assert result == [{"name": "test", "value": "val"}]

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    @patch.object(MobileExtractor, "_pull_file", return_value=False)
    def test_wildcard_path_ls_fails(self, mock_pull, mock_run):
        mock_run.return_value = _completed(returncode=1, stdout="")
        ext = MobileExtractor()
        ext._adb_available = True
        paths = ["/data/data/org.mozilla.firefox/files/mozilla/*.default*/cookies.sqlite"]
        result = ext._extract_via_adb(paths=paths, browser="firefox", profile="default")
        assert result == []

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    @patch.object(MobileExtractor, "_pull_file", return_value=True)
    @patch.object(MobileExtractor, "_extract_from_file", return_value=[{"name": "cookie", "value": "v"}])
    @patch("pathlib.Path.exists", return_value=True)
    def test_non_wildcard_path(self, mock_exists, mock_extract, mock_pull, mock_run):
        mock_run.return_value = _completed()
        ext = MobileExtractor()
        ext._adb_available = True
        paths = ["/data/data/com.android.chrome/app_chrome/Default/Cookies"]
        result = ext._extract_via_adb(paths=paths, browser="chrome", profile="Default")
        assert result == [{"name": "cookie", "value": "v"}]

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    @patch.object(MobileExtractor, "_pull_file", return_value=True)
    def test_non_wildcard_local_file_missing(self, mock_pull, mock_run):
        mock_run.return_value = _completed()
        ext = MobileExtractor()
        ext._adb_available = True
        paths = ["/data/data/com.android.chrome/app_chrome/Default/Cookies"]
        result = ext._extract_via_adb(paths=paths, browser="chrome", profile="Default")
        assert result == []

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    @patch.object(MobileExtractor, "_pull_file", return_value=True)
    @patch.object(MobileExtractor, "_extract_from_file", return_value=[])
    def test_with_device_id(self, mock_extract, mock_pull, mock_run):
        mock_run.return_value = _completed()
        ext = MobileExtractor(device_id="DEVICE123")
        ext._adb_available = True
        paths = ["/data/data/com.android.chrome/app_chrome/Default/Cookies"]
        ext._extract_via_adb(paths=paths, browser="chrome", profile="Default")
        assert mock_pull.called

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    @patch.object(MobileExtractor, "_pull_file", return_value=False)
    def test_no_paths_match(self, mock_pull, mock_run):
        mock_run.return_value = _completed()
        ext = MobileExtractor()
        ext._adb_available = True
        paths = ["/nonexistent/path"]
        result = ext._extract_via_adb(paths=paths, browser="chrome", profile="Default")
        assert result == []


# ---------------------------------------------------------------------------
# _pull_file
# ---------------------------------------------------------------------------

class TestPullFile:
    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = _completed(returncode=0)
        ext = MobileExtractor()
        assert ext._pull_file("/remote/file", "/local/dir") is True

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = _completed(returncode=1)
        ext = MobileExtractor()
        assert ext._pull_file("/remote/file", "/local/dir") is False

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    def test_exception(self, mock_run):
        mock_run.side_effect = [FileNotFoundError(), Exception("timeout")]
        ext = MobileExtractor()
        assert ext._pull_file("/remote/file", "/local/dir") is False

    @patch("tokenade.core.importer.mobile_extractor.subprocess.run")
    def test_with_device_id(self, mock_run):
        mock_run.return_value = _completed(returncode=0)
        ext = MobileExtractor(device_id="DEV1")
        ext._pull_file("/remote/file", "/local/dir")
        call_args = mock_run.call_args[0][0]
        assert "-s" in call_args
        assert "DEV1" in call_args


# ---------------------------------------------------------------------------
# _extract_from_file
# ---------------------------------------------------------------------------

class TestExtractFromFile:
    @patch("tokenade.core.importer.mobile_extractor.shutil.copy2")
    def test_success(self, mock_copy):
        mock_extractor_class = MagicMock()
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract.return_value = [{"name": "c1", "value": "v1"}]
        mock_extractor_class.return_value = mock_extractor_instance

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            ext = MobileExtractor()
            with patch.dict("sys.modules", {
                "tokenade.core.importer.cookie_extractor": MagicMock(CookieExtractor=mock_extractor_class)
            }):
                result = ext._extract_from_file(db_path, "chrome")
                assert result == [{"name": "c1", "value": "v1"}]
                mock_extractor_instance.extract.assert_called_once()
        finally:
            Path(db_path).unlink(missing_ok=True)

    @patch("tokenade.core.importer.mobile_extractor.shutil.copy2",
           side_effect=Exception("copy failed"))
    def test_copy_failure(self, _mock):
        ext = MobileExtractor()
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            result = ext._extract_from_file(db_path, "chrome")
            assert result == []
        finally:
            Path(db_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# extract_ios_safari
# ---------------------------------------------------------------------------

class TestExtractIosSafari:
    @patch("tokenade.core.importer.mobile_extractor.sys")
    def test_non_darwin_platform(self, mock_sys):
        mock_sys.platform = "linux"
        ext = MobileExtractor()
        result = ext.extract_ios_safari()
        assert result == []

    @patch("tokenade.core.importer.mobile_extractor.sys")
    def test_import_error(self, mock_sys):
        mock_sys.platform = "darwin"
        with patch.dict("sys.modules", {"pymobiledevice3.lockdown": None, "pymobiledevice3.services.afc": None}):
            ext = MobileExtractor()
            result = ext.extract_ios_safari()
            assert result == []

    @patch("tokenade.core.importer.mobile_extractor.sys")
    @patch("tokenade.core.importer.mobile_extractor.tempfile.TemporaryDirectory")
    def test_afc_pull_failure(self, mock_tmp, mock_sys):
        mock_sys.platform = "darwin"
        mock_tmp.return_value.__enter__ = MagicMock(return_value="/tmp/fake")
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)

        mock_lockdown = MagicMock()
        mock_afc = MagicMock()
        mock_afc.pull.side_effect = Exception("pull failed")

        with patch.dict("sys.modules", {
            "pymobiledevice3.lockdown": MagicMock(create_using_usbmux=MagicMock(return_value=mock_lockdown)),
            "pymobiledevice3.services.afc": MagicMock(AfcService=MagicMock(return_value=mock_afc)),
        }):
            ext = MobileExtractor()
            result = ext.extract_ios_safari()
            assert result == []

    @patch("tokenade.core.importer.mobile_extractor.sys")
    @patch("tokenade.core.importer.mobile_extractor.tempfile.TemporaryDirectory")
    def test_successful_extraction(self, mock_tmp, mock_sys):
        mock_sys.platform = "darwin"
        tmpdir = tempfile.mkdtemp()
        mock_tmp.return_value.__enter__ = MagicMock(return_value=tmpdir)
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)

        mock_lockdown = MagicMock()
        mock_afc = MagicMock()
        mock_afc.pull.return_value = None

        mock_safari_extractor_class = MagicMock()
        mock_safari_instance = MagicMock()
        mock_safari_instance._parse_binary_cookies.return_value = [{"name": "test"}]
        mock_safari_extractor_class.return_value = mock_safari_instance

        with patch.dict("sys.modules", {
            "pymobiledevice3.lockdown": MagicMock(create_using_usbmux=MagicMock(return_value=mock_lockdown)),
            "pymobiledevice3.services.afc": MagicMock(AfcService=MagicMock(return_value=mock_afc)),
            "tokenade.core.importer.safari_extractor": MagicMock(SafariExtractor=mock_safari_extractor_class),
        }):
            ext = MobileExtractor()
            result = ext.extract_ios_safari()
            assert isinstance(result, list)
        shutil.rmtree(tmpdir, ignore_errors=True)

    @patch("tokenade.core.importer.mobile_extractor.sys")
    def test_non_darwin_win32(self, mock_sys):
        mock_sys.platform = "win32"
        ext = MobileExtractor()
        assert ext.extract_ios_safari() == []

    @patch("tokenade.core.importer.mobile_extractor.sys")
    @patch("tokenade.core.importer.mobile_extractor.tempfile.TemporaryDirectory")
    def test_afc_pull_no_cookies_file(self, mock_tmp, mock_sys):
        mock_sys.platform = "darwin"
        tmpdir = tempfile.mkdtemp()
        mock_tmp.return_value.__enter__ = MagicMock(return_value=tmpdir)
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)

        mock_lockdown = MagicMock()
        mock_afc = MagicMock()
        mock_afc.pull.return_value = None

        with patch.dict("sys.modules", {
            "pymobiledevice3.lockdown": MagicMock(create_using_usbmux=MagicMock(return_value=mock_lockdown)),
            "pymobiledevice3.services.afc": MagicMock(AfcService=MagicMock(return_value=mock_afc)),
        }):
            ext = MobileExtractor()
            result = ext.extract_ios_safari()
            assert result == []
        shutil.rmtree(tmpdir, ignore_errors=True)
