"""Extended coverage tests for chromium_forks module."""

from pathlib import Path
from unittest.mock import patch
from tokenade.core.importer.chromium_forks import ChromiumForkDetector, ChromiumForkInfo


class TestChromiumForkInfo:
    def test_dataclass_fields(self):
        info = ChromiumForkInfo(
            name="Brave",
            browser_type="brave",
            profile_dirs=[Path("/some/path")],
            is_default=True,
            notes="Test notes",
        )
        assert info.name == "Brave"
        assert info.browser_type == "brave"
        assert info.profile_dirs == [Path("/some/path")]
        assert info.is_default is True
        assert info.notes == "Test notes"

    def test_defaults(self):
        info = ChromiumForkInfo(
            name="Test",
            browser_type="chrome",
            profile_dirs=[],
        )
        assert info.is_default is False
        assert info.notes == ""


class TestGetNotes:
    def test_arc_notes(self):
        d = ChromiumForkDetector()
        notes = d._get_notes("arc")
        assert "Arc" in notes
        assert "Chromium" in notes

    def test_opera_notes(self):
        d = ChromiumForkDetector()
        notes = d._get_notes("opera")
        assert "Opera" in notes
        assert "VPN" in notes

    def test_vivaldi_notes(self):
        d = ChromiumForkDetector()
        notes = d._get_notes("vivaldi")
        assert "Vivaldi" in notes
        assert "customization" in notes

    def test_brave_notes(self):
        d = ChromiumForkDetector()
        notes = d._get_notes("brave")
        assert "Brave" in notes
        assert "Tor" in notes

    def test_edge_notes(self):
        d = ChromiumForkDetector()
        notes = d._get_notes("edge")
        assert "Edge" in notes
        assert "Microsoft" in notes

    def test_unknown_browser_notes(self):
        d = ChromiumForkDetector()
        notes = d._get_notes("unknown")
        assert notes == ""

    def test_chrome_notes(self):
        d = ChromiumForkDetector()
        notes = d._get_notes("chrome")
        assert notes == ""


class TestGetBrowserTypeForExtractor:
    def test_chrome_maps_to_chrome(self):
        d = ChromiumForkDetector()
        fork = ChromiumForkInfo(name="Chrome", browser_type="chrome", profile_dirs=[])
        assert d.get_browser_type_for_extractor(fork) == "chrome"

    def test_edge_maps_to_chrome(self):
        d = ChromiumForkDetector()
        fork = ChromiumForkInfo(name="Edge", browser_type="edge", profile_dirs=[])
        assert d.get_browser_type_for_extractor(fork) == "chrome"

    def test_brave_maps_to_chrome(self):
        d = ChromiumForkDetector()
        fork = ChromiumForkInfo(name="Brave", browser_type="brave", profile_dirs=[])
        assert d.get_browser_type_for_extractor(fork) == "chrome"

    def test_opera_maps_to_chrome(self):
        d = ChromiumForkDetector()
        fork = ChromiumForkInfo(name="Opera", browser_type="opera", profile_dirs=[])
        assert d.get_browser_type_for_extractor(fork) == "chrome"

    def test_vivaldi_maps_to_chrome(self):
        d = ChromiumForkDetector()
        fork = ChromiumForkInfo(name="Vivaldi", browser_type="vivaldi", profile_dirs=[])
        assert d.get_browser_type_for_extractor(fork) == "chrome"

    def test_arc_maps_to_chrome(self):
        d = ChromiumForkDetector()
        fork = ChromiumForkInfo(name="Arc", browser_type="arc", profile_dirs=[])
        assert d.get_browser_type_for_extractor(fork) == "chrome"

    def test_unknown_defaults_to_chrome(self):
        d = ChromiumForkDetector()
        fork = ChromiumForkInfo(name="Unknown", browser_type="unknown", profile_dirs=[])
        assert d.get_browser_type_for_extractor(fork) == "chrome"


