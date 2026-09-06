"""Shared database utilities for browser data extraction."""

import logging
import os
import shutil
import sqlite3
import tempfile

logger = logging.getLogger(__name__)


def copy_db(db_path: str) -> str:
    """Copy database to temp file (browser may lock it).

    Also copies WAL (-wal) and SHM (-shm) files if present,
    since Firefox/Chrome use WAL mode and data may be in WAL.

    Args:
        db_path: Path to the database file

    Returns:
        Path to the temporary copy

    Raises:
        FileNotFoundError: If db_path does not exist
        PermissionError: If file cannot be read
        sqlite3.DatabaseError: If the database is corrupt
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    temp_fd, temp_path = tempfile.mkstemp(suffix=".db")
    os.close(temp_fd)

    try:
        shutil.copy2(db_path, temp_path)
    except PermissionError:
        os.unlink(temp_path)
        raise
    except shutil.Error as e:
        os.unlink(temp_path)
        raise sqlite3.DatabaseError(f"Failed to copy database: {e}")

    # Copy WAL and SHM files if present
    for suffix in ("-wal", "-shm"):
        src = db_path + suffix
        if os.path.exists(src):
            try:
                shutil.copy2(src, temp_path + suffix)
            except (PermissionError, shutil.Error):
                logger.warning(f"Could not copy {suffix} file for {db_path}")

    # Own the temp copies: copy2 propagates the source mode, so a read-only
    # source yields read-only temp files that cannot be cleaned up on
    # Windows (WinError 5). Owner-only mode also keeps cookie material
    # out of reach of other local users on POSIX.
    for p in (temp_path, temp_path + "-wal", temp_path + "-shm"):
        if os.path.exists(p):
            try:
                os.chmod(p, 0o600)
            except OSError:
                pass

    # Validate it's a real SQLite database. The connection must be closed
    # on every path: Windows refuses to unlink a file with an open handle.
    conn = None
    try:
        conn = sqlite3.connect(f"file:{temp_path}?mode=ro", uri=True)
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1")
    except sqlite3.DatabaseError:
        for p in [temp_path, temp_path + "-wal", temp_path + "-shm"]:
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass
        raise
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    return temp_path
