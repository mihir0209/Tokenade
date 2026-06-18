"""Tests for session manager."""

import json
import pytest
from pathlib import Path
from tokenade.core.importer.session_manager import (
    SessionManager,
    SessionInfo,
)


class TestSessionManager:
    @pytest.fixture
    def manager(self, tmp_path):
        return SessionManager(sessions_dir=str(tmp_path))

    @pytest.fixture
    def session_files(self, tmp_path):
        """Create multiple session files for testing."""
        sessions = []
        for i, (site, cookies) in enumerate([
            ("google", [{"name": "SID", "value": "abc", "domain": ".google.com", "path": "/"}]),
            ("github", [{"name": "user_session", "value": "xyz", "domain": ".github.com", "path": "/"}]),
            ("google_extra", [{"name": "SID", "value": "abc", "domain": ".google.com", "path": "/"},
                              {"name": "HSID", "value": "de", "domain": ".google.com", "path": "/"}]),
        ]):
            session = {
                "version": "2.0",
                "site_name": site,
                "cookies": cookies,
                "source_device": {"browser": "firefox" if i % 2 == 0 else "chrome"},
            }
            path = tmp_path / f"{site}.tokenade"
            path.write_text(json.dumps(session))
            sessions.append(str(path))
        return sessions

    def test_list_sessions(self, manager, session_files):
        sessions = manager.list_sessions()
        assert len(sessions) == 3

    def test_list_sessions_pattern(self, manager, session_files):
        sessions = manager.list_sessions(pattern="*google*")
        assert len(sessions) == 2

    def test_filter_sessions_by_site(self, manager, session_files):
        sessions = manager.list_sessions()
        filtered = manager.filter_sessions(sessions, site_name="google")
        assert len(filtered) == 2

    def test_filter_sessions_by_browser(self, manager, session_files):
        sessions = manager.list_sessions()
        filtered = manager.filter_sessions(sessions, browser="firefox")
        assert len(filtered) == 2

    def test_filter_sessions_by_cookie_count(self, manager, session_files):
        sessions = manager.list_sessions()
        filtered = manager.filter_sessions(sessions, min_cookies=2)
        assert len(filtered) == 1

    def test_merge_sessions(self, manager, session_files, tmp_path):
        output = str(tmp_path / "merged.tokenade")
        result = manager.merge_sessions(
            session_files[:2],
            output,
            site_name="merged",
        )
        assert result == output
        assert Path(output).exists()

        merged = json.loads(Path(output).read_text())
        assert merged["site_name"] == "merged"
        assert len(merged["cookies"]) == 2  # One from each file

    def test_merge_sessions_deduplication(self, manager, session_files, tmp_path):
        # Merge two files with same cookie
        output = str(tmp_path / "merged.tokenade")
        manager.merge_sessions(
            [session_files[0], session_files[2]],  # Both have SID cookie
            output,
        )
        merged = json.loads(Path(output).read_text())
        # Should deduplicate SID cookie
        sid_cookies = [c for c in merged["cookies"] if c["name"] == "SID"]
        assert len(sid_cookies) == 1

    def test_rotate_session_round_robin(self, manager, session_files):
        selected1 = manager.rotate_session(session_files, strategy="round-robin")
        selected2 = manager.rotate_session(session_files, strategy="round-robin")
        assert selected1 != selected2

    def test_rotate_session_random(self, manager, session_files):
        selected = manager.rotate_session(session_files, strategy="random")
        assert selected in session_files

    def test_rotate_session_single_file(self, manager, session_files):
        selected = manager.rotate_session([session_files[0]], strategy="round-robin")
        assert selected == session_files[0]

    def test_get_session_stats(self, manager, session_files):
        stats = manager.get_session_stats(session_files)
        assert stats["session_count"] == 3
        assert stats["total_cookies"] == 4  # 1 + 1 + 2
        assert "firefox" in stats["unique_browsers"]
        assert "chrome" in stats["unique_browsers"]

    def test_get_session_info(self, manager, session_files):
        info = manager._get_session_info(Path(session_files[0]))
        assert info is not None
        assert info.site_name == "google"
        assert info.cookie_count == 1
        assert info.source_browser == "firefox"

    def test_get_session_info_invalid(self, manager, tmp_path):
        invalid_file = tmp_path / "invalid.tokenade"
        invalid_file.write_text("not json")
        info = manager._get_session_info(invalid_file)
        assert info is None


class TestSessionInfo:
    def test_session_info_dataclass(self):
        info = SessionInfo(
            path="/path/to/session.tokenade",
            site_name="test",
            cookie_count=10,
            has_local_storage=True,
            created_at="2025-01-01T00:00:00Z",
            source_browser="firefox",
            file_size=1024,
        )
        assert info.path == "/path/to/session.tokenade"
        assert info.site_name == "test"
        assert info.cookie_count == 10
        assert info.has_local_storage is True
