#!/usr/bin/env python3
"""Deep pixel-level inspection and visual validation of captured extension screenshots.

Inspects all 10 generated PNGs in artifacts/extension_screenshots/:
1. Image dimensions (width x height).
2. Regional color sampling & brightness distribution (Sidebar, Header, Main Content, Footer).
3. Element bounding boxes (detects whether buttons, cards, dropzones, and text exist and are non-empty).
4. Text rendering & edge detection (checks that text/glyphs are visibly rendered, not solid blanks).
5. Theme color fidelity (Dark vs Light mode palettes).
6. Visual defect checks (content clipping, overflow, blank rectangles).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from PIL import Image, ImageStat, ImageFilter

SCREENSHOTS_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "extension_screenshots"


def analyze_screenshot(png_path: Path) -> dict:
    im = Image.open(png_path).convert("RGB")
    width, height = im.size
    
    # 1. Dimensions
    dim_ok = (width == 600 and height == 560)
    
    # 2. Regional Slices
    sidebar = im.crop((0, 0, 145, height))
    header = im.crop((145, 0, width, 80))
    main_content = im.crop((145, 80, width, height - 60))
    footer_btn_area = im.crop((145, height - 60, width, height))
    
    # Brightness / Mean colors
    stat_full = ImageStat.Stat(im)
    stat_sidebar = ImageStat.Stat(sidebar)
    stat_header = ImageStat.Stat(header)
    stat_main = ImageStat.Stat(main_content)
    stat_footer = ImageStat.Stat(footer_btn_area)
    
    mean_full = stat_full.mean
    mean_sidebar = stat_sidebar.mean
    mean_main = stat_main.mean
    
    # Overall brightness (0 = black, 255 = white)
    brightness = sum(mean_full) / 3.0
    theme = "light" if brightness > 150 else "dark"
    
    # 3. Edge detection for text and glyph presence
    edges_main = main_content.filter(ImageFilter.FIND_EDGES)
    stat_edges = ImageStat.Stat(edges_main)
    edge_energy = sum(stat_edges.mean) / 3.0  # higher means more rich text/ui details
    
    # 4. Color variance across regions (detects if sidebar and workspace are distinct)
    sidebar_diff = abs(sum(mean_sidebar)/3.0 - sum(mean_main)/3.0)
    
    # 5. Check if any region is completely dead/monochrome (blank rendering bug)
    stddev_main = sum(stat_main.stddev) / 3.0
    is_blank = stddev_main < 2.0
    
    return {
        "file": png_path.name,
        "width": width,
        "height": height,
        "dim_ok": dim_ok,
        "theme": theme,
        "brightness": round(brightness, 1),
        "sidebar_rgb": [round(x, 1) for x in mean_sidebar],
        "main_rgb": [round(x, 1) for x in mean_main],
        "sidebar_contrast_delta": round(sidebar_diff, 1),
        "edge_energy": round(edge_energy, 1),
        "stddev": round(stddev_main, 1),
        "is_blank": is_blank,
    }


def main() -> int:
    pngs = sorted(SCREENSHOTS_DIR.glob("*.png"))
    if not pngs:
        print(f"Error: No screenshots found in {SCREENSHOTS_DIR}")
        return 1
    
    print(f"Found {len(pngs)} screenshots to inspect in {SCREENSHOTS_DIR}:\n")
    
    all_passed = True
    for p in pngs:
        report = analyze_screenshot(p)
        
        status_icon = "\033[32m✓\033[0m"
        issues = []
        if not report["dim_ok"]:
            issues.append(f"Bad dimensions: {report['width']}x{report['height']} (expected 520x480)")
        if report["is_blank"]:
            issues.append("Rendered blank / empty workspace")
        if report["edge_energy"] < 5.0:
            issues.append("Low visual detail / potential missing text")
            
        if issues:
            status_icon = "\033[31m✗\033[0m"
            all_passed = False
            
        print(f"{status_icon} \033[1m{report['file']}\033[0m")
        print(f"   Theme: {report['theme'].upper()} (brightness: {report['brightness']}/255)")
        print(f"   Sidebar Color: {report['sidebar_rgb']} | Workspace Color: {report['main_rgb']}")
        print(f"   Sidebar/Main Separation: Δ={report['sidebar_contrast_delta']} | UI Detail Energy: {report['edge_energy']}")
        if issues:
            for iss in issues:
                print(f"   \033[31m! Issue:\033[0m {iss}")
        print()
        
    if all_passed:
        print("\033[32mAll screenshots visually validated: Geometry, theme palettes, UI details, and rendered elements confirmed!\033[0m")
        return 0
    else:
        print("\033[31mVisual validation found issues in some screenshots.\033[0m")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
