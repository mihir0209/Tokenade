"""
Tokenade Proxy Manager — coordinates proxy usage across all commands.

Provides a unified interface for sticky and rotating proxies.
Supports plugin-based proxy providers with fallback to CLI --proxy flag.

Usage:
    from tokenade.core.proxy.manager import ProxyManager, ProxyConfig

    mgr = ProxyManager()
    proxy = mgr.get_proxy(session_id="gmail.tokenade", mode="sticky")
    if proxy:
        browser = launch(proxy=proxy.server_url)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    """Standard proxy configuration.

    All proxy operations return ProxyConfig, not raw dicts.
    This ensures consistent proxy handling across commands.
    """

    host: str
    port: int
    protocol: str = "http"
    username: Optional[str] = None
    password: Optional[str] = None
    session_id: Optional[str] = None
    country: Optional[str] = None

    @property
    def server_url(self) -> str:
        """Return proxy URL string for browser --proxy-server flag.

        Format: protocol://[user:pass@]host:port
        """
        auth = ""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"
        return f"{self.protocol}://{auth}{self.host}:{self.port}"

    @property
    def is_authenticated(self) -> bool:
        return bool(self.username and self.password)

    @classmethod
    def from_url(cls, url: str) -> Optional["ProxyConfig"]:
        """Parse proxy URL into ProxyConfig.

        Supports:
            http://host:port
            http://user:pass@host:port
            socks5://host:port
            socks5://user:pass@host:port
        """
        if not url:
            return None

        # Parse protocol
        protocol = "http"
        if url.startswith("socks5://"):
            protocol = "socks5"
            url = url[9:]
        elif url.startswith("http://"):
            url = url[7:]
        elif url.startswith("https://"):
            protocol = "https"
            url = url[8:]

        # Parse auth
        username = None
        password = None
        if "@" in url:
            auth_part, url = url.rsplit("@", 1)
            if ":" in auth_part:
                username, password = auth_part.split(":", 1)

        # Parse host:port
        if ":" in url:
            host, port_str = url.rsplit(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                port = 8080
        else:
            host = url
            port = 8080

        return cls(
            host=host,
            port=port,
            protocol=protocol,
            username=username,
            password=password,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "protocol": self.protocol,
            "username": self.username,
            "password": "***" if self.password else None,
            "session_id": self.session_id,
            "country": self.country,
        }


class ProxyManager:
    """Coordinates proxy usage across all commands.

    Priority order:
    1. ProxyProviderPlugin (if installed and configured)
    2. --proxy CLI flag
    3. config.upstream_proxy

    Usage:
        mgr = ProxyManager()
        proxy = mgr.get_proxy(session_id="gmail.tokenade", mode="sticky")
    """

    def __init__(
        self,
        cli_proxy: Optional[str] = None,
        config_proxy: Optional[str] = None,
        plugin: Optional[Any] = None,
    ):
        self._cli_proxy = cli_proxy
        self._config_proxy = config_proxy
        self._plugin = plugin
        self._session_proxies: Dict[str, ProxyConfig] = {}

    @property
    def has_plugin(self) -> bool:
        return self._plugin is not None

    def register_plugin(self, plugin: Any) -> None:
        """Register a proxy provider plugin."""
        self._plugin = plugin
        logger.info(f"Registered proxy plugin: {plugin.name}")

    def get_proxy(
        self,
        session_id: Optional[str] = None,
        mode: str = "sticky",
    ) -> Optional[ProxyConfig]:
        """Get a proxy for the given session.

        Args:
            session_id: Session ID for sticky proxy binding.
            mode: "sticky" (same IP for session) or "rotating" (different IP).

        Returns:
            ProxyConfig or None if no proxy available.
        """
        # Try plugin first
        if self._plugin:
            proxy = self._get_from_plugin(session_id, mode)
            if proxy:
                return proxy

        # Fallback to CLI proxy
        if self._cli_proxy:
            proxy = ProxyConfig.from_url(self._cli_proxy)
            if proxy:
                if mode == "sticky" and session_id:
                    proxy.session_id = session_id
                return proxy

        # Fallback to config proxy
        if self._config_proxy:
            proxy = ProxyConfig.from_url(self._config_proxy)
            if proxy:
                if mode == "sticky" and session_id:
                    proxy.session_id = session_id
                return proxy

        return None

    def rotate(self, session_id: Optional[str] = None) -> Optional[ProxyConfig]:
        """Rotate to a new proxy.

        For sticky proxy: returns new proxy with new session binding.
        For rotating proxy: returns new proxy.
        """
        if self._plugin:
            try:
                result = self._plugin.rotate(session_id)
                if result and result.success:
                    data = result.data
                    proxy = ProxyConfig(
                        host=data.get("host", ""),
                        port=data.get("port", 0),
                        protocol=data.get("protocol", "http"),
                        username=data.get("username"),
                        password=data.get("password"),
                        session_id=session_id,
                    )
                    if session_id:
                        self._session_proxies[session_id] = proxy
                    return proxy
            except Exception as e:
                logger.warning(f"Plugin rotation failed: {e}")

        return None

    def _get_from_plugin(
        self, session_id: Optional[str], mode: str
    ) -> Optional[ProxyConfig]:
        """Get proxy from registered plugin."""
        try:
            if mode == "sticky" and session_id:
                # Check if we already have a proxy for this session
                if session_id in self._session_proxies:
                    return self._session_proxies[session_id]

                result = self._plugin.get_sticky_proxy(session_id)
            else:
                result = self._plugin.get_rotating_proxy()

            if result and result.success:
                data = result.data
                proxy = ProxyConfig(
                    host=data.get("host", ""),
                    port=data.get("port", 0),
                    protocol=data.get("protocol", "http"),
                    username=data.get("username"),
                    password=data.get("password"),
                    session_id=session_id,
                    country=data.get("country"),
                )
                if mode == "sticky" and session_id:
                    self._session_proxies[session_id] = proxy
                return proxy

        except Exception as e:
            logger.warning(f"Plugin proxy failed: {e}")

        return None

    def check_health(self, proxy: ProxyConfig) -> bool:
        """Check if a proxy is healthy."""
        if self._plugin:
            try:
                result = self._plugin.check_health(proxy.to_dict())
                if result and result.success:
                    return result.data.get("healthy", True)
            except Exception:
                pass
        return True  # Assume healthy if no plugin

    def get_config_schema(self) -> Dict[str, Any]:
        """Return config schema for proxy settings."""
        return {
            "upstream_proxy": {
                "type": "string",
                "required": False,
                "description": "Default proxy URL (e.g., http://host:port)",
            },
            "proxy_mode": {
                "type": "string",
                "required": False,
                "default": "sticky",
                "description": "Default proxy mode (sticky or rotating)",
            },
        }
