"""
Navigator Collector - Collects navigator properties.
"""

from typing import Dict, Any
from .base import BaseCollector


class NavigatorCollector(BaseCollector):
    """Collects navigator properties for fingerprint spoofing."""

    @property
    def api_name(self) -> str:
        return "navigator"

    def collect(self, browser_manager) -> Dict[str, Any]:
        """Collect navigator properties."""
        script = """() => ({
            userAgent: navigator.userAgent,
            platform: navigator.platform,
            language: navigator.language,
            languages: Array.from(navigator.languages || []),
            hardwareConcurrency: navigator.hardwareConcurrency,
            deviceMemory: navigator.deviceMemory,
            maxTouchPoints: navigator.maxTouchPoints,
            pdfViewerEnabled: navigator.pdfViewerEnabled,
            bluetooth: !!navigator.bluetooth,
            usb: !!navigator.usb,
            keyboard: !!navigator.keyboard,
            mediaCapabilities: {
                codecs: (navigator.mediaCapabilities || {}).codecs !== undefined
            },
            cookieEnabled: navigator.cookieEnabled,
            onLine: navigator.onLine,
            vendor: navigator.vendor,
            product: navigator.product,
            productSub: navigator.productSub,
            doNotTrack: navigator.doNotTrack,
            javaEnabled: navigator.javaEnabled ? navigator.javaEnabled() : false,
            webdriver: navigator.webdriver !== undefined,
            permissions: (navigator.permissions || {}).query !== undefined
        })"""

        try:
            result = browser_manager.evaluate(script)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    def get_script_template(self) -> str:
        return """
// Navigator spoofing
(function() {
    const navProps = {
        userAgent: "{{userAgent}}",
        platform: "{{platform}}",
        language: "{{language}}",
        languages: {{languages}},
        hardwareConcurrency: {{hardwareConcurrency}},
        deviceMemory: {{deviceMemory}},
        maxTouchPoints: {{maxTouchPoints}},
        pdfViewerEnabled: {{pdfViewerEnabled}},
        vendor: "{{vendor}}",
        product: "{{product}}",
        productSub: "{{productSub}}",
        doNotTrack: "{{doNotTrack}}",
        cookieEnabled: {{cookieEnabled}},
        onLine: {{onLine}}
    };

    for (const [key, value] of Object.entries(navProps)) {
        try {
            Object.defineProperty(navigator, key, {
                get: function() { return value; },
                configurable: true,
                enumerable: true
            });
        } catch(e) {}
    }

    // Remove webdriver
    delete navigator.webdriver;

    // Spoof bluetooth
    if ({{bluetooth}} === false) {
        delete navigator.bluetooth;
    }

    // Spoof usb
    if ({{usb}} === false) {
        delete navigator.usb;
    }

    // Spoof keyboard
    if ({{keyboard}} === false) {
        delete navigator.keyboard;
    }
})();
"""
