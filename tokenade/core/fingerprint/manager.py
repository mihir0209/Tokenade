"""
Fingerprint Manager - Browser fingerprint collection and matching.

Collects browser fingerprints from source devices and applies them
to target devices to maintain session continuity.
"""

import json
import os
import platform
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class BrowserFingerprint:
    """Complete browser fingerprint for session continuity."""

    # User Agent
    user_agent: str = ""

    # Screen/Viewport
    screen_width: int = 1920
    screen_height: int = 1080
    viewport_width: int = 1920
    viewport_height: int = 1080
    device_pixel_ratio: float = 1.0
    color_depth: int = 24

    # Platform
    platform: str = ""
    os_type: str = ""
    language: str = "en-US"
    languages: List[str] = field(default_factory=lambda: ["en-US"])
    timezone: str = "UTC"
    timezone_offset: int = 0

    # Hardware
    hardware_concurrency: int = 4
    device_memory: float = 8.0
    max_touch_points: int = 0

    # WebGL
    webgl_vendor: str = ""
    webgl_renderer: str = ""

    # Canvas/Fonts
    canvas_fingerprint: str = ""
    fonts: List[str] = field(default_factory=list)

    # Plugins
    plugins: List[Dict] = field(default_factory=list)

    # Chrome-specific
    chrome_version: str = ""

    # Network
    accept_language: str = "en-US,en;q=0.9"

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)

    def to_playwright_context(self) -> Dict:
        """Convert to Playwright context options."""
        return {
            "viewport": {
                "width": self.viewport_width,
                "height": self.viewport_height,
            },
            "screen": {
                "width": self.screen_width,
                "height": self.screen_height,
            },
            "user_agent": self.user_agent,
            "locale": self.language,
            "timezone_id": self.timezone,
            "device_scale_factor": self.device_pixel_ratio,
            "is_mobile": False,
            "has_touch": self.max_touch_points > 0,
            "color_scheme": "light",
            "reduced_motion": "no-preference",
        }

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, data: str) -> "BrowserFingerprint":
        """Deserialize from JSON."""
        return cls(**json.loads(data))

    @classmethod
    def from_dict(cls, data: Dict) -> "BrowserFingerprint":
        """Create from dictionary."""
        return cls(**data)


class FingerprintCollector:
    """Collects fingerprints from a running browser instance."""

    @staticmethod
    def collect_from_browser(browser_manager) -> BrowserFingerprint:
        """Collect fingerprint from active browser."""
        fp = BrowserFingerprint()

        try:
            # User agent
            fp.user_agent = browser_manager.evaluate(
                "() => navigator.userAgent"
            )

            # Screen info
            screen_info = browser_manager.evaluate("""() => ({
                width: screen.width,
                height: screen.height,
                availWidth: screen.availWidth,
                availHeight: screen.availHeight,
                colorDepth: screen.colorDepth,
                pixelRatio: window.devicePixelRatio
            })""")
            fp.screen_width = screen_info.get("width", 1920)
            fp.screen_height = screen_info.get("height", 1080)
            fp.color_depth = screen_info.get("colorDepth", 24)
            fp.device_pixel_ratio = screen_info.get("pixelRatio", 1.0)

            # Viewport
            viewport = browser_manager.evaluate("""() => ({
                width: window.innerWidth,
                height: window.innerHeight
            })""")
            fp.viewport_width = viewport.get("width", 1920)
            fp.viewport_height = viewport.get("height", 1080)

            # Platform
            fp.platform = browser_manager.evaluate("() => navigator.platform")
            fp.os_type = platform.system()

            # Language
            fp.language = browser_manager.evaluate("() => navigator.language")
            fp.languages = browser_manager.evaluate("() => navigator.languages")

            # Timezone
            fp.timezone = browser_manager.evaluate(
                "() => Intl.DateTimeFormat().resolvedOptions().timeZone"
            )
            fp.timezone_offset = browser_manager.evaluate(
                "() => new Date().getTimezoneOffset()"
            )

            # Hardware
            fp.hardware_concurrency = browser_manager.evaluate(
                "() => navigator.hardwareConcurrency"
            ) or 4
            fp.device_memory = browser_manager.evaluate(
                "() => navigator.deviceMemory"
            ) or 8.0
            fp.max_touch_points = browser_manager.evaluate(
                "() => navigator.maxTouchPoints"
            ) or 0

            # WebGL
            try:
                webgl = browser_manager.evaluate("""() => {
                    const canvas = document.createElement('canvas');
                    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                    if (!gl) return {};
                    const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
                    return {
                        vendor: debugInfo ? gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) : '',
                        renderer: debugInfo ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) : ''
                    };
                }""")
                fp.webgl_vendor = webgl.get("vendor", "")
                fp.webgl_renderer = webgl.get("renderer", "")
            except Exception:
                pass

            # Plugins
            try:
                plugins = browser_manager.evaluate("""() => {
                    return Array.from(navigator.plugins).map(p => ({
                        name: p.name,
                        description: p.description,
                        filename: p.filename
                    }));
                }""")
                fp.plugins = plugins or []
            except Exception:
                pass

            logger.info("Fingerprint collected successfully")

        except Exception as e:
            logger.warning(f"Some fingerprint fields could not be collected: {e}")

        return fp

    @staticmethod
    def collect_from_system() -> BrowserFingerprint:
        """Collect fingerprint from current system (fallback)."""
        fp = BrowserFingerprint()
        fp.os_type = platform.system()
        fp.platform = platform.platform()
        fp.language = os.environ.get("LANG", "en-US").split(".")[0]
        fp.languages = [fp.language]

        # Try to get timezone
        try:
            import tzlocal
            fp.timezone = str(tzlocal.get_localzone())
        except Exception:
            pass

        return fp


class FingerprintManager:
    """Manages fingerprint storage, retrieval, and application."""

    def __init__(self, storage_dir: str = ".fingerprints"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)

    def save(self, name: str, fingerprint: BrowserFingerprint) -> str:
        """Save fingerprint to storage."""
        path = self.storage_dir / f"{name}.json"
        path.write_text(fingerprint.to_json())
        logger.info(f"Fingerprint saved: {path}")
        return str(path)

    def load(self, name: str) -> Optional[BrowserFingerprint]:
        """Load fingerprint from storage."""
        path = self.storage_dir / f"{name}.json"
        if not path.exists():
            logger.warning(f"Fingerprint not found: {name}")
            return None

        return BrowserFingerprint.from_json(path.read_text())

    def list(self) -> List[str]:
        """List all stored fingerprints."""
        return [f.stem for f in self.storage_dir.glob("*.json")]

    def delete(self, name: str) -> bool:
        """Delete a fingerprint."""
        path = self.storage_dir / f"{name}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def apply_to_config(self, name: str, config: Dict) -> Dict:
        """Apply fingerprint to browser config dict."""
        fp = self.load(name)
        if not fp:
            return config

        config.update(fp.to_playwright_context())
        return config

    def compare(self, fp1: BrowserFingerprint, fp2: BrowserFingerprint) -> Dict[str, Any]:
        """Compare two fingerprints and return differences."""
        differences = {}

        for fld in BrowserFingerprint.__dataclass_fields__:
            val1 = getattr(fp1, fld)
            val2 = getattr(fp2, fld)

            if val1 != val2:
                differences[fld] = {"source": val1, "target": val2}

        return differences
