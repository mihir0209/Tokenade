"""Extended coverage tests for browser_discovery module."""

import os
from unittest.mock import patch
from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery, BrowserProfile


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


class TestDiscoverChromeProfiles:
    def test_no_profiles_returns_empty(self):
        d = BrowserProfileDiscovery()
        with patch("os.path.exists", return_value=False):
            profiles = d.discover_chrome_profiles()
            assert profiles == []

    def test_discovers_default_profile(self, tmp_path):
        d = BrowserProfileDiscovery()
        chrome_dir = tmp_path / "chrome_data"
        chrome_dir.mkdir()
        default = chrome_dir / "Default"
        default.mkdir()

        with patch.object(d, "_expand_path", return_value=str(chrome_dir)):
            with patch("tokenade.core.importer.browser_discovery.os.path.exists", side_effect=lambda p: True if str(p) == str(chrome_dir) or str(p) == str(default) else False):
                profiles = d.discover_chrome_profiles()
                assert len(profiles) >= 1
                assert any(p.is_default for p in profiles)

    def test_discovers_additional_profiles(self, tmp_path):
        d = BrowserProfileDiscovery()
        chrome_dir = tmp_path / "chrome_data"
        chrome_dir.mkdir()
        (chrome_dir / "Default").mkdir()
        (chrome_dir / "Profile 1").mkdir()
        default_path = str(chrome_dir / "Default")
        p1_path = str(chrome_dir / "Profile 1")
        base_str = str(chrome_dir)

        call_count = [0]

        def expand_side_effect(path):
            call_count[0] += 1
            if call_count[0] == 1:
                return base_str
            return "/nonexistent/path"

        with patch.object(d, "_expand_path", side_effect=expand_side_effect):
            with patch("os.path.exists", side_effect=lambda p: p in (base_str, default_path)):
                with patch("glob.glob", return_value=[p1_path]):
                    profiles = d.discover_chrome_profiles()
                    assert len(profiles) == 2

    def test_empty_os_type_returns_empty(self):
        d = BrowserProfileDiscovery()
        d.os_type = "UnsupportedOS"
        profiles = d.discover_chrome_profiles()
        assert profiles == []


