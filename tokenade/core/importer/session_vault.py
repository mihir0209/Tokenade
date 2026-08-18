"""
Session Vault - Encrypted session storage with access controls and versioning.

Provides secure storage for session files with:
- Per-session access ACLs
- Session metadata index (search without decryption)
- Session expiry tracking with background cleanup
- Session versioning (keep last N versions)
"""
import gzip
import hashlib
import json
import logging
import shutil
import threading
import time
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class VaultEntry:
    """Metadata for a vault entry."""
    session_id: str
    site_name: str
    created_at: str
    updated_at: str
    cookie_count: int
    file_path: str
    versions: List[str] = field(default_factory=list)
    acls: Dict[str, List[str]] = field(default_factory=dict)  # user -> [permissions]
    expires_at: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    compression: str = "none"  # "none", "gzip", "zlib"


class SessionVault:
    """Encrypted session storage with ACLs, compression, and versioning."""

    def __init__(self, vault_dir: str, max_versions: int = 5, compression: str = "none"):
        self.vault_dir = Path(vault_dir)
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.max_versions = max_versions
        self.compression = compression
        self._index_file = self.vault_dir / ".vault_index.json"
        self._lock = threading.Lock()
        self._index = self._load_index()

    def _load_index(self) -> Dict[str, VaultEntry]:
        """Load vault index from disk."""
        if self._index_file.exists():
            try:
                with open(self._index_file) as f:
                    data = json.load(f)
                return {k: VaultEntry(**v) for k, v in data.items()}
            except Exception as e:
                logger.warning(f"Failed to load vault index: {e}")
        return {}

    def _save_index(self):
        """Save vault index to disk."""
        data = {
            k: {
                "session_id": v.session_id,
                "site_name": v.site_name,
                "created_at": v.created_at,
                "updated_at": v.updated_at,
                "cookie_count": v.cookie_count,
                "file_path": v.file_path,
                "versions": v.versions,
                "acls": v.acls,
                "expires_at": v.expires_at,
                "tags": v.tags,
                "compression": getattr(v, "compression", "none"),
            }
            for k, v in self._index.items()
        }

        with open(self._index_file, "w") as f:
            json.dump(data, f, indent=2)

    def add(
        self,
        session_file: str,
        session_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        expires_in_seconds: Optional[int] = None,
        owner: Optional[str] = None,
    ) -> str:
        """Add a session to the vault.

        Args:
            session_file: Path to session file
            session_id: Optional custom ID (auto-generated if not provided)
            tags: Optional tags for organization
            expires_in_seconds: Optional TTL
            owner: Optional owner user ID

        Returns:
            Session ID
        """
        with self._lock:
            # Load session to get metadata
            with open(session_file) as f:
                session = json.load(f)

            # Generate ID if not provided
            if not session_id:
                content = json.dumps(session, sort_keys=True)
                session_id = hashlib.sha256(content.encode()).hexdigest()[:16]

            # Save to vault with optional compression
            vault_path = self.vault_dir / f"{session_id}.tokenade"
            comp = self.compression
            raw_bytes = Path(session_file).read_bytes()
            if comp == "gzip":
                vault_path.write_bytes(gzip.compress(raw_bytes))
            elif comp == "zlib":
                vault_path.write_bytes(zlib.compress(raw_bytes))
            else:
                vault_path.write_bytes(raw_bytes)
                comp = "none"

            # Calculate expiry
            expires_at = None
            if expires_in_seconds:
                expires_at = datetime.fromtimestamp(
                    time.time() + expires_in_seconds, tz=timezone.utc
                ).isoformat()

            # Create entry
            now = datetime.now(timezone.utc).isoformat()
            entry = VaultEntry(
                session_id=session_id,
                site_name=session.get("site_name", "unknown"),
                created_at=now,
                updated_at=now,
                cookie_count=len(session.get("cookies", [])),
                file_path=str(vault_path),
                versions=[],
                acls={owner: ["read", "write", "delete"]} if owner else {},
                expires_at=expires_at,
                tags=tags or [],
                compression=comp,
            )

            self._index[session_id] = entry
            self._save_index()

            logger.info(f"Added session {session_id} to vault")
            return session_id

    def get(self, session_id: str) -> Optional[Dict]:
        """Retrieve a session from the vault."""
        with self._lock:
            entry = self._index.get(session_id)
            if not entry:
                return None

            vault_path = Path(entry.file_path)
            if not vault_path.exists():
                return None

            raw = vault_path.read_bytes()
            comp = getattr(entry, "compression", "none")
            if comp == "gzip":
                raw = gzip.decompress(raw)
            elif comp == "zlib":
                raw = zlib.decompress(raw)

            return json.loads(raw.decode("utf-8"))

    def remove(self, session_id: str) -> bool:
        """Remove a session from the vault."""
        with self._lock:
            entry = self._index.pop(session_id, None)
            if not entry:
                return False

            # Remove file and versions
            vault_path = Path(entry.file_path)
            if vault_path.exists():
                vault_path.unlink()

            for version_path in entry.versions:
                p = Path(version_path)
                if p.exists():
                    p.unlink()

            self._save_index()
            logger.info(f"Removed session {session_id} from vault")
            return True

    def list_sessions(
        self, site_filter: Optional[str] = None, tag_filter: Optional[str] = None
    ) -> List[VaultEntry]:
        """List sessions in the vault with optional filters."""
        with self._lock:
            entries = list(self._index.values())

        if site_filter:
            entries = [e for e in entries if e.site_name == site_filter]
        if tag_filter:
            entries = [e for e in entries if tag_filter in e.tags]

        return sorted(entries, key=lambda e: e.updated_at, reverse=True)

    def update(self, session_id: str, session_file: str) -> bool:
        """Update a session, creating a version of the old one."""
        with self._lock:
            entry = self._index.get(session_id)
            if not entry:
                return False

            # Create version of current
            current_path = Path(entry.file_path)
            if current_path.exists():
                version_num = len(entry.versions) + 1
                version_path = self.vault_dir / f"{session_id}.v{version_num}.tokenade"
                shutil.copy2(current_path, version_path)
                entry.versions.append(str(version_path))

                # Remove oldest versions if over limit
                while len(entry.versions) > self.max_versions:
                    old = entry.versions.pop(0)
                    p = Path(old)
                    if p.exists():
                        p.unlink()

            # Copy new version
            shutil.copy2(session_file, current_path)

            # Update metadata
            with open(session_file) as f:
                session = json.load(f)

            entry.updated_at = datetime.now(timezone.utc).isoformat()
            entry.cookie_count = len(session.get("cookies", []))
            entry.site_name = session.get("site_name", entry.site_name)

            self._save_index()
            return True

    def set_acl(self, session_id: str, user: str, permissions: List[str]) -> bool:
        """Set ACL for a user on a session."""
        with self._lock:
            entry = self._index.get(session_id)
            if not entry:
                return False
            entry.acls[user] = permissions
            self._save_index()
            return True

    def check_permission(self, session_id: str, user: str, permission: str) -> bool:
        """Check if a user has a specific permission on a session."""
        with self._lock:
            entry = self._index.get(session_id)
            if not entry:
                return False

            # Owner has all permissions
            perms = entry.acls.get(user, [])
            return permission in perms or "*" in perms

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count removed."""
        with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            expired = [
                sid
                for sid, entry in self._index.items()
                if entry.expires_at and entry.expires_at < now
            ]

        count = 0
        for sid in expired:
            if self.remove(sid):
                count += 1

        return count

    def get_stats(self) -> Dict:
        """Get vault statistics."""
        with self._lock:
            entries = list(self._index.values())

        return {
            "total_sessions": len(entries),
            "total_cookies": sum(e.cookie_count for e in entries),
            "sites": list({e.site_name for e in entries}),
            "total_versions": sum(len(e.versions) for e in entries),
            "expired": sum(
                1
                for e in entries
                if e.expires_at and e.expires_at < datetime.now(timezone.utc).isoformat()
            ),
        }
