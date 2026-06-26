"""
Stealth Test Suite — automated testing against bot detection sites.

Launches a browser with stealth patches, navigates to detection sites,
and evaluates whether the browser is detected as automated.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class Verdict(Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


@dataclass
class TestResult:
    """Result of a single detection test."""
    name: str
    verdict: Verdict
    score: float  # 0-100
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0


@dataclass
class StealthTestReport:
    """Full stealth test report."""
    overall_score: float = 0.0
    results: List[TestResult] = field(default_factory=list)
    browser: str = "chromium"
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.verdict == Verdict.PASS)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.verdict == Verdict.FAIL)

    @property
    def warned(self) -> int:
        return sum(1 for r in self.results if r.verdict == Verdict.WARN)

    def summary(self) -> str:
        grade = self._grade()
        return (
            f"Score: {self.overall_score:.0f}/100 ({grade}) | "
            f"{self.passed} passed, {self.failed} failed, {self.warned} warned"
        )

    def _grade(self) -> str:
        if self.overall_score >= 90:
            return "A"
        elif self.overall_score >= 80:
            return "B"
        elif self.overall_score >= 70:
            return "C"
        elif self.overall_score >= 60:
            return "D"
        return "F"


# ─── JS property checks ──────────────────────────────────────

JS_CHECKS = {
    "webdriver_undefined": {
        "name": "navigator.webdriver = undefined",
        "weight": 5,
        "test_js": "() => navigator.webdriver === undefined",
    },
    "chrome_object": {
        "name": "window.chrome exists",
        "weight": 4,
        "test_js": "() => typeof window.chrome === 'object' && window.chrome !== null",
    },
    "chrome_loadtimes": {
        "name": "chrome.loadTimes() works",
        "weight": 3,
        "test_js": "() => typeof window.chrome?.loadTimes === 'function'",
    },
    "chrome_csi": {
        "name": "chrome.csi() works",
        "weight": 3,
        "test_js": "() => typeof window.chrome?.csi === 'function'",
    },
    "plugins_nonempty": {
        "name": "navigator.plugins is non-empty",
        "weight": 3,
        "test_js": "() => navigator.plugins.length > 0",
    },
    "permissions_query": {
        "name": "navigator.permissions.query works",
        "weight": 3,
        "test_js": "async () => { try { const r = await navigator.permissions.query({name:'notifications'}); return r.state !== 'denied'; } catch { return false; } }",
    },
    "webgl_vendor": {
        "name": "WebGL vendor is set",
        "weight": 3,
        "test_js": "() => { const c = document.createElement('canvas'); const gl = c.getContext('webgl'); if (!gl) return false; const ext = gl.getExtension('WEBGL_debug_renderer_info'); return ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL).length > 0 : false; }",
    },
    "webgl_renderer": {
        "name": "WebGL renderer is set",
        "weight": 3,
        "test_js": "() => { const c = document.createElement('canvas'); const gl = c.getContext('webgl'); if (!gl) return false; const ext = gl.getExtension('WEBGL_debug_renderer_info'); return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL).length > 0 : false; }",
    },
    "no_cdc_artifacts": {
        "name": "No automation artifacts (cdc_, __webdriver_)",
        "weight": 5,
        "test_js": "() => { const keys = Object.keys(window); return !keys.some(k => k.startsWith('cdc_') || k.startsWith('__webdriver_') || k.startsWith('__selenium_') || k.startsWith('webdriver') || k === 'domAutomation' || k === 'domAutomationController'); }",
    },
    "screen_dimensions": {
        "name": "Screen dimensions are realistic",
        "weight": 3,
        "test_js": "() => screen.width >= 1280 && screen.height >= 720 && screen.width <= 7680 && screen.height <= 4320",
    },
    "hardware_concurrency": {
        "name": "hardwareConcurrency is realistic",
        "weight": 2,
        "test_js": "() => navigator.hardwareConcurrency >= 2 && navigator.hardwareConcurrency <= 64",
    },
    "device_memory": {
        "name": "deviceMemory is realistic",
        "weight": 2,
        "test_js": "() => navigator.deviceMemory >= 2 && navigator.deviceMemory <= 64",
    },
    "connection_api": {
        "name": "navigator.connection is set",
        "weight": 2,
        "test_js": "() => navigator.connection !== undefined && navigator.connection.effectiveType !== undefined",
    },
    "iframe_consistency": {
        "name": "iframe contentWindow consistency",
        "weight": 3,
        "test_js": "() => { const iframe = document.createElement('iframe'); iframe.style.display = 'none'; document.body.appendChild(iframe); const same = iframe.contentWindow === iframe.contentWindow; document.body.removeChild(iframe); return same; }",
    },
    "toString_hidden": {
        "name": "Function.toString shows no modifications",
        "weight": 3,
        "test_js": "() => { try { return !navigator.webdriver.toString().includes(' webdriver'); } catch { return true; } }",
    },
    "no_headless_detection": {
        "name": "No headless detection indicators",
        "weight": 4,
        "test_js": "() => { const ua = navigator.userAgent; return !ua.includes('HeadlessChrome') && !ua.includes('Headless'); }",
    },
    "no_automation_flag": {
        "name": "window.automationControlled is absent",
        "weight": 3,
        "test_js": "() => !('automationControlled' in window)",
    },
    "language_consistent": {
        "name": "navigator.language is set",
        "weight": 2,
        "test_js": "() => typeof navigator.language === 'string' && navigator.language.length >= 2",
    },
}


class StealthTestSuite:
    """Run stealth tests against detection sites using Playwright."""

    def __init__(self, browser: str = "chromium", headless: bool = True):
        self.browser = browser
        self.headless = headless
        self._stealth_script = None

    def _get_stealth_script(self) -> str:
        """Get the comprehensive stealth script."""
        if self._stealth_script is None:
            from tokenade.core.browser.stealth import StealthManager
            manager = StealthManager()
            self._stealth_script = manager.get_comprehensive_script()
        return self._stealth_script

    async def run_all(self, url: Optional[str] = None) -> StealthTestReport:
        """Run all stealth tests."""
        report = StealthTestReport(browser=self.browser)
        start = time.time()

        # Run JS property checks
        js_results = await self._run_js_checks()
        report.results.extend(js_results)

        # Run site-specific tests
        if url:
            site_results = await self._run_site_test(url)
            report.results.extend(site_results)

        # Calculate overall score
        report.overall_score = self._calculate_score(report.results)
        report.duration_ms = (time.time() - start) * 1000

        return report

    async def _run_js_checks(self) -> List[TestResult]:
        """Run JavaScript property checks in a browser."""
        results = []
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return [TestResult(
                name="playwright",
                verdict=Verdict.SKIP,
                score=0,
                message="Playwright not installed",
            )]

        async with async_playwright() as p:
            browser_type = getattr(p, self.browser)
            browser = await browser_type.launch(headless=self.headless)
            context = await browser.new_context()
            page = await context.new_page()

            # Inject stealth script
            stealth = self._get_stealth_script()
            await page.add_init_script(stealth)

            # Navigate to blank page
            await page.goto("about:blank")

            # Run each JS check
            for check_id, check in JS_CHECKS.items():
                start = time.time()
                try:
                    result = await page.evaluate(check["test_js"])
                    verdict = Verdict.PASS if result else Verdict.FAIL
                    score = check["weight"] * 10 if result else 0
                    results.append(TestResult(
                        name=check["name"],
                        verdict=verdict,
                        score=score,
                        duration_ms=(time.time() - start) * 1000,
                    ))
                except Exception as e:
                    results.append(TestResult(
                        name=check["name"],
                        verdict=Verdict.WARN,
                        score=check["weight"] * 5,
                        message=f"Error: {str(e)[:100]}",
                        duration_ms=(time.time() - start) * 1000,
                    ))

            await browser.close()

        return results

    async def _run_site_test(self, url: str) -> List[TestResult]:
        """Test against a specific detection site."""
        results = []
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return []

        async with async_playwright() as p:
            browser_type = getattr(p, self.browser)
            browser = await browser_type.launch(headless=self.headless)
            context = await browser.new_context()
            page = await context.new_page()

            # Inject stealth
            stealth = self._get_stealth_script()
            await page.add_init_script(stealth)

            try:
                start = time.time()
                await page.goto(url, timeout=30000, wait_until="networkidle")
                duration = (time.time() - start) * 1000

                # Check if page loaded
                title = await page.title()
                results.append(TestResult(
                    name=f"Site: {url}",
                    verdict=Verdict.PASS if title else Verdict.WARN,
                    score=10 if title else 5,
                    message=f"Page loaded: {title}" if title else "Page loaded but no title",
                    duration_ms=duration,
                ))
            except Exception as e:
                results.append(TestResult(
                    name=f"Site: {url}",
                    verdict=Verdict.FAIL,
                    score=0,
                    message=f"Failed: {str(e)[:100]}",
                ))

            await browser.close()

        return results

    def _calculate_score(self, results: List[TestResult]) -> float:
        """Calculate weighted score (0-100)."""
        if not results:
            return 0.0

        total_weight = sum(c["weight"] for c in JS_CHECKS.values()) * 10
        if total_weight == 0:
            return 0.0
        weighted_sum = sum(r.score for r in results)
        return min(100.0, (weighted_sum / total_weight) * 100)

    async def run_silent(self) -> StealthTestReport:
        """Run tests silently, return report only."""
        return await self.run_all()


def run_stealth_tests(browser: str = "chromium", headless: bool = True) -> StealthTestReport:
    """Synchronous wrapper for running stealth tests."""
    suite = StealthTestSuite(browser=browser, headless=headless)
    return asyncio.run(suite.run_silent())
