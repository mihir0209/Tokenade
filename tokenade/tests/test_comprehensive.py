"""
Comprehensive integration tests for Tokenade.

Tests end-to-end workflows: extract → package → export → import → proxy.
"""
import json
import tempfile
from pathlib import Path
import pytest


class TestEndToEndExportImport:
    """Test full export → import workflow."""
    
    def test_export_to_playwright_and_import_back(self, sample_session, tmp_path):
        """Export to Playwright format, import back, verify cookies preserved."""
        from tokenade.core.importer.format_exporter import FormatExporter
        from tokenade.core.importer.format_importer import FormatImporter
        
        # Export
        exporter = FormatExporter(sample_session)
        playwright_json = exporter.to_playwright_storagestate()
        
        # Save to file
        ps_file = tmp_path / "storage_state.json"
        ps_file.write_text(playwright_json)
        
        # Import back
        imported = FormatImporter.from_playwright_storagestate(str(ps_file))
        
        # Verify cookies preserved
        assert len(imported["cookies"]) == len(sample_session["cookies"])
        for orig, imp in zip(sample_session["cookies"], imported["cookies"]):
            assert orig["name"] == imp["name"]
            assert orig["value"] == imp["value"]
            assert orig["domain"] == imp["domain"]
    
    def test_export_to_netscape_and_import_back(self, sample_session, tmp_path):
        """Export to Netscape, import back, verify cookies preserved."""
        from tokenade.core.importer.format_exporter import FormatExporter
        from tokenade.core.importer.format_importer import FormatImporter
        
        exporter = FormatExporter(sample_session)
        netscape = exporter.to_netscape()
        
        ns_file = tmp_path / "cookies.txt"
        ns_file.write_text(netscape)
        
        imported = FormatImporter.from_netscape(str(ns_file))
        
        assert len(imported["cookies"]) == len(sample_session["cookies"])
    
    def test_export_to_header_and_back(self, sample_session):
        """Export to cookie header, import back, verify."""
        from tokenade.core.importer.format_exporter import FormatExporter
        from tokenade.core.importer.format_importer import FormatImporter
        
        exporter = FormatExporter(sample_session)
        header = exporter.to_cookie_header()
        
        imported = FormatImporter.from_cookie_header(header, domain=".example.com")
        
        assert len(imported["cookies"]) == len(sample_session["cookies"])
    
    def test_format_detection(self, sample_session, tmp_path):
        """Format auto-detection should identify Playwright vs Netscape."""
        from tokenade.core.importer.format_exporter import FormatExporter
        from tokenade.core.importer.format_importer import FormatImporter
        
        exporter = FormatExporter(sample_session)
        
        # Playwright
        ps_file = tmp_path / "state.json"
        ps_file.write_text(exporter.to_playwright_storagestate())
        assert FormatImporter.detect_format(str(ps_file)) == "playwright"
        
        # Netscape
        ns_file = tmp_path / "cookies.txt"
        ns_file.write_text(exporter.to_netscape())
        assert FormatImporter.detect_format(str(ns_file)) == "netscape"


class TestSessionVaultWorkflow:
    """Test session vault end-to-end workflow."""
    
    def test_add_update_get_remove(self, sample_session, tmp_path):
        """Full vault lifecycle: add, update, get, remove."""
        from tokenade.core.importer.session_vault import SessionVault
        
        vault = SessionVault(str(tmpdir := tmp_path / "vault"))
        
        # Create session file
        session_file = tmp_path / "test.tokenade"
        session_file.write_text(json.dumps(sample_session))
        
        # Add
        sid = vault.add(str(session_file), tags=["test", "integration"])
        assert sid
        
        # Get
        retrieved = vault.get(sid)
        assert retrieved is not None
        assert retrieved["site_name"] == sample_session["site_name"]
        
        # Update
        sample_session["cookies"].append({
            "name": "new_cookie", "value": "new_val",
            "domain": ".example.com", "path": "/",
        })
        session_file.write_text(json.dumps(sample_session))
        vault.update(sid, str(session_file))
        
        # Verify update
        updated = vault.get(sid)
        assert len(updated["cookies"]) == len(sample_session["cookies"])
        
        # List
        entries = vault.list_sessions(site_filter="example")
        assert len(entries) == 1
        
        # Remove
        assert vault.remove(sid)
        assert vault.get(sid) is None
    
    def test_vault_acl_workflow(self, sample_session, tmp_path):
        """Test ACL set and permission check workflow."""
        from tokenade.core.importer.session_vault import SessionVault
        
        vault = SessionVault(str(tmp_path / "vault"))
        session_file = tmp_path / "test.tokenade"
        session_file.write_text(json.dumps(sample_session))
        
        sid = vault.add(str(session_file), owner="admin")
        
        # Owner has all permissions
        assert vault.check_permission(sid, "admin", "read")
        assert vault.check_permission(sid, "admin", "write")
        assert vault.check_permission(sid, "admin", "delete")
        
        # Grant read to user
        vault.set_acl(sid, "user1", ["read"])
        assert vault.check_permission(sid, "user1", "read")
        assert not vault.check_permission(sid, "user1", "write")
        
        # No access for unknown user
        assert not vault.check_permission(sid, "unknown", "read")


