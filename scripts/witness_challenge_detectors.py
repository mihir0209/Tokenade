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

Visual demo mode (see detection in action):
    python3 scripts/witness_challenge_detectors.py --headed --pause
    python3 scripts/witness_challenge_detectors.py --headed --screenshot-dir artifacts/challenge-detection
"""

import argparse
import re
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

DEFAULT_SCREENSHOT_DIR = REPO_ROOT / "artifacts" / "challenge-detection"

REQUIRED_SITES = [
    ("https://turnstile-demo.pages.dev", "cloudflare", "turnstile", 1, "Cloudflare Turnstile demo page (widget renders for everyone)"),
    ("https://nowsecure.nl", "cloudflare", None, 1, "Cloudflare bot-fight benchmark site (headless is challenged)"),
    ("https://cloudflare.datashield.co", "datadome", "datadome_captcha", 5, "DataDome testing portal on Cloudflare (challenges headless intermittently)"),
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


def detect_all(ctx: dict) -> dict:
    """Run every detector against one captured page context."""
    return {name: det.detect_challenge(ctx).data for name, det in DETECTORS.items()}


def screenshot(page, url: str, shot_dir: Path) -> str:
    """Save a full-page PNG of the current page. Returns the relative path."""
    if shot_dir is None:
        return ""
    shot_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", url.split("//", 1)[-1].rstrip("/")).strip("-") or "page"
    path = shot_dir / f"{slug}.png"
    page.screenshot(path=str(path), full_page=True)
    return str(path)


def verdict_line(url: str, ok: bool, detail: str, label: str = "") -> str:
    tag = f"[{label}] " if label else ""
    return f"{tag}{url} — {detail}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Live anti-bot challenge detection witness (real Cloudflare/Akamai/DataDome sites).",
    )
    parser.add_argument("--headed", action="store_true", help="Run with a visible browser window")
    parser.add_argument("--pause", action="store_true", help="Wait for Enter after each site (guided demo)")
    parser.add_argument("--no-screenshots", action="store_true", help="Do not save page screenshots")
    parser.add_argument("--screenshot-dir", type=Path, default=DEFAULT_SCREENSHOT_DIR,
                        help=f"Where to save screenshots (default: {DEFAULT_SCREENSHOT_DIR})")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: playwright not available")
        return 0

    shot_dir = None if args.no_screenshots else args.screenshot_dir
    mode = "headed (visual demo)" if args.headed else "headless (automated checks)"
    print(f"=== Live Anti-Bot Challenge Detection Witness [{mode}] ===")
    results = []

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=not args.headed)
        except Exception as e:
            print(f"SKIP: could not launch chromium: {e}")
            return 0

        last_page = None

        def visit(url, wait_s, shot_dir):
            nonlocal last_page
            context = browser.new_context(user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"))
            page = context.new_page()
            last_page = page
            try:
                ctx = capture_page(page, url, wait_s=wait_s)
                shot = screenshot(page, url, shot_dir)
                return ctx, shot
            except Exception:
                context.close()
                raise

        for url, expected, exp_type, retries, note in REQUIRED_SITES:
            try:
                ok = False
                detail = "no attempt"
                shot = ""
                for attempt in range(retries):
                    ctx, shot = visit(url, 4.0, shot_dir)
                    detections = detect_all(ctx)
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
                        last_page.goto("https://example.com", wait_until="domcontentloaded", timeout=25000)
                        time.sleep(1)
                results.append((url, ok, detail))
                print(verdict_line(url, ok, detail + (f" | shot: {shot}" if shot else ""), "PASS" if ok else "FAIL"))
                if args.pause:
                    input("  Press Enter to continue...")
            except Exception as e:
                results.append((url, False, f"ERROR: {e}"))
                print(verdict_line(url, False, f"ERROR: {e}", "FAIL"))
                if args.pause:
                    input("  Press Enter to continue...")

        for url, expected, _t, note in INFO_SITES:
            try:
                ctx, shot = visit(url, 3.0, shot_dir)
                detections = detect_all(ctx)
                presence = vendor_presence(ctx)
                winner = max(detections.items(), key=lambda kv: kv[1].get("confidence", 0))
                detail = (f"presence={presence} det={winner[1].get('challenge_type')} "
                          f"({winner[1].get('provider')} conf={winner[1].get('confidence', 0):.2f}) "
                          f"status={ctx['status_code']}"
                          + (f" | shot: {shot}" if shot else ""))
                results.append((url, True, detail))
                print(verdict_line(url, True, detail, "INFO"))
                if args.pause:
                    input("  Press Enter to continue...")
            except Exception as e:
                results.append((url, False, f"ERROR: {e}"))
                print(verdict_line(url, False, f"ERROR: {e}", "FAIL"))
                if args.pause:
                    input("  Press Enter to continue...")

        if args.headed and last_page is not None:
            print("\nDemo finished — browser stays open for manual inspection.")
            input("  Press Enter to close the browser...")

        browser.close()

    failures = 0
    required = REQUIRED_SITES
    for i, (url, ok, detail) in enumerate(results):
        label = "PASS" if ok else ("INFO" if i >= len(required) else "FAIL")
        if i < len(required) and not ok:
            failures += 1
    print(f"RESULT: {'SUCCESS' if failures == 0 else f'{failures} FAILURES'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
