"""
Fingerprint Generation — generate random but consistent browser fingerprints.

Creates realistic browser fingerprints based on OS, browser, and hardware profiles.
Fingerprints are consistent per session (same seed = same fingerprint).
"""

import hashlib

import logging

import random
import time
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Realistic OS/browser/screen profiles
OS_PROFILES = {
    "windows": {
        "platform": "Win32",
        "vendor": "Google Inc.",
        "user_agent_os": "Windows NT 10.0; Win64; x64",
        "languages": ["en-US", "en"],
        "timezone": "America/New_York",
    },
    "macos": {
        "platform": "MacIntel",
        "vendor": "Google Inc.",
        "user_agent_os": "Macintosh; Intel Mac OS X 10_15_7",
        "languages": ["en-US", "en"],
        "timezone": "America/Los_Angeles",
    },
    "linux": {
        "platform": "Linux x86_64",
        "vendor": "Google Inc.",
        "user_agent_os": "X11; Linux x86_64",
        "languages": ["en-US", "en"],
        "timezone": "America/Chicago",
    },
}

BROWSER_VERSIONS = {
    "chromium": ["131.0.6778.85", "130.0.6723.91", "129.0.6668.100"],
    "chrome": ["131.0.6778.85", "130.0.6723.91", "129.0.6668.100"],
    "firefox": ["133.0", "132.0.2", "131.0.3"],
    "brave": ["1.73.91", "1.72.101", "1.71.100"],
    "safari": ["18.1", "18.0", "17.6"],
}

HARDWARE_PROFILES = [
    {"hardwareConcurrency": 4, "deviceMemory": 4, "gpu": "Intel Iris Plus Graphics"},
    {"hardwareConcurrency": 8, "deviceMemory": 8, "gpu": "NVIDIA GeForce RTX 3060"},
    {"hardwareConcurrency": 16, "deviceMemory": 16, "gpu": "NVIDIA GeForce RTX 4070"},
    {"hardwareConcurrency": 8, "deviceMemory": 16, "gpu": "AMD Radeon RX 6700 XT"},
    {"hardwareConcurrency": 6, "deviceMemory": 8, "gpu": "Intel UHD Graphics 630"},
    {"hardwareConcurrency": 12, "deviceMemory": 32, "gpu": "NVIDIA GeForce RTX 4090"},
    {"hardwareConcurrency": 4, "deviceMemory": 4, "gpu": "Intel HD Graphics 620"},
    {"hardwareConcurrency": 8, "deviceMemory": 8, "gpu": "AMD Radeon RX 580"},
]

SCREEN_RESOLUTIONS = [
    {"width": 1920, "height": 1080},
    {"width": 2560, "height": 1440},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
    {"width": 3840, "height": 2160},
]

WEBGL_VENDORS = [
    "Google Inc. (NVIDIA)",
    "Google Inc. (AMD)",
    "Google Inc. (Intel)",
    "Google Inc. (Apple)",
]

