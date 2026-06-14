"""
ADB Extractor - Extract browser cookies from Android devices via ADB.

Supports Chrome and Firefox on Android by pulling their SQLite cookie
databases from the device and parsing them locally.
"""

import os
import shutil
import sqlite3
import subprocess
import tempfile
import logging
from typing import Dict, List, Optional

from tokenade.core.importer.cookie_extractor import CookieExtractor, SiteFilter
from tokenade.core.importer.db_utils import copy_db

logger = logging.getLogger(__name__)

# Common Android browser cookie paths
ANDROID_CHROME_PATHS = [
    "/data/data/com.android.chrome/app_chrome/Default/Cookies",
    "/data/data/com.android.chrome/app_chrome/Profile*/Cookies",
]

ANDROID_FIREFOX_PATHS = [
    "/data/data/org.mozilla.firefox/files/mozilla/*.default/cookies.sqlite",
    "/data/data/org.mozilla.fennec_aurora/files/mozilla/*.default/cookies.sqlite",
    "/data/data/org.mozilla.firefox/files/mozilla/*.default-release/cookies.sqlite",
]


class ADBExtractor:
    """Extract browser cookies from Android devices via ADB."""

    def __init__(self, device_id: Optional[str] = None):
        """
        Initialize ADB cookie extractor.

        Args:
            device_id: Specific device serial number. If None, uses the default device.
        """
        self.device_id = device_id

    def is_available(self) -> bool:
        """
        Check if ADB is installed and a device is connected.

        Returns:
            True if ADB is available and at least one device is connected.
        """
        try:
            output = self._run_adb(["devices"])
            lines = output.strip().split("\n")
            # First line is "List of devices attached", skip it
            devices = [
                line for line in lines[1:]
                if line.strip() and "device" in line
            ]
            return len(devices) > 0
        except (FileNotFoundError, subprocess.SubprocessError):
            return False

    def list_devices(self) -> List[Dict]:
        """
        List connected Android devices.

        Returns:
            List of device dicts with serial, model, and android_version.
        """
        devices = []
        try:
            output = self._run_adb(["devices", "-l"])
            lines = output.strip().split("\n")

            for line in lines[1:]:
                if not line.strip() or "device" not in line:
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue

                serial = parts[0]
                # Skip offline or unauthorized devices
                if serial in ("offline", "unauthorized"):
                    continue

                device_info = {"serial": serial, "model": "", "android_version": ""}

                # Extract model from the device properties
                try:
                    model_output = self._run_adb(
                        ["-s", serial, "shell", "getprop", "ro.product.model"]
                    )
                    device_info["model"] = model_output.strip()
                except subprocess.SubprocessError:
                    pass

                try:
                    version_output = self._run_adb(
                        ["-s", serial, "shell", "getprop", "ro.build.version.release"]
                    )
                    device_info["android_version"] = version_output.strip()
                except subprocess.SubprocessError:
                    pass

                devices.append(device_info)

        except (FileNotFoundError, subprocess.SubprocessError) as e:
            logger.warning(f"Failed to list ADB devices: {e}")

        return devices

    def extract_chrome_cookies(
        self,
        device_profile_path: str,
        site_filter: Optional[SiteFilter] = None,
    ) -> List[Dict]:
        """
        Extract Chrome cookies from an Android device.

        Pulls the Cookies SQLite database from the device, then parses
        it locally using CookieExtractor.

        Args:
            device_profile_path: Path to Chrome profile on the device.
                                Typically /data/data/com.android.chrome/app_chrome/Default
            site_filter: Optional SiteFilter to filter cookies.

        Returns:
            List of cookie dictionaries.
        """
        remote_path = os.path.join(device_profile_path, "Cookies")
        return self._extract_from_device(remote_path, "chrome", site_filter)

    def extract_firefox_cookies(
        self,
        device_profile_path: str,
        site_filter: Optional[SiteFilter] = None,
    ) -> List[Dict]:
        """
        Extract Firefox cookies from an Android device.

        Pulls the cookies.sqlite database from the device, then parses
        it locally using CookieExtractor.

        Args:
            device_profile_path: Path to Firefox profile on the device.
                                Typically /data/data/org.mozilla.firefox/files/mozilla/<profile>
            site_filter: Optional SiteFilter to filter cookies.

        Returns:
            List of cookie dictionaries.
        """
        remote_path = os.path.join(device_profile_path, "cookies.sqlite")
        return self._extract_from_device(remote_path, "firefox", site_filter)

    def _extract_from_device(
        self,
        remote_path: str,
        browser: str,
        site_filter: Optional[SiteFilter] = None,
    ) -> List[Dict]:
        """
        Pull a database file from the device and extract cookies.

        Args:
            remote_path: Path to the database file on the device.
            browser: Browser type (chrome or firefox).
            site_filter: Optional SiteFilter to filter cookies.

        Returns:
            List of cookie dictionaries.
        """
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix="tokenade_adb_")

            # Create a profile directory structure that CookieExtractor expects
            profile_dir = os.path.join(temp_dir, "profile")
            os.makedirs(profile_dir, exist_ok=True)

            if browser == "chrome":
                local_path = os.path.join(profile_dir, "Cookies")
            else:
                local_path = os.path.join(profile_dir, "cookies.sqlite")

            self._pull_file(remote_path, local_path)

            if not os.path.exists(local_path):
                logger.warning(f"Failed to pull cookies database from device: {remote_path}")
                return []

            try:
                extractor = CookieExtractor(profile_dir, browser=browser)
                if browser == "chrome":
                    cookies = extractor.extract_chrome(site_filter)
                else:
                    cookies = extractor.extract_firefox(site_filter)
            finally:
                # Clean up copied database
                if os.path.exists(local_path):
                    os.remove(local_path)
                    for suffix in ("-wal", "-shm"):
                        if os.path.exists(local_path + suffix):
                            os.remove(local_path + suffix)

            return cookies

        except (FileNotFoundError, subprocess.SubprocessError) as e:
            logger.warning(f"Failed to extract cookies from device: {e}")
            return []
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _run_adb(self, args: List[str]) -> str:
        """
        Run an ADB command and return stdout.

        Args:
            args: List of arguments to pass to adb (without the 'adb' prefix).

        Returns:
            stdout output from the command.

        Raises:
            FileNotFoundError: If adb is not installed.
            subprocess.SubprocessError: If the command fails.
        """
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(args)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise subprocess.SubprocessError(
                f"ADB command failed: {' '.join(cmd)}: {result.stderr}"
            )
        return result.stdout

    def _pull_file(self, remote_path: str, local_path: str) -> None:
        """
        Pull a file from the Android device via ADB.

        Args:
            remote_path: Path to the file on the device.
            local_path: Local path to save the file.

        Raises:
            FileNotFoundError: If adb is not installed.
            subprocess.SubprocessError: If the pull command fails.
        """
        self._run_adb(["pull", remote_path, local_path])