class TestFindProfiles:
    def test_no_profiles_dir(self, tmp_path):
        d = ChromiumForkDetector()
        result = d._find_profiles(tmp_path)
        assert result == []

    def test_profiles_dir_with_cookies(self, tmp_path):
        d = ChromiumForkDetector()
        profiles_dir = tmp_path / "Profiles"
        profiles_dir.mkdir()
        profile_a = profiles_dir / "Profile A"
        profile_a.mkdir()
        (profile_a / "Cookies").touch()
        result = d._find_profiles(tmp_path)
        assert len(result) == 1
        assert result[0] == profile_a

    def test_profiles_dir_without_cookies(self, tmp_path):
        d = ChromiumForkDetector()
        profiles_dir = tmp_path / "Profiles"
        profiles_dir.mkdir()
        profile_a = profiles_dir / "Profile A"
        profile_a.mkdir()
        result = d._find_profiles(tmp_path)
        assert len(result) == 0

    def test_numbered_profiles(self, tmp_path):
        d = ChromiumForkDetector()
        parent = tmp_path / "UserData"
        parent.mkdir()
        profile1 = tmp_path / "Profile 1"
        profile1.mkdir()
        (profile1 / "Cookies").touch()
        result = d._find_profiles(parent)
        assert len(result) == 1
        assert profile1 in result

    def test_multiple_numbered_profiles(self, tmp_path):
        d = ChromiumForkDetector()
        parent = tmp_path / "UserData"
        parent.mkdir()
        for i in range(1, 4):
            p = tmp_path / f"Profile {i}"
            p.mkdir()
            (p / "Cookies").touch()
        result = d._find_profiles(parent)
        assert len(result) == 3

    def test_profiles_dir_items(self, tmp_path):
        d = ChromiumForkDetector()
        profiles_dir = tmp_path / "Profiles"
        profiles_dir.mkdir()
        p1 = profiles_dir / "Default"
        p1.mkdir()
        (p1 / "Cookies").touch()
        p2 = profiles_dir / "Profile 1"
        p2.mkdir()
        (p2 / "Cookies").touch()
        result = d._find_profiles(tmp_path)
        assert len(result) == 2


class TestDetectAll:
    def test_detect_all_returns_list(self):
        d = ChromiumForkDetector()
        with patch.object(d, "_find_profiles", return_value=[]):
            result = d.detect_all()
            assert isinstance(result, list)

    def test_detect_all_with_existing_browser(self, tmp_path):
        d = ChromiumForkDetector()
        edge_dir = tmp_path / "microsoft-edge"
        edge_dir.mkdir()
        (edge_dir / "Default").mkdir()
        (edge_dir / "Default" / "Cookies").touch()

        with patch("sys.platform", "linux"):
            original_paths = ChromiumForkDetector.BROWSER_PATHS.copy()
            ChromiumForkDetector.BROWSER_PATHS = {
                "edge": {
                    "linux": [
                        tmp_path / "microsoft-edge" / "Default",
                    ],
                },
            }
            try:
                result = d.detect_all()
                assert isinstance(result, list)
            finally:
                ChromiumForkDetector.BROWSER_PATHS = original_paths

    def test_detect_all_linux_platform(self, tmp_path):
        d = ChromiumForkDetector()
        with patch("sys.platform", "linux"):
            with patch.object(Path, "exists", return_value=False):
                result = d.detect_all()
                assert isinstance(result, list)

    def test_detect_all_darwin_platform(self, tmp_path):
        d = ChromiumForkDetector()
        with patch("sys.platform", "darwin"):
            with patch.object(Path, "exists", return_value=False):
                result = d.detect_all()
                assert isinstance(result, list)

    def test_detect_all_windows_platform(self, tmp_path):
        d = ChromiumForkDetector()
        with patch("sys.platform", "win32"):
            with patch.object(Path, "exists", return_value=False):
                result = d.detect_all()
                assert isinstance(result, list)

    def test_detect_all_with_none_paths(self, tmp_path):
        d = ChromiumForkDetector()
        with patch("sys.platform", "linux"):
            with patch.object(Path, "exists", return_value=False):
                result = d.detect_all()
                assert isinstance(result, list)