class TestHealthScoringWorkflow:
    """Test health scoring end-to-end workflow."""
    
    def test_perfect_session_scores_high(self):
        """A fresh, secure session should score well."""
        from tokenade.core.refresh.health_scorer import SessionHealthScorer
        
        session = {
            "version": "2.0",
            "created_at": "2099-01-01T00:00:00Z",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [
                {
                    "name": "SID",
                    "value": "aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW",
                    "domain": ".google.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                    "sameSite": "Lax",
                    "expires": 2000000000,
                },
                {
                    "name": "HSID",
                    "value": "aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW",
                    "domain": ".google.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                    "sameSite": "Lax",
                    "expires": 2000000000,
                },
            ],
        }
        
        scorer = SessionHealthScorer()
        result = scorer.score(session)
        assert result.total_score >= 70, f"Expected score >= 70, got {result.total_score}"
    
    def test_expired_session_scores_low(self):
        """An expired session should score poorly."""
        from tokenade.core.refresh.health_scorer import SessionHealthScorer
        
        session = {
            "version": "2.0",
            "created_at": "2020-01-01T00:00:00Z",
            "site_name": "test",
            "auth_status": "logged_out",
            "cookies": [
                {
                    "name": "old_cookie",
                    "value": "abc",
                    "domain": ".test.com",
                    "path": "/",
                    "secure": False,
                    "httpOnly": False,
                    "sameSite": "",
                    "expires": 1500000000,  # 2017
                },
            ],
        }
        
        scorer = SessionHealthScorer()
        result = scorer.score(session)
        assert result.total_score < 40, f"Expected score < 40, got {result.total_score}"
        assert len(result.issues) > 0


class TestAntidetectionWorkflow:
    """Test anti-detection features end-to-end."""
    
    def test_cdp_cleaner_scripts_are_valid_js(self):
        """All stealth scripts should be valid JavaScript."""
        from tokenade.core.antidetection.cdp_cleaner import CDPCleaner
        
        scripts = CDPCleaner.get_stealth_scripts()
        assert len(scripts) > 0
        
        # Each script should be non-empty and contain JS syntax
        for script in scripts:
            assert len(script.strip()) > 0
            # Should contain some JS construct
            assert any(kw in script for kw in ["navigator", "window", "Object", "delete", "undefined"])
    
    def test_behavioral_injector_generates_paths(self):
        """Mouse path generation should produce reasonable output."""
        from tokenade.core.antidetection.behavioral import BehavioralInjector
        
        path = BehavioralInjector.generate_mouse_path((0, 0), (500, 500))
        assert len(path) > 0
        # Start should be near origin (small jitter from Gaussian)
        assert abs(path[0]["x"]) < 5
        assert abs(path[0]["y"]) < 5
        
        # End should be near target
        last = path[-1]
        assert abs(last["x"] - 500) < 50
        assert abs(last["y"] - 500) < 50
    
    def test_scroll_pattern_generates_steps(self):
        """Scroll pattern should produce scroll events."""
        from tokenade.core.antidetection.behavioral import BehavioralInjector
        
        pattern = BehavioralInjector.generate_scroll_pattern(500)
        assert len(pattern) > 0
        assert all("delta_y" in p for p in pattern)
        assert all("delay_ms" in p for p in pattern)


class TestPluginRegistryWorkflow:
    """Test plugin registry functionality."""
    
    def test_plugin_registry_init(self, tmp_path):
        """Registry should initialize with proper directory structure."""
        from tokenade.core.integration.plugin_registry import PluginRegistry
        
        registry = PluginRegistry(plugins_dir=tmp_path / "plugins")
        assert registry.plugins_dir.exists()
    
    def test_plugin_list_installed_empty(self, tmp_path):
        """Empty registry should return empty list."""
        from tokenade.core.integration.plugin_registry import PluginRegistry
        
        registry = PluginRegistry(plugins_dir=tmp_path / "plugins")
        installed = registry.list_installed()
        assert isinstance(installed, list)
        assert len(installed) == 0


class TestEnterpriseWorkflow:
    """Test enterprise features end-to-end."""
    
    def test_audit_logger_workflow(self, tmp_path):
        """Full audit log workflow: log, query, summary."""
        from tokenade.core.security.audit import AuditLogger
        
        log_file = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_file))
        
        # Log events
        logger.log_event("session_export", session_id="s1", site_name="google")
        logger.log_event("session_share", session_id="s1", method="email")
        logger.log_event("session_export", session_id="s2", site_name="github")
        
        # Query
        events = logger.query_events(event_type="session_export")
        assert len(events) == 2
        
        # Summary
        summary = logger.get_summary()
        assert summary["session_export"] == 2
        assert summary["session_share"] == 1
    
    def test_rbac_workflow(self, tmp_path):
        """Full RBAC workflow: assign, check, revoke."""
        from tokenade.core.security.audit import RoleManager
        
        rbac = RoleManager(storage_path=str(tmp_path / "rbac.json"))
        
        rbac.assign_role("admin@example.com", "admin")
        rbac.assign_role("user@example.com", "viewer")
        
        assert rbac.check_permission("admin@example.com", "revoke_share")
        assert not rbac.check_permission("user@example.com", "revoke_share")
        assert rbac.check_permission("user@example.com", "view_share")
