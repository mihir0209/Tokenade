"""
Tokenade Browser - System browser management and CDP connection.
"""

from tokenade.core.browser.undetectable import (
    SystemBrowserLauncher,
    BrowserProcess,
    BrowserLaunchConfig,
)

from tokenade.core.browser.cdp_connection import (
    CDPConnection,
    get_undetectable_stealth_script,
)

from tokenade.core.browser.patcher import (
    ChromePatcher,
    PatchResult,
)

__all__ = [
    "SystemBrowserLauncher",
    "BrowserProcess",
    "BrowserLaunchConfig",
    "CDPConnection",
    "get_undetectable_stealth_script",
    "ChromePatcher",
    "PatchResult",
]
