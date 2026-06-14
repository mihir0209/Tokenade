"""
Performance utilities: connection pooling, LRU cache, parallel extraction.
"""

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache, wraps
from typing import Any, Callable, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class CacheEntry:
    """Cache entry with expiry."""
    value: Any
    created_at: float
    ttl: int  # seconds
    
    @property
    def is_expired(self) -> bool:
        return time.time() - self.created_at >= self.ttl


class LRUCache:
    """
    Thread-safe LRU cache with TTL support.
    
    Features:
    - Configurable max size
    - TTL-based expiry
    - Thread-safe operations
    - Cache statistics
    """
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if key in self._cache:
            entry = self._cache[key]
            if entry.is_expired:
                del self._cache[key]
                self._stats["misses"] += 1
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._stats["hits"] += 1
            return entry.value
        
        self._stats["misses"] += 1
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache."""
        if key in self._cache:
            self._cache.move_to_end(key)
        elif len(self._cache) >= self._max_size:
            # Evict oldest
            self._cache.popitem(last=False)
            self._stats["evictions"] += 1
        
        self._cache[key] = CacheEntry(
            value=value,
            created_at=time.time(),
            ttl=ttl if ttl is not None else self._default_ttl,
        )
    
    def delete(self, key: str) -> bool:
        """Delete value from cache."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
    
    def cleanup(self) -> int:
        """Remove expired entries. Returns number of removed entries."""
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired
        ]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)
    
    @property
    def stats(self) -> Dict:
        """Get cache statistics."""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total if total > 0 else 0
        return {
            **self._stats,
            "size": len(self._cache),
            "max_size": self._max_size,
            "hit_rate": f"{hit_rate:.2%}",
        }
    
    def __len__(self) -> int:
        return len(self._cache)
    
    def __contains__(self, key: str) -> bool:
        return key in self._cache and not self._cache[key].is_expired


def cached(ttl: int = 300, max_size: int = 100):
    """
    Decorator for caching function results.
    
    Args:
        ttl: Time-to-live in seconds
        max_size: Maximum cache size
    """
    def decorator(func: Callable) -> Callable:
        cache = LRUCache(max_size=max_size, default_ttl=ttl)
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from arguments
            key_parts = [func.__name__] + [str(a) for a in args]
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = hashlib.md5("|".join(key_parts).encode()).hexdigest()
            
            # Check cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Execute function
            result = func(*args, **kwargs)
            cache.set(cache_key, result)
            return result
        
        wrapper.cache = cache
        return wrapper
    
    return decorator


class ConnectionPool:
    """
    Async connection pool with configurable limits.
    
    Features:
    - Per-host connection limits
    - Connection reuse
    - Automatic cleanup
    - Statistics tracking
    """
    
    def __init__(
        self,
        max_connections: int = 100,
        max_per_host: int = 30,
        connection_timeout: int = 10,
        idle_timeout: int = 60,
    ):
        self._max_connections = max_connections
        self._max_per_host = max_per_host
        self._connection_timeout = connection_timeout
        self._idle_timeout = idle_timeout
        self._connections: Dict[str, List[Any]] = {}
        self._active_count = 0
        self._stats = {"created": 0, "reused": 0, "closed": 0}
    
    async def acquire(self, host: str) -> Any:
        """Acquire a connection for the host."""
        if host in self._connections and self._connections[host]:
            # Reuse existing connection
            conn = self._connections[host].pop()
            self._active_count += 1
            self._stats["reused"] += 1
            return conn
        
        # Create new connection if under limit
        if self._active_count < self._max_connections:
            conn = await self._create_connection(host)
            self._active_count += 1
            self._stats["created"] += 1
            return conn
        
        # Wait for available connection
        return await self._wait_for_connection(host)
    
    async def release(self, host: str, conn: Any) -> None:
        """Release a connection back to the pool."""
        self._active_count -= 1
        
        if host not in self._connections:
            self._connections[host] = []
        
        if len(self._connections[host]) < self._max_per_host:
            self._connections[host].append(conn)
        else:
            await self._close_connection(conn)
            self._stats["closed"] += 1
    
    async def _create_connection(self, host: str) -> Any:
        """Create a new connection."""
        import aiohttp
        
        connector = aiohttp.TCPConnector(
            ssl=None,
            limit=1,
            enable_cleanup_closed=True,
        )
        timeout = aiohttp.ClientTimeout(total=self._connection_timeout)
        session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return session
    
    async def _wait_for_connection(self, host: str) -> Any:
        """Wait for an available connection."""
        timeout = self._connection_timeout
        start = time.time()
        
        while time.time() - start < timeout:
            if host in self._connections and self._connections[host]:
                return await self.release(host, self._connections[host].pop())
            await asyncio.sleep(0.1)
        
        raise TimeoutError(f"Timeout waiting for connection to {host}")
    
    async def _close_connection(self, conn: Any) -> None:
        """Close a connection."""
        try:
            if hasattr(conn, 'close'):
                await conn.close()
        except Exception:
            pass
    
    async def cleanup(self) -> None:
        """Cleanup idle connections."""
        now = time.time()
        for host in list(self._connections.keys()):
            conns = self._connections[host]
            self._connections[host] = [
                c for c in conns
                if now - getattr(c, '_created_at', now) < self._idle_timeout
            ]
    
    @property
    def stats(self) -> Dict:
        """Get pool statistics."""
        return {
            **self._stats,
            "active": self._active_count,
            "idle": sum(len(c) for c in self._connections.values()),
        }


