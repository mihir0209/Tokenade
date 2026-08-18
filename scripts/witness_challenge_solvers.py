#!/usr/bin/env python3
"""
Witness: Live challenge SOLVING against real protected sites.

Uses CloakBrowser (source-patched stealth Chromium) to actually clear
anti-bot challenges:

  1. nowsecure.nl          : Cloudflare Managed Challenge -> cf_clearance cookie
  2. turnstile-demo.pages.dev (non-interactive sitekey): Turnstile widget ->
     cf-turnstile-response token
  3. example.com           : negative control (no challenge, trivial pass)

Required checks must PASS for RESULT: SUCCESS. Screenshots of solved pages are
saved under artifacts/challenge-solving/.
"""

import argparse
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tokenade.core.integration.challenge_detectors import (
    CloudflareChallengeDetector,
)
from tokenade.core.integration.challenge_solver import CloakBrowserAutoSolver
from tokenade.core.browser.stealth.cloak import CloakBrowserBackend

DEFAULT_SHOT_DIR = REPO_ROOT / "artifacts" / "challenge-solving"

REQUIRED_SITES = [
    ("https://nowsecure.nl", "cloudflare", "cf_clearance",
     "Cloudflare Managed Challenge must drop cf_clearance"),
    ("https://turnstile-demo.pages.dev", "cloudflare", "token",
     "Turnstile widget (non-interactive sitekey) must issue a token"),
    ("https://example.com", "clean", "none",
     "Negative control — no challenge, no solving needed"),
]

TURNSTILE_DEMO_SITEKEY = "0x4AAAAAAAGhYbwMOGHiaL4f"  # Non-interactive test sitekey


def select_turnstile_demo_sitekey(page) -> None:
    """The demo page only renders the widget after choosing a sitekey."""
    page.select_option("select >> nth=0", TURNSTILE_DEMO_SITEKEY)
    time.sleep(2)


def solve_one(browser, url: str, expected: str) -> tuple:
    """Run the full detect -> solve -> verify flow for one site."""
    context = browser.new_context()
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        if "turnstile-demo" in url:
            select_turnstile_demo_sitekey(page)

        detector = CloudflareChallengeDetector()
        ctx = {
            "html": page.content(),
            "title": page.title(),
            "headers": {},
            "status_code": 200,
        }
        detection = detector.detect_challenge(ctx).data

        if expected in ("clean", "none"):
            ok = not detection.get("detected")
            return ok, f"detected={detection.get('detected')} — no solve attempted"

        solver = CloakBrowserAutoSolver(wait_timeout_s=25, reload_attempts=2)
        result = solver.solve(page, detection)
        if not result.success or not result.data.get("solved"):
            return False, result.error or "solve failed"

        token = result.data.get("token", "")
        cookies = result.data.get("clearance_cookies", [])
        cookie_names = {c["name"] for c in cookies}
        verified = result.data.get("verified", False)

        if expected == "cf_clearance":
            ok = "cf_clearance" in cookie_names
            detail = (f"cookies={sorted(cookie_names)} verified={verified} "
                      f"elapsed={result.data.get('elapsed_s')}s")
        elif expected == "token":
            ok = len(token) > 100
            detail = f"token_len={len(token)} verified={verified} elapsed={result.data.get('elapsed_s')}s"
        else:
            ok = False
            detail = f"unexpected expected={expected}"
        return ok, detail
    except Exception as e:
        return False, f"ERROR: {e}"
    finally:
        context.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Live challenge SOLVING witness (CloakBrowser vs real Cloudflare challenges).")
    parser.add_argument("--headed", action="store_true", help="Visible browser window")
    parser.add_argument("--no-screenshots", action="store_true", help="Skip PNG artifacts")
    parser.add_argument("--screenshot-dir", type=Path, default=DEFAULT_SHOT_DIR)
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright  # noqa: F401  (cloakbrowser manages its own)
    except ImportError:
        print("SKIP: playwright not available")
        return 0

    backend = CloakBrowserBackend()
    if not backend.is_available():
        print("SKIP: CloakBrowser binary not installed (run tokenade cloak install)")
        return 0

    shot_dir = None if args.no_screenshots else args.screenshot_dir
    print(f"=== Live Challenge SOLVING Witness [{('headed' if args.headed else 'headless')}] ===")

    browser = backend.launch(headless=not args.headed, fingerprint_seed=1337)
    failures = 0
    for url, _provider, expected, note in REQUIRED_SITES:
        try:
            ok, detail = solve_one(browser, url, expected)
        except Exception as e:
            ok, detail = False, f"ERROR: {e}"
        if not ok:
            failures += 1
        print(f"  [{'PASS' if ok else 'FAIL'}] {url} — {detail}")
        if shot_dir is not None:
            slug = re.sub(r"[^a-z0-9]+", "-", url.split("//", 1)[-1].rstrip("/")).strip("-")
            shot_dir.mkdir(parents=True, exist_ok=True)
            # re-open page for screenshot post-solve
            try:
                with browser.new_context() as ctx:
                    pg = ctx.new_page()
                    pg.goto(url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(2)
                    pg.screenshot(path=str(shot_dir / f"{slug}-solved.png"), full_page=True)
            except Exception:
                pass
    browser.close()

    print(f"RESULT: {'SUCCESS' if failures == 0 else f'{failures} FAILURES'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
