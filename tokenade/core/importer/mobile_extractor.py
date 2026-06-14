"""
Mobile browser cookie extraction.

Supports:
- Android Chrome (via ADB)
- Android Firefox (via ADB)
- Samsung Internet (via ADB)
- Android WebView (via ADB)
- iOS Safari (via pymobiledevice3, macOS only)
"""
import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)


class MobileExtractor:
    """Extract cookies from mobile browsers."""
    
    # Android Chrome paths
    ANDROID_CHROME_PATHS = [
        "/data/data/com.android.chrome/app_chrome/Default/Cookies",
        "/data/data/com.android.chrome/app_chrome/Profile*/Cookies",
    ]
    
    # Android Firefox paths
    ANDROID_FIREFOX_PATHS = [
        "/data/data/org.mozilla.firefox/files/mozilla/*.default*/cookies.sqlite",
        "/data/data/org.mozilla.firefox/files/mozilla/*.default*/Cookies",
    ]
    
    # Samsung Internet paths
    ANDROID_SAMSUNG_PATHS = [
        "/data/data/com.sec.android.app.sbrowser/files/Default/Cookies",
    ]
    
    # Android WebView paths
    ANDROID_WEBVIEW_PATHS = [
        "/data/data/com.android.webview/app_chrome/Default/Cookies",
        "/data/data/com.google.android.webview/app_chrome/Default/Cookies",
    ]
    
    def __init__(self, device_id: Optional[str] = None):
        self.device_id = device_id
        self._adb_available = self._check_adb()
    
    def _check_adb(self) -> bool:
        """Check if ADB is available."""
        try:
            result = subprocess.run(
                ["adb", "version"],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def is_available(self) -> bool:
        """Check if mobile extraction is possible."""
        return self._adb_available
    
    def list_devices(self) -> List[Dict]:
        """List connected Android devices."""
        if not self._adb_available:
            return []
        
        try:
            result = subprocess.run(
                ["adb", "devices", "-l"],
                capture_output=True, text=True, timeout=5
            )
            
            devices = []
            for line in result.stdout.strip().split("\n")[1:]:
                if not line.strip() or "offline" in line:
                    continue
                
                parts = line.split()
                if len(parts) >= 2:
                    serial = parts[0]
                    status = parts[1]
                    
                    # Get device info
                    model = self._get_device_prop(serial, "ro.product.model")
                    android_version = self._get_device_prop(serial, "ro.build.version.release")
                    
                    devices.append({
                        "serial": serial,
                        "status": status,
                        "model": model,
                        "android_version": android_version,
                    })
            
            return devices
            
        except Exception as e:
            logger.error(f"Failed to list devices: {e}")
            return []
    
    def _get_device_prop(self, serial: str, prop: str) -> str:
        """Get a device property via ADB."""
        try:
            result = subprocess.run(
                ["adb", "-s", serial, "shell", "getprop", prop],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"
    
    def extract_chrome(self, profile: str = "Default") -> List[Dict]:
        """Extract cookies from Android Chrome via ADB."""
        return self._extract_via_adb(
            paths=self.ANDROID_CHROME_PATHS,
            browser="chrome",
            profile=profile,
        )
    
    def extract_firefox(self, profile: str = "default") -> List[Dict]:
        """Extract cookies from Android Firefox via ADB."""
        return self._extract_via_adb(
            paths=self.ANDROID_FIREFOX_PATHS,
            browser="firefox",
            profile=profile,
        )
    
    def extract_samsung(self, profile: str = "Default") -> List[Dict]:
        """Extract cookies from Samsung Internet via ADB."""
        return self._extract_via_adb(
            paths=self.ANDROID_SAMSUNG_PATHS,
            browser="chrome",  # Samsung uses Chromium
            profile=profile,
        )
    
    def extract_webview(self, profile: str = "Default") -> List[Dict]:
        """Extract cookies from Android WebView via ADB."""
        return self._extract_via_adb(
            paths=self.ANDROID_WEBVIEW_PATHS,
            browser="chrome",
            profile=profile,
        )
    
    def _extract_via_adb(self, paths: List[str], browser: str, profile: str) -> List[Dict]:
        """Extract cookies via ADB pull + CookieExtractor."""
        if not self._adb_available:
            logger.warning("ADB not available")
            return []
        
        serial_args = ["-s", self.device_id] if self.device_id else []
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Try each path pattern
            for path_pattern in paths:
                # Expand profile wildcards
                if "*" in path_pattern:
                    # List matching files
                    remote_dir = str(Path(path_pattern).parent)
                    result = subprocess.run(
                        ["adb"] + serial_args + ["shell", "ls", remote_dir],
                        capture_output=True, text=True, timeout=10
                    )
                    
                    if result.returncode != 0:
                        continue
                    
                    for filename in result.stdout.strip().split("\n"):
                        remote_path = f"{remote_dir}/{filename}"
                        if self._pull_file(remote_path, tmpdir):
                            local_path = Path(tmpdir) / Path(remote_path).name
                            if local_path.exists():
                                return self._extract_from_file(str(local_path), browser)
                else:
                    remote_path = path_pattern
                    if self._pull_file(remote_path, tmpdir):
                        local_path = Path(tmpdir) / Path(remote_path).name
                        if local_path.exists():
                            return self._extract_from_file(str(local_path), browser)
        
        return []
    
    def _pull_file(self, remote_path: str, local_dir: str) -> bool:
        """Pull a file from device via ADB."""
        serial_args = ["-s", self.device_id] if self.device_id else []
        
        try:
            result = subprocess.run(
                ["adb"] + serial_args + ["pull", remote_path, local_dir],
                capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug(f"Failed to pull {remote_path}: {e}")
            return False
    
    def _extract_from_file(self, db_path: str, browser: str) -> List[Dict]:
        """Extract cookies from a pulled SQLite database."""
        from tokenade.core.importer.cookie_extractor import CookieExtractor
        
        try:
            # Create a minimal profile directory
            profile_dir = Path(db_path).parent / "profile"
            profile_dir.mkdir(exist_ok=True)
            
            # Copy the database
            dest = profile_dir / "Cookies"
            shutil.copy2(db_path, dest)
            
            # Extract cookies
            extractor = CookieExtractor(str(profile_dir), browser=browser)
            return extractor.extract(site_filter=None)
            
        except Exception as e:
            logger.error(f"Failed to extract from {db_path}: {e}")
            return []
    
    def extract_ios_safari(self) -> List[Dict]:
        """Extract cookies from iOS Safari via pymobiledevice3 (macOS only).
        
        Requires: pip install pymobiledevice3
        """
        if sys.platform != "darwin":
            logger.warning("iOS Safari extraction requires macOS")
            return []
        
        try:
            from pymobiledevice3.lockdown import create_using_usbmux
            from pymobiledevice3.services.afc import AfcService
            
            # Connect to device
            lockdown = create_using_usbmux()
            afc = AfcService(lockdown)
            
            # Pull Safari cookies (iOS sandbox path)
            # This varies by iOS version
            with tempfile.TemporaryDirectory() as tmpdir:
                try:
                    afc.pull(
                        "/AppDomain-com.apple.mobilesafari/Library/Cookies/Cookies.binarycookies",
                        tmpdir
                    )
                    
                    # Parse the binary cookies
                    from tokenade.core.importer.safari_extractor import SafariExtractor
                    
                    cookies_file = Path(tmpdir) / "Cookies.binarycookies"
                    if cookies_file.exists():
                        extractor = SafariExtractor(profile_path=str(cookies_file))
                        return extractor._parse_binary_cookies(str(cookies_file))
                        
                except Exception as e:
                    logger.debug(f"iOS Safari extraction failed: {e}")
        
        except ImportError:
            logger.warning("pymobiledevice3 not installed. Install with: pip install pymobiledevice3")
        except Exception as e:
            logger.error(f"iOS Safari extraction failed: {e}")
        
        return []
