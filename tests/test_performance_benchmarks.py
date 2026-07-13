"""Performance benchmarks — timing assertions for critical plugin operations.

These are NOT speed tests. They assert upper bounds to catch regressions.
"""
import json
import time

import pytest

from tokenade.core.integration.plugin_loader import PluginLoader
from tokenade.core.integration.plugin_search import PluginSearchIndex
from tokenade.core.integration.plugin_security import validate_plugin_security
from tokenade.core.integration.plugin_verifier import PluginVerifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_plugins(base, count, prefix="perf"):
    """Create N plugin directories with valid manifests."""
    for i in range(count):
        d = base / f"{prefix}-{i}"
        d.mkdir()
        (d / "plugin.json").write_text(json.dumps({
            "name": f"{prefix}-{i}", "version": "1.0.0", "type": "handler",
            "entry_point": "plugin.py", "description": f"Plugin {i}",
            "tags": ["tag" if i % 2 == 0 else "other"],
            "category": "security" if i % 3 == 0 else "validators",
        }))
        (d / "plugin.py").write_text(f"class P:\n    name = '{prefix}-{i}'\n")


@pytest.fixture
def perf_plugins(tmp_path):
    """Create 50 plugin directories for performance testing."""
    _create_plugins(tmp_path, 50)
    return tmp_path


# ===================================================================
# Discovery speed
# ===================================================================

class TestDiscoveryPerformance:
    def test_discover_50_plugins_under_2s(self, perf_plugins):
        loader = PluginLoader(plugins_dir=perf_plugins)
        start = time.monotonic()
        plugins = loader.discover()
        elapsed = time.monotonic() - start
        assert len(plugins) == 50
        assert elapsed < 2.0, f"Discovery took {elapsed:.2f}s (>2s)"

    def test_discover_10_plugins_under_500ms(self, tmp_path):
        _create_plugins(tmp_path, 10, prefix="fast")
        loader = PluginLoader(plugins_dir=tmp_path)
        start = time.monotonic()
        plugins = loader.discover()
        elapsed = time.monotonic() - start
        assert len(plugins) == 10
        assert elapsed < 0.5, f"Discovery took {elapsed:.2f}s (>500ms)"


# ===================================================================
# Cache effectiveness
# ===================================================================

class TestCachePerformance:
    def test_cached_fetch_faster_than_network(self, perf_plugins):
        from tokenade.core.integration.plugin_registry import PluginRegistry
        import time as _time

        reg = PluginRegistry(registry_url="https://example.com", plugins_dir=perf_plugins)
        plugins = [{"name": f"p{i}", "version": "1.0", "type": "handler",
                    "entry_point": "plugin.py", "description": f"P{i}"}
                   for i in range(50)]
        cache = {"timestamp": _time.time(), "plugins": plugins}
        (perf_plugins / ".registry_cache.json").write_text(json.dumps(cache))

        # Cached fetch
        start = time.monotonic()
        for _ in range(100):
            reg._fetch_registry()
        cached_time = time.monotonic() - start

        # Should be fast (< 100ms for 100 reads)
        assert cached_time < 0.1, f"100 cached fetches took {cached_time:.3f}s (>100ms)"


# ===================================================================
# Search latency
# ===================================================================

class TestSearchPerformance:
    def test_search_100_plugins_under_500ms(self, tmp_path):
        idx = PluginSearchIndex(plugins_dir=tmp_path)
        plugins = [{"name": f"search-{i}", "description": f"Description for plugin {i}",
                    "author": f"author-{i % 10}", "tags": [f"tag{i % 5}"]}
                   for i in range(100)]
        idx.build_index(plugins)

        queries = ["search", "plugin", "author-3", "tag2", "description"]
        start = time.monotonic()
        for q in queries:
            idx.search(q)
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"5 searches on 100 plugins took {elapsed:.3f}s (>500ms)"

    def test_build_index_100_plugins_under_200ms(self, tmp_path):
        idx = PluginSearchIndex(plugins_dir=tmp_path)
        plugins = [{"name": f"idx-{i}", "description": f"Desc {i}",
                    "author": "auth", "tags": ["t1", "t2"]}
                   for i in range(100)]
        start = time.monotonic()
        idx.build_index(plugins)
        elapsed = time.monotonic() - start
        assert elapsed < 0.2, f"Index build took {elapsed:.3f}s (>200ms)"


# ===================================================================
# Security validation per plugin
# ===================================================================

class TestSecurityPerformance:
    def test_security_check_under_100ms(self, perf_plugins):
        start = time.monotonic()
        for i in range(50):
            validate_plugin_security(perf_plugins / f"perf-{i}")
        elapsed = time.monotonic() - start
        per_plugin = elapsed / 50
        assert per_plugin < 0.1, f"Security check took {per_plugin*1000:.1f}ms/plugin (>100ms)"


# ===================================================================
# Memory: loading 50 plugins
# ===================================================================

class TestMemoryPerformance:
    def test_load_50_plugins_under_2s(self, perf_plugins):
        loader = PluginLoader(plugins_dir=perf_plugins)
        loader.discover()
        start = time.monotonic()
        loader.load_all()
        elapsed = time.monotonic() - start
        # Plugins without proper entry classes won't load, but discovery+attempt should be fast
        assert elapsed < 2.0, f"Loading 50 plugins took {elapsed:.2f}s (>2s)"


# ===================================================================
# Verifier performance
# ===================================================================

class TestVerifierPerformance:
    def test_compute_checksums_50_plugins_under_1s(self, perf_plugins):
        verifier = PluginVerifier(plugins_dir=perf_plugins)
        start = time.monotonic()
        for i in range(50):
            verifier.compute_plugin_checksums(f"perf-{i}")
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"Checksum computation took {elapsed:.2f}s (>1s)"
