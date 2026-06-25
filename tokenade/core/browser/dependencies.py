"""
System Dependency Checker & Installer.

Checks for required system dependencies and installs missing ones.
This prevents bot detection that flags browsers with missing dependencies.
"""

import logging
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

LINUX_DEPENDENCIES = {
    "chromium": [
        "libgtk-3-0", "libnspr4", "libpango-1.0-0", "libxss1",
        "fonts-liberation", "libnss3", "libatk-bridge2.0-0",
        "libdrm2", "libgbm1", "libasound2", "libxcomposite1",
        "libxdamage1", "libxrandr2", "libxfixes3", "libxcursor1",
        "libxi6", "libxtst6", "libatk1.0-0", "libcups2",
        "libdbus-1-3", "libexpat1", "libxkbcommon0",
    ],
    "firefox": [
        "libgtk-3-0", "libdbus-glib-1-2", "libxt6",
        "libasound2", "libcanberra-gtk3-0", "libdbus-1-3",
    ],
}

PLAYWRIGHT_SYSTEM_DEPS = [
    "libgtk-3-0", "libnspr4", "libpango-1.0-0", "libxss1",
    "fonts-liberation", "libnss3", "libatk-bridge2.0-0",
    "libdrm2", "libgbm1", "libasound2", "libxcomposite1",
    "libxdamage1", "libxrandr2", "libxfixes3", "libxcursor1",
    "libxi6", "libxtst6", "libatk1.0-0", "libcups2",
    "libdbus-1-3", "libexpat1", "libxkbcommon0",
    "libglib2.0-0", "libspeechd2", "libspice-client-glib-2.0-4",
    "libatspi2.0-0", "libxshmfence1", "libwayland-client0",
]


@dataclass
class DependencyCheckResult:
    """Result of a dependency check."""
    name: str
    installed: bool
    package: Optional[str] = None
    version: Optional[str] = None


@dataclass
class DependencyInstallResult:
    """Result of a dependency installation attempt."""
    name: str
    success: bool
    message: str


