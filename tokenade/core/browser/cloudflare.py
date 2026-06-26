"""
Cloudflare & Akamai Bypass — cf_clearance cookie extraction and challenge handling.

Detects Cloudflare challenge pages, extracts cf_clearance cookies,
and provides session aging to bypass Cloudflare heuristics.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CLOUDFLARE_COOKIE_NAMES = [
    "cf_clearance",
    "__cf_bm",
    "cf_chl_",
    "cf_ob_info",
    "cf_use_ob",
    "__cflb",
    "__cuid",
]

AKAMAI_COOKIE_NAMES = [
    "ak_bmsc",
    "bm_sv",
    "akavpau_",
    "_abck",
    "secsesession",
]

CHALLENGE_INDICATORS = [
    "Just a moment...",
    "Checking your browser",
    "Verify you are human",
    "challenge-platform",
    "cf-challenge",
    "turnstile",
    "managed-challenge",
    "Under attack mode",
    "_abck",
    "akamai",
    "bm_sz",
    "ak_bmsc",
]


@dataclass
class ChallengeDetection:
    """Result of challenge detection."""
    is_challenge: bool
    challenge_type: Optional[str] = None
    provider: Optional[str] = None
    indicators: List[str] = field(default_factory=list)
    cookies_found: List[str] = field(default_factory=list)


@dataclass
class ClearanceResult:
    """Result of cf_clearance extraction."""
    success: bool
    cookies: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None
    provider: Optional[str] = None
    extraction_time: float = 0.0


class CloudflareBypass:
    """Cloudflare challenge detection and cf_clearance extraction."""

    def __init__(self):
        self._challenge_cache: Dict[str, float] = {}

    def detect_challenge(self, page_content: str, url: str = "") -> ChallengeDetection:
        """Detect if a page is a Cloudflare/Akamai challenge."""
        indicators = []
        provider = None
        challenge_type = None

        content_lower = page_content.lower()

        for indicator in CHALLENGE_INDICATORS:
            if indicator.lower() in content_lower:
                indicators.append(indicator)

        cloudflare_indicators = [i for i in indicators if any(k in i.lower() for k in ["cf-", "cloudflare", "turnstile", "just a moment", "checking your browser", "verify you are human", "challenge-platform", "managed-challenge", "under attack"])]
        akamai_indicators = [i for i in indicators if any(k in i.lower() for k in ["akamai", "_abck"])]

        if cloudflare_indicators:
            provider = "cloudflare"
            if "turnstile" in content_lower:
                challenge_type = "turnstile"
            elif "managed" in content_lower:
                challenge_type = "managed"
            elif "under attack" in content_lower:
                challenge_type = "under-attack"
            else:
                challenge_type = "js-challenge"
        elif akamai_indicators:
            provider = "akamai"
            challenge_type = "akamai-bot"

        is_challenge = len(indicators) > 0

        return ChallengeDetection(
            is_challenge=is_challenge,
            challenge_type=challenge_type,
            provider=provider,
            indicators=indicators,
        )

    async def detect_challenge_async(self, page: Any) -> ChallengeDetection:
        """Detect challenge on a Playwright page (async)."""
        try:
            content = await page.content()
            url = page.url
            return self.detect_challenge(content, url)
        except Exception as e:
            logger.warning(f"Challenge detection failed: {e}")
            return ChallengeDetection(is_challenge=False)

    def extract_cookies_from_page(self, cookies: List[Dict]) -> ClearanceResult:
        """Extract cf_clearance and other relevant cookies."""
        start_time = time.time()
        extracted = {}
        provider = None

        for cookie in cookies:
            name = cookie.get("name", "")
            value = cookie.get("value", "")

            if name in ("cf_clearance", "__cf_bm"):
                extracted[name] = value
                provider = "cloudflare"
            elif name in ("_abck", "ak_bmsc", "bm_sv"):
                extracted[name] = value
                provider = "akamai"
            elif any(name.startswith(p) for p in CLOUDFLARE_COOKIE_NAMES):
                extracted[name] = value
                provider = "cloudflare"
            elif any(name.startswith(p) for p in AKAMAI_COOKIE_NAMES):
                extracted[name] = value
                provider = "akamai"

        elapsed = time.time() - start_time

        if not extracted:
            return ClearanceResult(
                success=False,
                error="No Cloudflare/Akamai cookies found",
                extraction_time=elapsed,
            )

        return ClearanceResult(
            success=True,
            cookies=extracted,
            provider=provider,
            extraction_time=elapsed,
        )

    async def extract_cookies_from_page_async(self, page: Any) -> ClearanceResult:
        """Extract cookies from a Playwright page (async)."""
        try:
            cookies = await page.context.cookies()
            return self.extract_cookies_from_page(cookies)
        except Exception as e:
            logger.error(f"Cookie extraction failed: {e}")
            return ClearanceResult(
                success=False,
                error=str(e),
            )

    def extract_cookies_from_session(self, session: Dict) -> ClearanceResult:
        """Extract Cloudflare/Akamai cookies from a session dict."""
        cookies = session.get("cookies", [])
        return self.extract_cookies_from_page(cookies)

    async def wait_for_clearance(
        self,
        page: Any,
        timeout: int = 30,
        poll_interval: float = 1.0,
    ) -> ClearanceResult:
        """Wait for Cloudflare challenge to resolve and extract clearance cookie."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            detection = await self.detect_challenge_async(page)

            if not detection.is_challenge:
                result = await self.extract_cookies_from_page_async(page)
                if result.success:
                    logger.info(
                        f"Got clearance cookies in {time.time() - start_time:.1f}s: "
                        f"{list(result.cookies.keys())}"
                    )
                    return result

            await page.wait_for_timeout(int(poll_interval * 1000))

        return ClearanceResult(
            success=False,
            error=f"Challenge not resolved within {timeout}s",
        )

    def get_clearance_from_cookies(self, cookies: List[Dict]) -> Dict[str, str]:
        """Quick extraction of clearance cookies from a cookie list."""
        result = self.extract_cookies_from_page(cookies)
        return result.cookies if result.success else {}

    def has_clearance(self, cookies: List[Dict]) -> bool:
        """Check if clearance cookies exist."""
        for cookie in cookies:
            name = cookie.get("name", "")
            if name in ("cf_clearance", "_abck", "ak_bmsc"):
                return True
        return False

    def merge_clearance_into_session(self, session: Dict, clearance_cookies: Dict[str, str]) -> Dict:
        """Merge clearance cookies into a session dict."""
        existing_cookies = session.get("cookies", [])
        existing_names = {c.get("name") for c in existing_cookies}

        for name, value in clearance_cookies.items():
            if name not in existing_names:
                existing_cookies.append({
                    "name": name,
                    "value": value,
                    "domain": ".challenge",
                    "path": "/",
                    "secure": True,
                    "httpOnly": False,
                })
            else:
                for cookie in existing_cookies:
                    if cookie.get("name") == name:
                        cookie["value"] = value
                        break

        session["cookies"] = existing_cookies
        return session


