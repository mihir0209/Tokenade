"""Tests for session vault - encrypted storage with ACLs and versioning."""

import json
import threading
import time
from pathlib import Path

import pytest

from tokenade.core.importer.session_vault import SessionVault, VaultEntry


@pytest.fixture
def vault_dir(tmp_path):
    return str(tmp_path / "vault")


@pytest.fixture
def vault(vault_dir):
    return SessionVault(vault_dir, max_versions=3)


@pytest.fixture
def sample_session():
    return {
        "version": "2.0",
        "site_name": "github",
        "auth_status": "logged_in",
        "created_at": "2026-01-01T00:00:00Z",
        "cookies": [
            {"name": "user_session", "value": "abc", "domain": ".github.com", "path": "/"},
            {"name": "_gh_sess", "value": "def", "domain": ".github.com", "path": "/"},
        ],
    }


@pytest.fixture
def session_file(tmp_path, sample_session):
    f = tmp_path / "test.tokenade"
    with open(f, "w") as fh:
        json.dump(sample_session, fh)
    return str(f)


@pytest.fixture
def alt_session():
    return {
        "version": "2.0",
        "site_name": "google",
        "auth_status": "logged_in",
        "created_at": "2026-06-01T00:00:00Z",
        "cookies": [
            {"name": "SID", "value": "xyz", "domain": ".google.com", "path": "/"},
        ],
    }


@pytest.fixture
def alt_session_file(tmp_path, alt_session):
    f = tmp_path / "alt.tokenade"
    with open(f, "w") as fh:
        json.dump(alt_session, fh)
    return str(f)


class TestAddAndRetrieve:
    def test_add_returns_session_id(self, vault, session_file):
        sid = vault.add(session_file)
        assert isinstance(sid, str)
        assert len(sid) > 0

    def test_add_custom_id(self, vault, session_file):
        sid = vault.add(session_file, session_id="my-session")
        assert sid == "my-session"

    def test_retrieve_session(self, vault, session_file):
        sid = vault.add(session_file)
        data = vault.get(sid)
        assert data is not None
        assert data["site_name"] == "github"
        assert len(data["cookies"]) == 2

    def test_retrieve_nonexistent(self, vault):
        assert vault.get("nonexistent") is None

    def test_add_with_tags(self, vault, session_file):
        sid = vault.add(session_file, tags=["production", "team-a"])
        entries = vault.list_sessions()
        assert len(entries) == 1
        assert "production" in entries[0].tags
        assert "team-a" in entries[0].tags

    def test_add_with_owner(self, vault, session_file):
        sid = vault.add(session_file, owner="alice")
        assert vault.check_permission(sid, "alice", "read")
        assert vault.check_permission(sid, "alice", "write")
        assert vault.check_permission(sid, "alice", "delete")

    def test_add_with_expiry(self, vault, session_file):
        sid = vault.add(session_file, expires_in_seconds=3600)
        entries = vault.list_sessions()
        assert entries[0].expires_at is not None


class TestRemove:
    def test_remove_existing(self, vault, session_file):
        sid = vault.add(session_file)
        assert vault.remove(sid) is True
        assert vault.get(sid) is None

    def test_remove_nonexistent(self, vault):
        assert vault.remove("nonexistent") is False

    def test_remove_cleans_up_file(self, vault, session_file):
        sid = vault.add(session_file)
        entry = vault.list_sessions()[0]
        file_path = Path(entry.file_path)
        assert file_path.exists()
        vault.remove(sid)
        assert not file_path.exists()

    def test_remove_cleans_up_versions(self, vault, session_file, tmp_path):
        sid = vault.add(session_file)
        # Create an update to generate a version
        updated = tmp_path / "updated.tokenade"
        updated_session = {
            "version": "2.0",
            "site_name": "github",
            "auth_status": "logged_in",
            "cookies": [{"name": "new", "value": "v", "domain": ".github.com", "path": "/"}],
        }
        with open(updated, "w") as f:
            json.dump(updated_session, f)
        vault.update(sid, str(updated))

        entries = vault.list_sessions()
        assert len(entries[0].versions) > 0

        vault.remove(sid)
        for vp in entries[0].versions:
            assert not Path(vp).exists()