class TestDetectAllIntegration:
    def test_detect_brave_profiles(self, tmp_path):
        d = ChromiumForkDetector()
        brave_dir = tmp_path / "BraveSoftware" / "Brave-Browser"
        brave_dir.mkdir(parents=True)
        default = brave_dir / "Default"
        default.mkdir()
        (default / "Cookies").touch()

        with patch("sys.platform", "linux"):
            with patch.object(Path, "home", return_value=tmp_path):
                # Override the BROWSER_PATHS to point to our test directory
                original_paths = ChromiumForkDetector.BROWSER_PATHS.copy()
                ChromiumForkDetector.BROWSER_PATHS = {
                    "brave": {
                        "linux": [
                            tmp_path / "BraveSoftware" / "Brave-Browser" / "Default",
                        ],
                    },
                }
                try:
                    result = d.detect_all()
                    assert len(result) >= 1
                    assert any(f.browser_type == "brave" for f in result)
                finally:
                    ChromiumForkDetector.BROWSER_PATHS = original_paths

    def test_detect_edge_profiles(self, tmp_path):
        d = ChromiumForkDetector()
        edge_dir = tmp_path / "microsoft-edge"
        edge_dir.mkdir()
        default = edge_dir / "Default"
        default.mkdir()
        (default / "Cookies").touch()

        with patch("sys.platform", "linux"):
            with patch.object(Path, "home", return_value=tmp_path):
                original_paths = ChromiumForkDetector.BROWSER_PATHS.copy()
                ChromiumForkDetector.BROWSER_PATHS = {
                    "edge": {
                        "linux": [
                            tmp_path / "microsoft-edge" / "Default",
                        ],
                    },
                }
                try:
                    result = d.detect_all()
                    assert len(result) >= 1
                    assert any(f.browser_type == "edge" for f in result)
                finally:
                    ChromiumForkDetector.BROWSER_PATHS = original_paths

    def test_detect_opera_profiles(self, tmp_path):
        d = ChromiumForkDetector()
        opera_dir = tmp_path / ".config" / "opera"
        opera_dir.mkdir(parents=True)
        default = opera_dir / "Default"
        default.mkdir()
        (default / "Cookies").touch()

        with patch("sys.platform", "linux"):
            with patch.object(Path, "home", return_value=tmp_path):
                original_paths = ChromiumForkDetector.BROWSER_PATHS.copy()
                ChromiumForkDetector.BROWSER_PATHS = {
                    "opera": {
                        "linux": [
                            tmp_path / ".config" / "opera" / "Default",
                        ],
                    },
                }
                try:
                    result = d.detect_all()
                    assert len(result) >= 1
                    assert any(f.browser_type == "opera" for f in result)
                finally:
                    ChromiumForkDetector.BROWSER_PATHS = original_paths

    def test_detect_vivaldi_profiles(self, tmp_path):
        d = ChromiumForkDetector()
        vivaldi_dir = tmp_path / ".config" / "vivaldi"
        vivaldi_dir.mkdir(parents=True)
        default = vivaldi_dir / "Default"
        default.mkdir()
        (default / "Cookies").touch()

        with patch("sys.platform", "linux"):
            with patch.object(Path, "home", return_value=tmp_path):
                original_paths = ChromiumForkDetector.BROWSER_PATHS.copy()
                ChromiumForkDetector.BROWSER_PATHS = {
                    "vivaldi": {
                        "linux": [
                            tmp_path / ".config" / "vivaldi" / "Default",
                        ],
                    },
                }
                try:
                    result = d.detect_all()
                    assert len(result) >= 1
                    assert any(f.browser_type == "vivaldi" for f in result)
                finally:
                    ChromiumForkDetector.BROWSER_PATHS = original_paths

    def test_no_browsers_detected(self, tmp_path):
        d = ChromiumForkDetector()
        with patch("sys.platform", "linux"):
            with patch.object(Path, "exists", return_value=False):
                result = d.detect_all()
                assert result == []

    def test_detect_with_profiles_subdir(self, tmp_path):
        d = ChromiumForkDetector()
        # Create structure: edge_user_data/Default/Profiles/Profile 1/Cookies
        edge_user_data = tmp_path / "microsoft-edge"
        edge_user_data.mkdir()
        default = edge_user_data / "Default"
        default.mkdir()
        (default / "Cookies").touch()
        profiles_dir = default / "Profiles"
        profiles_dir.mkdir()
        prof = profiles_dir / "Profile 1"
        prof.mkdir()
        (prof / "Cookies").touch()

        original_paths = ChromiumForkDetector.BROWSER_PATHS.copy()
        ChromiumForkDetector.BROWSER_PATHS = {
            "edge": {
                "linux": [edge_user_data / "Default"],
            },
        }
        try:
            with patch("sys.platform", "linux"):
                result = d.detect_all()
                assert len(result) >= 1
                all_dirs = [str(p) for f in result for p in f.profile_dirs]
                assert any("Profile 1" in d for d in all_dirs)
        finally:
            ChromiumForkDetector.BROWSER_PATHS = original_paths


