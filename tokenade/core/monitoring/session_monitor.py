"""
Session monitoring for Tokenade.

Provides real-time session health monitoring during proxy operation.
Tracks cookie expiry, health scores, and refresh history.
"""
import time
import threading
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class CookieStatus:
    """Status of a single cookie."""
    name: str
    domain: str
    expires: Optional[float] = None
    remaining_seconds: Optional[float] = None
    is_secure: bool = False
    is_http_only: bool = False
    same_site: str = "None"
    health: str = "healthy"  # healthy, warning, expired


@dataclass
class SessionStatus:
    """Real-time status of a monitored session."""
    session_id: str
    site_name: str
    cookie_count: int = 0
    healthy_cookies: int = 0
    warning_cookies: int = 0
    expired_cookies: int = 0
    health_score: float = 0.0
    last_check: float = 0.0
    last_refresh: Optional[float] = None
    refresh_count: int = 0
    cookies: List[CookieStatus] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class MonitorConfig:
    """Monitoring configuration."""
    check_interval: float = 60.0  # seconds between health checks
    warning_threshold: float = 0.5  # cookie TTL ratio for warning
    auto_refresh: bool = False
    auto_refresh_threshold: float = 0.2  # refresh when this fraction of cookies expiring
    source_browser: Optional[str] = None


