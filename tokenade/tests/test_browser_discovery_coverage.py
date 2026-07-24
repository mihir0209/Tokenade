"""Extended coverage tests for browser_discovery module."""

import json
import os
from pathlib import Path
from unittest.mock import patch

from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery, BrowserProfile


def _firefox_profile(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "cookies.sqlite").touch()
    (path / "prefs.js").write_text("user_pref('browser.startup.homepage', 'about:home');")
    return path


def _chromium_profile(path: Path, name: str = "Default") -> Path:
    path.mkdir(parents=True)
    (path.parent / "Local State").write_text(json.dumps({"profile": {"info_cache": {path.name: {"name": name}}}}))
    (path / "Preferences").write_text(json.dumps({"profile": {"name": name}}))
    network = path / "Network"
    network.mkdir()
    (network / "Cookies").touch()
    return path


class TestBrowserProfileDataclass:
    def test_to_dict(self):
        profile = BrowserProfile(
            name="Default",
            path="/home/user/.config/chrome/Default",
            browser="chrome",
            last_used="2024-01-01",
            is_default=True,
        )
        d = profile.to_dict()
        assert d["name"] == "Default"
        assert d["path"] == "/home/user/.config/chrome/Default"
        assert d["browser"] == "chrome"
        assert d["last_used"] == "2024-01-01"
        assert d["is_default"] is True

    def test_to_dict_defaults(self):
        profile = BrowserProfile(name="P1", path="/p1", browser="firefox")
        d = profile.to_dict()
        assert d["last_used"] is None
        assert d["is_default"] is False

    def test_profile_all_fields(self):
        profile = BrowserProfile(
            name="Test", path="/test", browser="edge",
            last_used="2024-06-01", is_default=True,
        )
        assert profile.name == "Test"
        assert profile.path == "/test"
        assert profile.browser == "edge"
        assert profile.last_used == "2024-06-01"
        assert profile.is_default is True


class TestExpandPath:
    def test_expand_user_home(self):
        d = BrowserProfileDiscovery()
        result = d._expand_path("~/test")
        assert result.startswith("/") or result[1] == ":"
        assert "test" in result

    def test_expand_no_vars(self):
        d = BrowserProfileDiscovery()
        result = d._expand_path("/absolute/path")
        assert result == "/absolute/path"

    def test_expand_env_var(self):
        d = BrowserProfileDiscovery()
        with patch.dict(os.environ, {"TESTVAR": "/test/value"}):
            result = d._expand_path("$TESTVAR/file")
            assert "/test/value/file" in result


class TestPathExists:
    def test_path_exists_true(self, tmp_path):
        d = BrowserProfileDiscovery()
        f = tmp_path / "exists.txt"
        f.write_text("x")
        assert d._path_exists(str(f)) is True

    def test_path_exists_false(self):
        d = BrowserProfileDiscovery()
        assert d._path_exists("/nonexistent/path/xyz") is False

    def test_path_exists_expands(self):
        d = BrowserProfileDiscovery()
        with patch.dict(os.environ, {"TESTVAR": "/nonexistent"}):
            assert d._path_exists("$TESTVAR/file") is False



