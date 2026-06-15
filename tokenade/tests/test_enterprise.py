"""
Comprehensive tests for enterprise security features.
Tests AuditLogger, RoleBasedAccessControl, and LDAPAuthenticator.
"""

import json
import os
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tokenade.core.security.audit import (
    AuditLogger,
    LDAPAuthenticator,
    LDAPConfig,
    RoleBasedAccessControl,
    RoleManager,
    ROLE_HIERARCHY,
    ROLE_PERMISSIONS,
)


class TestAuditLogger:
    """Tests for AuditLogger class."""

    def test_init_default_path(self, tmp_path):
        """Test AuditLogger creates default path when none specified."""
        with patch("os.path.expanduser") as mock_expand:
            mock_expand.return_value = str(tmp_path / ".tokenade" / "audit.log")
            logger = AuditLogger()
            assert logger.log_path.parent.exists()

    def test_init_custom_path(self, tmp_path):
        """Test AuditLogger with custom log path."""
        log_path = tmp_path / "custom_audit.log"
        logger = AuditLogger(log_path=str(log_path))
        assert logger.log_path == log_path

    def test_log_event_basic(self, tmp_path):
        """Test basic event logging."""
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_event("session_export", session_id="abc123")

        assert log_path.exists()
        with open(log_path, "r") as f:
            line = f.readline().strip()
            event = json.loads(line)

        assert event["event_type"] == "session_export"
        assert event["session_id"] == "abc123"
        assert event["timestamp"] > 0
        assert event["user"] is None
        assert event["details"] == {}

    def test_log_event_full_fields(self, tmp_path):
        """Test event logging with all fields."""
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_event(
            "session_share",
            user="admin@example.com",
            session_id="xyz789",
            details={"shared_with": ["user1@example.com"]},
            source_ip="192.168.1.100",
        )

        with open(log_path, "r") as f:
            event = json.loads(f.readline().strip())

        assert event["user"] == "admin@example.com"
        assert event["session_id"] == "xyz789"
        assert event["details"]["shared_with"] == ["user1@example.com"]
        assert event["source_ip"] == "192.168.1.100"

    def test_log_event_creates_parent_dirs(self, tmp_path):
        """Test that logging creates parent directories."""
        log_path = tmp_path / "nested" / "dir" / "audit.log"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_event("login", user="test@test.com")

        assert log_path.exists()

    def test_query_events_all(self, tmp_path):
        """Test querying all events."""
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_event("login", user="user1@test.com")
        logger.log_event("logout", user="user1@test.com")
        logger.log_event("session_export", user="user2@test.com")

        events = logger.query_events()
        assert len(events) == 3

    def test_query_events_by_type(self, tmp_path):
        """Test querying events filtered by type."""
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_event("login", user="user1@test.com")
        logger.log_event("logout", user="user1@test.com")
        logger.log_event("login", user="user2@test.com")

        events = logger.query_events(event_type="login")
        assert len(events) == 2
        assert all(e["event_type"] == "login" for e in events)

    def test_query_events_since(self, tmp_path):
        """Test querying events after a timestamp."""
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))

        now = time.time()
        logger.log_event("login")
        time.sleep(0.01)
        cutoff = time.time()
        time.sleep(0.01)
        logger.log_event("logout")

        events = logger.query_events(since=cutoff)
        assert len(events) == 1
        assert events[0]["event_type"] == "logout"

    def test_query_events_until(self, tmp_path):
        """Test querying events before a timestamp."""
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))

        now = time.time()
        logger.log_event("login")
        time.sleep(0.01)
        cutoff = time.time()
        time.sleep(0.01)
        logger.log_event("logout")

        events = logger.query_events(until=cutoff)
        assert len(events) == 1
        assert events[0]["event_type"] == "login"

    def test_query_events_limit(self, tmp_path):
        """Test querying events with limit."""
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))

        for i in range(10):
            logger.log_event(f"event_{i}")

        events = logger.query_events(limit=5)
        assert len(events) == 5

    def test_query_events_empty_file(self, tmp_path):
        """Test querying events when file doesn't exist."""
        log_path = tmp_path / "nonexistent.log"
        logger = AuditLogger(log_path=str(log_path))

        events = logger.query_events()
        assert events == []

    def test_get_summary(self, tmp_path):
        """Test getting event summary."""
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_event("login")
        logger.log_event("login")
        logger.log_event("logout")
        logger.log_event("session_export")

        summary = logger.get_summary()
        assert summary["login"] == 2
        assert summary["logout"] == 1
        assert summary["session_export"] == 1

    def test_get_summary_since(self, tmp_path):
        """Test summary with time filter."""
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_event("login")
        time.sleep(0.01)
        cutoff = time.time()
        time.sleep(0.01)
        logger.log_event("logout")
        logger.log_event("logout")

        summary = logger.get_summary(since=cutoff)
        assert summary.get("login", 0) == 0
        assert summary["logout"] == 2

    def test_get_summary_empty(self, tmp_path):
        """Test summary with no events."""
        log_path = tmp_path / "nonexistent.log"
        logger = AuditLogger(log_path=str(log_path))

        summary = logger.get_summary()
        assert summary == {}

    def test_rotate_needed(self, tmp_path):
        """Test log rotation when size exceeds threshold."""
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))

        # Write enough data to trigger rotation
        with open(log_path, "w") as f:
            f.write("x" * (1024 * 1024))  # 1 MB

        archive_path = logger.rotate(max_size_mb=0.5)
        assert archive_path is not None
        assert not log_path.exists()
        assert Path(archive_path).exists()

    def test_rotate_not_needed(self, tmp_path):
        """Test log rotation when size is under threshold."""
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_event("login")

        archive_path = logger.rotate(max_size_mb=100)
        assert archive_path is None
        assert log_path.exists()

    def test_rotate_no_file(self, tmp_path):
        """Test rotation when log file doesn't exist."""
        log_path = tmp_path / "nonexistent.log"
        logger = AuditLogger(log_path=str(log_path))

        archive_path = logger.rotate()
        assert archive_path is None

    def test_thread_safety(self, tmp_path):
        """Test concurrent event logging is thread-safe."""
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))

        def log_events(n):
            for i in range(n):
                logger.log_event(f"event_{threading.current_thread().name}_{i}")

        threads = [
            threading.Thread(target=log_events, args=(50,), name=f"thread_{i}")
            for i in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        events = logger.query_events(limit=500)
        assert len(events) == 250


class TestRoleManager:
    """Tests for RoleManager class."""

    def test_init_default_path(self, tmp_path):
        """Test RoleManager creates default path when none specified."""
        with patch("os.path.expanduser") as mock_expand:
            mock_expand.return_value = str(tmp_path / ".tokenade" / "rbac.json")
            manager = RoleManager()
            assert manager.storage_path.parent.exists()

    def test_init_custom_path(self, tmp_path):
        """Test RoleManager with custom storage path."""
        storage_path = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage_path))
        assert manager.storage_path == storage_path

    def test_assign_role_valid(self, tmp_path):
        """Test assigning a valid role."""
        storage_path = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage_path))

        result = manager.assign_role("user1@test.com", "admin")
        assert result is True
        assert manager.get_user_role("user1@test.com") == "admin"

    def test_assign_role_invalid(self, tmp_path):
        """Test assigning an invalid role fails."""
        storage_path = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage_path))

        result = manager.assign_role("user1@test.com", "superuser")
        assert result is False
        assert manager.get_user_role("user1@test.com") is None

    def test_assign_role_all_valid_roles(self, tmp_path):
        """Test all valid roles can be assigned."""
        storage_path = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage_path))

        for role in ROLE_HIERARCHY:
            result = manager.assign_role(f"user_{role}@test.com", role)
            assert result is True
            assert manager.get_user_role(f"user_{role}@test.com") == role

    def test_check_permission_admin(self, tmp_path):
        """Test admin has all permissions."""
        storage_path = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage_path))

        manager.assign_role("admin@test.com", "admin")

        assert manager.check_permission("admin@test.com", "create_share") is True
        assert manager.check_permission("admin@test.com", "view_share") is True
        assert manager.check_permission("admin@test.com", "revoke_share") is True
        assert manager.check_permission("admin@test.com", "refresh_session") is True
        assert manager.check_permission("admin@test.com", "start_proxy") is True

    def test_check_permission_editor(self, tmp_path):
        """Test editor permissions."""
        storage_path = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage_path))

        manager.assign_role("editor@test.com", "editor")

        assert manager.check_permission("editor@test.com", "create_share") is True
        assert manager.check_permission("editor@test.com", "view_share") is True
        assert manager.check_permission("editor@test.com", "revoke_share") is True
        assert manager.check_permission("editor@test.com", "refresh_session") is True
        assert manager.check_permission("editor@test.com", "start_proxy") is False

    def test_check_permission_viewer(self, tmp_path):
        """Test viewer permissions."""
        storage_path = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage_path))

        manager.assign_role("viewer@test.com", "viewer")

        assert manager.check_permission("viewer@test.com", "create_share") is False
        assert manager.check_permission("viewer@test.com", "view_share") is True
        assert manager.check_permission("viewer@test.com", "revoke_share") is False
        assert manager.check_permission("viewer@test.com", "refresh_session") is False
        assert manager.check_permission("viewer@test.com", "start_proxy") is False

    def test_check_permission_unknown_user(self, tmp_path):
        """Test permission check for unknown user."""
        storage_path = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage_path))

        assert manager.check_permission("unknown@test.com", "view_share") is False

    def test_list_users(self, tmp_path):
        """Test listing all users."""
        storage_path = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage_path))

        manager.assign_role("user1@test.com", "admin")
        manager.assign_role("user2@test.com", "viewer")

        users = manager.list_users()
        assert len(users) == 2

        user_ids = {u["user_id"] for u in users}
        assert "user1@test.com" in user_ids
        assert "user2@test.com" in user_ids

    def test_revoke_role(self, tmp_path):
        """Test revoking a role."""
        storage_path = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage_path))

        manager.assign_role("user@test.com", "admin")
        result = manager.revoke_role("user@test.com")

        assert result is True
        assert manager.get_user_role("user@test.com") is None

    def test_revoke_role_unknown_user(self, tmp_path):
        """Test revoking role from unknown user."""
        storage_path = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage_path))

        result = manager.revoke_role("unknown@test.com")
        assert result is False

    def test_persistence(self, tmp_path):
        """Test that roles persist to file."""
        storage_path = tmp_path / "rbac.json"

        # Create and assign role
        manager1 = RoleManager(storage_path=str(storage_path))
        manager1.assign_role("user@test.com", "editor")

        # Load from file
        manager2 = RoleManager(storage_path=str(storage_path))
        assert manager2.get_user_role("user@test.com") == "editor"

    def test_thread_safety(self, tmp_path):
        """Test concurrent role operations are thread-safe."""
        storage_path = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage_path))

        def assign_roles(role, count):
            for i in range(count):
                manager.assign_role(f"user_{role}_{i}@test.com", role)

        threads = [
            threading.Thread(target=assign_roles, args=("admin", 20)),
            threading.Thread(target=assign_roles, args=("editor", 20)),
            threading.Thread(target=assign_roles, args=("viewer", 20)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        users = manager.list_users()
        assert len(users) == 60


class TestRoleBasedAccessControl:
    """Tests for RoleBasedAccessControl class."""

    def test_grant_access(self, tmp_path):
        """Test granting access to a user."""
        storage_path = tmp_path / "rbac.json"
        rbac = RoleBasedAccessControl(storage_path=str(storage_path))

        result = rbac.grant_access("user@test.com", "editor", granted_by="admin@test.com")
        assert result is True
        assert rbac.role_manager.get_user_role("user@test.com") == "editor"

    def test_has_permission(self, tmp_path):
        """Test permission checking."""
        storage_path = tmp_path / "rbac.json"
        rbac = RoleBasedAccessControl(storage_path=str(storage_path))

        rbac.grant_access("user@test.com", "viewer")

        assert rbac.has_permission("user@test.com", "view_share") is True
        assert rbac.has_permission("user@test.com", "create_share") is False

    def test_revoke_access(self, tmp_path):
        """Test revoking access."""
        storage_path = tmp_path / "rbac.json"
        rbac = RoleBasedAccessControl(storage_path=str(storage_path))

        rbac.grant_access("user@test.com", "admin")
        result = rbac.revoke_access("user@test.com", revoked_by="superadmin@test.com")

        assert result is True
        assert rbac.has_permission("user@test.com", "view_share") is False


class TestLDAPConfig:
    """Tests for LDAPConfig dataclass."""

    def test_default_values(self):
        """Test LDAPConfig default values."""
        config = LDAPConfig(server="ldap.example.com")

        assert config.server == "ldap.example.com"
        assert config.port == 389
        assert config.use_ssl is False
        assert config.bind_dn == ""
        assert config.bind_password == ""
        assert config.user_search_base == ""
        assert config.user_search_filter == "(uid={username})"
        assert config.group_search_base == ""
        assert config.group_search_filter == "(member={user_dn})"

    def test_custom_values(self):
        """Test LDAPConfig with custom values."""
        config = LDAPConfig(
            server="ldap.corp.com",
            port=636,
            use_ssl=True,
            bind_dn="cn=admin,dc=corp,dc=com",
            bind_password="secret",
            user_search_base="ou=users,dc=corp,dc=com",
            user_search_filter="(mail={username})",
            group_search_base="ou=groups,dc=corp,dc=com",
            group_search_filter="(uniqueMember={user_dn})",
        )

        assert config.server == "ldap.corp.com"
        assert config.port == 636
        assert config.use_ssl is True
        assert config.bind_dn == "cn=admin,dc=corp,dc=com"
        assert config.user_search_filter == "(mail={username})"


class TestLDAPAuthenticator:
    """Tests for LDAPAuthenticator class."""

    @patch("tokenade.core.security.audit.LDAPAuthenticator._check_ldap3")
    def test_init_without_ldap3(self, mock_check):
        """Test initialization when ldap3 is not installed."""
        mock_check.return_value = False
        config = LDAPConfig(server="ldap.example.com")
        auth = LDAPAuthenticator(config)

        assert auth._ldap3_available is False

    @patch("tokenade.core.security.audit.LDAPAuthenticator._check_ldap3")
    def test_authenticate_without_ldap3(self, mock_check):
        """Test authentication returns False when ldap3 is not installed."""
        mock_check.return_value = False
        config = LDAPConfig(server="ldap.example.com")
        auth = LDAPAuthenticator(config)

        result = auth.authenticate("user", "password")
        assert result is False

    @patch("tokenade.core.security.audit.LDAPAuthenticator._check_ldap3")
    def test_get_groups_without_ldap3(self, mock_check):
        """Test getting groups returns empty list when ldap3 is not installed."""
        mock_check.return_value = False
        config = LDAPConfig(server="ldap.example.com")
        auth = LDAPAuthenticator(config)

        groups = auth.get_user_groups("user")
        assert groups == []

    @patch("tokenade.core.security.audit.LDAPAuthenticator._check_ldap3")
    def test_check_group_without_ldap3(self, mock_check):
        """Test group check returns False when ldap3 is not installed."""
        mock_check.return_value = False
        config = LDAPConfig(server="ldap.example.com")
        auth = LDAPAuthenticator(config)

        result = auth.check_group_membership("user", "group")
        assert result is False

    @patch("tokenade.core.security.audit.LDAPAuthenticator._check_ldap3")
    @patch("tokenade.core.security.audit.LDAPAuthenticator._get_connection")
    def test_authenticate_success(self, mock_get_conn, mock_check):
        """Test successful LDAP authentication."""
        mock_check.return_value = True

        # Mock connection
        mock_conn = MagicMock()
        mock_entry = MagicMock()
        mock_entry.entry_dn = "cn=user,ou=users,dc=example,dc=com"
        mock_conn.entries = [mock_entry]
        mock_get_conn.return_value = mock_conn

        config = LDAPConfig(
            server="ldap.example.com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="admin_pass",
            user_search_base="ou=users,dc=example,dc=com",
        )
        auth = LDAPAuthenticator(config)

        # Mock ldap3 module
        mock_ldap3 = MagicMock()
        mock_server = MagicMock()
        mock_ldap3.Server.return_value = mock_server
        mock_ldap3.ALL = "ALL"
        mock_ldap3.Connection.return_value = mock_conn

        with patch.dict("sys.modules", {"ldap3": mock_ldap3}):
            with patch("ldap3.Connection", return_value=mock_conn):
                with patch("ldap3.Server", return_value=mock_server):
                    with patch("ldap3.ALL", "ALL"):
                        result = auth.authenticate("user", "password")

        assert result is True

    @patch("tokenade.core.security.audit.LDAPAuthenticator._check_ldap3")
    def test_authenticate_connection_failure(self, mock_check):
        """Test authentication fails on connection error."""
        mock_check.return_value = True

        config = LDAPConfig(server="ldap.example.com")
        auth = LDAPAuthenticator(config)

        mock_ldap3 = MagicMock()
        mock_ldap3.Server.side_effect = Exception("Connection failed")
        mock_ldap3.ALL = "ALL"

        with patch.dict("sys.modules", {"ldap3": mock_ldap3}):
            result = auth.authenticate("user", "password")

        assert result is False

    @patch("tokenade.core.security.audit.LDAPAuthenticator._check_ldap3")
    def test_get_user_groups_success(self, mock_check):
        """Test getting user groups successfully."""
        mock_check.return_value = True

        # Create mock entry with proper string representation
        class MockEntry:
            def __init__(self, dn=None, cn=None):
                self.entry_dn = dn
                self.cn = cn
            def __str__(self):
                return self.cn or ""

        # Mock connection for bind
        mock_conn = MagicMock()
        mock_conn.entries = [MockEntry(dn="cn=user,ou=users,dc=example,dc=com")]

        # Create group entries
        group1 = MockEntry(cn="admins")
        group2 = MockEntry(cn="developers")

        # First search returns user DN, second search returns groups
        def mock_search(**kwargs):
            if "cn" in kwargs.get("search_filter", ""):
                mock_conn.entries = [group1, group2]
            return True

        mock_conn.search.side_effect = mock_search
        mock_conn.entries = [MockEntry(dn="cn=user,ou=users,dc=example,dc=com")]

        mock_ldap3 = MagicMock()
        mock_ldap3.ALL = "ALL"
        mock_ldap3.Connection.return_value = mock_conn
        mock_ldap3.Server.return_value = MagicMock()

        config = LDAPConfig(
            server="ldap.example.com",
            user_search_base="ou=users,dc=example,dc=com",
            group_search_base="ou=groups,dc=example,dc=com",
        )
        auth = LDAPAuthenticator(config)

        with patch.dict("sys.modules", {"ldap3": mock_ldap3}):
            groups = auth.get_user_groups("user")

        assert groups == ["admins", "developers"]

    @patch("tokenade.core.security.audit.LDAPAuthenticator._check_ldap3")
    def test_check_group_membership_true(self, mock_check):
        """Test checking group membership returns True."""
        mock_check.return_value = True

        # Create mock entry with proper string representation
        class MockEntry:
            def __init__(self, dn=None, cn=None):
                self.entry_dn = dn
                self.cn = cn
            def __str__(self):
                return self.cn or ""

        # Mock connection
        mock_conn = MagicMock()
        mock_conn.entries = [MockEntry(dn="cn=user,ou=users,dc=example,dc=com")]

        # Create group entry
        group = MockEntry(cn="admins")

        # First search returns user DN, second search returns groups
        def mock_search(**kwargs):
            if "cn" in kwargs.get("search_filter", ""):
                mock_conn.entries = [group]
            return True

        mock_conn.search.side_effect = mock_search
        mock_conn.entries = [MockEntry(dn="cn=user,ou=users,dc=example,dc=com")]

        mock_ldap3 = MagicMock()
        mock_ldap3.ALL = "ALL"
        mock_ldap3.Connection.return_value = mock_conn
        mock_ldap3.Server.return_value = MagicMock()

        config = LDAPConfig(
            server="ldap.example.com",
            user_search_base="ou=users,dc=example,dc=com",
            group_search_base="ou=groups,dc=example,dc=com",
        )
        auth = LDAPAuthenticator(config)

        with patch.dict("sys.modules", {"ldap3": mock_ldap3}):
            result = auth.check_group_membership("user", "admins")

        assert result is True

    @patch("tokenade.core.security.audit.LDAPAuthenticator._check_ldap3")
    def test_check_group_membership_false(self, mock_check):
        """Test checking group membership returns False."""
        mock_check.return_value = True

        # Mock connection for bind
        mock_bind_conn = MagicMock()
        mock_bind_conn.entries = [MagicMock(entry_dn="cn=user,ou=users,dc=example,dc=com")]

        # Mock connection for group search (empty result)
        mock_group_conn = MagicMock()
        mock_group_conn.entries = []

        mock_ldap3 = MagicMock()
        mock_ldap3.ALL = "ALL"
        mock_ldap3.Connection.side_effect = [mock_bind_conn, mock_group_conn]
        mock_ldap3.Server.return_value = MagicMock()

        config = LDAPConfig(
            server="ldap.example.com",
            user_search_base="ou=users,dc=example,dc=com",
            group_search_base="ou=groups,dc=example,dc=com",
        )
        auth = LDAPAuthenticator(config)

        with patch.dict("sys.modules", {"ldap3": mock_ldap3}):
            result = auth.check_group_membership("user", "admins")

        assert result is False

    @patch("tokenade.core.security.audit.LDAPAuthenticator._check_ldap3")
    def test_authenticate_user_not_found(self, mock_check):
        """Test authentication fails when user not found."""
        mock_check.return_value = True

        config = LDAPConfig(
            server="ldap.example.com",
            user_search_base="ou=users,dc=example,dc=com",
        )
        auth = LDAPAuthenticator(config)

        # Mock connection that returns no entries
        mock_conn = MagicMock()
        mock_conn.entries = []

        mock_ldap3 = MagicMock()
        mock_ldap3.ALL = "ALL"
        mock_ldap3.Connection.return_value = mock_conn
        mock_ldap3.Server.return_value = MagicMock()

        with patch.dict("sys.modules", {"ldap3": mock_ldap3}):
            result = auth.authenticate("nonexistent", "password")

        assert result is False


class TestRoleHierarchy:
    """Tests for role hierarchy and permissions."""

    def test_role_hierarchy_order(self):
        """Test role hierarchy is correctly ordered."""
        assert ROLE_HIERARCHY.index("admin") > ROLE_HIERARCHY.index("editor")
        assert ROLE_HIERARCHY.index("editor") > ROLE_HIERARCHY.index("viewer")

    def test_admin_has_all_permissions(self):
        """Test admin role includes all permissions."""
        all_permissions = set()
        for perms in ROLE_PERMISSIONS.values():
            all_permissions.update(perms)

        assert set(ROLE_PERMISSIONS["admin"]) == all_permissions

    def test_viewer_has_view_only(self):
        """Test viewer has only view permission."""
        assert ROLE_PERMISSIONS["viewer"] == ["view_share"]

    def test_editor_cannot_start_proxy(self):
        """Test editor cannot start proxy."""
        assert "start_proxy" not in ROLE_PERMISSIONS["editor"]


class TestAuditEventTypes:
    """Tests for valid audit event types."""

    def test_session_export_event(self, tmp_path):
        """Test logging session export event."""
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_event("session_export", session_id="abc", details={"format": "json"})

        events = logger.query_events(event_type="session_export")
        assert len(events) == 1
        assert events[0]["details"]["format"] == "json"

    def test_session_import_event(self, tmp_path):
        """Test logging session import event."""
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_event("session_import", session_id="xyz", details={"source": "file"})

        events = logger.query_events(event_type="session_import")
        assert len(events) == 1

    def test_session_revoke_event(self, tmp_path):
        """Test logging session revoke event."""
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_event("session_revoke", user="admin@test.com", session_id="abc")

        events = logger.query_events(event_type="session_revoke")
        assert len(events) == 1
        assert events[0]["user"] == "admin@test.com"

    def test_proxy_start_event(self, tmp_path):
        """Test logging proxy start event."""
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_event("proxy_start", details={"port": 8080, "target": "http://example.com"})

        events = logger.query_events(event_type="proxy_start")
        assert len(events) == 1
        assert events[0]["details"]["port"] == 8080

    def test_login_logout_events(self, tmp_path):
        """Test login and logout events."""
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))

        logger.log_event("login", user="user@test.com", source_ip="10.0.0.1")
        logger.log_event("logout", user="user@test.com")

        events = logger.query_events()
        assert len(events) == 2
        assert events[0]["event_type"] == "login"
        assert events[1]["event_type"] == "logout"
