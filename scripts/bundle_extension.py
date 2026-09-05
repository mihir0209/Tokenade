#!/usr/bin/env python3
"""Build distributable zip/xpi packages for Chrome Web Store and Firefox AMO."""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tokenade.core.browser.extension_bundler import ExtensionBundler


def main():
    parser = argparse.ArgumentParser(description="Bundle Tokenade browser extension for store distribution.")
    parser.add_argument("--source-dir", type=Path, default=REPO_ROOT / "extension", help="Path to extension directory")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "dist" / "extension", help="Output directory")
    parser.add_argument("--target", choices=["all", "chrome", "firefox"], default="all", help="Target browser store")

    args = parser.parse_args()

    bundler = ExtensionBundler(source_dir=args.source_dir)
    valid, errors = bundler.validate_source()
    if not valid:
        print("ERROR: Extension validation failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    manifest = bundler.get_manifest_data()
    version = manifest.get("version", "1.0.0")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Bundling Tokenade Extension v{version}...")

    if args.target in ("all", "chrome"):
        chrome_zip = args.out_dir / f"tokenade-extension-chrome-v{version}.zip"
        bundler.build_chrome_zip(chrome_zip)
        print(f"  ✓ Chrome package: {chrome_zip} ({chrome_zip.stat().st_size / 1024:.1f} KB)")

    if args.target in ("all", "firefox"):
        firefox_xpi = args.out_dir / f"tokenade-extension-firefox-v{version}.xpi"
        bundler.build_firefox_xpi(firefox_xpi)
        print(f"  ✓ Firefox package: {firefox_xpi} ({firefox_xpi.stat().st_size / 1024:.1f} KB)")

    print("Done!")


if __name__ == "__main__":
    main()
