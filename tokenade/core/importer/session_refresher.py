"""
Session auto-refresh: detect cookie expiry during proxy operation, re-export from source browser.

Features:
- Periodic cookie expiry monitoring
- Auto-refresh from source browser when cookies expire
- Multi-browser fallback (try firefox, then chrome, etc.)
- WebSocket notifications to connected clients on refresh
- Hot-reload session into running proxy
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Callable, Awaitable, List, Set

logger = logging.getLogger(__name__)


@dataclass
class RefreshConfig:
    """Configuration for session auto-refresh."""
    check_interval: int = 300  # Check every 5 minutes
    expiry_warning_days: int = 7  # Warn if expiring within 7 days
    expiry_critical_days: int = 1  # Critical if expiring within 1 day
    auto_refresh: bool = False  # Auto-refresh if source browser available
    source_browser: Optional[str] = None  # e.g., "firefox", "chrome"
    source_profile: Optional[str] = None  # e.g., "default", "Profile 1"
    domains: Optional[str] = None  # comma-separated domains to filter
    # Multi-browser fallback: try these browsers in order if primary fails
    fallback_browsers: List[str] = field(default_factory=list)
    # WebSocket notification callback
    notify_ws: Optional[Callable[[Dict], Awaitable[None]]] = None


@dataclass
class CookieExpiryInfo:
    """Info about cookie expiry status."""
    total_cookies: int
    expired_count: int
    expiring_soon_count: int  # within warning_days
    critical_count: int  # within critical_days
    next_expiry_epoch: Optional[float]
    next_expiry_human: Optional[str]


class SessionRefresher:
    """
    Monitors session cookie expiry and triggers re-export when needed.

    During proxy operation:
    1. Periodically checks cookie expiry status
    2. Logs warnings when cookies are expiring
    3. Optionally auto-refreshes from source browser (with multi-browser fallback)
    4. Hot-reloads session into the proxy
    5. Sends WebSocket notifications to connected clients
    """

    def __init__(
        self,
        session: Dict,
        config: Optional[RefreshConfig] = None,
        on_refresh: Optional[Callable[[Dict], Awaitable[None]]] = None,
    ):
        self.session = session
        self.config = config or RefreshConfig()
        self.on_refresh = on_refresh
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_check = 0
        self._last_status: Optional[CookieExpiryInfo] = None
        self._ws_clients: Set[asyncio.Queue] = set()

    def check_expiry(self) -> CookieExpiryInfo:
        """Check cookie expiry status without triggering any action."""
        cookies = self.session.get("cookies", [])
        now = time.time()

        expired = 0
        expiring_soon = 0
        critical = 0
        next_expiry = None

        warning_threshold = now + (self.config.expiry_warning_days * 86400)
        critical_threshold = now + (self.config.expiry_critical_days * 86400)

        for cookie in cookies:
            expires = cookie.get("expires", 0)
            if not expires or expires <= 0:
                continue  # Session cookie, no expiry

            # Handle Firefox millisecond format
            exp = float(expires)
            if exp > 1262304000000:
                exp = exp / 1000

            if exp < now:
                expired += 1
            elif exp < critical_threshold:
                critical += 1
            elif exp < warning_threshold:
                expiring_soon += 1

            # Track next expiry
            if exp > now and (next_expiry is None or exp < next_expiry):
                next_expiry = exp

        # Format human-readable next expiry
        next_expiry_human = None
        if next_expiry:
            remaining = next_expiry - now
            if remaining < 3600:
                next_expiry_human = f"{int(remaining / 60)} minutes"
            elif remaining < 86400:
                next_expiry_human = f"{int(remaining / 3600)} hours"
            else:
                next_expiry_human = f"{int(remaining / 86400)} days"

        return CookieExpiryInfo(
            total_cookies=len(cookies),
            expired_count=expired,
            expiring_soon_count=expiring_soon,
            critical_count=critical,
            next_expiry_epoch=next_expiry,
            next_expiry_human=next_expiry_human,
        )

    async def start(self):
        """Start the auto-refresh monitor."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Session auto-refresh monitor started")

    async def stop(self):
        """Stop the auto-refresh monitor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Session auto-refresh monitor stopped")

    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                await asyncio.sleep(self.config.check_interval)

                status = self.check_expiry()
                self._last_check = time.time()
                self._last_status = status

                # Log warnings
                if status.expired_count > 0:
                    logger.warning(
                        f"Session has {status.expired_count} expired cookies "
                        f"(of {status.total_cookies} total)"
                    )
                    await self._notify_ws_clients({
                        "type": "cookies_expired",
                        "expired_count": status.expired_count,
                        "total": status.total_cookies,
                        "timestamp": time.time(),
                    })

                if status.critical_count > 0:
                    logger.warning(
                        f"Session has {status.critical_count} cookies expiring within "
                        f"{self.config.expiry_critical_days} day(s)"
                    )
                    if status.next_expiry_human:
                        logger.warning(f"Next expiry: {status.next_expiry_human}")

                    await self._notify_ws_clients({
                        "type": "cookies_critical",
                        "critical_count": status.critical_count,
                        "next_expiry": status.next_expiry_human,
                        "timestamp": time.time(),
                    })

                elif status.expiring_soon_count > 0:
                    logger.info(
                        f"Session has {status.expiring_soon_count} cookies expiring within "
                        f"{self.config.expiry_warning_days} days"
                    )

                # Auto-refresh if enabled and critical
                if (
                    self.config.auto_refresh
                    and self.config.source_browser
                    and (status.expired_count > 0 or status.critical_count > 0)
                ):
                    await self._attempt_refresh()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Session refresh check failed: {e}")
                await asyncio.sleep(60)

    async def _attempt_refresh(self):
        """Attempt to re-export session from source browser with multi-browser fallback."""
        from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery
        from tokenade.core.importer.cookie_extractor import CookieExtractor
        from tokenade.core.importer.session_packager import SessionPackager

        # Build list of browsers to try: primary + fallbacks
        browsers_to_try = []
        if self.config.source_browser:
            browsers_to_try.append(
                (self.config.source_browser, self.config.source_profile)
            )
        for fb in self.config.fallback_browsers:
            browsers_to_try.append((fb, None))

        if not browsers_to_try:
            logger.warning("No source browser configured for auto-refresh")
            return

        discovery = BrowserProfileDiscovery()
        packager = SessionPackager()

        for browser_name, profile_name in browsers_to_try:
            try:
                logger.info(
                    f"Attempting auto-refresh from {browser_name} "
                    f"profile '{profile_name or 'default'}'"
                )

                # Discover browser profile path
                profiles = discovery.discover_all()
                all_profiles = []
                for browser_profiles in profiles.values():
                    all_profiles.extend(browser_profiles)

                matching = [p for p in all_profiles if p.browser == browser_name]
                if profile_name:
                    matching = [p for p in matching if p.name == profile_name]

                if not matching:
                    logger.warning(f"No profile found for {browser_name}")
                    continue

                browser_path = str(matching[0].path)

                # Extract cookies from source browser
                extractor = CookieExtractor(browser_path, browser=browser_name)
                cookies = extractor.extract(site_filter=None)

                if not cookies:
                    logger.warning(f"No cookies extracted from {browser_name}")
                    continue

                # Filter by domains if specified
                if self.config.domains:
                    domain_list = [d.strip().lower() for d in self.config.domains.split(",")]
                    cookies = [
                        c for c in cookies
                        if any(d in c.get("domain", "").lower() for d in domain_list)
                    ]

                if not cookies:
                    logger.warning(f"No matching cookies found in {browser_name} after domain filtering")
                    continue

                # Create new session package
                new_session = packager.package(
                    cookies=cookies,
                    browser=browser_name,
                    profile=profile_name or matching[0].name,
                )

                # Preserve local storage from original session if present
                if self.session.get("local_storage"):
                    new_session["local_storage"] = self.session["local_storage"]

                # Update session
                self.session.update(new_session)

                logger.info(f"Session refreshed from {browser_name}: {len(cookies)} cookies")

                # Send WebSocket notification
                await self._notify_ws_clients({
                    "type": "session_refreshed",
                    "source_browser": browser_name,
                    "cookies_count": len(cookies),
                    "timestamp": time.time(),
                })

                # Callback for proxy to hot-reload
                if self.on_refresh:
                    await self.on_refresh(new_session)

                return  # Success, stop trying other browsers

            except Exception as e:
                logger.warning(f"Auto-refresh from {browser_name} failed: {e}")
                continue

        # All browsers failed
        logger.error("Auto-refresh failed: all browsers exhausted")
        await self._notify_ws_clients({
            "type": "refresh_failed",
            "error": "all browsers exhausted",
            "timestamp": time.time(),
        })

    def update_session(self, session: Dict):
        """Update the session data (e.g., after manual re-export)."""
        self.session = session
        self._last_status = None  # Reset cached status
        logger.info("Session data updated")

    def register_ws_client(self) -> asyncio.Queue:
        """Register a WebSocket client to receive refresh notifications."""
        queue: asyncio.Queue = asyncio.Queue()
        self._ws_clients.add(queue)
        logger.debug(f"WebSocket client registered ({len(self._ws_clients)} total)")
        return queue

    def unregister_ws_client(self, queue: asyncio.Queue):
        """Unregister a WebSocket client."""
        self._ws_clients.discard(queue)
        logger.debug(f"WebSocket client unregistered ({len(self._ws_clients)} total)")

    async def _notify_ws_clients(self, event: Dict):
        """Send notification to all connected WebSocket clients."""
        for queue in list(self._ws_clients):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("WebSocket client queue full, dropping notification")

    def get_status(self) -> Dict:
        """Get current refresh status as dict."""
        status = self.check_expiry()
        return {
            "total_cookies": status.total_cookies,
            "expired_count": status.expired_count,
            "expiring_soon_count": status.expiring_soon_count,
            "critical_count": status.critical_count,
            "next_expiry_human": status.next_expiry_human,
            "auto_refresh_enabled": self.config.auto_refresh,
            "source_browser": self.config.source_browser,
            "fallback_browsers": self.config.fallback_browsers,
            "last_check": self._last_check,
        }
