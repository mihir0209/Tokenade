"""
Backward-compatible wrapper — imports from stealth/cloak.py.

This file exists for backward compatibility. All new code should use:
    from tokenade.core.browser.stealth.cloak import CloakBrowserBackend
"""

from tokenade.core.browser.stealth.cloak import (  # noqa: F401
    CloakBrowserBackend,
    is_cloakbrowser_available,
    is_binary_installed,
    get_binary_info,
    ensure_binary,
    get_stealth_backend_name,
)

__all__ = [
    "CloakBrowserBackend",
    "is_cloakbrowser_available",
    "is_binary_installed",
    "get_binary_info",
    "ensure_binary",
    "get_stealth_backend_name",
]
