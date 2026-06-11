"""
Tokenade Proxy Server - Local fingerprint-matched proxy.

Two proxy implementations:
1. CDPProxy (recommended): Playwright-based, no URL rewriting needed
2. TokenadeProxy (legacy): SW-based reverse proxy with URL rewriting
"""

from tokenade.core.proxy.cdp_proxy import CDPProxy, CDPProxyConfig

__all__ = ["CDPProxy", "CDPProxyConfig"]
