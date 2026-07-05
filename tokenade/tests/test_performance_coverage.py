"""Tests for performance utilities - coverage boost."""

import asyncio
import time
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from tokenade.core.utils.performance import (
    LRUCache,
    CacheEntry,
    ConnectionPool,
    ParallelExtractor,
    RateLimiter,
    cached,
)


def _run_async(coro):
    return asyncio.run(coro)


class TestCacheEntry:
    def test_not_expired(self):
        entry = CacheEntry(value="v", created_at=time.time(), ttl=300)
        assert entry.is_expired is False

    def test_expired(self):
        entry = CacheEntry(value="v", created_at=time.time() - 400, ttl=300)
        assert entry.is_expired is True

    def test_boundary_expired(self):
        entry = CacheEntry(value="v", created_at=time.time() - 300, ttl=300)
        assert entry.is_expired is True


class TestLRUCacheCoverage:
    def test_set_existing_key_moves_to_end(self):
        cache = LRUCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("a", 10)  # update and move to end
        cache.set("d", 4)  # should evict b
        assert cache.get("a") == 10
        assert cache.get("b") is None
        assert cache.get("c") == 3

    def test_get_expired_entry(self):
        cache = LRUCache()
        cache.set("key", "val", ttl=0.01)
        time.sleep(0.05)
        assert cache.get("key") is None
        assert cache.stats["misses"] >= 1

    def test_delete_returns_false(self):
        cache = LRUCache()
        assert cache.delete("nonexistent") is False

    def test_contains_expired(self):
        cache = LRUCache()
        cache.set("key", "val", ttl=0.01)
        time.sleep(0.05)
        assert "key" not in cache

    def test_cleanup_returns_count(self):
        cache = LRUCache()
        cache.set("a", 1, ttl=0.01)
        cache.set("b", 2, ttl=0.01)
        cache.set("c", 3, ttl=300)
        time.sleep(0.05)
        removed = cache.cleanup()
        assert removed == 2
        assert len(cache) == 1

    def test_cleanup_no_expired(self):
        cache = LRUCache()
        cache.set("a", 1, ttl=300)
        removed = cache.cleanup()
        assert removed == 0

    def test_stats_empty_cache(self):
        cache = LRUCache()
        stats = cache.stats
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["evictions"] == 0
        assert stats["size"] == 0

    def test_stats_with_evictions(self):
        cache = LRUCache(max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)  # evicts a
        stats = cache.stats
        assert stats["evictions"] == 1

    def test_clear_resets(self):
        cache = LRUCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert len(cache) == 0
        assert cache.get("a") is None


class TestCachedDecoratorCoverage:
    def test_cached_with_kwargs(self):
        call_count = 0

        @cached(ttl=60)
        def func(x, y=10):
            nonlocal call_count
            call_count += 1
            return x + y

        assert func(1, y=20) == 21
        assert func(1, y=20) == 21
        assert call_count == 1

    def test_cached_different_kwargs(self):
        call_count = 0

        @cached(ttl=60)
        def func(x, y=10):
            nonlocal call_count
            call_count += 1
            return x + y

        func(1, y=20)
        func(1, y=30)
        assert call_count == 2


