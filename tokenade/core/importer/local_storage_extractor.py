"""
Local Storage Extractor - Read localStorage from browser databases.

Supports:
- Firefox: ls/data.sqlite (SQLite-based localStorage)
- Chrome/Chromium: Local Storage/leveldb (LevelDB-based)

Handles site-specific filtering so users only export what they need.
"""

import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class LocalStorageExtractor:
    """Extracts localStorage data from browser databases."""

    def __init__(self, profile_path: str, browser: str = "chrome"):
        """
        Initialize localStorage extractor.

        Args:
            profile_path: Path to browser profile directory
            browser: Browser type (chrome, firefox, edge)
        """
        self.profile_path = profile_path
        self.browser = browser.lower()

    def _copy_db(self, db_path: str) -> str:
        """Copy database to temp file (browser may lock it).

        Also copies WAL (-wal) and SHM (-shm) files if present.
        """
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"LocalStorage database not found: {db_path}")

        temp_fd, temp_path = tempfile.mkstemp(suffix=".db")
        os.close(temp_fd)
        shutil.copy2(db_path, temp_path)

        # Copy WAL and SHM files if present
        for suffix in ("-wal", "-shm"):
            wal_path = db_path + suffix
            if os.path.exists(wal_path):
                temp_wal = temp_path + suffix
                shutil.copy2(wal_path, temp_wal)

        return temp_path

    def extract_firefox(self, origin_filter: Optional[str] = None) -> Dict[str, str]:
        """
        Extract localStorage from Firefox's ls/data.sqlite.

        Firefox stores localStorage in profile/ls/data.sqlite with tables:
        - database: origin metadata (origin, usage, last_vacuum_time, etc.)
        - data: key-value pairs (key, utf16_length, conversion_type,
                compression_type, last_access_time, value)

        Args:
            origin_filter: Optional origin URL to filter by (e.g., "https://learner.pceterp.in")

        Returns:
            Dictionary of {key: value} for the matching origin
        """
        ls_db = os.path.join(self.profile_path, "ls", "data.sqlite")
        if not os.path.exists(ls_db):
            logger.warning(f"Firefox localStorage DB not found: {ls_db}")
            return {}

        temp_db = self._copy_db(ls_db)
        local_storage = {}

        try:
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()

            # Get all origins first
            cursor.execute("""
                SELECT id, origin FROM database
                ORDER BY origin
            """)
            origins = {row[0]: row[1] for row in cursor.fetchall()}

            if not origins:
                logger.warning("No origins found in Firefox localStorage database")
                conn.close()
                return {}

            # Build query based on filter
            if origin_filter:
                # Find matching origin IDs
                matching_ids = [
                    oid for oid, origin in origins.items()
                    if origin_filter in origin or origin in origin_filter
                ]
                if not matching_ids:
                    logger.warning(f"No origin matching '{origin_filter}' found")
                    logger.info(f"Available origins: {list(origins.values())}")
                    conn.close()
                    return {}

                placeholders = ",".join("?" * len(matching_ids))
                cursor.execute(f"""
                    SELECT key, value FROM data
                    WHERE database_id IN ({placeholders})
                    ORDER BY key
                """, matching_ids)
            else:
                cursor.execute("""
                    SELECT d.key, d.value, db.origin
                    FROM data d
                    JOIN database db ON d.database_id = db.id
                    ORDER BY db.origin, d.key
                """)

            for row in cursor.fetchall():
                if origin_filter:
                    key, value = row
                else:
                    key, value, origin = row
                    # Prefix with origin for disambiguation when no filter
                    key = f"[{origin}] {key}"

                # Decode value if it's bytes
                if isinstance(value, bytes):
                    try:
                        value = value.decode("utf-8")
                    except UnicodeDecodeError:
                        value = value.decode("utf-8", errors="replace")

                local_storage[key] = value

            conn.close()

        finally:
            if os.path.exists(temp_db):
                os.remove(temp_db)

        logger.info(f"Extracted {len(local_storage)} localStorage entries from Firefox")
        return local_storage

    def extract_chrome(self, origin_filter: Optional[str] = None) -> Dict[str, str]:
        """
        Extract localStorage from Chrome's LevelDB.

        Chrome stores localStorage in profile/Local Storage/leveldb/
        using Google's LevelDB format. This requires the plyvel library.

        Args:
            origin_filter: Optional origin to filter by

        Returns:
            Dictionary of {key: value}
        """
        leveldb_path = os.path.join(self.profile_path, "Local Storage", "leveldb")
        if not os.path.exists(leveldb_path):
            logger.warning(f"Chrome LevelDB not found: {leveldb_path}")
            return {}

        try:
            import plyvel
        except ImportError:
            logger.error("plyvel library required for Chrome localStorage extraction. "
                        "Install with: pip install plyvel")
            return {}

        local_storage = {}

        try:
            db = plyvel.DB(leveldb_path, create_if_missing=False)

            # Chrome LevelDB keys are prefixed with origin
            # Format: _https://example.com\x00\x01key
            for key_bytes, value_bytes in db:
                try:
                    key_str = key_bytes.decode("utf-8", errors="replace")

                    # Parse Chrome's key format
                    if key_str.startswith("_"):
                        # Extract origin and actual key
                        parts = key_str.split("\x00", 1)
                        if len(parts) == 2:
                            origin = parts[0][1:]  # Remove leading underscore
                            actual_key = parts[1]

                            if origin_filter and origin_filter not in origin:
                                continue

                            # Decode value (may be JSON or plain string)
                            try:
                                value = value_bytes.decode("utf-8")
                            except UnicodeDecodeError:
                                value = value_bytes.decode("utf-8", errors="replace")

                            storage_key = actual_key if origin_filter else f"[{origin}] {actual_key}"
                            local_storage[storage_key] = value

                except Exception as e:
                    logger.debug(f"Failed to parse LevelDB entry: {e}")
                    continue

            db.close()

        except Exception as e:
            logger.error(f"Failed to read Chrome LevelDB: {e}")
            return {}

        logger.info(f"Extracted {len(local_storage)} localStorage entries from Chrome")
        return local_storage

    def extract(self, origin_filter: Optional[str] = None) -> Dict[str, str]:
        """
        Extract localStorage based on browser type.

        Args:
            origin_filter: Optional origin URL to filter by

        Returns:
            Dictionary of {key: value}
        """
        if self.browser in ("chrome", "chromium", "edge"):
            return self.extract_chrome(origin_filter)
        elif self.browser == "firefox":
            return self.extract_firefox(origin_filter)
        else:
            logger.error(f"Unsupported browser for localStorage: {self.browser}")
            return {}

    def list_origins(self) -> List[str]:
        """
        List all origins that have localStorage data.

        Returns:
            List of origin URLs
        """
        if self.browser == "firefox":
            return self._list_origins_firefox()
        elif self.browser in ("chrome", "chromium", "edge"):
            return self._list_origins_chrome()
        else:
            return []

    def _list_origins_firefox(self) -> List[str]:
        """List origins from Firefox localStorage database."""
        ls_db = os.path.join(self.profile_path, "ls", "data.sqlite")
        if not os.path.exists(ls_db):
            return []

        temp_db = self._copy_db(ls_db)
        origins = []

        try:
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("SELECT origin FROM database ORDER BY origin")
            origins = [row[0] for row in cursor.fetchall()]
            conn.close()
        finally:
            if os.path.exists(temp_db):
                os.remove(temp_db)

        return origins

    def _list_origins_chrome(self) -> List[str]:
        """List origins from Chrome LevelDB."""
        leveldb_path = os.path.join(self.profile_path, "Local Storage", "leveldb")
        if not os.path.exists(leveldb_path):
            return []

        try:
            import plyvel
        except ImportError:
            return []

        origins = set()

        try:
            db = plyvel.DB(leveldb_path, create_if_missing=False)
            for key_bytes, _ in db:
                try:
                    key_str = key_bytes.decode("utf-8", errors="replace")
                    if key_str.startswith("_"):
                        parts = key_str.split("\x00", 1)
                        if len(parts) == 2:
                            origins.add(parts[0][1:])
                except Exception:
                    continue
            db.close()
        except Exception:
            pass

        return sorted(list(origins))

    @staticmethod
    def parse_json_file(file_path: str) -> Dict[str, str]:
        """Parse a JSON file containing localStorage data."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Handle both flat dict and structured formats
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                # Firefox ls/data.sqlite export format
                result = {}
                for entry in data["data"]:
                    if "key" in entry and "value" in entry:
                        result[entry["key"]] = entry["value"]
                return result
            else:
                # Plain key-value dict
                return data

        return {}
