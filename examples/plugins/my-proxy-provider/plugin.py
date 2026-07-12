"""Example: Proxy Provider Plugin

Provides rotating residential proxies for session operations.

Install:
    cp -r my-proxy-provider ~/.tokenade/plugins/my-proxy-provider
    tokenade plugin list
"""

from typing import Optional
from tokenade.plugin.base import ProxyProviderPlugin


class MyProxyProviderPlugin(ProxyProviderPlugin):
    """Example proxy provider — returns a sticky proxy URL."""

    name = "my-proxy-provider"
    version = "1.0.0"
    description = "Example proxy provider plugin"

    def get_proxy(self, session_id: str) -> Optional[dict]:
        """Return proxy configuration for a session."""
        return {
            "server_url": f"socks5://user:pass@proxy.example.com:1080",
            "sticky": True,
            "session_id": session_id,
        }

    def release_proxy(self, session_id: str) -> None:
        """Release a sticky proxy allocation."""
        pass
