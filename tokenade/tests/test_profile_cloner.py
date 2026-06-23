"""Tests for Phase 41: Browser Profile Cloner."""
import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def fake_chrome_profile(tmp_dir):
    """Create a fake Chrome profile structure."""
    profile = tmp_dir / "source_profile"
    profile.mkdir()

    # Create Default profile dir
    default = profile / "Default"
    default.mkdir()

    # Create some files
    (default / "Preferences").write_text('{"browser": {"check_default_browser": false}}')
    (default / "Secure Preferences").write_text('{}')
    (default / "Bookmarks").write_text('{"roots": {}}')

    # Create cookies database
    import sqlite3
    cookies_db = default / "Cookies"
    conn = sqlite3.connect(str(cookies_db))
    conn.execute("""CREATE TABLE IF NOT EXISTS cookies (
        host_key TEXT, name TEXT, value TEXT, path TEXT,
        expires_utc INTEGER, is_secure INTEGER, is_httponly INTEGER,
        samesite INTEGER, encrypted_value BLOB
    )""")
    conn.commit()
    conn.close()

    # Create cache dirs (should be skipped)
    (profile / "Cache").mkdir()
    (profile / "Code Cache").mkdir()
    (profile / "GPUCache").mkdir()

    # Create extensions dir (should be copied)
    ext_dir = profile / "Extensions"
    ext_dir.mkdir()
    (ext_dir / "ext1").mkdir()
    (ext_dir / "ext1" / "manifest.json").write_text('{"name": "Test Extension"}')

    return profile


@pytest.fixture
def fake_session_file(tmp_dir):
    """Create a fake .tokenade session file."""
    import json
    session = {
        "site_name": "gmail",
        "cookies": [
            {"name": "SID", "value": "abc123", "domain": ".google.com", "path": "/"},
            {"name": "HSID", "value": "xyz789", "domain": ".google.com", "path": "/"},
        ],
        "local_storage": {"key1": "value1"},
        "session_storage": {},
    }
    path = tmp_dir / "session.tokenade"
    path.write_text(json.dumps(session))
    return path


class TestProfileCloner:
    """Test profile cloning."""

    def test_clone_basic(self, tmp_dir, fake_chrome_profile):
        from tokenade.core.browser.profile_cloner import ProfileCloner

        cloner = ProfileCloner()
        dest = tmp_dir / "cloned_profile"

        result = cloner.clone_profile(
            str(fake_chrome_profile), str(dest), browser="chrome"
        )

        assert result.success
        assert result.files_copied > 0
        assert result.size_bytes > 0
        assert dest.exists()
        assert (dest / "Default" / "Preferences").exists()

    def test_clone_skips_cache_dirs(self, tmp_dir, fake_chrome_profile):
        from tokenade.core.browser.profile_cloner import ProfileCloner

        cloner = ProfileCloner()
        dest = tmp_dir / "cloned_profile"

        result = cloner.clone_profile(
            str(fake_chrome_profile), str(dest), browser="chrome"
        )

        assert result.success
        # Cache dirs should NOT be copied
        assert not (dest / "Cache").exists()
        assert not (dest / "Code Cache").exists()
        assert not (dest / "GPUCache").exists()

    def test_clone_copies_extensions(self, tmp_dir, fake_chrome_profile):
        from tokenade.core.browser.profile_cloner import ProfileCloner

        cloner = ProfileCloner()
        dest = tmp_dir / "cloned"

        cloner.clone_profile(str(fake_chrome_profile), str(dest), browser="chrome")

        assert (dest / "Extensions" / "ext1" / "manifest.json").exists()

    def test_clone_source_not_found(self, tmp_dir):
        from tokenade.core.browser.profile_cloner import ProfileCloner

        cloner = ProfileCloner()
        result = cloner.clone_profile(
            str(tmp_dir / "nonexistent"), str(tmp_dir / "dest"), browser="chrome"
        )

        assert not result.success
        assert "not found" in result.errors[0].lower()

    def test_clone_dest_already_exists(self, tmp_dir, fake_chrome_profile):
        from tokenade.core.browser.profile_cloner import ProfileCloner

        cloner = ProfileCloner()
        dest = tmp_dir / "existing"
        dest.mkdir()

        result = cloner.clone_profile(
            str(fake_chrome_profile), str(dest), browser="chrome"
        )

        assert not result.success
        assert "already exists" in result.errors[0].lower()

    def test_clone_with_session_injection(self, tmp_dir, fake_chrome_profile, fake_session_file):
        from tokenade.core.browser.profile_cloner import ProfileCloner

        cloner = ProfileCloner()
        dest = tmp_dir / "cloned"

        result = cloner.clone_profile(
            str(fake_chrome_profile), str(dest),
            browser="chrome", session_file=str(fake_session_file),
        )

        assert result.success
        assert result.session_injected
        assert result.cookies_injected == 2

    def test_clone_summary(self, tmp_dir, fake_chrome_profile):
        from tokenade.core.browser.profile_cloner import ProfileCloner

        cloner = ProfileCloner()
        dest = tmp_dir / "cloned"

        result = cloner.clone_profile(
            str(fake_chrome_profile), str(dest), browser="chrome"
        )

        summary = result.summary
        assert "files" in summary
        assert "MB" in summary

    def test_list_profiles_empty(self, tmp_dir):
        from tokenade.core.browser.profile_cloner import ProfileCloner

        cloner = ProfileCloner()
        # Just verify it doesn't crash
        profiles = cloner.list_profiles("nonexistent_browser_xyz")
        assert isinstance(profiles, list)


class TestCloneCLI:
    """Test CLI parser for clone-profile."""

    def test_clone_profile_parser(self):
        from tokenade.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args([
            "clone-profile", "/tmp/source",
            "--dest", "/tmp/dest",
            "--browser", "chrome",
        ])
        assert args.command == "clone-profile"
        assert args.source == "/tmp/source"
        assert args.dest == "/tmp/dest"
        assert args.browser == "chrome"

    def test_clone_profile_with_session(self):
        from tokenade.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args([
            "clone-profile", "--dest", "/tmp/dest",
            "--session", "gmail.tokenade",
        ])
        assert args.dest == "/tmp/dest"
        assert args.session == "gmail.tokenade"

    def test_clone_profile_list_profiles(self):
        from tokenade.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args([
            "clone-profile", "--dest", "/tmp/dest",
            "--list-profiles",
        ])
        assert args.list_profiles is True

    def test_clone_profile_no_dest_fails(self):
        from tokenade.cli import _build_parser

        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["clone-profile", "/tmp/source"])
