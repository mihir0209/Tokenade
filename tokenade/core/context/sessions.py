"""Sessions namespace for shared context.

Stores session data, health scores, and metadata.
Thread-safe for concurrent access.
"""

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class SessionsNamespace:
    """Namespace for session-related shared state.

    Stores:
    - Session data (Dict)
    - Health scores (float 0-100)
    - Metadata (site, created_at, updated_at, source)

    Thread-safe: all operations are locked.

    Example:
        sessions = SessionsNamespace()
        sessions.set("session-1", {"cookies": {...}, "site": "example.com"})
        sessions.set_health("session-1", 85.0)
        data = sessions.get("session-1")
    """

    def __init__(self):
        self._data: Dict[str, Dict[str, Any]] = {}
        self._health: Dict[str, float] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data.

        Args:
            session_id: The session identifier

        Returns:
            Session data dict, or None if not found
        """
        with self._lock:
            data = self._data.get(session_id)
            return dict(data) if data else None

    def set(self, session_id: str, data: Dict[str, Any]) -> None:
        """Set session data.

        Args:
            session_id: The session identifier
            data: Session data to store
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            self._data[session_id] = dict(data)
            # Update metadata
            if session_id not in self._metadata:
                self._metadata[session_id] = {
                    "created_at": now,
                    "updated_at": now,
                    "source": data.get("source", "unknown"),
                    "site": data.get("site", "unknown"),
                }
            else:
                self._metadata[session_id]["updated_at"] = now

    def delete(self, session_id: str) -> bool:
        """Delete session data.

        Args:
            session_id: The session identifier

        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            deleted = session_id in self._data
            self._data.pop(session_id, None)
            self._health.pop(session_id, None)
            self._metadata.pop(session_id, None)
            return deleted

    def list(self) -> List[str]:
        """List all session IDs.

        Returns:
            List of session identifiers
        """
        with self._lock:
            return list(self._data.keys())

    def exists(self, session_id: str) -> bool:
        """Check if a session exists.

        Args:
            session_id: The session identifier

        Returns:
            True if session exists
        """
        with self._lock:
            return session_id in self._data

    def get_health(self, session_id: str) -> Optional[float]:
        """Get session health score (0-100).

        Args:
            session_id: The session identifier

        Returns:
            Health score, or None if not set
        """
        with self._lock:
            return self._health.get(session_id)

    def set_health(self, session_id: str, score: float) -> None:
        """Set session health score.

        Args:
            session_id: The session identifier
            score: Health score (0-100)
        """
        if not 0 <= score <= 100:
            raise ValueError(f"Health score must be 0-100, got {score}")
        with self._lock:
            self._health[session_id] = score

    def get_metadata(self, session_id: str) -> Dict[str, Any]:
        """Get session metadata.

        Args:
            session_id: The session identifier

        Returns:
            Metadata dict with created_at, updated_at, source, site
        """
        with self._lock:
            meta = self._metadata.get(session_id, {})
            return dict(meta)

    def set_metadata(self, session_id: str, metadata: Dict[str, Any]) -> None:
        """Set session metadata.

        Args:
            session_id: The session identifier
            metadata: Metadata to store
        """
        with self._lock:
            self._metadata[session_id] = dict(metadata)

    def count(self) -> int:
        """Get the number of sessions.

        Returns:
            Number of sessions
        """
        with self._lock:
            return len(self._data)

    def clear(self) -> int:
        """Clear all session data.

        Returns:
            Number of sessions removed
        """
        with self._lock:
            count = len(self._data)
            self._data.clear()
            self._health.clear()
            self._metadata.clear()
            return count
