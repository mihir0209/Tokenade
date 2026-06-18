"""
Stealth Script Builder - Generates fingerprint spoofing scripts.
"""

import json
import logging
from typing import List

from .manager import BrowserFingerprint

logger = logging.getLogger(__name__)


class StealthScriptBuilder:
    """Builds stealth injection scripts from fingerprint data."""

    def __init__(self, fingerprint: BrowserFingerprint):
        self.fingerprint = fingerprint
        self.script_parts: List[str] = []

    def build(self, level: str = "maximum") -> str:
        """
        Build complete stealth injection script.

        Args:
            level: Stealth level - "basic", "advanced", or "maximum"

        Returns:
            Complete JavaScript injection script
        """
        self.script_parts = []

        # Add base framework
        self._add_base_framework()

        # Add automation cleanup
        self._add_automation_cleanup()

        # Add navigator spoofing
        self._add_navigator_spoofs()

        # Add screen spoofing
        self._add_screen_spoofs()

        # Add WebGL spoofing
        self._add_webgl_spoofs()

        # Add canvas spoofing
        self._add_canvas_spoofs()

        # Add audio spoofing (advanced/maximum only)
        if level in ("advanced", "maximum"):
            self._add_audio_spoofs()

        # Add plugin spoofing
        self._add_plugin_spoofs()

        # Add WebRTC spoofing (maximum only)
        if level == "maximum":
            self._add_webrtc_spoofs()
            self._add_battery_spoofs()

        return "\n\n".join(self.script_parts)

    def _add_base_framework(self):
        """Add stealth framework that prevents detection."""
        script = """
// Stealth framework - prevents detection of overrides
(function() {
    // Store original methods
    const origDefineProperty = Object.defineProperty;
    const origGetOwnPropertyDescriptor = Object.getOwnPropertyDescriptor;

    // Helper to make overrides undetectable
    window._stealthUtils = {
        defineProperty: function(obj, prop, descriptor) {
            try {
                origDefineProperty(obj, prop, descriptor);
            } catch(e) {}
        },
        patchToString: function(fn, nativeCode) {
            fn.toString = function() {
                return nativeCode || 'function ' + fn.name + '() { [native code] }';
            };
        }
    };
})();
"""
        self.script_parts.append(script)

    def _add_automation_cleanup(self):
        """Remove automation flags."""
        script = """
// Remove automation flags
(function() {
    // Remove navigator.webdriver
    delete navigator.webdriver;

    // Remove chrome.runtime if it exposes automation
    if (window.chrome && window.chrome.runtime) {
        const origRuntime = window.chrome.runtime;
        Object.defineProperty(window.chrome, 'runtime', {
            get: function() {
                return origRuntime;
            },
            configurable: true
        });
    }

    // Remove CDC props (Chrome DevTools Protocol)
    const props = Object.getOwnPropertyNames(window);
    props.forEach(prop => {
        if (prop.startsWith('cdc_')) {
            delete window[prop];
        }
    });

    // Override permissions.query to deny notifications
    if (navigator.permissions) {
        const origQuery = navigator.permissions.query;
        navigator.permissions.query = function(parameters) {
            if (parameters.name === 'notifications') {
                return Promise.resolve({ state: Notification.permission });
            }
            return origQuery.call(navigator.permissions, parameters);
        };
    }
})();
"""
        self.script_parts.append(script)

    def _add_navigator_spoofs(self):
        """Add navigator property overrides."""
        fp = self.fingerprint

        script = f"""
// Navigator spoofing
(function() {{
    const navProps = {{
        userAgent: {json.dumps(fp.user_agent)},
        platform: {json.dumps(fp.platform)},
        language: {json.dumps(fp.language)},
        languages: {json.dumps(fp.languages)},
        hardwareConcurrency: {fp.hardware_concurrency},
        deviceMemory: {fp.device_memory},
        maxTouchPoints: {fp.max_touch_points}
    }};

    for (const [key, value] of Object.entries(navProps)) {{
        try {{
            Object.defineProperty(navigator, key, {{
                get: function() {{ return value; }},
                configurable: true,
                enumerable: true
            }});
        }} catch(e) {{}}
    }}
}})();
"""
        self.script_parts.append(script)

    def _add_screen_spoofs(self):
        """Add screen/window overrides."""
        fp = self.fingerprint

        script = f"""
// Screen spoofing
(function() {{
    const screenProps = {{
        width: {fp.screen_width},
        height: {fp.screen_height},
        colorDepth: {fp.color_depth}
    }};

    for (const [key, value] of Object.entries(screenProps)) {{
        try {{
            Object.defineProperty(screen, key, {{
                get: function() {{ return value; }},
                configurable: true,
                enumerable: true
            }});
        }} catch(e) {{}}
    }}

    Object.defineProperty(window, 'devicePixelRatio', {{
        get: function() {{ return {fp.device_pixel_ratio}; }},
        configurable: true
    }});
}})();
"""
        self.script_parts.append(script)

    def _add_webgl_spoofs(self):
        """Add WebGL parameter overrides."""
        fp = self.fingerprint

        script = f"""
// WebGL spoofing
(function() {{
    const vendor = {json.dumps(fp.webgl_vendor)};
    const renderer = {json.dumps(fp.webgl_renderer)};

    const origGetExtension = WebGLRenderingContext.prototype.getExtension;
    WebGLRenderingContext.prototype.getExtension = function(name) {{
        if (name === 'WEBGL_debug_renderer_info') {{
            return {{
                UNMASKED_VENDOR_WEBGL: 0x9245,
                UNMASKED_RENDERER_WEBGL: 0x9246
            }};
        }}
        return origGetExtension.call(this, name);
    }};

    const origGetParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {{
        if (parameter === 0x9245) return vendor;
        if (parameter === 0x9246) return renderer;
        return origGetParameter.call(this, parameter);
    }};
}})();
"""
        self.script_parts.append(script)

    def _add_canvas_spoofs(self):
        """Add Canvas 2D pixel data overrides."""
        fp = self.fingerprint

        if not fp.canvas_fingerprint:
            return

        script = f"""
// Canvas spoofing
(function() {{
    const canvasDataUrl = {json.dumps(fp.canvas_fingerprint)};

    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type, quality) {{
        if (this.width <= 300 && this.height <= 100) {{
            return canvasDataUrl;
        }}
        return origToDataURL.call(this, type, quality);
    }};
}})();
"""
        self.script_parts.append(script)

    def _add_audio_spoofs(self):
        """Add AudioContext overrides."""
        script = """
// Audio spoofing
(function() {
    const origAudioContext = window.AudioContext || window.webkitAudioContext;
    if (!origAudioContext) return;

    window.AudioContext = function() {
        const ctx = new origAudioContext();

        // Override analyser
        const origCreateAnalyser = ctx.createAnalyser;
        ctx.createAnalyser = function() {
            const analyser = origCreateAnalyser.call(ctx);

            const origGetByteFrequencyData = analyser.getByteFrequencyData;
            analyser.getByteFrequencyData = function(array) {
                // Return consistent data
                for (let i = 0; i < array.length; i++) {
                    array[i] = i % 256;
                }
                return array;
            };

            return analyser;
        };

        return ctx;
    };
})();
"""
        self.script_parts.append(script)

    def _add_plugin_spoofs(self):
        """Add plugin/MIME type overrides."""
        fp = self.fingerprint

        if not fp.plugins:
            return

        plugins_json = json.dumps(fp.plugins)

        script = f"""
// Plugins spoofing
(function() {{
    const pluginsData = {plugins_json};

    const fakePlugins = pluginsData.map(p => ({{
        name: p.name,
        description: p.description,
        filename: p.filename,
        length: p.length || 0
    }}));

    Object.defineProperty(navigator, 'plugins', {{
        get: function() {{
            const arr = fakePlugins;
            arr.length = fakePlugins.length;
            arr.item = function(index) {{ return this[index]; }};
            arr.namedItem = function(name) {{ return this.find(p => p.name === name); }};
            return arr;
        }},
        configurable: true
    }});
}})();
"""
        self.script_parts.append(script)

    def _add_webrtc_spoofs(self):
        """Add WebRTC IP hiding."""
        script = """
// WebRTC spoofing
(function() {
    const RTCPeerConnection = window.RTCPeerConnection ||
        window.mozRTCPeerConnection || window.webkitRTCPeerConnection;

    if (!RTCPeerConnection) return;

    const origCreateOffer = RTCPeerConnection.prototype.createOffer;
    RTCPeerConnection.prototype.createOffer = function() {
        return origCreateOffer.apply(this, arguments).then(offer => {
            if (offer.sdp) {
                offer.sdp = offer.sdp.replace(/([0-9]{1,3}\\.){3}[0-9]{1,3}/g, '0.0.0.0');
            }
            return offer;
        });
    };
})();
"""
        self.script_parts.append(script)

    def _add_battery_spoofs(self):
        """Add battery API overrides."""
        script = """
// Battery spoofing
(function() {
    if (navigator.getBattery) {
        navigator.getBattery = function() {
            return Promise.resolve({
                charging: true,
                level: 1.0,
                chargingTime: 0,
                dischargingTime: Infinity,
                addEventListener: function() {}
            });
        };
    }
})();
"""
        self.script_parts.append(script)
