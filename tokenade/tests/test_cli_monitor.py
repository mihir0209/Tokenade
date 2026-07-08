"""
Tests for CLI monitor commands — status, start, stop, history, predict.
"""
import json
import time
import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tokenade.cli.management import cmd_monitor, _health_bar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_file(tmp_path, filename="test.tokenade", site_name="example.com"):
    session = {
        "cookies": [
            {"name": "sid", "domain": ".example.com", "expires": time.time() + 3600,
             "secure": True, "httpOnly": True, "sameSite": "Lax", "value": "abc"},
        ],
        "metadata": {"site_name": site_name},
    }
    path = Path(tmp_path) / filename
    path.write_text(json.dumps(session))
    return str(path)


def _make_args(**kwargs):
    defaults = {
        "monitor_command": "status",
        "sessions_dir": None,
        "session": None,
        "interval": 60,
        "auto_refresh": False,
        "limit": 50,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# cmd_monitor dispatch
# ---------------------------------------------------------------------------

class TestCmdMonitorDispatch:
    def test_status_subcommand(self, tmp_path, capsys):
        path = _make_session_file(tmp_path)
        args = _make_args(monitor_command="status", session=path)
        cmd_monitor(args)
        output = capsys.readouterr().out
        assert "TOKENADE - Session Monitor Status" in output

    def test_unknown_subcommand(self, capsys):
        args = _make_args(monitor_command="unknown")
        cmd_monitor(args)
        output = capsys.readouterr().out
        assert "❌" in output


# ---------------------------------------------------------------------------
# _monitor_status
# ---------------------------------------------------------------------------

class TestMonitorStatus:
    def test_status_no_args(self, capsys):
        args = _make_args(monitor_command="status")
        cmd_monitor(args)
        output = capsys.readouterr().out
        assert "❌" in output

    def test_status_with_session(self, tmp_path, capsys):
        path = _make_session_file(tmp_path)
        args = _make_args(monitor_command="status", session=path)
        cmd_monitor(args)
        output = capsys.readouterr().out
        assert "example.com" in output
        assert "Health:" in output

    def test_status_with_sessions_dir(self, tmp_path, capsys):
        _make_session_file(tmp_path, "s1.tokenade")
        _make_session_file(tmp_path, "s2.tokenade", site_name="other.com")
        args = _make_args(monitor_command="status", sessions_dir=str(tmp_path))
        cmd_monitor(args)
        output = capsys.readouterr().out
        assert "2 sessions" in output

    def test_status_empty_dir(self, tmp_path, capsys):
        args = _make_args(monitor_command="status", sessions_dir=str(tmp_path))
        cmd_monitor(args)
        output = capsys.readouterr().out
        assert "No sessions found" in output

    def test_status_invalid_file(self, tmp_path, capsys):
        path = Path(tmp_path) / "bad.tokenade"
        path.write_text("not json")
        args = _make_args(monitor_command="status", session=str(path))
        cmd_monitor(args)
        output = capsys.readouterr().out
        assert "❌" in output


# ---------------------------------------------------------------------------
# _monitor_start
# ---------------------------------------------------------------------------

class TestMonitorStart:
    def test_start_no_args(self, capsys):
        args = _make_args(monitor_command="start")
        cmd_monitor(args)
        output = capsys.readouterr().out
        assert "❌" in output

    def test_start_with_session(self, tmp_path, capsys):
        path = _make_session_file(tmp_path)
        args = _make_args(monitor_command="start", session=path, interval=1)
        with patch("tokenade.cli.handlers.misc.time.sleep", side_effect=KeyboardInterrupt):
            cmd_monitor(args)
        output = capsys.readouterr().out
        assert "Monitoring session" in output
        assert "Monitor stopped" in output

    def test_start_with_sessions_dir(self, tmp_path, capsys):
        _make_session_file(tmp_path)
        args = _make_args(monitor_command="start", sessions_dir=str(tmp_path), interval=1)
        with patch("tokenade.cli.handlers.misc.time.sleep", side_effect=KeyboardInterrupt):
            cmd_monitor(args)
        output = capsys.readouterr().out
        assert "Monitoring" in output


# ---------------------------------------------------------------------------
# _monitor_stop
# ---------------------------------------------------------------------------

class TestMonitorStop:
    def test_stop_no_pid_file(self, capsys):
        args = _make_args(monitor_command="stop")
        cmd_monitor(args)
        output = capsys.readouterr().out
        assert "❌" in output


# ---------------------------------------------------------------------------
# _monitor_history
# ---------------------------------------------------------------------------

class TestMonitorHistory:
    def test_history_empty(self, capsys):
        args = _make_args(monitor_command="history")
        cmd_monitor(args)
        output = capsys.readouterr().out
        assert "No monitor events" in output


# ---------------------------------------------------------------------------
# _monitor_predict
# ---------------------------------------------------------------------------

class TestMonitorPredict:
    def test_predict_no_sessions(self, capsys):
        args = _make_args(monitor_command="predict")
        cmd_monitor(args)
        output = capsys.readouterr().out
        # no sessions = no output lines (just passes)
        assert "❌" not in output

    def test_predict_with_session(self, tmp_path, capsys):
        path = _make_session_file(tmp_path)
        args = _make_args(monitor_command="predict", session=path)
        cmd_monitor(args)
        output = capsys.readouterr().out
        assert "insufficient data" in output


# ---------------------------------------------------------------------------
# _health_bar
# ---------------------------------------------------------------------------

class TestHealthBar:
    def test_bar_100_percent(self):
        bar = _health_bar(100.0)
        assert bar.count("█") == 20

    def test_bar_50_percent(self):
        bar = _health_bar(50.0)
        assert "▓" in bar
        assert bar.count("▓") == 10

    def test_bar_10_percent(self):
        bar = _health_bar(10.0)
        assert "░" in bar
        assert bar.count("░") == 2

    def test_bar_0_percent(self):
        bar = _health_bar(0.0)
        assert bar.startswith("[")
        assert bar.endswith("]")
