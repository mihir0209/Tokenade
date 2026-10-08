"""
Mobile Import Manager.

Unified interface for importing sessions from mobile devices (Android/iOS).
Auto-detects connected devices, discovers installed browsers, and extracts
cookies into .tokenade format.

Usage:
    # CLI
    tokenade mobile-import --auto
    tokenade mobile-import --device <serial> --browser chrome --domains "google.com"
    tokenade mobile-import --ios --output gmail.tokenade

    # Python
    from tokenade.core.importer.mobile_import import MobileImportManager
    manager = MobileImportManager()
    devices = manager.list_devices()
    result = manager.extract(device=devices[0], browser="chrome")
"""


import logging
import platform
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MobileDevice:
    """Detected mobile device."""
    serial: str
    platform: str  # "android" or "ios"
    model: str = "unknown"
    os_version: str = "unknown"
    available_browsers: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "serial": self.serial,
            "platform": self.platform,
            "model": self.model,
            "os_version": self.os_version,
            "available_browsers": self.available_browsers,
        }


@dataclass
class MobileExtractResult:
    """Result of mobile cookie extraction."""
    success: bool
    device: Optional[MobileDevice] = None
    browser: str = ""
    cookie_count: int = 0
    session_file: Optional[str] = None
    site_name: str = "unknown"
    auth_status: str = "unknown"
    error: Optional[str] = None
    domains: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "device": self.device.to_dict() if self.device else None,
            "browser": self.browser,
            "cookie_count": self.cookie_count,
            "session_file": self.session_file,
            "site_name": self.site_name,
            "auth_status": self.auth_status,
            "error": self.error,
            "domains": self.domains,
        }


# Android browser package names and cookie paths
ANDROID_BROWSERS = {
    "chrome": {
        "package": "com.android.chrome",
        "paths": [
            "/data/data/com.android.chrome/app_chrome/Default/Cookies",
        ],
    },
    "firefox": {
        "package": "org.mozilla.firefox",
        "paths": [
            "/data/data/org.mozilla.firefox/files/mozilla/*.default*/cookies.sqlite",
        ],
    },
    "samsung": {
        "package": "com.sec.android.app.sbrowser",
        "paths": [
            "/data/data/com.sec.android.app.sbrowser/files/Default/Cookies",
        ],
    },
    "brave": {
        "package": "com.brave.browser",
        "paths": [
            "/data/data/com.brave.browser/app_chrome/Default/Cookies",
        ],
    },
    "edge": {
        "package": "com.microsoft.emmx",
        "paths": [
            "/data/data/com.microsoft.emmx/app_chrome/Default/Cookies",
        ],
    },
}


