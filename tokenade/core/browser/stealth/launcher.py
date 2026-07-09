"""
Undetectable Browser - System browser launcher with CDP connection.

Launches system Chrome/Firefox (NOT Playwright's bundled Chromium) with
remote debugging enabled. Connects via CDP WebSocket for cookie injection
and page control.

Why this works:
- System Chrome has no Playwright artifacts (no cdc_ prefix, no webdriver flag)
- Uses the real browser binary, not an automation-patched one
- CDP connection is indistinguishable from normal DevTools usage
- Platforms cannot detect this as automation

Usage:
    launcher = SystemBrowserLauncher()
    browser = launcher.launch(browser="chrome", visible=True)
    browser.inject_cookies(cookies)
    browser.navigate("https://mail.google.com")
    # ... do stuff ...
    browser.close()
"""

import json
import logging
import os
import platform
import shutil

import subprocess
import tempfile
import time
from dataclasses import dataclass, field

from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


@dataclass
class BrowserLaunchConfig:
    """Configuration for system browser launch."""
    browser: str = "chrome"  # chrome, firefox, brave, edge
    visible: bool = True  # Show browser window
    port: int = 9222  # CDP debugging port
    profile_dir: Optional[str] = None  # Custom profile directory
    user_data_dir: Optional[str] = None  # Chrome user data dir
    window_size: tuple = (1920, 1080)
    extra_args: List[str] = field(default_factory=list)
    timeout: float = 10.0  # Seconds to wait for CDP to be ready
    upstream_proxy: Optional[str] = None  # e.g. "socks5://user:pass@host:port"


class BrowserProcess:
    """Represents a running system browser with CDP connection."""

    def __init__(
        self,
        process: subprocess.Popen,
        port: int,
        profile_dir: str,
        browser_name: str,
    ):
        self.process = process
        self.port = port
        self.profile_dir = profile_dir
        self.browser_name = browser_name
        self._ws_url: Optional[str] = None
        self._connected = False

    @property
    def pid(self) -> int:
        return self.process.pid

    @property
    def is_running(self) -> bool:
        return self.process.poll() is None

    @property
    def cdp_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def get_ws_url(self) -> Optional[str]:
        """Get WebSocket debugger URL from CDP /json/version endpoint."""
        import urllib.request
        import urllib.error

        try:
            req = urllib.request.Request(f"{self.cdp_url}/json/version")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                return data.get("webSocketDebuggerUrl")
        except Exception as e:
            logger.debug(f"Failed to get WS URL: {e}")
            return None

    def get_targets(self) -> List[Dict]:
        """Get list of open tabs/pages from CDP /json/list."""
        import urllib.request

        try:
            req = urllib.request.Request(f"{self.cdp_url}/json/list")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            return []

    def wait_for_cdp(self, timeout: float = 10.0) -> bool:
        """Wait for CDP endpoint to become available."""
        import urllib.request
        import urllib.error

        start = time.time()
        while time.time() - start < timeout:
            try:
                req = urllib.request.Request(f"{self.cdp_url}/json/version")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        return True
            except (urllib.error.URLError, ConnectionRefusedError, OSError):
                pass
            time.sleep(0.2)
        return False

    def close(self):
        """Terminate the browser process."""
        if self.process and self.is_running:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
            except Exception:
                pass
        logger.info(f"Browser {self.browser_name} closed (PID: {self.pid})")