class TestConnectionPoolCoverage:
    def test_pool_stats_initial_state(self):
        pool = ConnectionPool()
        stats = pool.stats
        assert stats["created"] == 0
        assert stats["reused"] == 0
        assert stats["closed"] == 0
        assert stats["active"] == 0
        assert stats["idle"] == 0

    def test_pool_custom_params(self):
        pool = ConnectionPool(max_connections=50, max_per_host=10, connection_timeout=5, idle_timeout=30)
        assert pool._max_connections == 50
        assert pool._max_per_host == 10
        assert pool._connection_timeout == 5
        assert pool._idle_timeout == 30

    def test_acquire_new_connection(self):
        pool = ConnectionPool()
        mock_session = AsyncMock()
        mock_session._created_at = time.time()
        with patch.object(pool, '_create_connection', new_callable=AsyncMock, return_value=mock_session):
            conn = _run_async(pool.acquire("example.com"))
            assert conn is mock_session
            assert pool._active_count == 1
            assert pool._stats["created"] == 1

    def test_acquire_reuse_connection(self):
        pool = ConnectionPool()
        mock_session = AsyncMock()
        mock_session._created_at = time.time()
        pool._connections["example.com"] = [mock_session]
        conn = _run_async(pool.acquire("example.com"))
        assert conn is mock_session
        assert pool._stats["reused"] == 1

    def test_release_to_pool(self):
        pool = ConnectionPool()
        mock_session = AsyncMock()
        pool._active_count = 1
        _run_async(pool.release("example.com", mock_session))
        assert pool._active_count == 0
        assert pool._connections["example.com"] == [mock_session]

    def test_release_over_limit(self):
        pool = ConnectionPool(max_per_host=1)
        mock_existing = AsyncMock()
        mock_new = AsyncMock()
        pool._connections["example.com"] = [mock_existing]
        pool._active_count = 2
        _run_async(pool.release("example.com", mock_new))
        assert pool._active_count == 1

    def test_wait_for_connection_timeout(self):
        pool = ConnectionPool(connection_timeout=0.01)
        with pytest.raises(TimeoutError):
            _run_async(pool._wait_for_connection("example.com"))

    def test_close_connection_with_close(self):
        pool = ConnectionPool()
        mock_conn = AsyncMock()
        mock_conn.close = AsyncMock()
        _run_async(pool._close_connection(mock_conn))
        mock_conn.close.assert_called_once()

    def test_close_connection_without_close(self):
        pool = ConnectionPool()
        _run_async(pool._close_connection("plain_string_conn"))

    def test_close_connection_exception(self):
        pool = ConnectionPool()
        mock_conn = AsyncMock()
        mock_conn.close = AsyncMock(side_effect=Exception("fail"))
        _run_async(pool._close_connection(mock_conn))

    def test_cleanup_removes_idle(self):
        pool = ConnectionPool(idle_timeout=0.01)
        mock_old = MagicMock()
        mock_old._created_at = time.time() - 100
        pool._connections["example.com"] = [mock_old]
        time.sleep(0.02)
        _run_async(pool.cleanup())
        assert pool._connections["example.com"] == []

    def test_cleanup_keeps_fresh(self):
        pool = ConnectionPool(idle_timeout=300)
        mock_fresh = MagicMock()
        mock_fresh._created_at = time.time()
        pool._connections["example.com"] = [mock_fresh]
        _run_async(pool.cleanup())
        assert len(pool._connections["example.com"]) == 1

    def test_acquire_under_limit(self):
        pool = ConnectionPool(max_connections=10)
        pool._active_count = 5
        mock_session = AsyncMock()
        with patch.object(pool, '_create_connection', new_callable=AsyncMock, return_value=mock_session):
            conn = _run_async(pool.acquire("example.com"))
            assert conn is mock_session


class TestRateLimiterCoverage:
    def test_refill_tokens(self):
        limiter = RateLimiter(rate=10, burst=5)
        limiter._tokens = 0
        limiter._last_refill = time.time() - 1
        limiter._refill()
        assert limiter._tokens > 0
        assert limiter._tokens <= 5

    def test_refill_caps_at_burst(self):
        limiter = RateLimiter(rate=100, burst=3)
        limiter._tokens = 2
        limiter._last_refill = time.time() - 10
        limiter._refill()
        assert limiter._tokens == 3

    def test_available_refills_first(self):
        limiter = RateLimiter(rate=10, burst=5)
        limiter._tokens = 0
        limiter._last_refill = time.time() - 1
        avail = limiter.available
        assert avail > 0

    def test_acquire_when_available(self):
        limiter = RateLimiter(rate=100, burst=5)
        _run_async(limiter.acquire())
        assert limiter._tokens < 5

    def test_acquire_waits_for_token(self):
        limiter = RateLimiter(rate=1000, burst=1)
        limiter._tokens = 0
        limiter._last_refill = time.time() - 1
        _run_async(limiter.acquire())
        assert limiter._tokens < 1


