"""
Tokenade Proxy Server - Local fingerprint-matched proxy.

Two proxy implementations:
1. CDPProxy (recommended): Playwright-based, no URL rewriting needed
2. TokenadeProxy (legacy): SW-based reverse proxy with URL rewriting

Plus upstream proxy rotation:
3. ProxyPool/ProxyRotator: provider-agnostic proxy rotation with health checking
"""

from tokenade.core.proxy.cdp_proxy import CDPProxy, CDPProxyConfig
from tokenade.core.proxy.rotation import (
    ProxyEntry,
    ProxyPool,
    ProxyRotator,
    RotationStrategy,
)

__all__ = [
    "CDPProxy",
    "CDPProxyConfig",
    "ProxyEntry",
    "ProxyPool",
    "ProxyRotator",
    "RotationStrategy",
]
