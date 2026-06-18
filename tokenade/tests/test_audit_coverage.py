"""Tests for security audit module - coverage boost."""

import json
import os
import time
import tempfile
from unittest.mock import patch, MagicMock

from tokenade.core.security.audit import (
    AuditLogger,
    RoleManager,
    RoleBasedAccessControl,
    LDAPConfig,
    LDAPAuthenticator,
    ROLE_HIERARCHY,
    ROLE_PERMISSIONS,
)


class TestAuditLoggerCoverage:
    def test_init_default_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("os.path.expanduser", return_value=os.path.join(tmp, ".tokenade", "audit.log")):
                logger = AuditLogger()
                assert logger.log_path.parent.exists()

    def test_init_custom_path(self, tmp_path):
        log_path = tmp_path / "custom_audit.log"
        logger = AuditLogger(log_path=str(log_path))
        assert logger.log_path == log_path
        assert logger.log_path.parent.exists()

    def test_log_event(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))
        logger.log_event("session_export", user="alice", session_id="s1", details={"key": "val"}, source_ip="127.0.0.1")
        assert log_path.exists()
        with open(log_path) as f:
            line = f.readline()
            event = json.loads(line)
            assert event["event_type"] == "session_export"
            assert event["user"] == "alice"
            assert event["session_id"] == "s1"
            assert event["details"] == {"key": "val"}
            assert event["source_ip"] == "127.0.0.1"
            assert "timestamp" in event

    def test_log_event_exception(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))
        with patch("builtins.open", side_effect=PermissionError("denied")):
            logger.log_event("test_event")

    def test_query_events_all(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))
        for i in range(5):
            logger.log_event("test", user=f"user{i}")
        events = logger.query_events()
        assert len(events) == 5

    def test_query_events_by_type(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))
        logger.log_event("export")
        logger.log_event("import")
        logger.log_event("export")
        events = logger.query_events(event_type="export")
        assert len(events) == 2

    def test_query_events_since(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))
        time.time()
        logger.log_event("test")
        time.sleep(0.01)
        t2 = time.time()
        logger.log_event("test")
        events = logger.query_events(since=t2)
        assert len(events) == 1

    def test_query_events_until(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))
        t1 = time.time()
        logger.log_event("test")
        time.sleep(0.01)
        time.time()
        logger.log_event("test")
        events = logger.query_events(until=t1 + 0.001)
        assert len(events) == 1

    def test_query_events_limit(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))
        for _ in range(10):
            logger.log_event("test")
        events = logger.query_events(limit=3)
        assert len(events) == 3

    def test_query_events_no_file(self, tmp_path):
        log_path = tmp_path / "nonexistent.log"
        logger = AuditLogger(log_path=str(log_path))
        events = logger.query_events()
        assert events == []

    def test_query_events_invalid_json(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))
        with open(log_path, "w") as f:
            f.write("not json\n")
            f.write(json.dumps({"event_type": "ok", "timestamp": time.time()}) + "\n")
        events = logger.query_events()
        assert len(events) == 1

    def test_query_events_exception(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))
        logger.log_event("test")
        with patch("builtins.open", side_effect=PermissionError("denied")):
            events = logger.query_events()
            assert events == []

    def test_get_summary(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))
        logger.log_event("export")
        logger.log_event("export")
        logger.log_event("import")
        summary = logger.get_summary()
        assert summary["export"] == 2
        assert summary["import"] == 1

    def test_get_summary_with_since(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))
        logger.log_event("export")
        time.sleep(0.01)
        t = time.time()
        logger.log_event("import")
        summary = logger.get_summary(since=t)
        assert summary == {"import": 1}

    def test_get_summary_no_file(self, tmp_path):
        log_path = tmp_path / "nonexistent.log"
        logger = AuditLogger(log_path=str(log_path))
        summary = logger.get_summary()
        assert summary == {}

    def test_get_summary_invalid_json(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))
        with open(log_path, "w") as f:
            f.write("bad\n")
        summary = logger.get_summary()
        assert summary == {}

    def test_get_summary_exception(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))
        logger.log_event("test")
        with patch("builtins.open", side_effect=PermissionError("denied")):
            summary = logger.get_summary()
            assert summary == {}

    def test_rotate_not_needed(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))
        logger.log_event("test")
        result = logger.rotate(max_size_mb=100)
        assert result is None

    def test_rotate_needed(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))
        logger.log_event("test")
        result = logger.rotate(max_size_mb=0)
        assert result is not None
        assert not log_path.exists()

    def test_rotate_no_file(self, tmp_path):
        log_path = tmp_path / "nonexistent.log"
        logger = AuditLogger(log_path=str(log_path))
        result = logger.rotate()
        assert result is None

    def test_rotate_exception(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))
        logger.log_event("test")
        with patch("shutil.move", side_effect=PermissionError("denied")):
            result = logger.rotate(max_size_mb=0)
            assert result is None

    def test_log_event_empty_kwargs(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path=str(log_path))
        logger.log_event("simple_event")
        with open(log_path) as f:
            event = json.loads(f.readline())
            assert event["user"] is None
            assert event["session_id"] is None
            assert event["details"] == {}
            assert event["source_ip"] is None


