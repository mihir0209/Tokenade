"""
Auto-Refresh Daemon for Tokenade sessions.

Watches sessions and auto-refreshes before expiry.
Runs as a background process with signal handling and webhook notifications.

Usage:
    tokenade daemon start        # Start daemon in background
    tokenade daemon stop         # Graceful shutdown
    tokenade daemon status       # Check daemon health
    tokenade daemon run-once     # Single refresh cycle (foreground)
    tokenade daemon add <file>   # Add session to watch list
    tokenade daemon remove <file># Remove session from watch list
    tokenade daemon logs         # View daemon logs
"""
import json
import os
import signal
import sys
import time
import threading
import logging
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_DIR = Path.home() / ".tokenade"
DAEMON_CONFIG_FILE = DEFAULT_CONFIG_DIR / "daemon.json"
DAEMON_PID_FILE = DEFAULT_CONFIG_DIR / "daemon.pid"
DAEMON_LOG_FILE = DEFAULT_CONFIG_DIR / "logs" / "daemon.log"
DAEMON_HISTORY_FILE = DEFAULT_CONFIG_DIR / "daemon_history.json"


class DaemonState(Enum):
    """Daemon operational state."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    REFRESHING = "refreshing"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class SessionEntry:
    """A session the daemon watches and refreshes."""
    path: str
    site_name: str = ""
    browser: str = "chrome"
    refresh_before_hours: float = 2.0
    target_url: str = ""
    enabled: bool = True
    last_refreshed: Optional[str] = None
    last_health: Optional[float] = None
    refresh_count: int = 0
    last_error: Optional[str] = None
    added_at: Optional[str] = None

    def __post_init__(self):
        if not self.added_at:
            self.added_at = datetime.now(timezone.utc).isoformat()


@dataclass
class DaemonConfig:
    """Daemon configuration."""
    sessions: List[SessionEntry] = field(default_factory=list)
    check_interval_minutes: float = 30.0
    max_concurrent_refreshes: int = 1
    webhook_url: Optional[str] = None
    webhook_on_success: bool = True
    webhook_on_failure: bool = True
    log_retention_days: int = 7
    headless: bool = True
    refresh_wait_seconds: int = 8
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sessions": [asdict(s) for s in self.sessions],
            "check_interval_minutes": self.check_interval_minutes,
            "max_concurrent_refreshes": self.max_concurrent_refreshes,
            "webhook_url": self.webhook_url,
            "webhook_on_success": self.webhook_on_success,
            "webhook_on_failure": self.webhook_on_failure,
            "log_retention_days": self.log_retention_days,
            "headless": self.headless,
            "refresh_wait_seconds": self.refresh_wait_seconds,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DaemonConfig":
        sessions = []
        for s in data.get("sessions", []):
            if isinstance(s, dict):
                sessions.append(SessionEntry(**s))
            else:
                sessions.append(s)
        return cls(
            sessions=sessions,
            check_interval_minutes=data.get("check_interval_minutes", 30.0),
            max_concurrent_refreshes=data.get("max_concurrent_refreshes", 1),
            webhook_url=data.get("webhook_url"),
            webhook_on_success=data.get("webhook_on_success", True),
            webhook_on_failure=data.get("webhook_on_failure", True),
            log_retention_days=data.get("log_retention_days", 7),
            headless=data.get("headless", True),
            refresh_wait_seconds=data.get("refresh_wait_seconds", 8),
            enabled=data.get("enabled", True),
        )

    def save(self, path: Optional[Path] = None):
        path = path or DAEMON_CONFIG_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))
        logger.info(f"Daemon config saved to {path}")

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "DaemonConfig":
        path = path or DAEMON_CONFIG_FILE
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
            return cls.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load daemon config: {e}")
            return cls()


@dataclass
class RefreshResult:
    """Result of a single session refresh attempt."""
    session_path: str
    site_name: str
    success: bool
    cookies_before: int = 0
    cookies_after: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    timestamp: Optional[str] = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class SessionDaemon:
    """
    Auto-refresh daemon that watches sessions and refreshes before expiry.

    Runs as a background process with:
    - Configurable check intervals
    - Signal handling (SIGTERM/SIGINT=stop, SIGHUP=reload)
    - Webhook notifications on refresh success/failure
    - PID file management
    - History tracking
    """

    def __init__(self, config: Optional[DaemonConfig] = None):
        self.config = config or DaemonConfig.load()
        self.state = DaemonState.STOPPED
        self._stop_event = threading.Event()
        self._reload_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._history: List[RefreshResult] = []
        self._original_handlers: Dict[int, Any] = {}

    # ── Lifecycle ──────────────────────────────────────────────

    def start(self, daemonize: bool = True) -> bool:
        """Start the daemon.

        Args:
            daemonize: If True, fork to background. If False, run in foreground.
        """
        if self.state == DaemonState.RUNNING:
            logger.warning("Daemon already running")
            return True

        # Check PID file
        if DAEMON_PID_FILE.exists():
            old_pid = DAEMON_PID_FILE.read_text().strip()
            if self._is_alive(old_pid):
                logger.error(f"Daemon already running with PID {old_pid}")
                return False
            else:
                logger.warning(f"Stale PID file found (PID {old_pid}), removing")
                DAEMON_PID_FILE.unlink(missing_ok=True)

        if daemonize:
            return self._daemonize()
        else:
            return self._run()

    def stop(self) -> bool:
        """Gracefully stop the daemon."""
        if not DAEMON_PID_FILE.exists():
            logger.info("Daemon not running (no PID file)")
            return True

        pid = DAEMON_PID_FILE.read_text().strip()
        if not self._is_alive(pid):
            logger.info(f"Daemon not running (stale PID {pid})")
            DAEMON_PID_FILE.unlink(missing_ok=True)
            return True

        logger.info(f"Stopping daemon (PID {pid})")
        try:
            os.kill(int(pid), signal.SIGTERM)
            # Wait for process to stop
            for _ in range(30):
                if not self._is_alive(pid):
                    break
                time.sleep(0.5)
            else:
                logger.warning("Daemon did not stop gracefully, sending SIGKILL")
                os.kill(int(pid), signal.SIGKILL)
            DAEMON_PID_FILE.unlink(missing_ok=True)
            return True
        except ProcessLookupError:
            DAEMON_PID_FILE.unlink(missing_ok=True)
            return True
        except Exception as e:
            logger.error(f"Failed to stop daemon: {e}")
            return False

    def status(self) -> Dict[str, Any]:
        """Get daemon status."""
        pid = None
        running = False
        uptime = None

        if DAEMON_PID_FILE.exists():
            pid = DAEMON_PID_FILE.read_text().strip()
            running = self._is_alive(pid)

        return {
            "running": running,
            "pid": int(pid) if running else None,
            "state": self.state.value,
            "config_file": str(DAEMON_CONFIG_FILE),
            "pid_file": str(DAEMON_PID_FILE),
            "sessions_watched": len(self.config.sessions),
            "sessions_enabled": sum(1 for s in self.config.sessions if s.enabled),
            "check_interval_minutes": self.config.check_interval_minutes,
            "webhook_configured": self.config.webhook_url is not None,
            "history_count": len(self._history),
        }

    # ── Config Management ──────────────────────────────────────

    def add_session(self, session_path: str, browser: str = "chrome",
                    refresh_before_hours: float = 2.0, target_url: str = "",
                    site_name: str = "") -> bool:
        """Add a session to the watch list."""
        path = Path(session_path).resolve()
        if not path.exists():
            logger.error(f"Session file not found: {session_path}")
            return False

        # Check for duplicates
        for s in self.config.sessions:
            if Path(s.path).resolve() == path:
                logger.warning(f"Session already watched: {session_path}")
                return False

        # Auto-detect site name if not provided
        if not site_name:
            site_name = path.stem

        entry = SessionEntry(
            path=str(path),
            site_name=site_name,
            browser=browser,
            refresh_before_hours=refresh_before_hours,
            target_url=target_url,
        )
        self.config.sessions.append(entry)
        self.config.save()
        logger.info(f"Added session: {site_name} ({path.name})")
        return True

    def remove_session(self, session_path: str) -> bool:
        """Remove a session from the watch list."""
        path = Path(session_path).resolve()
        original_count = len(self.config.sessions)
        self.config.sessions = [
            s for s in self.config.sessions
            if Path(s.path).resolve() != path
        ]
        if len(self.config.sessions) < original_count:
            self.config.save()
            logger.info(f"Removed session: {session_path}")
            return True
        logger.warning(f"Session not found in watch list: {session_path}")
        return False

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all watched sessions with status."""
        result = []
        for s in self.config.sessions:
            path = Path(s.path)
            result.append({
                "path": s.path,
                "site_name": s.site_name,
                "browser": s.browser,
                "enabled": s.enabled,
                "file_exists": path.exists(),
                "refresh_before_hours": s.refresh_before_hours,
                "last_refreshed": s.last_refreshed,
                "last_health": s.last_health,
                "refresh_count": s.refresh_count,
                "last_error": s.last_error,
            })
        return result

    # ── Core Refresh Logic ─────────────────────────────────────

    def run_once(self) -> List[RefreshResult]:
        """Run a single refresh cycle for all enabled sessions."""
        results = []
        enabled = [s for s in self.config.sessions if s.enabled]

        if not enabled:
            logger.info("No enabled sessions to refresh")
            return results

        logger.info(f"Refresh cycle: {len(enabled)} sessions")

        for entry in enabled:
            result = self._refresh_session(entry)
            results.append(result)
            self._history.append(result)

            # Update entry metadata
            entry.last_refreshed = result.timestamp
            if result.success:
                entry.last_error = None
                entry.refresh_count += 1
            else:
                entry.last_error = result.error

        # Save config with updated metadata
        self.config.save()
        self._save_history()

        # Send webhook notifications
        self._send_webhook_notifications(results)

        return results

    def _refresh_session(self, entry: SessionEntry) -> RefreshResult:
        """Refresh a single session."""
        start_time = time.time()
        path = Path(entry.path)

        if not path.exists():
            return RefreshResult(
                session_path=entry.path,
                site_name=entry.site_name,
                success=False,
                error="Session file not found",
            )

        try:
            # Load session to get cookies
            from tokenade.core.importer.session_packager import SessionPackager
            packager = SessionPackager()
            session = packager.load(str(path))
            cookies = session.get("cookies", [])
            cookies_before = len(cookies)

            if not cookies:
                return RefreshResult(
                    session_path=entry.path,
                    site_name=entry.site_name,
                    success=False,
                    cookies_before=0,
                    error="No cookies in session",
                )

            # Auto-detect URL if not set
            target_url = entry.target_url
            if not target_url:
                target_url = self._detect_url_from_cookies(cookies)
                if not target_url:
                    return RefreshResult(
                        session_path=entry.path,
                        site_name=entry.site_name,
                        success=False,
                        cookies_before=cookies_before,
                        error="Could not detect target URL from cookies",
                    )

            # Launch browser and refresh
            from tokenade.core.browser.undetectable import SystemBrowserLauncher
            from tokenade.core.browser.cdp_connection import cdp_cmd

            self.state = DaemonState.REFRESHING
            logger.info(f"Refreshing {entry.site_name}: {target_url}")

            launcher = SystemBrowserLauncher()
            browser_proc = launcher.launch(
                browser=entry.browser,
                visible=not self.config.headless,
                port=9222,  # Will be handled by launcher
            )

            try:
                # Inject cookies via CDP
                fresh_cookies, fresh_ls, fresh_ss = self._refresh_cookies(
                    browser_proc, session, target_url
                )

                if fresh_cookies:
                    session["cookies"] = fresh_cookies
                    if fresh_ls:
                        session["local_storage"] = fresh_ls
                    if fresh_ss:
                        session["session_storage"] = fresh_ss

                    if "metadata" not in session:
                        session["metadata"] = {}
                    session["metadata"]["cookie_count"] = len(fresh_cookies)
                    session["metadata"]["last_refreshed"] = datetime.now(timezone.utc).isoformat()

                    packager.save(session, str(path))

                    duration = time.time() - start_time
                    logger.info(f"Refreshed {entry.site_name}: {cookies_before} → {len(fresh_cookies)} cookies ({duration:.1f}s)")

                    return RefreshResult(
                        session_path=entry.path,
                        site_name=entry.site_name,
                        success=True,
                        cookies_before=cookies_before,
                        cookies_after=len(fresh_cookies),
                        duration_seconds=duration,
                    )
                else:
                    return RefreshResult(
                        session_path=entry.path,
                        site_name=entry.site_name,
                        success=False,
                        cookies_before=cookies_before,
                        error="No cookies extracted after refresh",
                    )
            finally:
                browser_proc.close()
                self.state = DaemonState.RUNNING

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Refresh failed for {entry.site_name}: {e}")
            return RefreshResult(
                session_path=entry.path,
                site_name=entry.site_name,
                success=False,
                duration_seconds=duration,
                error=str(e),
            )

    def _refresh_cookies(self, browser_proc, session, target_url):
        """Refresh cookies via browser CDP connection (simplified wrapper)."""
        # Import the refresh logic from management.py
        from tokenade.cli.management import _refresh_session_cookies
        cookies = session.get("cookies", [])
        return _refresh_session_cookies(
            browser_proc, 9222, cookies, target_url,
            self.config.refresh_wait_seconds
        )

    def _detect_url_from_cookies(self, cookies: List[Dict]) -> str:
        """Auto-detect target URL from cookie domains."""
        from tokenade.cli.management import _detect_url_from_cookies
        return _detect_url_from_cookies(cookies)

    # ── Daemon Internals ───────────────────────────────────────

    def _run(self) -> bool:
        """Run the daemon in the foreground."""
        self.state = DaemonState.RUNNING
        self._setup_signal_handlers()
        self._write_pid()
        self._ensure_log_dir()

        logger.info("Daemon started")
        logger.info(f"Watching {len(self.config.sessions)} sessions")
        logger.info(f"Check interval: {self.config.check_interval_minutes} minutes")

        try:
            while not self._stop_event.is_set():
                # Check if reload requested
                if self._reload_event.is_set():
                    self._reload_config()
                    self._reload_event.clear()

                # Run refresh cycle
                self.run_once()

                # Wait for next cycle or stop signal
                self._stop_event.wait(timeout=self.config.check_interval_minutes * 60)
        except Exception as e:
            logger.error(f"Daemon error: {e}", exc_info=True)
            self.state = DaemonState.ERROR
        finally:
            self._cleanup()

        return True

    def _daemonize(self) -> bool:
        """Fork to background (Unix double-fork)."""
        try:
            # First fork
            pid = os.fork()
            if pid > 0:
                # Parent waits for child to start, then exits
                time.sleep(1)
                print(f"Daemon started with PID {pid}")
                return True

            # Child becomes session leader
            os.setsid()

            # Second fork
            pid = os.fork()
            if pid > 0:
                # First child exits
                sys.exit(0)

            # Redirect stdio to /dev/null
            sys.stdin = open(os.devnull, "r")
            sys.stdout = open(os.devnull, "w")
            sys.stderr = open(os.devnull, "w")

            # Run daemon
            self._run()
            sys.exit(0)

        except OSError as e:
            logger.error(f"Failed to daemonize: {e}")
            return False

    def _setup_signal_handlers(self):
        """Register signal handlers."""
        self._original_handlers[signal.SIGTERM] = signal.getsignal(signal.SIGTERM)
        self._original_handlers[signal.SIGHUP] = signal.getsignal(signal.SIGHUP)
        self._original_handlers[signal.SIGINT] = signal.getsignal(signal.SIGINT)

        def handle_stop(signum, _frame):
            logger.info(f"Received signal {signum}, stopping...")
            self.state = DaemonState.STOPPING
            self._stop_event.set()

        def handle_reload(signum, _frame):
            logger.info(f"Received SIGHUP, reloading config...")
            self._reload_event.set()

        signal.signal(signal.SIGTERM, handle_stop)
        signal.signal(signal.SIGINT, handle_stop)
        signal.signal(signal.SIGHUP, handle_reload)

    def _reload_config(self):
        """Reload configuration from disk."""
        old_count = len(self.config.sessions)
        self.config = DaemonConfig.load()
        new_count = len(self.config.sessions)
        logger.info(f"Config reloaded: {old_count} → {new_count} sessions")

    def _write_pid(self):
        """Write PID file."""
        DAEMON_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        DAEMON_PID_FILE.write_text(str(os.getpid()))
        logger.debug(f"PID file written: {os.getpid()}")

    def _cleanup(self):
        """Cleanup on exit."""
        DAEMON_PID_FILE.unlink(missing_ok=True)
        # Restore original signal handlers
        for sig, handler in self._original_handlers.items():
            signal.signal(sig, handler)
        logger.info("Daemon stopped")

    def _ensure_log_dir(self):
        """Ensure log directory exists."""
        DAEMON_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # ── History ────────────────────────────────────────────────

    def _save_history(self):
        """Save refresh history to disk."""
        # Keep last 1000 entries
        history = self._history[-1000:]
        data = [asdict(r) for r in history]
        DAEMON_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        DAEMON_HISTORY_FILE.write_text(json.dumps(data, indent=2))

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent refresh history."""
        if not self._history:
            # Load from disk
            if DAEMON_HISTORY_FILE.exists():
                try:
                    data = json.loads(DAEMON_HISTORY_FILE.read_text())
                    self._history = [RefreshResult(**r) for r in data]
                except Exception:
                    pass
        return [asdict(r) for r in self._history[-limit:]]

    # ── Webhooks ───────────────────────────────────────────────

    def _send_webhook_notifications(self, results: List[RefreshResult]):
        """Send webhook notifications for refresh results."""
        if not self.config.webhook_url:
            return

        for result in results:
            if result.success and not self.config.webhook_on_success:
                continue
            if not result.success and not self.config.webhook_on_failure:
                continue

            self._send_webhook(result)

    def _send_webhook(self, result: RefreshResult):
        """Send a single webhook notification."""
        try:
            import urllib.request
            import urllib.error

            status = "✅ SUCCESS" if result.success else "❌ FAILED"
            payload = {
                "text": f"{status}: {result.site_name}\n"
                        f"Cookies: {result.cookies_before} → {result.cookies_after}\n"
                        f"Duration: {result.duration_seconds:.1f}s\n"
                        f"Time: {result.timestamp}",
                "session": result.site_name,
                "success": result.success,
                "cookies_before": result.cookies_before,
                "cookies_after": result.cookies_after,
                "duration_seconds": result.duration_seconds,
                "error": result.error,
                "timestamp": result.timestamp,
            }

            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.config.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
            logger.debug(f"Webhook sent for {result.site_name}")

        except Exception as e:
            logger.warning(f"Webhook failed for {result.site_name}: {e}")

    # ── Utilities ──────────────────────────────────────────────

    @staticmethod
    def _is_alive(pid: str) -> bool:
        """Check if a process with given PID is alive."""
        try:
            pid = int(pid)
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, ValueError, PermissionError):
            return False
