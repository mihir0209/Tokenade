"""
Extension Store Bundler and Packager.

Builds distribution-ready packages for:
1. Chrome Web Store / Chromium (.zip)
2. Firefox AMO (.xpi / .zip with Firefox manifest compatibility)

Excludes developer artifacts (tests, python scripts, temp files, etc.)
and validates manifests before output.
"""

import json
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# Core files required in extension build
REQUIRED_EXTENSION_FILES = [
    "manifest.json",
    "background.js",
    "content.js",
    "content-main.js",
    "popup.html",
    "popup.js",
    "crypto.js",
]

# Patterns or filenames to exclude from extension zip/xpi bundles
EXCLUDED_PATTERNS = {
    ".DS_Store",
    "Thumbs.db",
    "__pycache__",
    "generate_icons.py",
    "generate_icons.sh",
    ".gitignore",
    ".pytest_cache",
}


class ExtensionBundler:
    """Bundles the Tokenade browser extension for store distribution."""

    def __init__(self, source_dir: Optional[Path] = None):
        if source_dir is None:
            # Default to repo's extension directory
            self.source_dir = Path(__file__).resolve().parents[3] / "extension"
        else:
            self.source_dir = Path(source_dir).resolve()

        if not self.source_dir.is_dir():
            raise FileNotFoundError(f"Extension source directory not found at {self.source_dir}")

    def validate_source(self) -> Tuple[bool, List[str]]:
        """Validate that all required extension files and manifest exist."""
        errors = []
        for req in REQUIRED_EXTENSION_FILES:
            target = self.source_dir / req
            if not target.is_file():
                errors.append(f"Missing required extension file: {req}")

        manifest_path = self.source_dir / "manifest.json"
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if not manifest.get("name"):
                    errors.append("manifest.json missing 'name'")
                if not manifest.get("version"):
                    errors.append("manifest.json missing 'version'")
                if manifest.get("manifest_version") != 3:
                    errors.append("manifest.json must be manifest_version 3")
            except Exception as e:
                errors.append(f"Invalid JSON in manifest.json: {e}")

        return len(errors) == 0, errors

    def get_manifest_data(self) -> Dict[str, Any]:
        """Read and return parsed manifest.json."""
        manifest_path = self.source_dir / "manifest.json"
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def build_chrome_zip(self, output_path: Path) -> Path:
        """
        Build a Chrome Web Store distribution zip.
        Removes Firefox-specific keys if necessary and packages cleanly.
        """
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        manifest = self.get_manifest_data()
        version = manifest.get("version", "1.0.0")

        with tempfile.TemporaryDirectory(prefix="tokenade-chrome-bundle-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            self._copy_clean_files(tmp_path)

            # Package into zip
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in sorted(tmp_path.rglob("*")):
                    if file_path.is_file():
                        arcname = file_path.relative_to(tmp_path)
                        zf.write(file_path, arcname)

        logger.info(f"Built Chrome extension bundle v{version} -> {output_path}")
        return output_path

    def build_firefox_xpi(self, output_path: Path) -> Path:
        """
        Build a Firefox AMO distribution XPI / zip.
        Ensures gecko ID and background.scripts compatibility fallback are present.
        """
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        manifest = self.get_manifest_data()
        version = manifest.get("version", "1.0.0")

        with tempfile.TemporaryDirectory(prefix="tokenade-firefox-bundle-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            self._copy_clean_files(tmp_path)

            # Ensure Firefox gecko settings in manifest copy
            manifest_copy = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
            if "browser_specific_settings" not in manifest_copy:
                manifest_copy["browser_specific_settings"] = {
                    "gecko": {
                        "id": "tokenade@tokenade.dev",
                        "data_collection_permissions": {"required": ["none"]}
                    }
                }
            if "background" in manifest_copy:
                if "scripts" not in manifest_copy["background"]:
                    manifest_copy["background"]["scripts"] = ["background.js"]

            (tmp_path / "manifest.json").write_text(json.dumps(manifest_copy, indent=2), encoding="utf-8")

            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in sorted(tmp_path.rglob("*")):
                    if file_path.is_file():
                        arcname = file_path.relative_to(tmp_path)
                        zf.write(file_path, arcname)

        logger.info(f"Built Firefox extension bundle v{version} -> {output_path}")
        return output_path

    def _copy_clean_files(self, dest_dir: Path):
        """Copy extension assets excluding development scripts and caches."""
        for item in self.source_dir.rglob("*"):
            if item.is_file():
                # Check exclusions
                rel_parts = set(item.relative_to(self.source_dir).parts)
                if any(p in EXCLUDED_PATTERNS or p.endswith(".py") or p.endswith(".pyc") for p in rel_parts):
                    continue

                rel_path = item.relative_to(self.source_dir)
                target = dest_dir / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