class TestRoleManagerCoverage:
    def test_init_default_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("os.path.expanduser", return_value=os.path.join(tmp, ".tokenade", "rbac.json")):
                manager = RoleManager()
                assert manager.storage_path.parent.exists()

    def test_init_custom_path(self, tmp_path):
        storage = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage))
        assert manager.storage_path == storage

    def test_assign_role_valid(self, tmp_path):
        storage = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage))
        result = manager.assign_role("user1", "admin")
        assert result is True
        assert manager.get_user_role("user1") == "admin"

    def test_assign_role_invalid(self, tmp_path):
        storage = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage))
        result = manager.assign_role("user1", "superadmin")
        assert result is False

    def test_check_permission(self, tmp_path):
        storage = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage))
        manager.assign_role("user1", "viewer")
        assert manager.check_permission("user1", "view_share") is True
        assert manager.check_permission("user1", "start_proxy") is False

    def test_check_permission_unknown_user(self, tmp_path):
        storage = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage))
        assert manager.check_permission("unknown", "view_share") is False

    def test_list_users(self, tmp_path):
        storage = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage))
        manager.assign_role("u1", "admin")
        manager.assign_role("u2", "viewer")
        users = manager.list_users()
        assert len(users) == 2
        ids = {u["user_id"] for u in users}
        assert ids == {"u1", "u2"}

    def test_revoke_role(self, tmp_path):
        storage = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage))
        manager.assign_role("u1", "admin")
        result = manager.revoke_role("u1")
        assert result is True
        assert manager.get_user_role("u1") is None

    def test_revoke_role_nonexistent(self, tmp_path):
        storage = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage))
        result = manager.revoke_role("unknown")
        assert result is False

    def test_load_existing_storage(self, tmp_path):
        storage = tmp_path / "rbac.json"
        storage.write_text(json.dumps({"user1": "admin"}))
        manager = RoleManager(storage_path=str(storage))
        assert manager.get_user_role("user1") == "admin"

    def test_load_corrupt_storage(self, tmp_path):
        storage = tmp_path / "rbac.json"
        storage.write_text("not json {{{")
        manager = RoleManager(storage_path=str(storage))
        assert manager._users == {}

    def test_save_exception(self, tmp_path):
        storage = tmp_path / "rbac.json"
        manager = RoleManager(storage_path=str(storage))
        with patch("builtins.open", side_effect=PermissionError("denied")):
            manager._save()

    def test_load_exception(self, tmp_path):
        storage = tmp_path / "nonexistent.json"
        with patch("builtins.open", side_effect=PermissionError("denied")):
            manager = RoleManager(storage_path=str(storage))
            assert manager._users == {}

    def test_persistence(self, tmp_path):
        storage = tmp_path / "rbac.json"
        manager1 = RoleManager(storage_path=str(storage))
        manager1.assign_role("u1", "editor")
        manager2 = RoleManager(storage_path=str(storage))
        assert manager2.get_user_role("u1") == "editor"


