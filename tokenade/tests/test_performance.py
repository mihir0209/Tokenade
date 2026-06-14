"""Tests for performance utilities."""

import asyncio
import time
import pytest
from unittest.mock import patch, MagicMock
from tokenade.core.utils.performance import (
    LRUCache,
    ConnectionPool,
    ParallelExtractor,
    RateLimiter,
    cached,
    get_cache,
    get_connection_pool,
)


class TestLRUCache:
    def test_basic_get_set(self):
        cache = LRUCache(max_size=10)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
    
    def test_cache_miss(self):
        cache = LRUCache()
        assert cache.get("nonexistent") is None
    
    def test_cache_expiry(self):
        cache = LRUCache()
        cache.set("key1", "value1", ttl=0.01)
        time.sleep(0.1)
        assert cache.get("key1") is None
    
    def test_lru_eviction(self):
        cache = LRUCache(max_size=2)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")  # Should evict key1
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"
    
    def test_lru_ordering(self):
        cache = LRUCache(max_size=2)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.get("key1")  # Access key1 to make it recent
        cache.set("key3", "value3")  # Should evict key2
        assert cache.get("key1") == "value1"
        assert cache.get("key2") is None
    
    def test_delete(self):
        cache = LRUCache()
        cache.set("key1", "value1")
        assert cache.delete("key1") is True
        assert cache.get("key1") is None
        assert cache.delete("key1") is False
    
    def test_clear(self):
        cache = LRUCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert len(cache) == 0
    
    def test_cleanup(self):
        cache = LRUCache()
        cache.set("key1", "value1", ttl=0.01)
        cache.set("key2", "value2", ttl=300)
        time.sleep(0.1)
        removed = cache.cleanup()
        assert removed == 1
        assert len(cache) == 1
    
    def test_stats(self):
        cache = LRUCache(max_size=10)
        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key2")  # Miss
        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1
    
    def test_contains(self):
        cache = LRUCache()
        cache.set("key1", "value1")
        assert "key1" in cache
        assert "key2" not in cache

    def test_overwrite_existing_key(self):
        cache = LRUCache(max_size=3)
        cache.set("key1", "v1")
        cache.set("key1", "v2")
        assert cache.get("key1") == "v2"
        assert len(cache) == 1

    def test_default_ttl(self):
        cache = LRUCache(default_ttl=0.01)
        cache.set("key1", "value1")
        time.sleep(0.1)
        assert cache.get("key1") is None

    def test_custom_ttl_overrides_default(self):
        cache = LRUCache(default_ttl=300)
        cache.set("key1", "value1", ttl=0.01)
        time.sleep(0.1)
        assert cache.get("key1") is None

    def test_stats_hit_rate(self):
        cache = LRUCache()
        cache.set("a", 1)
        cache.get("a")  # hit
        cache.get("a")  # hit
        cache.get("b")  # miss
        stats = cache.stats
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == "66.67%"


class TestCachedDecorator:
    def test_cached_function(self):
        call_count = 0
        
        @cached(ttl=60)
        def expensive_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2
        
        result1 = expensive_func(5)
        result2 = expensive_func(5)
        assert result1 == 10
        assert result2 == 10
        assert call_count == 1  # Should only be called once
    
    def test_cached_different_args(self):
        call_count = 0
        
        @cached(ttl=60)
        def func(x):
            nonlocal call_count
            call_count += 1
            return x * 2
        
        func(5)
        func(10)
        assert call_count == 2

    def test_cached_expires(self):
        call_count = 0

        @cached(ttl=0.01)
        def func(x):
            nonlocal call_count
            call_count += 1
            return x

        func(1)
        assert call_count == 1
        time.sleep(0.1)
        func(1)
        assert call_count == 2

    def test_cached_has_cache_attr(self):
        @cached(ttl=60)
        def func(x):
            return x

        assert hasattr(func, 'cache')
        assert isinstance(func.cache, LRUCache)


