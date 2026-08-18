"""
ChallengeGuard — automatic mitigation of anti-bot challenges during navigation.

Wraps a Playwright page (or anything duck-typed like it) and adds a
detect -> solve loop around page.goto, so session operations transparently
clear Cloudflare / DataDome challenges instead of failing.

Flow per navigation:
    goto(url) -> settle -> detect (all built-in detectors) ->
    if challenged -> solve (CloakBrowserAutoSolver) -> verify ->
    on failure -> retry navigation (max_attempts) -> raise or warn.
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from tokenade.core.integration.challenge_detectors import (
    AkamaiChallengeDetector,
    CloudflareChallengeDetector,
    DataDomeChallengeDetector,
)
from tokenade.core.integration.challenge_solver import (
    CapSolverSolverPlugin,
    ChallengeSolver,
    CloakBrowserAutoSolver,
    TwoCaptchaSolverPlugin,
)

logger = logging.getLogger(__name__)

BUILTIN_DETECTORS = (
    CloudflareChallengeDetector(),
    AkamaiChallengeDetector(),
    DataDomeChallengeDetector(),
)


def detect_on_page(page: Any) -> Dict[str, Any]:
    """Run all built-in detectors against a live page; return the top hit.

    Returns:
        dict with keys: detected, provider, challenge_type, confidence,
        details, all (list of every detector's verdict)
    """
    ctx = {"html": "", "title": "", "headers": {}, "status_code": 200, "cookies": []}
    try:
        ctx["html"] = page.content()
    except Exception:
        pass
    try:
        ctx["title"] = page.title()
    except Exception:
        pass
    try:
        ctx["cookies"] = page.context.cookies()
    except Exception:
        pass

    results = []
    for detector in BUILTIN_DETECTORS:
        try:
            results.append(detector.detect_challenge(ctx).data)
        except Exception:
            pass

    detected = [r for r in results if r.get("detected")]
    if not detected:
        return {"detected": False, "provider": "", "challenge_type": "none",
                "confidence": 0.0, "details": {}, "all": results}
    top = dict(max(detected, key=lambda r: r.get("confidence", 0)))
    top["all"] = results
    return top


def default_challenge_solver(
    auto_solver: Optional[Any] = None,
    external_solvers: Optional[List[Any]] = None,
    enable_external_fallback: bool = True,
) -> Any:
    """Construct standard orchestrator with stealth auto solver and configured external fallbacks."""
    stealth = auto_solver if auto_solver is not None else CloakBrowserAutoSolver(wait_timeout_s=20)
    externals = list(external_solvers or [])
    if enable_external_fallback and not externals:
        two_captcha = TwoCaptchaSolverPlugin()
        if two_captcha.api_key:
            externals.append(two_captcha)
        capsolver = CapSolverSolverPlugin()
        if capsolver.api_key:
            externals.append(capsolver)
    if externals:
        return ChallengeSolver(auto_solver=stealth, external=externals)
    return stealth


class ChallengeError(Exception):
    """Raised when a challenge could not be resolved within attempts."""


class ChallengeGuard:
    """Detect -> solve loop around navigation for a single page."""

    def __init__(self, page: Any, solver: Optional[Any] = None,
                 enabled: bool = True, settle_s: float = 2.0,
                 max_attempts: int = 3, raise_on_failure: bool = False,
                 on_solve: Optional[Callable[[str, Dict[str, Any], Any], None]] = None,
                 enable_external_fallback: bool = True):
        """
        Args:
            page: Playwright page (or duck-typed equivalent).
            solver: ChallengeSolverPlugin/ChallengeSolver; defaults to orchestrator with stealth + external fallbacks.
            enabled: when False, navigate() behaves like plain goto.
            settle_s: seconds to wait after load before detection (lets JS
                interstitials render).
            max_attempts: full re-navigation retries when a challenge sticks.
            raise_on_failure: raise ChallengeError instead of warning.
            on_solve: callback(url, detection, solver_result) on successful solve.
            enable_external_fallback: whether to include configured API solvers if stealth fails.
        """
        self.page = page
        self.solver = solver if solver is not None else default_challenge_solver(
            enable_external_fallback=enable_external_fallback)
        self.enabled = enabled
        self.settle_s = settle_s
        self.max_attempts = max_attempts
        self.raise_on_failure = raise_on_failure
        self.on_solve = on_solve

    def navigate(self, url: str, wait_until: str = "domcontentloaded",
                 timeout: int = 30000) -> Any:
        """goto, then clear any challenge that appears (with reload retries)."""
        response = self.page.goto(url, wait_until=wait_until, timeout=timeout)
        if not self.enabled:
            return response

        for attempt in range(self.max_attempts):
            time.sleep(self.settle_s)
            detection = detect_on_page(self.page)
            if not detection.get("detected"):
                return response

            logger.info("Challenge detected on %s: %s (%s conf=%.2f)",
                        url, detection.get("challenge_type"),
                        detection.get("provider"), detection.get("confidence", 0.0))
            result = self.solver.solve(self.page, detection)
            result.data.setdefault("provider", detection.get("provider", ""))
            result.data.setdefault("challenge_type", detection.get("challenge_type", ""))
            if result.success and result.data.get("solved"):
                if self.on_solve:
                    self.on_solve(url, detection, result)
                return response

            logger.warning("Solve attempt %d failed for %s: %s",
                           attempt + 1, url, result.error)
            response = self.page.goto(url, wait_until=wait_until, timeout=timeout)

        if self.raise_on_failure:
            raise ChallengeError(f"Challenge could not be cleared for {url}")
        logger.warning("Challenge unresolved for %s after %d attempts",
                       url, self.max_attempts)
        return response

    def try_mitigate(self, url: str = "", settle_s: Optional[float] = None) -> Optional[Any]:
        """Detect + solve on the current page without re-navigating.

        Returns:
            solver PluginResult when a challenge was found and attempted,
            None when the page is clean (or guard disabled).
        """
        if not self.enabled:
            return None
        if settle_s:
            time.sleep(settle_s)
        detection = detect_on_page(self.page)
        if not detection.get("detected"):
            return None
        result = self.solver.solve(self.page, detection)
        result.data.setdefault("provider", detection.get("provider", ""))
        result.data.setdefault("challenge_type", detection.get("challenge_type", ""))
        if result.success and result.data.get("solved") and self.on_solve:
            self.on_solve(url or self._page_url(), detection, result)
        return result

    def _page_url(self) -> str:
        try:
            return self.page.url
        except Exception:
            return ""
