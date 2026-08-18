"""
Challenge detector plugins for major Anti-Bot & WAF providers.

Provides:
1. CloudflareChallengeDetector: Turnstile, 5-second shield (managed challenge), WAF 1020/403 blocks.
2. AkamaiChallengeDetector: Akamai Bot Manager, interstitial sensor scripts, Sec-CH challenge.
3. DataDomeChallengeDetector: DataDome device check captcha & 403 blocks.
4. GenericWAFChallengeDetector: Catch-all for standard Captchas (reCAPTCHA, hCaptcha, AWS WAF).
"""

import re
from typing import Any, Dict, List, Optional
from tokenade.plugin.api import PluginResult
from tokenade.plugin.base import ChallengeDetectorPlugin


class CloudflareChallengeDetector(ChallengeDetectorPlugin):
    """Detects Cloudflare Turnstile, Managed Challenges, and WAF blocks."""

    name = "cloudflare-challenge-detector"
    version = "1.0.0"
    description = "Detects Cloudflare Turnstile, interstitial pages, and WAF blocks"
    author = "Tokenade"
    provider = "cloudflare"

    # Known Cloudflare challenge DOM indicators
    SELECTORS = [
        "iframe[src*='challenges.cloudflare.com']",
        "#cf-challenge-running",
        "#challenge-stage",
        "#turnstile-wrapper",
        ".cf-turnstile",
        "[data-cf-turnstile]",
        "form#challenge-form",
        "#cf-wrapper",
    ]

    TITLE_PATTERNS = [
        r"just a moment\.\.\.",
        r"attention required!\s*\|\s*cloudflare",
        r"security check",
        r"ddos protection by cloudflare",
    ]

    HEADER_INDICATORS = [
        ("server", "cloudflare"),
        ("cf-ray", None),
        ("cf-mitigated", "challenge"),
    ]

    def detect_challenge(self, page_context: Any) -> PluginResult:
        """Analyze page HTML, title, headers, or live Playwright page."""
        detected = False
        challenge_type = "none"
        confidence = 0.0
        details = {}

        # 1. Inspect dictionary / static representation
        if isinstance(page_context, dict):
            html = str(page_context.get("html", "")).lower()
            title = str(page_context.get("title", "")).lower()
            headers = {k.lower(): str(v).lower() for k, v in page_context.get("headers", {}).items()}
            status_code = page_context.get("status_code", 200)

            # Check Headers
            if "cf-mitigated" in headers and "challenge" in headers["cf-mitigated"]:
                detected = True
                challenge_type = "managed_challenge"
                confidence = 1.0
                details["reason"] = "cf-mitigated header present"

            # Check Title
            for pat in self.TITLE_PATTERNS:
                if re.search(pat, title):
                    detected = True
                    challenge_type = "managed_challenge"
                    confidence = max(confidence, 0.95)
                    details["title_match"] = title

            # Check HTML & Selectors
            if "challenges.cloudflare.com/turnstile" in html or "class=\"cf-turnstile\"" in html:
                detected = True
                challenge_type = "turnstile"
                confidence = max(confidence, 0.98)
                details["turnstile_found"] = True

            if status_code in (403, 503) and ("cloudflare" in html or "cf-ray" in headers):
                if not detected:
                    detected = True
                    challenge_type = "waf_block"
                    confidence = 0.9
                    details["status_code"] = status_code

        # 2. Inspect live Playwright page object if available
        elif hasattr(page_context, "content") and hasattr(page_context, "title"):
            try:
                title = (page_context.title() or "").lower()
                for pat in self.TITLE_PATTERNS:
                    if re.search(pat, title):
                        detected = True
                        challenge_type = "managed_challenge"
                        confidence = 0.95

                for sel in self.SELECTORS:
                    try:
                        if page_context.is_visible(sel, timeout=500):
                            detected = True
                            challenge_type = "turnstile" if "turnstile" in sel else "managed_challenge"
                            confidence = 0.99
                            details["selector_matched"] = sel
                            break
                    except Exception:
                        pass
            except Exception as e:
                details["inspect_error"] = str(e)

        return PluginResult(
            success=True,
            data={
                "detected": detected,
                "provider": self.provider,
                "challenge_type": challenge_type,
                "confidence": confidence if detected else 0.0,
                "details": details,
            }
        )


class AkamaiChallengeDetector(ChallengeDetectorPlugin):
    """Detects Akamai Bot Manager, sensor data triggers, and interstitial blocks."""

    name = "akamai-challenge-detector"
    version = "1.0.0"
    description = "Detects Akamai Bot Manager and interstitial challenge states"
    author = "Tokenade"
    provider = "akamai"

    AKAMAI_KEYWORDS = [
        "akamai",
        "akam",
        "_abck",
        "bm_sz",
        "sensor_data",
        "access denied",
        "sec-cpt",
    ]

    def detect_challenge(self, page_context: Any) -> PluginResult:
        detected = False
        challenge_type = "none"
        confidence = 0.0
        details = {}

        if isinstance(page_context, dict):
            html = str(page_context.get("html", "")).lower()
            title = str(page_context.get("title", "")).lower()
            headers = {k.lower(): str(v).lower() for k, v in page_context.get("headers", {}).items()}
            status = page_context.get("status_code", 200)

            # Akamai challenge headers
            if "server" in headers and "ghost" in headers["server"]:
                details["akamai_ghost"] = True
            if "x-akamai-transformed" in headers or "x-akamai-request-id" in headers:
                details["akamai_headers"] = True

            if status in (403, 503) and ("access denied" in title or "access denied" in html or "sec-cpt" in html):
                detected = True
                challenge_type = "akamai_interstitial"
                confidence = 0.92
                details["blocked"] = True

            if "sec-cpt" in html or "akamai bot manager" in html:
                detected = True
                challenge_type = "akamai_challenge"
                confidence = 0.96

        return PluginResult(
            success=True,
            data={
                "detected": detected,
                "provider": self.provider,
                "challenge_type": challenge_type,
                "confidence": confidence if detected else 0.0,
                "details": details,
            }
        )


class DataDomeChallengeDetector(ChallengeDetectorPlugin):
    """Detects DataDome device verification and CAPTCHA screens."""

    name = "datadome-challenge-detector"
    version = "1.0.0"
    description = "Detects DataDome anti-bot challenges and captchas"
    author = "Tokenade"
    provider = "datadome"

    def detect_challenge(self, page_context: Any) -> PluginResult:
        detected = False
        challenge_type = "none"
        confidence = 0.0
        details = {}

        if isinstance(page_context, dict):
            html = str(page_context.get("html", "")).lower()
            headers = {k.lower(): str(v).lower() for k, v in page_context.get("headers", {}).items()}
            status = page_context.get("status_code", 200)

            if "x-datadome" in headers or "datadome=" in headers.get("set-cookie", ""):
                details["datadome_present"] = True

            if "geo.captcha-delivery.com" in html or "datadome.js" in html:
                if status == 403 or "please enable js and disable any ad blocker" in html:
                    detected = True
                    challenge_type = "datadome_captcha"
                    confidence = 0.98
                    details["captcha_url_found"] = True

        return PluginResult(
            success=True,
            data={
                "detected": detected,
                "provider": self.provider,
                "challenge_type": challenge_type,
                "confidence": confidence if detected else 0.0,
                "details": details,
            }
        )
