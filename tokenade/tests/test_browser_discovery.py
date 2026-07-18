"""Tests for browser discovery."""

from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery, BrowserProfile


class TestBrowserDiscovery:
    def test_discover_all_returns_dict(self, tmp_path):
        discovery = BrowserProfileDiscovery(scan_roots=[tmp_path])
        profiles = discovery.discover_all()
        assert isinstance(profiles, dict)

    def test_profile_dataclass(self):
        profile = BrowserProfile(
            name="default",
            path="/home/user/.mozilla/firefox/xxx.default",
            browser="firefox",
        )
        assert profile.name == "default"
        assert profile.browser == "firefox"

    def test_discover_firefox_profiles(self, tmp_path):
        discovery = BrowserProfileDiscovery(scan_roots=[tmp_path])
        profiles = discovery.discover_firefox_profiles()
        assert isinstance(profiles, list)
        for p in profiles:
            assert p.browser == "firefox"

    def test_discover_chrome_profiles(self, tmp_path):
        discovery = BrowserProfileDiscovery(scan_roots=[tmp_path])
        profiles = discovery.discover_chrome_profiles()
        assert isinstance(profiles, list)
        for p in profiles:
            assert p.browser in ("chrome", "chromium")

    def test_discover_all_keys(self, tmp_path):
        discovery = BrowserProfileDiscovery(scan_roots=[tmp_path])
        profiles = discovery.discover_all()
        assert isinstance(profiles, dict)
        for key in profiles:
            assert isinstance(profiles[key], list)

    def test_profile_has_path(self, tmp_path):
        discovery = BrowserProfileDiscovery(scan_roots=[tmp_path])
        profiles = discovery.discover_firefox_profiles()
        for p in profiles:
            assert p.path is not None
            assert len(p.path) > 0

    def test_get_default_profile(self, tmp_path):
        discovery = BrowserProfileDiscovery(scan_roots=[tmp_path])
        profile = discovery.get_default_profile("firefox")
        if profile:
            assert profile.browser == "firefox"

    def test_list_profiles_text(self, tmp_path):
        discovery = BrowserProfileDiscovery(scan_roots=[tmp_path])
        text = discovery.list_profiles_text()
        assert isinstance(text, str)