class TestListFilters:
    def test_list_all(self, vault, session_file, alt_session_file):
        vault.add(session_file)
        vault.add(alt_session_file)
        entries = vault.list_sessions()
        assert len(entries) == 2

    def test_list_site_filter(self, vault, session_file, alt_session_file):
        vault.add(session_file)
        vault.add(alt_session_file)
        entries = vault.list_sessions(site_filter="github")
        assert len(entries) == 1
        assert entries[0].site_name == "github"

    def test_list_tag_filter(self, vault, session_file, alt_session_file):
        vault.add(session_file, tags=["prod"])
        vault.add(alt_session_file, tags=["staging"])
        entries = vault.list_sessions(tag_filter="prod")
        assert len(entries) == 1

    def test_list_sorted_by_updated(self, vault, session_file, alt_session_file):
        vault.add(session_file)
        time.sleep(0.05)
        vault.add(alt_session_file)
        entries = vault.list_sessions()
        # Most recent first
        assert entries[0].site_name == "google"

    def test_list_empty_vault(self, vault):
        entries = vault.list_sessions()
        assert entries == []


class TestUpdate:
    def test_update_creates_version(self, vault, session_file, tmp_path):
        sid = vault.add(session_file)
        updated = tmp_path / "updated.tokenade"
        updated_session = {
            "version": "2.0",
            "site_name": "github",
            "auth_status": "logged_in",
            "cookies": [{"name": "new_cookie", "value": "v", "domain": ".github.com", "path": "/"}],
        }
        with open(updated, "w") as f:
            json.dump(updated_session, f)
        result = vault.update(sid, str(updated))
        assert result is True

        entries = vault.list_sessions()
        assert len(entries[0].versions) == 1
        assert entries[0].cookie_count == 1

    def test_update_nonexistent(self, vault, session_file):
        assert vault.update("nonexistent", session_file) is False

    def test_update_retrieves_new_data(self, vault, session_file, tmp_path):
        sid = vault.add(session_file)
        updated = tmp_path / "updated.tokenade"
        updated_session = {
            "version": "2.0",
            "site_name": "github",
            "auth_status": "logged_in",
            "cookies": [{"name": "brand_new", "value": "v", "domain": ".github.com", "path": "/"}],
        }
        with open(updated, "w") as f:
            json.dump(updated_session, f)
        vault.update(sid, str(updated))

        data = vault.get(sid)
        assert data["cookies"][0]["name"] == "brand_new"

    def test_version_cleanup_max_versions(self, vault, session_file, tmp_path):
        sid = vault.add(session_file)
        for i in range(5):
            updated = tmp_path / f"update_{i}.tokenade"
            session = {
                "version": "2.0",
                "site_name": "github",
                "auth_status": "logged_in",
                "cookies": [
                    {"name": f"cookie_{i}", "value": "v", "domain": ".github.com", "path": "/"}
                ],
            }
            with open(updated, "w") as f:
                json.dump(session, f)
            vault.update(sid, str(updated))

        entries = vault.list_sessions()
        assert len(entries[0].versions) <= vault.max_versions


class TestACLs:
    def test_set_acl(self, vault, session_file):
        sid = vault.add(session_file)
        assert vault.set_acl(sid, "bob", ["read"]) is True
        assert vault.check_permission(sid, "bob", "read")
        assert not vault.check_permission(sid, "bob", "write")

    def test_set_acl_nonexistent(self, vault):
        assert vault.set_acl("nonexistent", "bob", ["read"]) is False

    def test_owner_has_all_permissions(self, vault, session_file):
        sid = vault.add(session_file, owner="alice")
        assert vault.check_permission(sid, "alice", "read")
        assert vault.check_permission(sid, "alice", "write")
        assert vault.check_permission(sid, "alice", "delete")
        # Owner does not get wildcard unless explicitly set
        assert not vault.check_permission(sid, "alice", "anything")

    def test_wildcard_permission(self, vault, session_file):
        sid = vault.add(session_file)
        vault.set_acl(sid, "admin", ["*"])
        assert vault.check_permission(sid, "admin", "read")
        assert vault.check_permission(sid, "admin", "delete")

    def test_no_permission(self, vault, session_file):
        sid = vault.add(session_file)
        assert not vault.check_permission(sid, "stranger", "read")

    def test_check_permission_nonexistent(self, vault):
        assert vault.check_permission("nonexistent", "user", "read") is False

    def test_multiple_users(self, vault, session_file):
        sid = vault.add(session_file)
        vault.set_acl(sid, "alice", ["read", "write"])
        vault.set_acl(sid, "bob", ["read"])
        assert vault.check_permission(sid, "alice", "write")
        assert not vault.check_permission(sid, "bob", "write")


