"""
Tokenade Stealth — unified stealth browser management.

This package consolidates all stealth-related functionality:
- manager.py — JavaScript injection patches (StealthManager)
- launcher.py — System browser launcher with CDP (SystemBrowserLauncher)
- cloak.py — CloakBrowser integration (C++ source-level patches)
- backend.py — Auto-detection of best available backend

Backward-compatible imports are provided so existing code continues to work.
"""

# Backward-compatible imports from stealth.py
from tokenade.core.browser.stealth.manager import (
    StealthConfig,
    StealthManager,
    build_stealth_script,
    generate_canvas_seed,
    get_canvas_consistency_script,
    get_session_aging_script,
)

# Backward-compatible imports from undetectable.py
from tokenade.core.browser.stealth.launcher import (
    SystemBrowserLauncher,
    BrowserProcess,
    BrowserLaunchConfig,
)

# Backward-compatible imports from cloak.py
from tokenade.core.browser.stealth.cloak import (
    CloakBrowserBackend,
    is_cloakbrowser_available,
    is_binary_installed,
    get_binary_info,
    ensure_binary,
)

# Backend auto-detection
from tokenade.core.browser.stealth.backend import (
    get_stealth_backend_name,
    get_stealth_script,
    launch_stealth_browser,
)

__all__ = [
    # Manager
    "StealthConfig",
    "StealthManager",
    "build_stealth_script",
    "generate_canvas_seed",
    "get_canvas_consistency_script",
    "get_session_aging_script",
    # Launcher
    "SystemBrowserLauncher",
    "BrowserProcess",
    "BrowserLaunchConfig",
    # CloakBrowser
    "CloakBrowserBackend",
    "is_cloakbrowser_available",
    "is_binary_installed",
    "get_binary_info",
    "ensure_binary",
    # Backend
    "get_stealth_backend_name",
    "get_stealth_script",
    "launch_stealth_browser",
]
