"""
Chrome Binary Patcher - Remove cdc_ artifacts at the binary level.

ChromeDriver injects `$cdc_*` variables into pages via the Chrome binary.
Bot detection scripts check for these. This module patches the Chrome
binary to replace the cdc_ injection block with benign code of the same
length, preventing detection at the source.

Approach (based on undetected-chromedriver v3.4+):
1. Search for `{window.cdc.*?;}` pattern in the binary
2. Replace with same-length benign code
3. Create patched copy (never modify original)

Usage:
    from tokenade.core.browser.patcher import ChromePatcher
    patcher = ChromePatcher()
    result = patcher.patch("/usr/bin/google-chrome")
"""

import logging
import os
import re
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PatchResult:
    """Result of a binary patch operation."""
    success: bool
    original_path: str
    patched_path: Optional[str] = None
    patches_applied: int = 0
    error: Optional[str] = None
    backup_path: Optional[str] = None

    @property
    def summary(self) -> str:
        if self.success:
            return f"Patched {self.patches_applied} cdc_ artifact(s) -> {self.patched_path}"
        return f"Patch failed: {self.error}"


# Regex pattern for the cdc_ injection block in ChromeDriver/Chrome binary.
# Matches: {window.cdc_asdjflasutopfhvcZLmcfl_Array = ...;}
# The pattern captures the full block including braces.
CDC_PATTERN = re.compile(rb"\{window\.cdc[_ ].{0,120}?\}")

# Replacement: same-length benign code that won't trigger detection.
# Uses console.log which is a no-op in production.
CDC_REPLACEMENT_TEMPLATE = b'{console.log("tokenade")}'