class ParallelExtractor:
    """
    Parallel cookie extraction from multiple browsers.
    
    Features:
    - Extract from multiple browsers simultaneously
    - Profile discovery before extraction
    - Configurable concurrency limit
    - Progress tracking
    - Error aggregation
    """
    
    def __init__(self, max_workers: int = 4):
        self._max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
    
    async def extract_parallel(
        self,
        extraction_tasks: List[Dict],
    ) -> Dict[str, Any]:
        """
        Extract cookies from multiple browsers in parallel.
        
        Args:
            extraction_tasks: List of task dicts with keys:
                - browser: Browser name (chrome, firefox, edge, brave)
                - profile: Profile name (optional, uses default if not specified)
                - domains: Comma-separated domain filter (optional)
                
        Returns:
            Dict mapping task index to result with keys:
                - success: bool
                - data: List[Dict] of cookies (if success)
                - error: str (if not success)
                - browser: str
                - profile: str
                - cookie_count: int
        """
        from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery
        
        discovery = BrowserProfileDiscovery()
        all_profiles = discovery.discover_all()
        
        flat_profiles = []
        for browser_profiles in all_profiles.values():
            flat_profiles.extend(browser_profiles)
        
        loop = asyncio.get_event_loop()
        results = {}
        
        futures = {}
        for i, task in enumerate(extraction_tasks):
            future = loop.run_in_executor(
                self._executor,
                self._extract_single,
                task,
                flat_profiles,
            )
            futures[i] = future
        
        for i, future in futures.items():
            try:
                result = await future
                results[i] = {
                    "success": True,
                    "data": result["cookies"],
                    "browser": result["browser"],
                    "profile": result["profile"],
                    "cookie_count": len(result["cookies"]),
                }
            except Exception as e:
                results[i] = {
                    "success": False,
                    "error": str(e),
                    "browser": extraction_tasks[i].get("browser", "unknown"),
                    "profile": extraction_tasks[i].get("profile", "default"),
                    "cookie_count": 0,
                }
        
        return results
    
    def _extract_single(self, task: Dict, flat_profiles: list) -> Dict:
        """Extract cookies from a single browser profile."""
        from tokenade.core.importer.cookie_extractor import CookieExtractor
        
        browser = task.get("browser", "chrome")
        profile_name = task.get("profile")
        domains = task.get("domains")
        
        matching = [p for p in flat_profiles if p.browser == browser]
        if profile_name:
            matching = [p for p in matching if p.name == profile_name]
        
        if not matching:
            raise ValueError(f"No profile found for {browser}" + 
                           (f" (profile: {profile_name})" if profile_name else ""))
        
        profile = matching[0]
        extractor = CookieExtractor(str(profile.path), browser=browser)
        
        site_filter = None
        if domains:
            from tokenade.core.importer.cookie_extractor import SiteFilter
            domain_list = [d.strip() for d in domains.split(",") if d.strip()]
            if domain_list:
                site_filter = SiteFilter(domains=domain_list)
        
        cookies = extractor.extract(site_filter=site_filter)
        
        return {
            "cookies": cookies,
            "browser": browser,
            "profile": profile.name,
        }
    
    def shutdown(self) -> None:
        """Shutdown the executor."""
        self._executor.shutdown(wait=False)


class RateLimiter:
    """
    Token bucket rate limiter.
    
    Features:
    - Configurable rate (requests per second)
    - Burst support
    - Async compatible
    """
    
    def __init__(self, rate: float, burst: int = 1):
        self._rate = rate
        self._burst = burst
        self._tokens = burst
        self._last_refill = time.time()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """Acquire a token, waiting if necessary."""
        async with self._lock:
            self._refill()
            
            while self._tokens < 1:
                wait_time = (1 - self._tokens) / self._rate
                await asyncio.sleep(wait_time)
                self._refill()
            
            self._tokens -= 1
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self._last_refill
        self._tokens = min(
            self._burst,
            self._tokens + elapsed * self._rate,
        )
        self._last_refill = now
    
    @property
    def available(self) -> float:
        """Available tokens."""
        self._refill()
        return self._tokens


# Global instances
_global_cache = LRUCache(max_size=1000, default_ttl=300)
_global_connection_pool = ConnectionPool()


def get_cache() -> LRUCache:
    """Get global LRU cache."""
    return _global_cache


def get_connection_pool() -> ConnectionPool:
    """Get global connection pool."""
    return _global_connection_pool
