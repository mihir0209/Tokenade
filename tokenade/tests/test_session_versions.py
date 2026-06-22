"""Tests for session versioning (Phase 35)."""
import json
import pytest
from pathlib import Path

from tokenade.core.storage.session_versions import (
    SessionVersionManager, VersionInfo, SessionDiff,
)


def _make_session(tmp_path, name="github", cookies=None):
    """Create a sample session file."""
    if cookies is None:
        cookies = [
            {"name": "user_session", "value": "abc", "domain": ".github.com", "path": "/"},
            {"name": "logged_in", "value": "yes", "domain": ".github.com", "path": "/"},
        ]
    session = {
        "version": "1.0",
        "site_name": name,
        "cookies": cookies,
        "metadata": {"cookie_count": len(cookies)},
    }
    path = tmp_path / f"{name}.tokenade"
    path.write_text(json.dumps(session))
    return path


class TestVersionInfo:

    def test_to_dict(self):
        info = VersionInfo(version=1, path="/v1.tokenade", created_at="2026-01-01T00:00:00")
        data = info.to_dict()
        assert data["version"] == 1
        assert data["path"] == "/v1.tokenade"

    def test_from_dict(self):
        data = {"version": 2, "path": "/v2.tokenade", "created_at": "2026-01-01T00:00:00",
                "cookie_count": 10, "site_name": "github"}
        info = VersionInfo.from_dict(data)
        assert info.version == 2
        assert info.cookie_count == 10

    def test_from_dict_extra_keys(self):
        data = {"version": 1, "path": "/x", "created_at": "t", "unknown_key": True}
        info = VersionInfo.from_dict(data)
        assert info.version == 1


class TestSessionDiff:

    def test_no_changes(self):
        diff = SessionDiff(version_a=1, version_b=1, cookies_unchanged=5)
        assert diff.has_changes is False
        assert diff.total_changes == 0

    def test_has_changes(self):
        diff = SessionDiff(version_a=1, version_b=2, cookies_added=[{"name": "x"}])
        assert diff.has_changes is True
        assert diff.total_changes == 1

    def test_multiple_changes(self):
        diff = SessionDiff(
            version_a=1, version_b=2,
            cookies_added=[{"name": "a"}],
            cookies_removed=[{"name": "b"}],
            cookies_modified=[{"name": "c"}],
        )
        assert diff.total_changes == 3


