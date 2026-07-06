"""
Plugin verification via SHA256 checksums.

Verifies that installed plugins match known-good checksums
from the registry to detect tampering or corruption.
"""

import hashlib
import json
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of plugin verification."""
    plugin_name: str
    verified: bool
    file_count: int
    files_checked: int
    checksums_match: int
    checksums_mismatch: int
    errors: List[str]

    @property
    def summary(self) -> str:
        if self.verified:
            return f"OK ({self.checksums_match}/{self.files_checked} files verified)"
        return f"FAILED ({self.checksums_mismatch} checksum mismatches, {len(self.errors)} errors)"


class PluginVerifier:
    """Verify installed plugins against registry checksums."""

    def __init__(self, plugins_dir: Path = None):
        from tokenade.core.integration.plugin_registry import DEFAULT_PLUGINS_DIR
        self.plugins_dir = plugins_dir or DEFAULT_PLUGINS_DIR
        self._checksums_file = self.plugins_dir / ".checksums.json"
        self._local_checksums = self._load_checksums()

    def verify(self, plugin_name: str) -> VerificationResult:
        """Verify a single plugin's checksums against registry data."""
        plugin_dir = self.plugins_dir / plugin_name
        if not plugin_dir.exists():
            return VerificationResult(
                plugin_name=plugin_name,
                verified=False,
                file_count=0,
                files_checked=0,
                checksums_match=0,
                checksums_mismatch=0,
                errors=[f"Plugin directory not found: {plugin_dir}"],
            )

        expected = self._get_expected_checksums(plugin_name)
        if not expected:
            return VerificationResult(
                plugin_name=plugin_name,
                verified=False,
                file_count=0,
                files_checked=0,
                checksums_match=0,
                checksums_mismatch=0,
                errors=["No checksum data available for this plugin"],
            )

        files_checked = 0
        checksums_match = 0
        checksums_mismatch = 0
        errors = []

        for filename, expected_hash in expected.items():
            filepath = plugin_dir / filename
            if not filepath.exists():
                errors.append(f"Missing file: {filename}")
                checksums_mismatch += 1
                files_checked += 1
                continue

            try:
                actual_hash = self._compute_sha256(filepath)
                files_checked += 1
                if actual_hash == expected_hash:
                    checksums_match += 1
                else:
                    checksums_mismatch += 1
                    errors.append(f"Checksum mismatch: {filename}")
            except OSError as e:
                errors.append(f"Error reading {filename}: {e}")
                files_checked += 1
                checksums_mismatch += 1

        verified = checksums_mismatch == 0 and files_checked > 0

        return VerificationResult(
            plugin_name=plugin_name,
            verified=verified,
            file_count=len(expected),
            files_checked=files_checked,
            checksums_match=checksums_match,
            checksums_mismatch=checksums_mismatch,
            errors=errors,
        )

    def verify_all(self) -> List[VerificationResult]:
        """Verify all installed plugins."""
        results = []
        for plugin_dir in sorted(self.plugins_dir.iterdir()):
            if not plugin_dir.is_dir() or plugin_dir.name.startswith("."):
                continue
            if (plugin_dir / "plugin.json").exists():
                results.append(self.verify(plugin_dir.name))
        return results

    def store_checksums(self, plugin_name: str, checksums: Dict[str, str]) -> None:
        """Store expected checksums for a plugin (from registry)."""
        self._local_checksums[plugin_name] = checksums
        self._save_checksums()

    def compute_plugin_checksums(self, plugin_name: str) -> Dict[str, str]:
        """Compute checksums for all files in a plugin directory."""
        plugin_dir = self.plugins_dir / plugin_name
        if not plugin_dir.exists():
            return {}

        checksums = {}
        for filepath in sorted(plugin_dir.rglob("*")):
            if filepath.is_file() and not filepath.name.startswith("."):
                rel_path = str(filepath.relative_to(plugin_dir))
                try:
                    checksums[rel_path] = self._compute_sha256(filepath)
                except OSError as e:
                    logger.warning(f"Failed to compute checksum for {filepath}: {e}")

        return checksums

    def register_plugin(self, plugin_name: str) -> Dict[str, str]:
        """Compute and store checksums for a newly installed plugin."""
        checksums = self.compute_plugin_checksums(plugin_name)
        if checksums:
            self.store_checksums(plugin_name, checksums)
        return checksums

    def _get_expected_checksums(self, plugin_name: str) -> Dict[str, str]:
        """Get expected checksums from registry cache or local store."""
        # Check local checksums first
        if plugin_name in self._local_checksums:
            return self._local_checksums[plugin_name]

        # Try to load from registry cache
        cache_file = self.plugins_dir / ".registry_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    cache = json.load(f)
                for p in cache.get("plugins", []):
                    if p.get("name") == plugin_name and "checksums" in p:
                        return p["checksums"]
            except (json.JSONDecodeError, OSError):
                pass

        return {}

    @staticmethod
    def _compute_sha256(filepath: Path) -> str:
        """Compute SHA256 hash of a file."""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _load_checksums(self) -> Dict:
        """Load checksums from disk."""
        if self._checksums_file.exists():
            try:
                with open(self._checksums_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_checksums(self):
        """Save checksums to disk."""
        try:
            with open(self._checksums_file, "w") as f:
                json.dump(self._local_checksums, f, indent=2)
        except OSError as e:
            logger.warning(f"Failed to save checksums: {e}")