WEBGL_RENDERERS = [
    "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "ANGLE (AMD, AMD Radeon RX 6700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "ANGLE (Intel, Intel(R) Iris(R) Plus Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "Apple GPU",
    "Mozilla",
]

# Fonts per OS
FONTS = {
    "windows": [
        "Arial", "Arial Black", "Calibri", "Cambria", "Candara",
        "Comic Sans MS", "Consolas", "Constantia", "Corbel",
        "Courier New", "Georgia", "Impact", "Lucida Console",
        "Microsoft Sans Serif", "Palatino Linotype", "Segoe UI",
        "Tahoma", "Times New Roman", "Trebuchet MS", "Verdana",
    ],
    "macos": [
        "Arial", "American Typewriter", "Apple Chancery", "Arial Black",
        "Avenir", "Avenir Next", "Baskerville", "Big Caslon",
        "Brush Script MT", "Chalkboard", "Cochin", "Comic Sans MS",
        "Copperplate", "Courier New", "Didot", "Futura",
        "Geneva", "Gill Sans", "Helvetica", "Hoefler Text",
        "Impact", "Lucida Grande", "Marker Felt", "Optima",
        "Palatino", "Papyrus", "Phosphate", "Rockwell",
        "Skia", "Times New Roman", "Trebuchet MS", "Zapfino",
    ],
    "linux": [
        "Arial", "Bitstream Charter", "Cantarell", "DejaVu Sans",
        "DejaVu Serif", "Droid Sans", "Droid Serif", "Fira Mono",
        "Fira Sans", "FreeMono", "FreeSans", "FreeSerif",
        "Garuda", "Geneva", "Gentium Plus", "Gill Sans",
        "Hack", "Helvetica", "Inconsolata", "Liberation Mono",
        "Liberation Sans", "Liberation Serif", "Nimbus Mono PS",
        "Nimbus Sans L", "Noto Sans", "Noto Serif", "Open Sans",
        "Purisa", "Quattrocento", "Roboto", "Roboto Mono",
        "Source Code Pro", "Source Sans Pro", "TakaoPGothic",
        "TeX Gyre Cursor", "TeX Gyre Heros", "Times New Roman",
        "Trebuchet MS", "Ubuntu", "URW Gothic L", "URW Palladio L",
        "Verdana", "WenQuanYi Micro Hei", "WenQuanYi Zen Hei",
    ],
}


class FingerprintGenerator:
    """Generate random but consistent browser fingerprints."""

    def __init__(self, seed: Optional[int] = None):
        self.seed = seed or int(time.time() * 1000) % (2**31)
        self._rng = random.Random(self.seed)

    def generate(
        self,
        os_name: str = "windows",
        browser: str = "chromium",
        hardware: Optional[Dict] = None,
        screen: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Generate a complete browser fingerprint."""
        os_profile = OS_PROFILES.get(os_name, OS_PROFILES["windows"])
        browser_versions = BROWSER_VERSIONS.get(browser, BROWSER_VERSIONS["chromium"])
        version = self._rng.choice(browser_versions)

        hw = hardware or self._rng.choice(HARDWARE_PROFILES)
        scr = screen or self._rng.choice(SCREEN_RESOLUTIONS)

        # Generate deterministic but random-looking values
        webgl_vendor = self._rng.choice(WEBGL_VENDORS)
        webgl_renderer = self._rng.choice(WEBGL_RENDERERS)
        fonts = self._get_random_fonts(os_name)

        user_agent = self._build_user_agent(os_profile, browser, version)

        fingerprint = {
            "navigator": {
                "platform": os_profile["platform"],
                "vendor": os_profile["vendor"],
                "language": os_profile["languages"][0],
                "languages": os_profile["languages"],
                "hardwareConcurrency": hw["hardwareConcurrency"],
                "deviceMemory": hw["deviceMemory"],
                "maxTouchPoints": 0,
                "doNotTrack": None,
                "pdfViewerEnabled": True,
            },
            "screen": {
                "width": scr["width"],
                "height": scr["height"],
                "availWidth": scr["width"],
                "availHeight": scr["height"] - 40,
                "colorDepth": 24,
                "pixelDepth": 24,
                "orientation": "landscape-primary",
            },
            "webgl": {
                "vendor": webgl_vendor,
                "renderer": webgl_renderer,
                "extensions": [
                    "WEBGL_debug_renderer_info",
                    "OES_texture_float",
                    "OES_texture_half_float",
                    "WEBGL_compressed_texture_s3tc",
                    "EXT_texture_filter_anisotropic",
                ],
            },
            "canvas": {
                "noise": self._rng.random() * 0.001,
                "winding": True,
                "rgb": True,
            },
            "audio": {
                "sampleRate": 44100,
                "channelCount": 2,
                "noise": self._rng.random() * 0.0001,
            },
            "fonts": fonts,
            "timezone": os_profile["timezone"],
            "userAgent": user_agent,
            "browser": browser,
            "browserVersion": version,
            "os": os_name,
            "hardware": hw,
            "plugins": self._get_plugins(browser),
            "mimeTypes": self._get_mime_types(browser),
        }

        return fingerprint

    def _build_user_agent(self, os_profile: Dict, browser: str, version: str) -> str:
        """Build a realistic user agent string."""
        ua_os = os_profile["user_agent_os"]

        if browser in ("chromium", "chrome"):
            return f"Mozilla/5.0 ({ua_os}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Safari/537.36"
        elif browser == "firefox":
            return f"Mozilla/5.0 ({ua_os}; rv:{version.split('.')[0]}.0) Gecko/20100101 Firefox/{version}"
        elif browser == "brave":
            return f"Mozilla/5.0 ({ua_os}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Safari/537.36"
        elif browser == "safari":
            safari_ver = f"{int(version.split('.')[0]) + 3}.{version.split('.')[1]}"
            webkit_ver = "605.1.15"
            return f"Mozilla/5.0 ({ua_os}) AppleWebKit/{webkit_ver} (KHTML, like Gecko) Version/{safari_ver} Safari/605.1.15"
        return f"Mozilla/5.0 ({ua_os}) AppleWebKit/537.36 Chrome/{version} Safari/537.36"

    def _get_random_fonts(self, os_name: str) -> List[str]:
        """Get a random subset of fonts for the OS."""
        all_fonts = FONTS.get(os_name, FONTS["windows"])
        count = self._rng.randint(15, min(25, len(all_fonts)))
        return sorted(self._rng.sample(all_fonts, count))

    def _get_plugins(self, browser: str) -> List[Dict]:
        """Get browser plugins."""
        if browser in ("firefox", "safari"):
            return []
        return [
            {"name": "PDF Viewer", "filename": "internal-pdf-viewer", "description": "Portable Document Format"},
            {"name": "Chrome PDF Viewer", "filename": "internal-pdf-viewer", "description": ""},
            {"name": "Chromium PDF Viewer", "filename": "internal-pdf-viewer", "description": ""},
            {"name": "Microsoft Edge PDF Viewer", "filename": "internal-pdf-viewer", "description": ""},
            {"name": "WebKit built-in PDF", "filename": "internal-pdf-viewer", "description": ""},
        ]

    def _get_mime_types(self, browser: str) -> List[Dict]:
        """Get browser MIME types."""
        if browser in ("firefox", "safari"):
            return []
        return [
            {"type": "application/pdf", "suffixes": "pdf", "description": "Portable Document Format"},
            {"type": "application/x-google-chrome-pdf", "suffixes": "pdf", "description": "Portable Document Format"},
            {"type": "application/x-nacl", "suffixes": "", "description": "Native Client Executable"},
            {"type": "application/x-pnacl", "suffixes": "", "description": "Portable Native Client Executable"},
        ]

    def generate_seed(self, identifier: str) -> int:
        """Generate a deterministic seed from an identifier."""
        return int(hashlib.md5(identifier.encode()).hexdigest()[:8], 16)

    def generate_for_session(self, session_id: str) -> Dict[str, Any]:
        """Generate a fingerprint that's consistent for a given session ID."""
        self.seed = self.generate_seed(session_id)
        self._rng = random.Random(self.seed)
        return self.generate()
