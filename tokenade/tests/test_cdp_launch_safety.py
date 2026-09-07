"""Safety gates for CDP auto-launch: snapshot layout, live-dir refusal, donor backup.

Background: automation launched against a live Chromium profile can prune
cookie rows it cannot decrypt (observed on Windows Edge with app-bound
encryption). The export flow must therefore snapshot, refuse live user-data
dirs, and back up donor files before quitting anything.
"""

from pathlib import Path

from tokenade.cli.session_export import (
    _backup_donor_profile,
    _is_live_user_data_dir,
    _snapshot_chromium_profile,
)


def _fake_profile(root: Path) -> Path:
    """Build a minimal Chromium-like profile tree. Returns profile dir."""
    ud = root / "User Data"
    prof = ud / "Default"
    (prof / "Network").mkdir(parents=True)
    (prof / "Network" / "Cookies").write_bytes(b"fake-cookies-db")
    (prof / "Network" / "Cookies-journal").write_bytes(b"")
    leveldb = prof / "Local Storage" / "leveldb"
    leveldb.mkdir(parents=True)
    (leveldb / "000003.log").write_bytes(b"fake-entries")
    (prof / "Preferences").write_text("{}")
    (ud / "Local State").write_text("{}")
    cache = prof / "Cache"
    cache.mkdir(parents=True)
    (cache / "data_0").write_bytes(b"x" * 1024)
    return prof


class TestSnapshotLayout:
    def test_mirrors_session_files_not_caches(self, tmp_path):
        prof = _fake_profile(tmp_path)
        snap = _snapshot_chromium_profile(prof)
        try:
            assert (snap / "User Data" / "Default" / "Network" / "Cookies").is_file()
            assert (snap / "User Data" / "Default" / "Preferences").is_file()
            assert (snap / "User Data" / "Default" / "Local Storage" / "leveldb" / "000003.log").is_file()
            assert (snap / "User Data" / "Local State").is_file()
            assert not (snap / "User Data" / "Default" / "Cache").exists()
        finally:
            import shutil

            shutil.rmtree(snap, ignore_errors=True)

    def test_snapshot_outside_donor_tree(self, tmp_path):
        import tempfile

        prof = _fake_profile(tmp_path)
        snap = _snapshot_chromium_profile(prof)
        try:
            assert Path(tempfile.gettempdir()) in snap.resolve().parents
            assert tmp_path.resolve() not in snap.resolve().parents
        finally:
            import shutil

            shutil.rmtree(snap, ignore_errors=True)


class TestLiveDirRefusal:
    def test_live_user_data_dir_refused(self, tmp_path):
        ud = tmp_path / "User Data"
        prof = ud / "Default"
        assert _is_live_user_data_dir(str(ud), str(prof)) is True
        assert _is_live_user_data_dir(str(ud / "Default"), str(prof)) is True

    def test_snapshot_dir_allowed(self, tmp_path):
        prof = _fake_profile(tmp_path)
        snap = _snapshot_chromium_profile(prof)
        try:
            assert _is_live_user_data_dir(str(snap / "User Data"), str(prof)) is False
        finally:
            import shutil

            shutil.rmtree(snap, ignore_errors=True)

    def test_missing_inputs_allowed(self):
        assert _is_live_user_data_dir(None, None) is False
        assert _is_live_user_data_dir("", "") is False


class TestDonorBackup:
    def test_backup_copies_cookies_and_local_state(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        prof = _fake_profile(tmp_path / "browser")
        dest = _backup_donor_profile(str(prof), "edge")
        assert dest is not None
        assert (dest / "Cookies").is_file()
        assert (dest / "Local State").is_file()
        assert dest.parent.parent.name == ".tokenade"
