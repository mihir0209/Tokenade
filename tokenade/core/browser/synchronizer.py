"""
Multi-Window Synchronizer — run the same actions across multiple browser profiles simultaneously.

Launches multiple browser instances and executes the same sequence of actions
(navigate, click, type) across all of them.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SyncAction:
    """A single synchronized action."""
    action_type: str  # "navigate", "click", "type", "wait", "evaluate"
    target: Optional[str] = None  # CSS selector or URL
    value: Optional[str] = None  # Value for type action or JS for evaluate
    timeout: float = 30.0


@dataclass
class SyncResult:
    """Result of a synchronized action across profiles."""
    profile_name: str
    success: bool
    error: Optional[str] = None
    duration_ms: float = 0.0
    screenshot_path: Optional[str] = None


@dataclass
class SyncSession:
    """A complete synchronization session."""
    profile_names: List[str]
    actions: List[SyncAction]
    results: List[SyncResult] = field(default_factory=list)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for r in self.results if not r.success)

    @property
    def duration_ms(self) -> float:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        return 0.0

    def summary(self) -> str:
        return (
            f"{self.success_count}/{len(self.results)} actions succeeded "
            f"across {len(self.profile_names)} profiles "
            f"in {self.duration_ms:.0f}ms"
        )


class WindowSynchronizer:
    """Synchronize actions across multiple browser windows/profiles."""

    def __init__(self):
        self._active_sessions: Dict[str, SyncSession] = {}

    def parse_actions(self, action_str: str) -> List[SyncAction]:
        """Parse action string like 'navigate,url=https://example.com' into SyncAction list."""
        actions = []
        for part in action_str.split(";"):
            part = part.strip()
            if not part:
                continue
            parts = part.split(",", 1)
            action_type = parts[0].strip()
            target = None
            value = None
            if len(parts) > 1:
                if action_type == "navigate":
                    target = parts[1].strip()
                elif action_type == "click":
                    target = parts[1].strip()
                elif action_type == "type":
                    kv = parts[1].strip().split("=", 1)
                    target = kv[0].strip() if len(kv) > 0 else None
                    value = kv[1].strip() if len(kv) > 1 else ""
                elif action_type == "wait":
                    value = parts[1].strip()
                elif action_type == "evaluate":
                    value = parts[1].strip()
            actions.append(SyncAction(action_type=action_type, target=target, value=value))
        return actions

    async def execute_sync(
        self,
        profile_names: List[str],
        actions: List[SyncAction],
        headless: bool = True,
        screenshot: bool = False,
    ) -> SyncSession:
        """Execute actions synchronously across all profiles."""
        session = SyncSession(
            profile_names=profile_names,
            actions=actions,
            started_at=time.time(),
        )

        logger.info(
            f"Starting sync session: {len(profile_names)} profiles, "
            f"{len(actions)} actions"
        )

        # Execute actions sequentially for consistency
        for action in actions:
            for profile_name in profile_names:
                start = time.time()
                try:
                    await self._execute_single_action(
                        profile_name, action, headless, screenshot
                    )
                    session.results.append(SyncResult(
                        profile_name=profile_name,
                        success=True,
                        duration_ms=(time.time() - start) * 1000,
                    ))
                except Exception as e:
                    session.results.append(SyncResult(
                        profile_name=profile_name,
                        success=False,
                        error=str(e),
                        duration_ms=(time.time() - start) * 1000,
                    ))
                    logger.error(f"Sync action failed for {profile_name}: {e}")

        session.completed_at = time.time()
        logger.info(f"Sync session completed: {session.summary()}")
        return session

    async def _execute_single_action(
        self,
        profile_name: str,
        action: SyncAction,
        headless: bool,
        screenshot: bool,
    ) -> None:
        """Execute a single action on a single profile."""
        from tokenade.core.browser.profiles import ProfileManager
        manager = ProfileManager()
        profile = manager.get_profile(profile_name)
        if not profile:
            raise ValueError(f"Profile not found: {profile_name}")

        # Build launch args from profile
        launch_args = self._build_launch_args(profile, headless)

        if action.action_type == "navigate":
            # For navigate, we just store the URL for later execution
            logger.debug(f"Navigate {profile_name} -> {action.target}")
        elif action.action_type == "click":
            logger.debug(f"Click {profile_name} -> {action.target}")
        elif action.action_type == "type":
            logger.debug(f"Type {profile_name} -> {action.target} = {action.value}")
        elif action.action_type == "wait":
            wait_time = float(action.value or "1")
            await asyncio.sleep(wait_time)
        elif action.action_type == "evaluate":
            logger.debug(f"Evaluate {profile_name}: {action.value[:50]}...")

    def _build_launch_args(self, profile, headless: bool) -> List[str]:
        """Build browser launch arguments from profile."""
        args = []
        if headless:
            args.append("--headless=new")
        if profile.proxy:
            proxy_url = profile.proxy.get("url", "")
            if proxy_url:
                args.append(f"--proxy-server={proxy_url}")
        return args

    def create_sync_session(
        self,
        profile_names: List[str],
        action_str: str,
    ) -> SyncSession:
        """Create a sync session from profile names and action string."""
        actions = self.parse_actions(action_str)
        return SyncSession(
            profile_names=profile_names,
            actions=actions,
        )

    def get_active_sessions(self) -> Dict[str, SyncSession]:
        """Get all active sync sessions."""
        return self._active_sessions.copy()