class TestParallelExtractorCoverage:
    def test_shutdown(self):
        extractor = ParallelExtractor(max_workers=2)
        extractor.shutdown()

    def test_extract_single_no_profile(self):
        extractor = ParallelExtractor()
        with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery") as mock_disc:
            mock_disc.return_value.discover_all.return_value = {"chrome": []}
            with pytest.raises(ValueError, match="No profile found"):
                extractor._extract_single(
                    {"browser": "chrome"}, []
                )

    def test_extract_single_with_profile(self):
        extractor = ParallelExtractor()
        mock_profile = MagicMock()
        mock_profile.browser = "chrome"
        mock_profile.name = "Default"
        mock_profile.path = "/path"
        with patch("tokenade.core.importer.cookie_extractor.CookieExtractor") as mock_ext:
            mock_extractor = MagicMock()
            mock_extractor.extract.return_value = [{"name": "c"}]
            mock_ext.return_value = mock_extractor
            result = extractor._extract_single(
                {"browser": "chrome"}, [mock_profile]
            )
            assert result["cookies"] == [{"name": "c"}]
            assert result["browser"] == "chrome"
            assert result["profile"] == "Default"

    def test_extract_single_with_domains(self):
        extractor = ParallelExtractor()
        mock_profile = MagicMock()
        mock_profile.browser = "firefox"
        mock_profile.name = "Default"
        mock_profile.path = "/path"
        with patch("tokenade.core.importer.cookie_extractor.CookieExtractor") as mock_ext, \
                patch("tokenade.core.importer.cookie_extractor.SiteFilter") as mock_sf:
            mock_extractor = MagicMock()
            mock_extractor.extract.return_value = [{"name": "c"}]
            mock_ext.return_value = mock_extractor
            mock_sf.return_value = MagicMock()
            result = extractor._extract_single(
                {"browser": "firefox", "domains": "example.com, test.com"}, [mock_profile]
            )
            assert result["cookies"] == [{"name": "c"}]

    def test_extract_single_with_empty_domains(self):
        extractor = ParallelExtractor()
        mock_profile = MagicMock()
        mock_profile.browser = "chrome"
        mock_profile.name = "Default"
        mock_profile.path = "/path"
        with patch("tokenade.core.importer.cookie_extractor.CookieExtractor") as mock_ext:
            mock_extractor = MagicMock()
            mock_extractor.extract.return_value = []
            mock_ext.return_value = mock_extractor
            result = extractor._extract_single(
                {"browser": "chrome", "domains": ",,,"}, [mock_profile]
            )
            assert result["cookies"] == []

    def test_extract_single_with_profile_filter(self):
        extractor = ParallelExtractor()
        mock_profile1 = MagicMock()
        mock_profile1.browser = "chrome"
        mock_profile1.name = "Profile1"
        mock_profile1.path = "/path1"
        mock_profile2 = MagicMock()
        mock_profile2.browser = "chrome"
        mock_profile2.name = "Profile2"
        mock_profile2.path = "/path2"
        with patch("tokenade.core.importer.cookie_extractor.CookieExtractor") as mock_ext:
            mock_extractor = MagicMock()
            mock_extractor.extract.return_value = [{"name": "c"}]
            mock_ext.return_value = mock_extractor
            result = extractor._extract_single(
                {"browser": "chrome", "profile": "Profile2"},
                [mock_profile1, mock_profile2],
            )
            assert result["profile"] == "Profile2"


class TestExtractParallel:
    def test_extract_parallel_success(self):
        extractor = ParallelExtractor(max_workers=2)
        mock_profile = MagicMock()
        mock_profile.browser = "chrome"
        mock_profile.name = "Default"
        mock_profile.path = "/path"

        with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery") as mock_disc, \
                patch("tokenade.core.importer.cookie_extractor.CookieExtractor") as mock_ext:
            mock_disc.return_value.discover_all.return_value = {"chrome": [mock_profile]}
            mock_extractor = MagicMock()
            mock_extractor.extract.return_value = [{"name": "c1"}]
            mock_ext.return_value = mock_extractor

            results = _run_async(extractor.extract_parallel([
                {"browser": "chrome"},
            ]))
            assert 0 in results
            assert results[0]["success"] is True
            assert results[0]["cookie_count"] == 1

        extractor.shutdown()

    def test_extract_parallel_error(self):
        extractor = ParallelExtractor(max_workers=2)

        with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery") as mock_disc:
            mock_disc.return_value.discover_all.return_value = {"chrome": []}

            results = _run_async(extractor.extract_parallel([
                {"browser": "nonexistent"},
            ]))
            assert 0 in results
            assert results[0]["success"] is False
            assert results[0]["cookie_count"] == 0

        extractor.shutdown()