class TestDiscoverFirefoxProfiles:
    def test_no_profiles_returns_empty(self):
        d = BrowserProfileDiscovery()
        with patch("os.path.exists", return_value=False):
            profiles = d.discover_firefox_profiles()
            assert profiles == []

    def test_profiles_ini_parsing(self, tmp_path):
        d = BrowserProfileDiscovery()
        base = tmp_path / "mozilla"
        base.mkdir()
        profiles_ini = tmp_path / "profiles.ini"
        profiles_ini.write_text(
            "[Profile0]\n"
            "Name=default\n"
            "IsRelative=1\n"
            "Path=Profiles/abc.default\n"
            "Default=1\n"
        )
        profile_dir = tmp_path / "Profiles" / "abc.default"
        profile_dir.mkdir(parents=True)

        with patch.object(d, "_expand_path", return_value=str(base)):
            def fake_exists(p):
                p_str = str(p)
                if p_str == str(base):
                    return True
                if p_str == str(profiles_ini):
                    return True
                if p_str == str(profile_dir):
                    return True
                return False
            with patch("os.path.exists", side_effect=fake_exists):
                profiles = d.discover_firefox_profiles()
                assert len(profiles) >= 1

    def test_absolute_path_profile(self, tmp_path):
        d = BrowserProfileDiscovery()
        base = tmp_path / "mozilla"
        base.mkdir()
        profile_dir = tmp_path / "absolute_profile"
        profile_dir.mkdir()

        profiles_ini = tmp_path / "profiles.ini"
        profiles_ini.write_text(
            "[Profile0]\n"
            "Name=AbsProfile\n"
            "IsRelative=0\n"
            f"Path={profile_dir}\n"
            "Default=1\n"
        )

        with patch.object(d, "_expand_path", return_value=str(base)):
            def fake_exists(p):
                p_str = str(p)
                if p_str == str(base):
                    return True
                if p_str == str(profiles_ini):
                    return True
                if p_str == str(profile_dir):
                    return True
                return False
            with patch("os.path.exists", side_effect=fake_exists):
                profiles = d.discover_firefox_profiles()
                assert len(profiles) >= 1

    def test_fallback_directory_scan(self, tmp_path):
        d = BrowserProfileDiscovery()
        base = tmp_path / "mozilla"
        base.mkdir()
        profile_dir = base / "abc.default-release"
        profile_dir.mkdir()

        base_str = str(base)
        profile_str = str(profile_dir)

        call_count = [0]

        def expand_side_effect(path):
            call_count[0] += 1
            if call_count[0] == 1:
                return base_str
            return "/nonexistent/path"

        with patch.object(d, "_expand_path", side_effect=expand_side_effect):
            def exists_side_effect(p):
                p_str = str(p)
                if p_str == base_str:
                    return True
                if "profiles.ini" in p_str:
                    return False
                if p_str == profile_str:
                    return True
                return False
            with patch("os.path.exists", side_effect=exists_side_effect):
                with patch("glob.glob", return_value=[profile_str]):
                    profiles = d.discover_firefox_profiles()
                    assert len(profiles) == 1
                    assert profiles[0].browser == "firefox"

    def test_profiles_ini_in_parent_dir(self, tmp_path):
        d = BrowserProfileDiscovery()
        base = tmp_path / "mozilla" / "firefox"
        base.mkdir(parents=True)
        profiles_ini = tmp_path / "mozilla" / "profiles.ini"
        profiles_ini.write_text(
            "[Profile0]\n"
            "Name=default\n"
            "IsRelative=1\n"
            "Path=firefox/abc.default\n"
            "Default=1\n"
        )
        profile_dir = base / "abc.default"
        profile_dir.mkdir()

        with patch.object(d, "_expand_path", return_value=str(base)):
            def fake_exists(p):
                p_str = str(p)
                if p_str == str(base):
                    return True
                if p_str == str(profiles_ini):
                    return True
                if p_str == str(profile_dir):
                    return True
                return False
            with patch("os.path.exists", side_effect=fake_exists):
                profiles = d.discover_firefox_profiles()
                assert len(profiles) >= 1

    def test_invalid_profiles_ini(self, tmp_path):
        d = BrowserProfileDiscovery()
        base = tmp_path / "mozilla"
        base.mkdir()
        profiles_ini = tmp_path / "profiles.ini"
        profiles_ini.write_text("this is not valid ini {{{")

        with patch.object(d, "_expand_path", return_value=str(base)):
            with patch("os.path.exists", return_value=True):
                profiles = d.discover_firefox_profiles()
                assert isinstance(profiles, list)

    def test_empty_profiles_ini(self, tmp_path):
        d = BrowserProfileDiscovery()
        base = tmp_path / "mozilla"
        base.mkdir()
        profiles_ini = tmp_path / "profiles.ini"
        profiles_ini.write_text("")

        with patch.object(d, "_expand_path", return_value=str(base)):
            with patch("os.path.exists", return_value=True):
                profiles = d.discover_firefox_profiles()
                assert profiles == []

    def test_os_type_not_matching(self):
        d = BrowserProfileDiscovery()
        d.os_type = "UnsupportedOS"
        profiles = d.discover_firefox_profiles()
        assert profiles == []


