"""
Fingerprint Collectors - Modular collectors for each API category.

Each collector gathers fingerprint data from a specific browser API
and provides a script template for spoofing that API.
"""

from .base import BaseCollector
from .navigator import NavigatorCollector
from .screen import ScreenCollector
from .webgl import WebGLCollector
from .canvas import CanvasCollector
from .audio import AudioCollector
from .fonts import FontsCollector
from .plugins import PluginsCollector
from .webrtc import WebRTCCollector
from .battery import BatteryCollector

__all__ = [
    "BaseCollector",
    "NavigatorCollector",
    "ScreenCollector",
    "WebGLCollector",
    "CanvasCollector",
    "AudioCollector",
    "FontsCollector",
    "PluginsCollector",
    "WebRTCCollector",
    "BatteryCollector",
]
