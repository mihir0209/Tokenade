"""
Session Sync Daemon - Monitor browser cookies and auto-export on change.

Features:
- File mtime-based change detection (lightweight, no polling)
- Multi-browser support (Firefox, Chrome, Brave, Edge)
- Multi-site monitoring (export multiple sites simultaneously)
- Configurable output directories (local, network share, SSH)
- Sync history with timestamps
- CLI integration: tokenade sync start/stop/status
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Callable

logger = logging.getLogger(__name__)


@dataclass
class SyncTarget:
    """A site to monitor and sync."""
    name: str
    domains: List[str]
    browser: str = "firefox"
    browser_profile: Optional[str] = None
    output_dir: str = "~/.tokenade/synced"
    output_filename: Optional[str] = None  # defaults to {name}.tokenade


@dataclass
class SyncStatus:
    """Status of a sync target."""
    target: str
    last_sync: Optional[str] = None
    last_cookie_count: int = 0
    last_file_hash: Optional[str] = None
    last_db_mtime: float = 0.0
    sync_count: int = 0
    error: Optional[str] = None


class SessionSyncDaemon:
    """
    Monitors browser cookie databases and auto-exports sessions on change.

    Uses file mtime (os.stat) to detect database changes without reading
    the database on every check. Only re-extracts when mtime changes.

    Usage:
        daemon = SessionSyncDaemon()
        daemon.add_target(SyncTarget(
            name="gmail",
            domains=["google.com", "accounts.google.com", "mail.google.com"],
            browser="firefox",
        ))
        daemon.start(interval=60)  # Check every 60 seconds
    """

    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = Path(storage_dir or "~/.tokenade/sync").expanduser()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._targets: List[SyncTarget] = []
        self._statuses: Dict[str, SyncStatus] = {}
        self._running = False
        self._on_sync_callbacks: List[Callable] = []

    def add_target(self, target: SyncTarget):
        """Add a site to monitor."""
        self._targets.append(target)
        if target.name not in self._statuses:
            self._statuses[target.name] = SyncStatus(target=target.name)
        logger.info(f"Sync target added: {target.name} ({target.browser}, {len(target.domains)} domains)")

    def remove_target(self, name: str):
        """Remove a sync target."""
        self._targets = [t for t in self._targets if t.name != name]
        self._statuses.pop(name, None)

    def on_sync(self, callback: Callable):
        """Register a callback for sync events."""
        self._on_sync_callbacks.append(callback)

    def _get_db_path(self, target: SyncTarget) -> Optional[Path]:
        """Get the cookie database path for a browser."""
        from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery
        discovery = BrowserProfileDiscovery()
        profiles = discovery.discover_all()

        all_profiles = []
        for browser_profiles in profiles.values():
            all_profiles.extend(browser_profiles)

        matching = [p for p in all_profiles if p.browser == target.browser]
        if target.browser_profile:
            matching = [p for p in matching if p.name == target.browser_profile]

        if not matching:
            logger.warning(f"No profile found for {target.browser}")
            return None

        profile_path = Path(matching[0].path)

        # Find cookie database
        if target.browser == "firefox":
            return profile_path / "cookies.sqlite"
        elif target.browser in ("chrome", "chromium", "edge", "brave"):
            return profile_path / "Default" / "Cookies"
        else:
            return profile_path / "cookies.sqlite"

    def _get_db_mtime(self, target: SyncTarget) -> float:
        """Get the modification time of the cookie database."""
        db_path = self._get_db_path(target)
        if db_path and db_path.exists():
            return db_path.stat().st_mtime
        return 0.0

    def _extract_and_save(self, target: SyncTarget) -> Optional[int]:
        """Extract cookies and save to output file. Returns cookie count or None on error."""
        from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery
        from tokenade.core.importer.cookie_extractor import CookieExtractor
        from tokenade.core.importer.session_packager import SessionPackager

        try:
            # Discover profile
            discovery = BrowserProfileDiscovery()
            profiles = discovery.discover_all()

            all_profiles = []
            for browser_profiles in profiles.values():
                all_profiles.extend(browser_profiles)

            matching = [p for p in all_profiles if p.browser == target.browser]
            if target.browser_profile:
                matching = [p for p in matching if p.name == target.browser_profile]

            if not matching:
                return None

            browser_path = str(matching[0].path)

            # Extract cookies
            extractor = CookieExtractor(browser_path, browser=target.browser)
            all_cookies = extractor.extract(site_filter=None)

            # Filter by domains
            cookies = []
            for cookie in all_cookies:
                domain = cookie.get("domain", "")
                for d in target.domains:
                    if d.startswith("."):
                        if domain.endswith(d) or domain == d[1:]:
                            cookies.append(cookie)
                            break
                    else:
                        if domain == d or domain.endswith("." + d):
                            cookies.append(cookie)
                            break

            if not cookies:
                logger.warning(f"No cookies extracted for {target.name}")
                return 0

            # Package and save
            packager = SessionPackager()
            session = packager.package(
                cookies=cookies,
                browser=target.browser,
                profile=target.browser_profile or matching[0].name,
            )

            # Add sync metadata
            session["metadata"]["sync_target"] = target.name
            session["metadata"]["synced_at"] = datetime.now().isoformat()

            # Determine output path
            output_dir = Path(target.output_dir).expanduser()
            output_dir.mkdir(parents=True, exist_ok=True)

            filename = target.output_filename or f"{target.name}.tokenade"
            output_path = output_dir / filename

            packager.save(session, str(output_path))

            logger.info(f"Synced {target.name}: {len(cookies)} cookies -> {output_path}")
            return len(cookies)

        except Exception as e:
            logger.error(f"Sync failed for {target.name}: {e}")
            return None

    def check_once(self) -> Dict[str, bool]:
        """Check all targets once and sync if changed. Returns dict of target -> changed."""
        results = {}

        for target in self._targets:
            status = self._statuses[target.name]
            current_mtime = self._get_db_mtime(target)

            if current_mtime > status.last_db_mtime or status.last_db_mtime == 0:
                # Database changed or first run
                cookie_count = self._extract_and_save(target)

                if cookie_count is not None:
                    status.last_sync = datetime.now().isoformat()
                    status.last_cookie_count = cookie_count
                    status.last_db_mtime = current_mtime
                    status.sync_count += 1
                    status.error = None
                    results[target.name] = True

                    # Fire callbacks
                    for cb in self._on_sync_callbacks:
                        try:
                            cb(target.name, cookie_count)
                        except Exception:
                            pass
                else:
                    status.error = "Extraction failed"
                    results[target.name] = False
            else:
                results[target.name] = False

        return results

    def start(self, interval: int = 60):
        """Start the sync daemon (blocking)."""
        self._running = True
        logger.info(f"Session sync daemon started (interval: {interval}s, targets: {len(self._targets)})")

        # Initial sync
        self.check_once()

        while self._running:
            time.sleep(interval)
            try:
                self.check_once()
            except Exception as e:
                logger.error(f"Sync check error: {e}")

    def stop(self):
        """Stop the sync daemon."""
        self._running = False
        logger.info("Session sync daemon stopped")

    def get_status(self) -> List[Dict]:
        """Get status of all sync targets."""
        statuses = []
        for target in self._targets:
            status = self._statuses.get(target.name, SyncStatus(target=target.name))
            statuses.append({
                "name": target.name,
                "browser": target.browser,
                "domains": target.domains,
                "output_dir": target.output_dir,
                "last_sync": status.last_sync,
                "last_cookie_count": status.last_cookie_count,
                "sync_count": status.sync_count,
                "error": status.error,
            })
        return statuses

    def save_config(self):
        """Save sync configuration to disk."""
        config = {
            "targets": [
                {
                    "name": t.name,
                    "domains": t.domains,
                    "browser": t.browser,
                    "browser_profile": t.browser_profile,
                    "output_dir": t.output_dir,
                    "output_filename": t.output_filename,
                }
                for t in self._targets
            ]
        }
        config_path = self.storage_dir / "sync_config.json"
        config_path.write_text(json.dumps(config, indent=2))
        logger.info(f"Sync config saved: {config_path}")

    @classmethod
    def load_config(cls, storage_dir: Optional[str] = None) -> "SessionSyncDaemon":
        """Load sync daemon from saved config."""
        daemon = cls(storage_dir=storage_dir)
        config_path = daemon.storage_dir / "sync_config.json"

        if config_path.exists():
            config = json.loads(config_path.read_text())
            for target_data in config.get("targets", []):
                daemon.add_target(SyncTarget(**target_data))

        return daemon
