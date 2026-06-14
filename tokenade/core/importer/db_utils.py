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

    # Validate it's a real SQLite database
    try:
        conn = sqlite3.connect(f"file:{temp_path}?mode=ro", uri=True)
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1")
        conn.close()
    except sqlite3.DatabaseError:
        os.unlink(temp_path)
        for suffix in ("-wal", "-shm"):
            p = temp_path + suffix
            if os.path.exists(p):
                os.unlink(p)
        raise

    return temp_path
