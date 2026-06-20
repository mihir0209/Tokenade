"""
Batch Session Refresh for Multi-Account Orchestration.

Handles refreshing multiple .tokenade session files with:
- Rate limiting to avoid API throttling
- Parallel refresh with configurable concurrency
- Retry logic with exponential backoff
- Detailed reporting per account
- Health checks after refresh

Usage:
    batch = BatchRefresher(sessions_dir="sessions/")
    report = batch.refresh_all()
    print(f"Refreshed {report.succeeded}/{report.total}")
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionRefreshResult:
    """Result of refreshing a single session."""
    session_file: str
    site_name: str
    success: bool
    method: str  # "oauth" or "cookie"
    error: Optional[str] = None
    duration_ms: float = 0.0
    tokens_refreshed: int = 0


@dataclass
class BatchRefreshReport:
    """Report from a batch refresh operation."""
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    oauth_refreshed: int = 0
    cookie_refreshed: int = 0
    results: List[SessionRefreshResult] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.succeeded / self.total

    def summary(self) -> str:
        lines = [
            "=== Batch Refresh Report ===",
            f"Total: {self.total}",
            f"Succeeded: {self.succeeded}",
            f"Failed: {self.failed}",
            f"Skipped: {self.skipped}",
            f"OAuth refreshed: {self.oauth_refreshed}",
            f"Cookie refreshed: {self.cookie_refreshed}",
            f"Success rate: {self.success_rate:.1%}",
            f"Duration: {self.duration_ms:.0f}ms",
            "",
        ]

        for result in self.results:
            status = "✓" if result.success else "✗"
            method = f"[{result.method}]" if result.success else ""
            error = f" - {result.error}" if result.error else ""
            lines.append(f"  {status} {result.site_name} ({Path(result.session_file).name}) {method}{error}")

        return "\n".join(lines)


class BatchRefresher:
    """
    Refreshes multiple session files with rate limiting and parallelism.

    Usage:
        batch = BatchRefresher(
            sessions_dir="sessions/",
            max_workers=3,
            delay_between=1.0,
        )
        report = batch.refresh_all()
    """

    def __init__(
        self,
        sessions_dir: str = "sessions/",
        max_workers: int = 3,
        delay_between: float = 1.0,
        max_retries: int = 3,
        retry_delay: float = 5.0,
        source_browser: str = "firefox",
        source_profile: Optional[str] = None,
    ):
        self.sessions_dir = Path(sessions_dir)
        self.max_workers = max_workers
        self.delay_between = delay_between
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.source_browser = source_browser
        self.source_profile = source_profile

    def discover_sessions(self) -> List[Path]:
        """Find all .tokenade files in sessions directory."""
        if not self.sessions_dir.exists():
            return []
        return sorted(self.sessions_dir.glob("*.tokenade"))

    def refresh_all(
        self,
        session_files: Optional[List[str]] = None,
        force: bool = False,
    ) -> BatchRefreshReport:
        """
        Refresh all discovered or specified sessions.

        Args:
            session_files: Optional list of specific files to refresh
            force: Force refresh even if tokens aren't expired

        Returns:
            BatchRefreshReport
        """
        start_time = time.time()

        if session_files:
            files = [Path(f) for f in session_files]
        else:
            files = self.discover_sessions()

        report = BatchRefreshReport(total=len(files))

        if not files:
            logger.info("No session files found to refresh")
            return report

        logger.info(f"Refreshing {len(files)} sessions (max_workers={self.max_workers})")

        if self.max_workers <= 1:
            for i, f in enumerate(files):
                result = self._refresh_single(f, force)
                report.results.append(result)

                if result.success:
                    report.succeeded += 1
                    if result.method == "oauth":
                        report.oauth_refreshed += 1
                    else:
                        report.cookie_refreshed += 1
                else:
                    report.failed += 1

                if i < len(files) - 1:
                    time.sleep(self.delay_between)
        else:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {}
                for i, f in enumerate(files):
                    future = executor.submit(self._refresh_single, f, force)
                    futures[future] = (f, i)

                for future in as_completed(futures):
                    result = future.result()
                    report.results.append(result)

                    if result.success:
                        report.succeeded += 1
                        if result.method == "oauth":
                            report.oauth_refreshed += 1
                        else:
                            report.cookie_refreshed += 1
                    else:
                        report.failed += 1

        report.results.sort(key=lambda r: r.session_file)
        report.duration_ms = (time.time() - start_time) * 1000

        logger.info(f"Batch refresh complete: {report.succeeded}/{report.total} succeeded")
        return report

    def _refresh_single(self, session_file: Path, force: bool = False) -> SessionRefreshResult:
        """Refresh a single session file with retries."""
        start_time = time.time()
        session_file_str = str(session_file)

        try:
            with open(session_file) as f:
                session = json.load(f)

            site_name = session.get("site_name", "unknown")
            has_oauth = "oauth_config" in session

            if force:
                pass
            elif has_oauth:
                tokens = session.get("tokens", [])
                from tokenade.core.refresh.oauth_refresh import TokenPair
                token_pair = TokenPair.from_tokens_list(tokens)
                if not token_pair.is_expired:
                    return SessionRefreshResult(
                        session_file=session_file_str,
                        site_name=site_name,
                        success=True,
                        method="oauth",
                        duration_ms=(time.time() - start_time) * 1000,
                    )
            else:
                auth_status = session.get("auth_status", "unknown")
                if auth_status == "logged_in":
                    cookies = session.get("cookies", [])
                    has_expiry = any(
                        c.get("expires", 0) and int(c.get("expires", 0)) > 0
                        for c in cookies
                    )
                    if not has_expiry:
                        return SessionRefreshResult(
                            session_file=session_file_str,
                            site_name=site_name,
                            success=True,
                            method="cookie",
                            duration_ms=(time.time() - start_time) * 1000,
                        )

            for attempt in range(self.max_retries):
                try:
                    if has_oauth:
                        result = self._refresh_oauth(session_file, session)
                    else:
                        result = self._refresh_cookie(session_file, session)

                    if result.success:
                        return result

                    if attempt < self.max_retries - 1:
                        delay = self.retry_delay * (2 ** attempt)
                        logger.warning(f"Retry {attempt + 1}/{self.max_retries} for {session_file.name} in {delay}s")
                        time.sleep(delay)

                except Exception as e:
                    if attempt < self.max_retries - 1:
                        delay = self.retry_delay * (2 ** attempt)
                        logger.warning(f"Retry {attempt + 1}/{self.max_retries} for {session_file.name}: {e}")
                        time.sleep(delay)
                    else:
                        return SessionRefreshResult(
                            session_file=session_file_str,
                            site_name=site_name,
                            success=False,
                            method="oauth" if has_oauth else "cookie",
                            error=str(e),
                            duration_ms=(time.time() - start_time) * 1000,
                        )

            return SessionRefreshResult(
                session_file=session_file_str,
                site_name=site_name,
                success=False,
                method="oauth" if has_oauth else "cookie",
                error=f"Failed after {self.max_retries} attempts",
                duration_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            return SessionRefreshResult(
                session_file=session_file_str,
                site_name="unknown",
                success=False,
                method="unknown",
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )

    def _refresh_oauth(self, session_file: Path, session: Dict) -> SessionRefreshResult:
        """Refresh using OAuth token refresh."""
        from tokenade.core.refresh.oauth_refresh import SessionOAuthManager

        manager = SessionOAuthManager(str(session_file))
        manager._session = session

        result = manager.refresh()

        return SessionRefreshResult(
            session_file=str(session_file),
            site_name=session.get("site_name", "unknown"),
            success=result.success,
            method="oauth",
            error=result.error,
            duration_ms=result.duration_ms,
            tokens_refreshed=1 if result.success else 0,
        )

    def _refresh_cookie(self, session_file: Path, session: Dict) -> SessionRefreshResult:
        """Refresh using cookie re-export from source browser."""
        from tokenade.core.refresh.health_checker import SessionRefresher

        refresher = SessionRefresher()
        result = refresher.refresh(
            session_file=str(session_file),
            source_browser=self.source_browser,
            source_profile=self.source_profile,
        )

        return SessionRefreshResult(
            session_file=str(session_file),
            site_name=session.get("site_name", "unknown"),
            success=result.success,
            method="cookie",
            error=result.error,
            tokens_refreshed=result.cookies_refreshed,
        )
