"""
Enterprise Security Features - Audit Logging, RBAC, and LDAP Authentication.

Features:
- Structured audit logging with JSONL format
- Role-Based Access Control for shared sessions
- LDAP/SSO authentication integration
- Thread-safe operations
- Configurable storage paths
"""

import json
import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Role hierarchy (higher index = more permissions)
ROLE_HIERARCHY = ["viewer", "editor", "admin"]

# Permissions per role
ROLE_PERMISSIONS = {
    "viewer": ["view_share"],
    "editor": ["view_share", "create_share", "revoke_share", "refresh_session"],
    "admin": ["view_share", "create_share", "revoke_share", "refresh_session", "start_proxy"],
}


class AuditLogger:
    """
    Structured audit logging for session operations.

    Stores audit logs in JSONL format (one JSON object per line) with
    thread-safe operations and rotation support.
    """

    def __init__(self, log_path: Optional[str] = None):
        """
        Initialize AuditLogger.

        Args:
            log_path: Path to audit log file. Defaults to ~/.tokenade/audit.log
        """
        if log_path is None:
            log_path = os.path.expanduser("~/.tokenade/audit.log")
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log_event(self, event_type: str, **kwargs) -> None:
        """
        Log an audit event.

        Args:
            event_type: Type of event (session_export, session_import, etc.)
            **kwargs: Additional fields (user, session_id, details, source_ip)
        """
        event = {
            "timestamp": time.time(),
            "event_type": event_type,
            "user": kwargs.get("user"),
            "session_id": kwargs.get("session_id"),
            "details": kwargs.get("details", {}),
            "source_ip": kwargs.get("source_ip"),
        }

        with self._lock:
            try:
                with open(self.log_path, "a") as f:
                    f.write(json.dumps(event) + "\n")
            except Exception as e:
                logger.error(f"Failed to write audit log: {e}")

    def query_events(
        self,
        event_type: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """
        Query audit events with optional filters.

        Args:
            event_type: Filter by event type
            since: Filter events after this timestamp
            until: Filter events before this timestamp
            limit: Maximum number of events to return

        Returns:
            List of matching event dictionaries
        """
        events = []

        with self._lock:
            try:
                if not self.log_path.exists():
                    return events

                with open(self.log_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        if event_type and event.get("event_type") != event_type:
                            continue
                        if since and event.get("timestamp", 0) < since:
                            continue
                        if until and event.get("timestamp", 0) > until:
                            continue

                        events.append(event)

                        if len(events) >= limit:
                            break
            except Exception as e:
                logger.error(f"Failed to query audit logs: {e}")

        return events

    def get_summary(self, since: Optional[float] = None) -> Dict[str, int]:
        """
        Get summary of events grouped by type.

        Args:
            since: Only count events after this timestamp

        Returns:
            Dictionary mapping event_type to count
        """
        summary: Dict[str, int] = {}

        with self._lock:
            try:
                if not self.log_path.exists():
                    return summary

                with open(self.log_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        if since and event.get("timestamp", 0) < since:
                            continue

                        event_type = event.get("event_type", "unknown")
                        summary[event_type] = summary.get(event_type, 0) + 1
            except Exception as e:
                logger.error(f"Failed to get audit summary: {e}")

        return summary

    def rotate(self, max_size_mb: int = 100) -> Optional[str]:
        """
        Rotate audit log when it exceeds max size.

        Archives the current log and creates a new one.

        Args:
            max_size_mb: Maximum log size in megabytes before rotation

        Returns:
            Path to archived log, or None if rotation wasn't needed
        """
        with self._lock:
            try:
                if not self.log_path.exists():
                    return None

                size_mb = self.log_path.stat().st_size / (1024 * 1024)
                if size_mb < max_size_mb:
                    return None

                timestamp = int(time.time())
                archive_path = self.log_path.with_suffix(f".{timestamp}.log")
                shutil.move(str(self.log_path), str(archive_path))
                logger.info(f"Rotated audit log to {archive_path}")
                return str(archive_path)
            except Exception as e:
                logger.error(f"Failed to rotate audit log: {e}")
                return None


class RoleManager:
    """
    Role-Based Access Control manager for shared sessions.

    Manages user roles and permissions with persistent JSON storage.
    """

    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize RoleManager.

        Args:
            storage_path: Path to RBAC storage file. Defaults to ~/.tokenade/rbac.json
        """
        if storage_path is None:
            storage_path = os.path.expanduser("~/.tokenade/rbac.json")
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._users: Dict[str, str] = self._load()

    def _load(self) -> Dict[str, str]:
        """Load user roles from storage."""
        try:
            if self.storage_path.exists():
                with open(self.storage_path, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load RBAC data: {e}")
        return {}

    def _save(self) -> None:
        """Save user roles to storage."""
        try:
            with open(self.storage_path, "w") as f:
                json.dump(self._users, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save RBAC data: {e}")

    def assign_role(self, user_id: str, role: str) -> bool:
        """
        Assign a role to a user.

        Args:
            user_id: User identifier
            role: Role to assign (admin, editor, viewer)

        Returns:
            True if role was assigned successfully
        """
        if role not in ROLE_HIERARCHY:
            logger.warning(f"Invalid role: {role}")
            return False

        with self._lock:
            self._users[user_id] = role
            self._save()
            logger.info(f"Assigned role '{role}' to user '{user_id}'")
            return True

    def check_permission(self, user_id: str, permission: str) -> bool:
        """
        Check if a user has a specific permission.

        Args:
            user_id: User identifier
            permission: Permission to check

        Returns:
            True if user has the permission
        """
        with self._lock:
            role = self._users.get(user_id)
            if role is None:
                return False
            return permission in ROLE_PERMISSIONS.get(role, [])

    def get_user_role(self, user_id: str) -> Optional[str]:
        """
        Get the role assigned to a user.

        Args:
            user_id: User identifier

        Returns:
            Role name or None if user has no role
        """
        with self._lock:
            return self._users.get(user_id)

    def list_users(self) -> List[Dict]:
        """
        List all users and their roles.

        Returns:
            List of dictionaries with user_id and role keys
        """
        with self._lock:
            return [{"user_id": uid, "role": role} for uid, role in self._users.items()]

    def revoke_role(self, user_id: str) -> bool:
        """
        Revoke a user's role.

        Args:
            user_id: User identifier

        Returns:
            True if role was revoked, False if user had no role
        """
        with self._lock:
            if user_id not in self._users:
                return False
            del self._users[user_id]
            self._save()
            logger.info(f"Revoked role from user '{user_id}'")
            return True


class RoleBasedAccessControl:
    """
    Role-Based Access Control for shared sessions.

    Convenience wrapper around RoleManager with validation.
    """

    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize RBAC system.

        Args:
            storage_path: Path to RBAC storage file
        """
        self.role_manager = RoleManager(storage_path)

    def grant_access(self, user_id: str, role: str, granted_by: Optional[str] = None) -> bool:
        """
        Grant access to a user with a specific role.

        Args:
            user_id: User to grant access to
            role: Role to assign
            granted_by: User who granted the access (for audit)

        Returns:
            True if access was granted
        """
        success = self.role_manager.assign_role(user_id, role)
        if success:
            logger.info(
                f"Access granted: user={user_id}, role={role}, granted_by={granted_by}"
            )
        return success

    def has_permission(self, user_id: str, permission: str) -> bool:
        """
        Check if user has a specific permission.

        Args:
            user_id: User identifier
            permission: Permission to check

        Returns:
            True if user has the permission
        """
        return self.role_manager.check_permission(user_id, permission)

    def revoke_access(self, user_id: str, revoked_by: Optional[str] = None) -> bool:
        """
        Revoke a user's access.

        Args:
            user_id: User to revoke access from
            revoked_by: User who revoked the access (for audit)

        Returns:
            True if access was revoked
        """
        success = self.role_manager.revoke_role(user_id)
        if success:
            logger.info(f"Access revoked: user={user_id}, revoked_by={revoked_by}")
        return success


@dataclass
class LDAPConfig:
    """LDAP connection configuration."""

    server: str
    port: int = 389
    use_ssl: bool = False
    bind_dn: str = ""
    bind_password: str = ""
    user_search_base: str = ""
    user_search_filter: str = "(uid={username})"
    group_search_base: str = ""
    group_search_filter: str = "(member={user_dn})"


class LDAPAuthenticator:
    """
    LDAP/SSO authentication integration.

    Provides LDAP bind authentication and group membership checks
    with graceful fallback when ldap3 is not installed.
    """

    def __init__(self, config: LDAPConfig):
        """
        Initialize LDAP authenticator.

        Args:
            config: LDAP connection configuration
        """
        self.config = config
        self._ldap3_available = self._check_ldap3()

    def _check_ldap3(self) -> bool:
        """Check if ldap3 library is available."""
        try:
            import ldap3  # noqa: F401
            return True
        except ImportError:
            logger.warning(
                "ldap3 library not installed. LDAP authentication unavailable. "
                "Install with: pip install ldap3"
            )
            return False

    def _get_connection(self):
        """Create an LDAP connection."""
        if not self._ldap3_available:
            return None

        try:
            from ldap3 import ALL, Connection, Server

            server = Server(
                self.config.server,
                port=self.config.port,
                use_ssl=self.config.use_ssl,
                get_info=ALL,
            )
            return Connection(
                server,
                user=self.config.bind_dn,
                password=self.config.bind_password,
                auto_bind=True,
            )
        except Exception as e:
            logger.error(f"Failed to create LDAP connection: {e}")
            return None

    def authenticate(self, username: str, password: str) -> bool:
        """
        Authenticate a user via LDAP bind.

        Args:
            username: Username to authenticate
            password: Password to verify

        Returns:
            True if authentication successful
        """
        if not self._ldap3_available:
            return False

        try:
            from ldap3 import ALL, Connection, Server

            server = Server(
                self.config.server,
                port=self.config.port,
                use_ssl=self.config.use_ssl,
                get_info=ALL,
            )

            # First, search for the user DN
            conn = Connection(
                server,
                user=self.config.bind_dn,
                password=self.config.bind_password,
                auto_bind=True,
            )

            search_filter = self.config.user_search_filter.format(username=username)
            conn.search(
                search_base=self.config.user_search_base,
                search_filter=search_filter,
                attributes=["dn"],
            )

            if not conn.entries:
                logger.warning(f"User not found: {username}")
                conn.unbind()
                return False

            user_dn = str(conn.entries[0].entry_dn)
            conn.unbind()

            # Try to bind as the user
            user_conn = Connection(
                server,
                user=user_dn,
                password=password,
                auto_bind=True,
            )
            user_conn.unbind()
            logger.info(f"LDAP authentication successful for user: {username}")
            return True

        except Exception as e:
            logger.error(f"LDAP authentication failed for user {username}: {e}")
            return False

    def get_user_groups(self, username: str) -> List[str]:
        """
        Get LDAP groups for a user.

        Args:
            username: Username to look up

        Returns:
            List of group names
        """
        if not self._ldap3_available:
            return []

        try:
            from ldap3 import ALL, Connection, Server

            conn = self._get_connection()
            if conn is None:
                return []

            # Get user DN first
            search_filter = self.config.user_search_filter.format(username=username)
            conn.search(
                search_base=self.config.user_search_base,
                search_filter=search_filter,
                attributes=["dn"],
            )

            if not conn.entries:
                conn.unbind()
                return []

            user_dn = str(conn.entries[0].entry_dn)

            # Search for groups
            group_filter = self.config.group_search_filter.format(user_dn=user_dn)
            conn.search(
                search_base=self.config.group_search_base,
                search_filter=group_filter,
                attributes=["cn"],
            )

            groups = [str(entry.cn) for entry in conn.entries]
            conn.unbind()
            return groups

        except Exception as e:
            logger.error(f"Failed to get groups for user {username}: {e}")
            return []

    def check_group_membership(self, username: str, group: str) -> bool:
        """
        Check if a user is a member of a specific LDAP group.

        Args:
            username: Username to check
            group: Group name to check membership of

        Returns:
            True if user is a member of the group
        """
        groups = self.get_user_groups(username)
        return group in groups
