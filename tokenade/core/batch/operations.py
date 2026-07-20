"""
Batch Operations - Multi-site export and load.

Provides batch processing capabilities for exporting and loading
multiple sites simultaneously.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class BatchSiteConfig:
    """Configuration for a single site in batch operation."""
    name: str
    url: str
    domains: List[str] = field(default_factory=list)
    auth_cookies: List[str] = field(default_factory=list)
    validation_strategies: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict) -> 'BatchSiteConfig':
        """Create from dictionary."""
        return cls(
            name=data.get('name', ''),
            url=data.get('url', ''),
            domains=data.get('domains', []),
            auth_cookies=data.get('auth_cookies', []),
            validation_strategies=data.get('validation_strategies', {}),
        )


@dataclass
class BatchExportResult:
    """Result of batch export operation."""
    success: bool
    sites_exported: int
    sites_total: int
    cookies_total: int
    results: List[Dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class BatchLoadResult:
    """Result of batch load operation."""
    success: bool
    sites_loaded: int
    sites_total: int
    cookies_injected: int
    results: List[Dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class BatchExporter:
    """
    Batch export multiple sites from browser.

    Usage:
        exporter = BatchExporter()
        result = exporter.export_batch(
            browser="firefox",
            sites=sites_config,
            output_dir="./sessions"
        )
    """

    def export_batch(
        self,
        browser: str,
        sites: List[BatchSiteConfig],
        output_dir: str,
        browser_path: Optional[str] = None,
        profile: Optional[str] = None,
        extract_local_storage: bool = False
    ) -> BatchExportResult:
        """
        Export multiple sites in batch.

        Args:
            browser: Browser name
            sites: List of site configurations
            output_dir: Output directory
            browser_path: Custom browser profile path
            profile: Profile name
            extract_local_storage: Extract localStorage

        Returns:
            BatchExportResult
        """
        from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery
        from tokenade.core.importer.cookie_extractor import CookieExtractor
        from tokenade.core.importer.session_packager import SessionPackager

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        results = []
        errors = []
        total_cookies = 0

        # Discover browser profile if not provided
        if not browser_path:
            discovery = BrowserProfileDiscovery()
            profiles = discovery.discover_all()
            all_profiles = []
            for browser_profiles in profiles.values():
                all_profiles.extend(browser_profiles)

            matching = [p for p in all_profiles if p.browser == browser]
            if profile:
                matching = [p for p in matching if p.name == profile]

            if matching:
                browser_path = str(matching[0].path)
                logger.info(f"Using profile: {matching[0].name}")
            else:
                return BatchExportResult(
                    success=False,
                    sites_exported=0,
                    sites_total=len(sites),
                    cookies_total=0,
                    errors=[f"No profile found for {browser}"]
                )

        # Extract all cookies first
        extractor = CookieExtractor(browser_path, browser=browser)
        try:
            all_cookies = extractor.extract(site_filter=None)
        except Exception as e:
            return BatchExportResult(
                success=False,
                sites_exported=0,
                sites_total=len(sites),
                cookies_total=0,
                errors=[f"Cookie extraction failed: {e}"]
            )

        logger.info(f"Extracted {len(all_cookies)} total cookies")

        # Process each site
        packager = SessionPackager()

        for site in sites:
            try:
                # Filter cookies for this site
                site_cookies = []
                for cookie in all_cookies:
                    domain = cookie.get('domain', '')
                    for d in site.domains:
                        if d.startswith('.'):
                            if domain.endswith(d) or domain == d[1:]:
                                site_cookies.append(cookie)
                                break
                        else:
                            if domain == d or domain.endswith('.' + d):
                                site_cookies.append(cookie)
                                break

                if not site_cookies:
                    logger.warning(f"No cookies found for {site.name}")
                    results.append({
                        "site": site.name,
                        "status": "no_cookies",
                        "cookies": 0
                    })
                    continue

                # Package session
                extra = [c for c in site_cookies if c.get("name") in ("EMAIL", "email")]
                package = packager.package(
                    cookies=site_cookies,
                    browser=browser,
                    profile=profile or "unknown",
                    local_storage=None,
                    extra_cookies=extra if extra else None,
                )

                # Save
                output_file = output_path / f"{site.name}_session"
                saved_path = packager.save(package, str(output_file))

                total_cookies += len(site_cookies)
                results.append({
                    "site": site.name,
                    "status": "success",
                    "cookies": len(site_cookies),
                    "path": saved_path
                })

                logger.info(f"Exported {site.name}: {len(site_cookies)} cookies")

            except Exception as e:
                logger.error(f"Failed to export {site.name}: {e}")
                errors.append(f"{site.name}: {e}")
                results.append({
                    "site": site.name,
                    "status": "error",
                    "error": str(e)
                })

        return BatchExportResult(
            success=len(errors) == 0,
            sites_exported=sum(1 for r in results if r['status'] == 'success'),
            sites_total=len(sites),
            cookies_total=total_cookies,
            results=results,
            errors=errors
        )


class BatchLoader:
    """
    Batch load multiple sessions into browser.

    Usage:
        loader = BatchLoader()
        result = loader.load_batch(
            sessions_dir="./sessions",
            target_browser="brave",
            site_configs=sites_config
        )
    """

    def load_batch(
        self,
        sessions_dir: str,
        target_browser: str,
        site_configs: Optional[List[BatchSiteConfig]] = None,
        profile_dir: Optional[str] = None,
        validate: bool = False,
        visible: bool = False
    ) -> BatchLoadResult:
        """
        Load multiple sessions in batch.

        Args:
            sessions_dir: Directory containing session files
            target_browser: Target browser name
            site_configs: Optional site configurations for validation
            profile_dir: Target profile directory
            validate: Validate sessions after loading
            visible: Show browser window

        Returns:
            BatchLoadResult
        """
        from tokenade.core.importer.session_loader import SessionLoader

        sessions_path = Path(sessions_dir)
        if not sessions_path.exists():
            return BatchLoadResult(
                success=False,
                sites_loaded=0,
                sites_total=0,
                cookies_injected=0,
                errors=[f"Directory not found: {sessions_dir}"]
            )

        # Find session files
        session_files = list(sessions_path.glob("*.tokenade")) + list(sessions_path.glob("*.session"))
        if not session_files:
            session_files = list(sessions_path.glob("*.json"))

        results = []
        errors = []
        total_injected = 0

        loader = SessionLoader()

        for session_file in session_files:
            try:
                logger.info(f"Loading: {session_file.name}")

                # Find matching site config
                site_config = None
                if site_configs:
                    for config in site_configs:
                        if config.name in session_file.name:
                            site_config = {
                                'name': config.name,
                                'domains': config.domains,
                                'validation_strategies': config.validation_strategies
                            }
                            break

                result = loader.load(
                    file_path=str(session_file),
                    stealth_level="maximum",
                    validate=validate,
                    visible=visible,
                    profile_dir=profile_dir,
                    site_config=site_config
                )

                if result['success']:
                    total_injected += result['cookies_injected']
                    results.append({
                        "file": session_file.name,
                        "status": "success",
                        "cookies": result['cookies_injected'],
                        "site": result.get('site_name', 'unknown')
                    })
                else:
                    results.append({
                        "file": session_file.name,
                        "status": "failed",
                        "error": result.get('error', 'Unknown error')
                    })
                    errors.append(f"{session_file.name}: {result.get('error', 'Unknown error')}")

            except Exception as e:
                logger.error(f"Failed to load {session_file.name}: {e}")
                errors.append(f"{session_file.name}: {e}")
                results.append({
                    "file": session_file.name,
                    "status": "error",
                    "error": str(e)
                })

        return BatchLoadResult(
            success=len(errors) == 0,
            sites_loaded=sum(1 for r in results if r['status'] == 'success'),
            sites_total=len(session_files),
            cookies_injected=total_injected,
            results=results,
            errors=errors
        )


def load_batch_config(config_file: str) -> List[BatchSiteConfig]:
    """
    Load batch configuration from JSON file.

    Args:
        config_file: Path to JSON config file

    Returns:
        List of BatchSiteConfig
    """
    with open(config_file) as f:
        data = json.load(f)

    if isinstance(data, list):
        return [BatchSiteConfig.from_dict(item) for item in data]
    elif isinstance(data, dict):
        return [BatchSiteConfig.from_dict(data)]
    else:
        raise ValueError("Invalid config format")


def generate_batch_report(result: BatchExportResult | BatchLoadResult) -> str:
    """
    Generate human-readable batch report.

    Args:
        result: Batch operation result

    Returns:
        Formatted report string
    """
    lines = []

    if isinstance(result, BatchExportResult):
        lines.append("BATCH EXPORT REPORT")
        lines.append("=" * 50)
        lines.append(f"Sites exported: {result.sites_exported}/{result.sites_total}")
        lines.append(f"Total cookies: {result.cookies_total}")
        lines.append("")

        for r in result.results:
            status = "✅" if r['status'] == 'success' else "❌"
            lines.append(f"{status} {r['site']}: {r.get('cookies', 0)} cookies")
            if r.get('path'):
                lines.append(f"   Path: {r['path']}")
    else:
        lines.append("BATCH LOAD REPORT")
        lines.append("=" * 50)
        lines.append(f"Sites loaded: {result.sites_loaded}/{result.sites_total}")
        lines.append(f"Total cookies injected: {result.cookies_injected}")
        lines.append("")

        for r in result.results:
            status = "✅" if r['status'] == 'success' else "❌"
            lines.append(f"{status} {r.get('site', r.get('file'))}: {r.get('cookies', 0)} cookies")

    if result.errors:
        lines.append("")
        lines.append("ERRORS:")
        for error in result.errors:
            lines.append(f"  • {error}")

    return "\n".join(lines)


# ── Parallel Batch Operations ──────────────────────────────────────────────

import time
from concurrent.futures import ThreadPoolExecutor, as_completed


class ParallelBatchResult:
    """Result of a parallel batch operation."""

    def __init__(self, operation: str):
        self.operation = operation
        self.successes: List[Dict[str, Any]] = []
        self.failures: List[Dict[str, Any]] = []
        self.start_time = time.time()
        self.end_time: Optional[float] = None

    def add_success(self, item: Dict[str, Any]):
        """Add a successful result."""
        self.successes.append(item)

    def add_failure(self, item: Dict[str, Any], error: str):
        """Add a failed result."""
        self.failures.append({"item": item, "error": error})

    def complete(self):
        """Mark the operation as complete."""
        self.end_time = time.time()

    @property
    def duration(self) -> float:
        """Get operation duration in seconds."""
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    @property
    def total(self) -> int:
        """Get total number of items processed."""
        return len(self.successes) + len(self.failures)

    @property
    def success_rate(self) -> float:
        """Get success rate as percentage."""
        if self.total == 0:
            return 0.0
        return (len(self.successes) / self.total) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "operation": self.operation,
            "total": self.total,
            "successes": len(self.successes),
            "failures": len(self.failures),
            "success_rate": f"{self.success_rate:.1f}%",
            "duration_seconds": round(self.duration, 2),
            "details": {
                "successful_items": self.successes,
                "failed_items": self.failures,
            },
        }


class ParallelBatchExporter:
    """Parallel batch export sessions from multiple browsers."""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers

    def export_all(
        self,
        output_dir: str,
        browsers: Optional[List[str]] = None,
        sites: Optional[List[str]] = None,
    ) -> ParallelBatchResult:
        """
        Export all sessions from discovered browsers in parallel.

        Args:
            output_dir: Directory to save exported sessions
            browsers: List of browser names to export from (None = all)
            sites: List of sites to export (None = all)

        Returns:
            ParallelBatchResult with successes and failures
        """
        result = ParallelBatchResult("batch-export")
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery

        discovery = BrowserProfileDiscovery()
        discovered = discovery.discover_all()
        if browsers:
            discovered = [b for b in discovered if b.get("name") in browsers]

        tasks = []
        for browser in discovered:
            for site in (sites or [None]):
                tasks.append({
                    "browser": browser,
                    "site": site,
                    "output_dir": str(output_path),
                })

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_task = {
                executor.submit(self._export_single, task): task
                for task in tasks
            }

            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    session_file = future.result()
                    result.add_success({
                        "browser": task["browser"].get("name", "unknown"),
                        "site": task["site"] or "all",
                        "session_file": session_file,
                    })
                except Exception as e:
                    result.add_failure({
                        "browser": task["browser"].get("name", "unknown"),
                        "site": task["site"] or "all",
                    }, str(e))

        result.complete()
        return result

    def _export_single(self, task: Dict[str, Any]) -> str:
        """Export a single session."""
        from tokenade.core.importer.session_exporter import SessionExporter

        browser = task["browser"]
        site = task["site"]
        output_dir = task["output_dir"]

        exporter = SessionExporter()
        session_file = exporter.export(
            browser_name=browser.get("name"),
            site_name=site,
            output_dir=output_dir,
        )

        if not session_file:
            raise RuntimeError(f"Failed to export session from {browser.get('name')}")

        return session_file


class ParallelBatchLoader:
    """Parallel batch load sessions into browsers."""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers

    def load_all(
        self,
        session_dir: str,
        pattern: str = "*.tokenade",
        browser_name: Optional[str] = None,
        visible: bool = False,
    ) -> ParallelBatchResult:
        """
        Load all sessions from a directory in parallel.

        Args:
            session_dir: Directory containing session files
            pattern: File pattern to match
            browser_name: Target browser name
            visible: Run browser in visible mode

        Returns:
            ParallelBatchResult with successes and failures
        """
        result = ParallelBatchResult("batch-load")
        session_path = Path(session_dir)

        if not session_path.exists():
            raise FileNotFoundError(f"Session directory not found: {session_dir}")

        session_files = list(session_path.glob(pattern))
        if not session_files:
            raise FileNotFoundError(f"No sessions found matching pattern: {pattern}")

        tasks = [
            {"session_file": str(f), "browser_name": browser_name, "visible": visible}
            for f in session_files
        ]

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_task = {
                executor.submit(self._load_single, task): task
                for task in tasks
            }

            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    success = future.result()
                    if success:
                        result.add_success({
                            "session_file": task["session_file"],
                            "browser": task["browser_name"] or "auto",
                        })
                    else:
                        result.add_failure({
                            "session_file": task["session_file"],
                        }, "Load returned False")
                except Exception as e:
                    result.add_failure({
                        "session_file": task["session_file"],
                    }, str(e))

        result.complete()
        return result

    def _load_single(self, task: Dict[str, Any]) -> bool:
        """Load a single session."""
        from tokenade.core.importer.session_loader import SessionLoader

        loader = SessionLoader()
        return loader.load(
            session_file=task["session_file"],
            browser_name=task["browser_name"],
            visible=task["visible"],
        )


class ParallelBatchRefresher:
    """Parallel batch refresh multiple sessions."""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers

    def refresh_all(
        self,
        session_dir: str,
        pattern: str = "*.tokenade",
        output_dir: Optional[str] = None,
    ) -> ParallelBatchResult:
        """
        Refresh all sessions in a directory in parallel.

        Args:
            session_dir: Directory containing session files
            pattern: File pattern to match
            output_dir: Output directory for refreshed sessions

        Returns:
            ParallelBatchResult with successes and failures
        """
        result = ParallelBatchResult("batch-refresh")
        session_path = Path(session_dir)

        if not session_path.exists():
            raise FileNotFoundError(f"Session directory not found: {session_dir}")

        session_files = list(session_path.glob(pattern))
        if not session_files:
            raise FileNotFoundError(f"No sessions found matching pattern: {pattern}")

        tasks = [
            {"session_file": str(f), "output_dir": output_dir}
            for f in session_files
        ]

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_task = {
                executor.submit(self._refresh_single, task): task
                for task in tasks
            }

            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    refreshed_file = future.result()
                    if refreshed_file:
                        result.add_success({
                            "original": task["session_file"],
                            "refreshed": refreshed_file,
                        })
                    else:
                        result.add_failure({
                            "session_file": task["session_file"],
                        }, "Refresh returned None")
                except Exception as e:
                    result.add_failure({
                        "session_file": task["session_file"],
                    }, str(e))

        result.complete()
        return result

    def _refresh_single(self, task: Dict[str, Any]) -> Optional[str]:
        """Refresh a single session."""
        from tokenade.core.refresh.session_refresher import SessionRefresher

        refresher = SessionRefresher()
        return refresher.refresh(
            session_file=task["session_file"],
            output_dir=task["output_dir"],
        )
