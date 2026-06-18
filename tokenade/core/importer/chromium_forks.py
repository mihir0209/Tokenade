"""
Chromium fork browser support.

Auto-detects and extracts cookies from Chromium-based browsers:
- Arc Browser
- Opera / Opera GX
- Vivaldi
- Brave (with Tor profiles)
- Edge (already supported via Chrome, but explicit support)
"""
import os
import sys
from pathlib import Path
from typing import List
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ChromiumForkInfo:
    """Information about a detected Chromium fork."""
    name: str
    browser_type: str  # 'chrome', 'edge', 'brave', 'opera', 'vivaldi', 'arc'
    profile_dirs: List[Path]
    is_default: bool = False
    notes: str = ""


class ChromiumForkDetector:
    """Detect installed Chromium-based browsers."""

    # Browser-specific profile locations by platform
    BROWSER_PATHS = {
        "arc": {
            "linux": [
                Path.home() / ".config" / "Arc" / "User Data",
            ],
            "darwin": [
                Path.home() / "Library" / "Application Support" / "Arc" / "User Data",
            ],
            "windows": [
                Path(os.environ.get("LOCALAPPDATA", "")) / "Arc" / "User Data" if os.environ.get("LOCALAPPDATA") else None,
            ],
        },
        "opera": {
            "linux": [
                Path.home() / ".config" / "opera" / "Default",
                Path.home() / ".config" / "opera-stable" / "Default",
            ],
            "darwin": [
                Path.home() / "Library" / "Application Support" / "com.operasoftware.Opera" / "Default",
            ],
            "windows": [
                Path(os.environ.get("APPDATA", "")) / "Opera Software" / "Opera Stable" / "Default" if os.environ.get("APPDATA") else None,
            ],
        },
        "vivaldi": {
            "linux": [
                Path.home() / ".config" / "vivaldi" / "Default",
                Path.home() / ".config" / "Vivaldi" / "Default",
            ],
            "darwin": [
                Path.home() / "Library" / "Application Support" / "Vivaldi" / "Default",
            ],
            "windows": [
                Path(os.environ.get("LOCALAPPDATA", "")) / "Vivaldi" / "User Data" / "Default" if os.environ.get("LOCALAPPDATA") else None,
            ],
        },
        "brave": {
            "linux": [
                Path.home() / ".config" / "BraveSoftware" / "Brave-Browser" / "Default",
                Path.home() / ".config" / "BraveSoftware" / "Brave-Browser-Tor" / "Default",
            ],
            "darwin": [
                Path.home() / "Library" / "Application Support" / "BraveSoftware" / "Brave-Browser" / "Default",
            ],
            "windows": [
                Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware" / "Brave-Browser" / "Default" if os.environ.get("LOCALAPPDATA") else None,
            ],
        },
        "edge": {
            "linux": [
                Path.home() / ".config" / "microsoft-edge" / "Default",
                Path.home() / ".config" / "microsoft-edge-dev" / "Default",
            ],
            "darwin": [
                Path.home() / "Library" / "Application Support" / "Microsoft Edge" / "Default",
            ],
            "windows": [
                Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data" / "Default" if os.environ.get("LOCALAPPDATA") else None,
            ],
        },
    }

    def detect_all(self) -> List[ChromiumForkInfo]:
        """Detect all installed Chromium forks."""
        platform = sys.platform
        if platform == "linux":
            plat_key = "linux"
        elif platform == "darwin":
            plat_key = "darwin"
        else:
            plat_key = "windows"

        detected = []

        for browser_name, paths in self.BROWSER_PATHS.items():
            plat_paths = paths.get(plat_key, [])
            found_paths = []

            for p in plat_paths:
                if p is None:
                    continue
                if p.exists():
                    found_paths.append(p)
                    # Check for multiple profiles
                    profile_dirs = self._find_profiles(p)
                    if profile_dirs:
                        found_paths.extend(profile_dirs)

            if found_paths:
                detected.append(ChromiumForkInfo(
                    name=browser_name.title(),
                    browser_type=browser_name,
                    profile_dirs=found_paths,
                    is_default=browser_name in ("chrome", "edge"),
                    notes=self._get_notes(browser_name),
                ))

        return detected

    def _find_profiles(self, base_path: Path) -> List[Path]:
        """Find profile directories within a browser's User Data."""
        profiles = []

        # Check for Profiles directory (multi-profile browsers)
        profiles_dir = base_path / "Profiles"
        if profiles_dir.exists():
            for item in profiles_dir.iterdir():
                if item.is_dir() and (item / "Cookies").exists():
                    profiles.append(item)

        # Check for numbered profiles (Profile 1, Profile 2, etc.)
        for i in range(1, 10):
            profile = base_path.parent / f"Profile {i}"
            if profile.exists() and (profile / "Cookies").exists():
                profiles.append(profile)

        return profiles

    def _get_notes(self, browser_name: str) -> str:
        """Get notes about a browser."""
        notes = {
            "arc": "Arc uses Chromium with custom UI. Cookie extraction works like Chrome.",
            "opera": "Opera uses Chromium with built-in VPN and ad blocker.",
            "vivaldi": "Vivaldi uses Chromium with extensive customization.",
            "brave": "Brave has built-in ad blocker and Tor mode. Tor profiles use separate storage.",
            "edge": "Microsoft Edge is Chromium-based with Microsoft account integration.",
        }
        return notes.get(browser_name, "")

    def get_browser_type_for_extractor(self, fork: ChromiumForkInfo) -> str:
        """Map fork type to CookieExtractor browser parameter."""
        mapping = {
            "chrome": "chrome",
            "edge": "chrome",  # Edge is Chromium-based
            "brave": "chrome",  # Brave is Chromium-based
            "opera": "chrome",  # Opera is Chromium-based
            "vivaldi": "chrome",  # Vivaldi is Chromium-based
            "arc": "chrome",  # Arc is Chromium-based
        }
        return mapping.get(fork.browser_type, "chrome")
