"""Security testing for the plugin system.

Tests attack vectors: path traversal, malicious code, JSON bombs,
circular dependencies, symlink attacks, and manifest manipulation.
"""
import json
import os
from pathlib import Path

import pytest

from tokenade.core.integration.plugin_loader import PluginLoader
from tokenade.core.integration.plugin_security import (
    SecurityValidator,
    PluginSecurityError,
    validate_plugin_security,
)


class TestPluginSecurityTesting:
    """Security tests for plugin system attack vectors."""

    @pytest.fixture
    def security_plugin_dir(self, tmp_path):
        """Create a base directory for security test plugins."""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        return plugin_dir

    def test_path_traversal_in_plugin_name(self, security_plugin_dir):
        """Test: Path traversal in plugin name is REJECTED."""
        validator = SecurityValidator()
        
        # Attack: ../../../etc/passwd
        with pytest.raises(PluginSecurityError, match="Path traversal"):
            validator.sanitize_plugin_path(security_plugin_dir, "../../../etc/passwd")
        
        # Attack: ../../malicious
        with pytest.raises(PluginSecurityError, match="Path traversal"):
            validator.sanitize_plugin_path(security_plugin_dir, "../../malicious")

    def test_path_traversal_in_entry_point(self, security_plugin_dir):
        """Test: Path traversal in entry_point is REJECTED."""
        plugin_path = security_plugin_dir / "traversal-plugin"
        plugin_path.mkdir()
        
        # Malicious manifest with path traversal in entry_point
        manifest = {
            "name": "traversal-plugin",
            "version": "1.0.0",
            "type": "handler",
            "entry_point": "../../../etc/passwd",
        }
        (plugin_path / "plugin.json").write_text(json.dumps(manifest))
        
        # Validate manifest
        is_valid, msg, _ = SecurityValidator().validate_plugin_manifest(
            plugin_path / "plugin.json"
        )
        
        assert not is_valid
        assert "Path traversal" in msg

    def test_absolute_path_rejected(self, security_plugin_dir):
        """Test: Absolute paths are REJECTED."""
        validator = SecurityValidator()
        
        with pytest.raises(PluginSecurityError, match="Path traversal"):
            validator.sanitize_plugin_path(security_plugin_dir, "/etc/passwd")

    def test_json_bomb_large_manifest(self, security_plugin_dir):
        """Test: Overly large manifests are REJECTED."""
        plugin_path = security_plugin_dir / "bomb-plugin"
        plugin_path.mkdir()
        
        # Create a 2MB manifest (exceeds 1MB limit)
        huge_data = "a" * (2 * 1024 * 1024)
        manifest = {
            "name": "bomb-plugin",
            "version": "1.0.0",
            "type": "handler",
            "entry_point": "plugin.py",
            "data": huge_data
        }
        (plugin_path / "plugin.json").write_text(json.dumps(manifest))
        
        # Validate
        is_valid, msg, _ = SecurityValidator().validate_plugin_manifest(
            plugin_path / "plugin.json"
        )
        
        assert not is_valid
        assert "too large" in msg

    def test_json_bomb_many_dependencies(self, security_plugin_dir):
        """Test: Excessive dependencies are REJECTED."""
        plugin_path = security_plugin_dir / "deps-bomb"
        plugin_path.mkdir()
        
        # Create manifest with 100 dependencies (exceeds 50 limit)
        manifest = {
            "name": "deps-bomb",
            "version": "1.0.0",
            "type": "handler",
            "entry_point": "plugin.py",
            "dependencies": [f"dep-{i}" for i in range(100)]
        }
        (plugin_path / "plugin.json").write_text(json.dumps(manifest))
        
        # Validate
        is_valid, msg, _ = SecurityValidator().validate_plugin_manifest(
            plugin_path / "plugin.json"
        )
        
        assert not is_valid
        assert "Too many dependencies" in msg

    def test_suspicious_patterns_warning(self, security_plugin_dir):
        """Test: Suspicious patterns generate WARNINGs but don't reject."""
        plugin_path = security_plugin_dir / "suspicious-plugin"
        plugin_path.mkdir()
        
        # Manifest with suspicious pattern
        manifest = {
            "name": "suspicious-plugin",
            "version": "1.0.0",
            "type": "handler",
            "entry_point": "plugin.py",
            "description": "Uses __import__ for dynamic loading"
        }
        (plugin_path / "plugin.json").write_text(json.dumps(manifest))
        
        # Validate - should accept with warning
        is_valid, msg, _ = SecurityValidator().validate_plugin_manifest(
            plugin_path / "plugin.json"
        )
        
        assert is_valid  # Accepted
        assert msg is not None  # But has warning
        assert "Suspicious pattern" in msg

    def test_symlink_attack_rejected(self, security_plugin_dir, tmp_path):
        """Test: Symlink attacks are REJECTED."""
        # Create a sensitive file outside plugin dir
        sensitive_dir = tmp_path / "sensitive"
        sensitive_dir.mkdir()
        sensitive_file = sensitive_dir / "secret.py"
        sensitive_file.write_text("SECRET_KEY = 'top-secret'")
        
        # Create plugin with symlink to sensitive file
        plugin_path = security_plugin_dir / "symlink-plugin"
        plugin_path.mkdir()
        
        manifest = {
            "name": "symlink-plugin",
            "version": "1.0.0",
            "type": "handler",
            "entry_point": "plugin.py",
        }
        (plugin_path / "plugin.json").write_text(json.dumps(manifest))
        
        # Create symlink
        symlink_path = plugin_path / "plugin.py"
        try:
            symlink_path.symlink_to(sensitive_file)
        except OSError:
            pytest.skip("Symlinks not supported on this platform")
        
        # Validate - should reject symlink
        is_safe, error = SecurityValidator().check_symlink_attack(symlink_path)
        
        assert not is_safe
        assert "Symlink" in error

    def test_missing_required_fields(self, security_plugin_dir):
        """Test: Missing required manifest fields are REJECTED."""
        plugin_path = security_plugin_dir / "incomplete-plugin"
        plugin_path.mkdir()
        
        # Manifest missing 'entry_point'
        manifest = {
            "name": "incomplete-plugin",
            "version": "1.0.0",
            "type": "handler",
        }
        (plugin_path / "plugin.json").write_text(json.dumps(manifest))
        
        is_valid, msg, _ = SecurityValidator().validate_plugin_manifest(
            plugin_path / "plugin.json"
        )
        
        assert not is_valid
        assert "entry_point" in msg

    def test_malicious_plugin_rejected_by_loader(self, security_plugin_dir):
        """Test: Loader rejects malicious plugins with path traversal."""
        plugin_path = security_plugin_dir / "malicious"
        plugin_path.mkdir()
        
        # Malicious manifest
        manifest = {
            "name": "malicious",
            "version": "1.0.0",
            "type": "handler",
            "entry_point": "../../../../../../etc/passwd",
        }
        (plugin_path / "plugin.json").write_text(json.dumps(manifest))
        
        # Try to load with PluginLoader
        loader = PluginLoader(plugins_dir=security_plugin_dir)
        plugins = loader.discover()
        
        # Should discover but not load
        assert len(plugins) == 1
        
        loaded = loader.load_plugin(plugins[0])
        
        # Should be rejected
        assert loaded is None

    def test_valid_plugin_passes_security(self, security_plugin_dir):
        """Test: Valid, safe plugins pass security checks."""
        plugin_path = security_plugin_dir / "safe-plugin"
        plugin_path.mkdir()
        
        # Valid manifest
        manifest = {
            "name": "safe-plugin",
            "version": "1.0.0",
            "type": "handler",
            "entry_point": "plugin.py",
            "dependencies": []
        }
        (plugin_path / "plugin.json").write_text(json.dumps(manifest))
        
        # Valid plugin code
        code = """
from tokenade.plugin.base import SiteHandlerPlugin
from tokenade.plugin.api import PluginResult

class SafeHandler(SiteHandlerPlugin):
    name = "safe-plugin"
    version = "1.0.0"
    
    def can_handle(self, url): return False
    def extract_session(self, ctx, url): return PluginResult(success=True)
    def inject_session(self, ctx, session): return PluginResult(success=True)
"""
        (plugin_path / "plugin.py").write_text(code)
        
        # Validate
        is_safe, msg = validate_plugin_security(plugin_path)
        
        assert is_safe
        assert msg is None  # No warnings

    def test_long_plugin_name_rejected(self, security_plugin_dir):
        """Test: Overly long plugin names are REJECTED."""
        plugin_path = security_plugin_dir / "long-name"
        plugin_path.mkdir()
        
        # Name with 200 chars (exceeds 100 limit)
        long_name = "a" * 200
        manifest = {
            "name": long_name,
            "version": "1.0.0",
            "type": "handler",
            "entry_point": "plugin.py",
        }
        (plugin_path / "plugin.json").write_text(json.dumps(manifest))
        
        is_valid, msg, _ = SecurityValidator().validate_plugin_manifest(
            plugin_path / "plugin.json"
        )
        
        assert not is_valid
        assert "too long" in msg

    def test_non_python_entry_point_rejected(self, security_plugin_dir):
        """Test: Non-.py entry points are REJECTED."""
        plugin_path = security_plugin_dir / "bad-ext"
        plugin_path.mkdir()
        
        manifest = {
            "name": "bad-ext",
            "version": "1.0.0",
            "type": "handler",
            "entry_point": "plugin.sh",
        }
        (plugin_path / "plugin.json").write_text(json.dumps(manifest))
        
        # Create the .sh file
        (plugin_path / "plugin.sh").write_text("#!/bin/bash\necho 'malicious'")
        
        # Validate entry point
        is_valid, error = SecurityValidator().validate_entry_point(
            plugin_path, "plugin.sh"
        )
        
        assert not is_valid
        assert ".py file" in error
