"""
CloakBrowser integration backend for Tokenade.

CloakBrowser is a stealth Chromium binary with 58 source-level C++ patches.
This module provides Tokenade's integration layer — launching stealth browsers,
injecting sessions via storage_state, and providing CDP server mode.

Usage:
    from tokenade.core.browser.cloak import CloakBrowserBackend

    backend = CloakBrowserBackend()
    if backend.is_available():
        browser = backend.launch(headless=True)
        # ... use browser ...
        browser.close()
"""

import logging
import subprocess
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CLOAKBROWSER_AVAILABLE = False
_cloakbrowser = None

try:
    import cloakbrowser as _cloakbrowser_mod
    _cloakbrowser = _cloakbrowser_mod
    _CLOAKBROWSER_AVAILABLE = True
except ImportError:
    pass


def is_cloakbrowser_available() -> bool:
    """Check if cloakbrowser package is installed."""
    return _CLOAKBROWSER_AVAILABLE


def is_binary_installed() -> bool:
    """Check if the CloakBrowser binary is downloaded."""
    if not _CLOAKBROWSER_AVAILABLE:
        return False
    try:
        info = _cloakbrowser.binary_info()
        return info.get("installed", False)
    except Exception:
        return False


def get_binary_info() -> Dict[str, Any]:
    """Get CloakBrowser binary info."""
    if not _CLOAKBROWSER_AVAILABLE:
        return {"installed": False, "error": "cloakbrowser not installed"}
    try:
        return _cloakbrowser.binary_info()
    except Exception as e:
        return {"installed": False, "error": str(e)}


def ensure_binary() -> bool:
    """Download the CloakBrowser binary if not already present.

    Returns True if binary is available after call.
    """
    if not _CLOAKBROWSER_AVAILABLE:
        logger.warning("cloakbrowser package not installed")
        return False
    try:
        _cloakbrowser.ensure_binary()
        return True
    except Exception as e:
        logger.error(f"Failed to download CloakBrowser binary: {e}")
        return False


def get_stealth_backend_name() -> str:
    """Return the name of the active stealth backend.

    Returns:
        "cloakbrowser" if binary available, "playwright" otherwise.
    """
    if is_binary_installed():
        return "cloakbrowser"
    return "playwright"


