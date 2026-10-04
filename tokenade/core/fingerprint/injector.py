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


WORKER_PARITY_SCRIPT = """() => (async () => {
    const main = {
        userAgent: navigator.userAgent,
        platform: navigator.platform,
        hardwareConcurrency: navigator.hardwareConcurrency,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        languages: Array.from(navigator.languages || []),
    };
    let worker = null;
    try {
        const code = `
            self.postMessage({
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                hardwareConcurrency: navigator.hardwareConcurrency,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                languages: (navigator.languages ? Array.from(navigator.languages) : []),
            });
        `;
        const w = new Worker(URL.createObjectURL(
            new Blob([code], {type: 'application/javascript'})));
        worker = await Promise.race([
            new Promise((resolve) => { w.onmessage = (e) => resolve(e.data); }),
            new Promise((_, reject) => setTimeout(
                () => reject(new Error('worker timeout')), 5000)),
        ]);
        w.terminate();
    } catch (e) {
        return {main: main, worker: null, worker_error: String(e)};
    }
    return {main: main, worker: worker, worker_error: null};
})()"""


def validate_worker_parity(browser_manager) -> Dict[str, Any]:
    """
    Compare main-thread vs Web Worker fingerprint reads.

    Detectors re-probe identity inside Workers precisely because JS spoofs
    (add_init_script) do not run there. This check makes the gap VISIBLE per
    load instead of silent: status is "match" (native tier holds),
    "mismatch" (lists diverged fields — expected under JS spoofing), or
    "unknown" (backend couldn't evaluate). Never raises.
    """
    evaluate = getattr(browser_manager, "evaluate", None)
    if not callable(evaluate):
        return {"status": "unknown", "reason": "backend has no evaluate()"}
    try:
        result = evaluate(WORKER_PARITY_SCRIPT)
    except Exception as e:
        return {"status": "unknown", "reason": f"evaluate failed: {e}"}
    try:
        main = dict(result.get("main", {}) or {})
        worker = result.get("worker")
    except (AttributeError, TypeError, ValueError):
        return {"status": "unknown", "reason": "unreadable evaluate result"}
    if not isinstance(worker, dict):
        return {"status": "unknown", "reason": result.get("worker_error") or "no worker read",
                "main": main}
    mismatches = sorted(
        key for key in set(main) | set(worker) if main.get(key) != worker.get(key)
    )
    if mismatches:
        return {"status": "mismatch", "mismatches": mismatches,
                "main": main, "worker": worker}
    return {"status": "match", "probes": sorted(main), "main": main}


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
