"""
WebGL Collector - Collects WebGL parameters and extensions.
"""

from typing import Dict, Any
from .base import BaseCollector


class WebGLCollector(BaseCollector):
    """Collects WebGL fingerprint data."""
    
    @property
    def api_name(self) -> str:
        return "webgl"
    
    def collect(self, browser_manager) -> Dict[str, Any]:
        """Collect WebGL parameters."""
        script = """() => {
            const canvas = document.createElement('canvas');
            const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
            if (!gl) return {};
            
            const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
            const params = {};
            const paramNames = [
                'ALIASED_LINE_WIDTH_RANGE',
                'ALIASED_POINT_SIZE_RANGE',
                'ALPHA_BITS',
                'BLUE_BITS',
                'DEPTH_BITS',
                'GREEN_BITS',
                'RED_BITS',
                'MAX_COMBINED_TEXTURE_IMAGE_UNITS',
                'MAX_CUBE_MAP_TEXTURE_SIZE',
                'MAX_FRAGMENT_UNIFORM_VECTORS',
                'MAX_RENDERBUFFER_SIZE',
                'MAX_TEXTURE_IMAGE_UNITS',
                'MAX_TEXTURE_SIZE',
                'MAX_VARYING_VECTORS',
                'MAX_VERTEX_ATTRIBS',
                'MAX_VERTEX_TEXTURE_IMAGE_UNITS',
                'MAX_VERTEX_UNIFORM_VECTORS',
                'PRECISION_FORMATS',
                'RENDERER',
                'SHADING_LANGUAGE_VERSION',
                'VENDOR',
                'VERSION'
            ];
            
            paramNames.forEach(name => {
                try {
                    const param = gl.getParameter(gl[name]);
                    params[name] = param;
                } catch(e) {}
            });
            
            const extensions = gl.getSupportedExtensions() || [];
            
            return {
                vendor: debugInfo ? gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) : '',
                renderer: debugInfo ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) : '',
                params: params,
                extensions: extensions
            };
        }"""
        
        try:
            result = browser_manager.evaluate(script)
            return result if isinstance(result, dict) else {}
        except Exception as e:
            return {}
    
    def get_script_template(self) -> str:
        return """
// WebGL spoofing
(function() {
    const vendor = "{{vendor}}";
    const renderer = "{{renderer}}";
    const extensions = {{extensions}};
    
    const origGetExtension = WebGLRenderingContext.prototype.getExtension;
    WebGLRenderingContext.prototype.getExtension = function(name) {
        if (name === 'WEBGL_debug_renderer_info') {
            return {
                UNMASKED_VENDOR_WEBGL: 0x9245,
                UNMASKED_RENDERER_WEBGL: 0x9246
            };
        }
        return origGetExtension.call(this, name);
    };
    
    const origGetParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 0x9245) return vendor;
        if (parameter === 0x9246) return renderer;
        return origGetParameter.call(this, parameter);
    };
    
    const origGetSupportedExtensions = WebGLRenderingContext.prototype.getSupportedExtensions;
    WebGLRenderingContext.prototype.getSupportedExtensions = function() {
        return extensions;
    };
})();
"""
