"""
Plugins Collector - Collects plugin and MIME type data.
"""

from typing import Dict, Any
from .base import BaseCollector


class PluginsCollector(BaseCollector):
    """Collects plugin and MIME type data."""

    @property
    def api_name(self) -> str:
        return "plugins"

    def collect(self, browser_manager) -> Dict[str, Any]:
        """Collect plugin data."""
        script = """() => ({
            plugins: Array.from(navigator.plugins).map(p => ({
                name: p.name,
                description: p.description,
                filename: p.filename,
                version: p.version || '',
                length: p.length
            })),
            mimeTypes: Array.from(navigator.mimeTypes).map(m => ({
                type: m.type,
                description: m.description,
                suffixes: m.suffixes,
                enabledPlugin: m.enabledPlugin ? m.enabledPlugin.name : null
            })),
            pluginsLength: navigator.plugins.length,
            mimeTypesLength: navigator.mimeTypes.length
        })"""

        try:
            result = browser_manager.evaluate(script)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    def get_script_template(self) -> str:
        return """
// Plugins spoofing
(function() {
    const pluginsData = {{plugins}};
    const mimeTypesData = {{mimeTypes}};

    // Create fake PluginArray
    const fakePlugins = pluginsData.map(p => ({
        name: p.name,
        description: p.description,
        filename: p.filename,
        version: p.version || '',
        length: p.length,
        item: function(index) { return this[index]; },
        namedItem: function(name) { return this.find(pl => pl.name === name); }
    }));

    // Create fake MimeTypeArray
    const fakeMimeTypes = mimeTypesData.map(m => ({
        type: m.type,
        description: m.description,
        suffixes: m.suffixes,
        enabledPlugin: m.enabledPlugin,
        item: function(index) { return this[index]; },
        namedItem: function(name) { return this.find(mt => mt.type === name); }
    }));

    Object.defineProperty(navigator, 'plugins', {
        get: function() {
            const arr = fakePlugins;
            arr.length = fakePlugins.length;
            arr.item = function(index) { return this[index]; };
            arr.namedItem = function(name) { return this.find(p => p.name === name); };
            return arr;
        },
        configurable: true
    });

    Object.defineProperty(navigator, 'mimeTypes', {
        get: function() {
            const arr = fakeMimeTypes;
            arr.length = fakeMimeTypes.length;
            arr.item = function(index) { return this[index]; };
            arr.namedItem = function(name) { return this.find(m => m.type === name); };
            return arr;
        },
        configurable: true
    });
})();
"""
