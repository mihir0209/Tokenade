"""
Battle Test Suite — end-to-end stealth validation against real detection sites.

Launches a stealth-patched browser, navigates to bot detection sites,
extracts detection results, and generates a composite battle score.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class BattleVerdict(Enum):
    CLEAN = "clean"
    DETECTED = "detected"
    PARTIAL = "partial"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class SiteResult:
    """Result from a single detection site."""
    site_name: str
    url: str
    verdict: BattleVerdict
    score: float  # 0-100, 100 = fully stealthy
    detection_details: Dict[str, Any] = field(default_factory=dict)
    raw_output: str = ""
    duration_ms: float = 0.0
    error: str = ""

    @property
    def passed(self) -> bool:
        return self.verdict == BattleVerdict.CLEAN


@dataclass
class BattleTestReport:
    """Aggregated battle test report across all sites."""
    overall_score: float = 0.0
    site_results: List[SiteResult] = field(default_factory=list)
    browser: str = "chromium"
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0

    @property
    def passed(self) -> int:
        return sum(1 for r in self.site_results if r.verdict == BattleVerdict.CLEAN)

    @property
    def detected(self) -> int:
        return sum(1 for r in self.site_results if r.verdict == BattleVerdict.DETECTED)

    @property
    def partial(self) -> int:
        return sum(1 for r in self.site_results if r.verdict == BattleVerdict.PARTIAL)

    @property
    def errors(self) -> int:
        return sum(1 for r in self.site_results if r.verdict == BattleVerdict.ERROR)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.site_results if r.verdict == BattleVerdict.SKIPPED)

    @property
    def total_sites(self) -> int:
        return len(self.site_results)

    @property
    def grade(self) -> str:
        if self.overall_score >= 90:
            return "A"
        elif self.overall_score >= 80:
            return "B"
        elif self.overall_score >= 70:
            return "C"
        elif self.overall_score >= 50:
            return "D"
        return "F"

    def summary(self) -> str:
        passed = self.passed
        total = self.total_sites
        detected = self.detected
        partial = self.partial
        errors = self.errors
        skipped = self.skipped
        lines = [
            f"Battle Test Report — Grade: {self.grade} "
            f"({self.overall_score:.0f}/100)",
            f"  Passed: {passed}/{total} | Detected: {detected} "
            f"| Partial: {partial} | Errors: {errors} "
            f"| Skipped: {skipped}",
            "",
        ]
        for r in self.site_results:
            icons = {
                "clean": "✅", "detected": "❌", "partial": "⚠️",
                "error": "💥", "skipped": "⏭️",
            }
            icon = icons[r.verdict.value]
            detail = r.error if r.error else (
                r.detection_details.get("summary", "")
                if r.detection_details else ""
            )
            lines.append(f"  {icon} {r.site_name}: {r.verdict.value} ({r.score:.0f}/100) {detail}")
        return "\n".join(lines)


DETECTION_SITES = {
    "bot_sannysoft": {
        "name": "Bot.sannysoft.com",
        "url": "https://bot.sannysoft.com/",
        "weight": 1.0,
        "extract_js": """
        () => {
            const results = {};
            const rows = document.querySelectorAll('table tr');
            for (const row of rows) {
                const cells = row.querySelectorAll('td');
                if (cells.length >= 2) {
                    const name = cells[0]?.textContent?.trim();
                    const value = cells[1]?.textContent?.trim();
                    const color = cells[1]?.style?.backgroundColor || '';
                    if (name && value) {
                        results[name] = {
                            value: value,
                            passed: !color.includes('red') && !color.includes('255, 0'),
                        };
                    }
                }
            }
            const failed = Object.values(results).filter(r => !r.passed).length;
            const total = Object.keys(results).length || 1;
            const score = Math.round(((total - failed) / total) * 100);
            return {
                score: score,
                failed_checks: failed,
                total_checks: total,
                details: results,
                summary: failed === 0 ? 'All checks passed' : failed + '/' + total + ' checks detected',
            };
        }
        """,
    },
    "creepjs": {
        "name": "CreepJS",
        "url": "https://abrahamjuliot.github.io/creepjs/",
        "weight": 0.8,
        "extract_js": """
        async () => {
            await new Promise(r => setTimeout(r, 8000));
            let score = 50;
            const details = {};

            // Find grade elements (class contains 'grade-')
            const gradeEls = document.querySelectorAll(
                '[class*="grade-"]'
            );
            const grades = [];
            gradeEls.forEach(el => {
                const cls = el.className || '';
                const m = cls.match(/grade-([A-F][+-]?)/i);
                if (m) grades.push(m[1]);
            });
            details.grades = grades;

            // Find headless rating percentage
            const headlessEl = document.querySelector(
                '[class*="headless-rating"]'
            );
            if (headlessEl) {
                const text = headlessEl.textContent.trim();
                const pctMatch = text.match(/(\\d+)%/);
                details.headless_pct = pctMatch
                    ? parseInt(pctMatch[1]) : null;
            }

            // Check stealth percentage
            const bodyText = document.body?.textContent || '';
            const stealthMatch = bodyText.match(/(\\d+)%\\s*stealth/i);
            details.stealth_pct = stealthMatch
                ? parseInt(stealthMatch[1]) : null;

            // Calculate score from grade
            // Grade C = 60-69 (moderate detection)
            // Grade A = 90-100 (high stealth)
            // We use the FIRST grade (overall assessment)
            if (grades.length > 0) {
                const gradeScores = {
                    'A+': 100, 'A': 95, 'A-': 90,
                    'B+': 85, 'B': 80, 'B-': 75,
                    'C+': 70, 'C': 65, 'C-': 60,
                    'D+': 55, 'D': 50, 'D-': 45,
                    'F': 20,
                };
                // Use the WORST grade (first one is overall)
                score = gradeScores[grades[0]] || 50;
            }

            // Boost if stealth percentage is high
            if (details.stealth_pct && details.stealth_pct > 70) {
                score = Math.min(100, score + 5);
            }

            return {
                score: Math.min(100, Math.max(0, score)),
                details: details,
                summary: grades.length > 0
                    ? 'Grade: ' + grades.join(', ')
                    : 'Grade not found',
            };
        }
        """,
    },
    "pixelscan": {
        "name": "Pixelscan",
        "url": "https://pixelscan.net/",
        "weight": 1.0,
        "extract_js": """
        async () => {
            await new Promise(r => setTimeout(r, 5000));
            let score = 50;
            const details = {};

            // Check navigator properties
            details.webdriver = navigator.webdriver;
            details.chrome = typeof window.chrome !== 'undefined';
            details.plugins = navigator.plugins?.length || 0;

            // Check body text for detection keywords
            const bodyText = document.body?.textContent || '';
            const cleanCount = (
                bodyText.match(/clean|passed|not automated/gi) || []
            ).length;
            const detCount = (
                bodyText.match(/detected|automated|flagged/gi) || []
            ).length;
            details.clean_matches = cleanCount;
            details.detected_matches = detCount;

            // Check webdriver flag explicitly
            if (navigator.webdriver === true) {
                score -= 40;
                details.webdriver_flag = true;
            } else {
                score += 20;
                details.webdriver_flag = false;
            }

            // Check chrome object
            if (typeof window.chrome === 'undefined') {
                score -= 15;
            } else {
                score += 10;
            }

            // Check plugins
            if (details.plugins === 0) {
                score -= 10;
            } else {
                score += 5;
            }

            // Factor in text content
            if (cleanCount > detCount) {
                score += 10;
            } else if (detCount > cleanCount) {
                score -= 20;
            }

            return {
                score: Math.min(100, Math.max(0, score)),
                details: details,
                summary: score >= 70
                    ? 'Likely clean'
                    : (navigator.webdriver
                        ? 'Webdriver detected'
                        : 'Partial detection'),
            };
        }
        """,
    },
    "browserleaks": {
        "name": "BrowserLeaks",
        "url": "https://browserleaks.com/javascript",
        "weight": 0.7,
        "extract_js": """
        () => {
            const results = {};
            let score = 80;
            const webdriver = navigator.webdriver;
            results.webdriver_flag = webdriver;
            if (webdriver === true) {
                score -= 40;
            }
            const chrome = window.chrome;
            results.chrome_object = !!chrome;
            if (!chrome) {
                score -= 20;
            }
            const plugins = navigator.plugins;
            results.plugins_count = plugins ? plugins.length : 0;
            if (results.plugins_count === 0) {
                score -= 15;
            }
            const ua = navigator.userAgent;
            results.user_agent = ua.substring(0, 100);
            results.has_headless = ua.toLowerCase().includes('headless');
            if (results.has_headless) {
                score -= 25;
            }
            return {
                score: Math.min(100, Math.max(0, score)),
                details: results,
                summary: score >= 70 ? 'JavaScript API looks clean' : 'Detection vectors found',
            };
        }
        """,
    },
    "iphey": {
        "name": "Iphey",
        "url": "https://iphey.com/",
        "weight": 0.6,
        "extract_js": """
        async () => {
            await new Promise(r => setTimeout(r, 6000));
            let score = 60;
            const details = {};

            const bodyText = document.body?.textContent || '';

            // Check webdriver
            details.webdriver = navigator.webdriver;
            if (navigator.webdriver === true) {
                score -= 35;
            }

            // Check for "you seem real" / positive verdict
            if (bodyText.match(/you seem (real|genuine|human)/i)) {
                score += 30;
                details.verdict = 'Passed';
            }
            else {
                details.verdict = 'Unknown';
            }

            // Check plugins
            details.plugins = navigator.plugins?.length || 0;
            if (details.plugins === 0) {
                score -= 10;
            }

            // Check chrome object
            if (typeof window.chrome !== 'undefined') {
                score += 10;
            }

            return {
                score: Math.min(100, Math.max(0, score)),
                details: details,
                summary: details.verdict || 'Unknown',
            };
        }
        """,
    },
}


async def _run_battle_site(
    browser_type,
    site_config: Dict,
    stealth_script: str,
    headless: bool = True,
    timeout_ms: int = 30000,
) -> SiteResult:
    """Run battle test against a single detection site."""
    site_name = site_config["name"]
    url = site_config["url"]
    start_time = time.time()

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return SiteResult(
            site_name=site_name,
            url=url,
            verdict=BattleVerdict.SKIPPED,
            score=0.0,
            error="playwright not installed",
        )

    try:
        async with async_playwright() as p:
            bt = getattr(p, browser_type)
            browser = await bt.launch(headless=headless)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            # CDP-level UA override for Chromium (fixes Worker UA detection)
            if browser_type == "chromium":
                try:
                    cdp = await context.new_cdp_session(page=page)
                    await cdp.send("Emulation.setUserAgentOverride", {
                        "userAgent": (
                            "Mozilla/5.0 (X11; Linux x86_64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/131.0.0.0 Safari/537.36"
                        ),
                        "acceptLanguage": "en-GB,en;q=0.9",
                        "platform": "Linux x86_64",
                        "userAgentMetadata": {
                            "brands": [
                                {"brand": "Google Chrome",
                                 "version": "131"},
                                {"brand": "Chromium",
                                 "version": "131"},
                            ],
                            "fullVersionList": [
                                {"brand": "Google Chrome",
                                 "version": "131.0.0.0"},
                                {"brand": "Chromium",
                                 "version": "131.0.0.0"},
                            ],
                            "platform": "Linux",
                            "platformVersion": "6.5.0",
                            "architecture": "x86",
                            "model": "",
                            "mobile": False,
                        },
                    })
                except Exception:
                    pass  # CDP not available on non-Chromium

            if stealth_script:
                await page.add_init_script(stealth_script)

            try:
                await page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            except Exception:
                await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")

            extract_js = site_config.get("extract_js", "")
            if extract_js:
                try:
                    extraction = await page.evaluate(extract_js)
                except Exception as e:
                    extraction = {"score": 0, "error": str(e), "summary": f"Extraction failed: {str(e)[:80]}"}

                score = float(extraction.get("score", 0))
                details = {k: v for k, v in extraction.items() if k not in ("score",)}
                summary = extraction.get("summary", "")

                if score >= 75:
                    verdict = BattleVerdict.CLEAN
                elif score >= 40:
                    verdict = BattleVerdict.PARTIAL
                else:
                    verdict = BattleVerdict.DETECTED
            else:
                title = await page.title()
                score = 80.0 if title else 40.0
                details = {"title": title}
                summary = f"Page loaded: {title}" if title else "No title"
                verdict = BattleVerdict.CLEAN if score >= 75 else BattleVerdict.PARTIAL

            await browser.close()

            duration = (time.time() - start_time) * 1000
            return SiteResult(
                site_name=site_name,
                url=url,
                verdict=verdict,
                score=score,
                detection_details=details,
                raw_output=summary,
                duration_ms=duration,
            )

    except Exception as e:
        duration = (time.time() - start_time) * 1000
        return SiteResult(
            site_name=site_name,
            url=url,
            verdict=BattleVerdict.ERROR,
            score=0.0,
            error=str(e)[:200],
            duration_ms=duration,
        )


class BattleTestSuite:
    """Battle test suite for end-to-end stealth validation."""

    def __init__(
        self,
        browser: str = "chromium",
        headless: bool = True,
        sites: Optional[List[str]] = None,
        timeout_ms: int = 30000,
    ):
        self.browser = browser
        self.headless = headless
        self.sites = sites or list(DETECTION_SITES.keys())
        self.timeout_ms = timeout_ms

    def _get_stealth_script(self) -> str:
        try:
            from tokenade.core.browser.stealth import StealthManager
            sm = StealthManager()
            return sm.get_combined_script()
        except Exception:
            return ""

    async def run_all(self) -> BattleTestReport:
        """Run battle tests against all configured sites."""
        start_time = time.time()
        stealth_script = self._get_stealth_script()
        results: List[SiteResult] = []

        for site_key in self.sites:
            if site_key not in DETECTION_SITES:
                results.append(SiteResult(
                    site_name=site_key,
                    url="",
                    verdict=BattleVerdict.SKIPPED,
                    score=0.0,
                    error=f"Unknown site: {site_key}",
                ))
                continue

            site_config = DETECTION_SITES[site_key]
            logger.info(f"Battle testing: {site_config['name']} ({site_config['url']})")

            result = await _run_battle_site(
                browser_type=self.browser,
                site_config=site_config,
                stealth_script=stealth_script,
                headless=self.headless,
                timeout_ms=self.timeout_ms,
            )
            results.append(result)

        total_duration = (time.time() - start_time) * 1000

        weighted_score = 0.0
        total_weight = 0.0
        for r in results:
            site_config = DETECTION_SITES.get(r.site_name, {})
            weight = site_config.get("weight", 0.5)
            if r.verdict not in (BattleVerdict.ERROR, BattleVerdict.SKIPPED):
                weighted_score += r.score * weight
                total_weight += weight * 100

        overall_score = (weighted_score / total_weight * 100) if total_weight > 0 else 0.0

        return BattleTestReport(
            overall_score=overall_score,
            site_results=results,
            browser=self.browser,
            timestamp=time.time(),
            duration_ms=total_duration,
        )

    def run_sync(self) -> BattleTestReport:
        """Synchronous wrapper for run_all()."""
        return asyncio.run(self.run_all())
