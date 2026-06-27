"""
CAPTCHA Solving Plugin Interface — abstract base for CAPTCHA solvers.

Provides a standard interface for CAPTCHA solving services (2Captcha, CapSolver, etc.)
that can be implemented as plugins.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CaptchaType(Enum):
    """Supported CAPTCHA types."""
    RECAPTCHA_V2 = "recaptcha_v2"
    RECAPTCHA_V3 = "recaptcha_v3"
    HCAPTCHA = "hcaptcha"
    TURNSTILE = "turnstile"
    FUNCAPTCHA = "funcaptcha"
    IMAGE_CAPTCHA = "image_captcha"
    TEXT_CAPTCHA = "text_captcha"
    AKAMAI_BOT = "akamai_bot"


@dataclass
class CaptchaChallenge:
    """A detected CAPTCHA challenge."""
    captcha_type: CaptchaType
    site_key: Optional[str] = None
    page_url: Optional[str] = None
    action: Optional[str] = None
    extra_data: Optional[Dict] = None


@dataclass
class CaptchaSolution:
    """Solution to a CAPTCHA challenge."""
    success: bool
    token: Optional[str] = None
    error: Optional[str] = None
    solve_time: float = 0.0
    captcha_type: Optional[CaptchaType] = None


class CaptchaSolver(ABC):
    """Abstract base class for CAPTCHA solvers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the solver."""
        ...

    @property
    @abstractmethod
    def supported_types(self) -> list:
        """List of supported CAPTCHA types."""
        ...

    @abstractmethod
    def solve(self, challenge: CaptchaChallenge) -> CaptchaSolution:
        """Solve a CAPTCHA challenge."""
        ...

    def can_solve(self, captcha_type: CaptchaType) -> bool:
        """Check if this solver can handle a CAPTCHA type."""
        return captcha_type in self.supported_types

    def get_info(self) -> Dict:
        """Get solver information."""
        return {
            "name": self.name,
            "supported_types": [t.value for t in self.supported_types],
        }


class NullCaptchaSolver(CaptchaSolver):
    """No-op solver that always fails (for testing)."""

    @property
    def name(self) -> str:
        return "null"

    @property
    def supported_types(self) -> list:
        return []

    def solve(self, challenge: CaptchaChallenge) -> CaptchaSolution:
        return CaptchaSolution(
            success=False,
            error="No CAPTCHA solver configured",
            captcha_type=challenge.captcha_type,
        )


class CaptchaDetector:
    """Detect CAPTCHAs on web pages."""

    RECAPTCHA_PATTERNS = [
        "g-recaptcha",
        "recaptcha/api.js",
        "recaptcha/api2/enterprise.js",
        "data-sitekey",
    ]

    HCATCHA_PATTERNS = [
        "h-captcha",
        "hcaptcha.com",
        "data-hcaptcha-widget-id",
    ]

    TURNSTILE_PATTERNS = [
        "turnstile",
        "cf-turnstile",
        "challenges.cloudflare.com",
    ]

    def detect(self, page_content: str, url: str = "") -> Optional[CaptchaChallenge]:
        """Detect CAPTCHA type on a page. Order: turnstile > hcaptcha > recaptcha (most specific first)."""
        content_lower = page_content.lower()

        # Check turnstile first (Cloudflare-specific)
        for pattern in self.TURNSTILE_PATTERNS:
            if pattern in content_lower:
                site_key = self._extract_site_key(page_content, "cf-turnstile")
                return CaptchaChallenge(
                    captcha_type=CaptchaType.TURNSTILE,
                    site_key=site_key,
                    page_url=url,
                )

        # Check hcaptcha before recaptcha (both use data-sitekey)
        for pattern in self.HCATCHA_PATTERNS:
            if pattern in content_lower:
                site_key = self._extract_site_key(page_content, "h-captcha")
                return CaptchaChallenge(
                    captcha_type=CaptchaType.HCAPTCHA,
                    site_key=site_key,
                    page_url=url,
                )

        # Check recaptcha last (most generic)
        for pattern in self.RECAPTCHA_PATTERNS:
            if pattern in content_lower:
                site_key = self._extract_site_key(page_content, "g-recaptcha")
                return CaptchaChallenge(
                    captcha_type=CaptchaType.RECAPTCHA_V2,
                    site_key=site_key,
                    page_url=url,
                )

        return None

    async def detect_async(self, page: Any) -> Optional[CaptchaChallenge]:
        """Detect CAPTCHA on a Playwright page (async)."""
        try:
            content = await page.content()
            url = page.url
            return self.detect(content, url)
        except Exception as e:
            logger.warning(f"CAPTCHA detection failed: {e}")
            return None

    def _extract_site_key(self, html: str, widget_class: str) -> Optional[str]:
        """Extract site key from HTML."""
        import re

        patterns = [
            r'data-sitekey="([^"]+)"',
            r"sitekey=([A-Za-z0-9_-]+)",
            rf'"{widget_class}"[^>]*data-sitekey="([^"]+)"',
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return match.group(1)

        return None


class CaptchaManager:
    """Manages CAPTCHA detection and solving."""

    def __init__(self, solver: Optional[CaptchaSolver] = None):
        self.solver = solver or NullCaptchaSolver()
        self.detector = CaptchaDetector()

    def set_solver(self, solver: CaptchaSolver) -> None:
        """Set the CAPTCHA solver."""
        self.solver = solver
        logger.info(f"CAPTCHA solver set to: {solver.name}")

    def detect(self, page_content: str, url: str = "") -> Optional[CaptchaChallenge]:
        """Detect CAPTCHA on a page."""
        return self.detector.detect(page_content, url)

    def solve(self, challenge: CaptchaChallenge) -> CaptchaSolution:
        """Solve a CAPTCHA challenge."""
        if not self.solver.can_solve(challenge.captcha_type):
            return CaptchaSolution(
                success=False,
                error=f"Solver '{self.solver.name}' cannot handle {challenge.captcha_type.value}",
                captcha_type=challenge.captcha_type,
            )

        logger.info(f"Solving {challenge.captcha_type.value} with {self.solver.name}...")
        solution = self.solver.solve(challenge)

        if solution.success:
            logger.info(f"CAPTCHA solved in {solution.solve_time:.1f}s")
        else:
            logger.warning(f"CAPTCHA solve failed: {solution.error}")

        return solution

    async def detect_and_solve_async(self, page: Any) -> Optional[CaptchaSolution]:
        """Detect and solve CAPTCHA on a Playwright page (async)."""
        challenge = await self.detector.detect_async(page)
        if not challenge:
            return None

        solution = self.solve(challenge)

        if solution.success and solution.token:
            try:
                await page.evaluate(f"""
                    document.getElementById('g-recaptcha-response').value = '{solution.token}';
                """)
            except Exception:
                pass

        return solution

    def get_info(self) -> Dict:
        """Get manager information."""
        return {
            "solver": self.solver.get_info(),
            "detector": "CaptchaDetector",
        }
