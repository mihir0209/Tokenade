"""
Tor Browser Cookie Extractor - Extract cookies from Tor Browser.

Tor Browser is Firefox-based, so it uses the same cookies.sqlite format.
This module handles profile discovery and delegates extraction to CookieExtractor.
"""

import os
import glob
import logging
import platform
from typing import Dict, List, Optional

from tokenade.core.importer.cookie_extractor import CookieExtractor, SiteFilter

logger = logging.getLogger(__name__)

# Tor Browser profile paths by platform
TOR_PROFILE_PATHS = {
    "Linux": [
        "~/.torbrowser/tor-browser/Browser/TorBrowser/Data/Browser/profile.default",
        "~/.local/share/torbrowser/tor-browser/Browser/TorBrowser/Data/Browser/profile.default",
        # torbrowser-launcher paths
        "~/.local/share/torbrowser-launcher/tor-browser/Browser/TorBrowser/Data/Browser/profile.default",
        "~/.local/share/torbrowser-launcher/tor/Browser/TorBrowser/Data/Browser/profile.default",
    ],
    "Darwin": [
        "~/Library/Application Support/TorBrowser-Data/Browser/profile.default",
    ],
    "Windows": [
        "%LOCALAPPDATA%/Tor Browser/Browser/TorBrowser/Data/Browser/profile.default",
        "%APPDATA%/Tor Browser/Browser/TorBrowser/Data/Browser/profile.default",
    ],
}


class TorExtractor:
    """Extract cookies from Tor Browser (Firefox-based)."""

    def __init__(self, profile_path: Optional[str] = None):
        """
        Initialize Tor Browser cookie extractor.

        Args:
            profile_path: Path to Tor Browser profile directory.
                         If None, auto-detects the default Tor Browser profile.
        """
        if profile_path is None:
            profile_path = self._find_tor_profile()
        self.profile_path = profile_path
        self._extractor = None

    def _find_tor_profile(self) -> Optional[str]:
        """
        Find Tor Browser profile directory on the current platform.

        Checks platform-specific paths and looks for cookies.sqlite
        to confirm it's a valid Firefox-based profile.

        Returns:
            Path to profile directory, or None if not found.
        """
        os_type = platform.system()

        paths = TOR_PROFILE_PATHS.get(os_type, [])

        for path_template in paths:
            expanded = os.path.expandvars(os.path.expanduser(path_template))
            if os.path.exists(expanded):
                cookies_db = os.path.join(expanded, "cookies.sqlite")
                if os.path.exists(cookies_db):
                    logger.info(f"Found Tor Browser profile at: {expanded}")
                    return expanded
                logger.debug(
                    f"Tor Browser profile dir exists but no cookies.sqlite: {expanded}"
                )

        # Fallback: glob for any profile.default* directories in known parent dirs
        glob_parents = []
        if os_type == "Linux":
            glob_parents = [
                os.path.expanduser("~/.torbrowser"),
                os.path.expanduser("~/.local/share/torbrowser"),
                os.path.expanduser("~/.local/share/torbrowser-launcher"),
            ]
        elif os_type == "Darwin":
            glob_parents = [
                os.path.expanduser("~/Library/Application Support/TorBrowser-Data"),
            ]
        elif os_type == "Windows":
            local_app = os.environ.get("LOCALAPPDATA", "")
            app_data = os.environ.get("APPDATA", "")
            glob_parents = [
                os.path.join(local_app, "Tor Browser"),
                os.path.join(app_data, "Tor Browser"),
            ]

        for parent in glob_parents:
            if not os.path.exists(parent):
                continue
            for profile_dir in glob.glob(os.path.join(parent, "**", "profile.default*"), recursive=True):
                cookies_db = os.path.join(profile_dir, "cookies.sqlite")
                if os.path.exists(cookies_db):
                    logger.info(f"Found Tor Browser profile at: {profile_dir}")
                    return profile_dir

        logger.warning("Tor Browser profile not found")
        return None

    def extract(self, site_filter: Optional[SiteFilter] = None) -> List[Dict]:
        """
        Extract cookies from Tor Browser.

        Since Tor Browser is Firefox-based, this delegates to CookieExtractor
        with browser="firefox".

        Args:
            site_filter: Optional SiteFilter to filter cookies by domain/site.

        Returns:
            List of cookie dictionaries.

        Raises:
            FileNotFoundError: If no profile was found.
        """
        if self.profile_path is None:
            logger.warning("No Tor Browser profile found")
            return []

        if not os.path.exists(self.profile_path):
            logger.warning(f"Tor Browser profile path does not exist: {self.profile_path}")
            return []

        self._extractor = CookieExtractor(self.profile_path, browser="firefox")
        cookies = self._extractor.extract_firefox(site_filter)

        logger.info(f"Extracted {len(cookies)} cookies from Tor Browser")
        return cookies
