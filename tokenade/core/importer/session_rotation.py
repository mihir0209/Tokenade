"""
Session Rotation - Auto-detect login events and rotate sessions.

Monitors cookie changes during proxy operation to detect login events
and trigger automatic session re-export.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Callable
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


@dataclass
class LoginEvent:
    """Detected login event."""
    timestamp: str
    site_name: str
    event_type: str  # 'login', 'logout', 'token_refresh'
    cookies_added: List[str] = field(default_factory=list)
    cookies_removed: List[str] = field(default_factory=list)
    cookies_modified: List[str] = field(default_factory=list)


class SessionRotationMonitor:
    """Monitor cookie changes and detect login/logout events."""

    # Known auth cookie patterns per site
    AUTH_COOKIE_PATTERNS = {
        "google": ["SID", "HSID", "SSID", "APISID", "SAPISID", "__Secure-1PSID"],
        "github": ["logged_in", "user_session", "_gh_sess", "gh_sess"],
        "twitter": ["auth_token", "ct0", "twid"],
        "facebook": ["c_user", "xs", "datr", "fr"],
        "default": [
            "session_id", "session", "sid", "token", "auth",
            "jwt", "access_token",
        ],
    }

    def __init__(self, site_name: str = "default"):
        self.site_name = site_name
        self._previous_cookies: Dict[str, str] = {}
        self._events: List[LoginEvent] = []
        self._on_login_callback: Optional[Callable] = None

    def set_callback(self, callback: Callable):
        """Set callback for login events."""
        self._on_login_callback = callback

    def snapshot(self, cookies: List[Dict]):
        """Take a snapshot of current cookies for comparison."""
        self._previous_cookies = {
            c.get("name", ""): c.get("value", "") for c in cookies
        }

    def detect_changes(self, current_cookies: List[Dict]) -> Optional[LoginEvent]:
        """Compare current cookies with previous snapshot to detect login events.

        Returns LoginEvent if a significant change is detected, None otherwise.
        """
        current = {c.get("name", ""): c.get("value", "") for c in current_cookies}

        previous = self._previous_cookies

        # Find changes
        added = set(current.keys()) - set(previous.keys())
        removed = set(previous.keys()) - set(current.keys())
        modified = {
            name
            for name in set(current.keys()) & set(previous.keys())
            if current[name] != previous[name]
        }

        if not added and not removed and not modified:
            return None

        # Determine event type
        auth_names = self._get_auth_cookie_names()

        auth_added = added & auth_names
        auth_removed = removed & auth_names
        auth_modified = modified & auth_names

        if auth_added or auth_modified:
            event_type = "login"
        elif auth_removed:
            event_type = "logout"
        elif modified:
            event_type = "token_refresh"
        else:
            event_type = "cookie_change"

        event = LoginEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            site_name=self.site_name,
            event_type=event_type,
            cookies_added=sorted(added),
            cookies_removed=sorted(removed),
            cookies_modified=sorted(modified),
        )

        self._events.append(event)
        self._previous_cookies = current

        # Fire callback
        if self._on_login_callback:
            try:
                self._on_login_callback(event)
            except Exception as e:
                logger.warning(f"Login callback failed: {e}")

        logger.info(
            f"Detected {event_type}: +{len(added)} -{len(removed)} ~{len(modified)} cookies"
        )

        return event

    def _get_auth_cookie_names(self) -> Set[str]:
        """Get auth cookie names for the current site."""
        # Check specific site patterns
        for site, patterns in self.AUTH_COOKIE_PATTERNS.items():
            if site in self.site_name.lower():
                return set(patterns)

        # Use default patterns
        return set(self.AUTH_COOKIE_PATTERNS["default"])

    def get_events(self) -> List[LoginEvent]:
        """Get all detected events."""
        return list(self._events)

    def clear_events(self):
        """Clear event history."""
        self._events.clear()

    def should_refresh(self) -> bool:
        """Check if a session refresh is recommended based on events."""
        if not self._events:
            return False

        # Check last 5 events for login patterns
        recent = self._events[-5:]
        login_count = sum(1 for e in recent if e.event_type == "login")

        # Multiple logins may indicate token rotation needed
        return login_count >= 2
