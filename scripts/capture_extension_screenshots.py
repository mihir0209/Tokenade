#!/usr/bin/env python3
"""Capture high-resolution visual screenshots of the Tokenade browser extension popup.

Exercises all 4 workspace tabs, light/dark themes, and interactive states:
- Export tab (dark, encrypted, all-domains)
- Inject/Import tab (empty dropzone, encrypted session loaded)
- Inspect tab (full table, search filtered)
- Settings tab (proxy bridge, light/dark themes)

Saves PNG images into artifacts/extension_screenshots/ for visual inspection.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import playwright.sync_api as pw

REPO_ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = REPO_ROOT / "extension"
OUTPUT_DIR = REPO_ROOT / "artifacts" / "extension_screenshots"


def find_extension_id(context) -> str | None:
    for page in context.pages:
        if page.url.startswith("chrome-extension://"):
            return page.url.split("/")[2]
    for worker in context.service_workers:
        if worker.url.startswith("chrome-extension://"):
            return worker.url.split("/")[2]
    return None


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Saving extension visual screenshots to: {OUTPUT_DIR}")

    with tempfile.TemporaryDirectory() as user_data_dir:
        with pw.sync_playwright() as p:
            args = [
                f"--disable-extensions-except={EXTENSION_DIR}",
                f"--load-extension={EXTENSION_DIR}",
                "--headless=new",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
            context = p.chromium.launch_persistent_context(
                user_data_dir,
                headless=False,  # driven by --headless=new in args
                args=args,
                viewport={"width": 1280, "height": 800},
            )

            try:
                # Seed test cookies and storage on a page
                site = context.new_page()
                site.goto("https://discord.com", timeout=30000, wait_until="commit")

                # Inject cookies into context
                context.add_cookies([
                    {
                        "name": "__dcfduid",
                        "value": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
                        "domain": ".discord.com",
                        "path": "/",
                        "secure": True,
                        "httpOnly": True,
                        "sameSite": "Lax",
                    },
                    {
                        "name": "__sdcfduid",
                        "value": "b9a8c7d6e5f4g3h2i1j0k1l2m3n4o5p6",
                        "domain": ".discord.com",
                        "path": "/",
                        "secure": True,
                        "httpOnly": True,
                        "sameSite": "Lax",
                    },
                    {
                        "name": "locale",
                        "value": "en-US",
                        "domain": ".discord.com",
                        "path": "/",
                        "secure": True,
                        "httpOnly": False,
                        "sameSite": "Lax",
                    },
                ])

                # Inject localStorage
                site.evaluate("""() => {
                    try {
                        localStorage.setItem("token", "mfa.abc123xyz456_fake_token_for_testing_ui_only");
                        localStorage.setItem("user_theme", "midnight");
                        sessionStorage.setItem("voice_channel_state", "connected");
                    } catch (_) {}
                }""")

                # Discover extension ID
                time.sleep(1)
                ext_id = find_extension_id(context)
                if not ext_id:
                    # Probe extension page directly
                    test_page = context.new_page()
                    for sw in context.service_workers:
                        if "chrome-extension://" in sw.url:
                            ext_id = sw.url.split("/")[2]
                            break

                if not ext_id:
                    print("Error: Could not discover extension ID")
                    return 1

                print(f"Discovered extension ID: {ext_id}")

                # Open popup
                popup = context.new_page()
                popup.set_viewport_size({"width": 520, "height": 480})
                popup.goto(f"chrome-extension://{ext_id}/popup.html", wait_until="domcontentloaded")

                # Bring site tab to front so active tab discovery works
                cdp = context.new_cdp_session(site)
                cdp.send("Page.bringToFront")
                popup.reload(wait_until="domcontentloaded")
                popup.wait_for_timeout(1000)

                # 1. Capture Export Tab (Dark)
                popup.screenshot(path=str(OUTPUT_DIR / "01-export-dark.png"))
                print("Captured 01-export-dark.png")

                # 2. Capture Export Tab with Password Entered
                popup.fill("#export-password", "SuperSecretPassphrase123!")
                popup.screenshot(path=str(OUTPUT_DIR / "02-export-encrypted-dark.png"))
                print("Captured 02-export-encrypted-dark.png")
                popup.fill("#export-password", "")

                # 3. Capture Inject/Import Tab (Empty Dropzone)
                popup.click("#nav-import")
                popup.wait_for_timeout(300)
                popup.screenshot(path=str(OUTPUT_DIR / "03-inject-dropzone-dark.png"))
                print("Captured 03-inject-dropzone-dark.png")

                # 4. Capture Inspect Tab (Cookie Table)
                popup.click("#nav-inspect")
                popup.wait_for_timeout(300)
                popup.screenshot(path=str(OUTPUT_DIR / "04-inspect-cookies-dark.png"))
                print("Captured 04-inspect-cookies-dark.png")

                # 5. Capture Inspect Tab (Search Filtered)
                popup.fill("#cookie-search", "dcfduid")
                popup.wait_for_timeout(300)
                popup.screenshot(path=str(OUTPUT_DIR / "05-inspect-search-dark.png"))
                print("Captured 05-inspect-search-dark.png")
                popup.fill("#cookie-search", "")

                # 6. Capture Settings Tab (Dark)
                popup.click("#nav-settings")
                popup.wait_for_timeout(300)
                popup.screenshot(path=str(OUTPUT_DIR / "06-settings-dark.png"))
                print("Captured 06-settings-dark.png")

                # 7. Switch to Light Theme and Capture All Tabs
                popup.select_option("#setting-theme", "light")
                popup.wait_for_timeout(300)
                popup.screenshot(path=str(OUTPUT_DIR / "07-settings-light.png"))
                print("Captured 07-settings-light.png")

                popup.click("#nav-export")
                popup.wait_for_timeout(300)
                popup.screenshot(path=str(OUTPUT_DIR / "08-export-light.png"))
                print("Captured 08-export-light.png")

                popup.click("#nav-inspect")
                popup.wait_for_timeout(300)
                popup.screenshot(path=str(OUTPUT_DIR / "09-inspect-light.png"))
                print("Captured 09-inspect-light.png")

                popup.click("#nav-import")
                popup.wait_for_timeout(300)
                popup.screenshot(path=str(OUTPUT_DIR / "10-inject-light.png"))
                print("Captured 10-inject-light.png")

            finally:
                context.close()

    print(f"\nAll 10 visual screenshots captured in {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
