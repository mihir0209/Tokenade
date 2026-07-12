"""Runtime namespace for shared context.

Stores transient runtime state: active proxy, solved CAPTCHAs,
refresh timestamps, and task state references.
Thread-safe for concurrent access.
"""

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class RuntimeNamespace:
    """Namespace for runtime-related shared state.

    Stores:
    - Active proxy
    - Solved CAPTCHAs (cached with expiry)
    - Refresh timestamps
    - Task state references

    Thread-safe: all operations are locked.

    Example:
        runtime = RuntimeNamespace()
        runtime.set_active_proxy({"host": "127.0.0.1", "port": 8080})
        runtime.set_solved_captcha("captcha-1", {"type": "recaptcha", "solution": "..."})
        proxy = runtime.get_active_proxy()
    """

    def __init__(self):
        self._active_proxy: Optional[Dict[str, Any]] = None
        self._solved_captchas: Dict[str, Dict[str, Any]] = {}
        self._refresh_timestamps: Dict[str, datetime] = {}
        self._task_refs: Dict[str, str] = {}  # task_id → plugin_name
        self._lock = threading.RLock()

    def get_active_proxy(self) -> Optional[Dict[str, Any]]:
        """Get the currently active proxy.

        Returns:
            Proxy dict, or None if no proxy is active
        """
        with self._lock:
            return dict(self._active_proxy) if self._active_proxy else None

    def set_active_proxy(self, proxy: Optional[Dict[str, Any]]) -> None:
        """Set the active proxy.

        Args:
            proxy: Proxy dict (host, port, type, etc.), or None to clear
        """
        with self._lock:
            self._active_proxy = dict(proxy) if proxy else None

    def get_solved_captcha(self, captcha_id: str) -> Optional[Dict[str, Any]]:
        """Get a solved CAPTCHA solution.

        Args:
            captcha_id: CAPTCHA identifier

        Returns:
            Solution dict, or None if not found or expired
        """
        with self._lock:
            solution = self._solved_captchas.get(captcha_id)
            if not solution:
                return None
            # Check expiry
            expires_at = solution.get("expires_at")
            if expires_at and datetime.now(timezone.utc) > expires_at:
                del self._solved_captchas[captcha_id]
                return None
            return dict(solution)

    def set_solved_captcha(
        self,
        captcha_id: str,
        solution: Dict[str, Any],
        ttl_seconds: int = 300,
    ) -> None:
        """Cache a solved CAPTCHA.

        Args:
            captcha_id: CAPTCHA identifier
            solution: Solution data
            ttl_seconds: Time-to-live in seconds (default 5 minutes)
        """
        now = datetime.now(timezone.utc)
        from datetime import timedelta

        with self._lock:
            self._solved_captchas[captcha_id] = {
                **solution,
                "solved_at": now,
                "expires_at": now + timedelta(seconds=ttl_seconds),
            }

    def clear_expired_captchas(self) -> int:
        """Remove expired CAPTCHA solutions.

        Returns:
            Number of solutions removed
        """
        now = datetime.now(timezone.utc)
        removed = 0
        with self._lock:
            to_remove = []
            for cap_id, solution in self._solved_captchas.items():
                expires_at = solution.get("expires_at")
                if expires_at and now > expires_at:
                    to_remove.append(cap_id)
            for cap_id in to_remove:
                del self._solved_captchas[cap_id]
                removed += 1
        return removed

    def get_refresh_timestamp(self, session_id: str) -> Optional[datetime]:
        """Get when a session was last refreshed.

        Args:
            session_id: Session identifier

        Returns:
            Timestamp, or None if never refreshed
        """
        with self._lock:
            return self._refresh_timestamps.get(session_id)

    def set_refresh_timestamp(
        self, session_id: str, timestamp: Optional[datetime] = None
    ) -> None:
        """Set the refresh timestamp for a session.

        Args:
            session_id: Session identifier
            timestamp: Refresh time (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        with self._lock:
            self._refresh_timestamps[session_id] = timestamp

    def clear_refresh_timestamp(self, session_id: str) -> bool:
        """Clear a session's refresh timestamp.

        Args:
            session_id: Session identifier

        Returns:
            True if cleared, False if not found
        """
        with self._lock:
            deleted = session_id in self._refresh_timestamps
            self._refresh_timestamps.pop(session_id, None)
            return deleted

    def set_task_ref(self, task_id: str, plugin_name: str) -> None:
        """Associate a task ID with a plugin name.

        Args:
            task_id: Task identifier
            plugin_name: Plugin that owns this task
        """
        with self._lock:
            self._task_refs[task_id] = plugin_name

    def get_task_ref(self, task_id: str) -> Optional[str]:
        """Get the plugin name for a task.

        Args:
            task_id: Task identifier

        Returns:
            Plugin name, or None if not found
        """
        with self._lock:
            return self._task_refs.get(task_id)

    def clear_task_ref(self, task_id: str) -> bool:
        """Clear a task reference.

        Args:
            task_id: Task identifier

        Returns:
            True if cleared, False if not found
        """
        with self._lock:
            deleted = task_id in self._task_refs
            self._task_refs.pop(task_id, None)
            return deleted

    def count_captchas(self) -> int:
        """Get the number of cached CAPTCHA solutions.

        Returns:
            Number of cached solutions
        """
        with self._lock:
            return len(self._solved_captchas)
