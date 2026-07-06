"""
Xvfb (X Virtual Framebuffer) manager for headless browser operations.

Provides a virtual X11 display for browsers that need one in Docker/CI
environments where no physical display is available.

Usage:
    xvfb = XvfbManager()
    with xvfb:
        # DISPLAY is set, browsers can launch
        launcher = SystemBrowserLauncher()
        browser = launcher.launch(visible=False)
"""
import os
import platform
import shutil

import subprocess
import time
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class XvfbManager:
    """
    Manages an Xvfb virtual framebuffer for headless browser operations.

    Automatically detects if a display is available, starts Xvfb if needed,
    and sets the DISPLAY environment variable.

    Usage as context manager:
        with XvfbManager() as xvfb:
            # DISPLAY is set for child processes
            subprocess.run(["chrome", "--headless=new"])

    Usage standalone:
        xvfb = XvfbManager()
        xvfb.start()
        # ... do stuff ...
        xvfb.stop()
    """

    def __init__(self, display: str = ":99", width: int = 1920, height: int = 1080,
                 depth: int = 24, screen: int = 0):
        """
        Args:
            display: X display number (e.g., ":99")
            width: Virtual screen width
            height: Virtual screen height
            depth: Color depth (24 = True Color)
            screen: Screen number
        """
        self.display = f"{display}:{screen}"
        self.width = width
        self.height = height
        self.depth = depth
        self.screen = screen
        self._process: Optional[subprocess.Popen] = None
        self._original_display: Optional[str] = None
        self._started_by_us = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        self.stop()
        return False

    def is_display_available(self) -> bool:
        """Check if an X display is already available."""
        display = os.environ.get("DISPLAY")
        if not display:
            return False

        # Verify the display is actually usable
        if platform.system() == "Linux" and shutil.which("xdpyinfo"):
            try:
                result = subprocess.run(
                    ["xdpyinfo", "-display", display],
                    capture_output=True, timeout=2,
                )
                return result.returncode == 0
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        # If we can't verify, assume it's available if DISPLAY is set
        return True

    def is_xvfb_available(self) -> bool:
        """Check if Xvfb is installed."""
        return shutil.which("Xvfb") is not None

    def start(self) -> bool:
        """
        Start Xvfb if no display is available.

        Returns:
            True if Xvfb was started or display was already available.
        """
        if self.is_display_available():
            logger.debug(f"Display already available: {os.environ.get('DISPLAY')}")
            return True

        if not self.is_xvfb_available():
            logger.warning(
                "Xvfb not installed. Install it:\n"
                "  Ubuntu/Debian: sudo apt install xvfb\n"
                "  CentOS/RHEL: sudo yum install xorg-x11-server-Xvfb\n"
                "  macOS: brew install xquartz"
            )
            return False

        # Find an unused display number
        display_num = self._find_free_display()
        if display_num is None:
            logger.error("Could not find free display number for Xvfb")
            return False

        self.display = f":{display_num}"

        logger.info(f"Starting Xvfb on {self.display} ({self.width}x{self.height}x{self.depth})")

        try:
            self._process = subprocess.Popen(
                [
                    "Xvfb",
                    self.display,
                    "-screen", str(self.screen),
                    f"{self.width}x{self.height}x{self.depth}",
                    "-ac",  # Disable access control
                    "-nolisten", "tcp",  # Only listen on Unix socket
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Wait for Xvfb to start
            time.sleep(0.5)

            if self._process.poll() is not None:
                logger.error(f"Xvfb exited immediately with code {self._process.returncode}")
                return False

            # Set DISPLAY
            self._original_display = os.environ.get("DISPLAY")
            os.environ["DISPLAY"] = self.display
            self._started_by_us = True

            logger.info(f"Xvfb started (PID: {self._process.pid}, DISPLAY={self.display})")
            return True

        except FileNotFoundError:
            logger.error("Xvfb binary not found")
            return False
        except Exception as e:
            logger.error(f"Failed to start Xvfb: {e}")
            return False

    def stop(self):
        """Stop Xvfb and restore original DISPLAY."""
        if not self._started_by_us:
            return

        # Restore original DISPLAY
        if self._original_display is not None:
            os.environ["DISPLAY"] = self._original_display
        elif "DISPLAY" in os.environ:
            del os.environ["DISPLAY"]

        # Kill Xvfb
        if self._process and self._process.poll() is None:
            logger.info(f"Stopping Xvfb (PID: {self._process.pid})")
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=3)
            except Exception:
                pass

        self._process = None
        self._started_by_us = False

    def _find_free_display(self) -> Optional[int]:
        """Find a free display number starting from 99."""
        for num in range(99, 200):
            display_path = f"/tmp/.X11-unix/X{num}"
            if not Path(display_path).exists():
                return num
        return None

    @property
    def is_running(self) -> bool:
        """Check if Xvfb is running."""
        return (
            self._process is not None
            and self._process.poll() is None
        )

    @property
    def display_number(self) -> int:
        """Get the display number."""
        return int(self.display.split(":")[1].split(".")[0])

    @classmethod
    def auto_start(cls, **kwargs) -> "XvfbManager":
        """
        Auto-start Xvfb if needed and return the manager.

        Convenience method for quick setup:
            xvfb = XvfbManager.auto_start()
            # ... do stuff ...
            xvfb.stop()
        """
        manager = cls(**kwargs)
        manager.start()
        return manager