class TestSessionVersionManager:

    def test_init_default(self):
        mgr = SessionVersionManager()
        assert mgr.max_versions == 10

    def test_init_custom(self):
        mgr = SessionVersionManager(versions_dir="/tmp/versions", max_versions=5)
        assert mgr.max_versions == 5

    def test_create_version(self, tmp_path):
        session = _make_session(tmp_path)
        mgr = SessionVersionManager(versions_dir=str(tmp_path / "versions"))
        version = mgr.create_version(str(session))
        assert version.version == 1
        assert version.cookie_count == 2
        assert version.site_name == "github"
        assert Path(version.path).exists()

    def test_create_multiple_versions(self, tmp_path):
        session = _make_session(tmp_path)
        mgr = SessionVersionManager(versions_dir=str(tmp_path / "versions"))
        v1 = mgr.create_version(str(session))
        v2 = mgr.create_version(str(session))
        assert v1.version == 1
        assert v2.version == 2

    def test_create_version_with_description(self, tmp_path):
        session = _make_session(tmp_path)
        mgr = SessionVersionManager(versions_dir=str(tmp_path / "versions"))
        v = mgr.create_version(str(session), description="before refresh")
        assert v.description == "before refresh"

    def test_list_versions_empty(self, tmp_path):
        session = _make_session(tmp_path)
        mgr = SessionVersionManager(versions_dir=str(tmp_path / "versions"))
        versions = mgr.list_versions(str(session))
        assert versions == []

    def test_list_versions(self, tmp_path):
        session = _make_session(tmp_path)
        mgr = SessionVersionManager(versions_dir=str(tmp_path / "versions"))
        mgr.create_version(str(session))
        mgr.create_version(str(session))
        versions = mgr.list_versions(str(session))
        assert len(versions) == 2

    def test_rollback(self, tmp_path):
        session = _make_session(tmp_path)
        mgr = SessionVersionManager(versions_dir=str(tmp_path / "versions"))

        # Create v1
        mgr.create_version(str(session))

        # Modify session
        data = json.loads(session.read_text())
        data["cookies"].append({"name": "new", "value": "1", "domain": ".github.com", "path": "/"})
        session.write_text(json.dumps(data))

        # Create v2
        mgr.create_version(str(session))

        # Rollback to v1
        assert mgr.rollback(str(session), 1) is True

        # Verify rollback
        restored = json.loads(session.read_text())
        assert len(restored["cookies"]) == 2  # Original 2 cookies

    def test_rollback_nonexistent(self, tmp_path):
        session = _make_session(tmp_path)
        mgr = SessionVersionManager(versions_dir=str(tmp_path / "versions"))
        assert mgr.rollback(str(session), 99) is False

    def test_diff_no_changes(self, tmp_path):
        session = _make_session(tmp_path)
        mgr = SessionVersionManager(versions_dir=str(tmp_path / "versions"))
        mgr.create_version(str(session))
        mgr.create_version(str(session))
        diff = mgr.diff(str(session), 1, 2)
        assert diff.has_changes is False
        assert diff.cookies_unchanged == 2

    def test_diff_with_added(self, tmp_path):
        session = _make_session(tmp_path)
        mgr = SessionVersionManager(versions_dir=str(tmp_path / "versions"))
        mgr.create_version(str(session))

        # Add cookie
        data = json.loads(session.read_text())
        data["cookies"].append({"name": "new", "value": "1", "domain": ".github.com", "path": "/"})
        session.write_text(json.dumps(data))
        mgr.create_version(str(session))

        diff = mgr.diff(str(session), 1, 2)
        assert len(diff.cookies_added) == 1
        assert diff.cookies_added[0]["name"] == "new"

    def test_diff_with_removed(self, tmp_path):
        session = _make_session(tmp_path)
        mgr = SessionVersionManager(versions_dir=str(tmp_path / "versions"))
        mgr.create_version(str(session))

        # Remove cookie
        data = json.loads(session.read_text())
        data["cookies"] = data["cookies"][:1]
        session.write_text(json.dumps(data))
        mgr.create_version(str(session))

        diff = mgr.diff(str(session), 1, 2)
        assert len(diff.cookies_removed) == 1

    def test_diff_with_modified(self, tmp_path):
        session = _make_session(tmp_path)
        mgr = SessionVersionManager(versions_dir=str(tmp_path / "versions"))
        mgr.create_version(str(session))

        # Modify cookie value
        data = json.loads(session.read_text())
        data["cookies"][0]["value"] = "modified"
        session.write_text(json.dumps(data))
        mgr.create_version(str(session))

        diff = mgr.diff(str(session), 1, 2)
        assert len(diff.cookies_modified) == 1
        assert diff.cookies_modified[0]["name"] == "user_session"

    def test_diff_nonexistent_version(self, tmp_path):
        session = _make_session(tmp_path)
        mgr = SessionVersionManager(versions_dir=str(tmp_path / "versions"))
        diff = mgr.diff(str(session), 1, 2)
        assert diff.has_changes is False

    def test_delete_version(self, tmp_path):
        session = _make_session(tmp_path)
        mgr = SessionVersionManager(versions_dir=str(tmp_path / "versions"))
        mgr.create_version(str(session))
        mgr.create_version(str(session))
        assert mgr.delete_version(str(session), 1) is True
        versions = mgr.list_versions(str(session))
        assert len(versions) == 1
        assert versions[0].version == 2

    def test_delete_nonexistent(self, tmp_path):
        session = _make_session(tmp_path)
        mgr = SessionVersionManager(versions_dir=str(tmp_path / "versions"))
        assert mgr.delete_version(str(session), 99) is False

    def test_prune_versions(self, tmp_path):
        session = _make_session(tmp_path)
        mgr = SessionVersionManager(versions_dir=str(tmp_path / "versions"), max_versions=3)
        for _ in range(5):
            mgr.create_version(str(session))
        versions = mgr.list_versions(str(session))
        assert len(versions) == 3
        assert versions[0].version == 3

    def test_metadata_persistence(self, tmp_path):
        session = _make_session(tmp_path)
        versions_dir = tmp_path / "versions"
        mgr = SessionVersionManager(versions_dir=str(versions_dir))
        mgr.create_version(str(session))

        # Create new manager instance
        mgr2 = SessionVersionManager(versions_dir=str(versions_dir))
        versions = mgr2.list_versions(str(session))
        assert len(versions) == 1

    def test_create_version_file_is_copy(self, tmp_path):
        session = _make_session(tmp_path)
        mgr = SessionVersionManager(versions_dir=str(tmp_path / "versions"))
        v = mgr.create_version(str(session))

        # Version file should be identical to original
        version_data = json.loads(Path(v.path).read_text())
        original_data = json.loads(session.read_text())
        assert version_data == original_data

    def test_diff_storage_changes(self, tmp_path):
        session = _make_session(tmp_path)
        mgr = SessionVersionManager(versions_dir=str(tmp_path / "versions"))
        mgr.create_version(str(session))

        # Add localStorage
        data = json.loads(session.read_text())
        data["local_storage"] = {"key": "value"}
        session.write_text(json.dumps(data))
        mgr.create_version(str(session))

        diff = mgr.diff(str(session), 1, 2)
        assert "local_storage" in diff.storage_changes
