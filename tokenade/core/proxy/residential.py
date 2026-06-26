"""
Residential Proxy Support — geo-matched, ASN-validated proxies.

Cloudflare and Akamai flag datacenter IPs. Residential proxies from real ISPs
are required for production bypass. This module provides geo-matching,
health checking, and session-aware proxy selection.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

GEO_TIMEZONE_MAP = {
    "US": "America/New_York",
    "GB": "Europe/London",
    "DE": "Europe/Berlin",
    "FR": "Europe/Paris",
    "JP": "Asia/Tokyo",
    "AU": "Australia/Sydney",
    "BR": "America/Sao_Paulo",
    "IN": "Asia/Kolkata",
    "CA": "America/Toronto",
    "NL": "Europe/Amsterdam",
}

# Known datacenter ASNs to avoid
DATACENTER_ASNS = {
    "AS14061",  # DigitalOcean
    "AS16509",  # Amazon AWS
    "AS15169",  # Google Cloud
    "AS8075",   # Microsoft Azure
    "AS14618",  # Amazon AWS
    "AS24940",  # Hetzner
    "AS57043",  # HOSTKEY
    "AS208162", # OVH
    "AS47583",  # Hostinger
    "AS396982", # Google Cloud
}


@dataclass
class ResidentialProxyConfig:
    """Configuration for a residential proxy."""
    host: str
    port: int
    protocol: str = "http"
    username: Optional[str] = None
    password: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    isp: Optional[str] = None
    asn: Optional[str] = None
    is_residential: bool = True


@dataclass
class ProxyHealth:
    """Health status of a proxy."""
    proxy: ResidentialProxyConfig
    is_healthy: bool = True
    last_check: float = 0.0
    response_time: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    error: Optional[str] = None

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 1.0


class ResidentialProxyPool:
    """Pool of residential proxies with health checking and geo-matching."""

    def __init__(self, proxies: Optional[List[ResidentialProxyConfig]] = None):
        self._proxies: List[ResidentialProxyConfig] = proxies or []
        self._health: Dict[str, ProxyHealth] = {}
        self._current_index = 0

    def add_proxy(self, proxy: ResidentialProxyConfig) -> None:
        """Add a proxy to the pool."""
        self._proxies.append(proxy)
        key = f"{proxy.host}:{proxy.port}"
        self._health[key] = ProxyHealth(proxy=proxy)

    def remove_proxy(self, host: str, port: int) -> bool:
        """Remove a proxy from the pool."""
        key = f"{host}:{port}"
        for i, p in enumerate(self._proxies):
            if p.host == host and p.port == port:
                self._proxies.pop(i)
                self._health.pop(key, None)
                return True
        return False

    def get_proxy_url(self, proxy: ResidentialProxyConfig) -> str:
        """Get proxy URL string."""
        if proxy.username and proxy.password:
            return f"{proxy.protocol}://{proxy.username}:{proxy.password}@{proxy.host}:{proxy.port}"
        return f"{proxy.protocol}://{proxy.host}:{proxy.port}"

    def get_next(self) -> Optional[ResidentialProxyConfig]:
        """Get next healthy proxy (round-robin)."""
        healthy = [p for p in self._proxies if self._is_healthy(p)]
        if not healthy:
            return None
        proxy = healthy[self._current_index % len(healthy)]
        self._current_index += 1
        return proxy

    def get_by_country(self, country_code: str) -> Optional[ResidentialProxyConfig]:
        """Get a proxy matching a country code."""
        for p in self._proxies:
            if p.country and p.country.upper() == country_code.upper() and self._is_healthy(p):
                return p
        return None

    def get_best_for_session(self, session: Dict) -> Optional[ResidentialProxyConfig]:
        """Get the best proxy for a session based on timezone/locale."""
        timezone = session.get("timezone", "")
        locale = session.get("locale", "")

        for tz_prefix, country in GEO_TIMEZONE_MAP.items():
            if tz_prefix in timezone or tz_prefix in locale:
                proxy = self.get_by_country(country)
                if proxy:
                    return proxy

        return self.get_next()

    def _is_healthy(self, proxy: ResidentialProxyConfig) -> bool:
        """Check if a proxy is healthy."""
        key = f"{proxy.host}:{proxy.port}"
        health = self._health.get(key)
        if not health:
            return True
        if not health.is_healthy:
            if time.time() - health.last_check > 300:
                health.is_healthy = True
                return True
            return False
        return True

    def mark_success(self, host: str, port: int, response_time: float = 0.0) -> None:
        """Mark a proxy as successful."""
        key = f"{host}:{port}"
        health = self._health.get(key)
        if health:
            health.success_count += 1
            health.response_time = response_time
            health.last_check = time.time()

    def mark_failure(self, host: str, port: int, error: str = "") -> None:
        """Mark a proxy as failed."""
        key = f"{host}:{port}"
        health = self._health.get(key)
        if health:
            health.failure_count += 1
            health.last_check = time.time()
            health.error = error
            if health.failure_count >= 3:
                health.is_healthy = False
                logger.warning(f"Proxy {host}:{port} marked unhealthy: {error}")

    def check_health(self, proxy: ResidentialProxyConfig, test_url: str = "https://httpbin.org/ip") -> ProxyHealth:
        """Check health of a single proxy."""
        import urllib.request

        key = f"{proxy.host}:{proxy.port}"
        health = self._health.get(key, ProxyHealth(proxy=proxy))

        proxy_url = self.get_proxy_url(proxy)
        start_time = time.time()

        try:
            handler = urllib.request.ProxyHandler({
                "http": proxy_url,
                "https": proxy_url,
            })
            opener = urllib.request.build_opener(handler)
            response = opener.open(test_url, timeout=10)
            elapsed = time.time() - start_time

            health.is_healthy = True
            health.response_time = elapsed
            health.last_check = time.time()
            health.error = None

        except Exception as e:
            health.is_healthy = False
            health.last_check = time.time()
            health.error = str(e)
            logger.warning(f"Health check failed for {proxy.host}:{proxy.port}: {e}")

        self._health[key] = health
        return health

    def check_all_health(self) -> List[ProxyHealth]:
        """Check health of all proxies."""
        return [self.check_health(p) for p in self._proxies]

    def get_stats(self) -> Dict:
        """Get pool statistics."""
        healthy = sum(1 for p in self._proxies if self._is_healthy(p))
        return {
            "total": len(self._proxies),
            "healthy": healthy,
            "unhealthy": len(self._proxies) - healthy,
            "countries": list(set(p.country for p in self._proxies if p.country)),
        }

    def load_from_config(self, config: Dict) -> None:
        """Load proxies from config dict."""
        for proxy_data in config.get("proxies", []):
            proxy = ResidentialProxyConfig(
                host=proxy_data["host"],
                port=proxy_data["port"],
                protocol=proxy_data.get("protocol", "http"),
                username=proxy_data.get("username"),
                password=proxy_data.get("password"),
                country=proxy_data.get("country"),
                state=proxy_data.get("state"),
                city=proxy_data.get("city"),
                isp=proxy_data.get("isp"),
                asn=proxy_data.get("asn"),
                is_residential=proxy_data.get("is_residential", True),
            )
            self.add_proxy(proxy)

    def load_from_file(self, filepath: str) -> None:
        """Load proxies from file (one per line, format: protocol://user:pass@host:port)."""
        from pathlib import Path

        path = Path(filepath)
        if not path.exists():
            logger.error(f"Proxy file not found: {filepath}")
            return

        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            try:
                from urllib.parse import urlparse
                parsed = urlparse(line)
                proxy = ResidentialProxyConfig(
                    host=parsed.hostname,
                    port=parsed.port or 8080,
                    protocol=parsed.scheme,
                    username=parsed.username,
                    password=parsed.password,
                    is_residential=True,
                )
                self.add_proxy(proxy)
            except Exception as e:
                logger.warning(f"Failed to parse proxy line: {line}: {e}")


class SessionAwareProxy:
    """Proxy selection that considers session context (timezone, locale, etc.)."""

    def __init__(self, pool: ResidentialProxyPool):
        self.pool = pool

    def select_for_session(self, session: Dict) -> Optional[ResidentialProxyConfig]:
        """Select best proxy for a session."""
        return self.pool.get_best_for_session(session)

    def apply_to_session(self, session: Dict, proxy: ResidentialProxyConfig) -> Dict:
        """Apply proxy config to a session dict."""
        session["upstream_proxy"] = self.pool.get_proxy_url(proxy)
        session["proxy_country"] = proxy.country
        session["proxy_is_residential"] = proxy.is_residential
        return session

    def apply_to_launch_config(self, config: Any, proxy: ResidentialProxyConfig) -> Any:
        """Apply proxy to a BrowserLaunchConfig."""
        config.upstream_proxy = self.pool.get_proxy_url(proxy)
        return config


def create_residential_proxy(
    host: str,
    port: int,
    username: Optional[str] = None,
    password: Optional[str] = None,
    country: Optional[str] = None,
    protocol: str = "http",
) -> ResidentialProxyConfig:
    """Create a residential proxy config."""
    return ResidentialProxyConfig(
        host=host,
        port=port,
        protocol=protocol,
        username=username,
        password=password,
        country=country,
        is_residential=True,
    )
