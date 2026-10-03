"""
Live-browser oracle - Answer scalar probes from a real page on the origin.

A headless Chromium page evaluates allowlisted probe expressions on demand,
so answers are the ORIGIN device's live values (not export-time snapshots).
Render-readback probes are deliberately absent from PROBE_JS — they are never
answered remotely (plan doc §3.2); only scalar/metadata probes are listed.

Scalar answers are cached (default 5 min TTL): they don't change mid-session
and caching keeps per-query cost near zero. stop() closes the browser.
"""

import logging
import time
from typing import Any, Dict, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# method -> JS expression evaluated in a blank origin page. Everything here
# must be JSON-serializable and side-effect free.
PROBE_JS: Dict[str, str] = {
    "navigator.userAgent": "navigator.userAgent",
    "navigator.platform": "navigator.platform",
    "navigator.language": "navigator.language",
    "navigator.languages": "Array.from(navigator.languages || [])",
    "navigator.hardwareConcurrency": "navigator.hardwareConcurrency",
    "navigator.deviceMemory": "navigator.deviceMemory",
    "navigator.maxTouchPoints": "navigator.maxTouchPoints",
    "navigator.webdriver": "navigator.webdriver",
    "navigator.plugins": ("Array.from(navigator.plugins || []).map(p => "
                          "({name: p.name, filename: p.filename}))"),
    "screen.width": "screen.width",
    "screen.height": "screen.height",
    "screen.colorDepth": "screen.colorDepth",
    "screen.availWidth": "screen.availWidth",
    "screen.availHeight": "screen.availHeight",
    "window.devicePixelRatio": "window.devicePixelRatio",
    "window.innerWidth": "window.innerWidth",
    "window.innerHeight": "window.innerHeight",
    "Intl.timeZone": "Intl.DateTimeFormat().resolvedOptions().timeZone",
    "Intl.locale": "Intl.NumberFormat().resolvedOptions().locale",
    "webgl.vendor": """(() => {
        const c = document.createElement('canvas');
        const gl = c.getContext('webgl');
        if (!gl) return '';
        const ext = gl.getExtension('WEBGL_debug_renderer_info');
        return ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : '';
    })()""",
    "webgl.renderer": """(() => {
        const c = document.createElement('canvas');
        const gl = c.getContext('webgl');
        if (!gl) return '';
        const ext = gl.getExtension('WEBGL_debug_renderer_info');
        return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : '';
    })()""",
    "fonts.list": """(() => {
        const test = ['Arial', 'Times New Roman', 'Courier New', 'Verdana',
                      'Georgia', 'Comic Sans MS', 'Trebuchet MS', 'Segoe UI',
                      'Calibri', 'Consolas', 'Tahoma', 'Helvetica'];
        const probe = document.createElement('span');
        probe.style.fontSize = '72px';
        probe.textContent = 'mmmmmmmmmmlli';
        document.body.appendChild(probe);
        const base = {};
        for (const generic of ['monospace', 'serif', 'sans-serif']) {
            probe.style.fontFamily = generic;
            base[generic] = probe.offsetWidth;
        }
        const present = [];
        for (const font of test) {
            for (const generic of ['monospace', 'serif', 'sans-serif']) {
                probe.style.fontFamily = `'${font}',${generic}`;
                if (probe.offsetWidth !== base[generic]) { present.push(font); break; }
            }
        }
        probe.remove();
        return present;
    })()""",
}


class LiveBrowserOracle:
    """Headless-Chromium oracle for allowlisted scalar probes."""

    def __init__(
        self,
        allowlist=None,
        cache_ttl_s: float = 300.0,
        headless: bool = True,
    ):
        from tokenade.core.session_runtime.plan import ORACLE_ALLOWLIST

        self.allowlist: Set[str] = set(allowlist or ORACLE_ALLOWLIST)
        self.cache_ttl_s = cache_ttl_s
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._page = None
        self._cache: Dict[str, Tuple[Any, float]] = {}

    # -- lifecycle --

    def start(self) -> None:
        """Launch headless Chromium (raises if browsers aren't installed)."""
        if self._page is not None:
            return
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._page = self._browser.new_page()
        logger.info("live oracle browser started")

    def stop(self) -> None:
        """Close browser (cache survives for degraded reads)."""
        for handle in (self._browser, self._playwright):
            if handle is not None:
                try:
                    handle.close() if hasattr(handle, "close") else handle.stop()
                except Exception:
                    pass
        self._browser = None
        self._page = None
        self._playwright = None

    @property
    def running(self) -> bool:
        """Whether the browser is currently up."""
        return self._page is not None

    # -- queries --

    def answer(self, method: str) -> Tuple[Any, Optional[str]]:
        """Answer one probe: (value, None) or (None, error). Deny-by-default."""
        if method not in self.allowlist:
            return None, f"denied: {method}"
        probe = PROBE_JS.get(method)
        if probe is None:
            return None, f"unknown: {method}"
        cached = self._cache.get(method)
        if cached is not None and (time.time() - cached[1]) < self.cache_ttl_s:
            return cached[0], None
        if self._page is None:
            return None, "oracle offline"
        try:
            value = self._page.evaluate(f"() => ({probe})")
        except Exception as exc:
            return None, f"eval failed: {exc}"
        self._cache[method] = (value, time.time())
        return value, None
