"""
Plugin registry with multi-source support.

Supports multiple registries (local directories and remote URLs) stored
in ~/.tokenade/preferences.json. Registries are merged, deduplicated by
name, and the first match wins for installs when no registry is specified.

Local registries are auto-detected: a directory path containing plugins.json
and a plugins/ subdirectory. Remote registries are HTTP URLs.
"""

import json
import logging
import os
import shutil
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from packaging.version import Version


def _version_lt(a: str, b: str) -> bool:
    """Return True if version a < version b."""
    try:
        return Version(a) < Version(b)
    except Exception:
        return a < b


logger = logging.getLogger(__name__)

DEFAULT_REMOTE_REGISTRY = "https://tokenade-plugins.pages.dev"
DEFAULT_PLUGINS_DIR = Path.home() / ".tokenade" / "plugins"
PREFERENCES_FILE = Path.home() / ".tokenade" / "preferences.json"

CATEGORIES = [
    {"name": "authentication", "description": "OAuth2, SSO, API token refresh", "icon": "🔐"},
    {"name": "site-handlers", "description": "Custom extraction/injection for specific sites", "icon": "🌐"},
    {"name": "export-formats", "description": "Custom session export formats", "icon": "📤"},
    {"name": "validators", "description": "Custom session validation rules", "icon": "✅"},
    {"name": "notifications", "description": "Webhook, Slack, Discord notifications", "icon": "🔔"},
    {"name": "security", "description": "Encryption, signing, audit logging", "icon": "🔒"},
]


@dataclass
class Plugin:
    """Plugin metadata."""
    name: str
    version: str
    description: str
    author: str
    url: str
    type: str
    entry_point: str
    dependencies: List[str] = None
    category: str = ""
    tags: List[str] = field(default_factory=list)
    rating: float = 0.0
    review_count: int = 0
    downloads: int = 0
    verified: bool = False
    icon: str = ""
    min_version: str = ""

    def __post_init__(self) -> None:
        if self.dependencies is None:
            self.dependencies = []