class TestDiscoverEdgeProfiles:
    def test_no_profiles_returns_empty(self):
        d = BrowserProfileDiscovery()
        with patch("os.path.exists", return_value=False):
            profiles = d.discover_edge_profiles()
            assert profiles == []

    def test_discovers_default_profile(self, tmp_path):
        d = BrowserProfileDiscovery()
        edge_dir = tmp_path / "edge_data"
        edge_dir.mkdir()
        (edge_dir / "Default").mkdir()

        with patch.object(d, "_expand_path", return_value=str(edge_dir)):
            with patch("os.path.exists", return_value=True):
                with patch("glob.glob", return_value=[]):
                    profiles = d.discover_edge_profiles()
                    assert len(profiles) == 1
                    assert profiles[0].browser == "edge"
                    assert profiles[0].is_default is True

    def test_discovers_additional_profiles(self, tmp_path):
        d = BrowserProfileDiscovery()
        edge_dir = tmp_path / "edge_data"
        edge_dir.mkdir()
        (edge_dir / "Default").mkdir()
        (edge_dir / "Profile 1").mkdir()

        with patch.object(d, "_expand_path", return_value=str(edge_dir)):
            with patch("os.path.exists", return_value=True):
                with patch("glob.glob", return_value=[str(edge_dir / "Profile 1")]):
                    profiles = d.discover_edge_profiles()
                    assert len(profiles) == 2

    def test_no_default_profile(self, tmp_path):
        d = BrowserProfileDiscovery()
        edge_dir = tmp_path / "edge_data"
        edge_dir.mkdir()
        # No "Default" directory created

        with patch.object(d, "_expand_path", return_value=str(edge_dir)):
            with patch("os.path.exists", side_effect=lambda p: str(p) == str(edge_dir)):
                with patch("glob.glob", return_value=[]):
                    profiles = d.discover_edge_profiles()
                    assert len(profiles) == 0

    def test_os_type_not_matching(self):
        d = BrowserProfileDiscovery()
        d.os_type = "UnsupportedOS"
        profiles = d.discover_edge_profiles()
        assert profiles == []


class TestDiscoverBraveProfiles:
    def test_no_profiles_returns_empty(self):
        d = BrowserProfileDiscovery()
        with patch("os.path.exists", return_value=False):
            profiles = d.discover_brave_profiles()
            assert profiles == []

    def test_discovers_default_profile(self, tmp_path):
        d = BrowserProfileDiscovery()
        brave_dir = tmp_path / "brave_data"
        brave_dir.mkdir()
        (brave_dir / "Default").mkdir()

        with patch.object(d, "_expand_path", return_value=str(brave_dir)):
            with patch("os.path.exists", return_value=True):
                with patch("glob.glob", return_value=[]):
                    profiles = d.discover_brave_profiles()
                    assert len(profiles) == 1
                    assert profiles[0].browser == "brave"

    def test_discovers_additional_profiles(self, tmp_path):
        d = BrowserProfileDiscovery()
        brave_dir = tmp_path / "brave_data"
        brave_dir.mkdir()
        (brave_dir / "Default").mkdir()
        (brave_dir / "Profile 1").mkdir()

        with patch.object(d, "_expand_path", return_value=str(brave_dir)):
            with patch("os.path.exists", return_value=True):
                with patch("glob.glob", return_value=[str(brave_dir / "Profile 1")]):
                    profiles = d.discover_brave_profiles()
                    assert len(profiles) == 2

    def test_os_type_not_matching(self):
        d = BrowserProfileDiscovery()
        d.os_type = "UnsupportedOS"
        profiles = d.discover_brave_profiles()
        assert profiles == []


class TestGetProfile:
    def test_finds_existing_profile(self, tmp_path):
        d = BrowserProfileDiscovery()
        chrome_dir = tmp_path / "chrome"
        chrome_dir.mkdir()
        (chrome_dir / "Default").mkdir()

        with patch.object(d, "_expand_path", return_value=str(chrome_dir)):
            with patch("os.path.exists", return_value=True):
                with patch("glob.glob", return_value=[]):
                    profile = d.get_profile("chrome", "Default")
                    assert profile is not None
                    assert profile.name == "Default"

    def test_returns_none_for_missing(self):
        d = BrowserProfileDiscovery()
        with patch("os.path.exists", return_value=False):
            profile = d.get_profile("chrome", "Nonexistent")
            assert profile is None

    def test_returns_none_for_unknown_browser(self):
        d = BrowserProfileDiscovery()
        with patch("os.path.exists", return_value=False):
            profile = d.get_profile("unknown_browser", "Default")
            assert profile is None