class SystemBrowserLauncher:
    """
    Launches system Chrome/Firefox with CDP debugging enabled.

    Unlike Playwright, this uses the actual system browser binary,
    which has no automation artifacts and is undetectable.

    Usage:
        launcher = SystemBrowserLauncher()
        browser = launcher.launch(browser="chrome", visible=True)
        print(f"CDP URL: {browser.cdp_url}")
        # Connect via WebSocket and control the browser
        browser.close()
    """

    # Chrome/Chromium paths per platform
    CHROME_PATHS = {
        "Linux": [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
        ],
        "Darwin": [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ],
        "Windows": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ],
    }

    FIREFOX_PATHS = {
        "Linux": [
            "/usr/bin/firefox",
            "/usr/bin/firefox-esr",
            "/snap/bin/firefox",
        ],
        "Darwin": [
            "/Applications/Firefox.app/Contents/MacOS/firefox",
        ],
        "Windows": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ],
    }

    BRAVE_PATHS = {
        "Linux": [
            "/usr/bin/brave-browser",
            "/usr/bin/brave-browser-stable",
        ],
        "Darwin": [
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        ],
        "Windows": [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        ],
    }

    EDGE_PATHS = {
        "Linux": [
            "/usr/bin/microsoft-edge",
            "/usr/bin/microsoft-edge-stable",
        ],
        "Darwin": [
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ],
        "Windows": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ],
    }

    VIVALDI_PATHS = {
        "Linux": [
            "/usr/bin/vivaldi",
            "/usr/bin/vivaldi-stable",
            "/opt/vivaldi/vivaldi",
            "/opt/vivaldi/vivaldi-bin",
        ],
        "Darwin": [
            "/Applications/Vivaldi.app/Contents/MacOS/Vivaldi",
        ],
        "Windows": [
            r"C:\Program Files\Vivaldi\Application\vivaldi.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe"),
        ],
    }

    def __init__(self):
        self._active_browsers: List[BrowserProcess] = []
        self._xvfb: Optional[Any] = None

    def _get_default_profile_dir(self, browser: str) -> Optional[str]:
        """Find the user's default browser profile directory."""
        os_type = platform.system()

        if browser.lower() in ("chrome", "chromium"):
            if os_type == "Linux":
                for path in [
                    os.path.expanduser("~/.config/google-chrome"),
                    os.path.expanduser("~/.config/chromium"),
                ]:
                    if os.path.exists(path):
                        return path
            elif os_type == "Darwin":
                path = os.path.expanduser("~/Library/Application Support/Google/Chrome")
                if os.path.exists(path):
                    return path
            elif os_type == "Windows":
                path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")
                if os.path.exists(path):
                    return path

        elif browser.lower() == "brave":
            if os_type == "Linux":
                path = os.path.expanduser("~/.config/BraveSoftware/Brave-Browser")
                if os.path.exists(path):
                    return path
            elif os_type == "Darwin":
                path = os.path.expanduser("~/Library/Application Support/BraveSoftware/Brave-Browser")
                if os.path.exists(path):
                    return path
            elif os_type == "Windows":
                path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "BraveSoftware", "Brave-Browser", "User Data")
                if os.path.exists(path):
                    return path

        elif browser.lower() == "firefox":
            if os_type == "Linux":
                path = os.path.expanduser("~/.mozilla/firefox")
                if os.path.exists(path):
                    return path
            elif os_type == "Darwin":
                path = os.path.expanduser("~/Library/Application Support/Firefox/Profiles")
                if os.path.exists(path):
                    return path

        elif browser.lower() in ("edge", "msedge"):
            if os_type == "Linux":
                path = os.path.expanduser("~/.config/microsoft-edge")
                if os.path.exists(path):
                    return path

        elif browser.lower() == "vivaldi":
            if os_type == "Linux":
                path = os.path.expanduser("~/.config/vivaldi")
                if os.path.exists(path):
                    return path
            elif os_type == "Darwin":
                path = os.path.expanduser("~/Library/Application Support/Vivaldi")
                if os.path.exists(path):
                    return path
            elif os_type == "Windows":
                path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Vivaldi", "User Data")
                if os.path.exists(path):
                    return path

        return None

    def _copy_profile(self, browser: str, dest_dir: str) -> bool:
        """
        Copy the user's real browser profile to dest_dir.

        Full copy (not selective) ensures the browser fingerprint matches
        the user's real browser. Skips only cache directories to save space.
        """
        import shutil

        src_dir = self._get_default_profile_dir(browser)
        if not src_dir:
            logger.debug(f"No default profile found for {browser}")
            return False

        logger.info(f"Copying real {browser} profile from {src_dir}")

        # Directories to skip (cache, can be regenerated)
        SKIP_DIRS = {
            "Cache", "Code Cache", "GPUCache", "ShaderCache", "GrShaderCache",
            "Service Worker", "ServiceWorker", "ScriptCache", "IndexedDB",
            "Session Storage", "Local Storage", "blob_storage",
            "File System", "GCM Store", "databases",
            "component_crx_cache", "extensions_crx_cache",
            "BudgetDatabase", "WebStorage",
        }

        def _ignore(_directory, contents):
            return [c for c in contents if c in SKIP_DIRS]

        try:
            shutil.copytree(src_dir, dest_dir, ignore=_ignore, dirs_exist_ok=True)
            size_mb = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, _, fnames in os.walk(dest_dir)
                for f in fnames
            ) / (1024 * 1024)
            logger.info(f"Profile copy complete ({size_mb:.0f} MB)")
            return True
        except Exception as e:
            logger.warning(f"Profile copy failed: {e}")
            return False

    def find_browser(self, browser: str = "chrome") -> Optional[str]:
        """
        Find system browser executable path.

        Args:
            browser: Browser name (chrome, firefox, brave, edge)

        Returns:
            Path to browser executable or None
        """
        os_type = platform.system()

        path_map = {
            "chrome": self.CHROME_PATHS,
            "chromium": self.CHROME_PATHS,
            "firefox": self.FIREFOX_PATHS,
            "brave": self.BRAVE_PATHS,
            "edge": self.EDGE_PATHS,
            "msedge": self.EDGE_PATHS,
            "vivaldi": self.VIVALDI_PATHS,
        }

        paths = path_map.get(browser.lower(), self.CHROME_PATHS)
        for path in paths.get(os_type, []):
            if os.path.exists(path):
                logger.info(f"Found {browser} at: {path}")
                return path

        # Try PATH
        which_name = {
            "chrome": "google-chrome",
            "chromium": "chromium",
            "firefox": "firefox",
            "brave": "brave-browser",
            "edge": "microsoft-edge",
            "vivaldi": "vivaldi",
        }.get(browser.lower(), browser)

        found = shutil.which(which_name)
        if found:
            logger.info(f"Found {browser} in PATH: {found}")
            return found

        logger.warning(f"Could not find {browser} browser")
        return None

    def launch(
        self,
        browser: str = "chrome",
        visible: bool = True,
        port: int = 9222,
        profile_dir: Optional[str] = None,
        user_data_dir: Optional[str] = None,
        window_size: tuple = (1920, 1080),
        extra_args: Optional[List[str]] = None,
        timeout: float = 15.0,
        upstream_proxy: Optional[str] = None,
    ) -> BrowserProcess:
        """
        Launch system browser with CDP debugging enabled.

        Args:
            browser: Browser name (chrome, firefox, brave, edge)
            visible: Show browser window (False for headless)
            port: CDP debugging port
            profile_dir: Custom profile directory (auto-created if None)
            user_data_dir: Chrome user data directory
            window_size: Browser window size (width, height)
            extra_args: Additional command-line arguments
            timeout: Seconds to wait for CDP to be ready
            upstream_proxy: Upstream proxy URL (e.g. "socks5://user:pass@host:port")

        Returns:
            BrowserProcess with CDP connection info

        Raises:
            RuntimeError: If browser not found or launch fails
        """
        # Find browser executable
        browser_path = self.find_browser(browser)
        if not browser_path:
            raise RuntimeError(
                f"{browser} browser not found. Install it:\n"
                f"  Ubuntu/Debian: sudo apt install {'google-chrome' if browser in ('chrome', 'chromium') else browser}\n"
                f"  macOS: brew install --cask {'google-chrome' if browser == 'chrome' else browser}\n"
                f"  Or specify path: --browser-path /path/to/browser"
            )

        # Auto-start Xvfb if headless and no display available
        if not visible and platform.system() == "Linux":
            from tokenade.core.browser.xvfb import XvfbManager
            xvfb = XvfbManager()
            if not xvfb.is_display_available():
                if xvfb.is_xvfb_available():
                    if xvfb.start():
                        self._xvfb = xvfb
                        logger.info(f"Auto-started Xvfb for headless {browser}")
                    else:
                        logger.warning("Xvfb start failed, browser may not render correctly")
                else:
                    logger.debug("Xvfb not installed, using browser headless mode")

        # Create profile directory
        if profile_dir is None:
            profile_dir = tempfile.mkdtemp(prefix=f"tokenade_{browser}_")
        else:
            os.makedirs(profile_dir, exist_ok=True)

        # Check if port is already in use
        if self._is_port_in_use(port):
            # Find next available port
            for try_port in range(port + 1, port + 100):
                if not self._is_port_in_use(try_port):
                    port = try_port
                    break
            else:
                raise RuntimeError(f"No available port near {port}")

        # Build launch arguments
        args = self._build_args(
            browser=browser,
            browser_path=browser_path,
            visible=visible,
            port=port,
            profile_dir=profile_dir,
            user_data_dir=user_data_dir,
            window_size=window_size,
            extra_args=extra_args or [],
            upstream_proxy=upstream_proxy,
        )

        logger.info(f"Launching {browser}: {' '.join(args[:5])}...")

        # Launch process
        try:
            process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid if platform.system() != "Windows" else None,
            )
        except FileNotFoundError as e:
            raise RuntimeError(f"Failed to launch {browser}: {e}")
        except PermissionError as e:
            raise RuntimeError(f"Permission denied launching {browser}: {e}")

        # Create BrowserProcess
        browser_proc = BrowserProcess(
            process=process,
            port=port,
            profile_dir=profile_dir,
            browser_name=browser,
        )

        # Wait for CDP to be ready
        if not browser_proc.wait_for_cdp(timeout=timeout):
            process.terminate()
            raise RuntimeError(
                f"Browser {browser} launched but CDP not ready after {timeout}s.\n"
                f"The browser may have crashed or CDP is not enabled."
            )

        self._active_browsers.append(browser_proc)
        logger.info(f"Browser {browser} ready (PID: {process.pid}, CDP: {browser_proc.cdp_url})")

        return browser_proc

    def _build_args(
        self,
        browser: str,
        browser_path: str,
        visible: bool,
        port: int,
        profile_dir: str,
        user_data_dir: Optional[str],
        window_size: tuple,
        extra_args: List[str],
        upstream_proxy: Optional[str] = None,
    ) -> List[str]:
        """Build browser command-line arguments."""
        args = [browser_path]

        if browser.lower() in ("chrome", "chromium", "brave", "edge", "msedge", "vivaldi"):
            # Chromium-based browsers
            # Minimal flags — real users don't have --disable-* flags
            args.extend([
                f"--remote-debugging-port={port}",
                f"--window-size={window_size[0]},{window_size[1]}",
                "--no-first-run",
                "--no-default-browser-check",
            ])

            if user_data_dir:
                args.append(f"--user-data-dir={user_data_dir}")
            else:
                args.append(f"--user-data-dir={profile_dir}")

            if not visible:
                args.append("--headless=new")

            if upstream_proxy:
                args.append(f"--proxy-server={upstream_proxy}")
                args.append("--proxy-bypass-list=localhost,127.0.0.1,<-loopback>")

        elif browser.lower() == "firefox":
            # Firefox
            args.extend([
                f"--remote-debugging-port={port}",
                f"--profile={profile_dir}",
                "--no-remote",
            ])

            if not visible:
                args.append("--headless")

            if upstream_proxy:
                # Firefox uses --proxy-server for SOCKS5/HTTP
                args.append(f"--proxy-server={upstream_proxy}")

        else:
            # Generic: just add CDP port
            args.append(f"--remote-debugging-port={port}")

            if upstream_proxy:
                args.append(f"--proxy-server={upstream_proxy}")

        args.extend(extra_args)
        return args

    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is already in use."""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return False
            except OSError:
                return True

    def close_all(self):
        """Close all active browser processes and cleanup Xvfb."""
        for browser in self._active_browsers:
            browser.close()
        self._active_browsers.clear()
        if self._xvfb:
            self._xvfb.stop()
            self._xvfb = None

    def __del__(self):
        self.close_all()
