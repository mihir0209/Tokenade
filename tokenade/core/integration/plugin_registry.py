"""
Plugin registry using GitHub raw content.

Plugins are listed in a JSON file hosted in a public GitHub repo.
No domain or hosting costs required.

Enhanced with categories, tags, ratings, download tracking, and verification.
"""

import json
import logging
import time
import urllib.request
import urllib.error
from typing import Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

DEFAULT_REGISTRY_URL = "https://raw.githubusercontent.com/mihir0209/tokenade-plugins/main"
DEFAULT_PLUGINS_DIR = Path.home() / ".tokenade" / "plugins"

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

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []


class PluginRegistry:
    """Manage plugins via GitHub-hosted registry."""

    def __init__(
        self,
        registry_url: str = DEFAULT_REGISTRY_URL,
        plugins_dir: Path = DEFAULT_PLUGINS_DIR,
    ):
        self.registry_url = registry_url
        self.plugins_dir = plugins_dir
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file = self.plugins_dir / ".registry_cache.json"
        self._ratings_file = self.plugins_dir / ".ratings.json"
        self._downloads_file = self.plugins_dir / ".downloads.json"
        self._local_ratings = self._load_local_ratings()
        self._local_downloads = self._load_local_downloads()

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

        # Sort
        if sort_by == "rating":
            results.sort(key=lambda p: (-p.get("rating", 0), -p.get("review_count", 0)))
        elif sort_by == "downloads":
            results.sort(key=lambda p: -p.get("downloads", 0))
        elif sort_by == "name":
            results.sort(key=lambda p: p.get("name", ""))
        elif sort_by == "recent":
            results.reverse()

        return results

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

    def install(self, plugin_name: str) -> bool:
        """Install a plugin from the registry."""
        plugins = self._fetch_registry()
        plugin_meta = None
        for p in plugins:
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

        for dep in plugin_meta.get("dependencies", []):
            dep_dir = self.plugins_dir / dep
            if not dep_dir.exists():
                logger.error(f"Missing dependency: {dep}. Install it first.")
                return False

        success = self._download_plugin(plugin_meta)
        if success:
            self.increment_downloads(plugin_name)
            logger.info(f"Plugin installed: {plugin_name}")
        return success

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
        """List installed plugins with available updates."""
        installed = self.list_installed()
        registry_plugins = self._fetch_registry()
        registry_map = {p["name"]: p for p in registry_plugins}

        outdated = []
        for plugin in installed:
            remote = registry_map.get(plugin.name)
            if remote and remote.get("version", "") != plugin.version:
                outdated.append({
                    "name": plugin.name,
                    "installed_version": plugin.version,
                    "available_version": remote.get("version", ""),
                    "description": remote.get("description", ""),
                })

        return outdated

    def update(self, plugin_name: Optional[str] = None) -> int:
        """Update one or all installed plugins. Returns count updated."""
        installed = self.list_installed()
        registry_plugins = self._fetch_registry()
        registry_map = {p["name"]: p for p in registry_plugins}

        updated = 0
        for plugin in installed:
            if plugin_name and plugin.name != plugin_name:
                continue

            remote = registry_map.get(plugin.name)
            if not remote:
                continue

            if remote.get("version", "") != plugin.version:
                plugin_dir = self.plugins_dir / plugin.name
                import shutil
                shutil.rmtree(plugin_dir)
                if self._download_plugin(remote):
                    updated += 1
                    logger.info(f"Updated {plugin.name}: {plugin.version} -> {remote['version']}")

        return updated

    def _fetch_registry(self) -> List[Dict]:
        """Fetch plugin list from GitHub."""
        if self._cache_file.exists():
            try:
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                if time.time() - cache.get("timestamp", 0) < 3600:
                    return cache.get("plugins", [])
            except (json.JSONDecodeError, OSError):
                pass

        url = f"{self.registry_url}/plugins.json"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Tokenade/2.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            plugins = data if isinstance(data, list) else data.get("plugins", [])

            cache_data = {"timestamp": time.time(), "plugins": plugins}
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)

            return plugins
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to fetch plugin registry: {e}")
            return []

    def _download_plugin(self, plugin: Dict) -> bool:
        """Download plugin files from GitHub."""
        name = plugin.get("name", "")
        files = plugin.get("files", [])
        base_url = f"{self.registry_url}/plugins/{name}"

        plugin_dir = self.plugins_dir / name
        plugin_dir.mkdir(parents=True, exist_ok=True)

        all_files = ["plugin.json"] + [f for f in files if f != "plugin.json"]

        for filename in all_files:
            file_url = f"{base_url}/{filename}"
            target_path = plugin_dir / filename

            try:
                req = urllib.request.Request(file_url, headers={"User-Agent": "Tokenade/2.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    content = resp.read()
                with open(target_path, "wb") as f:
                    f.write(content)
            except (urllib.error.URLError, OSError) as e:
                logger.error(f"Failed to download {file_url}: {e}")
                return False

        return True

    def _load_local_ratings(self) -> Dict:
        """Load local ratings from disk."""
        if self._ratings_file.exists():
            try:
                with open(self._ratings_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_local_ratings(self):
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

    def _save_local_downloads(self):
        """Save local download counts to disk."""
        try:
            with open(self._downloads_file, "w") as f:
                json.dump(self._local_downloads, f, indent=2)
        except OSError as e:
            logger.warning(f"Failed to save download counts: {e}")