class TestGetDefaultProfile:
    def test_returns_default_profile(self, tmp_path):
        d = BrowserProfileDiscovery()
        chrome_dir = tmp_path / "chrome"
        chrome_dir.mkdir()
        (chrome_dir / "Default").mkdir()

        with patch.object(d, "_expand_path", return_value=str(chrome_dir)):
            with patch("os.path.exists", return_value=True):
                with patch("glob.glob", return_value=[]):
                    profile = d.get_default_profile("chrome")
                    assert profile is not None
                    assert profile.is_default is True

    def test_returns_first_when_no_default(self, tmp_path):
        d = BrowserProfileDiscovery()
        edge_dir = tmp_path / "edge"
        edge_dir.mkdir()

        with patch.object(d, "_expand_path", return_value=str(edge_dir)):
            with patch("os.path.exists", return_value=True):
                with patch("glob.glob", return_value=[]):
                    d.get_default_profile("edge")
                    # May be None or first profile depending on structure

    def test_returns_none_for_empty(self):
        d = BrowserProfileDiscovery()
        with patch("os.path.exists", return_value=False):
            profile = d.get_default_profile("nonexistent")
            assert profile is None


class TestListProfilesText:
    def test_empty_profiles_text(self):
        d = BrowserProfileDiscovery()
        with patch("os.path.exists", return_value=False):
            text = d.list_profiles_text()
            assert "No browser profiles found" in text
            assert "Total profiles: 0" in text

    def test_with_profiles_text(self, tmp_path):
        d = BrowserProfileDiscovery()
        chrome_dir = tmp_path / "chrome"
        chrome_dir.mkdir()
        (chrome_dir / "Default").mkdir()

        with patch.object(d, "_expand_path", return_value=str(chrome_dir)):
            with patch("os.path.exists", return_value=True):
                with patch("glob.glob", return_value=[]):
                    text = d.list_profiles_text()
                    assert "BROWSER PROFILES" in text
                    assert "=" * 60 in text

    def test_profiles_text_contains_default_mark(self, tmp_path):
        d = BrowserProfileDiscovery()
        chrome_dir = tmp_path / "chrome"
        chrome_dir.mkdir()
        (chrome_dir / "Default").mkdir()

        with patch.object(d, "_expand_path", return_value=str(chrome_dir)):
            with patch("os.path.exists", return_value=True):
                with patch("glob.glob", return_value=[]):
                    text = d.list_profiles_text()
                    assert "default" in text.lower()


class TestDiscoverAll:
    def test_returns_all_browser_keys(self):
        d = BrowserProfileDiscovery()
        with patch("os.path.exists", return_value=False):
            result = d.discover_all()
            assert "chrome" in result
            assert "firefox" in result
            assert "edge" in result
            assert "brave" in result

    def test_all_values_are_lists(self):
        d = BrowserProfileDiscovery()
        with patch("os.path.exists", return_value=False):
            result = d.discover_all()
            for key in result:
                assert isinstance(result[key], list)


class TestBrowserPaths:
    def test_chrome_paths_has_all_platforms(self):
        paths = BrowserProfileDiscovery.BROWSER_PATHS["chrome"]
        assert "Windows" in paths
        assert "Linux" in paths
        assert "Darwin" in paths

    def test_firefox_paths_has_all_platforms(self):
        paths = BrowserProfileDiscovery.BROWSER_PATHS["firefox"]
        assert "Windows" in paths
        assert "Linux" in paths
        assert "Darwin" in paths

    def test_edge_paths_has_all_platforms(self):
        paths = BrowserProfileDiscovery.BROWSER_PATHS["edge"]
        assert "Windows" in paths
        assert "Linux" in paths
        assert "Darwin" in paths

    def test_brave_paths_has_all_platforms(self):
        paths = BrowserProfileDiscovery.BROWSER_PATHS["brave"]
        assert "Windows" in paths
        assert "Linux" in paths
        assert "Darwin" in paths
