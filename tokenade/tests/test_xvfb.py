"""Tests for Xvfb manager (Phase 34)."""
import os
import shutil
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

from tokenade.core.browser.xvfb import XvfbManager


class TestXvfbManager:

    def test_init_defaults(self):
        xvfb = XvfbManager()
        assert xvfb.display == ":99:0"
        assert xvfb.width == 1920
        assert xvfb.height == 1080
        assert xvfb.depth == 24

    def test_init_custom(self):
        xvfb = XvfbManager(display=":1", width=800, height=600, depth=16)
        assert xvfb.display == ":1:0"
        assert xvfb.width == 800
        assert xvfb.height == 600
        assert xvfb.depth == 16

    def test_is_running_default(self):
        xvfb = XvfbManager()
        assert xvfb.is_running is False

    def test_display_number(self):
        xvfb = XvfbManager(display=":42")
        assert xvfb.display_number == 42

    def test_context_manager(self):
        with patch.object(XvfbManager, "start") as mock_start, \
             patch.object(XvfbManager, "stop") as mock_stop:
            with XvfbManager() as xvfb:
                mock_start.assert_called_once()
            mock_stop.assert_called_once()

    def test_context_manager_stop_on_exception(self):
        with patch.object(XvfbManager, "start"), \
             patch.object(XvfbManager, "stop") as mock_stop:
            try:
                with XvfbManager() as xvfb:
                    raise ValueError("test")
            except ValueError:
                pass
            mock_stop.assert_called_once()

    def test_is_display_available_no_display(self):
        xvfb = XvfbManager()
        with patch.dict(os.environ, {}, clear=True):
            assert xvfb.is_display_available() is False

    def test_is_display_available_with_display(self):
        xvfb = XvfbManager()
        with patch.dict(os.environ, {"DISPLAY": ":0"}):
            assert xvfb.is_display_available() is True

    @patch("shutil.which")
    def test_is_xvfb_available_true(self, mock_which):
        mock_which.return_value = "/usr/bin/Xvfb"
        assert XvfbManager().is_xvfb_available() is True

    @patch("shutil.which")
    def test_is_xvfb_available_false(self, mock_which):
        mock_which.return_value = None
        assert XvfbManager().is_xvfb_available() is False

    def test_start_display_already_available(self):
        xvfb = XvfbManager()
        with patch.object(xvfb, "is_display_available", return_value=True):
            result = xvfb.start()
            assert result is True
            assert xvfb._started_by_us is False

    def test_start_xvfb_not_installed(self):
        xvfb = XvfbManager()
        with patch.object(xvfb, "is_display_available", return_value=False), \
             patch.object(xvfb, "is_xvfb_available", return_value=False):
            result = xvfb.start()
            assert result is False

    def test_stop_no_start(self):
        xvfb = XvfbManager()
        # Should not raise
        xvfb.stop()
        assert xvfb._started_by_us is False

    def test_stop_restores_display(self):
        xvfb = XvfbManager()
        xvfb._started_by_us = True
        xvfb._original_display = ":0"
        with patch.dict(os.environ, {"DISPLAY": ":99"}):
            xvfb.stop()
            assert os.environ.get("DISPLAY") == ":0"

    def test_stop_clears_display(self):
        xvfb = XvfbManager()
        xvfb._started_by_us = True
        xvfb._original_display = None
        with patch.dict(os.environ, {"DISPLAY": ":99"}):
            xvfb.stop()
            assert "DISPLAY" not in os.environ

    def test_find_free_display(self):
        xvfb = XvfbManager()
        with patch("pathlib.Path.exists", return_value=False):
            num = xvfb._find_free_display()
            assert num == 99

    def test_find_free_display_occupied(self):
        xvfb = XvfbManager()
        occupied = {"/tmp/.X11-unix/X99"}
        original_exists = Path.exists
        def mock_exists(self_path):
            return str(self_path) in occupied
        with patch.object(Path, "exists", mock_exists):
            num = xvfb._find_free_display()
            assert num == 100

    def test_auto_start(self):
        with patch.object(XvfbManager, "start", return_value=True):
            xvfb = XvfbManager.auto_start()
            assert isinstance(xvfb, XvfbManager)

    def test_start_process_failure(self):
        xvfb = XvfbManager()
        with patch.object(xvfb, "is_display_available", return_value=False), \
             patch.object(xvfb, "is_xvfb_available", return_value=True), \
             patch("subprocess.Popen", side_effect=FileNotFoundError("not found")):
            result = xvfb.start()
            assert result is False

    def test_start_process_permission_error(self):
        xvfb = XvfbManager()
        with patch.object(xvfb, "is_display_available", return_value=False), \
             patch.object(xvfb, "is_xvfb_available", return_value=True), \
             patch("subprocess.Popen", side_effect=PermissionError("denied")):
            result = xvfb.start()
            assert result is False

    def test_stop_kills_process(self):
        xvfb = XvfbManager()
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        xvfb._process = mock_process
        xvfb._started_by_us = True
        xvfb._original_display = ":0"
        xvfb.stop()
        mock_process.terminate.assert_called_once()

    def test_stop_timeout_kills(self):
        xvfb = XvfbManager()
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        mock_process.terminate.side_effect = subprocess.TimeoutExpired("Xvfb", 5)
        xvfb._process = mock_process
        xvfb._started_by_us = True
        xvfb._original_display = ":0"
        xvfb.stop()
        mock_process.kill.assert_called_once()

    def test_display_number_complex(self):
        xvfb = XvfbManager(display=":0.1")
        # Splits on : then . for screen
        assert xvfb.display_number == 0