class TestCleanupExpired:
    def test_cleanup_removes_expired(self, vault, session_file):
        sid = vault.add(session_file, expires_in_seconds=-3600)  # Already expired
        count = vault.cleanup_expired()
        assert count == 1
        assert vault.get(sid) is None

    def test_cleanup_keeps_valid(self, vault, session_file):
        sid = vault.add(session_file, expires_in_seconds=7200)
        count = vault.cleanup_expired()
        assert count == 0
        assert vault.get(sid) is not None

    def test_cleanup_no_expiry(self, vault, session_file):
        sid = vault.add(session_file)
        count = vault.cleanup_expired()
        assert count == 0
        assert vault.get(sid) is not None

    def test_cleanup_mixed(self, vault, session_file, alt_session_file):
        vault.add(session_file, expires_in_seconds=-3600)
        vault.add(alt_session_file, expires_in_seconds=7200)
        count = vault.cleanup_expired()
        assert count == 1


class TestStats:
    def test_stats_empty_vault(self, vault):
        stats = vault.get_stats()
        assert stats["total_sessions"] == 0
        assert stats["total_cookies"] == 0
        assert stats["sites"] == []
        assert stats["total_versions"] == 0
        assert stats["expired"] == 0

    def test_stats_with_sessions(self, vault, session_file, alt_session_file):
        vault.add(session_file)
        vault.add(alt_session_file)
        stats = vault.get_stats()
        assert stats["total_sessions"] == 2
        assert stats["total_cookies"] == 3
        assert set(stats["sites"]) == {"github", "google"}

    def test_stats_with_versions(self, vault, session_file, tmp_path):
        sid = vault.add(session_file)
        updated = tmp_path / "upd.tokenade"
        with open(updated, "w") as f:
            json.dump(
                {
                    "version": "2.0",
                    "site_name": "github",
                    "cookies": [{"name": "c", "value": "v", "domain": ".github.com", "path": "/"}],
                },
                f,
            )
        vault.update(sid, str(updated))
        stats = vault.get_stats()
        assert stats["total_versions"] == 1

    def test_stats_expired(self, vault, session_file):
        vault.add(session_file, expires_in_seconds=-100)
        stats = vault.get_stats()
        assert stats["expired"] == 1


class TestThreadSafety:
    def test_concurrent_adds(self, vault_dir, sample_session, tmp_path):
        results = []
        errors = []
        vault = SessionVault(vault_dir, max_versions=3)

        def add_session(i):
            try:
                f = tmp_path / f"s_{i}.tokenade"
                session = {**sample_session, "site_name": f"site_{i}"}
                with open(f, "w") as fh:
                    json.dump(session, fh)
                sid = vault.add(str(f))
                results.append(sid)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_session, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 10
        assert len(set(results)) == 10  # All unique
        assert vault.get_stats()["total_sessions"] == 10

    def test_concurrent_reads(self, vault, session_file):
        sid = vault.add(session_file)
        results = []

        def read_session():
            data = vault.get(sid)
            results.append(data is not None)

        threads = [threading.Thread(target=read_session) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(results)


class TestIndexPersistence:
    def test_index_survives_reload(self, vault_dir, session_file):
        v1 = SessionVault(vault_dir)
        sid = v1.add(session_file, tags=["test"])

        v2 = SessionVault(vault_dir)
        data = v2.get(sid)
        assert data is not None
        entries = v2.list_sessions()
        assert entries[0].tags == ["test"]

    def test_index_corrupt_file_handled(self, vault_dir):
        index_file = Path(vault_dir) / ".vault_index.json"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        with open(index_file, "w") as f:
            f.write("not valid json {{{")

        vault = SessionVault(vault_dir)
        assert vault._index == {}


class TestVaultEntryDataclass:
    def test_default_values(self):
        entry = VaultEntry(
            session_id="abc",
            site_name="test",
            created_at="2026-01-01",
            updated_at="2026-01-01",
            cookie_count=0,
            file_path="/tmp/test",
        )
        assert entry.versions == []
        assert entry.acls == {}
        assert entry.expires_at is None
        assert entry.tags == []
