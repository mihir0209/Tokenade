"""
Session Versioning & Rollback for Tokenade.

Automatically versions sessions before refresh, supports rollback to
any previous version, and provides diff between versions.

Versions are stored in ~/.tokenade/versions/<session-name>/
Each version is a numbered .tokenade file (v1.tokenade, v2.tokenade, etc.)
"""
import json
import shutil
import logging
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

DEFAULT_VERSIONS_DIR = Path.home() / ".tokenade" / "versions"
MAX_VERSIONS_PER_SESSION = 10


@dataclass
class VersionInfo:
    """Metadata for a single session version."""
    version: int
    path: str
    created_at: str
    cookie_count: int = 0
    site_name: str = ""
    health_score: Optional[float] = None
    size_bytes: int = 0
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VersionInfo":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class SessionDiff:
    """Difference between two session versions."""
    version_a: int
    version_b: int
    cookies_added: List[Dict[str, Any]] = field(default_factory=list)
    cookies_removed: List[Dict[str, Any]] = field(default_factory=list)
    cookies_modified: List[Dict[str, Any]] = field(default_factory=list)
    cookies_unchanged: int = 0
    storage_changes: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_changes(self) -> int:
        return len(self.cookies_added) + len(self.cookies_removed) + len(self.cookies_modified)

    @property
    def has_changes(self) -> bool:
        return self.total_changes > 0


