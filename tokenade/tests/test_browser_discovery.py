"""
Tests for Browser Profile Discovery

Phase 1 tests - must pass before proceeding to Phase 2.
"""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery, BrowserProfile


class TestBrowserProfileDiscovery:
    """Test browser profile discovery across platforms."""

    def test_expand_path_with_tilde(self):
        """Test expanding user home directory."""
        discovery = BrowserProfileDiscovery()
        result = discovery._expand_path("~/test")
        assert result.startswith("/")
        assert result.endswith("/test")

    def test_expand_path_with_env(self):
        """Test expanding environment variables."""
        discovery = BrowserProfileDiscovery()
        with patch.dict(os.environ, {"TEST_VAR": "/test/path"}):
            result = discovery._expand_path("$TEST_VAR/sub")
            assert "/test/path/sub" in result

    def test_path_exists_true(self):
        """Test path existence check."""
        discovery = BrowserProfileDiscovery()
        with tempfile.TemporaryDirectory() as tmpdir:
            assert discovery._path_exists(tmpdir) is True

    def test_path_exists_false(self):
        """Test path existence check for non-existent path."""
        discovery = BrowserProfileDiscovery()
        assert discovery._path_exists("/nonexistent/path/12345") is False

    def test_discover_chrome_profiles_linux(self):
        """Test Chrome profile discovery on Linux."""
        discovery = BrowserProfileDiscovery()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create mock Chrome profile structure
            chrome_dir = os.path.join(tmpdir, ".config", "google-chrome")
            default_profile = os.path.join(chrome_dir, "Default")
            profile1 = os.path.join(chrome_dir, "Profile 1")
            os.makedirs(default_profile)
            os.makedirs(profile1)
            
            with patch.object(discovery, "BROWSER_PATHS", {
                "chrome": {"Linux": [chrome_dir]},
                "firefox": {"Linux": []},
                "edge": {"Linux": []},
            }):
                profiles = discovery.discover_chrome_profiles()
                
                assert len(profiles) == 2
                assert profiles[0].name == "Default"
                assert profiles[0].is_default is True
                assert profiles[1].name == "Profile 1"
                assert profiles[1].is_default is False

    def test_discover_chrome_profiles_empty(self):
        """Test Chrome profile discovery when no profiles exist."""
        discovery = BrowserProfileDiscovery()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(discovery, "BROWSER_PATHS", {
                "chrome": {"Linux": [tmpdir]},
                "firefox": {"Linux": []},
                "edge": {"Linux": []},
            }):
                profiles = discovery.discover_chrome_profiles()
                assert len(profiles) == 0

    def test_discover_firefox_profiles_ini(self):
        """Test Firefox profile discovery via profiles.ini."""
        discovery = BrowserProfileDiscovery()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            firefox_dir = os.path.join(tmpdir, ".mozilla", "firefox")
            os.makedirs(firefox_dir)
            
            # Create profiles.ini
            profiles_ini = os.path.join(firefox_dir, "profiles.ini")
            with open(profiles_ini, "w") as f:
                f.write("""[Profile0]
Name=default
IsRelative=1
Path=abc123.default
Default=1

[Profile1]
Name=work
IsRelative=1
Path=def456.work
Default=0
""")
            
            # Create profile directories
            os.makedirs(os.path.join(firefox_dir, "abc123.default"))
            os.makedirs(os.path.join(firefox_dir, "def456.work"))
            
            with patch.object(discovery, "BROWSER_PATHS", {
                "chrome": {"Linux": []},
                "firefox": {"Linux": [firefox_dir]},
                "edge": {"Linux": []},
            }):
                profiles = discovery.discover_firefox_profiles()
                
                assert len(profiles) == 2
                assert profiles[0].name == "default"
                assert profiles[0].is_default is True
                assert profiles[1].name == "work"
                assert profiles[1].is_default is False

    def test_discover_firefox_profiles_fallback(self):
        """Test Firefox profile discovery fallback when profiles.ini missing."""
        discovery = BrowserProfileDiscovery()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            firefox_dir = os.path.join(tmpdir, ".mozilla", "firefox")
            os.makedirs(firefox_dir)
            
            # Create profile directories without profiles.ini
            os.makedirs(os.path.join(firefox_dir, "abc123.default"))
            os.makedirs(os.path.join(firefox_dir, "def456.default-release"))
            
            with patch.object(discovery, "BROWSER_PATHS", {
                "chrome": {"Linux": []},
                "firefox": {"Linux": [firefox_dir]},
                "edge": {"Linux": []},
            }):
                profiles = discovery.discover_firefox_profiles()
                
                assert len(profiles) == 2
                assert "default" in profiles[0].name

    def test_discover_edge_profiles(self):
        """Test Edge profile discovery."""
        discovery = BrowserProfileDiscovery()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            edge_dir = os.path.join(tmpdir, ".config", "microsoft-edge")
            default_profile = os.path.join(edge_dir, "Default")
            os.makedirs(default_profile)
            
            with patch.object(discovery, "BROWSER_PATHS", {
                "chrome": {"Linux": []},
                "firefox": {"Linux": []},
                "edge": {"Linux": [edge_dir]},
            }):
                profiles = discovery.discover_edge_profiles()
                
                assert len(profiles) == 1
                assert profiles[0].name == "Default"
                assert profiles[0].browser == "edge"

    def test_discover_all(self):
        """Test discovering all browser profiles."""
        discovery = BrowserProfileDiscovery()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create Chrome
            chrome_dir = os.path.join(tmpdir, "chrome")
            os.makedirs(os.path.join(chrome_dir, "Default"))
            
            # Create Firefox
            firefox_dir = os.path.join(tmpdir, "firefox")
            os.makedirs(os.path.join(firefox_dir, "abc.default"))
            
            with patch.object(discovery, "BROWSER_PATHS", {
                "chrome": {"Linux": [chrome_dir]},
                "firefox": {"Linux": [firefox_dir]},
                "edge": {"Linux": []},
            }):
                all_profiles = discovery.discover_all()
                
                assert len(all_profiles["chrome"]) == 1
                assert len(all_profiles["firefox"]) == 1
                assert len(all_profiles["edge"]) == 0

    def test_get_profile_found(self):
        """Test getting a specific profile."""
        discovery = BrowserProfileDiscovery()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            chrome_dir = os.path.join(tmpdir, "chrome")
            os.makedirs(os.path.join(chrome_dir, "Default"))
            os.makedirs(os.path.join(chrome_dir, "Profile 1"))
            
            with patch.object(discovery, "BROWSER_PATHS", {
                "chrome": {"Linux": [chrome_dir]},
                "firefox": {"Linux": []},
                "edge": {"Linux": []},
            }):
                profile = discovery.get_profile("chrome", "Default")
                assert profile is not None
                assert profile.name == "Default"

    def test_get_profile_not_found(self):
        """Test getting a non-existent profile."""
        discovery = BrowserProfileDiscovery()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(discovery, "BROWSER_PATHS", {
                "chrome": {"Linux": [tmpdir]},
                "firefox": {"Linux": []},
                "edge": {"Linux": []},
            }):
                profile = discovery.get_profile("chrome", "NonExistent")
                assert profile is None

    def test_get_default_profile(self):
        """Test getting default profile."""
        discovery = BrowserProfileDiscovery()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            chrome_dir = os.path.join(tmpdir, "chrome")
            os.makedirs(os.path.join(chrome_dir, "Default"))
            os.makedirs(os.path.join(chrome_dir, "Profile 1"))
            
            with patch.object(discovery, "BROWSER_PATHS", {
                "chrome": {"Linux": [chrome_dir]},
                "firefox": {"Linux": []},
                "edge": {"Linux": []},
            }):
                profile = discovery.get_default_profile("chrome")
                assert profile is not None
                assert profile.is_default is True

    def test_get_default_profile_fallback(self):
        """Test fallback to first profile when no default."""
        discovery = BrowserProfileDiscovery()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            chrome_dir = os.path.join(tmpdir, "chrome")
            os.makedirs(os.path.join(chrome_dir, "Profile 1"))
            
            with patch.object(discovery, "BROWSER_PATHS", {
                "chrome": {"Linux": [chrome_dir]},
                "firefox": {"Linux": []},
                "edge": {"Linux": []},
            }):
                profile = discovery.get_default_profile("chrome")
                assert profile is not None
                assert profile.name == "Profile 1"

    def test_list_profiles_text(self):
        """Test text listing of profiles."""
        discovery = BrowserProfileDiscovery()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            chrome_dir = os.path.join(tmpdir, "chrome")
            os.makedirs(os.path.join(chrome_dir, "Default"))
            
            with patch.object(discovery, "BROWSER_PATHS", {
                "chrome": {"Linux": [chrome_dir]},
                "firefox": {"Linux": []},
                "edge": {"Linux": []},
            }):
                text = discovery.list_profiles_text()
                assert "CHROME" in text
                assert "Default" in text
                assert "Total profiles: 1" in text

    def test_list_profiles_text_empty(self):
        """Test text listing when no profiles found."""
        discovery = BrowserProfileDiscovery()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(discovery, "BROWSER_PATHS", {
                "chrome": {"Linux": [tmpdir]},
                "firefox": {"Linux": []},
                "edge": {"Linux": []},
            }):
                text = discovery.list_profiles_text()
                assert "No browser profiles found" in text

    def test_browser_profile_to_dict(self):
        """Test BrowserProfile serialization."""
        profile = BrowserProfile(
            name="Default",
            path="/home/user/.config/chrome/Default",
            browser="chrome",
            is_default=True,
        )
        d = profile.to_dict()
        assert d["name"] == "Default"
        assert d["browser"] == "chrome"
        assert d["is_default"] is True

    def test_discover_no_browsers_found(self):
        """Test graceful handling when no browsers installed."""
        discovery = BrowserProfileDiscovery()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(discovery, "BROWSER_PATHS", {
                "chrome": {"Linux": [os.path.join(tmpdir, "nonexistent")]},
                "firefox": {"Linux": [os.path.join(tmpdir, "nonexistent2")]},
                "edge": {"Linux": [os.path.join(tmpdir, "nonexistent3")]},
            }):
                all_profiles = discovery.discover_all()
                assert all(len(p) == 0 for p in all_profiles.values())


class TestBrowserProfileDiscoveryWindows:
    """Windows-specific tests."""

    @patch("platform.system", return_value="Windows")
    def test_windows_paths(self, mock_platform):
        """Test Windows path expansion."""
        discovery = BrowserProfileDiscovery()
        assert discovery.os_type == "Windows"
        
        # Check that Windows paths are defined
        assert "Windows" in discovery.BROWSER_PATHS["chrome"]
        assert len(discovery.BROWSER_PATHS["chrome"]["Windows"]) > 0


class TestBrowserProfileDiscoveryMacOS:
    """macOS-specific tests."""

    @patch("platform.system", return_value="Darwin")
    def test_macos_paths(self, mock_platform):
        """Test macOS path expansion."""
        discovery = BrowserProfileDiscovery()
        assert discovery.os_type == "Darwin"
        
        # Check that macOS paths are defined
        assert "Darwin" in discovery.BROWSER_PATHS["chrome"]
        assert len(discovery.BROWSER_PATHS["chrome"]["Darwin"]) > 0