class TestBrowserPaths:
    def test_arc_has_all_platforms(self):
        assert "linux" in ChromiumForkDetector.BROWSER_PATHS["arc"]
        assert "darwin" in ChromiumForkDetector.BROWSER_PATHS["arc"]
        assert "windows" in ChromiumForkDetector.BROWSER_PATHS["arc"]

    def test_opera_has_all_platforms(self):
        assert "linux" in ChromiumForkDetector.BROWSER_PATHS["opera"]
        assert "darwin" in ChromiumForkDetector.BROWSER_PATHS["opera"]
        assert "windows" in ChromiumForkDetector.BROWSER_PATHS["opera"]

    def test_vivaldi_has_all_platforms(self):
        assert "linux" in ChromiumForkDetector.BROWSER_PATHS["vivaldi"]
        assert "darwin" in ChromiumForkDetector.BROWSER_PATHS["vivaldi"]
        assert "windows" in ChromiumForkDetector.BROWSER_PATHS["vivaldi"]

    def test_brave_has_all_platforms(self):
        assert "linux" in ChromiumForkDetector.BROWSER_PATHS["brave"]
        assert "darwin" in ChromiumForkDetector.BROWSER_PATHS["brave"]
        assert "windows" in ChromiumForkDetector.BROWSER_PATHS["brave"]

    def test_edge_has_all_platforms(self):
        assert "linux" in ChromiumForkDetector.BROWSER_PATHS["edge"]
        assert "darwin" in ChromiumForkDetector.BROWSER_PATHS["edge"]
        assert "windows" in ChromiumForkDetector.BROWSER_PATHS["edge"]

    def test_linux_opera_has_two_paths(self):
        paths = ChromiumForkDetector.BROWSER_PATHS["opera"]["linux"]
        assert len(paths) == 2

    def test_linux_vivaldi_has_two_paths(self):
        paths = ChromiumForkDetector.BROWSER_PATHS["vivaldi"]["linux"]
        assert len(paths) == 2

    def test_linux_edge_has_two_paths(self):
        paths = ChromiumForkDetector.BROWSER_PATHS["edge"]["linux"]
        assert len(paths) == 2

    def test_linux_brave_has_two_paths(self):
        paths = ChromiumForkDetector.BROWSER_PATHS["brave"]["linux"]
        assert len(paths) == 2
