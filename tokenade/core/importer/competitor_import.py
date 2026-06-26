"""
Competitor Import — import sessions/profiles from AdsPower, Multilogin, GoLogin.

Each competitor has a different export format. This module normalizes them
into Tokenade's BrowserProfile format.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class CompetitorImporter:
    """Import sessions/profiles from competitor tools."""

    SUPPORTED_FORMATS = ["adspower", "multilogin", "gologin"]

    def import_file(self, file_path: str, source: Optional[str] = None) -> List[Dict]:
        """Import profiles from a file. Auto-detects source if not specified."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(path) as f:
            data = json.load(f)

        if source is None:
            source = self._detect_source(data, path.name)

        if source not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported source: {source}. "
                f"Supported: {', '.join(self.SUPPORTED_FORMATS)}"
            )

        if source == "adspower":
            return self._import_adspower(data)
        elif source == "multilogin":
            return self._import_multilogin(data)
        elif source == "gologin":
            return self._import_gologin(data)
        return []

    def _detect_source(self, data: Any, filename: str) -> str:
        """Auto-detect the source format."""
        filename_lower = filename.lower()

        # Check filename hints
        if "adspower" in filename_lower or "ads_power" in filename_lower:
            return "adspower"
        if "multilogin" in filename_lower or "mixin" in filename_lower:
            return "multilogin"
        if "gologin" in filename_lower:
            return "gologin"

        # Check data structure
        if isinstance(data, dict):
            if "user" in data or "profile_id" in data:
                return "adspower"
            if "profiles" in data and isinstance(data["profiles"], list):
                if data["profiles"] and "name" in data["profiles"][0]:
                    return "multilogin"
            if "profiles" in data and "cookies" in str(data):
                return "gologin"

        if isinstance(data, list) and data:
            item = data[0]
            if "profile_id" in item or "user_id" in item:
                return "adspower"
            if "name" in item and "browser_type" in item:
                return "multilogin"

        # Default to adspower (most common)
        return "adspower"

    def _import_adspower(self, data: Any) -> List[Dict]:
        """Import from AdsPower JSON export."""
        profiles = []

        # Handle both single profile and list
        items = data if isinstance(data, list) else [data]

        for item in items:
            profile = {
                "name": item.get("name", item.get("profile_name", "unnamed")),
                "source": "adspower",
                "browser": self._map_adspower_browser(item.get("browser_type", "")),
                "os": self._map_adspower_os(item.get("system", "")),
                "fingerprint": self._extract_adspower_fingerprint(item),
                "proxy": self._extract_adspower_proxy(item),
                "cookies": item.get("cookies", []),
                "notes": item.get("remark", ""),
                "tags": [item.get("group_name", "")] if item.get("group_name") else [],
            }
            profiles.append(profile)

        logger.info(f"Imported {len(profiles)} profiles from AdsPower")
        return profiles

    def _extract_adspower_fingerprint(self, item: Dict) -> Dict:
        """Extract fingerprint from AdsPower profile."""
        fp = {}

        # Navigator
        fp["navigator"] = {
            "platform": item.get("platform", "Win32"),
            "vendor": "Google Inc.",
            "language": item.get("language", "en-US"),
            "languages": [item.get("language", "en-US")],
            "hardwareConcurrency": item.get("cpu", 4),
            "deviceMemory": item.get("memory", 8),
        }

        # Screen
        resolution = item.get("resolution", "1920x1080").split("x")
        fp["screen"] = {
            "width": int(resolution[0]) if len(resolution) > 0 else 1920,
            "height": int(resolution[1]) if len(resolution) > 1 else 1080,
            "colorDepth": 24,
        }

        # WebGL
        fp["webgl"] = {
            "vendor": item.get("webgl_vendor", "Google Inc."),
            "renderer": item.get("webgl_renderer", ""),
        }

        return fp

    def _extract_adspower_proxy(self, item: Dict) -> Optional[Dict]:
        """Extract proxy from AdsPower profile."""
        proxy_config = item.get("proxy_config", item.get("proxy", {}))
        if not proxy_config:
            return None

        proxy_type = proxy_config.get("proxy_type", "")
        if not proxy_type or proxy_type == "no_proxy":
            return None

        return {
            "type": proxy_type,
            "host": proxy_config.get("proxy_host", ""),
            "port": proxy_config.get("proxy_port", 0),
            "username": proxy_config.get("proxy_user", ""),
            "password": proxy_config.get("proxy_password", ""),
        }

    def _map_adspower_browser(self, browser_type: str) -> str:
        """Map AdsPower browser type to Tokenade browser."""
        mapping = {
            "chrome": "chromium",
            "chromium": "chromium",
            "firefox": "firefox",
        }
        return mapping.get(browser_type.lower(), "chromium")

    def _map_adspower_os(self, system: str) -> str:
        """Map AdsPower OS to Tokenade OS."""
        system_lower = system.lower()
        if "windows" in system_lower or "win" in system_lower:
            return "windows"
        if "mac" in system_lower or "darwin" in system_lower:
            return "macos"
        if "linux" in system_lower:
            return "linux"
        return "windows"

    def _import_multilogin(self, data: Any) -> List[Dict]:
        """Import from Multilogin JSON export."""
        profiles = []

        items = data if isinstance(data, list) else data.get("profiles", [])

        for item in items:
            profile = {
                "name": item.get("name", "unnamed"),
                "source": "multilogin",
                "browser": self._map_multilogin_browser(item.get("browser_type", "")),
                "os": self._map_multilogin_os(item.get("os", "")),
                "fingerprint": self._extract_multilogin_fingerprint(item),
                "proxy": self._extract_multilogin_proxy(item),
                "cookies": item.get("cookies", []),
                "notes": item.get("notes", ""),
                "tags": item.get("tags", []),
            }
            profiles.append(profile)

        logger.info(f"Imported {len(profiles)} profiles from Multilogin")
        return profiles

    def _extract_multilogin_fingerprint(self, item: Dict) -> Dict:
        """Extract fingerprint from Multilogin profile."""
        fp = {}

        fp["navigator"] = {
            "platform": item.get("platform", "Win32"),
            "vendor": "Google Inc.",
            "language": item.get("language", "en-US"),
            "languages": [item.get("language", "en-US")],
            "hardwareConcurrency": item.get("navigator", {}).get("hardwareConcurrency", 4),
            "deviceMemory": item.get("navigator", {}).get("deviceMemory", 8),
        }

        fp["screen"] = {
            "width": item.get("screen", {}).get("width", 1920),
            "height": item.get("screen", {}).get("height", 1080),
            "colorDepth": 24,
        }

        fp["webgl"] = {
            "vendor": item.get("webgl", {}).get("vendor", ""),
            "renderer": item.get("webgl", {}).get("renderer", ""),
        }

        return fp

    def _extract_multilogin_proxy(self, item: Dict) -> Optional[Dict]:
        """Extract proxy from Multilogin profile."""
        proxy = item.get("proxy", {})
        if not proxy or not proxy.get("host"):
            return None
        return {
            "type": proxy.get("type", "http"),
            "host": proxy.get("host", ""),
            "port": proxy.get("port", 0),
            "username": proxy.get("username", ""),
            "password": proxy.get("password", ""),
        }

    def _map_multilogin_browser(self, browser_type: str) -> str:
        """Map Multilogin browser type to Tokenade browser."""
        mapping = {
            "chrome": "chromium",
            "mixin": "chromium",
            "fox": "firefox",
        }
        return mapping.get(browser_type.lower(), "chromium")

    def _map_multilogin_os(self, os_str: str) -> str:
        """Map Multilogin OS to Tokenade OS."""
        os_lower = os_str.lower()
        if "windows" in os_lower:
            return "windows"
        if "mac" in os_lower:
            return "macos"
        if "linux" in os_lower:
            return "linux"
        return "windows"

    def _import_gologin(self, data: Any) -> List[Dict]:
        """Import from GoLogin JSON export."""
        profiles = []

        items = data if isinstance(data, list) else data.get("profiles", [])

        for item in items:
            profile = {
                "name": item.get("name", "unnamed"),
                "source": "gologin",
                "browser": "chromium",  # GoLogin uses Chromium
                "os": self._map_gologin_os(item.get("os", "")),
                "fingerprint": self._extract_gologin_fingerprint(item),
                "proxy": self._extract_gologin_proxy(item),
                "cookies": item.get("cookies", []),
                "notes": item.get("notes", ""),
                "tags": item.get("tags", []),
            }
            profiles.append(profile)

        logger.info(f"Imported {len(profiles)} profiles from GoLogin")
        return profiles

    def _extract_gologin_fingerprint(self, item: Dict) -> Dict:
        """Extract fingerprint from GoLogin profile."""
        fp = {}

        fp["navigator"] = {
            "platform": item.get("navigator", {}).get("platform", "Win32"),
            "vendor": "Google Inc.",
            "language": item.get("navigator", {}).get("language", "en-US"),
            "languages": item.get("navigator", {}).get("languages", ["en-US"]),
            "hardwareConcurrency": item.get("navigator", {}).get("hardwareConcurrency", 4),
            "deviceMemory": item.get("navigator", {}).get("deviceMemory", 8),
        }

        fp["screen"] = {
            "width": item.get("screen", {}).get("width", 1920),
            "height": item.get("screen", {}).get("height", 1080),
            "colorDepth": 24,
        }

        fp["webgl"] = {
            "vendor": item.get("webgl", {}).get("vendor", ""),
            "renderer": item.get("webgl", {}).get("renderer", ""),
        }

        return fp

    def _extract_gologin_proxy(self, item: Dict) -> Optional[Dict]:
        """Extract proxy from GoLogin profile."""
        proxy = item.get("proxy", {})
        if not proxy or not proxy.get("host"):
            return None
        return {
            "type": proxy.get("type", "http"),
            "host": proxy.get("host", ""),
            "port": proxy.get("port", 0),
            "username": proxy.get("username", ""),
            "password": proxy.get("password", ""),
        }

    def _map_gologin_os(self, os_str: str) -> str:
        """Map GoLogin OS to Tokenade OS."""
        os_lower = os_str.lower()
        if "windows" in os_lower:
            return "windows"
        if "mac" in os_lower:
            return "macos"
        if "linux" in os_lower:
            return "linux"
        return "windows"