class TestRoleBasedAccessControlCoverage:
    def test_grant_access(self, tmp_path):
        storage = tmp_path / "rbac.json"
        rbac = RoleBasedAccessControl(storage_path=str(storage))
        result = rbac.grant_access("user1", "admin", granted_by="superadmin")
        assert result is True

    def test_has_permission(self, tmp_path):
        storage = tmp_path / "rbac.json"
        rbac = RoleBasedAccessControl(storage_path=str(storage))
        rbac.grant_access("user1", "editor")
        assert rbac.has_permission("user1", "create_share") is True
        assert rbac.has_permission("user1", "start_proxy") is False

    def test_revoke_access(self, tmp_path):
        storage = tmp_path / "rbac.json"
        rbac = RoleBasedAccessControl(storage_path=str(storage))
        rbac.grant_access("user1", "viewer")
        result = rbac.revoke_access("user1", revoked_by="admin")
        assert result is True
        assert rbac.has_permission("user1", "view_share") is False

    def test_grant_access_invalid_role(self, tmp_path):
        storage = tmp_path / "rbac.json"
        rbac = RoleBasedAccessControl(storage_path=str(storage))
        result = rbac.grant_access("user1", "invalid_role")
        assert result is False

    def test_revoke_access_nonexistent(self, tmp_path):
        storage = tmp_path / "rbac.json"
        rbac = RoleBasedAccessControl(storage_path=str(storage))
        result = rbac.revoke_access("unknown")
        assert result is False

    def test_all_roles(self, tmp_path):
        storage = tmp_path / "rbac.json"
        rbac = RoleBasedAccessControl(storage_path=str(storage))
        for role in ROLE_HIERARCHY:
            rbac.grant_access(f"user_{role}", role)
        for role in ROLE_HIERARCHY:
            assert rbac.role_manager.get_user_role(f"user_{role}") == role


class TestLDAPConfig:
    def test_defaults(self):
        config = LDAPConfig(server="ldap.example.com")
        assert config.port == 389
        assert config.use_ssl is False
        assert config.bind_dn == ""
        assert config.bind_password == ""
        assert config.user_search_filter == "(uid={username})"

    def test_custom_values(self):
        config = LDAPConfig(
            server="ldap.corp.com", port=636, use_ssl=True,
            bind_dn="cn=admin", bind_password="secret",
            user_search_base="ou=users", user_search_filter="(cn={username})",
            group_search_base="ou=groups", group_search_filter="(member={user_dn})",
        )
        assert config.port == 636
        assert config.use_ssl is True


