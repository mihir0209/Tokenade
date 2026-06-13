"""Tests for performance utilities."""

import asyncio
import time
import pytest
from tokenade.core.utils.performance import (
    LRUCache,
    ConnectionPool,
    ParallelExtractor,
    RateLimiter,
    cached,
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


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_rate_limiter(self):
        limiter = RateLimiter(rate=10, burst=5)
        assert limiter.available == 5
        
        await limiter.acquire()
        assert limiter.available < 5


class TestParallelExtractor:
    def test_extractor_creation(self):
        extractor = ParallelExtractor(max_workers=4)
        assert extractor._max_workers == 4
        extractor.shutdown()