class TestSignatureDiscovery:
    def test_discovers_firefox_from_arbitrary_root(self, tmp_path):
        profile_dir = _firefox_profile(tmp_path / "somewhere" / "snap" / "firefox" / "abc.default")
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])

        profiles = d.discover_firefox_profiles()

        assert len(profiles) == 1
        assert profiles[0].browser == "firefox"
        assert profiles[0].path == str(profile_dir.resolve())

    def test_discovers_firefox_profiles_ini_names_and_default(self, tmp_path):
        profile_dir = _firefox_profile(tmp_path / "portable" / "Profiles" / "abc.default")
        (tmp_path / "portable" / "profiles.ini").write_text(
            "[Profile0]\n"
            "Name=Personal\n"
            "IsRelative=1\n"
            "Path=Profiles/abc.default\n"
            "Default=1\n"
        )
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])

        profiles = d.discover_firefox_profiles()

        assert len(profiles) == 1
        assert profiles[0].name == "Personal"
        assert profiles[0].is_default is True
        assert profiles[0].path == str(profile_dir.resolve())

    def test_discovers_chromium_from_arbitrary_root(self, tmp_path):
        profile_dir = _chromium_profile(tmp_path / "unknown-place" / "Chrome Canary" / "Profile 7", "Work")
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])

        profiles = d.discover_chrome_profiles()

        assert len(profiles) == 1
        assert profiles[0].browser == "chrome"
        assert profiles[0].name == "Work"
        assert profiles[0].path == str(profile_dir.resolve())

    def test_classifies_edge_brave_vivaldi_by_path_tokens(self, tmp_path):
        edge = _chromium_profile(tmp_path / "random" / "Microsoft Edge" / "Default")
        brave = _chromium_profile(tmp_path / "random" / "BraveSoftware" / "Profile 1", "Brave Work")
        vivaldi = _chromium_profile(tmp_path / "random" / "vivaldi" / "Default")
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])

        profiles = d.discover_all()

        actual = {browser: [p.path for p in found] for browser, found in profiles.items()}
        assert actual["edge"] == [str(edge.resolve())], actual
        assert actual["brave"] == [str(brave.resolve())], actual
        assert actual["vivaldi"] == [str(vivaldi.resolve())], actual

    def test_classifies_windows_edge_user_data_layout(self, tmp_path):
        """Windows: .../Microsoft/Edge/User Data/Default (not 'Microsoft Edge')."""
        edge = _chromium_profile(
            tmp_path / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data" / "Default"
        )
        edge_beta = _chromium_profile(
            tmp_path
            / "AppData"
            / "Local"
            / "Microsoft"
            / "Edge Beta"
            / "User Data"
            / "Default",
            "Beta",
        )
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])
        profiles = d.discover_all(use_cache=False)
        paths = {p.path for p in profiles.get("edge") or []}
        assert str(edge.resolve()) in paths, profiles
        assert str(edge_beta.resolve()) in paths, profiles
        # Must not swallow Edge as chrome
        chrome_paths = {p.path for p in profiles.get("chrome") or []}
        assert str(edge.resolve()) not in chrome_paths
        assert any(v == "edge" for _, v in d.list_launch_browsers(use_cache=False))
        assert any(v == "edge" for _, v in d.list_export_browsers(use_cache=False))

    def test_env_scan_roots(self, tmp_path):
        profile_dir = _firefox_profile(tmp_path / "nested" / "abc.default")
        with patch.dict(os.environ, {BrowserProfileDiscovery.SCAN_ROOTS_ENV: str(tmp_path)}):
            d = BrowserProfileDiscovery()
            profiles = d.discover_firefox_profiles()
        assert [p.path for p in profiles] == [str(profile_dir.resolve())]

    def test_max_depth_limits_scan(self, tmp_path):
        _firefox_profile(tmp_path / "one" / "two" / "three" / "abc.default")
        d = BrowserProfileDiscovery(scan_roots=[tmp_path], max_depth=2)

        assert d.discover_firefox_profiles() == []

    def test_prunes_node_modules(self, tmp_path):
        _firefox_profile(tmp_path / "node_modules" / "package" / "abc.default")
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])

        assert d.discover_firefox_profiles() == []

    def test_ignores_chromium_like_app_data_without_user_data_parent(self, tmp_path):
        app_data = tmp_path / "Code"
        app_data.mkdir()
        (app_data / "Preferences").write_text(json.dumps({"profile": {"name": "Code"}}))
        network = app_data / "Network"
        network.mkdir()
        (network / "Cookies").touch()
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])

        assert d.discover_chrome_profiles() == []

    def test_filters_ebwebview_and_temp_cloak_profiles(self, tmp_path):
        """Windows EBWebView + temp cloak copies must not appear as chrome."""
        real = _chromium_profile(
            tmp_path / "AppData" / "Local" / "Google" / "Chrome" / "User Data" / "Default"
        )
        eb = _chromium_profile(
            tmp_path
            / "AppData"
            / "Local"
            / "Packages"
            / "MicrosoftWindows.Client.CBS_cw5n1h2txyewy"
            / "LocalState"
            / "EBWebView"
            / "Default"
        )
        cloak = _chromium_profile(
            tmp_path / "AppData" / "Local" / "Temp" / "tokenade_cloak_clean_abc123" / "Default"
        )
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])
        profiles = d.discover_all(use_cache=False)
        chrome_paths = {p.path for p in profiles.get("chrome") or []}
        assert str(real.resolve()) in chrome_paths
        assert str(eb.resolve()) not in chrome_paths
        assert str(cloak.resolve()) not in chrome_paths
        assert BrowserProfileDiscovery._is_junk_profile_path(eb) is True
        assert BrowserProfileDiscovery._is_junk_profile_path(cloak) is True
        assert BrowserProfileDiscovery._is_junk_profile_path(real) is False