class AkamaiBypass:
    """Akamai Bot Manager bypass."""

    def __init__(self):
        self._sensor_data_cache: Dict[str, str] = {}

    def detect_akamai_challenge(self, page_content: str) -> bool:
        """Detect Akamai bot challenge."""
        indicators = ["_abck", "akamai", "bm_sz", "ak_bmsc"]
        content_lower = page_content.lower()
        return any(ind in content_lower for ind in indicators)

    def extract_akamai_cookies(self, cookies: List[Dict]) -> Dict[str, str]:
        """Extract Akamai-specific cookies."""
        extracted = {}
        akamai_names = ["_abck", "ak_bmsc", "bm_sv", "bm_sz"]

        for cookie in cookies:
            name = cookie.get("name", "")
            if name in akamai_names or any(name.startswith(p) for p in ["akavpau_", "secsesession"]):
                extracted[name] = cookie.get("value", "")

        return extracted

    async def extract_akamai_cookies_async(self, page: Any) -> Dict[str, str]:
        """Extract Akamai cookies from a Playwright page (async)."""
        try:
            cookies = await page.context.cookies()
            return self.extract_akamai_cookies(cookies)
        except Exception as e:
            logger.error(f"Akamai cookie extraction failed: {e}")
            return {}


def detect_challenge(page_content: str, url: str = "") -> ChallengeDetection:
    """Quick challenge detection."""
    bypass = CloudflareBypass()
    return bypass.detect_challenge(page_content, url)


def extract_clearance(cookies: List[Dict]) -> Dict[str, str]:
    """Quick clearance cookie extraction."""
    bypass = CloudflareBypass()
    return bypass.get_clearance_from_cookies(cookies)


def has_clearance(cookies: List[Dict]) -> bool:
    """Quick clearance check."""
    bypass = CloudflareBypass()
    return bypass.has_clearance(cookies)
