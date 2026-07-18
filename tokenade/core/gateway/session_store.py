"""Context-neutral loading of sanitized session records for gateway routing."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from tokenade.core.refresh.health_checker import SessionHealthChecker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionRecord:
    """Sanitized metadata for one routable session."""

    id: str
    path: str
    site_name: str = "unknown"
    auth_status: str = "unknown"
    cookie_count: int = 0
    health_score: float = 0.0
    healthy: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a serializable record that contains no cookies or storage secrets."""
        return {
            "id": self.id,
            "path": self.path,
            "site_name": self.site_name,
            "auth_status": self.auth_status,
            "cookie_count": self.cookie_count,
            "health_score": self.health_score,
            "healthy": self.healthy,
            "metadata": dict(self.metadata),
        }


class SessionStore:
    """Load `.tokenade` files into sanitized records for routing."""

    def __init__(self, health_checker: Optional[SessionHealthChecker] = None):
        self.health_checker = health_checker or SessionHealthChecker()
        self.records: List[SessionRecord] = []

    def load_directory(self, sessions_dir: str | Path, pattern: str = "*.tokenade") -> List[SessionRecord]:
        """Load session records from a directory using a glob pattern."""
        directory = Path(sessions_dir).expanduser()
        if not directory.exists() or not directory.is_dir():
            raise FileNotFoundError(f"sessions directory not found: {sessions_dir}")

        paths = sorted(path for path in directory.glob(pattern) if path.is_file())
        self.records = self.load_paths(paths)
        return list(self.records)

    def load_paths(self, paths: Iterable[str | Path]) -> List[SessionRecord]:
        """Load explicit session paths, skipping malformed/unreadable files."""
        records: List[SessionRecord] = []
        for path in sorted((Path(item).expanduser() for item in paths), key=lambda item: str(item)):
            record = self.load_file(path)
            if record is not None:
                records.append(record)
        self.records = records
        return list(records)

    def load_file(self, path: str | Path) -> Optional[SessionRecord]:
        """Load one session file as a sanitized routing record."""
        session_path = Path(path).expanduser()
        try:
            with open(session_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load session %s: %s", session_path, exc)
            return None

        if not isinstance(data, dict):
            logger.warning("Failed to load session %s: expected JSON object", session_path)
            return None

        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        cookies = data.get("cookies") if isinstance(data.get("cookies"), list) else []
        health = self.health_checker.check_session(str(session_path))
        session_id = self._session_id(session_path, data, metadata)

        return SessionRecord(
            id=session_id,
            path=str(session_path.resolve()),
            site_name=self._string_value(data.get("site_name") or metadata.get("site_name"), "unknown"),
            auth_status=self._string_value(data.get("auth_status") or metadata.get("auth_status"), "unknown"),
            cookie_count=len(cookies),
            health_score=self._clamp_health(health.health_score),
            healthy=bool(health.healthy),
            metadata=self._sanitize_metadata(metadata),
        )

    def _session_id(self, path: Path, data: Dict[str, Any], metadata: Dict[str, Any]) -> str:
        explicit = metadata.get("session_id") or data.get("session_id")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()

        parts = [
            str(path.resolve()),
            self._string_value(data.get("created_at") or metadata.get("created_at"), ""),
            self._string_value(data.get("site_name") or metadata.get("site_name"), "unknown"),
        ]
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]

    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {
            "session_id",
            "site_name",
            "created_at",
            "extraction_method",
            "site_handler",
            "source_network",
            "browser_name",
            "browser_version",
        }
        sanitized = {key: metadata[key] for key in allowed if key in metadata}
        source_network = sanitized.get("source_network")
        if isinstance(source_network, dict) and source_network.get("raw_ip_stored") is not True:
            sanitized["source_network"] = {key: value for key, value in source_network.items() if key != "ip"}
        return sanitized

    def _string_value(self, value: Any, default: str) -> str:
        return value if isinstance(value, str) and value.strip() else default

    def _clamp_health(self, value: Any) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(score, 1.0))