class PluginRegistry:
    """Manage plugins from multiple registries (local + remote)."""

    def __init__(
        self,
        plugins_dir: Path = DEFAULT_PLUGINS_DIR,
        registry_url: Optional[str] = None,
    ) -> None:
        self.plugins_dir = Path(plugins_dir)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self._ratings_file = self.plugins_dir / ".ratings.json"
        self._downloads_file = self.plugins_dir / ".downloads.json"
        self._local_ratings = self._load_local_ratings()
        self._local_downloads = self._load_local_downloads()
        self._registry_cache: Dict[str, List[Dict]] = {}
        # Isolate preferences: default location for real installs,
        # per-plugins_dir file for tests / custom dirs
        if self.plugins_dir.resolve() == DEFAULT_PLUGINS_DIR.resolve():
            self._preferences_file = PREFERENCES_FILE
        else:
            self._preferences_file = self.plugins_dir / ".preferences.json"
        # Backward compat: if registry_url given, use as sole remote source
        if registry_url is not None:
            normalized = self._normalize_registry_url(registry_url)
            self._registries = [{
                "name": "default",
                "source": normalized,
                "type": "remote",
                "enabled": True,
            }]
        else:
            self._registries = self._load_preferences()

    @property
    def registry_url(self) -> str:
        """Primary registry URL (backward-compat property for TUI/tests)."""
        for r in self._registries:
            if r.get("enabled", True) and r.get("type") == "remote":
                return r["source"]
        for r in self._registries:
            if r.get("enabled", True):
                return r["source"]
        return DEFAULT_REMOTE_REGISTRY

    @property
    def _cache_file(self) -> Path:
        """Primary cache file path (backward-compat for tests)."""
        for r in self._registries:
            if r.get("enabled", True):
                if r["type"] == "remote":
                    return self.plugins_dir / f".cache_{r['name']}.json"
        return self.plugins_dir / ".registry_cache.json"

    # ── Preferences (multi-registry) ────────────────────────────────

    def _load_preferences(self) -> List[Dict]:
        """Load registry list from preferences.json."""
        prefs_file = getattr(self, "_preferences_file", PREFERENCES_FILE)
        if prefs_file.exists():
            try:
                with open(prefs_file, "r", encoding="utf-8") as f:
                    prefs = json.load(f)
                return prefs.get("registries", [])
            except (json.JSONDecodeError, OSError):
                pass
        # Seed with the official remote registry
        default = [{
            "name": "official",
            "source": DEFAULT_REMOTE_REGISTRY,
            "type": "remote",
            "enabled": True,
        }]
        self._save_preferences(default)
        return default

    def _save_preferences(self, registries: Optional[List[Dict]] = None) -> None:
        """Write registry list to preferences.json."""
        if registries is None:
            registries = self._registries
        prefs = {"registries": registries}
        prefs_file = getattr(self, "_preferences_file", PREFERENCES_FILE)
        prefs_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(prefs_file, "w", encoding="utf-8") as f:
                json.dump(prefs, f, indent=2)
        except OSError as e:
            logger.warning(f"Failed to save preferences: {e}")

    def add_registry(self, name: str, source: str) -> Dict:
        """Add a registry. Auto-detects local vs remote. Returns the entry."""
        # Duplicate check
        for r in self._registries:
            if r["name"] == name:
                raise ValueError(f"Registry '{name}' already exists")

        # Auto-detect type
        expanded = os.path.expanduser(source)
        if os.path.isdir(expanded):
            reg_type = "local"
            source = expanded
            # Validate: must have plugins.json
            if not (Path(source) / "plugins.json").exists():
                raise ValueError(f"Local registry must contain plugins.json: {source}")
        else:
            reg_type = "remote"
            source = self._normalize_registry_url(source)

        entry = {"name": name, "source": source, "type": reg_type, "enabled": True}
        self._registries.append(entry)
        self._save_preferences()
        return entry

    def remove_registry(self, name: str) -> bool:
        """Remove a registry by name."""
        before = len(self._registries)
        self._registries = [r for r in self._registries if r["name"] != name]
        if len(self._registries) == before:
            logger.warning(f"Registry not found: {name}")
            return False
        self._save_preferences()
        return True

    def list_registries(self) -> List[Dict]:
        """Return all configured registries."""
        return list(self._registries)

    def get_registry(self, name: str) -> Optional[Dict]:
        """Get a single registry by name."""
        for r in self._registries:
            if r["name"] == name:
                return r
        return None

    # ── Registry detection helpers ──────────────────────────────────

    @staticmethod
    def _is_local_registry(source: str) -> bool:
        """True if source is a local directory path."""
        return os.path.isdir(os.path.expanduser(source))

    def _registry_plugins_file(self, registry: Dict) -> Path:
        """Return path to plugins.json for a local registry."""
        return Path(registry["source"]) / "plugins.json"

    # ── Existing helpers ────────────────────────────────────────────

    @staticmethod
    def _normalize_registry_url(url: str) -> str:
        """Normalize registry URL to raw GitHub content URL.

        Supports:
        - Raw URL: https://raw.githubusercontent.com/user/repo/main
        - GitHub URL: https://github.com/user/repo (converts to raw)
        - GitHub URL with branch: https://github.com/user/repo/tree/main
        - Plain URL: https://example.com/plugins (used as-is)
        """
        import re

        # Convert github.com URLs to raw.githubusercontent.com
        github_match = re.match(
            r"https?://github\.com/([^/]+)/([^/]+)(?:/(?:tree|blob)/([^/]+))?(?:/(.*))?",
            url,
        )
        if github_match:
            user = github_match.group(1)
            repo = github_match.group(2)
            branch = github_match.group(3) or "main"
            path = github_match.group(4) or ""
            if path:
                return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}"
            return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}"

        return url.rstrip("/")

    def search(
        self,
        query: str = "",
        plugin_type: str = "",
        category: str = "",
        tags: Optional[List[str]] = None,
        sort_by: str = "rating",
    ) -> List[Dict]:
        """Search plugins with filtering and sorting."""
        plugins = self._fetch_registry()
        results = plugins

        if query:
            query_lower = query.lower()
            results = [
                p for p in results
                if query_lower in p.get("name", "").lower()
                or query_lower in p.get("description", "").lower()
                or query_lower in p.get("author", "").lower()
                or any(query_lower in t.lower() for t in p.get("tags", []))
            ]

        if plugin_type:
            results = [p for p in results if p.get("type") == plugin_type]

        if category:
            results = [p for p in results if p.get("category") == category]

        if tags:
            tag_set = {t.lower() for t in tags}
            results = [
                p for p in results
                if tag_set & {t.lower() for t in p.get("tags", [])}
            ]

        # Merge local ratings/downloads
        for p in results:
            name = p.get("name", "")
            if name in self._local_ratings:
                p["rating"] = self._local_ratings[name].get("rating", p.get("rating", 0))
                p["review_count"] = self._local_ratings[name].get("review_count", p.get("review_count", 0))
            if name in self._local_downloads:
                p["downloads"] = p.get("downloads", 0) + self._local_downloads[name]

        # Sort — name is the honest default when registry has no metrics
        if sort_by == "rating":
            results.sort(
                key=lambda p: (
                    -float(p["rating"]) if p.get("rating") is not None else 0,
                    -p.get("review_count", 0),
                    p.get("name", ""),
                )
            )
        elif sort_by == "downloads":
            results.sort(
                key=lambda p: (
                    -int(p["downloads"]) if p.get("downloads") is not None else 0,
                    p.get("name", ""),
                )
            )
        elif sort_by == "name":
            results.sort(key=lambda p: p.get("name", ""))
        elif sort_by == "recent":
            results.reverse()
        elif sort_by == "trending":
            import time
            week_ago = time.time() - 7 * 86400
            for p in results:
                recent = p.get("recent_downloads", {}) or []
                trending_score = 0
                if isinstance(recent, list):
                    for entry in recent:
                        if entry.get("date", 0) > week_ago:
                            trending_score += entry.get("count", 0)
                p["_trending"] = trending_score
            results.sort(key=lambda p: (-p.get("_trending", 0), p.get("name", "")))
        else:
            results.sort(key=lambda p: p.get("name", ""))

        return results

    def check_compatibility(self, name: str, tokenade_version: str = "6.0.0") -> Dict:
        """Check if a plugin is compatible with the given Tokenade version."""
        plugins = self._fetch_registry()
        plugin = None
        for p in plugins:
            if p.get("name") == name:
                plugin = p
                break
        if not plugin:
            return {"compatible": False, "reason": "Plugin not found in registry"}

        min_ver = plugin.get("min_version", "")
        max_ver = plugin.get("max_version", "")
        if min_ver and _version_lt(tokenade_version, min_ver):
            return {"compatible": False, "reason": f"Requires Tokenade >= {min_ver}"}
        if max_ver and _version_lt(max_ver, tokenade_version):
            return {"compatible": False, "reason": f"Requires Tokenade <= {max_ver}"}
        return {"compatible": True, "reason": ""}

    def get_categories(self) -> List[Dict]:
        """List all categories with plugin counts."""
        plugins = self._fetch_registry()
        category_counts = {}
        for p in plugins:
            cat = p.get("category", "other")
            category_counts[cat] = category_counts.get(cat, 0) + 1

        result = []
        for cat in CATEGORIES:
            result.append({
                **cat,
                "plugin_count": category_counts.get(cat["name"], 0),
            })

        # Add uncategorized if any
        if "other" in category_counts:
            result.append({
                "name": "other",
                "description": "Uncategorized plugins",
                "icon": "📦",
                "plugin_count": category_counts["other"],
            })

        return result

    def get_plugin_details(self, name: str) -> Optional[Dict]:
        """Get full metadata for a specific plugin."""
        plugins = self._fetch_registry()
        for p in plugins:
            if p.get("name") == name:
                # Merge local data
                if name in self._local_ratings:
                    p["rating"] = self._local_ratings[name].get("rating", p.get("rating", 0))
                    p["review_count"] = self._local_ratings[name].get("review_count", p.get("review_count", 0))
                    p["user_reviews"] = self._local_ratings[name].get("reviews", [])
                if name in self._local_downloads:
                    p["downloads"] = p.get("downloads", 0) + self._local_downloads[name]
                return p
        return None

    def get_popular(self, limit: int = 10) -> List[Dict]:
        """Get top plugins by download count."""
        return self.search(sort_by="downloads")[:limit]

    def get_recent(self, limit: int = 10) -> List[Dict]:
        """Get newest plugins."""
        return self.search(sort_by="recent")[:limit]

    def rate_plugin(self, name: str, rating: float, review: str = "") -> bool:
        """Submit a rating for a plugin (stored locally)."""
        if not 1.0 <= rating <= 5.0:
            logger.error("Rating must be between 1.0 and 5.0")
            return False

        if name not in self._local_ratings:
            self._local_ratings[name] = {
                "rating": rating,
                "review_count": 1,
                "reviews": [],
            }
            if review:
                self._local_ratings[name]["reviews"].append({
                    "rating": rating,
                    "review": review,
                    "timestamp": time.time(),
                })
        else:
            entry = self._local_ratings[name]
            old_total = entry["rating"] * entry["review_count"]
            entry["review_count"] += 1
            entry["rating"] = (old_total + rating) / entry["review_count"]
            if review:
                entry["reviews"].append({
                    "rating": rating,
                    "review": review,
                    "timestamp": time.time(),
                })

        self._save_local_ratings()
        logger.info(f"Rated {name}: {rating}/5")
        return True

    def get_ratings(self, name: str) -> Dict:
        """Get ratings for a plugin."""
        if name in self._local_ratings:
            return self._local_ratings[name]
        return {"rating": 0.0, "review_count": 0, "reviews": []}

    def increment_downloads(self, name: str) -> None:
        """Track a download (local counter)."""
        self._local_downloads[name] = self._local_downloads.get(name, 0) + 1
        self._save_local_downloads()

    def find_plugin(
        self, plugin_name: str, registry_name: Optional[str] = None
    ) -> Tuple[Optional[Dict], List[Dict]]:
        """Find a plugin across registries.

        Returns (plugin_meta, conflicts) where conflicts is a list of
        registries that also have this plugin (only if >1 match).
        """
        matches: List[Dict] = []
        for reg in self._registries:
            if not reg.get("enabled", True):
                continue
            if registry_name and reg["name"] != registry_name:
                continue
            try:
                plugins = self._fetch_single_registry(reg)
            except Exception:
                continue
            for p in plugins:
                if p.get("name") == plugin_name:
                    p = dict(p)
                    p["_registry"] = reg["name"]
                    matches.append(p)

        if not matches:
            return None, []
        if len(matches) == 1:
            return matches[0], []
        # Conflict: return first match + list of all
        return matches[0], matches

    def install(
        self,
        plugin_name: str,
        registry_name: Optional[str] = None,
        _install_chain: Optional[List[str]] = None,
    ) -> bool:
        """Install a plugin. Auto-installs missing dependencies.

        Args:
            plugin_name: Name of the plugin to install
            registry_name: Optional registry to install from (for conflicts)
            _install_chain: Internal chain for circular dependency detection
        """
        if _install_chain is None:
            _install_chain = []

        if plugin_name in _install_chain:
            logger.error(
                f"Circular dependency detected: "
                f"{' -> '.join(_install_chain)} -> {plugin_name}"
            )
            return False

        if registry_name:
            plugin_meta, conflicts = self.find_plugin(plugin_name, registry_name)
        else:
            enabled = [r for r in self._registries if r.get("enabled", True)]
            if len(enabled) > 1:
                plugin_meta, conflicts = self.find_plugin(plugin_name)
                if conflicts:
                    sources = [c.get("_registry", "?") for c in conflicts]
                    logger.error(
                        f"Plugin '{plugin_name}' found in multiple registries: "
                        f"{', '.join(sources)}. Use --registry <name> to choose."
                    )
                    return False
            else:
                # Single registry: use merged fetch (mockable in tests)
                plugin_meta = None
                conflicts = []
                for p in self._fetch_registry():
                    if p.get("name") == plugin_name:
                        plugin_meta = p
                        break

        if plugin_meta is None:
            logger.error(f"Plugin not found in registry: {plugin_name}")
            return False

        plugin_dir = self.plugins_dir / plugin_name
        if plugin_dir.exists():
            logger.info(f"Plugin already installed: {plugin_name}")
            return True

        _install_chain.append(plugin_name)

        for dep in plugin_meta.get("dependencies", []):
            dep_dir = self.plugins_dir / dep
            if not dep_dir.exists():
                logger.info(f"Installing dependency: {dep}")
                if not self.install(dep, registry_name, _install_chain):
                    logger.error(f"Failed to install dependency: {dep}")
                    return False

        reg = self.get_registry(plugin_meta.get("_registry", ""))
        success = self._download_plugin(plugin_meta, reg)
        if success:
            self.increment_downloads(plugin_name)
            logger.info(f"Plugin installed: {plugin_name}")
        return success

    def install_from_git(
        self,
        repo_url: str,
        branch: Optional[str] = None,
        subdirectory: Optional[str] = None,
    ) -> bool:
        """
        Clone or download a remote Git / GitHub repository and install discovered plugin(s).
        Supports:
        - GitHub repo URL (e.g. 'https://github.com/user/my-tokenade-plugin')
        - Shorthand ('user/repo' or 'github:user/repo')
        - Direct git clone URL (.git)
        """
        import re
        import subprocess
        import tempfile

        # Normalize GitHub shorthands
        if repo_url.startswith("github:"):
            repo_url = f"https://github.com/{repo_url[7:]}"
        elif re.match(r"^[\w\-]+/[\w\-]+$", repo_url):
            repo_url = f"https://github.com/{repo_url}"

        logger.info(f"Installing plugin from git source: {repo_url}")

        with tempfile.TemporaryDirectory(prefix="tokenade-git-plugin-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            cmd = ["git", "clone", "--depth", "1"]
            if branch:
                cmd.extend(["-b", branch])
            cmd.extend([repo_url, str(tmp_path)])

            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
            except Exception as e:
                logger.error(f"Failed to clone git repository {repo_url}: {e}")
                return False

            source_root = tmp_path
            if subdirectory:
                source_root = tmp_path / subdirectory
                if not source_root.is_dir():
                    logger.error(f"Specified subdirectory '{subdirectory}' not found in repo")
                    return False

            # Check if source_root is a single plugin or a collection of plugins
            if (source_root / "plugin.json").is_file():
                return self._install_plugin_dir(source_root)

            # Look for subdirectories containing plugin.json
            installed_any = False
            for sub_dir in sorted(source_root.iterdir()):
                if sub_dir.is_dir() and (sub_dir / "plugin.json").is_file():
                    if self._install_plugin_dir(sub_dir):
                        installed_any = True

            if not installed_any:
                logger.error(f"No valid plugins found in {repo_url}")
                return False

            return True

    def _install_plugin_dir(self, src_dir: Path) -> bool:
        """Helper to install a verified local plugin directory into ~/.tokenade/plugins/."""
        manifest_path = src_dir / "plugin.json"
        if not manifest_path.is_file() or not (src_dir / "plugin.py").is_file():
            logger.error(f"Missing plugin.json or plugin.py in {src_dir}")
            return False

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            plugin_name = meta.get("name", src_dir.name)
        except Exception as e:
            logger.error(f"Failed to parse plugin manifest in {src_dir}: {e}")
            return False

        target_dir = self.plugins_dir / plugin_name
        target_dir.mkdir(parents=True, exist_ok=True)

        skip_names = {"__pycache__", ".pytest_cache", ".git", ".mypy_cache", "node_modules"}
        for path in src_dir.rglob("*"):
            if any(part in skip_names or part.endswith(".pyc") for part in path.parts):
                continue
            rel = path.relative_to(src_dir)
            dst = target_dir / rel
            if path.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
            elif path.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dst)

        logger.info(f"Plugin installed from git: {plugin_name}")
        return True

    def uninstall(self, plugin_name: str) -> bool:
        """Remove an installed plugin."""
        plugin_dir = self.plugins_dir / plugin_name
        if not plugin_dir.exists():
            logger.warning(f"Plugin not installed: {plugin_name}")
            return False

        installed = self.list_installed()
        for p in installed:
            if plugin_name in (p.dependencies or []) and p.name != plugin_name:
                logger.error(f"Cannot uninstall {plugin_name}: plugin {p.name} depends on it")
                return False

        import shutil
        shutil.rmtree(plugin_dir)
        logger.info(f"Plugin uninstalled: {plugin_name}")
        return True

    def list_installed(self) -> List[Plugin]:
        """List locally installed plugins."""
        plugins = []
        for plugin_dir in sorted(self.plugins_dir.iterdir()):
            if not plugin_dir.is_dir() or plugin_dir.name.startswith("."):
                continue

            manifest_path = plugin_dir / "plugin.json"
            if not manifest_path.exists():
                continue

            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                plugins.append(Plugin(
                    name=meta.get("name", plugin_dir.name),
                    version=meta.get("version", "0.0.0"),
                    description=meta.get("description", ""),
                    author=meta.get("author", ""),
                    url=meta.get("url", ""),
                    type=meta.get("type", "handler"),
                    entry_point=meta.get("entry_point", ""),
                    dependencies=meta.get("dependencies", []),
                    category=meta.get("category", ""),
                    tags=meta.get("tags", []),
                ))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load plugin manifest {manifest_path}: {e}")

        return plugins

    def get_outdated(self) -> List[Dict]:
        """List installed plugins with available updates (semver comparison)."""
        installed = self.list_installed()
        registry_plugins = self._fetch_registry()
        registry_map = {p["name"]: p for p in registry_plugins}

        outdated = []
        for plugin in installed:
            remote = registry_map.get(plugin.name)
            if not remote:
                continue
            remote_ver = remote.get("version", "")
            if remote_ver and _version_lt(plugin.version, remote_ver):
                outdated.append({
                    "name": plugin.name,
                    "installed_version": plugin.version,
                    "available_version": remote_ver,
                    "description": remote.get("description", ""),
                    "registry": remote.get("_registry", ""),
                })
        return outdated

    def update(
        self,
        plugin_name: Optional[str] = None,
        force: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, List[str]]:
        """Update one or all installed plugins.

        Args:
            plugin_name: Update only this plugin (None = all outdated)
            force: Re-download even if already up-to-date
            dry_run: Report what would be updated without changing files

        Returns:
            {"updated": [...], "skipped": [...], "failed": [...]}
        """
        installed = self.list_installed()
        registry_plugins = self._fetch_registry()
        registry_map = {p["name"]: p for p in registry_plugins}

        result: Dict[str, List[str]] = {"updated": [], "skipped": [], "failed": []}

        for plugin in installed:
            if plugin_name and plugin.name != plugin_name:
                continue

            remote = registry_map.get(plugin.name)
            if not remote:
                result["skipped"].append(plugin.name)
                continue

            remote_ver = remote.get("version", "")
            is_outdated = remote_ver and _version_lt(plugin.version, remote_ver)

            if not is_outdated and not force:
                result["skipped"].append(plugin.name)
                continue

            if dry_run:
                result["updated"].append(
                    f"{plugin.name} {plugin.version} -> {remote_ver}"
                )
                continue

            # Backup user config
            plugin_dir = self.plugins_dir / plugin.name
            config_backup = None
            config_path = plugin_dir / "config.json"
            if config_path.exists():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_backup = f.read()
                except OSError:
                    pass

            # Re-download
            shutil.rmtree(plugin_dir)
            reg = self.get_registry(remote.get("_registry", ""))
            if self._download_plugin(remote, reg):
                # Restore config
                if config_backup is not None:
                    try:
                        with open(plugin_dir / "config.json", "w", encoding="utf-8") as f:
                            f.write(config_backup)
                    except OSError as e:
                        logger.warning(f"Failed to restore config for {plugin.name}: {e}")
                result["updated"].append(
                    f"{plugin.name} {plugin.version} -> {remote_ver}"
                )
                logger.info(
                    f"Updated {plugin.name}: {plugin.version} -> {remote_ver}"
                )
            else:
                result["failed"].append(plugin.name)
                logger.error(f"Failed to update {plugin.name}")

        return result

    def _fetch_registry(self) -> List[Dict]:
        """Fetch and merge plugins from all enabled registries.

        Local registries are read directly from disk (no TTL).
        Remote registries use a 1-hour disk cache per registry.
        Deduplicates by name — first registry in list wins.
        """
        seen_names: set = set()
        merged: List[Dict] = []

        for reg in self._registries:
            if not reg.get("enabled", True):
                continue
            try:
                plugins = self._fetch_single_registry(reg)
            except Exception as e:
                logger.warning(f"Failed to fetch registry '{reg['name']}': {e}")
                continue
            for p in plugins:
                name = p.get("name", "")
                if name and name not in seen_names:
                    p["_registry"] = reg["name"]
                    seen_names.add(name)
                    merged.append(p)

        return merged

    def _fetch_single_registry(self, registry: Dict) -> List[Dict]:
        """Fetch plugins from a single registry (local or remote)."""
        if registry["type"] == "local":
            return self._fetch_local_registry(registry)
        return self._fetch_remote_registry(registry)

    def _fetch_local_registry(self, registry: Dict) -> List[Dict]:
        """Read plugins.json directly from a local directory."""
        plugins_file = Path(registry["source"]) / "plugins.json"
        if not plugins_file.exists():
            logger.warning(f"Local registry missing plugins.json: {plugins_file}")
            return []
        try:
            with open(plugins_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            plugins = data if isinstance(data, list) else data.get("plugins", [])
            return plugins
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read local registry {plugins_file}: {e}")
            return []

    def _fetch_remote_registry(self, registry: Dict) -> List[Dict]:
        """Fetch plugins.json from a remote URL with 1-hour cache."""
        cache_file = self.plugins_dir / f".cache_{registry['name']}.json"

        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                if time.time() - cache.get("timestamp", 0) < 3600:
                    return cache.get("plugins", [])
            except (json.JSONDecodeError, OSError):
                pass

        url = f"{registry['source']}/plugins.json"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Tokenade/2.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            plugins = data if isinstance(data, list) else data.get("plugins", [])

            cache_data = {"timestamp": time.time(), "plugins": plugins}
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)

            return plugins
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to fetch remote registry '{registry['name']}': {e}")
            return []

    def _download_plugin(self, plugin: Dict, registry: Optional[Dict] = None) -> bool:
        """Download plugin files from a registry.

        For local registries: copies files from the local directory.
        For remote registries: downloads via HTTP.
        Falls back to the first enabled registry if none specified.
        """
        name = plugin.get("name", "")
        if not name:
            return False

        if registry is None:
            reg_name = plugin.get("_registry", "")
            registry = self.get_registry(reg_name) or self._registries[0] if self._registries else None

        plugin_dir = self.plugins_dir / name
        plugin_dir.mkdir(parents=True, exist_ok=True)

        core_files = ["plugin.json", "plugin.py", "site_config.json"]
        extra_files = [f for f in plugin.get("files", []) if f not in core_files]
        all_files = core_files + extra_files

        if registry and registry["type"] == "local":
            return self._copy_plugin_local(name, all_files, registry, plugin_dir)
        return self._download_plugin_remote(name, all_files, plugin_dir)

    def _copy_plugin_local(
        self, name: str, files: List[str], registry: Dict, target_dir: Path
    ) -> bool:
        """Copy plugin files from a local registry directory.

        Copies the full plugin tree (except caches) so nested assets like
        ``sites/*.json`` are included. Explicit ``files`` remain a fallback
        for partial layouts.
        """
        src_dir = Path(registry["source"]) / "plugins" / name
        if not src_dir.exists():
            logger.error(f"Plugin source not found in local registry: {src_dir}")
            return False

        if not (src_dir / "plugin.json").is_file() or not (src_dir / "plugin.py").is_file():
            logger.error(f"Required plugin.json/plugin.py missing in {src_dir}")
            return False

        skip_names = {"__pycache__", ".pytest_cache", ".git", ".mypy_cache", "node_modules"}
        for path in src_dir.rglob("*"):
            if any(part in skip_names or part.endswith(".pyc") for part in path.parts):
                continue
            rel = path.relative_to(src_dir)
            dst = target_dir / rel
            if path.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
            elif path.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dst)

        # Ensure any explicitly listed files were considered (compat)
        for filename in files:
            src = src_dir / filename
            if src.is_file():
                dst = target_dir / filename
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        return True

    def _download_plugin_remote(self, name: str, files: List[str], target_dir: Path) -> bool:
        """Download plugin files from a remote registry URL."""
        # Find the remote registry source
        reg_source = DEFAULT_REMOTE_REGISTRY
        for reg in self._registries:
            if reg["type"] == "remote" and reg.get("enabled", True):
                reg_source = reg["source"]
                break

        base_url = f"{reg_source}/plugins/{name}"
        for filename in files:
            file_url = f"{base_url}/{filename}"
            target_path = target_dir / filename
            try:
                req = urllib.request.Request(file_url, headers={"User-Agent": "Tokenade/2.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    content = resp.read()
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with open(target_path, "wb") as f:
                    f.write(content)
            except (urllib.error.URLError, OSError) as e:
                if filename in ("plugin.json", "plugin.py"):
                    logger.error(f"Failed to download {file_url}: {e}")
                    return False
                logger.debug(f"Skipped optional file {filename}: {e}")
        return True

    def discover_from_url(self, url: str) -> List[Dict]:
        """Discover plugins from any URL pointing to a plugin directory or registry.

        Supports:
        - Full registry URL (has plugins.json at root)
        - GitHub directory URL (e.g., https://github.com/user/repo/tree/main/plugins)
        - Raw GitHub directory URL (e.g., https://raw.githubusercontent.com/user/repo/main/plugins)

        Returns list of plugin metadata dicts.
        """
        normalized = self._normalize_registry_url(url)

        # Try fetching plugins.json first
        try:
            plugins_url = f"{normalized}/plugins.json"
            req = urllib.request.Request(plugins_url, headers={"User-Agent": "Tokenade/2.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            plugins = data if isinstance(data, list) else data.get("plugins", [])
            if plugins:
                logger.info(f"Discovered {len(plugins)} plugins from {url}")
                return plugins
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            pass

        # Try marketplace.json
        try:
            market_url = f"{normalized}/marketplace.json"
            req = urllib.request.Request(market_url, headers={"User-Agent": "Tokenade/2.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data and "plugins" in data:
                logger.info(f"Discovered {len(data['plugins'])} plugins from marketplace")
                return data["plugins"]
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            pass

        # Try scanning for plugin.json files in subdirectories
        # This handles raw directory listings
        try:
            # Fetch directory listing (GitHub API)
            import re
            api_match = re.match(
                r"https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.*)",
                normalized,
            )
            if api_match:
                user, repo, branch, path = api_match.groups()
                api_url = f"https://api.github.com/repos/{user}/{repo}/contents/{path}?ref={branch}"
                req = urllib.request.Request(api_url, headers={"User-Agent": "Tokenade/2.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    items = json.loads(resp.read().decode("utf-8"))

                plugins = []
                for item in items:
                    if item.get("type") == "dir":
                        # Try to fetch plugin.json from this directory
                        try:
                            pj_url = item.get("download_url", "").replace(
                                item["name"], f"{item['name']}/plugin.json"
                            )
                            if not pj_url:
                                pj_url = f"{normalized}/{item['name']}/plugin.json"
                            req2 = urllib.request.Request(pj_url, headers={"User-Agent": "Tokenade/2.0"})
                            with urllib.request.urlopen(req2, timeout=10) as resp2:
                                meta = json.loads(resp2.read().decode("utf-8"))
                            meta["_path"] = item["name"]
                            plugins.append(meta)
                        except Exception:
                            continue

                if plugins:
                    logger.info(f"Discovered {len(plugins)} plugins from directory scan")
                    return plugins
        except Exception as e:
            logger.debug(f"Directory scan failed: {e}")

        return []

    def _load_local_ratings(self) -> Dict:
        """Load local ratings from disk."""
        if self._ratings_file.exists():
            try:
                with open(self._ratings_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_local_ratings(self) -> None:
        """Save local ratings to disk."""
        try:
            with open(self._ratings_file, "w") as f:
                json.dump(self._local_ratings, f, indent=2)
        except OSError as e:
            logger.warning(f"Failed to save ratings: {e}")

    def _load_local_downloads(self) -> Dict:
        """Load local download counts from disk."""
        if self._downloads_file.exists():
            try:
                with open(self._downloads_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_local_downloads(self) -> None:
        """Save local download counts to disk."""
        try:
            with open(self._downloads_file, "w") as f:
                json.dump(self._local_downloads, f, indent=2)
        except OSError as e:
            logger.warning(f"Failed to save download counts: {e}")