class TestLDAPAuthenticatorCoverage:
    def test_init(self):
        config = LDAPConfig(server="ldap.example.com")
        auth = LDAPAuthenticator(config)
        assert auth.config == config

    def test_authenticate_without_ldap3(self):
        config = LDAPConfig(server="ldap.example.com")
        auth = LDAPAuthenticator(config)
        auth._ldap3_available = False
        assert auth.authenticate("user", "pass") is False

    def test_get_user_groups_without_ldap3(self):
        config = LDAPConfig(server="ldap.example.com")
        auth = LDAPAuthenticator(config)
        auth._ldap3_available = False
        groups = auth.get_user_groups("user")
        assert groups == []

    def test_get_connection_without_ldap3(self):
        config = LDAPConfig(server="ldap.example.com")
        auth = LDAPAuthenticator(config)
        auth._ldap3_available = False
        conn = auth._get_connection()
        assert conn is None

    def test_check_group_membership_without_ldap3(self):
        config = LDAPConfig(server="ldap.example.com")
        auth = LDAPAuthenticator(config)
        auth._ldap3_available = False
        assert auth.check_group_membership("user", "admins") is False

    def test_check_ldap3_not_installed(self):
        config = LDAPConfig(server="ldap.example.com")
        with patch.dict("sys.modules", {"ldap3": None}):
            auth = LDAPAuthenticator(config)
            assert auth._ldap3_available is False

    def test_authenticate_exception(self):
        config = LDAPConfig(server="ldap.example.com")
        auth = LDAPAuthenticator(config)
        auth._ldap3_available = True
        with patch.dict("sys.modules", {"ldap3": MagicMock()}):
            with patch("ldap3.Server", side_effect=Exception("conn fail")):
                result = auth.authenticate("user", "pass")
                assert result is False

    def test_get_user_groups_exception(self):
        config = LDAPConfig(server="ldap.example.com")
        auth = LDAPAuthenticator(config)
        auth._ldap3_available = True
        with patch.dict("sys.modules", {"ldap3": MagicMock()}):
            with patch("ldap3.Server", side_effect=Exception("fail")):
                groups = auth.get_user_groups("user")
                assert groups == []

    def test_get_user_groups_no_entries(self):
        config = LDAPConfig(server="ldap.example.com")
        auth = LDAPAuthenticator(config)
        auth._ldap3_available = True
        mock_ldap3 = MagicMock()
        mock_conn = MagicMock()
        mock_conn.entries = []
        mock_ldap3.Connection.return_value = mock_conn
        mock_ldap3.ALL = "ALL"
        mock_ldap3.Server.return_value = MagicMock()
        with patch.dict("sys.modules", {"ldap3": mock_ldap3}):
            groups = auth.get_user_groups("user")
            assert groups == []

    def test_get_user_groups_with_entries(self):
        config = LDAPConfig(
            server="ldap.example.com",
            user_search_base="ou=users",
            user_search_filter="(uid={username})",
            group_search_base="ou=groups",
            group_search_filter="(member={user_dn})",
        )
        auth = LDAPAuthenticator(config)
        auth._ldap3_available = True

        mock_ldap3 = MagicMock()
        mock_conn = MagicMock()

        # First search returns user DN
        user_entry = MagicMock()
        user_entry.entry_dn = "cn=user1,ou=users"
        mock_conn.entries = [user_entry]

        # Second search returns groups
        group1 = MagicMock()
        group1.cn = "admins"
        group2 = MagicMock()
        group2.cn = "editors"

        call_count = [0]
        mock_conn.search

        def mock_search(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                mock_conn.entries = [user_entry]
            else:
                mock_conn.entries = [group1, group2]

        mock_conn.search = mock_search
        mock_ldap3.Connection.return_value = mock_conn
        mock_ldap3.ALL = "ALL"
        mock_ldap3.Server.return_value = MagicMock()

        with patch.dict("sys.modules", {"ldap3": mock_ldap3}):
            groups = auth.get_user_groups("user1")
            assert "admins" in groups
            assert "editors" in groups

    def test_authenticate_success(self):
        config = LDAPConfig(
            server="ldap.example.com",
            user_search_base="ou=users",
            user_search_filter="(uid={username})",
        )
        auth = LDAPAuthenticator(config)
        auth._ldap3_available = True

        mock_ldap3 = MagicMock()
        mock_conn = MagicMock()

        user_entry = MagicMock()
        user_entry.entry_dn = "cn=user1,ou=users"
        mock_conn.entries = [user_entry]

        call_count = [0]

        def mock_search(**kwargs):
            call_count[0] += 1
            mock_conn.entries = [user_entry]

        mock_conn.search = mock_search
        mock_ldap3.Connection.return_value = mock_conn
        mock_ldap3.ALL = "ALL"
        mock_ldap3.Server.return_value = MagicMock()

        with patch.dict("sys.modules", {"ldap3": mock_ldap3}):
            result = auth.authenticate("user1", "password123")
            assert result is True

    def test_authenticate_user_not_found(self):
        config = LDAPConfig(
            server="ldap.example.com",
            user_search_base="ou=users",
            user_search_filter="(uid={username})",
        )
        auth = LDAPAuthenticator(config)
        auth._ldap3_available = True

        mock_ldap3 = MagicMock()
        mock_conn = MagicMock()
        mock_conn.entries = []
        mock_ldap3.Connection.return_value = mock_conn
        mock_ldap3.ALL = "ALL"
        mock_ldap3.Server.return_value = MagicMock()

        with patch.dict("sys.modules", {"ldap3": mock_ldap3}):
            result = auth.authenticate("nobody", "pass")
            assert result is False

    def test_check_group_membership_in_group(self):
        config = LDAPConfig(server="ldap.example.com")
        auth = LDAPAuthenticator(config)
        auth._ldap3_available = False
        with patch.object(auth, "get_user_groups", return_value=["admins", "users"]):
            assert auth.check_group_membership("user1", "admins") is True

    def test_check_group_membership_not_in_group(self):
        config = LDAPConfig(server="ldap.example.com")
        auth = LDAPAuthenticator(config)
        auth._ldap3_available = False
        with patch.object(auth, "get_user_groups", return_value=["users"]):
            assert auth.check_group_membership("user1", "admins") is False

    def test_get_connection_exception(self):
        config = LDAPConfig(server="ldap.example.com")
        auth = LDAPAuthenticator(config)
        auth._ldap3_available = True
        mock_ldap3 = MagicMock()
        mock_ldap3.Server.side_effect = Exception("fail")
        mock_ldap3.ALL = "ALL"
        with patch.dict("sys.modules", {"ldap3": mock_ldap3}):
            conn = auth._get_connection()
            assert conn is None

    def test_role_hierarchy(self):
        assert ROLE_HIERARCHY == ["viewer", "editor", "admin"]

    def test_role_permissions(self):
        assert "view_share" in ROLE_PERMISSIONS["viewer"]
        assert "start_proxy" in ROLE_PERMISSIONS["admin"]
        assert "start_proxy" not in ROLE_PERMISSIONS["editor"]