class TestConnectionPool:
    @pytest.mark.asyncio
    async def test_pool_creation(self):
        pool = ConnectionPool(max_connections=10, max_per_host=5)
        assert pool._max_connections == 10
        assert pool._max_per_host == 5
    
    @pytest.mark.asyncio
    async def test_pool_stats(self):
        pool = ConnectionPool()
        stats = pool.stats
        assert "active" in stats
        assert "idle" in stats
        assert "created" in stats

    @pytest.mark.asyncio
    async def test_pool_stats_initial(self):
        pool = ConnectionPool()
        stats = pool.stats
        assert stats["active"] == 0
        assert stats["idle"] == 0
        assert stats["created"] == 0


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_rate_limiter(self):
        limiter = RateLimiter(rate=10, burst=5)
        assert limiter.available == 5
        
        await limiter.acquire()
        assert limiter.available < 5

    @pytest.mark.asyncio
    async def test_rate_limiter_burst(self):
        limiter = RateLimiter(rate=100, burst=3)
        for _ in range(3):
            await limiter.acquire()
        assert limiter.available < 1


class TestParallelExtractor:
    def test_extractor_creation(self):
        extractor = ParallelExtractor(max_workers=4)
        assert extractor._max_workers == 4
        extractor.shutdown()

    def test_extractor_default_workers(self):
        extractor = ParallelExtractor()
        assert extractor._max_workers == 4
        extractor.shutdown()


class TestGlobalInstances:
    def test_get_cache(self):
        cache = get_cache()
        assert isinstance(cache, LRUCache)
        assert cache is get_cache()  # Same instance

    def test_get_connection_pool(self):
        pool = get_connection_pool()
        assert isinstance(pool, ConnectionPool)
        assert pool is get_connection_pool()


class TestSessionPackagerCache:
    def test_load_cached(self, tmp_path):
        from tokenade.core.importer.session_packager import SessionPackager

        session = {
            "version": "2.0",
            "created_at": "2026-01-01T00:00:00Z",
            "site_name": "test",
            "auth_status": "logged_in",
            "cookies": [
                {"name": "sid", "value": "abc", "domain": ".test.com", "path": "/"},
            ],
        }
        f = tmp_path / "test.tokenade"
        f.write_text(__import__("json").dumps(session))

        packager = SessionPackager(cache_ttl=60)
        result1 = packager.load(str(f))
        result2 = packager.load(str(f))
        assert result1["site_name"] == "test"
        assert result2["site_name"] == "test"

    def test_save_updates_cache(self, tmp_path):
        from tokenade.core.importer.session_packager import SessionPackager

        session = {
            "version": "2.0",
            "created_at": "2026-01-01T00:00:00Z",
            "site_name": "test",
            "auth_status": "logged_in",
            "cookies": [],
        }
        packager = SessionPackager(cache_ttl=60)
        out = tmp_path / "out.tokenade"
        saved_path = packager.save(session, str(out))
        cached = packager._cache.get(saved_path)
        assert cached is not None
        assert cached["site_name"] == "test"

    def test_cache_disabled(self, tmp_path):
        from tokenade.core.importer.session_packager import SessionPackager

        session = {
            "version": "2.0",
            "created_at": "2026-01-01T00:00:00Z",
            "site_name": "test",
            "auth_status": "logged_in",
            "cookies": [],
        }
        f = tmp_path / "test.tokenade"
        f.write_text(__import__("json").dumps(session))

        packager = SessionPackager(cache_ttl=0)
        assert packager._cache is None
        result = packager.load(str(f))
        assert result["site_name"] == "test"

    def test_load_file_not_found(self):
        from tokenade.core.importer.session_packager import SessionPackager

        packager = SessionPackager(cache_ttl=60)
        with pytest.raises(FileNotFoundError):
            packager.load("/nonexistent/file.tokenade")
