"""
Tokenade Proxy Server - Local fingerprint-matched proxy.

Two proxy implementations:
1. CDPProxy (recommended): Playwright-based, no URL rewriting needed
2. TokenadeProxy (legacy): SW-based reverse proxy with URL rewriting

Plus upstream proxy rotation:
3. ProxyPool/ProxyRotator: provider-agnostic proxy rotation with health checking

Plus residential proxy support:
4. ResidentialProxyPool: geo-matched, ASN-validated residential proxies
"""

from tokenade.core.proxy.cdp_proxy import CDPProxy, CDPProxyConfig
from tokenade.core.proxy.rotation import (
    ProxyEntry,
    ProxyPool,
    ProxyRotator,
    RotationStrategy,
)
from tokenade.core.proxy.residential import (
    ResidentialProxyConfig,
    ResidentialProxyPool,
    ProxyHealth,
    SessionAwareProxy,
    create_residential_proxy,
)

__all__ = [
    "CDPProxy",
    "CDPProxyConfig",
    "ProxyEntry",
    "ProxyPool",
    "ProxyRotator",
    "RotationStrategy",
    "ResidentialProxyConfig",
    "ResidentialProxyPool",
    "ProxyHealth",
    "SessionAwareProxy",
    "create_residential_proxy",
]
from tokenade.core.proxy.provider import ProxyProviderError, ProxyProviderResolver, ResolvedProxy, normalize_proxy_result

__all__ = [
    "ProxyProviderError",
    "ProxyProviderResolver",
    "ResolvedProxy",
    "normalize_proxy_result",
]
