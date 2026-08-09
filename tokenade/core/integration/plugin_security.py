"""Security validators for the plugin system.

Provides path sanitization, manifest validation, and attack detection
to prevent malicious plugins from compromising the system.

Security model: Hybrid approach
- REJECT critical threats (path traversal, injection)
- WARN for suspicious patterns (unusual names, large files)
"""
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class PluginSecurityError(Exception):
    """Raised when a plugin fails security validation."""
    pass


class SecurityValidator:
    """Validates plugin security and sanitizes inputs."""

    # Max manifest size: 1MB
    MAX_MANIFEST_SIZE = 1024 * 1024
    
    # Max plugin name/version length
    MAX_NAME_LENGTH = 100
    MAX_VERSION_LENGTH = 20
    
    # Max dependencies count
    MAX_DEPENDENCIES = 50
    
    # Forbidden path patterns (path traversal)
    FORBIDDEN_PATTERNS = [
        r"\.\.",  # Parent directory traversal
        r"^/",    # Absolute paths
        r"^~",    # Home directory
        r"\\",    # Windows path separators
    ]
    
    # Suspicious patterns (warn but don't reject)
    SUSPICIOUS_PATTERNS = [
        r"__import__",
        r"eval\(",
        r"exec\(",
        r"subprocess",
        r"os\.system",
    ]

    @staticmethod
    def sanitize_plugin_path(base_dir: Path, plugin_name: str) -> Path:
        """Sanitize and validate plugin path to prevent traversal attacks.
        
        Args:
            base_dir: Base plugin directory
            plugin_name: Plugin name from manifest
            
        Returns:
            Validated absolute path
            
        Raises:
            PluginSecurityError: If path traversal detected
        """
        # Check for forbidden patterns
        for pattern in SecurityValidator.FORBIDDEN_PATTERNS:
            if re.search(pattern, plugin_name):
                raise PluginSecurityError(
                    f"Path traversal detected in plugin name: {plugin_name}"
                )
        
        # Construct path and resolve
        plugin_path = (base_dir / plugin_name).resolve()
        base_resolved = base_dir.resolve()
        
        # Verify path is within base directory
        try:
            plugin_path.relative_to(base_resolved)
        except ValueError:
            raise PluginSecurityError(
                f"Plugin path {plugin_path} is outside base directory {base_resolved}"
            )
        
        return plugin_path

    @staticmethod
    def validate_plugin_manifest(manifest_path: Path) -> Tuple[bool, Optional[str], Dict]:
        """Validate plugin manifest for security issues.
        
        Args:
            manifest_path: Path to plugin.json
            
        Returns:
            (is_valid, error_or_warning, manifest_data)
            - is_valid: False = reject, True = accept (may have warnings)
            - error_or_warning: None if clean, message if issue
            - manifest_data: Parsed manifest or empty dict
        """
        # Check file size
        try:
            file_size = manifest_path.stat().st_size
            if file_size > SecurityValidator.MAX_MANIFEST_SIZE:
                return (False, f"Manifest too large: {file_size} bytes (max {SecurityValidator.MAX_MANIFEST_SIZE})", {})
        except OSError as e:
            return (False, f"Cannot read manifest: {e}", {})
        
        # Parse JSON
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except json.JSONDecodeError as e:
            return (False, f"Invalid JSON: {e}", {})
        except OSError as e:
            return (False, f"Cannot read manifest: {e}", {})
        
        # Validate required fields
        if not isinstance(manifest, dict):
            return (False, "Manifest must be a JSON object", {})
        
        name = manifest.get("name", "")
        if not name or not isinstance(name, str):
            return (False, "Missing or invalid 'name' field", {})
        
        if len(name) > SecurityValidator.MAX_NAME_LENGTH:
            return (False, f"Plugin name too long: {len(name)} chars (max {SecurityValidator.MAX_NAME_LENGTH})", {})
        
        version = manifest.get("version", "")
        if not version or not isinstance(version, str):
            return (False, "Missing or invalid 'version' field", {})
        
        if len(version) > SecurityValidator.MAX_VERSION_LENGTH:
            return (False, f"Version string too long: {len(version)} chars (max {SecurityValidator.MAX_VERSION_LENGTH})", {})
        
        entry_point = manifest.get("entry_point", "")
        if not entry_point or not isinstance(entry_point, str):
            return (False, "Missing or invalid 'entry_point' field", {})
        
        # Check for path traversal in entry_point
        for pattern in SecurityValidator.FORBIDDEN_PATTERNS:
            if re.search(pattern, entry_point):
                return (False, f"Path traversal detected in entry_point: {entry_point}", {})
        
        # Check dependencies count
        dependencies = manifest.get("dependencies", [])
        if not isinstance(dependencies, list):
            return (False, "dependencies must be a list", {})
        
        if len(dependencies) > SecurityValidator.MAX_DEPENDENCIES:
            return (False, f"Too many dependencies: {len(dependencies)} (max {SecurityValidator.MAX_DEPENDENCIES})", {})
        if any(not isinstance(dep, str) or not dep.strip() for dep in dependencies):
            return (False, "dependencies entries must be non-empty strings", {})
        if len(set(dependencies)) != len(dependencies):
            return (False, "dependencies must not contain duplicates", {})
        if name in dependencies:
            return (False, "plugin cannot depend on itself", {})

        from tokenade.core.integration.plugin_dependencies import validate_runtime_dependency_manifest
        runtime_errors = validate_runtime_dependency_manifest(manifest)
        if runtime_errors:
            return (False, runtime_errors[0], {})
        
        # Check for suspicious patterns (warning, not rejection)
        manifest_str = json.dumps(manifest)
        for pattern in SecurityValidator.SUSPICIOUS_PATTERNS:
            if re.search(pattern, manifest_str):
                logger.warning(f"Suspicious pattern in manifest: {pattern}")
                return (True, f"Warning: Suspicious pattern detected: {pattern}", manifest)
        
        return (True, None, manifest)

    @staticmethod
    def check_symlink_attack(path: Path) -> Tuple[bool, Optional[str]]:
        """Check if path is a symlink pointing outside allowed directories.
        
        Args:
            path: Path to check
            
        Returns:
            (is_safe, error_message)
        """
        if not path.exists():
            return (True, None)
        
        # Check if it's a symlink
        if path.is_symlink():
            target = path.resolve()
            
            # If symlink, verify target is in safe location
            # For now, reject all symlinks to be safe
            return (False, f"Symlinks not allowed: {path} -> {target}")
        
        return (True, None)

    @staticmethod
    def validate_entry_point(plugin_dir: Path, entry_point: str) -> Tuple[bool, Optional[str]]:
        """Validate entry point file exists and is safe.
        
        Args:
            plugin_dir: Plugin directory
            entry_point: Entry point path from manifest
            
        Returns:
            (is_valid, error_message)
        """
        # Sanitize entry point path
        try:
            entry_path = SecurityValidator.sanitize_plugin_path(plugin_dir, entry_point)
        except PluginSecurityError as e:
            return (False, str(e))
        
        # Check if file exists
        if not entry_path.exists():
            return (False, f"Entry point not found: {entry_point}")
        
        if not entry_path.is_file():
            return (False, f"Entry point is not a file: {entry_point}")
        
        # Check for symlink attack
        is_safe, error = SecurityValidator.check_symlink_attack(entry_path)
        if not is_safe:
            return (False, error)
        
        # Check file extension
        if entry_path.suffix != ".py":
            return (False, f"Entry point must be a .py file: {entry_point}")
        
        return (True, None)


def validate_plugin_security(plugin_dir: Path) -> Tuple[bool, Optional[str]]:
    """Comprehensive security validation for a plugin.
    
    Args:
        plugin_dir: Path to plugin directory
        
    Returns:
        (is_safe, error_or_warning_message)
    """
    validator = SecurityValidator()
    
    # Check plugin directory itself
    is_safe, error = validator.check_symlink_attack(plugin_dir)
    if not is_safe:
        return (False, f"Plugin directory: {error}")
    
    # Check manifest
    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.exists():
        return (False, "plugin.json not found")
    
    is_valid, msg, manifest = validator.validate_plugin_manifest(manifest_path)
    if not is_valid:
        return (False, f"Manifest validation: {msg}")
    
    # Check entry point
    entry_point = manifest.get("entry_point", "")
    if entry_point:
        is_valid, error = validator.validate_entry_point(plugin_dir, entry_point)
        if not is_valid:
            return (False, f"Entry point validation: {error}")
    
    # Return with warning if any
    return (True, msg)
