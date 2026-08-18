#!/usr/bin/env python3
"""
Witness: Live anti-bot challenge detection against well-known protected sites.

Visits real sites that sit behind Cloudflare (Turnstile / managed challenge),
Akamai Bot Manager, and DataDome, and validates that the ChallengeDetectorPlugin
family correctly identifies challenge states — and does not false-positive on a
clean site (example.com).

Required checks (must PASS):
  - turnstile-demo.pages.dev    : Cloudflare Turnstile widget detected
  - nowsecure.nl                : Cloudflare challenge detected (headless; turnstile or managed)
  - cloudflare.datashield.co    : DataDome CAPTCHA detected (official DataDome testing portal)
  - example.com                 : negative control — no detector fires

Informational checks report vendor presence signals (headers, cookies, scripts)
for well-known protected properties: apple.com, walmart.com, vinted.com,
ticketmaster.com, openstreetmap.org, pixabay.com, akamai.datashield.co,
challenges.cloudflare.com.
"""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tokenade.core.integration.challenge_detectors import (
    AkamaiChallengeDetector,
    CloudflareChallengeDetector,
    DataDomeChallengeDetector,
)

REQUIRED_SITES = [
    ("https://turnstile-demo.pages.dev", "cloudflare", "turnstile", 1, "Cloudflare Turnstile demo page (widget renders for everyone)"),
    ("https://nowsecure.nl", "cloudflare", None, 1, "Cloudflare bot-fight benchmark site (headless is challenged)"),
    ("https://cloudflare.datashield.co", "datadome", "datadome_captcha", 3, "DataDome testing portal on Cloudflare (challenges headless intermittently)"),
    ("https://example.com", "clean", None, 1, "Negative control — must not fire any detector"),
]

INFO_SITES = [
    ("https://challenges.cloudflare.com", "cloudflare", None, "Cloudflare's own challenge endpoint"),
    ("https://openstreetmap.org", "cloudflare", None, "Turnstile on signup/forms"),
    ("https://pixabay.com", "cloudflare", None, "Cloudflare Turnstile site"),
    ("https://apple.com", "akamai", None, "Akamai edge (AkamaiGHost)"),
    ("https://www.walmart.com", "akamai", None, "Akamai + PerimeterX block pages"),
    ("https://vinted.com", "datadome", None, "DataDome device check + cookie"),
    ("https://ticketmaster.com", "datadome", None, "DataDome-protected ticketing"),
    ("https://akamai.datashield.co", "datadome", None, "DataShield (DataDome) testing portal on Akamai"),
    ("https://cloudflare.datashield.co", "datadome", None, "DataShield (DataDome) testing portal on Cloudflare"),
]

DETECTORS = {
    "cloudflare": CloudflareChallengeDetector(),
    "akamai": AkamaiChallengeDetector(),
    "datadome": DataDomeChallengeDetector(),
}


def vendor_presence(page_context: dict) -> dict:
    """Best-effort vendor presence signals (headers/cookies/scripts), no challenge required."""
    html = str(page_context.get("html", "")).lower()
    headers = {k.lower(): str(v).lower() for k, v in page_context.get("headers", {}).items()}
    cookies = " ".join(str(c.get("name", "")).lower() + "=" + str(c.get("value", "")).lower()
                       for c in page_context.get("cookies", []))
    presence = {}
    presence["cloudflare"] = (
        "cf-ray" in headers or "cloudflare" in headers.get("server", "")
        or "challenges.cloudflare.com" in html or "cdn-cgi/challenge-platform" in html
        or "__cf_bm" in cookies or "cf_clearance" in cookies
    )
    presence["akamai"] = (
        "akamai" in headers.get("server", "") or "ghost" in headers.get("server", "")
        or "x-akamai" in " ".join(headers) or "errors.edgesuite.net" in html
        or "_abck" in cookies or "bm_sz" in cookies or "ak_bmsc" in cookies
    )
    presence["datadome"] = (
        "x-datadome" in headers or "geo.captcha-delivery.com" in html
        or "js.datadome.co" in html or "datadome" in cookies
    )
    return presence


def capture_page(page, url: str, wait_s: float = 3.0) -> dict:
    """Load a URL and capture the raw signals the detectors consume."""
    response = page.goto(url, wait_until="domcontentloaded", timeout=25000)
    time.sleep(wait_s)
    headers = {}
    status = 200
    if response is not None:
        try:
            headers = {k: v for k, v in response.headers.items()}
        except Exception:
            pass
        status = response.status if response.status is not None else 200
    ctx = {
        "html": page.content(),
        "title": page.title(),
        "headers": headers,
        "status_code": status,
        "cookies": page.context.cookies(),
    }
    return ctx


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: playwright not available")
        return 0

    print("=== Live Anti-Bot Challenge Detection Witness ===")
    results = []

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            print(f"SKIP: could not launch chromium: {e}")
            return 0

        for url, expected, exp_type, retries, note in REQUIRED_SITES:
            context = browser.new_context(user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"))
            page = context.new_page()
            try:
                ok = False
                detail = "no attempt"
                for attempt in range(retries):
                    ctx = capture_page(page, url, wait_s=4.0)
                    detections = {}
                    for name, det in DETECTORS.items():
                        res = det.detect_challenge(ctx)
                        detections[name] = res.data
                    if expected == "clean":
                        fired = {n: d for n, d in detections.items() if d.get("detected")}
                        ok = len(fired) == 0
                        detail = "no detector fired" if ok else f"false positive: {fired}"
                    else:
                        winner = max(detections.items(), key=lambda kv: kv[1].get("confidence", 0))
                        d = winner[1]
                        ok = (d.get("detected") and d.get("provider") == expected
                              and d.get("confidence", 0) >= 0.8)
                        detail = (f"provider={d.get('provider')} type={d.get('challenge_type')} "
                                  f"conf={d.get('confidence', 0):.2f}")
                        if exp_type:
                            ok = ok and d.get("challenge_type") == exp_type
                    if ok:
                        break
                    if attempt < retries - 1:
                        page.goto("https://example.com", wait_until="domcontentloaded", timeout=25000)
                        time.sleep(1)
                results.append((url, ok, detail))
            except Exception as e:
                results.append((url, False, f"ERROR: {e}"))
            finally:
                context.close()

        for url, expected, _t, note in INFO_SITES:
            context = browser.new_context(user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"))
            page = context.new_page()
            try:
                ctx = capture_page(page, url, wait_s=3.0)
                detections = {}
                for name, det in DETECTORS.items():
                    res = det.detect_challenge(ctx)
                    detections[name] = res.data
                presence = vendor_presence(ctx)
                winner = max(detections.items(), key=lambda kv: kv[1].get("confidence", 0))
                detail = (f"presence={presence} det={winner[1].get('challenge_type')} "
                          f"({winner[1].get('provider')} conf={winner[1].get('confidence', 0):.2f}) "
                          f"status={ctx['status_code']}")
                results.append((url, True, detail))
            except Exception as e:
                results.append((url, False, f"ERROR: {e}"))
            finally:
                context.close()

        browser.close()

    failures = 0
    required = REQUIRED_SITES
    for i, (url, ok, detail) in enumerate(results):
        label = "PASS" if ok else ("INFO" if i >= len(required) else "FAIL")
        if i < len(required) and not ok:
            failures += 1
        print(f"  [{label}] {url} — {detail}")

    print(f"RESULT: {'SUCCESS' if failures == 0 else f'{failures} FAILURES'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
