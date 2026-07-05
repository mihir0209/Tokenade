"""Tests for Phase 67 — New Plugin Ecosystem."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _load_plugin(name):
    """Load a plugin by name from ~/.tokenade/plugins/."""
    import importlib.util
    import sys
    plugin_dir = Path.home() / ".tokenade" / "plugins" / name
    plugin_file = plugin_dir / "plugin.py"
    if not plugin_file.exists():
        return None
    spec = importlib.util.spec_from_file_location(
        f"{name}.plugin", str(plugin_file)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"{name}.plugin"] = mod
    spec.loader.exec_module(mod)
    manifest = plugin_dir / "plugin.json"
    if manifest.exists():
        with open(manifest) as f:
            meta = json.load(f)
        cls_name = meta.get("entry_class", "")
        if hasattr(mod, cls_name):
            return getattr(mod, cls_name)()
    return None


def _plugin_available(name):
    return (Path.home() / ".tokenade" / "plugins" / name).exists()


# ─── Session Backup Tests ───────────────────────────────────

@pytest.mark.skipif(not _plugin_available("session-backup"), reason="not installed")
class TestSessionBackup:
    def _get(self):
        return _load_plugin("session-backup")

    def test_backup_session(self, tmp_path):
        plugin = self._get()
        # Create test session
        session = {
            "version": "2.0", "site_name": "test",
            "cookies": [{"name": "c1", "value": "v1", "domain": ".test.com"}],
        }
        session_file = tmp_path / "test.tokenade"
        session_file.write_text(json.dumps(session))

        result = plugin.backup_session(str(session_file))
        assert result["success"] is True
        assert result["backup_path"] is not None
        assert Path(result["backup_path"]).exists()

    def test_backup_nonexistent(self):
        plugin = self._get()
        result = plugin.backup_session("/nonexistent/file.tokenade")
        assert result["success"] is False

    def test_list_backups_empty(self, tmp_path):
        plugin = self._get()
        plugin.backup_dir = tmp_path / "backups"
        backups = plugin.list_backups()
        assert backups == []

    def test_restore_backup(self, tmp_path):
        plugin = self._get()
        # Create and backup
        session = {"version": "2.0", "cookies": [{"name": "c1", "value": "v1"}]}
        session_file = tmp_path / "test.tokenade"
        session_file.write_text(json.dumps(session))
        result = plugin.backup_session(str(session_file))

        # Restore
        output = tmp_path / "restored.tokenade"
        restore = plugin.restore_backup(result["backup_path"], str(output))
        assert restore["success"] is True
        assert output.exists()


# ─── Session Merge Tests ────────────────────────────────────

@pytest.mark.skipif(not _plugin_available("session-merge"), reason="not installed")
class TestSessionMerge:
    def _get(self):
        return _load_plugin("session-merge")

    def test_merge_sessions(self, tmp_path):
        plugin = self._get()
        s1 = {"cookies": [{"name": "c1", "value": "v1", "domain": ".a.com", "expires": 9999999999}]}
        s2 = {"cookies": [{"name": "c2", "value": "v2", "domain": ".a.com", "expires": 9999999999}]}
        f1 = tmp_path / "s1.tokenade"
        f2 = tmp_path / "s2.tokenade"
        f1.write_text(json.dumps(s1))
        f2.write_text(json.dumps(s2))

        output = tmp_path / "merged.tokenade"
        result = plugin.merge_sessions([str(f1), str(f2)], str(output))
        assert result["success"] is True
        assert result["merged_cookies"] == 2
        assert result["duplicates_removed"] == 0

    def test_merge_deduplicates(self, tmp_path):
        plugin = self._get()
        s1 = {"cookies": [{"name": "c1", "value": "v1", "domain": ".a.com", "expires": 100}]}
        s2 = {"cookies": [{"name": "c1", "value": "v2", "domain": ".a.com", "expires": 200}]}
        f1 = tmp_path / "s1.tokenade"
        f2 = tmp_path / "s2.tokenade"
        f1.write_text(json.dumps(s1))
        f2.write_text(json.dumps(s2))

        output = tmp_path / "merged.tokenade"
        result = plugin.merge_sessions([str(f1), str(f2)], str(output))
        assert result["success"] is True
        assert result["merged_cookies"] == 1
        assert result["duplicates_removed"] == 1

    def test_diff_sessions(self, tmp_path):
        plugin = self._get()
        s1 = {"cookies": [{"name": "c1", "value": "v1", "domain": ".a.com"}]}
        s2 = {"cookies": [{"name": "c2", "value": "v2", "domain": ".a.com"}]}
        f1 = tmp_path / "s1.tokenade"
        f2 = tmp_path / "s2.tokenade"
        f1.write_text(json.dumps(s1))
        f2.write_text(json.dumps(s2))

        diff = plugin.diff_sessions(str(f1), str(f2))
        assert diff["added"] == 1
        assert diff["removed"] == 1


# ─── Proxy Health Tests ─────────────────────────────────────

@pytest.mark.skipif(not _plugin_available("proxy-health"), reason="not installed")
class TestProxyHealth:
    def _get(self):
        return _load_plugin("proxy-health")

    def test_check_health_invalid_proxy(self):
        plugin = self._get()
        result = plugin.check_health("http://invalid-proxy:9999")
        assert result["healthy"] is False
        assert result["latency_ms"] > 0

    def test_check_rotation(self):
        plugin = self._get()
        result = plugin.check_rotation(["http://invalid1:9999", "http://invalid2:9999"])
        assert result["total"] == 2
        assert result["healthy"] == 0


# ─── Session Expiry Alert Tests ─────────────────────────────

@pytest.mark.skipif(not _plugin_available("session-expiry-alert"), reason="not installed")
class TestSessionExpiryAlert:
    def _get(self):
        return _load_plugin("session-expiry-alert")

    def test_check_expiry_healthy(self, tmp_path):
        plugin = self._get()
        session = {
            "cookies": [
                {"name": "c1", "value": "v1", "expires": int(time.time()) + 86400 * 30},
            ]
        }
        f = tmp_path / "test.tokenade"
        f.write_text(json.dumps(session))
        result = plugin.check_expiry(str(f))
        assert result["status"] == "healthy"
        assert result["expired_count"] == 0

    def test_check_expiry_expired(self, tmp_path):
        plugin = self._get()
        session = {
            "cookies": [
                {"name": "c1", "value": "v1", "expires": int(time.time()) - 3600},
            ]
        }
        f = tmp_path / "test.tokenade"
        f.write_text(json.dumps(session))
        result = plugin.check_expiry(str(f))
        assert result["status"] == "expired"
        assert result["expired_count"] == 1

    def test_check_expiry_expiring_soon(self, tmp_path):
        plugin = self._get()
        session = {
            "cookies": [
                {"name": "c1", "value": "v1", "expires": int(time.time()) + 3600},
            ]
        }
        f = tmp_path / "test.tokenade"
        f.write_text(json.dumps(session))
        result = plugin.check_expiry(str(f), warning_hours=24)
        assert result["status"] == "expiring_soon"

    def test_scan_sessions(self, tmp_path):
        plugin = self._get()
        plugin.backup_dir = tmp_path
        session = {
            "cookies": [
                {"name": "c1", "value": "v1", "expires": int(time.time()) + 86400},
            ]
        }
        f = tmp_path / "test.tokenade"
        f.write_text(json.dumps(session))
        results = plugin.scan_sessions(str(tmp_path))
        assert len(results) == 1


# ─── Fingerprint Rotate Tests ───────────────────────────────

@pytest.mark.skipif(not _plugin_available("fingerprint-rotate"), reason="not installed")
class TestFingerprintRotate:
    def _get(self):
        return _load_plugin("fingerprint-rotate")

    def test_generate_fingerprint(self):
        plugin = self._get()
        fp = plugin.generate_fingerprint(seed=42)
        assert "fingerprint_seed" in fp
        assert "gpu_vendor" in fp
        assert "screen_width" in fp
        assert isinstance(fp["fingerprint_seed"], int)

    def test_generate_random(self):
        plugin = self._get()
        fp1 = plugin.generate_fingerprint()
        fp2 = plugin.generate_fingerprint()
        assert fp1["fingerprint_seed"] != fp2["fingerprint_seed"]

    def test_get_browser_args(self):
        plugin = self._get()
        fp = plugin.generate_fingerprint(seed=42)
        args = plugin.get_browser_args(fp)
        assert any("--fingerprint=" in a for a in args)
        assert any("--fingerprint-gpu-vendor=" in a for a in args)

    def test_rotate_fingerprint(self):
        plugin = self._get()
        fp1 = plugin.generate_fingerprint(seed=42)
        fp2 = plugin.rotate_fingerprint(fp1)
        assert fp2["fingerprint_seed"] != fp1["fingerprint_seed"]


# ─── Bulk Export Tests ──────────────────────────────────────

@pytest.mark.skipif(not _plugin_available("bulk-export"), reason="not installed")
class TestBulkExport:
    def _get(self):
        return _load_plugin("bulk-export")

    def test_plugin_loads(self):
        plugin = self._get()
        assert plugin.name == "bulk-export"
        assert hasattr(plugin, "export_all")


# ─── Plugin Registry Tests ──────────────────────────────────

class TestNewPluginsInRegistry:
    def test_registry_has_new_plugins(self):
        from tokenade.core.integration.plugin_registry import PluginRegistry
        reg = PluginRegistry()
        plugins = reg.get_popular(limit=100)
        names = {p.get("name") for p in plugins}
        expected = {
            "session-backup", "session-merge", "proxy-health",
            "session-expiry-alert", "fingerprint-rotate", "bulk-export",
        }
        assert expected.issubset(names)

    def test_new_plugins_loadable(self):
        for name in ["session-backup", "session-merge", "proxy-health",
                      "session-expiry-alert", "fingerprint-rotate", "bulk-export"]:
            plugin = _load_plugin(name)
            assert plugin is not None, f"Failed to load {name}"
            assert hasattr(plugin, "name")
            assert plugin.name == name
