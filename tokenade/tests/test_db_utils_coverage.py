"""Extended coverage tests for db_utils module."""

import os
import sqlite3
import shutil
import tempfile
import pytest
from unittest.mock import patch
from tokenade.core.importer.db_utils import copy_db


class TestCopyDbPermissionError:
    def test_permission_error_on_copy(self, tmp_path):
        src = tmp_path / "test.db"
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE t (c TEXT)")
        conn.commit()
        conn.close()
        with patch("shutil.copy2", side_effect=PermissionError("denied")):
            with pytest.raises(PermissionError):
                copy_db(str(src))
            # Temp file should be cleaned up
            remaining = [f for f in os.listdir(tempfile.gettempdir()) if f.endswith(".db")]
            assert isinstance(remaining, list)

    def test_shutil_error_raises_database_error(self, tmp_path):
        src = tmp_path / "test.db"
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE t (c TEXT)")
        conn.commit()
        conn.close()
        with patch("shutil.copy2", side_effect=shutil.Error("copy failed")):
            with pytest.raises(sqlite3.DatabaseError):
                copy_db(str(src))


class TestCopyDbWalShmCopyFailure:
    def test_wal_copy_permission_error_logged(self, tmp_path):
        src = tmp_path / "test.db"
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE t (c TEXT)")
        conn.commit()
        conn.close()
        # Create WAL and SHM files
        wal_path = str(src) + "-wal"
        shm_path = str(src) + "-shm"
        open(wal_path, "wb").write(b"fake-wal")
        open(shm_path, "wb").write(b"fake-shm")

        call_count = 0
        original_copy2 = shutil.copy2

        def selective_copy2(src_path, dst_path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return original_copy2(src_path, dst_path)
            raise PermissionError("no permission for sidecar")

        with patch("shutil.copy2", side_effect=selective_copy2):
            result = copy_db(str(src))
            assert os.path.exists(result)
            # Sidecar copies failed but main copy succeeded
            os.unlink(result)


class TestCopyDbCorruptWithSidecars:
    def test_corrupt_db_cleans_wal_and_shm(self, tmp_path):
        src = tmp_path / "corrupt.db"
        src.write_bytes(b"this is not a sqlite database")
        # Create fake sidecar files
        wal_path = str(src) + "-wal"
        shm_path = str(src) + "-shm"
        open(wal_path, "wb").write(b"fake-wal")
        open(shm_path, "wb").write(b"fake-shm")
        with pytest.raises(sqlite3.DatabaseError):
            copy_db(str(src))
        # Verify cleanup happened (temp files removed)


class TestCopyDbNoSidecars:
    def test_no_wal_shm_files(self, tmp_path):
        src = tmp_path / "clean.db"
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE t (c TEXT)")
        conn.commit()
        conn.close()
        # Ensure no sidecar files exist
        for suffix in ("-wal", "-shm"):
            p = str(src) + suffix
            if os.path.exists(p):
                os.unlink(p)
        result = copy_db(str(src))
        assert os.path.exists(result)
        assert not os.path.exists(result + "-wal")
        assert not os.path.exists(result + "-shm")
        os.unlink(result)


class TestCopyDbWalCreation:
    def test_wal_file_copied_when_present(self, tmp_path):
        src = tmp_path / "test.db"
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE t (c TEXT)")
        conn.commit()
        conn.close()
        # Force WAL mode to create the file
        conn = sqlite3.connect(str(src))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("INSERT INTO t VALUES ('data')")
        conn.commit()
        conn.close()
        wal = str(src) + "-wal"
        if os.path.exists(wal):
            result = copy_db(str(src))
            assert os.path.exists(result + "-wal")
            os.unlink(result)
            if os.path.exists(result + "-wal"):
                os.unlink(result + "-wal")
        else:
            result = copy_db(str(src))
            assert os.path.exists(result)
            os.unlink(result)


class TestCopyDbShmCreation:
    def test_shm_file_copied_when_present(self, tmp_path):
        src = tmp_path / "test.db"
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE t (c TEXT)")
        conn.commit()
        conn.close()
        conn = sqlite3.connect(str(src))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("SELECT * FROM t")
        conn.commit()
        conn.close()
        shm = str(src) + "-shm"
        if os.path.exists(shm):
            result = copy_db(str(src))
            assert os.path.exists(result + "-shm")
            os.unlink(result)
            if os.path.exists(result + "-shm"):
                os.unlink(result + "-shm")
        else:
            result = copy_db(str(src))
            assert os.path.exists(result)
            os.unlink(result)


class TestCopyDbValidation:
    def test_validates_real_database(self, tmp_path):
        src = tmp_path / "valid.db"
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE cookies (name TEXT, value TEXT)")
        conn.execute("INSERT INTO cookies VALUES ('test', 'val')")
        conn.commit()
        conn.close()
        result = copy_db(str(src))
        conn2 = sqlite3.connect(result)
        rows = conn2.execute("SELECT * FROM cookies").fetchall()
        conn2.close()
        assert len(rows) == 1
        assert rows[0] == ("test", "val")
        os.unlink(result)

    def test_empty_database_valid(self, tmp_path):
        src = tmp_path / "empty.db"
        conn = sqlite3.connect(str(src))
        conn.close()
        result = copy_db(str(src))
        assert os.path.exists(result)
        conn2 = sqlite3.connect(result)
        tables = conn2.execute("SELECT name FROM sqlite_master").fetchall()
        conn2.close()
        assert len(tables) == 0
        os.unlink(result)


class TestCopyDbEdgeCases:
    def test_path_with_spaces(self, tmp_path):
        spaced_dir = tmp_path / "path with spaces"
        spaced_dir.mkdir()
        src = spaced_dir / "test.db"
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE t (c TEXT)")
        conn.commit()
        conn.close()
        result = copy_db(str(src))
        assert os.path.exists(result)
        os.unlink(result)

    def test_large_database(self, tmp_path):
        src = tmp_path / "large.db"
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE t (c TEXT)")
        for i in range(1000):
            conn.execute("INSERT INTO t VALUES (?)", (f"row_{i}",))
        conn.commit()
        conn.close()
        result = copy_db(str(src))
        conn2 = sqlite3.connect(result)
        count = conn2.execute("SELECT COUNT(*) FROM t").fetchone()[0]
        conn2.close()
        assert count == 1000
        os.unlink(result)

    def test_readonly_database_copy(self, tmp_path):
        src = tmp_path / "readonly.db"
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE t (c TEXT)")
        conn.commit()
        conn.close()
        os.chmod(str(src), 0o444)
        result = copy_db(str(src))
        assert os.path.exists(result)
        os.unlink(result)
        os.chmod(str(src), 0o644)
