"""
Fingerprint Injector - Injects stealth scripts into browser.
"""

import logging
from typing import Dict, Any

from .stealth import StealthScriptBuilder
from .manager import BrowserFingerprint

logger = logging.getLogger(__name__)


def inject_stealth_script(browser_manager, fingerprint: BrowserFingerprint, level: str = "maximum") -> bool:
    """
    Inject stealth script into browser.

    Args:
        browser_manager: Browser manager with evaluate() and add_init_script support
        fingerprint: Fingerprint data to spoof
        level: Stealth level (basic, advanced, maximum)

    Returns:
        True if injection successful
    """
    try:
        builder = StealthScriptBuilder(fingerprint)
        script = builder.build(level)

        # Try add_init_script first (Playwright)
        if hasattr(browser_manager, '_context') and browser_manager._context:
            try:
                browser_manager._context.add_init_script(script)
                logger.info("Stealth script injected via add_init_script")
                return True
            except Exception as e:
                logger.warning(f"add_init_script failed: {e}")

        # Fallback: evaluate in page
        if hasattr(browser_manager, 'evaluate'):
            browser_manager.evaluate(f"() => {{ {script} }}")
            logger.info("Stealth script injected via evaluate")
            return True

        logger.error("No injection method available")
        return False

    except Exception as e:
        logger.error(f"Failed to inject stealth script: {e}")
        return False


def validate_injection(browser_manager) -> Dict[str, Any]:
    """
    Verify spoofing is active by checking overridden APIs.

    Args:
        browser_manager: Browser manager with evaluate()

    Returns:
        Validation results dictionary
    """
    script = """() => ({
        webdriver: navigator.webdriver,
        userAgent: navigator.userAgent,
        platform: navigator.platform,
        hardwareConcurrency: navigator.hardwareConcurrency,
        deviceMemory: navigator.deviceMemory,
        screenWidth: screen.width,
        screenHeight: screen.height,
        devicePixelRatio: window.devicePixelRatio,
        pluginsLength: navigator.plugins.length,
        chromeRuntime: !!window.chrome?.runtime
    })"""

    try:
        result = browser_manager.evaluate(script)
        return {
            "webdriver_undefined": result.get("webdriver") is None,
            "user_agent": result.get("userAgent", ""),
            "platform": result.get("platform", ""),
            "hardware_concurrency": result.get("hardwareConcurrency", 0),
            "screen_width": result.get("screenWidth", 0),
            "screen_height": result.get("screenHeight", 0),
            "device_pixel_ratio": result.get("devicePixelRatio", 1.0),
            "plugins_count": result.get("pluginsLength", 0),
            "chrome_runtime_present": result.get("chromeRuntime", False),
            "valid": result.get("webdriver") is None
        }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e)
        }
