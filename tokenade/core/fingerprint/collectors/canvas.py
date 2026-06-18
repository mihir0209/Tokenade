"""
Canvas Collector - Collects Canvas 2D fingerprint.
"""

from typing import Dict, Any
from .base import BaseCollector


class CanvasCollector(BaseCollector):
    """Collects Canvas 2D fingerprint data."""

    @property
    def api_name(self) -> str:
        return "canvas"

    def collect(self, browser_manager) -> Dict[str, Any]:
        """Collect canvas fingerprint."""
        script = """() => {
            const canvas = document.createElement('canvas');
            canvas.width = 280;
            canvas.height = 60;
            const ctx = canvas.getContext('2d');

            // Draw fingerprinting pattern
            ctx.textBaseline = 'top';
            ctx.font = '14px Arial';
            ctx.textBaseline = 'alphabetic';
            ctx.fillStyle = '#f60';
            ctx.fillRect(0, 0, 280, 60);
            ctx.fillStyle = '#069';
            ctx.fillText('Tokenade Canvas FP', 2, 15);
            ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
            ctx.fillText('Tokenade Canvas FP', 4, 17);

            return {
                dataUrl: canvas.toDataURL(),
                width: canvas.width,
                height: canvas.height
            };
        }"""

        try:
            result = browser_manager.evaluate(script)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    def get_script_template(self) -> str:
        return """
// Canvas spoofing - return pre-computed data URL
(function() {
    const canvasDataUrl = "{{dataUrl}}";

    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type, quality) {
        // Only spoof fingerprinting canvases (small ones with text)
        if (this.width <= 300 && this.height <= 100) {
            return canvasDataUrl;
        }
        return origToDataURL.call(this, type, quality);
    };

    // Also spoof getImageData for fingerprinting detection
    const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
    CanvasRenderingContext2D.prototype.getImageData = function(x, y, w, h) {
        // For small canvases, return data from pre-computed image
        if (this.canvas.width <= 300 && this.canvas.height <= 100) {
            // Create a temporary canvas to decode the data URL
            const tempCanvas = document.createElement('canvas');
            tempCanvas.width = this.canvas.width;
            tempCanvas.height = this.canvas.height;
            const tempCtx = tempCanvas.getContext('2d');
            const img = new Image();
            img.src = canvasDataUrl;
            tempCtx.drawImage(img, 0, 0);
            return tempCtx.getImageData(x, y, w, h);
        }
        return origGetImageData.call(this, x, y, w, h);
    };
})();
"""
