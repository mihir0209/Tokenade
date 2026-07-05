"""
Backward-compatible wrapper — imports from stealth/launcher.py.

This file exists for backward compatibility. All new code should use:
    from tokenade.core.browser.stealth.launcher import SystemBrowserLauncher
"""

import platform as platform  # noqa: F811 — re-export for test compatibility

from tokenade.core.browser.stealth.launcher import (  # noqa: F401
    SystemBrowserLauncher,
    BrowserProcess,
    BrowserLaunchConfig,
)

__all__ = ["SystemBrowserLauncher", "BrowserProcess", "BrowserLaunchConfig"]
