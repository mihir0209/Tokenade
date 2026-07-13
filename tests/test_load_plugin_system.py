"""Load testing for the plugin ecosystem.

Tests performance and stability with 30+ plugins loaded simultaneously.
Verifies caching, concurrency, memory usage, and sandbox behavior at scale.
"""
import json
import threading
import time
import tracemalloc
from pathlib import Path

import pytest

from tokenade.core.integration.plugin_loader import PluginLoader
from tokenade.core.integration.plugin_sandbox import PluginSandbox


class TestPluginLoadTesting:
    """Load testing for plugin system with 30+ plugins."""

    @pytest.fixture
    def large_plugin_dir(self, tmp_path):
        """Create 30 dummy plugins for load testing."""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        
        for i in range(30):
            plugin_path = plugin_dir / f"load-plugin-{i}"
            plugin_path.mkdir()
            
            # Manifest
            manifest = {
                "name": f"load-plugin-{i}",
                "version": "1.0.0",
                "description": f"Load test plugin {i}",
                "author": "Test",
                "type": "handler",
                "entry_point": "plugin.py",
                "entry_class": "LoadHandler"
            }
            (plugin_path / "plugin.json").write_text(json.dumps(manifest, indent=2))
            
            # Simple plugin code
            code = f"""
from tokenade.plugin.base import SiteHandlerPlugin
from tokenade.plugin.api import PluginResult

class LoadHandler(SiteHandlerPlugin):
    name = "load-plugin-{i}"
    version = "1.0.0"
    description = "Load test plugin {i}"
    
    def can_handle(self, url):
        return "test{i}.com" in url
    
    def extract_session(self, ctx, url):
        return PluginResult(success=True, data={{"cookies": []}})
    
    def inject_session(self, ctx, session):
        return PluginResult(success=True)
"""
            (plugin_path / "plugin.py").write_text(code)
        
        return plugin_dir

    def test_discovery_performance_uncached(self, large_plugin_dir):
        """Test: discovery performance with 30 plugins (uncached)."""
        loader = PluginLoader(plugins_dir=large_plugin_dir)
        
        start = time.perf_counter()
        plugins = loader.discover(use_cache=False)
        duration = time.perf_counter() - start
        
        assert len(plugins) == 30
        assert duration < 0.5, f"Discovery took {duration:.3f}s, expected <0.5s"

    def test_discovery_performance_cached(self, large_plugin_dir):
        """Test: discovery cache effectiveness."""
        loader = PluginLoader(plugins_dir=large_plugin_dir)
        
        # First discovery (uncached)
        loader.discover(use_cache=False)
        
        # Second discovery (should use cache)
        start = time.perf_counter()
        plugins = loader.discover(use_cache=True)
        duration = time.perf_counter() - start
        
        assert len(plugins) == 30
        assert duration < 0.05, f"Cached discovery took {duration:.3f}s, expected <0.05s"

    def test_load_all_performance(self, large_plugin_dir):
        """Test: load 30 plugins performance and memory usage."""
        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()
        
        loader = PluginLoader(plugins_dir=large_plugin_dir)
        
        start = time.perf_counter()
        loaded_count = loader.load_all()
        duration = time.perf_counter() - start
        
        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()
        
        # Check performance
        assert loaded_count == 30
        assert duration < 5.0, f"Loading took {duration:.3f}s, expected <5s"
        
        # Check memory growth (rough estimate)
        top_stats = snapshot_after.compare_to(snapshot_before, 'lineno')
        total_growth = sum(stat.size_diff for stat in top_stats) / 1024 / 1024  # MB
        
        # 30 plugins should use <100MB
        assert total_growth < 100, f"Memory grew by {total_growth:.1f}MB, expected <100MB"

    def test_concurrent_plugin_loading(self, large_plugin_dir):
        """Test: thread safety with concurrent plugin operations."""
        loader = PluginLoader(plugins_dir=large_plugin_dir)
        errors = []
        
        def load_and_check():
            try:
                count = loader.load_all()
                if count != 30:
                    errors.append(f"Expected 30, got {count}")
            except Exception as e:
                errors.append(str(e))
        
        # 5 threads trying to load simultaneously
        threads = [threading.Thread(target=load_and_check) for _ in range(5)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should have no errors (thread-safe or first-wins)
        assert len(errors) == 0, f"Concurrent errors: {errors}"
        assert len(loader._loaded) == 30

    def test_sandbox_under_load(self, tmp_path):
        """Test: sandbox with 30 plugins, 10% failure rate."""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        
        # Create 27 good plugins + 3 failing plugins
        for i in range(27):
            plugin_path = plugin_dir / f"good-{i}"
            plugin_path.mkdir()
            
            manifest = {
                "name": f"good-{i}",
                "version": "1.0.0",
                "type": "handler",
                "entry_point": "plugin.py",
                "entry_class": "GoodHandler"
            }
            (plugin_path / "plugin.json").write_text(json.dumps(manifest))
            
            code = f"""
from tokenade.plugin.base import SiteHandlerPlugin
from tokenade.plugin.api import PluginResult

class GoodHandler(SiteHandlerPlugin):
    name = "good-{i}"
    version = "1.0.0"
    
    def can_handle(self, url): return False
    def extract_session(self, ctx, url): return PluginResult(success=True)
    def inject_session(self, ctx, session): return PluginResult(success=True)
"""
            (plugin_path / "plugin.py").write_text(code)
        
        # Create 3 failing plugins
        for i in range(3):
            plugin_path = plugin_dir / f"bad-{i}"
            plugin_path.mkdir()
            
            manifest = {
                "name": f"bad-{i}",
                "version": "1.0.0",
                "type": "handler",
                "entry_point": "plugin.py",
                "entry_class": "BadHandler"
            }
            (plugin_path / "plugin.json").write_text(json.dumps(manifest))
            
            code = f"""
from tokenade.plugin.base import SiteHandlerPlugin

class BadHandler(SiteHandlerPlugin):
    name = "bad-{i}"
    version = "1.0.0"
    
    def on_load(self):
        raise RuntimeError("Intentional failure")
    
    def can_handle(self, url): return False
    def extract_session(self, ctx, url): pass
    def inject_session(self, ctx, session): pass
"""
            (plugin_path / "plugin.py").write_text(code)
        
        sandbox = PluginSandbox(max_failures=2, disabled_file=plugin_dir / ".disabled")
        loader = PluginLoader(plugins_dir=plugin_dir, sandbox=sandbox)
        
        loaded_count = loader.load_all()
        
        # Should load 30 total (27 good + 3 failed)
        assert loaded_count == 30
        
        # 3 bad plugins should be in failed state
        failed_count = sum(1 for p in loader._loaded.values() if p.state.value == "failed")
        assert failed_count == 3
        
        # Check sandbox tracked failures
        for i in range(3):
            assert sandbox.get_failure_count(f"bad-{i}") >= 1

    def test_discovery_cache_stress(self, large_plugin_dir):
        """Test: rapid repeated discovery calls verify cache effectiveness."""
        loader = PluginLoader(plugins_dir=large_plugin_dir)
        
        # First uncached discovery
        loader.discover(use_cache=False)
        
        # 100 rapid cached discoveries
        start = time.perf_counter()
        for _ in range(100):
            plugins = loader.discover(use_cache=True)
            assert len(plugins) == 30
        duration = time.perf_counter() - start
        
        # Average per-call should be <1ms
        avg_per_call = duration / 100
        assert avg_per_call < 0.001, f"Avg cached discovery: {avg_per_call*1000:.2f}ms, expected <1ms"

    def test_memory_leak_load_unload_cycle(self, large_plugin_dir):
        """Test: 50 load/unload cycles for memory leaks."""
        tracemalloc.start()
        snapshot_start = tracemalloc.take_snapshot()
        
        for cycle in range(50):
            loader = PluginLoader(plugins_dir=large_plugin_dir)
            loader.load_all()
            
            # Unload all plugins
            for name in list(loader._loaded.keys()):
                loader.unload(name)
            
            # Delete loader to free memory
            del loader
        
        snapshot_end = tracemalloc.take_snapshot()
        tracemalloc.stop()
        
        # Check memory growth over 50 cycles
        top_stats = snapshot_end.compare_to(snapshot_start, 'lineno')
        total_growth = sum(stat.size_diff for stat in top_stats) / 1024 / 1024  # MB
        
        # Should have <10% growth (some GC delay is acceptable)
        # 50 cycles with proper cleanup should not leak significantly
        assert total_growth < 50, f"Memory grew by {total_growth:.1f}MB over 50 cycles, expected <50MB"