class ChromePatcher:
    """Patches Chrome/Chromium binaries to remove cdc_ artifacts."""

    def __init__(self):
        pass

    def find_browser_binary(self, browser: str = "chrome") -> Optional[str]:
        """Find the system browser binary path.

        Args:
            browser: Browser name (chrome, chromium, brave, edge)

        Returns:
            Path to binary or None if not found
        """
        browser_names = {
            "chrome": [
                "google-chrome", "google-chrome-stable",
                "chrome", "google-chrome-beta", "google-chrome-dev",
            ],
            "chromium": ["chromium", "chromium-browser"],
            "brave": ["brave-browser", "brave"],
            "edge": ["microsoft-edge", "microsoft-edge-stable", "microsoft-edge-dev"],
        }

        names = browser_names.get(browser, [browser])

        # Check PATH first
        for name in names:
            path = shutil.which(name)
            if path:
                return path

        # Check common installation paths (Linux)
        common_paths = {
            "chrome": [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/opt/google/chrome/chrome",
                "/usr/bin/chromium",
            ],
            "chromium": [
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
            ],
            "brave": [
                "/usr/bin/brave-browser",
                "/usr/bin/brave",
            ],
            "edge": [
                "/usr/bin/microsoft-edge",
                "/usr/bin/microsoft-edge-stable",
            ],
        }

        for path in common_paths.get(browser, []):
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path

        return None

    def scan(self, binary_path: str) -> dict:
        """Scan a binary for cdc_ artifacts without modifying it.

        Args:
            binary_path: Path to the browser binary

        Returns:
            Dict with scan results: matches, offsets, sizes
        """
        binary_path = os.path.abspath(binary_path)

        if not os.path.isfile(binary_path):
            return {"error": f"File not found: {binary_path}", "matches": []}

        with open(binary_path, "rb") as f:
            content = f.read()

        matches = []
        for match in CDC_PATTERN.finditer(content):
            matched_bytes = match.group()
            # Find the full block: from the opening { to the matching }
            start = match.start()
            end = match.end()
            matches.append({
                "offset": start,
                "length": end - start,
                "raw": matched_bytes,
                "hex": matched_bytes.hex(),
            })

        return {
            "binary": binary_path,
            "size": len(content),
            "matches": matches,
            "patchable": len(matches) > 0,
        }

    def _make_replacement(self, original_length: int) -> bytes:
        """Create a replacement of the exact same byte length.

        Args:
            original_length: Length of the original matched bytes

        Returns:
            Replacement bytes of the same length, padded with spaces
        """
        template = CDC_REPLACEMENT_TEMPLATE
        if len(template) >= original_length:
            return template[:original_length]
        # Pad with spaces to match exact length
        return template + b" " * (original_length - len(template))

    def patch(
        self,
        binary_path: str,
        output_path: Optional[str] = None,
        backup: bool = True,
    ) -> PatchResult:
        """Patch a Chrome binary to remove cdc_ artifacts.

        Args:
            binary_path: Path to the browser binary to patch
            output_path: Where to save patched binary (default: same dir, .patched suffix)
            backup: Create backup of original before patching

        Returns:
            PatchResult with details
        """
        binary_path = os.path.abspath(binary_path)

        if not os.path.isfile(binary_path):
            return PatchResult(
                success=False,
                original_path=binary_path,
                error=f"File not found: {binary_path}",
            )

        # Read binary
        with open(binary_path, "rb") as f:
            content = f.read()

        original_size = len(content)

        # Find all cdc_ matches
        matches = list(CDC_PATTERN.finditer(content))
        if not matches:
            return PatchResult(
                success=False,
                original_path=binary_path,
                error="No cdc_ artifacts found — binary is clean or uses unknown pattern",
            )

        logger.info(f"Found {len(matches)} cdc_ artifact(s) in {binary_path}")

        # Build patched content (process in reverse to preserve offsets)
        patched = bytearray(content)
        patches_applied = 0

        for match in reversed(matches):
            start = match.start()
            end = match.end()
            original_bytes = match.group()
            replacement = self._make_replacement(len(original_bytes))

            patched[start:end] = replacement
            patches_applied += 1

            logger.debug(
                f"  Patched offset {start}: {original_bytes[:40]}... -> {replacement[:40]}..."
            )

        # Verify size unchanged
        if len(patched) != original_size:
            return PatchResult(
                success=False,
                original_path=binary_path,
                error=f"Size mismatch: {original_size} -> {len(patched)}",
            )

        # Determine output path
        if output_path is None:
            output_path = binary_path + ".patched"
        output_path = os.path.abspath(output_path)

        # Create backup
        backup_path = None
        if backup:
            backup_path = binary_path + ".backup"
            shutil.copy2(binary_path, backup_path)
            logger.info(f"Backup created: {backup_path}")

        # Write patched binary
        with open(output_path, "wb") as f:
            f.write(patched)

        # Make executable (match original permissions)
        original_stat = os.stat(binary_path)
        os.chmod(output_path, original_stat.st_mode)

        logger.info(f"Patched binary saved: {output_path}")

        return PatchResult(
            success=True,
            original_path=binary_path,
            patched_path=output_path,
            patches_applied=patches_applied,
            backup_path=backup_path,
        )

    def restore(self, binary_path: str) -> bool:
        """Restore a binary from its backup.

        Args:
            binary_path: Path to the binary (looks for .backup sibling)

        Returns:
            True if restored successfully
        """
        backup_path = binary_path + ".backup"
        if not os.path.isfile(backup_path):
            logger.error(f"No backup found: {backup_path}")
            return False

        shutil.copy2(backup_path, binary_path)
        logger.info(f"Restored {binary_path} from backup")
        return True

    def verify(self, binary_path: str) -> dict:
        """Verify whether a binary has been patched.

        Checks the patched variant first (if it exists), then the original.

        Args:
            binary_path: Path to the binary

        Returns:
            Dict with verification results
        """
        binary_path = os.path.abspath(binary_path)
        patched_path = binary_path + ".patched"
        has_backup = os.path.isfile(binary_path + ".backup")
        has_patched = os.path.isfile(patched_path)

        # If a patched variant exists, scan that
        if has_patched:
            scan = self.scan(patched_path)
            return {
                "binary": binary_path,
                "patched": not scan.get("patchable", False),
                "has_backup": has_backup,
                "has_patched_variant": has_patched,
                "remaining_artifacts": len(scan.get("matches", [])),
            }

        # Fall back to scanning the original
        scan = self.scan(binary_path)
        return {
            "binary": binary_path,
            "patched": not scan.get("patchable", False),
            "has_backup": has_backup,
            "has_patched_variant": has_patched,
            "remaining_artifacts": len(scan.get("matches", [])),
        }