class SessionMonitor:
    """Monitor session health during proxy operation.

    Runs background health checks and tracks cookie expiry.
    """

    def __init__(self, config: Optional[MonitorConfig] = None):
        self.config = config or MonitorConfig()
        self._sessions: Dict[str, SessionStatus] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: List[Callable[[str, SessionStatus], None]] = []
        self._refresh_callback: Optional[Callable[[str], bool]] = None

    def register_session(self, session_id: str, session: Dict, site_name: str = "unknown"):
        """Register a session for monitoring."""
        cookies = session.get("cookies", [])
        status = SessionStatus(
            session_id=session_id,
            site_name=site_name,
            cookie_count=len(cookies),
            last_check=time.time(),
        )
        self._analyze_cookies(status, cookies)
        with self._lock:
            self._sessions[session_id] = status
        logger.debug(f"Registered session {session_id} ({site_name}) with {len(cookies)} cookies")

    def unregister_session(self, session_id: str):
        """Stop monitoring a session."""
        with self._lock:
            self._sessions.pop(session_id, None)

    def get_status(self, session_id: str) -> Optional[SessionStatus]:
        """Get current status of a monitored session."""
        with self._lock:
            return self._sessions.get(session_id)

    def get_all_statuses(self) -> List[SessionStatus]:
        """Get status of all monitored sessions."""
        with self._lock:
            return list(self._sessions.values())

    def on_health_change(self, callback: Callable[[str, SessionStatus], None]):
        """Register callback for health score changes."""
        self._callbacks.append(callback)

    def set_refresh_callback(self, callback: Callable[[str], bool]):
        """Set callback for auto-refresh."""
        self._refresh_callback = callback

    def start(self):
        """Start background monitoring."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Session monitor started")

    def stop(self):
        """Stop background monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Session monitor stopped")

    def _monitor_loop(self):
        """Background monitoring loop."""
        while self._running:
            try:
                self._check_all_sessions()
            except Exception as e:
                logger.error(f"Monitor check failed: {e}", exc_info=True)
            time.sleep(self.config.check_interval)

    def _check_all_sessions(self):
        """Check health of all registered sessions."""
        with self._lock:
            sessions = dict(self._sessions)

        for session_id, status in sessions.items():
            old_score = status.health_score
            self._update_status(status)
            new_score = status.health_score

            if old_score != new_score:
                for callback in self._callbacks:
                    try:
                        callback(session_id, status)
                    except Exception as e:
                        logger.error(f"Health callback failed: {e}", exc_info=True)

            if self.config.auto_refresh and new_score < (self.config.auto_refresh_threshold * 100):
                self._trigger_refresh(session_id, status)

    def _update_status(self, status: SessionStatus):
        """Update session status by re-analyzing cookies."""
        status.last_check = time.time()
        # Re-read cookies from the session's source if available
        # For now, just update based on existing cookie data
        self._recalculate_health(status)

    def _analyze_cookies(self, status: SessionStatus, cookies: List[Dict]):
        """Analyze cookies and update status."""
        now = time.time()
        status.cookies = []
        status.healthy_cookies = 0
        status.warning_cookies = 0
        status.expired_cookies = 0
        status.issues = []
        status.recommendations = []

        for cookie in cookies:
            name = cookie.get("name", "")
            domain = cookie.get("domain", "")
            expires = cookie.get("expires")
            secure = cookie.get("secure", False)
            http_only = cookie.get("httpOnly", False)
            same_site = cookie.get("sameSite", "None")

            cookie_status = CookieStatus(
                name=name,
                domain=domain,
                expires=expires,
                is_secure=secure,
                is_http_only=http_only,
                same_site=same_site,
            )

            if expires and expires > 0:
                remaining = expires - now
                cookie_status.remaining_seconds = remaining
                total_ttl = expires - (cookie.get("creation_time", now) if "creation_time" in cookie else now - 3600)
                ratio = remaining / max(total_ttl, 1) if total_ttl > 0 else 1.0

                if remaining <= 0:
                    cookie_status.health = "expired"
                    status.expired_cookies += 1
                elif ratio < self.config.warning_threshold:
                    cookie_status.health = "warning"
                    status.warning_cookies += 1
                else:
                    cookie_status.health = "healthy"
                    status.healthy_cookies += 1
            else:
                cookie_status.health = "healthy"
                status.healthy_cookies += 1

            if not secure:
                status.issues.append(f"Cookie '{name}' missing Secure flag")
            if not http_only:
                status.recommendations.append(f"Cookie '{name}' could benefit from HttpOnly flag")
            if same_site == "None":
                status.recommendations.append(f"Cookie '{name}' has SameSite=None")

            status.cookies.append(cookie_status)

        self._recalculate_health(status)

    def _recalculate_health(self, status: SessionStatus):
        """Recalculate health score from cookie statuses."""
        if not status.cookies:
            status.health_score = 0.0
            return

        total = len(status.cookies)
        healthy_weight = 1.0
        warning_weight = 0.5
        expired_weight = 0.0

        score = (
            status.healthy_cookies * healthy_weight
            + status.warning_cookies * warning_weight
            + status.expired_cookies * expired_weight
        ) / total * 100

        status.health_score = round(score, 1)

    def _trigger_refresh(self, session_id: str, status: SessionStatus):
        """Trigger auto-refresh for a session."""
        if not self._refresh_callback:
            return

        logger.info(f"Auto-refreshing session {session_id} (health: {status.health_score}%)")
        try:
            success = self._refresh_callback(session_id)
            if success:
                status.last_refresh = time.time()
                status.refresh_count += 1
                logger.info(f"Auto-refresh succeeded for {session_id}")
            else:
                logger.warning(f"Auto-refresh failed for {session_id}")
        except Exception as e:
            logger.error(f"Auto-refresh error for {session_id}: {e}", exc_info=True)

    def get_summary(self) -> Dict:
        """Get summary of all monitored sessions."""
        with self._lock:
            sessions = list(self._sessions.values())

        if not sessions:
            return {"total_sessions": 0, "overall_health": 0.0}

        total_cookies = sum(s.cookie_count for s in sessions)
        healthy = sum(s.healthy_cookies for s in sessions)
        warning = sum(s.warning_cookies for s in sessions)
        expired = sum(s.expired_cookies for s in sessions)
        avg_health = sum(s.health_score for s in sessions) / len(sessions)

        return {
            "total_sessions": len(sessions),
            "total_cookies": total_cookies,
            "healthy_cookies": healthy,
            "warning_cookies": warning,
            "expired_cookies": expired,
            "overall_health": round(avg_health, 1),
            "sessions": [
                {
                    "id": s.session_id,
                    "site": s.site_name,
                    "health": s.health_score,
                    "cookies": s.cookie_count,
                    "refreshes": s.refresh_count,
                }
                for s in sessions
            ],
        }
