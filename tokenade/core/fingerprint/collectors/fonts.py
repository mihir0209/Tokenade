"""
Fonts Collector - Collects font measurements.
"""

from typing import Dict, Any
from .base import BaseCollector


class FontsCollector(BaseCollector):
    """Collects font measurement fingerprint data."""
    
    @property
    def api_name(self) -> str:
        return "fonts"
    
    def collect(self, browser_manager) -> Dict[str, Any]:
        """Collect font measurements."""
        script = """() => {
            const fonts = ['Arial', 'Times New Roman', 'Courier New', 'Georgia', 'Verdana', 
                          'Helvetica', 'Tahoma', 'Trebuchet MS', 'Impact', 'Comic Sans MS'];
            const measurements = {};
            
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            ctx.font = '72px monospace';
            const baseline = ctx.measureText('mmmmmmmmmm').width;
            
            fonts.forEach(font => {
                ctx.font = '72px "' + font + '"';
                measurements[font] = {
                    width: ctx.measureText('mmmmmmmmmm').width,
                    diff: ctx.measureText('mmmmmmmmmm').width - baseline
                };
            });
            
            return { fonts: fonts, measurements: measurements };
        }"""
        
        try:
            result = browser_manager.evaluate(script)
            return result if isinstance(result, dict) else {}
        except Exception as e:
            return {}
    
    def get_script_template(self) -> str:
        return """
// Fonts spoofing - minimal, just ensure consistent measurements
(function() {
    // Font spoofing is complex; we rely on canvas spoofing instead
    // This is a placeholder for future font-specific spoofing
})();
"""