class DependencyChecker:
    """Check and install system dependencies."""

    def __init__(self):
        self.system = platform.system().lower()
        self.package_manager = self._detect_package_manager()

    def _detect_package_manager(self) -> Optional[str]:
        """Detect the available package manager."""
        if self.system != "linux":
            return None
        for pm in ["apt", "dnf", "yum", "pacman", "zypper"]:
            if shutil.which(pm):
                return pm
        return None

    def check_package(self, package: str) -> DependencyCheckResult:
        """Check if a system package is installed."""
        if self.system == "linux":
            if self.package_manager in ("apt", "dpkg"):
                try:
                    result = subprocess.run(
                        ["dpkg", "-s", package],
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0:
                        version = None
                        for line in result.stdout.split("\n"):
                            if line.startswith("Version:"):
                                version = line.split(":", 1)[1].strip()
                                break
                        return DependencyCheckResult(
                            name=package, installed=True,
                            package=package, version=version
                        )
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass
            elif self.package_manager in ("dnf", "yum", "rpm"):
                try:
                    result = subprocess.run(
                        ["rpm", "-q", package],
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0:
                        return DependencyCheckResult(
                            name=package, installed=True,
                            package=package, version=result.stdout.strip()
                        )
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass
            elif self.package_manager == "pacman":
                try:
                    result = subprocess.run(
                        ["pacman", "-Qi", package],
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0:
                        return DependencyCheckResult(
                            name=package, installed=True, package=package
                        )
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass
        return DependencyCheckResult(name=package, installed=False, package=package)

    def check_all(self, browser_type: str = "chromium") -> List[DependencyCheckResult]:
        """Check all dependencies for a browser type."""
        if self.system != "linux":
            logger.info(f"Dependency checking not needed on {self.system}")
            return []

        deps = LINUX_DEPENDENCIES.get(browser_type, LINUX_DEPENDENCIES["chromium"])
        return [self.check_package(dep) for dep in deps]

    def check_playwright_deps(self) -> List[DependencyCheckResult]:
        """Check Playwright-specific dependencies."""
        if self.system != "linux":
            return []
        return [self.check_package(dep) for dep in PLAYWRIGHT_SYSTEM_DEPS]

    def install_package(self, package: str) -> DependencyInstallResult:
        """Attempt to install a system package."""
        if self.system != "linux":
            return DependencyInstallResult(
                name=package, success=False,
                message=f"Package installation not supported on {self.system}"
            )

        if not self.package_manager:
            return DependencyInstallResult(
                name=package, success=False,
                message="No package manager found"
            )

        try:
            if self.package_manager == "apt":
                cmd = ["sudo", "apt-get", "install", "-y", package]
            elif self.package_manager == "dnf":
                cmd = ["sudo", "dnf", "install", "-y", package]
            elif self.package_manager == "yum":
                cmd = ["sudo", "yum", "install", "-y", package]
            elif self.package_manager == "pacman":
                cmd = ["sudo", "pacman", "-S", "--noconfirm", package]
            elif self.package_manager == "zypper":
                cmd = ["sudo", "zypper", "install", "-y", package]
            else:
                return DependencyInstallResult(
                    name=package, success=False,
                    message=f"Unsupported package manager: {self.package_manager}"
                )

            logger.info(f"Installing {package} via {self.package_manager}...")
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )

            if result.returncode == 0:
                logger.info(f"Successfully installed {package}")
                return DependencyInstallResult(
                    name=package, success=True,
                    message=f"Installed via {self.package_manager}"
                )
            else:
                error = result.stderr[:200] if result.stderr else "Unknown error"
                return DependencyInstallResult(
                    name=package, success=False,
                    message=f"Install failed: {error}"
                )
        except subprocess.TimeoutExpired:
            return DependencyInstallResult(
                name=package, success=False,
                message="Installation timed out"
            )
        except FileNotFoundError:
            return DependencyInstallResult(
                name=package, success=False,
                message=f"Package manager '{self.package_manager}' not found"
            )

    def install_missing(self, browser_type: str = "chromium") -> List[DependencyInstallResult]:
        """Install all missing dependencies for a browser type."""
        results = []
        checks = self.check_all(browser_type)
        for check in checks:
            if not check.installed:
                result = self.install_package(check.package)
                results.append(result)
        return results

    def install_playwright_deps(self) -> List[DependencyInstallResult]:
        """Install all missing Playwright dependencies."""
        results = []
        checks = self.check_playwright_deps()
        for check in checks:
            if not check.installed:
                result = self.install_package(check.package)
                results.append(result)
        return results

    def get_report(self, browser_type: str = "chromium") -> Dict:
        """Generate a dependency report."""
        checks = self.check_all(browser_type)
        installed = [c for c in checks if c.installed]
        missing = [c for c in checks if not c.installed]

        return {
            "system": self.system,
            "package_manager": self.package_manager,
            "browser_type": browser_type,
            "total": len(checks),
            "installed": len(installed),
            "missing": len(missing),
            "missing_packages": [c.name for c in missing],
            "all_installed": len(missing) == 0,
        }

    def ensure_playwright_deps(self) -> bool:
        """Ensure Playwright dependencies are installed. Returns True if all present."""
        if self.system != "linux":
            return True

        checks = self.check_playwright_deps()
        missing = [c for c in checks if not c.installed]

        if not missing:
            logger.info("All Playwright dependencies are installed")
            return True

        logger.warning(f"Missing {len(missing)} Playwright dependencies: {[c.name for c in missing]}")

        results = self.install_playwright_deps()
        failed = [r for r in results if not r.success]

        if failed:
            logger.error(f"Failed to install {len(failed)} dependencies: {[r.name for r in failed]}")
            return False

        logger.info("All Playwright dependencies installed successfully")
        return True


def check_system_deps(browser_type: str = "chromium") -> Dict:
    """Quick check for system dependencies."""
    checker = DependencyChecker()
    return checker.get_report(browser_type)


def install_system_deps(browser_type: str = "chromium") -> List[DependencyInstallResult]:
    """Install missing system dependencies."""
    checker = DependencyChecker()
    return checker.install_missing(browser_type)