class CloakBrowserBackend:
    """CloakBrowser integration for Tokenade.

    Provides stealth browser launch, session injection via storage_state,
    and CDP server mode.
    """

    def is_available(self) -> bool:
        """Check if CloakBrowser is ready to use."""
        return is_cloakbrowser_available() and is_binary_installed()

    def ensure_ready(self) -> bool:
        """Ensure binary is downloaded and ready."""
        if not is_cloakbrowser_available():
            return False
        if not is_binary_installed():
            return ensure_binary()
        return True

    def launch(
        self,
        headless: bool = True,
        proxy: Optional[str] = None,
        humanize: bool = False,
        geoip: bool = False,
        fingerprint_seed: Optional[int] = None,
        timezone: Optional[str] = None,
        locale: Optional[str] = None,
        args: Optional[List[str]] = None,
        **kwargs,
    ) -> Any:
        """Launch a stealth browser via CloakBrowser.

        Returns:
            Playwright Browser object (compatible with all Playwright code).
        """
        if not self.ensure_ready():
            raise RuntimeError(
                "CloakBrowser not available. Install with: pip install cloakbrowser"
            )

        launch_args = list(args or [])
        if fingerprint_seed is not None:
            launch_args.append(f"--fingerprint={fingerprint_seed}")

        return _cloakbrowser.launch(
            headless=headless,
            proxy=proxy,
            args=launch_args or None,
            humanize=humanize,
            geoip=geoip,
            timezone=timezone,
            locale=locale,
            **kwargs,
        )

    def launch_context(
        self,
        headless: bool = True,
        proxy: Optional[str] = None,
        humanize: bool = False,
        geoip: bool = False,
        storage_state: Optional[str] = None,
        user_agent: Optional[str] = None,
        viewport: Optional[Dict] = None,
        timezone: Optional[str] = None,
        locale: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """Launch browser + context in one call.

        Args:
            storage_state: Path to Playwright storage_state JSON file.
                Injects cookies + localStorage at launch time.

        Returns:
            Playwright BrowserContext object.
        """
        if not self.ensure_ready():
            raise RuntimeError("CloakBrowser not available")

        ctx_kwargs = {}
        if storage_state:
            ctx_kwargs["storage_state"] = storage_state
        if user_agent:
            ctx_kwargs["user_agent"] = user_agent
        if viewport:
            ctx_kwargs["viewport"] = viewport
        ctx_kwargs.update(kwargs)

        return _cloakbrowser.launch_context(
            headless=headless,
            proxy=proxy,
            humanize=humanize,
            geoip=geoip,
            timezone=timezone,
            locale=locale,
            **ctx_kwargs,
        )

    def launch_persistent(
        self,
        profile_dir: str,
        headless: bool = True,
        proxy: Optional[str] = None,
        humanize: bool = False,
        geoip: bool = False,
        **kwargs,
    ) -> Any:
        """Launch with persistent profile (cookies survive restarts).

        Args:
            profile_dir: Path to user data directory.

        Returns:
            Playwright BrowserContext object.
        """
        if not self.ensure_ready():
            raise RuntimeError("CloakBrowser not available")

        return _cloakbrowser.launch_persistent_context(
            profile_dir,
            headless=headless,
            proxy=proxy,
            humanize=humanize,
            geoip=geoip,
            **kwargs,
        )

    def serve_cdp(
        self,
        port: int = 9222,
        proxy: Optional[str] = None,
        headless: bool = True,
        idle_timeout: Optional[int] = None,
        user_data_dir: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
        ready_timeout: float = 20.0,
    ) -> subprocess.Popen:
        """Start CloakBrowser Chromium with remote debugging (CDP).

        Newer cloakbrowser packages dropped ``python -m cloakbrowser serve``.
        We launch the patched Chromium binary directly with
        ``--remote-debugging-port`` so Tokenade can inject cookies via CDP.
        """
        import os
        import tempfile
        import urllib.request

        if not self.ensure_ready():
            raise RuntimeError("CloakBrowser not available")

        info = get_binary_info()
        binary = info.get("binary_path")
        if not binary or not os.path.isfile(binary):
            raise RuntimeError(f"CloakBrowser binary missing: {binary}")

        profile = user_data_dir or tempfile.mkdtemp(prefix="tokenade_cloak_cdp_")
        os.makedirs(profile, exist_ok=True)

        cmd = [
            binary,
            f"--remote-debugging-port={int(port)}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-features=Translate,MediaRouter",
            # Required on many modern Linux distros (AppArmor userns restrictions)
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "about:blank",
        ]
        if headless:
            cmd.insert(1, "--headless=new")
        if proxy:
            cmd.append(f"--proxy-server={proxy}")
        if extra_args:
            cmd.extend(list(extra_args))

        logger.info("CloakBrowser CDP: %s", " ".join(cmd[:4]) + " ...")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        # Wait until CDP answers
        deadline = time.time() + max(2.0, float(ready_timeout))
        last_err = None
        while time.time() < deadline:
            if proc.poll() is not None:
                err = b""
                try:
                    err = proc.stderr.read() if proc.stderr else b""
                except Exception:
                    pass
                raise RuntimeError(
                    f"CloakBrowser exited early (code={proc.returncode}): "
                    f"{err.decode(errors='replace')[:400]}"
                )
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{int(port)}/json/version",
                    timeout=1,
                ) as resp:
                    if resp.status == 200:
                        return proc
            except Exception as e:
                last_err = e
            time.sleep(0.25)

        try:
            proc.terminate()
        except Exception:
            pass
        raise RuntimeError(
            f"CloakBrowser CDP not ready on port {port} within {ready_timeout}s: {last_err}"
        )

    def get_info(self) -> Dict[str, Any]:
        """Get full CloakBrowser status info."""
        info = get_binary_info()
        info["package_installed"] = is_cloakbrowser_available()
        info["binary_ready"] = self.is_available()
        info["stealth_backend"] = get_stealth_backend_name()
        return info
