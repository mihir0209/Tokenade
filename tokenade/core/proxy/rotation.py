"""
Proxy Rotation — provider-agnostic upstream proxy pool with health checking.

Supports any HTTP or SOCKS5 proxy. Users supply their own credentials.
No provider names are embedded in this module.

Rotation strategies:
- round-robin: cycle through proxies in order
- random: pick a random proxy each time
- health-weighted: prefer healthy proxies (default)
- sticky: always return the same proxy for a given session ID
"""

import hashlib
import logging
import random
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class RotationStrategy(Enum):
    ROUND_ROBIN = "round-robin"
    RANDOM = "random"
    HEALTH_WEIGHTED = "health-weighted"
    STICKY = "sticky"


@dataclass
class ProxyEntry:
    """A single upstream proxy."""
    url: str  # e.g. "socks5://user:pass@host:port" or "http://host:port"
    host: str = ""
    port: int = 0
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: str = "http"
    country: Optional[str] = None
    tag: Optional[str] = None
    # Health state
    healthy: bool = True
    last_check: float = 0.0
    last_success: float = 0.0
    last_failure: float = 0.0
    consecutive_failures: int = 0
    total_successes: int = 0
    total_failures: int = 0
    avg_latency_ms: float = 0.0

    def __post_init__(self):
        if not self.host or not self.port:
            self._parse_url()

    def _parse_url(self):
        """Parse host, port, credentials from URL."""
        try:
            parsed = urlparse(self.url)
            self.protocol = parsed.scheme or "http"
            self.host = parsed.hostname or ""
            self.port = parsed.port or 0
            if parsed.username:
                self.username = parsed.username
            if parsed.password:
                self.password = parsed.password
        except Exception:
            pass

    @property
    def host_port(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def server_url(self) -> str:
        """URL suitable for browser --proxy-server flag."""
        return self.url

    def record_success(self, latency_ms: float = 0.0):
        """Record a successful proxy request."""
        self.healthy = True
        self.last_success = time.time()
        self.consecutive_failures = 0
        self.total_successes += 1
        # Update rolling average latency
        n = self.total_successes
        self.avg_latency_ms = ((self.avg_latency_ms * (n - 1)) + latency_ms) / n

    def record_failure(self):
        """Record a failed proxy request."""
        self.last_failure = time.time()
        self.consecutive_failures += 1
        self.total_failures += 1
        # Mark unhealthy after 3 consecutive failures
        if self.consecutive_failures >= 3:
            self.healthy = False
            logger.warning(f"Proxy {self.host_port} marked unhealthy after {self.consecutive_failures} consecutive failures")

    @property
    def success_rate(self) -> float:
        total = self.total_successes + self.total_failures
        if total == 0:
            return 1.0
        return self.total_successes / total

    def to_dict(self) -> Dict:
        return {
            "url": self.url,
            "host": self.host,
            "port": self.port,
            "protocol": self.protocol,
            "country": self.country,
            "tag": self.tag,
            "healthy": self.healthy,
            "success_rate": round(self.success_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
        }


class ProxyPool:
    """Manages a pool of upstream proxies."""

    def __init__(self, proxies: Optional[List[ProxyEntry]] = None):
        self._proxies: List[ProxyEntry] = proxies or []
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        return len(self._proxies)

    @property
    def healthy_count(self) -> int:
        return sum(1 for p in self._proxies if p.healthy)

    def add(self, proxy: ProxyEntry):
        with self._lock:
            self._proxies.append(proxy)

    def remove(self, host_port: str):
        with self._lock:
            self._proxies = [p for p in self._proxies if p.host_port != host_port]

    def get_all(self) -> List[ProxyEntry]:
        with self._lock:
            return list(self._proxies)

    def get_healthy(self) -> List[ProxyEntry]:
        with self._lock:
            return [p for p in self._proxies if p.healthy]

    def get_by_index(self, index: int) -> Optional[ProxyEntry]:
        with self._lock:
            if 0 <= index < len(self._proxies):
                return self._proxies[index]
            return None

    def mark_checked(self, host_port: str, healthy: bool, latency_ms: float = 0.0):
        """Update health status after a health check."""
        with self._lock:
            for p in self._proxies:
                if p.host_port == host_port:
                    p.last_check = time.time()
                    if healthy:
                        p.record_success(latency_ms)
                    else:
                        p.record_failure()
                    break

    @classmethod
    def from_urls(cls, urls: List[str], **defaults) -> "ProxyPool":
        """Create pool from a list of proxy URLs.

        Each URL should be: protocol://[user:pass@]host:port
        Supported protocols: http, https, socks5
        """
        pool = cls()
        for url in urls:
            url = url.strip()
            if not url or url.startswith("#"):
                continue
            entry = ProxyEntry(url=url, **defaults)
            if entry.host and entry.port:
                pool.add(entry)
        return pool

    @classmethod
    def from_file(cls, filepath: str) -> "ProxyPool":
        """Load proxies from a text file. One proxy per line.

        Supported formats:
          - protocol://[user:pass@]host:port
          - host:port:user:pass (colon-separated, defaults to http)
          - host:port (no auth, defaults to http)
          - Lines starting with # are comments
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Proxy file not found: {filepath}")

        pool = cls()
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Check if it's a URL format
            if "://" in line:
                entry = ProxyEntry(url=line)
                if entry.host and entry.port:
                    pool.add(entry)
                continue

            # Colon-separated format: host:port[:user:pass]
            parts = line.split(":")
            if len(parts) >= 2:
                host = parts[0]
                try:
                    port = int(parts[1])
                except ValueError:
                    logger.warning(f"Invalid proxy line (bad port): {line}")
                    continue

                url = f"http://{host}:{port}"
                username = parts[2] if len(parts) > 2 else None
                password = parts[3] if len(parts) > 3 else None

                if username and password:
                    url = f"http://{username}:{password}@{host}:{port}"

                pool.add(ProxyEntry(url=url, username=username, password=password))

        return pool

    def to_dict(self) -> Dict:
        return {
            "size": self.size,
            "healthy": self.healthy_count,
            "proxies": [p.to_dict() for p in self._proxies],
        }


class ProxyRotator:
    """Selects the next proxy from a pool using a rotation strategy."""

    def __init__(
        self,
        pool: ProxyPool,
        strategy: RotationStrategy = RotationStrategy.HEALTH_WEIGHTED,
        sticky_seed: Optional[str] = None,
    ):
        self.pool = pool
        self.strategy = strategy
        self._index = 0
        self._lock = threading.Lock()
        self._sticky_seed = sticky_seed

    def next(self, session_id: Optional[str] = None) -> Optional[ProxyEntry]:
        """Get the next proxy from the pool.

        Args:
            session_id: For sticky strategy, ensures same proxy for same session_id

        Returns:
            Next ProxyEntry or None if pool is empty
        """
        proxies = self.pool.get_healthy()
        if not proxies:
            # Fallback: try all proxies if none are healthy
            proxies = self.pool.get_all()
        if not proxies:
            return None

        with self._lock:
            if self.strategy == RotationStrategy.ROUND_ROBIN:
                proxy = proxies[self._index % len(proxies)]
                self._index += 1
                return proxy

            elif self.strategy == RotationStrategy.RANDOM:
                return random.choice(proxies)

            elif self.strategy == RotationStrategy.HEALTH_WEIGHTED:
                # Weight by success rate and inversely by latency
                weights = []
                for p in proxies:
                    w = p.success_rate + 0.01  # avoid zero weight
                    if p.avg_latency_ms > 0:
                        w /= (1 + p.avg_latency_ms / 1000.0)
                    weights.append(w)
                return random.choices(proxies, weights=weights, k=1)[0]

            elif self.strategy == RotationStrategy.STICKY:
                seed = session_id or self._sticky_seed or "default"
                h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
                idx = h % len(proxies)
                return proxies[idx]

        return None

    def record_success(self, proxy: ProxyEntry, latency_ms: float = 0.0):
        """Record successful use of a proxy."""
        self.pool.mark_checked(proxy.host_port, True, latency_ms)

    def record_failure(self, proxy: ProxyEntry):
        """Record failed use of a proxy."""
        self.pool.mark_checked(proxy.host_port, False)

    @staticmethod
    def health_check(proxy: ProxyEntry, timeout: float = 10.0) -> Tuple[bool, float]:
        """Check if a proxy is reachable.

        Returns:
            (is_healthy, latency_ms)
        """
        import socket
        import ssl

        start = time.time()
        try:
            if proxy.protocol.startswith("socks"):
                # SOCKS5 health check — try TCP connect to the proxy itself
                with socket.create_connection((proxy.host, proxy.port), timeout=timeout) as sock:
                    # Send SOCKS5 greeting
                    sock.send(b"\x05\x01\x00")
                    resp = sock.recv(2)
                    if len(resp) >= 2 and resp[0] == 0x05:
                        latency_ms = (time.time() - start) * 1000
                        return True, latency_ms
                latency_ms = (time.time() - start) * 1000
                return False, latency_ms
            else:
                # HTTP(S) proxy health check — try connecting and sending HEAD
                with socket.create_connection((proxy.host, proxy.port), timeout=timeout) as sock:
                    # Send a simple HTTP request through the proxy
                    test_url = "http://httpbin.org/ip"
                    request = f"HEAD {test_url} HTTP/1.1\r\nHost: httpbin.org\r\nConnection: close\r\n\r\n"
                    sock.send(request.encode())
                    resp = sock.recv(1024)
                    latency_ms = (time.time() - start) * 1000
                    if b"200" in resp or b"403" in resp or b"407" in resp:
                        return True, latency_ms
                    return False, latency_ms
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            latency_ms = (time.time() - start) * 1000
            logger.debug(f"Health check failed for {proxy.host_port}: {e}")
            return False, latency_ms

    def check_health(self, timeout: float = 10.0) -> Dict[str, bool]:
        """Run health check on all proxies in the pool.

        Returns:
            Dict mapping host_port to healthy status
        """
        results = {}
        for proxy in self.pool.get_all():
            healthy, latency = self.health_check(proxy, timeout)
            self.pool.mark_checked(proxy.host_port, healthy, latency)
            results[proxy.host_port] = healthy
        return results