class SessionVersionManager:
    """Manages session file versions with auto-versioning and rollback."""

    def __init__(self, versions_dir: Optional[str] = None,
                 max_versions: int = MAX_VERSIONS_PER_SESSION):
        self.versions_dir = Path(versions_dir) if versions_dir else DEFAULT_VERSIONS_DIR
        self.max_versions = max_versions

    def _get_session_dir(self, session_path: str) -> Path:
        name = Path(session_path).stem
        return self.versions_dir / name

    def _get_metadata_path(self, session_path: str) -> Path:
        return self._get_session_dir(session_path) / "versions.json"

    def _load_metadata(self, session_path: str) -> List[VersionInfo]:
        meta_path = self._get_metadata_path(session_path)
        if not meta_path.exists():
            return []
        try:
            data = json.loads(meta_path.read_text())
            return [VersionInfo.from_dict(v) for v in data]
        except Exception as e:
            logger.error(f"Failed to load version metadata: {e}")
            return []

    def _save_metadata(self, session_path: str, versions: List[VersionInfo]):
        meta_path = self._get_metadata_path(session_path)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        data = [v.to_dict() for v in versions]
        meta_path.write_text(json.dumps(data, indent=2))

    def _get_session_info(self, session_path: str) -> Dict[str, Any]:
        try:
            with open(session_path) as f:
                session = json.load(f)
            return {
                "cookie_count": len(session.get("cookies", [])),
                "site_name": session.get("site_name", Path(session_path).stem),
                "health_score": session.get("metadata", {}).get("health_score"),
            }
        except Exception:
            return {"cookie_count": 0, "site_name": "", "health_score": None}

    def create_version(self, session_path: str, description: str = "") -> VersionInfo:
        """Create a new version of a session file."""
        session_path = str(Path(session_path).resolve())
        versions = self._load_metadata(session_path)
        next_version = len(versions) + 1

        session_dir = self._get_session_dir(session_path)
        session_dir.mkdir(parents=True, exist_ok=True)

        version_file = session_dir / f"v{next_version}.tokenade"
        shutil.copy2(session_path, version_file)

        info = self._get_session_info(session_path)

        version_info = VersionInfo(
            version=next_version,
            path=str(version_file),
            created_at=datetime.now(timezone.utc).isoformat(),
            cookie_count=info["cookie_count"],
            site_name=info["site_name"],
            health_score=info.get("health_score"),
            size_bytes=version_file.stat().st_size,
            description=description,
        )

        versions.append(version_info)
        self._save_metadata(session_path, versions)
        self._prune_versions(session_path, versions)

        logger.info(f"Created version {next_version} for {Path(session_path).name}")
        return version_info

    def list_versions(self, session_path: str) -> List[VersionInfo]:
        """List all versions for a session."""
        session_path = str(Path(session_path).resolve())
        return self._load_metadata(session_path)

    def rollback(self, session_path: str, version: int) -> bool:
        """Rollback a session to a specific version."""
        session_path = str(Path(session_path).resolve())
        versions = self._load_metadata(session_path)

        target = None
        for v in versions:
            if v.version == version:
                target = v
                break

        if not target:
            logger.error(f"Version {version} not found for {Path(session_path).name}")
            return False

        version_file = Path(target.path)
        if not version_file.exists():
            logger.error(f"Version file not found: {target.path}")
            return False

        self.create_version(session_path, description=f"auto before rollback to v{version}")
        shutil.copy2(version_file, session_path)
        logger.info(f"Rolled back {Path(session_path).name} to version {version}")
        return True

    def diff(self, session_path: str, version_a: int, version_b: int) -> SessionDiff:
        """Compare two versions of a session."""
        session_path = str(Path(session_path).resolve())
        versions = self._load_metadata(session_path)

        info_a = None
        info_b = None
        for v in versions:
            if v.version == version_a:
                info_a = v
            if v.version == version_b:
                info_b = v

        if not info_a or not info_b:
            return SessionDiff(version_a=version_a, version_b=version_b)

        try:
            data_a = json.loads(Path(info_a.path).read_text())
            data_b = json.loads(Path(info_b.path).read_text())
        except Exception as e:
            logger.error(f"Failed to load version files: {e}")
            return SessionDiff(version_a=version_a, version_b=version_b)

        cookies_a = {(c["name"], c["domain"]): c for c in data_a.get("cookies", [])}
        cookies_b = {(c["name"], c["domain"]): c for c in data_b.get("cookies", [])}

        keys_a = set(cookies_a.keys())
        keys_b = set(cookies_b.keys())

        added = [cookies_b[k] for k in keys_b - keys_a]
        removed = [cookies_a[k] for k in keys_a - keys_b]
        modified = []
        unchanged = 0

        for k in keys_a & keys_b:
            if cookies_a[k] != cookies_b[k]:
                modified.append({
                    "name": k[0], "domain": k[1],
                    "before": cookies_a[k], "after": cookies_b[k],
                })
            else:
                unchanged += 1

        storage_changes = {}
        for key in ("local_storage", "session_storage"):
            a_val = data_a.get(key)
            b_val = data_b.get(key)
            if a_val != b_val:
                storage_changes[key] = {"before": a_val, "after": b_val}

        return SessionDiff(
            version_a=version_a, version_b=version_b,
            cookies_added=added, cookies_removed=removed,
            cookies_modified=modified, cookies_unchanged=unchanged,
            storage_changes=storage_changes,
        )

    def delete_version(self, session_path: str, version: int) -> bool:
        """Delete a specific version."""
        session_path = str(Path(session_path).resolve())
        versions = self._load_metadata(session_path)

        target = None
        for v in versions:
            if v.version == version:
                target = v
                break

        if not target:
            return False

        version_file = Path(target.path)
        if version_file.exists():
            version_file.unlink()

        versions = [v for v in versions if v.version != version]
        self._save_metadata(session_path, versions)
        logger.info(f"Deleted version {version} for {Path(session_path).name}")
        return True

    def _prune_versions(self, session_path: str, versions: List[VersionInfo]):
        if len(versions) <= self.max_versions:
            return

        to_remove = versions[: len(versions) - self.max_versions]
        for v in to_remove:
            version_file = Path(v.path)
            if version_file.exists():
                version_file.unlink()

        remaining = versions[len(to_remove):]
        self._save_metadata(session_path, remaining)
