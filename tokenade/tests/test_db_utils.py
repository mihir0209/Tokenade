"""Tests for shared database utilities."""

import os
import sqlite3
import pytest
from tokenade.core.importer.db_utils import copy_db


class TestCopyDb:
    def test_copies_file(self, tmp_path):
        src = tmp_path / "test.db"
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE t (c TEXT)")
        conn.commit()
        conn.close()
        result = copy_db(str(src))
        assert os.path.exists(result)
        conn2 = sqlite3.connect(result)
        rows = conn2.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        conn2.close()
        assert len(rows) >= 1
        os.unlink(result)

    def test_copies_wal(self, tmp_path):
        src = tmp_path / "test.db"
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE t (c TEXT)")
        conn.commit()
        conn.close()
        # Create WAL file
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE t2 (c TEXT)")
        conn.commit()
        conn.close()
        wal = str(src) + "-wal"
        if os.path.exists(wal):
            result = copy_db(str(src))
            assert os.path.exists(result + "-wal")
            os.unlink(result)
            os.unlink(result + "-wal")
        else:
            result = copy_db(str(src))
            assert os.path.exists(result)
            os.unlink(result)

    def test_copies_shm(self, tmp_path):
        src = tmp_path / "test.db"
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE t (c TEXT)")
        conn.commit()
        conn.close()
        shm = str(src) + "-shm"
        if os.path.exists(shm):
            result = copy_db(str(src))
            assert os.path.exists(result + "-shm")
            os.unlink(result)
            os.unlink(result + "-shm")
        else:
            result = copy_db(str(src))
            assert os.path.exists(result)
            os.unlink(result)

    def test_no_wal_no_error(self, tmp_path):
        src = tmp_path / "test.db"
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE t (c TEXT)")
        conn.commit()
        conn.close()
        result = copy_db(str(src))
        assert os.path.exists(result)
        assert not os.path.exists(result + "-wal")
        os.unlink(result)

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            copy_db("/nonexistent/path/db.sqlite")

    def test_creates_temp_file(self, tmp_path):
        src = tmp_path / "test.db"
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE t (c TEXT)")
        conn.commit()
        conn.close()
        result = copy_db(str(src))
        assert result != str(src)
        assert "tmp" in result or "tmp" in result.lower()
        os.unlink(result)

    def test_validates_database(self, tmp_path):
        src = tmp_path / "notadb.db"
        src.write_bytes(b"this is not a sqlite database")
        with pytest.raises(sqlite3.DatabaseError):
            copy_db(str(src))
