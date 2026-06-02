"""
Browser Profile Discovery - Auto-detect browser profiles across platforms.

Supports Chrome, Firefox, Edge on Windows, Linux, and macOS.
"""

import os
import platform
import glob
import configparser
from dataclasses import dataclass
from pathlib import Path
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
    }

    def __init__(self):
        self.os_type = platform.system()

    def _expand_path(self, path: str) -> str:
        """Expand environment variables and user home."""
        expanded = os.path.expandvars(path)
        expanded = os.path.expanduser(expanded)
        return expanded

    def _path_exists(self, path: str) -> bool:
        """Check if a path exists after expansion."""
        return os.path.exists(self._expand_path(path))

    def discover_chrome_profiles(self) -> List[BrowserProfile]:
        """Discover Chrome/Chromium profiles."""
        profiles = []
        paths = self.BROWSER_PATHS["chrome"].get(self.os_type, [])

        for base_path in paths:
            expanded = self._expand_path(base_path)
            if not os.path.exists(expanded):
                continue

            # Chrome stores profiles as subdirectories
            # "Default" is the default profile
            # "Profile 1", "Profile 2", etc. are additional profiles
            default_path = os.path.join(expanded, "Default")
            if os.path.exists(default_path):
                profiles.append(BrowserProfile(
                    name="Default",
                    path=default_path,
                    browser="chrome",
                    is_default=True,
                ))

            # Find other profiles
            for profile_dir in glob.glob(os.path.join(expanded, "Profile *")):
                name = os.path.basename(profile_dir)
                profiles.append(BrowserProfile(
                    name=name,
                    path=profile_dir,
                    browser="chrome",
                    is_default=False,
                ))

        logger.info(f"Discovered {len(profiles)} Chrome profiles")
        return profiles

    def discover_firefox_profiles(self) -> List[BrowserProfile]:
        """Discover Firefox profiles via profiles.ini."""
        profiles = []
        paths = self.BROWSER_PATHS["firefox"].get(self.os_type, [])

        for base_path in paths:
            expanded = self._expand_path(base_path)
            if not os.path.exists(expanded):
                continue

            # Firefox uses profiles.ini to track profiles
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
                # Fallback: scan directories directly
                for profile_dir in glob.glob(os.path.join(expanded, "*.default*")):
                    name = os.path.basename(profile_dir)
                    profiles.append(BrowserProfile(
                        name=name,
                        path=profile_dir,
                        browser="firefox",
                        is_default="default" in name.lower(),
                    ))

        logger.info(f"Discovered {len(profiles)} Firefox profiles")
        return profiles

    def discover_edge_profiles(self) -> List[BrowserProfile]:
        """Discover Edge profiles (same structure as Chrome)."""
        profiles = []
        paths = self.BROWSER_PATHS["edge"].get(self.os_type, [])

        for base_path in paths:
            expanded = self._expand_path(base_path)
            if not os.path.exists(expanded):
                continue

            default_path = os.path.join(expanded, "Default")
            if os.path.exists(default_path):
                profiles.append(BrowserProfile(
                    name="Default",
                    path=default_path,
                    browser="edge",
                    is_default=True,
                ))

            for profile_dir in glob.glob(os.path.join(expanded, "Profile *")):
                name = os.path.basename(profile_dir)
                profiles.append(BrowserProfile(
                    name=name,
                    path=profile_dir,
                    browser="edge",
                    is_default=False,
                ))

        logger.info(f"Discovered {len(profiles)} Edge profiles")
        return profiles

    def discover_all(self) -> Dict[str, List[BrowserProfile]]:
        """Discover all browser profiles."""
        return {
            "chrome": self.discover_chrome_profiles(),
            "firefox": self.discover_firefox_profiles(),
            "edge": self.discover_edge_profiles(),
        }

    def get_profile(self, browser: str, name: str) -> Optional[BrowserProfile]:
        """Get a specific profile by browser and name."""
        all_profiles = self.discover_all()
        for profile in all_profiles.get(browser, []):
            if profile.name == name:
                return profile
        return None

    def get_default_profile(self, browser: str) -> Optional[BrowserProfile]:
        """Get the default profile for a browser."""
        all_profiles = self.discover_all()
        for profile in all_profiles.get(browser, []):
            if profile.is_default:
                return profile
        # Fallback to first profile
        profiles = all_profiles.get(browser, [])
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
