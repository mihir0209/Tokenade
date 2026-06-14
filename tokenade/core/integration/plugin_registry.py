"""
Plugin registry using GitHub raw content.

Plugins are listed in a JSON file hosted in a public GitHub repo.
No domain or hosting costs required.
"""

import json
import logging
import urllib.request
import urllib.error
from typing import Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Default registry URL (GitHub raw content - free, no domain needed)
DEFAULT_REGISTRY_URL = "https://raw.githubusercontent.com/mihir0209/tokenade-plugins/main"
DEFAULT_PLUGINS_DIR = Path.home() / ".tokenade" / "plugins"


@dataclass
class Plugin:
    """Plugin metadata."""

    name: str
    version: str
    description: str
    author: str
    url: str
    type: str  # 'handler', 'export_format', 'validator'
    entry_point: str
    dependencies: List[str] = None

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

    def search(self, query: str = "", plugin_type: str = "") -> List[Dict]:
        """Search plugins in registry.

        Fetches plugins.json from GitHub, caches locally for 1 hour.
        """
        plugins = self._fetch_registry()

        results = plugins

        if query:
            query_lower = query.lower()
            results = [
                p for p in results
                if query_lower in p.get("name", "").lower()
                or query_lower in p.get("description", "").lower()
                or query_lower in p.get("author", "").lower()
            ]

        if plugin_type:
            results = [p for p in results if p.get("type") == plugin_type]

        return results

    def install(self, plugin_name: str) -> bool:
        """Install a plugin from the registry.

        Downloads the plugin files to ~/.tokenade/plugins/{name}/
        """
        plugins = self._fetch_registry()
        plugin_meta = None
        for p in plugins:
            if p.get("name") == plugin_name:
                plugin_meta = p
                break

        if plugin_meta is None:
            logger.error(f"Plugin not found in registry: {plugin_name}")
            return False

        # Check if already installed
        plugin_dir = self.plugins_dir / plugin_name
        if plugin_dir.exists():
            logger.info(f"Plugin already installed: {plugin_name}")
            return True

        # Check dependencies
        for dep in plugin_meta.get("dependencies", []):
            dep_dir = self.plugins_dir / dep
            if not dep_dir.exists():
                logger.error(f"Missing dependency: {dep}. Install it first.")
                return False

        success = self._download_plugin(plugin_meta)
        if success:
            logger.info(f"Plugin installed: {plugin_name}")
        return success

    def uninstall(self, plugin_name: str) -> bool:
        """Remove an installed plugin."""
        plugin_dir = self.plugins_dir / plugin_name
        if not plugin_dir.exists():
            logger.warning(f"Plugin not installed: {plugin_name}")
            return False

        # Check if other plugins depend on this one
        installed = self.list_installed()
        for p in installed:
            if plugin_name in (p.dependencies or []) and p.name != plugin_name:
                logger.error(
                    f"Cannot uninstall {plugin_name}: plugin {p.name} depends on it"
                )
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
                ))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load plugin manifest {manifest_path}: {e}")

        return plugins

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
                    logger.info(
                        f"Updated {plugin.name}: {plugin.version} -> {remote['version']}"
                    )

        return updated

    def _fetch_registry(self) -> List[Dict]:
        """Fetch plugin list from GitHub."""
        # Check cache freshness (1 hour TTL)
        if self._cache_file.exists():
            try:
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                import time

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

            # Update cache
            import time

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

        # Always download manifest
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