class MobileImportManager:
    """
    Unified manager for importing sessions from mobile devices.

    Supports:
    - Android: via ADB (pull cookie databases directly from device)
    - iOS: via pymobiledevice3 (macOS only, device required)
    - iOS iTunes Backup: from local iTunes/Finder backup (all platforms, no device)

    Usage:
        manager = MobileImportManager()

        # Auto-detect and extract
        devices = manager.list_devices()
        for device in devices:
            result = manager.extract(device, browser="chrome")

        # Extract from iTunes backup (no device connected)
        result = manager.extract_from_itunes_backup(
            domains=["com.apple.mobilesafari"],
            browser="safari",
        )
    """

    def __init__(self):
        self._adb_available = self._check_adb()
        self._ios_available = self._check_ios()

    def _check_adb(self) -> bool:
        """Check if ADB is available."""
        try:
            result = subprocess.run(
                ["adb", "version"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _check_ios(self) -> bool:
        """Check if pymobiledevice3 is available (macOS only)."""
        if platform.system() != "Darwin":
            return False
        try:
            from pymobiledevice3.lockdown import create_using_usbmux
            return True
        except ImportError:
            return False

    def is_available(self) -> bool:
        """Check if any mobile extraction method is available."""
        return self._adb_available or self._ios_available

    def list_devices(self) -> List[MobileDevice]:
        """List all connected mobile devices (Android + iOS)."""
        devices = []

        if self._adb_available:
            devices.extend(self._list_android_devices())

        if self._ios_available:
            devices.extend(self._list_ios_devices())

        return devices

    def _list_android_devices(self) -> List[MobileDevice]:
        """List connected Android devices via ADB."""
        try:
            result = subprocess.run(
                ["adb", "devices", "-l"],
                capture_output=True, text=True, timeout=5,
            )

            devices = []
            for line in result.stdout.strip().split("\n")[1:]:
                if not line.strip() or "offline" in line:
                    continue

                parts = line.split()
                if len(parts) < 2:
                    continue

                serial = parts[0]
                if serial in ("offline", "unauthorized"):
                    continue

                # Get device info
                model = self._get_device_prop(serial, "ro.product.model")
                android_version = self._get_device_prop(serial, "ro.build.version.release")

                # Discover installed browsers
                browsers = self._discover_android_browsers(serial)

                devices.append(MobileDevice(
                    serial=serial,
                    platform="android",
                    model=model or "unknown",
                    os_version=android_version or "unknown",
                    available_browsers=browsers,
                ))

            return devices

        except Exception as e:
            logger.error(f"Failed to list Android devices: {e}")
            return []

    def _get_device_prop(self, serial: str, prop: str) -> str:
        """Get a device property via ADB."""
        try:
            result = subprocess.run(
                ["adb", "-s", serial, "shell", "getprop", prop],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def _discover_android_browsers(self, serial: str) -> List[str]:
        """Discover which browsers are installed on an Android device."""
        installed = []
        for browser_name, info in ANDROID_BROWSERS.items():
            try:
                result = subprocess.run(
                    ["adb", "-s", serial, "shell", "pm", "list", "packages", info["package"]],
                    capture_output=True, text=True, timeout=5,
                )
                if info["package"] in result.stdout:
                    installed.append(browser_name)
            except Exception:
                continue
        return installed

    def _list_ios_devices(self) -> List[MobileDevice]:
        """List connected iOS devices via pymobiledevice3."""
        try:
            from pymobiledevice3.lockdown import create_using_usbmux

            lockdown = create_using_usbmux()
            devices_info = lockdown.all_devices

            devices = []
            for dev in devices_info:
                # Check if Safari is available
                browsers = ["safari"]  # Safari is always available on iOS

                devices.append(MobileDevice(
                    serial=str(dev.serial),
                    platform="ios",
                    model=dev.product_type or "unknown",
                    os_version=dev.product_version or "unknown",
                    available_browsers=browsers,
                ))

            return devices

        except Exception as e:
            logger.error(f"Failed to list iOS devices: {e}")
            return []

    def extract(
        self,
        device: MobileDevice,
        browser: str = "auto",
        domains: Optional[List[str]] = None,
        output_file: Optional[str] = None,
        site_name: Optional[str] = None,
    ) -> MobileExtractResult:
        """
        Extract cookies from a mobile device.

        Args:
            device: MobileDevice to extract from
            browser: Browser to extract from ("auto" = first available)
            domains: Domain filter (None = all)
            output_file: Output .tokenade file path
            site_name: Site name override

        Returns:
            MobileExtractResult
        """
        # Auto-select browser
        if browser == "auto":
            if not device.available_browsers:
                return MobileExtractResult(
                    success=False, device=device,
                    error="No browsers found on device",
                )
            browser = device.available_browsers[0]

        if browser not in device.available_browsers:
            return MobileExtractResult(
                success=False, device=device, browser=browser,
                error=f"Browser '{browser}' not installed on device. Available: {', '.join(device.available_browsers)}",
            )

        if device.platform == "android":
            return self._extract_android(device, browser, domains, output_file, site_name)
        elif device.platform == "ios":
            return self._extract_ios(device, browser, domains, output_file, site_name)
        else:
            return MobileExtractResult(
                success=False, device=device,
                error=f"Unsupported platform: {device.platform}",
            )

    def _extract_android(
        self,
        device: MobileDevice,
        browser: str,
        domains: Optional[List[str]],
        output_file: Optional[str],
        site_name: Optional[str],
    ) -> MobileExtractResult:
        """Extract cookies from Android device."""
        from tokenade.core.importer.cookie_extractor import CookieExtractor
        from tokenade.core.importer.session_packager import SessionPackager

        browser_info = ANDROID_BROWSERS.get(browser)
        if not browser_info:
            return MobileExtractResult(
                success=False, device=device, browser=browser,
                error=f"Unknown browser: {browser}",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "profile"
            profile_dir.mkdir()

            # Try each path pattern
            pulled = False
            for path_pattern in browser_info["paths"]:
                if "*" in path_pattern:
                    # List matching files on device
                    remote_dir = str(Path(path_pattern).parent)
                    try:
                        result = subprocess.run(
                            ["adb", "-s", device.serial, "shell", "ls", remote_dir],
                            capture_output=True, text=True, timeout=10,
                        )
                        if result.returncode != 0:
                            continue

                        for filename in result.stdout.strip().split("\n"):
                            remote_path = f"{remote_dir}/{filename}"
                            local_dest = str(profile_dir / "Cookies" if browser != "firefox" else profile_dir / "cookies.sqlite")
                            if self._adb_pull(device.serial, remote_path, local_dest):
                                pulled = True
                                break
                    except Exception:
                        continue
                else:
                    local_dest = str(profile_dir / ("Cookies" if browser != "firefox" else "cookies.sqlite"))
                    if self._adb_pull(device.serial, path_pattern, local_dest):
                        pulled = True

                if pulled:
                    break

            if not pulled:
                return MobileExtractResult(
                    success=False, device=device, browser=browser,
                    error="Failed to pull cookie database from device",
                )

            # Extract cookies
            try:
                extractor = CookieExtractor(str(profile_dir), browser=browser)
                all_cookies = extractor.extract(site_filter=None)
            except Exception as e:
                return MobileExtractResult(
                    success=False, device=device, browser=browser,
                    error=f"Failed to parse cookies: {e}",
                )

        # Filter by domains
        if domains:
            filtered = []
            for cookie in all_cookies:
                cookie_domain = cookie.get("domain", "").lstrip(".")
                for d in domains:
                    d_clean = d.lstrip(".")
                    if cookie_domain == d_clean or cookie_domain.endswith("." + d_clean):
                        filtered.append(cookie)
                        break
            all_cookies = filtered

        if not all_cookies:
            return MobileExtractResult(
                success=False, device=device, browser=browser,
                error="No cookies found matching specified domains",
            )

        # Package session
        packager = SessionPackager()
        session = packager.package(
            cookies=all_cookies,
            browser=browser,
            profile="mobile",
        )

        # Add mobile metadata
        if "metadata" not in session:
            session["metadata"] = {}
        session["metadata"]["source"] = "mobile"
        session["metadata"]["device_model"] = device.model
        session["metadata"]["device_os"] = device.os_version
        session["metadata"]["device_platform"] = device.platform
        session["metadata"]["browser"] = browser

        # Determine domains
        extracted_domains = list({c.get("domain", "").lstrip(".") for c in all_cookies})

        # Save
        if not output_file:
            site = site_name or session.get("site_name", "mobile")
            output_file = f"{site}_{browser}.tokenade"

        packager.save(session, output_file)

        return MobileExtractResult(
            success=True,
            device=device,
            browser=browser,
            cookie_count=len(all_cookies),
            session_file=output_file,
            site_name=session.get("site_name", "unknown"),
            auth_status=session.get("auth_status", "unknown"),
            domains=extracted_domains,
        )

    def _extract_ios(
        self,
        device: MobileDevice,
        browser: str,
        domains: Optional[List[str]],
        output_file: Optional[str],
        site_name: Optional[str],
    ) -> MobileExtractResult:
        """Extract cookies from iOS device."""
        if platform.system() != "Darwin":
            return MobileExtractResult(
                success=False, device=device, browser=browser,
                error="iOS extraction requires macOS",
            )

        try:
            from pymobiledevice3.lockdown import create_using_usbmux
            from pymobiledevice3.services.afc import AfcService

            lockdown = create_using_usbmux()
            afc = AfcService(lockdown)

            with tempfile.TemporaryDirectory() as tmpdir:
                # Pull Safari cookies
                cookies_path = "/AppDomain-com.apple.mobilesafari/Library/Cookies/Cookies.binarycookies"
                try:
                    afc.pull(cookies_path, tmpdir)
                except Exception:
                    # Try alternate path for newer iOS
                    cookies_path = "/AppDomain-com.apple.mobilesafari/Library/Cookies/Cookies.binarycookies"
                    afc.pull(cookies_path, tmpdir)

                cookies_file = Path(tmpdir) / "Cookies.binarycookies"
                if not cookies_file.exists():
                    return MobileExtractResult(
                        success=False, device=device, browser=browser,
                        error="Safari cookies file not found on device",
                    )

                # Parse binary cookies
                from tokenade.core.importer.safari_extractor import SafariExtractor
                extractor = SafariExtractor(profile_path=str(cookies_file))
                all_cookies = extractor._parse_binary_cookies(str(cookies_file))

        except ImportError:
            return MobileExtractResult(
                success=False, device=device, browser=browser,
                error="pymobiledevice3 not installed. Install: pip install pymobiledevice3",
            )
        except Exception as e:
            return MobileExtractResult(
                success=False, device=device, browser=browser,
                error=f"iOS extraction failed: {e}",
            )

        # Filter by domains
        if domains:
            filtered = []
            for cookie in all_cookies:
                cookie_domain = cookie.get("domain", "").lstrip(".")
                for d in domains:
                    d_clean = d.lstrip(".")
                    if cookie_domain == d_clean or cookie_domain.endswith("." + d_clean):
                        filtered.append(cookie)
                        break
            all_cookies = filtered

        if not all_cookies:
            return MobileExtractResult(
                success=False, device=device, browser=browser,
                error="No cookies found matching specified domains",
            )

        # Package session
        from tokenade.core.importer.session_packager import SessionPackager
        packager = SessionPackager()
        session = packager.package(
            cookies=all_cookies,
            browser="safari",
            profile="mobile",
        )

        if "metadata" not in session:
            session["metadata"] = {}
        session["metadata"]["source"] = "mobile"
        session["metadata"]["device_model"] = device.model
        session["metadata"]["device_os"] = device.os_version
        session["metadata"]["device_platform"] = device.platform
        session["metadata"]["browser"] = "safari"

        extracted_domains = list({c.get("domain", "").lstrip(".") for c in all_cookies})

        if not output_file:
            site = site_name or session.get("site_name", "mobile")
            output_file = f"{site}_safari.tokenade"

        packager.save(session, output_file)

        return MobileExtractResult(
            success=True,
            device=device,
            browser="safari",
            cookie_count=len(all_cookies),
            session_file=output_file,
            site_name=session.get("site_name", "unknown"),
            auth_status=session.get("auth_status", "unknown"),
            domains=extracted_domains,
        )

    def _adb_pull(self, serial: str, remote_path: str, local_path: str) -> bool:
        """Pull a file from Android device via ADB."""
        try:
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                ["adb", "-s", serial, "pull", remote_path, local_path],
                capture_output=True, text=True, timeout=15,
            )
            return result.returncode == 0 and Path(local_path).exists()
        except Exception as e:
            logger.debug(f"ADB pull failed: {remote_path}: {e}")
            return False

    # ── iTunes Backup Support ──────────────────────────────────

    @staticmethod
    def _find_itunes_backups() -> List[Dict[str, str]]:
        """Find iTunes/Finder backups on the local filesystem.

        Returns:
            List of dicts with 'name', 'path', 'device_name', 'date' keys.
        """
        backup_dirs = []

        if platform.system() == "Darwin":
            base = Path.home() / "Library" / "Application Support" / "MobileSync" / "Backup"
        elif platform.system() == "Windows":
            base = Path.home() / "AppData" / "Roaming" / "Apple Computer" / "MobileSync" / "Backup"
        else:
            # Linux: check common iTunes backup locations
            base = Path.home() / ".local" / "share" / "itunes-backups"

        if base.exists():
            for d in base.iterdir():
                if d.is_dir() and (d / "Manifest.db").exists():
                    info = {
                        "name": d.name,
                        "path": str(d),
                        "device_name": d.name,
                        "date": datetime.fromtimestamp(
                            d.stat().st_mtime, tz=timezone.utc
                        ).isoformat(),
                    }
                    # Try to read device name from Info.plist
                    info_plist = d / "Info.plist"
                    if info_plist.exists():
                        try:
                            import plistlib
                            with open(info_plist, "rb") as f:
                                plist = plistlib.load(f)
                            info["device_name"] = plist.get("Device Name", d.name)
                            info["product_type"] = plist.get("Product Type", "")
                            info["ios_version"] = plist.get("Product Version", "")
                        except Exception:
                            pass
                    backup_dirs.append(info)

        # Also check for backups created with third-party tools
        alt_paths = [
            Path.home() / "Android" / "com.github.mihir0209.tokenade" / "backups",
        ]
        for alt in alt_paths:
            if alt.exists():
                for d in alt.iterdir():
                    if d.is_dir() and (d / "Manifest.db").exists():
                        backup_dirs.append({
                            "name": d.name,
                            "path": str(d),
                            "device_name": d.name,
                            "date": datetime.fromtimestamp(
                                d.stat().st_mtime, tz=timezone.utc
                            ).isoformat(),
                        })

        return backup_dirs

    @staticmethod
    def _find_safari_cookies_in_backup(backup_path: str) -> Optional[str]:
        """Find Safari cookies file in an iTunes backup.

        Args:
            backup_path: Path to the iTunes backup directory

        Returns:
            Path to Cookies.binarycookies file, or None
        """
        backup = Path(backup_path)

        # Common iOS Safari cookie paths within backups
        safari_patterns = [
            # iOS 8-14
            "AppDomain-com.apple.mobilesafari/Library/Cookies/Cookies.binarycookies",
            # iOS 15+
            "AppDomain-com.apple.mobilesafari/Library/Cookies/Cookies.binarycookies",
            # Alternative domain
            "AppDomain-com.apple.WebKit.Networking/.../Cookies.binarycookies",
        ]

        for pattern in safari_patterns:
            candidate = backup / pattern
            if candidate.exists():
                return str(candidate)

        # Fallback: glob search for Cookies.binarycookies
        for candidate in backup.rglob("Cookies.binarycookies"):
            # Only return Safari cookies, not other apps
            if "mobilesafari" in str(candidate).lower():
                return str(candidate)

        return None

    @staticmethod
    def _find_chrome_cookies_in_backup(backup_path: str) -> Optional[str]:
        """Find Chrome cookies file in an iTunes backup.

        Args:
            backup_path: Path to the iTunes backup directory

        Returns:
            Path to Cookies file, or None
        """
        backup = Path(backup_path)

        chrome_patterns = [
            "AppDomain-com.google.Chrome/Library/Application Support/Google/Chrome/Default/Cookies",
            "AppDomain-com.google.Chrome/.../Cookies",
        ]

        for pattern in chrome_patterns:
            candidate = backup / pattern
            if candidate.exists():
                return str(candidate)

        for candidate in backup.rglob("Cookies"):
            if "google.chrome" in str(candidate).lower():
                return str(candidate)

        return None

    def extract_from_itunes_backup(
        self,
        backup_path: Optional[str] = None,
        domains: Optional[List[str]] = None,
        browser: str = "safari",
        output_file: Optional[str] = None,
        site_name: Optional[str] = None,
    ) -> MobileExtractResult:
        """Extract cookies from an iTunes/Finder backup.

        Works on all platforms without a connected device.

        Args:
            backup_path: Path to iTunes backup. If None, finds the most recent backup.
            domains: Domain filter (None = all)
            browser: Browser to extract from ("safari" or "chrome")
            output_file: Output .tokenade file path
            site_name: Site name override

        Returns:
            MobileExtractResult
        """
        from tokenade.core.importer.cookie_extractor import CookieExtractor
        from tokenade.core.importer.session_packager import SessionPackager

        # Find backup
        if not backup_path:
            backups = self._find_itunes_backups()
            if not backups:
                return MobileExtractResult(
                    success=False,
                    error="No iTunes backups found. "
                    "Create a backup with iTunes/Finder or specify --backup-path.",
                )
            # Use most recent backup
            backups.sort(key=lambda b: b.get("date", ""), reverse=True)
            backup_path = backups[0]["path"]
            logger.info(f"Using most recent backup: {backups[0]['name']} ({backups[0]['date']})")

        if not Path(backup_path).exists():
            return MobileExtractResult(
                success=False,
                error=f"Backup path not found: {backup_path}",
            )

        # Find cookies file
        if browser == "safari":
            cookies_file = self._find_safari_cookies_in_backup(backup_path)
        elif browser == "chrome":
            cookies_file = self._find_chrome_cookies_in_backup(backup_path)
        else:
            return MobileExtractResult(
                success=False, browser=browser,
                error=f"Unsupported browser for iTunes backup: {browser}. Use 'safari' or 'chrome'.",
            )

        if not cookies_file:
            return MobileExtractResult(
                success=False, browser=browser,
                error=f"No {browser} cookies found in backup at {backup_path}",
            )

        # Parse cookies
        if browser == "safari":
            from tokenade.core.importer.safari_extractor import SafariExtractor
            extractor = SafariExtractor(profile_path=cookies_file)
            all_cookies = extractor.extract()
        else:
            try:
                extractor = CookieExtractor(
                    str(Path(cookies_file).parent), browser=browser
                )
                all_cookies = extractor.extract()
            except Exception as e:
                return MobileExtractResult(
                    success=False, browser=browser,
                    error=f"Failed to parse Chrome cookies: {e}",
                )

        # Filter by domains
        if domains:
            filtered = []
            for cookie in all_cookies:
                cookie_domain = cookie.get("domain", "").lstrip(".")
                for d in domains:
                    d_clean = d.lstrip(".")
                    if cookie_domain == d_clean or cookie_domain.endswith("." + d_clean):
                        filtered.append(cookie)
                        break
            all_cookies = filtered

        if not all_cookies:
            return MobileExtractResult(
                success=False, browser=browser,
                error="No cookies found matching specified domains",
            )

        # Package session
        packager = SessionPackager()
        session = packager.package(
            cookies=all_cookies,
            browser=browser,
            profile="mobile",
        )

        if "metadata" not in session:
            session["metadata"] = {}
        session["metadata"]["source"] = "itunes_backup"
        session["metadata"]["backup_path"] = backup_path
        session["metadata"]["browser"] = browser

        extracted_domains = list({c.get("domain", "").lstrip(".") for c in all_cookies})

        if not output_file:
            site = site_name or session.get("site_name", "mobile")
            output_file = f"{site}_{browser}_backup.tokenade"

        packager.save(session, output_file)

        return MobileExtractResult(
            success=True,
            browser=browser,
            cookie_count=len(all_cookies),
            session_file=output_file,
            site_name=session.get("site_name", "unknown"),
            auth_status=session.get("auth_status", "unknown"),
            domains=extracted_domains,
        )

    def list_itunes_backups(self) -> List[Dict[str, str]]:
        """List all iTunes/Finder backups found on this machine.

        Returns:
            List of backup info dicts.
        """
        return self._find_itunes_backups()
