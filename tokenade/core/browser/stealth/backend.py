"""
Stealth backend auto-detection.

Selects the best available stealth backend:
1. CloakBrowser (C++ source-level patches) — best
2. JS injection patches (StealthManager) — fallback

Usage:
    from tokenade.core.browser.stealth.backend import get_stealth_backend

    backend = get_stealth_backend()
    browser = backend.launch(headless=True)
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def get_stealth_backend_name() -> str:
    """Return the name of the active stealth backend.

    Returns:
        "cloakbrowser" if binary available, "playwright" otherwise.
    """
    try:
        from tokenade.core.browser.stealth.cloak import is_binary_installed
        if is_binary_installed():
            return "cloakbrowser"
    except Exception:
        pass
    return "playwright"


def is_cloakbrowser_available() -> bool:
    """Check if CloakBrowser is ready to use."""
    try:
        from tokenade.core.browser.stealth.cloak import is_cloakbrowser_available as _check
        return _check()
    except Exception:
        return False


def get_stealth_script() -> str:
    """Get the JavaScript stealth injection script.

    Returns the CloakBrowser stealth script if available,
    otherwise falls back to the JS patch manager.
    """
    try:
        from tokenade.core.browser.stealth.manager import StealthManager
        sm = StealthManager()
        return sm.get_combined_script()
    except Exception:
        return ""


def launch_stealth_browser(
    headless: bool = True,
    proxy: Optional[str] = None,
    humanize: bool = False,
    geoip: bool = False,
    **kwargs,
) -> Any:
    """Launch a stealth browser using the best available backend.

    Returns:
        Playwright Browser object (compatible with all Playwright code).
    """
    # Try CloakBrowser first
    try:
        from tokenade.core.browser.stealth.cloak import CloakBrowserBackend
        backend = CloakBrowserBackend()
        if backend.is_available():
            return backend.launch(
                headless=headless,
                proxy=proxy,
                humanize=humanize,
                geoip=geoip,
                **kwargs,
            )
    except Exception as e:
        logger.debug(f"CloakBrowser launch failed: {e}")

    # Fallback to Playwright + JS patches
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=headless)

        # Inject stealth scripts
        script = get_stealth_script()
        if script:
            context = browser.new_context()
            context.add_init_script(script)

        return browser
    except Exception as e:
        logger.error(f"Failed to launch stealth browser: {e}")
        raise
