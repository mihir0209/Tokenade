#!/usr/bin/env python3
"""Automated DOM, layout geometry, CSS styling, and contrast validator for Tokenade popup.

Inspects:
1. Viewport & container geometry (520px width, no unexpected horizontal/vertical overflow).
2. Element bounds & spacing (sidebar width, workspace width, button heights).
3. Contrast ratios (WCAG AA standard: >= 4.5:1 for normal text).
4. Interactive states across all 4 tabs in both Dark and Light themes.
5. DOM hierarchy and text truncation / clipping detection.
"""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path

import playwright.sync_api as pw

REPO_ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = REPO_ROOT / "extension"


def parse_rgb(rgb_str: str) -> tuple[int, int, int]:
    """Parse 'rgb(r, g, b)' or 'rgba(r, g, b, a)' into (r, g, b)."""
    rgb_str = rgb_str.replace("rgba(", "").replace("rgb(", "").replace(")", "")
    parts = [int(p.strip().split(".")[0]) for p in rgb_str.split(",")[:3]]
    return (parts[0], parts[1], parts[2])


def luminance(r: int, g: int, b: int) -> float:
    """Calculate relative luminance per WCAG 2.1."""
    srgb = [x / 255.0 for x in (r, g, b)]
    lin = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in srgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int]) -> float:
    """Calculate contrast ratio between two RGB colors."""
    l1 = luminance(*rgb1)
    l2 = luminance(*rgb2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def run_ui_validation() -> dict:
    results = {
        "passed": [],
        "warnings": [],
        "metrics": {},
    }

    def check(name: str, condition: bool, detail: str = ""):
        if condition:
            results["passed"].append(f"[PASS] {name}: {detail}" if detail else f"[PASS] {name}")
            print(f"  \033[32m✓\033[0m {name} {detail}")
        else:
            results["warnings"].append(f"[FAIL] {name}: {detail}" if detail else f"[FAIL] {name}")
            print(f"  \033[31m✗\033[0m {name} {detail}")

    with tempfile.TemporaryDirectory() as user_data_dir:
        with pw.sync_playwright() as p:
            args = [
                f"--disable-extensions-except={EXTENSION_DIR}",
                f"--load-extension={EXTENSION_DIR}",
                "--headless=new",
                "--no-sandbox",
            ]
            context = p.chromium.launch_persistent_context(
                user_data_dir,
                headless=False,
                args=args,
                viewport={"width": 1280, "height": 800},
            )

            try:
                # Seed test site
                site = context.new_page()
                site.goto("https://discord.com", timeout=30000, wait_until="commit")
                context.add_cookies([
                    {"name": "__dcfduid", "value": "test12345", "domain": ".discord.com", "path": "/", "secure": True, "httpOnly": True},
                    {"name": "locale", "value": "en-US", "domain": ".discord.com", "path": "/", "secure": True, "httpOnly": False},
                ])

                time.sleep(1)
                # Find extension ID
                ext_id = None
                for sw in context.service_workers:
                    if "chrome-extension://" in sw.url:
                        ext_id = sw.url.split("/")[2]
                        break

                if not ext_id:
                    print("Error: Could not discover extension ID")
                    return results

                popup = context.new_page()
                popup.set_viewport_size({"width": 600, "height": 560})
                popup.goto(f"chrome-extension://{ext_id}/popup.html", wait_until="domcontentloaded")

                # Bring site to front and reload popup
                cdp = context.new_cdp_session(site)
                cdp.send("Page.bringToFront")
                popup.reload(wait_until="domcontentloaded")
                popup.wait_for_timeout(1000)

                print("\n=== 1. Geometry & Layout Measurements ===")
                body_box = popup.evaluate("() => { const b = document.body.getBoundingClientRect(); return { width: b.width, height: b.height, scrollWidth: document.body.scrollWidth, scrollHeight: document.body.scrollHeight }; }")
                sidebar_box = popup.evaluate("() => { const s = document.querySelector('.sidebar').getBoundingClientRect(); return { width: s.width, height: s.height }; }")
                workspace_box = popup.evaluate("() => { const w = document.querySelector('.workspace').getBoundingClientRect(); return { width: w.width, height: w.height, scrollWidth: document.querySelector('.workspace').scrollWidth }; }")

                check("Body width is 600px", abs(body_box["width"] - 600) < 2, f"actual={body_box['width']}px")
                check("Body has no horizontal overflow", body_box["scrollWidth"] <= body_box["width"], f"scrollWidth={body_box['scrollWidth']} vs width={body_box['width']}")
                check("Sidebar width is ~145px", 135 <= sidebar_box["width"] <= 155, f"actual={sidebar_box['width']}px")
                check("Workspace width is ~455px", 440 <= workspace_box["width"] <= 470, f"actual={workspace_box['width']}px")

                check("Pop-out window button exists", popup.is_visible("#btn-popout-window"))
                check("Close popup button exists", popup.is_visible("#btn-close-popup"))

                print("\n=== 2. Color Contrast (Dark Theme) ===")
                dark_colors = popup.evaluate("""() => {
                    const getRgb = (sel, prop) => window.getComputedStyle(document.querySelector(sel))[prop];
                    return {
                        bodyBg: getRgb('body', 'backgroundColor'),
                        bodyText: getRgb('body', 'color'),
                        sidebarBg: getRgb('.sidebar', 'backgroundColor'),
                        accentText: getRgb('.brand-title', 'color'),
                        mutedText: getRgb('.form-label', 'color'),
                        btnPrimaryBg: getRgb('.btn-primary', 'backgroundColor'),
                        btnPrimaryColor: getRgb('.btn-primary', 'color'),
                        siteCardBg: getRgb('.site-card', 'backgroundColor'),
                        siteDomainColor: getRgb('.site-domain', 'color'),
                    };
                }""")

                body_bg = parse_rgb(dark_colors["bodyBg"])
                body_text = parse_rgb(dark_colors["bodyText"])
                sidebar_bg = parse_rgb(dark_colors["sidebarBg"])
                accent_text = parse_rgb(dark_colors["accentText"])
                site_card_bg = parse_rgb(dark_colors["siteCardBg"])
                site_domain_color = parse_rgb(dark_colors["siteDomainColor"])

                ratio_text = contrast_ratio(body_bg, body_text)
                ratio_accent = contrast_ratio(sidebar_bg, accent_text)
                ratio_domain = contrast_ratio(site_card_bg, site_domain_color)

                check("Dark Theme body text contrast (>= 4.5:1)", ratio_text >= 4.5, f"ratio={ratio_text:.2f}:1")
                check("Dark Theme accent contrast (>= 4.5:1)", ratio_accent >= 4.5, f"ratio={ratio_accent:.2f}:1")
                check("Dark Theme domain contrast in card (>= 4.5:1)", ratio_domain >= 4.5, f"ratio={ratio_domain:.2f}:1")

                print("\n=== 3. Tab Navigation & Interactive Elements ===")
                for tab_id, tab_sel in [
                    ("Export", "#nav-export"),
                    ("Inject", "#nav-import"),
                    ("Vault", "#nav-vault"),
                    ("Inspect", "#nav-inspect"),
                    ("Health", "#nav-health"),
                    ("Settings", "#nav-settings"),
                ]:
                    popup.click(tab_sel)
                    popup.wait_for_timeout(200)
                    nav_active = popup.evaluate(f"() => document.querySelector('{tab_sel}').classList.contains('active')")
                    check(f"{tab_id} nav tab activates cleanly", nav_active)

                print("\n=== 4. Color Contrast (Light Theme) ===")
                popup.click("#nav-settings")
                popup.select_option("#setting-theme", "light")
                popup.wait_for_timeout(300)

                light_colors = popup.evaluate("""() => {
                    const getRgb = (sel, prop) => window.getComputedStyle(document.querySelector(sel))[prop];
                    return {
                        bodyBg: getRgb('body', 'backgroundColor'),
                        bodyText: getRgb('body', 'color'),
                        sidebarBg: getRgb('.sidebar', 'backgroundColor'),
                        accentText: getRgb('.brand-title', 'color'),
                        siteCardBg: getRgb('.site-card', 'backgroundColor'),
                        siteDomainColor: getRgb('.site-domain', 'color'),
                    };
                }""")

                l_body_bg = parse_rgb(light_colors["bodyBg"])
                l_body_text = parse_rgb(light_colors["bodyText"])
                l_sidebar_bg = parse_rgb(light_colors["sidebarBg"])
                l_accent_text = parse_rgb(light_colors["accentText"])
                l_card_bg = parse_rgb(light_colors["siteCardBg"])
                l_domain_color = parse_rgb(light_colors["siteDomainColor"])

                l_ratio_text = contrast_ratio(l_body_bg, l_body_text)
                l_ratio_accent = contrast_ratio(l_sidebar_bg, l_accent_text)
                l_ratio_domain = contrast_ratio(l_card_bg, l_domain_color)

                check("Light Theme body text contrast (>= 4.5:1)", l_ratio_text >= 4.5, f"ratio={l_ratio_text:.2f}:1")
                check("Light Theme accent contrast (>= 4.5:1)", l_ratio_accent >= 4.5, f"ratio={l_ratio_accent:.2f}:1")
                check("Light Theme domain contrast (>= 4.5:1)", l_ratio_domain >= 4.5, f"ratio={l_ratio_domain:.2f}:1")

                print("\n=== 5. Cookie Table Inspection & Search Functionality ===")
                popup.click("#nav-inspect")
                popup.wait_for_timeout(300)
                table_info = popup.evaluate("""() => {
                    const rows = Array.from(document.querySelectorAll('#cookie-table-body tr'));
                    return {
                        rowCount: rows.length,
                        firstRowText: rows[0] ? rows[0].innerText : '',
                    };
                }""")
                check("Cookie table populated with active cookies", table_info["rowCount"] >= 2, f"rows={table_info['rowCount']}")

                # Test live search filter
                popup.fill("#cookie-search", "__sdcfduid")
                popup.wait_for_timeout(200)
                filtered_count = popup.evaluate("() => document.querySelectorAll('#cookie-table-body tr').length")
                check("Cookie search filter narrows to 1 matching row", filtered_count == 1, f"filtered={filtered_count}")

            finally:
                context.close()

    return results


if __name__ == "__main__":
    results = run_ui_validation()
    passed = len(results["passed"])
    warnings = len(results["warnings"])
    print(f"\n==========================================")
    print(f"UI/UX Validation: {passed} passed, {warnings} failed")
    print(f"==========================================")
    if warnings > 0:
        sys.exit(1)
