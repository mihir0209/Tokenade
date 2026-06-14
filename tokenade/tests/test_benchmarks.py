"""
Performance benchmarks for Tokenade.

These tests verify that critical operations complete within acceptable time limits.
They are not speed tests — they ensure operations don't regress into slowness.
"""
import json
import tempfile
import time
from pathlib import Path
import pytest


@pytest.fixture
def large_session():
    """Generate a session with many cookies for benchmarking."""
    cookies = []
    for i in range(200):
        cookies.append({
            "name": f"cookie_{i}",
            "value": "x" * 100,
            "domain": f".site{i}.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "Lax",
            "expires": 1800000000 + i,
        })
    return {
        "version": "2.0",
        "created_at": "2026-01-01T00:00:00Z",
        "site_name": "benchmark",
        "auth_status": "logged_in",
        "cookies": cookies,
        "fingerprint": {"user_agent": "Mozilla/5.0", "platform": "Linux"},
        "tls_profile": {"browser": "chrome", "version": "120", "impersonate": "chrome120"},
    }


class TestPerformanceBenchmarks:
    """Performance benchmarks for critical operations."""
    
    def test_session_packaging_speed(self, large_session):
        """Session packaging should handle 200 cookies in < 1 second."""
        from tokenade.core.importer.session_packager import SessionPackager
        packager = SessionPackager()
        
        start = time.time()
        for _ in range(10):
            packager.package(
                cookies=large_session["cookies"],
                browser="chrome",
                profile="default",
            )
        elapsed = time.time() - start
        
        assert elapsed < 1.0, f"Packaging 200 cookies x10 took {elapsed:.2f}s (expected < 1.0s)"
    
    def test_format_export_speed(self, large_session):
        """Format export should handle 200 cookies in < 1 second."""
        from tokenade.core.importer.format_exporter import FormatExporter
        exporter = FormatExporter(large_session)
        
        start = time.time()
        for _ in range(10):
            exporter.to_playwright_storagestate()
            exporter.to_puppeteer_cookies()
            exporter.to_netscape()
            exporter.to_cookie_header()
        elapsed = time.time() - start
        
        assert elapsed < 1.0, f"Exporting 200 cookies x10 took {elapsed:.2f}s (expected < 1.0s)"
    
    def test_health_scoring_speed(self, large_session):
        """Health scoring should handle 200 cookies in < 1 second."""
        from tokenade.core.refresh.health_scorer import SessionHealthScorer
        scorer = SessionHealthScorer()
        
        start = time.time()
        for _ in range(50):
            scorer.score(large_session)
        elapsed = time.time() - start
        
        assert elapsed < 1.0, f"Scoring 200 cookies x50 took {elapsed:.2f}s (expected < 1.0s)"
    
    def test_lru_cache_performance(self):
        """LRU cache should handle 10000 operations in < 1 second."""
        from tokenade.core.utils.performance import LRUCache
        cache = LRUCache(max_size=1000, default_ttl=300)
        
        start = time.time()
        for i in range(10000):
            cache.set(f"key_{i}", f"value_{i}")
        for i in range(10000):
            cache.get(f"key_{i}")
        elapsed = time.time() - start
        
        assert elapsed < 1.0, f"10000 cache ops took {elapsed:.2f}s (expected < 1.0s)"
    
    def test_vault_operations_speed(self, large_session):
        """Vault add/get/list should be fast."""
        from tokenade.core.importer.session_vault import SessionVault
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = SessionVault(tmpdir)
            
            # Create session file
            session_file = Path(tmpdir) / "bench.tokenade"
            session_file.write_text(json.dumps(large_session))
            
            start = time.time()
            # Add 100 sessions
            for i in range(100):
                vault.add(str(session_file), session_id=f"sess_{i}", tags=["bench"])
            
            # List all
            entries = vault.list_sessions()
            
            # Get one
            vault.get("sess_50")
            
            elapsed = time.time() - start
            
            assert elapsed < 2.0, f"100 vault ops took {elapsed:.2f}s (expected < 2.0s)"
            assert len(entries) == 100
    
    def test_cookie_header_parsing_speed(self):
        """Cookie header parsing should handle large headers quickly."""
        from tokenade.core.importer.format_importer import FormatImporter
        
        # Generate large cookie header
        pairs = [f"cookie_{i}=value_{i}" for i in range(200)]
        header = "; ".join(pairs)
        
        start = time.time()
        for _ in range(50):
            FormatImporter.from_cookie_header(header, domain=".example.com")
        elapsed = time.time() - start
        
        assert elapsed < 1.0, f"Parsing 200 cookies x50 took {elapsed:.2f}s (expected < 1.0s)"
    
    def test_netscape_parsing_speed(self):
        """Netscape format parsing should handle large files quickly."""
        from tokenade.core.importer.format_importer import FormatImporter
        
        # Generate large Netscape file
        lines = ["# Netscape HTTP Cookie File", ""]
        for i in range(200):
            lines.append(f".site{i}.com\tTRUE\t/\tFALSE\t1800000000\tcookie_{i}\tvalue_{i}")
        content = "\n".join(lines)
        
        start = time.time()
        for _ in range(50):
            FormatImporter.from_cookie_header(content, domain=".example.com")
        elapsed = time.time() - start
        
        assert elapsed < 1.0, f"Parsing Netscape x50 took {elapsed:.2f}s (expected < 1.0s)"

    def test_exception_creation_speed(self):
        """Exception creation should be fast."""
        from tokenade.core.errors import (
            TokenadeError, ExtractionError, InjectionError, EncryptionError,
            DecryptionError, ProxyError, ConfigurationError, ValidationError,
        )

        exceptions = [
            TokenadeError, ExtractionError, InjectionError, EncryptionError,
            DecryptionError, ProxyError, ConfigurationError, ValidationError,
        ]

        start = time.time()
        for _ in range(10000):
            for exc_cls in exceptions:
                try:
                    raise exc_cls("test message", operation="benchmark")
                except Exception:
                    pass
        elapsed = time.time() - start

        assert elapsed < 2.0, f"10000 exception creation/catch took {elapsed:.2f}s (expected < 2.0s)"

    def test_session_monitor_registration_speed(self, large_session):
        """Session monitor registration should be fast."""
        from tokenade.core.monitoring.session_monitor import SessionMonitor

        monitor = SessionMonitor()

        start = time.time()
        for i in range(100):
            monitor.register_session(f"sess_{i}", large_session, f"site_{i}")
        elapsed = time.time() - start

        assert elapsed < 1.0, f"Registering 100 sessions took {elapsed:.2f}s (expected < 1.0s)"

    def test_plugin_loader_discovery_speed(self):
        """Plugin discovery should be fast even with many directories."""
        from tokenade.core.integration.plugin_loader import PluginLoader
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_dir = Path(tmpdir) / "plugins"
            plugins_dir.mkdir()

            # Create 50 fake plugin directories
            for i in range(50):
                plugin_dir = plugins_dir / f"plugin_{i}"
                plugin_dir.mkdir()
                manifest = {"name": f"plugin_{i}", "version": "1.0.0", "type": "handler", "entry_point": ""}
                (plugin_dir / "plugin.json").write_text(json.dumps(manifest))

            loader = PluginLoader(plugins_dir)

            start = time.time()
            for _ in range(100):
                loader.discover()
            elapsed = time.time() - start

            assert elapsed < 1.0, f"Discovering 50 plugins x100 took {elapsed:.2f}s (expected < 1.0s)"
