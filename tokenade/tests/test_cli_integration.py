"""
Integration tests for CLI workflows — end-to-end command execution.
Tests that CLI commands produce correct output and side effects.
"""

import json
import time
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tokenade.cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_file(tmp_dir, filename="test.tokenade", site_name="example.com"):
    session = {
        "cookies": [
            {
                "name": "sid",
                "domain": ".example.com",
                "expires": time.time() + 3600,
                "secure": True,
                "httpOnly": True,
                "sameSite": "Lax",
                "value": "abc",
            },
        ],
        "site_name": site_name,
        "metadata": {"site_name": site_name},
        "version": "2.0",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path = Path(tmp_dir) / filename
    path.write_text(json.dumps(session))
    return str(path)


def _run_cli(*args, capsys):
    """Run the CLI with given args and capture output."""
    import sys

    with patch("sys.argv", ["tokenade", *args]):
        try:
            main()
        except SystemExit:
            pass
    return capsys.readouterr()


# ---------------------------------------------------------------------------
# Health command
# ---------------------------------------------------------------------------


class TestHealthCommand:
    def test_health_single_session(self, tmp_path, capsys):
        path = _make_session_file(str(tmp_path))
        out = _run_cli("health", "-s", path, capsys=capsys)
        assert "Session Health Check" in out.out

    def test_health_directory(self, tmp_path, capsys):
        _make_session_file(str(tmp_path), "s1.tokenade")
        _make_session_file(str(tmp_path), "s2.tokenade")
        out = _run_cli("health", "-d", str(tmp_path), capsys=capsys)
        assert "SUMMARY" in out.out

    def test_health_no_sessions(self, tmp_path, capsys):
        out = _run_cli("health", "-d", str(tmp_path), capsys=capsys)
        assert "No session files found" in out.out


# ---------------------------------------------------------------------------
# Sessions command
# ---------------------------------------------------------------------------


class TestSessionsCommand:
    def test_sessions_list(self, tmp_path, capsys):
        _make_session_file(str(tmp_path), "s1.tokenade", "site1.com")
        _make_session_file(str(tmp_path), "s2.tokenade", "site2.com")
        out = _run_cli("sessions", "list", "--dir", str(tmp_path), capsys=capsys)
        assert "site1.com" in out.out
        assert "site2.com" in out.out

    def test_sessions_list_empty(self, tmp_path, capsys):
        out = _run_cli("sessions", "list", "--dir", str(tmp_path), capsys=capsys)
        assert "No sessions found" in out.out

    def test_sessions_stats(self, tmp_path, capsys):
        _make_session_file(str(tmp_path), "s1.tokenade")
        out = _run_cli(
            "sessions", "stats", str(Path(tmp_path) / "s1.tokenade"), capsys=capsys
        )
        assert "Session Statistics" in out.out


# ---------------------------------------------------------------------------
# Monitor command
# ---------------------------------------------------------------------------


class TestMonitorCommand:
    def test_monitor_status_no_sessions(self, tmp_path, capsys):
        out = _run_cli(
            "monitor", "status", "--sessions-dir", str(tmp_path), capsys=capsys
        )
        assert "No sessions found" in out.out

    def test_monitor_status_with_sessions(self, tmp_path, capsys):
        _make_session_file(str(tmp_path))
        out = _run_cli(
            "monitor", "status", "--sessions-dir", str(tmp_path), capsys=capsys
        )
        assert "Session Monitor Status" in out.out

    def test_monitor_history_empty(self, capsys):
        out = _run_cli("monitor", "history", capsys=capsys)
        assert "No monitor events" in out.out


# ---------------------------------------------------------------------------
# Config command
# ---------------------------------------------------------------------------


class TestConfigCommand:
    def test_config_show(self, capsys):
        out = _run_cli("config", "show", capsys=capsys)
        assert "Tokenade Config" in out.out

    def test_config_path(self, capsys):
        out = _run_cli("config", "path", capsys=capsys)
        assert "config.json" in out.out


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------


class TestVersion:
    def test_version(self, capsys):
        out = _run_cli("--version", capsys=capsys)
        assert "tokenade" in out.out.lower() or "5." in out.out


# ---------------------------------------------------------------------------
# Refresh command
# ---------------------------------------------------------------------------


class TestRefreshCommand:
    def test_refresh_missing_session(self, capsys):
        out = _run_cli(
            "refresh", "-s", "/nonexistent.tokenade", "-b", "firefox", capsys=capsys
        )
        assert "not found" in out.out.lower() or "❌" in out.out


# ---------------------------------------------------------------------------
# Encrypt / Decrypt commands
# ---------------------------------------------------------------------------


class TestEncryptDecrypt:
    def test_encrypt_missing_file(self, capsys):
        out = _run_cli("encrypt", "-i", "/nonexistent.tokenade", capsys=capsys)
        assert "❌" in out.out or "not found" in out.out.lower()

    def test_decrypt_missing_file(self, capsys):
        out = _run_cli("decrypt", "-i", "/nonexistent.tokenade", capsys=capsys)
        assert "❌" in out.out or "not found" in out.out.lower()


# ---------------------------------------------------------------------------
# Plugin command
# ---------------------------------------------------------------------------


class TestPluginCommand:
    def test_plugin_list(self, capsys):
        out = _run_cli("plugin", "list", capsys=capsys)
        assert "plugin" in out.out.lower() or "No plugins" in out.out


# ---------------------------------------------------------------------------
# Completion command
# ---------------------------------------------------------------------------


class TestCompletionCommand:
    def test_bash_completion(self, capsys):
        out = _run_cli("completion", "bash", capsys=capsys)
        assert "_tokenade" in out.out

    def test_zsh_completion(self, capsys):
        out = _run_cli("completion", "zsh", capsys=capsys)
        assert "_tokenade" in out.out

    def test_fish_completion(self, capsys):
        out = _run_cli("completion", "fish", capsys=capsys)
        assert "complete" in out.out
