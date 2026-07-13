"""Integration tests for the plugin ecosystem.

Tests end-to-end workflows across plugin discovery, loading, lifecycle, and execution.
"""
import json
import tempfile
from pathlib import Path

import pytest

from tokenade.core.integration.plugin_loader import PluginLoader
from tokenade.core.integration.plugin_sandbox import PluginSandbox


class TestPluginEcosystemIntegration:
    """End-to-end integration tests for plugin ecosystem."""

    @pytest.fixture
    def temp_plugin_dir(self, tmp_path):
        """Create a temporary plugin directory."""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        return plugin_dir

    @pytest.fixture
    def simple_plugin(self, temp_plugin_dir):
        """Create a simple working plugin."""
        plugin_path = temp_plugin_dir / "simple-plugin"
        plugin_path.mkdir()
        
        # Manifest
        manifest = {
            "name": "simple-plugin",
            "version": "1.0.0",
            "description": "Simple test plugin",
            "author": "Test",
            "type": "handler",
            "entry_point": "plugin.py",
            "entry_class": "SimpleHandler"
        }
        (plugin_path / "plugin.json").write_text(json.dumps(manifest, indent=2))
        
        # Plugin code
        code = """
from tokenade.plugin.base import SiteHandlerPlugin
from tokenade.plugin.api import PluginResult

class SimpleHandler(SiteHandlerPlugin):
    name = "simple-plugin"
    version = "1.0.0"
    description = "Simple test plugin"
    
    def can_handle(self, url):
        return "example.com" in url
    
    def extract_session(self, ctx, url):
        return PluginResult(success=True, data={"cookies": []})
    
    def inject_session(self, ctx, session):
        return PluginResult(success=True)
"""
        (plugin_path / "plugin.py").write_text(code)
        return plugin_path

    def test_discover_load_lifecycle(self, temp_plugin_dir, simple_plugin):
        """Test: discover -> load -> activate workflow."""
        loader = PluginLoader(plugins_dir=temp_plugin_dir)
        
        # Discover
        plugins = loader.discover()
        assert len(plugins) == 1
        assert plugins[0]["name"] == "simple-plugin"
        
        # Load
        loaded_count = loader.load_all()
        assert loaded_count == 1
        
        # Check state
        loaded = loader._loaded.get("simple-plugin")
        assert loaded is not None
        assert loaded.state.value == "active"
        assert loaded.instance is not None

    def test_plugin_with_sandbox(self, temp_plugin_dir, simple_plugin):
        """Test: plugin loading with sandbox protection."""
        sandbox = PluginSandbox(max_failures=3, disabled_file=temp_plugin_dir / ".disabled")
        loader = PluginLoader(plugins_dir=temp_plugin_dir, sandbox=sandbox)
        
        loaded_count = loader.load_all()
        assert loaded_count == 1
        
        # Plugin should not be disabled
        assert not sandbox.is_disabled("simple-plugin")

    def test_failing_plugin_auto_disable(self, temp_plugin_dir):
        """Test: failing plugin gets auto-disabled by sandbox."""
        # Create failing plugin
        plugin_path = temp_plugin_dir / "bad-plugin"
        plugin_path.mkdir()
        
        manifest = {
            "name": "bad-plugin",
            "version": "1.0.0",
            "description": "Failing plugin",
            "type": "handler",
            "entry_point": "plugin.py",
            "entry_class": "BadHandler"
        }
        (plugin_path / "plugin.json").write_text(json.dumps(manifest))
        
        code = """
from tokenade.plugin.base import SiteHandlerPlugin

class BadHandler(SiteHandlerPlugin):
    name = "bad-plugin"
    version = "1.0.0"
    
    def on_load(self):
        raise RuntimeError("This plugin always fails")
    
    def can_handle(self, url):
        return False
    
    def extract_session(self, ctx, url):
        pass
    
    def inject_session(self, ctx, session):
        pass
"""
        (plugin_path / "plugin.py").write_text(code)
        
        sandbox = PluginSandbox(max_failures=1, disabled_file=temp_plugin_dir / ".disabled")
        loader = PluginLoader(plugins_dir=temp_plugin_dir, sandbox=sandbox)
        
        # First load will fail
        loader.load_all()
        
        # Plugin should be in failed state
        loaded = loader._loaded.get("bad-plugin")
        assert loaded is not None
        assert loaded.state.value == "failed"

    def test_multi_plugin_discovery(self, temp_plugin_dir):
        """Test: discover and load multiple plugins."""
        # Create 3 plugins
        for i in range(3):
            plugin_path = temp_plugin_dir / f"plugin-{i}"
            plugin_path.mkdir()
            
            manifest = {
                "name": f"plugin-{i}",
                "version": "1.0.0",
                "description": f"Plugin {i}",
                "type": "handler",
                "entry_point": "plugin.py",
                "entry_class": "Handler"
            }
            (plugin_path / "plugin.json").write_text(json.dumps(manifest))
            
            code = f"""
from tokenade.plugin.base import SiteHandlerPlugin
from tokenade.plugin.api import PluginResult

class Handler(SiteHandlerPlugin):
    name = "plugin-{i}"
    version = "1.0.0"
    
    def can_handle(self, url): return False
    def extract_session(self, ctx, url): return PluginResult(success=True)
    def inject_session(self, ctx, session): return PluginResult(success=True)
"""
            (plugin_path / "plugin.py").write_text(code)
        
        loader = PluginLoader(plugins_dir=temp_plugin_dir)
        plugins = loader.discover()
        assert len(plugins) == 3
        
        loaded_count = loader.load_all()
        assert loaded_count == 3

    def test_discovery_cache(self, temp_plugin_dir, simple_plugin):
        """Test: discovery caching works correctly."""
        loader = PluginLoader(plugins_dir=temp_plugin_dir)
        
        # First discovery
        plugins1 = loader.discover(use_cache=False)
        assert len(plugins1) == 1
        assert loader._discovery_cache is not None
        
        # Cached discovery
        plugins2 = loader.discover(use_cache=True)
        assert len(plugins2) == 1
        assert plugins1 == plugins2

    def test_plugin_reload_preserves_config(self, temp_plugin_dir, simple_plugin):
        """Test: reloading a plugin preserves its config."""
        loader = PluginLoader(plugins_dir=temp_plugin_dir)
        loader.load_all()
        
        # Set config
        loaded = loader._loaded.get("simple-plugin")
        loaded.config = {"test_key": "test_value"}
        
        # Reload
        reloaded = loader.reload("simple-plugin")
        assert reloaded is not None
        assert reloaded.config == {"test_key": "test_value"}

    def test_handler_registration(self, temp_plugin_dir, simple_plugin):
        """Test: handlers are registered after loading."""
        loader = PluginLoader(plugins_dir=temp_plugin_dir)
        loader.load_all()
        
        # Check handler is registered
        assert "simple-plugin" in loader._handlers
        handler = loader._handlers["simple-plugin"]
        assert handler is not None
        assert handler.can_handle("https://example.com/test")

    def test_disabled_plugin_not_loaded(self, temp_plugin_dir, simple_plugin):
        """Test: disabled plugins are skipped during load."""
        loader = PluginLoader(plugins_dir=temp_plugin_dir)
        
        # Disable the plugin
        loader._disabled.add("simple-plugin")
        loader._save_disabled_list()
        
        # Try to load
        loaded_count = loader.load_all()
        assert loaded_count == 0
        assert "simple-plugin" not in loader._loaded

    def test_sandbox_subprocess_verification(self, temp_plugin_dir, simple_plugin):
        """Test: sandbox can verify plugins in subprocess."""
        sandbox = PluginSandbox(disabled_file=temp_plugin_dir / ".disabled")
        plugin_file = simple_plugin / "plugin.py"
        
        success, output = sandbox.verify_in_subprocess(plugin_file, timeout=10)
        assert success
        assert "success" in output.lower()
