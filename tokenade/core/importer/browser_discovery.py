"""
Browser Profile Discovery - find real browser profiles by on-disk signatures.

Discovery intentionally does not depend on hardcoded browser profile locations.
It scans configured filesystem roots and recognizes profile directories from the
files browsers actually create, such as Firefox `cookies.sqlite` and Chromium
`Preferences` plus cookie/storage databases.
"""

from __future__ import annotations

import configparser
import json
import logging
import os
import platform
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class BrowserProfile:
    """Represents a discovered browser profile."""

    name: str
    path: str
    browser: str  # chrome, firefox, edge, brave, vivaldi
    last_used: Optional[str] = None
    is_default: bool = False

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "path": self.path,
            "browser": self.browser,
            "last_used": self.last_used,
            "is_default": self.is_default,
        }


class BrowserProfileDiscovery:
    """Discovers browser profiles on the current system."""

    SUPPORTED_BROWSERS = ("chrome", "firefox", "edge", "brave", "vivaldi")
    SCAN_ROOTS_ENV = "TOKENADE_PROFILE_SCAN_ROOTS"
    MAX_DEPTH_ENV = "TOKENADE_PROFILE_SCAN_MAX_DEPTH"
    CACHE_PATH_ENV = "TOKENADE_BROWSER_PATHS_CACHE"
    CACHE_MAX_AGE_ENV = "TOKENADE_BROWSER_PATHS_CACHE_MAX_AGE"
    DEFAULT_MAX_DEPTH = 12
    FAST_SCAN_DEPTH = 6
    DEFAULT_PERSISTENT_CACHE_MAX_AGE = 3600.0
    CACHE_VERSION = 1

    _PRUNE_DIRS = {
        ".cache",
        ".cargo",
        ".git",
        ".gradle",
        ".local/share/Trash",
        ".npm",
        ".rustup",
        "__pycache__",
        "node_modules",
        "target",
        "venv",
        ".venv",
    }

    _CHROMIUM_MARKERS = {
        "Preferences",
        "Secure Preferences",
        "History",
        "Login Data",
        "Web Data",
        "Local Storage",
        "IndexedDB",
    }

    def __init__(
        self,
        cache_ttl: float = 60.0,
        scan_roots: Optional[Iterable[str]] = None,
        max_depth: Optional[int] = None,
    ):
        self.os_type = platform.system()
        self._cache_ttl = cache_ttl
        self._browser_cache: Dict[str, List[BrowserProfile]] = {}
        self._browser_cache_time: Dict[str, float] = {}
        self._scan_roots = list(scan_roots) if scan_roots is not None else None
        self._max_depth = max_depth

    def _expand_path(self, path: str) -> str:
        """Expand environment variables and user home."""
        expanded = os.path.expandvars(path)
        expanded = os.path.expanduser(expanded)
        return expanded

    def _path_exists(self, path: str) -> bool:
        """Check if a path exists after expansion."""
        return os.path.exists(self._expand_path(path))

    def clear_cache(self) -> None:
        """Drop cached profile discovery results."""
        self._browser_cache.clear()
        self._browser_cache_time.clear()

    def _cache_fresh(self, browser: str) -> bool:
        if browser not in self._browser_cache:
            return False
        age = time.time() - self._browser_cache_time.get(browser, 0.0)
        return age < self._cache_ttl

    def _persistent_cache_path(self) -> Path:
        override = os.environ.get(self.CACHE_PATH_ENV)
        if override:
            return Path(self._expand_path(override))
        return Path.home() / ".tokenade" / "browser_paths.json"

    def _persistent_cache_enabled(self) -> bool:
        return self._scan_roots is None or bool(os.environ.get(self.CACHE_PATH_ENV))

    def _persistent_cache_max_age(self) -> float:
        raw = os.environ.get(self.CACHE_MAX_AGE_ENV)
        if raw:
            try:
                return max(0.0, float(raw))
            except ValueError:
                logger.warning("Ignoring invalid %s=%r", self.CACHE_MAX_AGE_ENV, raw)
        return self.DEFAULT_PERSISTENT_CACHE_MAX_AGE

    def _cache_payload(self, profiles_by_browser: Dict[str, List[BrowserProfile]]) -> Dict:
        return {
            "version": self.CACHE_VERSION,
            "created_at": time.time(),
            "scan_roots": [str(p) for p in self._discovery_roots()],
            "profiles": {
                browser: [profile.to_dict() for profile in profiles]
                for browser, profiles in profiles_by_browser.items()
            },
        }

    def _write_persistent_cache(self, profiles_by_browser: Dict[str, List[BrowserProfile]]) -> None:
        if not self._persistent_cache_enabled():
            return
        path = self._persistent_cache_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._cache_payload(profiles_by_browser), indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug("Failed to write browser profile cache %s: %s", path, e)

    def _profile_from_cache(self, item: Dict) -> Optional[BrowserProfile]:
        try:
            path = Path(str(item.get("path") or ""))
            browser = str(item.get("browser") or "").lower()
            if browser not in self.SUPPORTED_BROWSERS:
                return None
            if not path.exists() or not path.is_dir():
                return None
            if self._is_junk_profile_path(path):
                return None
            return BrowserProfile(
                name=str(item.get("name") or path.name),
                path=str(path),
                browser=browser,
                last_used=item.get("last_used"),
                is_default=bool(item.get("is_default", False)),
            )
        except Exception:
            return None

    def _read_persistent_cache(self) -> Optional[Dict[str, List[BrowserProfile]]]:
        if not self._persistent_cache_enabled():
            return None
        path = self._persistent_cache_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("version") != self.CACHE_VERSION:
                return None
            cached_roots = [str(p) for p in data.get("scan_roots", [])]
            current_roots = [str(p) for p in self._discovery_roots()]
            if cached_roots and cached_roots != current_roots:
                return None
            created_at = float(data.get("created_at") or 0.0)
            if time.time() - created_at > self._persistent_cache_max_age():
                return None
            profiles_raw = data.get("profiles") or {}
            result = {browser: [] for browser in self.SUPPORTED_BROWSERS}
            for browser, items in profiles_raw.items():
                key = str(browser).lower()
                if key not in result or not isinstance(items, list):
                    continue
                for item in items:
                    if isinstance(item, dict):
                        profile = self._profile_from_cache(item)
                        if profile:
                            result[key].append(profile)
            if any(result.values()):
                return result
        except Exception as e:
            logger.debug("Failed to read browser profile cache %s: %s", path, e)
        return None

    def refresh_cache(self) -> Dict[str, List[BrowserProfile]]:
        """Force a profile scan and persist results to the browser path cache."""
        all_profiles = [] if self._max_depth is not None else self._scan_profiles_fast()
        if not all_profiles:
            all_profiles = self._scan_profiles()
        result = {
            browser: [p for p in all_profiles if p.browser == browser]
            for browser in self.SUPPORTED_BROWSERS
        }
        now = time.time()
        for browser, profiles in result.items():
            self._browser_cache[browser] = profiles
            self._browser_cache_time[browser] = now
        self._write_persistent_cache(result)
        return {browser: list(profiles) for browser, profiles in result.items()}

    def _max_scan_depth(self) -> int:
        if self._max_depth is not None:
            return self._max_depth
        raw = os.environ.get(self.MAX_DEPTH_ENV)
        if raw:
            try:
                return max(1, int(raw))
            except ValueError:
                logger.warning("Ignoring invalid %s=%r", self.MAX_DEPTH_ENV, raw)
        return self.DEFAULT_MAX_DEPTH

    def _discovery_roots(self) -> List[Path]:
        roots = self._scan_roots
        if roots is None:
            env_roots = os.environ.get(self.SCAN_ROOTS_ENV)
            if env_roots:
                roots = [p for p in env_roots.split(os.pathsep) if p.strip()]
            else:
                roots = [str(Path.home())]

        resolved: List[Path] = []
        seen: Set[str] = set()
        for root in roots:
            try:
                path = Path(self._expand_path(str(root))).resolve()
            except Exception:
                continue
            key = os.path.normcase(str(path))
            if key in seen or not path.exists() or not path.is_dir():
                continue
            seen.add(key)
            resolved.append(path)
        return resolved

    def _fast_scan_roots(self) -> List[Path]:
        roots: List[Path] = []
        seen: Set[str] = set()
        for root in self._discovery_roots():
            candidates = [root]
            for name in ("snap", ".config", ".var", "Library", "AppData"):
                candidates.append(root / name)
            for candidate in candidates:
                try:
                    resolved = candidate.resolve()
                except Exception:
                    continue
                key = os.path.normcase(str(resolved))
                if key in seen or not resolved.exists() or not resolved.is_dir():
                    continue
                seen.add(key)
                roots.append(resolved)
        return roots

    def _should_prune(self, root: Path, current: Path, dirname: str) -> bool:
        if dirname in self._PRUNE_DIRS:
            return True
        try:
            rel = current.joinpath(dirname).relative_to(root).as_posix()
        except ValueError:
            return False
        return rel in self._PRUNE_DIRS

    def _walk_profile_candidates(
        self,
        roots: Optional[Iterable[Path]] = None,
        max_depth: Optional[int] = None,
    ) -> Iterable[Path]:
        max_depth = max_depth if max_depth is not None else self._max_scan_depth()
        roots = list(roots) if roots is not None else self._discovery_roots()
        emitted: Set[str] = set()

        for root in roots:
            for current_str, dirs, files in os.walk(root, topdown=True, followlinks=False):
                current = Path(current_str)
                try:
                    depth = len(current.relative_to(root).parts)
                except ValueError:
                    depth = 0
                if depth >= max_depth:
                    dirs[:] = []
                else:
                    dirs[:] = [d for d in dirs if not self._should_prune(root, current, d)]

                file_set = set(files)
                dir_set = set(dirs)
                if self._looks_like_firefox_profile(file_set, dir_set):
                    key = os.path.normcase(str(current.resolve()))
                    if key not in emitted:
                        emitted.add(key)
                        yield current
                    dirs[:] = []
                    continue
                if self._looks_like_chromium_profile(file_set, dir_set, current):
                    key = os.path.normcase(str(current.resolve()))
                    if key not in emitted:
                        emitted.add(key)
                        yield current
                    dirs[:] = []

    def _looks_like_firefox_profile(self, files: Set[str], dirs: Set[str]) -> bool:
        if "cookies.sqlite" in files:
            return True
        if "prefs.js" in files and ({"storage", "bookmarkbackups", "sessionstore-backups"} & dirs):
            return True
        return False

    def _looks_like_chromium_profile(self, files: Set[str], dirs: Set[str], path: Path) -> bool:
        if "Preferences" not in files:
            return False
        if not self._has_chromium_user_data_parent(path):
            return False
        if "Cookies" in files or "History" in files or "Login Data" in files:
            return True
        if "Network" in dirs and path.joinpath("Network", "Cookies").exists():
            return True
        return bool(self._CHROMIUM_MARKERS & dirs)

    def _has_chromium_user_data_parent(self, path: Path) -> bool:
        local_state = path.parent / "Local State"
        if not local_state.exists():
            return False
        name = path.name
        if name in {"Default", "Guest Profile", "System Profile"} or name.startswith("Profile "):
            return True
        try:
            data = json.loads(local_state.read_text(encoding="utf-8"))
            info_cache = data.get("profile", {}).get("info_cache", {})
            return name in info_cache
        except Exception:
            return False

    def _parse_firefox_profiles_ini(
        self,
        roots: Optional[Iterable[Path]] = None,
        max_depth: Optional[int] = None,
    ) -> Dict[str, Tuple[str, bool]]:
        profiles: Dict[str, Tuple[str, bool]] = {}
        max_depth = max_depth if max_depth is not None else self._max_scan_depth()
        roots = list(roots) if roots is not None else self._discovery_roots()
        for root in roots:
            for current_str, dirs, files in os.walk(root, topdown=True, followlinks=False):
                current = Path(current_str)
                try:
                    depth = len(current.relative_to(root).parts)
                except ValueError:
                    depth = 0
                if depth >= max_depth:
                    dirs[:] = []
                else:
                    dirs[:] = [d for d in dirs if not self._should_prune(root, current, d)]
                if "profiles.ini" not in files:
                    continue
                ini_path = current / "profiles.ini"
                try:
                    config = configparser.ConfigParser()
                    config.read(ini_path)
                    for section in config.sections():
                        if not section.startswith("Profile"):
                            continue
                        name = config.get(section, "Name", fallback=section)
                        path_value = config.get(section, "Path", fallback="")
                        if not path_value:
                            continue
                        is_relative = config.getboolean(section, "IsRelative", fallback=True)
                        is_default = config.getboolean(section, "Default", fallback=False)
                        profile_path = (ini_path.parent / path_value) if is_relative else Path(path_value)
                        try:
                            key = os.path.normcase(str(profile_path.resolve()))
                        except Exception:
                            key = os.path.normcase(str(profile_path))
                        profiles[key] = (name, is_default)
                except Exception as e:
                    logger.debug("Failed to parse Firefox profiles.ini at %s: %s", ini_path, e)
        return profiles

    def _classify_browser(self, path: Path) -> str:
        if path.joinpath("cookies.sqlite").exists() or path.joinpath("prefs.js").exists():
            return "firefox"

        # Full path: Windows is .../Microsoft/Edge/User Data/Default (last-3
        # tokens alone miss "Microsoft" and never match "microsoft edge").
        # Match whole path components only — never substring-scan joined paths
        # (pytest tmp dirs like test_classifies_edge_brave_* would false-hit).
        parts_l = [p.lower() for p in path.parts]

        def _is_component(name: str) -> bool:
            return name in parts_l

        def _component_startswith(prefix: str) -> bool:
            return any(p == prefix or p.startswith(prefix + " ") for p in parts_l)

        # Brave: BraveSoftware/... or a path component named brave
        if _is_component("bravesoftware") or _is_component("brave-browser"):
            return "brave"
        if _is_component("brave"):
            return "brave"

        for i, p in enumerate(parts_l):
            if p in ("microsoft-edge", "microsoft-edge-dev", "microsoft-edge-beta"):
                return "edge"
            if p == "microsoft edge" or p.startswith("microsoft edge "):
                return "edge"
            if p == "microsoft" and i + 1 < len(parts_l):
                nxt = parts_l[i + 1]
                # Edge, Edge Beta, Edge Dev, Edge SxS
                if nxt == "edge" or nxt.startswith("edge "):
                    return "edge"

        if _is_component("vivaldi") or _component_startswith("vivaldi"):
            return "vivaldi"
        if _is_component("chromium"):
            return "chrome"
        if _is_component("chrome") or _is_component("google-chrome") or _is_component("google"):
            return "chrome"
        # "Google/Chrome" style
        for i, p in enumerate(parts_l):
            if p == "google" and i + 1 < len(parts_l) and parts_l[i + 1] == "chrome":
                return "chrome"
        return "chrome"

    def _profile_name(self, path: Path, browser: str, firefox_ini: Dict[str, Tuple[str, bool]]) -> str:
        try:
            key = os.path.normcase(str(path.resolve()))
        except Exception:
            key = os.path.normcase(str(path))
        if browser == "firefox" and key in firefox_ini:
            return firefox_ini[key][0]

        prefs_path = path / "Preferences"
        if prefs_path.exists():
            try:
                prefs = json.loads(prefs_path.read_text(encoding="utf-8"))
                name = prefs.get("profile", {}).get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
            except Exception:
                pass
        return path.name

    def _is_default_profile(self, path: Path, browser: str, firefox_ini: Dict[str, Tuple[str, bool]]) -> bool:
        try:
            key = os.path.normcase(str(path.resolve()))
        except Exception:
            key = os.path.normcase(str(path))
        if browser == "firefox" and key in firefox_ini:
            return firefox_ini[key][1]
        return path.name.lower() in {"default", "default-release"} or "default" in path.name.lower()

    @staticmethod
    def _is_junk_profile_path(path: Path) -> bool:
        """Skip embedded WebViews, temp cloak copies, automation sandboxes."""
        try:
            parts = [p.lower() for p in path.parts]
        except Exception:
            parts = []
        joined = "/".join(parts)
        # Windows WebView2 / system shell host (not a real Chrome install)
        junk_components = (
            "ebwebview",
            "webview2",
            "msedgewebview2",
            "tokenade_cloak_clean",
            "tokenade_profile",
            "playwright",
            "ms-playwright",
            "puppeteer",
        )
        for part in parts:
            if part in junk_components or part.startswith("tokenade_cloak"):
                return True
        # Temp cloak clean profiles: .../Temp/.../tokenade_cloak_clean_*/
        if "temp" in parts or "tmp" in parts:
            if "tokenade" in joined and ("cloak" in joined or "clean" in joined):
                return True
        # Packages\*\LocalState\EBWebView
        if "packages" in parts and "ebwebview" in joined:
            return True
        if "localstate" in parts and "ebwebview" in joined:
            return True
        return False

    def _scan_profiles(
        self,
        roots: Optional[Iterable[Path]] = None,
        max_depth: Optional[int] = None,
    ) -> List[BrowserProfile]:
        firefox_ini = self._parse_firefox_profiles_ini(roots=roots, max_depth=max_depth)
        profiles: List[BrowserProfile] = []
        seen: Set[Tuple[str, str]] = set()
        for path in self._walk_profile_candidates(roots=roots, max_depth=max_depth):
            if self._is_junk_profile_path(path):
                continue
            browser = self._classify_browser(path)
            if browser not in self.SUPPORTED_BROWSERS:
                continue
            try:
                resolved = str(path.resolve())
            except Exception:
                resolved = str(path)
            key = (browser, os.path.normcase(resolved))
            if key in seen:
                continue
            seen.add(key)
            profiles.append(BrowserProfile(
                name=self._profile_name(path, browser, firefox_ini),
                path=resolved,
                browser=browser,
                is_default=self._is_default_profile(path, browser, firefox_ini),
            ))
        profiles.sort(key=lambda p: (p.browser, not p.is_default, p.name.lower(), p.path))
        logger.info("Discovered %d browser profiles", len(profiles))
        return profiles

    def _scan_profiles_fast(self) -> List[BrowserProfile]:
        return self._scan_profiles(roots=self._fast_scan_roots(), max_depth=self.FAST_SCAN_DEPTH)

    def _scan_browser(self, browser: str) -> List[BrowserProfile]:
        profiles = [] if self._max_depth is not None else [p for p in self._scan_profiles_fast() if p.browser == browser]
        if profiles:
            return profiles
        return [p for p in self._scan_profiles() if p.browser == browser]

    def discover_chrome_profiles(self) -> List[BrowserProfile]:
        """Discover Chrome/Chromium profiles."""
        return self.discover_browser("chrome")

    def discover_firefox_profiles(self) -> List[BrowserProfile]:
        """Discover Firefox profiles."""
        return self.discover_browser("firefox")

    def discover_edge_profiles(self) -> List[BrowserProfile]:
        """Discover Edge profiles."""
        return self.discover_browser("edge")

    def discover_brave_profiles(self) -> List[BrowserProfile]:
        """Discover Brave profiles."""
        return self.discover_browser("brave")

    def discover_vivaldi_profiles(self) -> List[BrowserProfile]:
        """Discover Vivaldi profiles."""
        return self.discover_browser("vivaldi")

    def discover_browser(self, browser: str, use_cache: bool = True) -> List[BrowserProfile]:
        """Discover profiles for a single browser (cached)."""
        key = (browser or "").lower()
        if key == "chromium":
            key = "chrome"
        if key not in self.SUPPORTED_BROWSERS:
            return []

        if use_cache and self._cache_fresh(key):
            return list(self._browser_cache[key])

        if use_cache:
            cached = self._read_persistent_cache()
            if cached is not None:
                now = time.time()
                for cached_browser, cached_profiles in cached.items():
                    self._browser_cache[cached_browser] = list(cached_profiles)
                    self._browser_cache_time[cached_browser] = now
                return list(cached.get(key, []))

        profiles = self._scan_browser(key)
        self._browser_cache[key] = profiles
        self._browser_cache_time[key] = time.time()
        return list(profiles)

    def discover_all(self, use_cache: bool = True) -> Dict[str, List[BrowserProfile]]:
        """Discover all browser profiles (per-browser cache)."""
        if use_cache and all(self._cache_fresh(browser) for browser in self.SUPPORTED_BROWSERS):
            return {browser: list(self._browser_cache[browser]) for browser in self.SUPPORTED_BROWSERS}

        if use_cache:
            cached = self._read_persistent_cache()
            if cached is not None:
                now = time.time()
                for browser, profiles in cached.items():
                    self._browser_cache[browser] = list(profiles)
                    self._browser_cache_time[browser] = now
                return {browser: list(cached.get(browser, [])) for browser in self.SUPPORTED_BROWSERS}

        return self.refresh_cache()

    def get_profile(self, browser: str, name: str) -> Optional[BrowserProfile]:
        """Get a specific profile by browser and name."""
        wanted = (name or "").lower()
        for profile in self.discover_browser(browser):
            if profile.name.lower() == wanted or Path(profile.path).name.lower() == wanted:
                return profile
        return None

    def get_default_profile(self, browser: str) -> Optional[BrowserProfile]:
        """Get the default profile for a browser (single-browser scan only)."""
        profiles = self.discover_browser(browser)
        for profile in profiles:
            if profile.is_default:
                return profile
        return profiles[0] if profiles else None

    def list_launch_browsers(self, use_cache: bool = True) -> List[Tuple[str, str]]:
        """Build browser Select options from one cached profile scan (+ cloak).

        Labels are plain browser names. Profiles are listed separately via
        ``list_profiles_for_browser``. Cloak is always first.
        """
        options: List[Tuple[str, str]] = []
        try:
            from tokenade.core.browser.stealth.cloak import (
                is_binary_installed,
                is_cloakbrowser_available,
            )
            if is_cloakbrowser_available():
                if is_binary_installed():
                    options.append(("cloak", "cloak"))
                else:
                    options.append(("cloak (install on launch)", "cloak"))
            else:
                options.append(("cloak (pip install)", "cloak"))
        except Exception:
            options.append(("cloak", "cloak"))

        profiles_by_browser = self.discover_all(use_cache=use_cache)
        for browser in self.SUPPORTED_BROWSERS:
            profiles = profiles_by_browser.get(browser) or []
            if profiles:
                options.append((browser, browser))
        # Any extra keys discovery may return beyond SUPPORTED_BROWSERS
        for browser, profiles in sorted(profiles_by_browser.items()):
            if not profiles:
                continue
            key = (browser or "").lower()
            if key in ("", "cloak", "cloakbrowser"):
                continue
            if any(v == key for _, v in options):
                continue
            options.append((key, key))

        seen: Set[str] = set()
        out: List[Tuple[str, str]] = []
        for label, value in options:
            if value in seen:
                continue
            seen.add(value)
            out.append((label, value))
        return out or [("cloak", "cloak")]

    def list_export_browsers(self, use_cache: bool = True) -> List[Tuple[str, str]]:
        """Browsers with on-disk profiles suitable for ``tokenade export``.

        Dynamic from ``discover_all`` — no cloak. Label includes profile count.
        Value is the browser key for ``--browser-name``.
        """
        profiles_by_browser = self.discover_all(use_cache=use_cache)
        options: List[Tuple[str, str]] = []
        seen: Set[str] = set()
        # Prefer known order, then any other discovered keys
        ordered = list(self.SUPPORTED_BROWSERS)
        for browser in profiles_by_browser:
            key = (browser or "").lower()
            if key and key not in ordered and key not in ("cloak", "cloakbrowser"):
                ordered.append(key)
        for browser in ordered:
            profiles = profiles_by_browser.get(browser) or []
            if not profiles:
                continue
            key = (browser or "").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            n = len(profiles)
            label = f"{key} ({n} profile{'s' if n != 1 else ''})"
            options.append((label, key))
        return options

    CLEAN_PROFILE_VALUE = "__clean__"

    def list_profiles_for_browser(
        self, browser: str, use_cache: bool = True
    ) -> List[Tuple[str, str]]:
        """Profile Select options for a browser: (label, profile_name).

        Cloak has no system profiles — returns a single clean-profile option.
        Clean profile value is ``CLEAN_PROFILE_VALUE`` (not a real profile name).
        """
        clean = self.CLEAN_PROFILE_VALUE
        key = (browser or "").lower()
        if key in ("cloak", "cloakbrowser", ""):
            return [("clean profile", clean)]
        profiles = self.discover_browser(key, use_cache=use_cache)
        if not profiles:
            return [("clean profile", clean)]
        opts: List[Tuple[str, str]] = [("clean profile", clean)]
        for p in profiles:
            folder = Path(p.path).name
            display = (p.name or "").strip() or folder
            # Firefox dirs often look like "xxxxxxxx.Profile Name" when ini Name missed
            if display == folder and "." in folder:
                head, _, tail = folder.partition(".")
                if len(head) >= 6 and head.isalnum() and tail.strip():
                    display = tail.strip()
            # Friendly name first; technical folder id in brackets when different
            if display and folder and display != folder:
                label = f"{display} ({folder})"
            else:
                label = display or folder or "profile"
            if p.is_default:
                label = f"{label} · default"
            # value stays the discovery name so --profile still resolves
            opts.append((label, p.name))
        return opts

    def list_profiles_text(self) -> str:
        """Generate a text listing of all profiles."""
        lines = []
        lines.append("=" * 60)
        lines.append("BROWSER PROFILES")
        lines.append("=" * 60)

        all_profiles = self.discover_all()
        total = 0

        for browser, profiles in all_profiles.items():
            if not profiles:
                continue
            lines.append(f"\n{browser.upper()}:")
            for p in profiles:
                default_mark = " (default)" if p.is_default else ""
                lines.append(f"  - {p.name}{default_mark}")
                lines.append(f"    Path: {p.path}")
                total += 1

        if total == 0:
            lines.append("\nNo browser profiles found.")

        lines.append(f"\nTotal profiles: {total}")
        return "\n".join(lines)
