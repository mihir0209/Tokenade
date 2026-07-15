"""
Browser Profile Discovery - Auto-detect browser profiles across platforms.

Supports Chrome, Firefox, Edge, Brave, Vivaldi on Windows, Linux, and macOS.
"""

import os
import platform
import glob
import configparser
from dataclasses import dataclass
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class BrowserProfile:
    """Represents a discovered browser profile."""
    name: str
    path: str
    browser: str  # chrome, firefox, edge, safari
    last_used: Optional[str] = None
    is_default: bool = False

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "path": self.path,
            "browser": self.browser,
            "last_used": self.last_used,
            "is_default": self.is_default,
        }


class BrowserProfileDiscovery:
    """Discovers browser profiles on the current system."""

    # Cross-platform browser data paths
    BROWSER_PATHS = {
        "chrome": {
            "Windows": [
                r"%LOCALAPPDATA%\Google\Chrome\User Data",
                r"%PROGRAMFILES%\Google\Chrome\User Data",
                r"%USERPROFILE%\AppData\Local\Google\Chrome\User Data",
            ],
            "Linux": [
                "~/.config/google-chrome",
                "~/.config/chromium",
                "~/.var/app/com.google.Chrome/config/google-chrome",  # Flatpak
            ],
            "Darwin": [
                "~/Library/Application Support/Google/Chrome",
                "~/Library/Application Support/Google/Chromium",
            ],
        },
        "firefox": {
            "Windows": [
                r"%APPDATA%\Mozilla\Firefox\Profiles",
                r"%USERPROFILE%\AppData\Roaming\Mozilla\Firefox\Profiles",
            ],
            "Linux": [
                "~/.mozilla/firefox",
                "~/snap/firefox/common/.mozilla/firefox",  # Snap
                "~/.var/app/org.mozilla.firefox/.mozilla/firefox",  # Flatpak
            ],
            "Darwin": [
                "~/Library/Application Support/Firefox/Profiles",
            ],
        },
        "edge": {
            "Windows": [
                r"%LOCALAPPDATA%\Microsoft\Edge\User Data",
                r"%USERPROFILE%\AppData\Local\Microsoft\Edge\User Data",
            ],
            "Linux": [
                "~/.config/microsoft-edge",
            ],
            "Darwin": [
                "~/Library/Application Support/Microsoft Edge",
            ],
        },
        "brave": {
            "Windows": [
                r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data",
            ],
            "Linux": [
                "~/.config/BraveSoftware/Brave-Browser",
            ],
            "Darwin": [
                "~/Library/Application Support/BraveSoftware/Brave-Browser",
            ],
        },
        "vivaldi": {
            "Windows": [
                r"%LOCALAPPDATA%\Vivaldi\User Data",
            ],
            "Linux": [
                "~/.config/vivaldi",
            ],
            "Darwin": [
                "~/Library/Application Support/Vivaldi",
            ],
        },
    }

    SUPPORTED_BROWSERS = ("chrome", "firefox", "edge", "brave", "vivaldi")

    def __init__(self, cache_ttl: float = 60.0):
        self.os_type = platform.system()
        self._cache_ttl = cache_ttl
        self._browser_cache: Dict[str, List[BrowserProfile]] = {}
        self._browser_cache_time: Dict[str, float] = {}

    def _expand_path(self, path: str) -> str:
        """Expand environment variables and user home."""
        expanded = os.path.expandvars(path)
        expanded = os.path.expanduser(expanded)
        return expanded

    def _path_exists(self, path: str) -> bool:
        """Check if a path exists after expansion."""
        return os.path.exists(self._expand_path(path))

    def clear_cache(self) -> None:
        """Drop cached profile discovery results."""
        self._browser_cache.clear()
        self._browser_cache_time.clear()

    def _cache_fresh(self, browser: str) -> bool:
        import time as _time
        if browser not in self._browser_cache:
            return False
        age = _time.time() - self._browser_cache_time.get(browser, 0.0)
        return age < self._cache_ttl

    def _discover_chromium_family(self, browser: str) -> List[BrowserProfile]:
        """Discover Chromium-family profiles (chrome, edge, brave, vivaldi)."""
        profiles = []
        paths = self.BROWSER_PATHS.get(browser, {}).get(self.os_type, [])

        for base_path in paths:
            expanded = self._expand_path(base_path)
            if not os.path.exists(expanded):
                continue

            default_path = os.path.join(expanded, "Default")
            if os.path.exists(default_path):
                profiles.append(BrowserProfile(
                    name="Default",
                    path=default_path,
                    browser=browser,
                    is_default=True,
                ))

            for profile_dir in glob.glob(os.path.join(expanded, "Profile *")):
                name = os.path.basename(profile_dir)
                profiles.append(BrowserProfile(
                    name=name,
                    path=profile_dir,
                    browser=browser,
                    is_default=False,
                ))

        logger.info("Discovered %d %s profiles", len(profiles), browser)
        return profiles

    def discover_chrome_profiles(self) -> List[BrowserProfile]:
        """Discover Chrome/Chromium profiles."""
        return self.discover_browser("chrome")

    def discover_firefox_profiles(self) -> List[BrowserProfile]:
        """Discover Firefox profiles via profiles.ini."""
        return self.discover_browser("firefox")

    def discover_edge_profiles(self) -> List[BrowserProfile]:
        """Discover Edge profiles (same structure as Chrome)."""
        return self.discover_browser("edge")

    def discover_brave_profiles(self) -> List[BrowserProfile]:
        """Discover Brave profiles (same structure as Chrome)."""
        return self.discover_browser("brave")

    def discover_vivaldi_profiles(self) -> List[BrowserProfile]:
        """Discover Vivaldi profiles (same structure as Chrome)."""
        return self.discover_browser("vivaldi")

    def _scan_firefox(self) -> List[BrowserProfile]:
        profiles = []
        paths = self.BROWSER_PATHS["firefox"].get(self.os_type, [])

        for base_path in paths:
            expanded = self._expand_path(base_path)
            if not os.path.exists(expanded):
                continue

            profiles_ini = os.path.join(os.path.dirname(expanded), "profiles.ini")
            if not os.path.exists(profiles_ini):
                profiles_ini = os.path.join(expanded, "profiles.ini")

            if os.path.exists(profiles_ini):
                try:
                    config = configparser.ConfigParser()
                    config.read(profiles_ini)

                    for section in config.sections():
                        if section.startswith("Profile"):
                            name = config.get(section, "Name", fallback=section)
                            path_rel = config.get(section, "Path", fallback="")
                            is_default = config.getboolean(section, "Default", fallback=False)
                            is_relative = config.getboolean(section, "IsRelative", fallback=True)

                            if is_relative:
                                profile_path = os.path.join(os.path.dirname(profiles_ini), path_rel)
                            else:
                                profile_path = path_rel

                            if os.path.exists(profile_path):
                                profiles.append(BrowserProfile(
                                    name=name,
                                    path=profile_path,
                                    browser="firefox",
                                    is_default=is_default,
                                ))
                except Exception as e:
                    logger.warning(f"Failed to parse Firefox profiles.ini: {e}")
            else:
                for profile_dir in glob.glob(os.path.join(expanded, "*.default*")):
                    name = os.path.basename(profile_dir)
                    profiles.append(BrowserProfile(
                        name=name,
                        path=profile_dir,
                        browser="firefox",
                        is_default="default" in name.lower(),
                    ))

        logger.info("Discovered %d Firefox profiles", len(profiles))
        return profiles

    def discover_browser(self, browser: str, use_cache: bool = True) -> List[BrowserProfile]:
        """Discover profiles for a single browser (cached).

        Prefer this over discover_all() when only one browser is needed.
        """
        import time as _time

        key = (browser or "").lower()
        if key == "chromium":
            key = "chrome"
        if key not in self.SUPPORTED_BROWSERS:
            return []

        if use_cache and self._cache_fresh(key):
            return list(self._browser_cache[key])

        if key == "firefox":
            profiles = self._scan_firefox()
        else:
            profiles = self._discover_chromium_family(key)

        self._browser_cache[key] = profiles
        self._browser_cache_time[key] = _time.time()
        return list(profiles)

    def discover_all(self, use_cache: bool = True) -> Dict[str, List[BrowserProfile]]:
        """Discover all browser profiles (per-browser cache)."""
        return {
            name: self.discover_browser(name, use_cache=use_cache)
            for name in self.SUPPORTED_BROWSERS
        }

    def get_profile(self, browser: str, name: str) -> Optional[BrowserProfile]:
        """Get a specific profile by browser and name."""
        for profile in self.discover_browser(browser):
            if profile.name == name:
                return profile
        return None

    def get_default_profile(self, browser: str) -> Optional[BrowserProfile]:
        """Get the default profile for a browser (single-browser scan only)."""
        profiles = self.discover_browser(browser)
        for profile in profiles:
            if profile.is_default:
                return profile
        return profiles[0] if profiles else None

    def list_profiles_text(self) -> str:
        """Generate a text listing of all profiles."""
        lines = []
        lines.append("=" * 60)
        lines.append("BROWSER PROFILES")
        lines.append("=" * 60)

        all_profiles = self.discover_all()
        total = 0

        for browser, profiles in all_profiles.items():
            if not profiles:
                continue
            lines.append(f"\n{browser.upper()}:")
            for p in profiles:
                default_mark = " (default)" if p.is_default else ""
                lines.append(f"  • {p.name}{default_mark}")
                lines.append(f"    Path: {p.path}")
                total += 1

        if total == 0:
            lines.append("\nNo browser profiles found.")

        lines.append(f"\nTotal profiles: {total}")
        return "\n".join(lines)
