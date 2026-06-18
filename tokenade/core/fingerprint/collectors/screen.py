"""
Screen Collector - Collects screen and window properties.
"""

from typing import Dict, Any
from .base import BaseCollector


class ScreenCollector(BaseCollector):
    """Collects screen and window properties."""

    @property
    def api_name(self) -> str:
        return "screen"

    def collect(self, browser_manager) -> Dict[str, Any]:
        """Collect screen and window properties."""
        script = """() => ({
            screenWidth: screen.width,
            screenHeight: screen.height,
            screenAvailWidth: screen.availWidth,
            screenAvailHeight: screen.availHeight,
            screenAvailLeft: screen.availLeft || 0,
            screenAvailTop: screen.availTop || 0,
            screenColorDepth: screen.colorDepth,
            screenPixelDepth: screen.pixelDepth || screen.colorDepth,
            devicePixelRatio: window.devicePixelRatio,
            outerWidth: window.outerWidth,
            outerHeight: window.outerHeight,
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
            screenLeft: window.screenLeft || window.screenX || 0,
            screenTop: window.screenTop || window.screenY || 0
        })"""

        try:
            result = browser_manager.evaluate(script)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    def get_script_template(self) -> str:
        return """
// Screen spoofing
(function() {
    const screenProps = {
        width: {{screenWidth}},
        height: {{screenHeight}},
        availWidth: {{screenAvailWidth}},
        availHeight: {{screenAvailHeight}},
        availLeft: {{screenAvailLeft}},
        availTop: {{screenAvailTop}},
        colorDepth: {{screenColorDepth}},
        pixelDepth: {{screenPixelDepth}}
    };

    for (const [key, value] of Object.entries(screenProps)) {
        try {
            Object.defineProperty(screen, key, {
                get: function() { return value; },
                configurable: true,
                enumerable: true
            });
        } catch(e) {}
    }

    // Window dimensions
    Object.defineProperty(window, 'outerWidth', {
        get: function() { return {{outerWidth}}; },
        configurable: true
    });
    Object.defineProperty(window, 'outerHeight', {
        get: function() { return {{outerHeight}}; },
        configurable: true
    });
    Object.defineProperty(window, 'devicePixelRatio', {
        get: function() { return {{devicePixelRatio}}; },
        configurable: true
    });
})();
"""