class TestPersistentCache:
    def test_refresh_cache_writes_browser_paths_json(self, tmp_path):
        cache_path = tmp_path / "cache" / "browser_paths.json"
        profile_dir = _firefox_profile(tmp_path / "profiles" / "abc.default")
        with patch.dict(os.environ, {BrowserProfileDiscovery.CACHE_PATH_ENV: str(cache_path)}):
            d = BrowserProfileDiscovery(scan_roots=[tmp_path])
            result = d.refresh_cache()

        assert [p.path for p in result["firefox"]] == [str(profile_dir.resolve())]
        data = json.loads(cache_path.read_text())
        assert data["version"] == BrowserProfileDiscovery.CACHE_VERSION
        assert data["profiles"]["firefox"][0]["path"] == str(profile_dir.resolve())

    def test_discover_browser_reads_cache_before_scan(self, tmp_path):
        cache_path = tmp_path / "browser_paths.json"
        profile_dir = _firefox_profile(tmp_path / "profiles" / "abc.default")
        payload = {
            "version": BrowserProfileDiscovery.CACHE_VERSION,
            "created_at": 9999999999,
            "scan_roots": [str(tmp_path)],
            "profiles": {
                "chrome": [],
                "firefox": [{
                    "name": "default",
                    "path": str(profile_dir),
                    "browser": "firefox",
                    "last_used": None,
                    "is_default": True,
                }],
                "edge": [],
                "brave": [],
                "vivaldi": [],
            },
        }
        cache_path.write_text(json.dumps(payload))
        with patch.dict(os.environ, {BrowserProfileDiscovery.CACHE_PATH_ENV: str(cache_path)}):
            d = BrowserProfileDiscovery(scan_roots=[tmp_path])
            with patch.object(d, "_scan_profiles", side_effect=AssertionError("scan should not run")):
                profiles = d.discover_browser("firefox")

        assert [p.path for p in profiles] == [str(profile_dir)]

    def test_stale_cache_is_ignored(self, tmp_path):
        cache_path = tmp_path / "browser_paths.json"
        profile_dir = _firefox_profile(tmp_path / "profiles" / "abc.default")
        cache_path.write_text(json.dumps({
            "version": BrowserProfileDiscovery.CACHE_VERSION,
            "created_at": 0,
            "profiles": {"firefox": []},
        }))
        with patch.dict(os.environ, {
            BrowserProfileDiscovery.CACHE_PATH_ENV: str(cache_path),
            BrowserProfileDiscovery.CACHE_MAX_AGE_ENV: "1",
        }):
            d = BrowserProfileDiscovery(scan_roots=[tmp_path])
            profiles = d.discover_browser("firefox")

        assert [p.path for p in profiles] == [str(profile_dir.resolve())]


class TestDiscoverBrowserMethods:
    def test_no_profiles_returns_empty(self, tmp_path):
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])
        assert d.discover_chrome_profiles() == []
        assert d.discover_firefox_profiles() == []
        assert d.discover_edge_profiles() == []
        assert d.discover_brave_profiles() == []
        assert d.discover_vivaldi_profiles() == []

    def test_unknown_browser_returns_empty(self, tmp_path):
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])
        assert d.discover_browser("unknown_browser") == []

    def test_chromium_alias_maps_to_chrome(self, tmp_path):
        profile_dir = _chromium_profile(tmp_path / "chromium" / "Default")
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])
        profiles = d.discover_browser("chromium")
        assert [p.path for p in profiles] == [str(profile_dir.resolve())]


class TestGetProfile:
    def test_finds_existing_profile_by_name(self, tmp_path):
        _chromium_profile(tmp_path / "chrome" / "Default", "Person 1")
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])

        profile = d.get_profile("chrome", "Person 1")

        assert profile is not None
        assert profile.name == "Person 1"

    def test_finds_existing_profile_by_directory_name(self, tmp_path):
        _chromium_profile(tmp_path / "chrome" / "Profile 8", "Work")
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])

        profile = d.get_profile("chrome", "Profile 8")

        assert profile is not None
        assert profile.name == "Work"

    def test_returns_none_for_missing(self, tmp_path):
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])
        assert d.get_profile("chrome", "Nonexistent") is None

    def test_returns_none_for_unknown_browser(self, tmp_path):
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])
        assert d.get_profile("unknown_browser", "Default") is None


class TestGetDefaultProfile:
    def test_returns_default_profile(self, tmp_path):
        _chromium_profile(tmp_path / "chrome" / "Default")
        _chromium_profile(tmp_path / "chrome" / "Profile 2", "Other")
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])

        profile = d.get_default_profile("chrome")

        assert profile is not None
        assert profile.is_default is True

    def test_returns_first_when_no_default(self, tmp_path):
        _chromium_profile(tmp_path / "chrome" / "Profile 2", "Other")
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])

        profile = d.get_default_profile("chrome")
        assert profile is not None
        assert profile.name == "Other"

    def test_returns_none_for_empty(self, tmp_path):
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])
        assert d.get_default_profile("chrome") is None


class TestListProfilesText:
    def test_empty_profiles_text(self, tmp_path):
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])
        text = d.list_profiles_text()
        assert "No browser profiles found" in text
        assert "Total profiles: 0" in text

    def test_with_profiles_text(self, tmp_path):
        _chromium_profile(tmp_path / "chrome" / "Default")
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])
        text = d.list_profiles_text()
        assert "BROWSER PROFILES" in text
        assert "CHROME" in text
        assert "default" in text.lower()


class TestDiscoverAll:
    def test_returns_all_browser_keys(self, tmp_path):
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])
        result = d.discover_all()
        assert "chrome" in result
        assert "firefox" in result
        assert "edge" in result
        assert "brave" in result
        assert "vivaldi" in result

    def test_all_values_are_lists(self, tmp_path):
        d = BrowserProfileDiscovery(scan_roots=[tmp_path])
        result = d.discover_all()
        for key in result:
            assert isinstance(result[key], list)
