"""
Local Storage Extractor - Read localStorage from browser databases.

Supports:
- Firefox: ls/data.sqlite (SQLite-based localStorage)
- Chrome/Chromium: Local Storage/leveldb (LevelDB-based)

Handles site-specific filtering so users only export what they need.
"""

import json
import os
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional
import logging

from tokenade.core.importer.db_utils import copy_db

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
        """Copy database to temp file (browser may lock it)."""
        return copy_db(db_path)

    def extract_firefox(self, origin_filter: Optional[str] = None) -> Dict[str, str]:
        """
        Extract localStorage from Firefox's per-origin ls/data.sqlite files.

        Firefox stores localStorage in:
          profile/storage/default/https+++domain/ls/data.sqlite

        Each file has tables:
        - database: origin metadata
        - data: key-value pairs (key, value)

        Args:
            origin_filter: Optional origin URL to filter by (e.g., "https://web.telegram.org")

        Returns:
            Dictionary of {key: value} for the matching origin
        """
        storage_base = os.path.join(self.profile_path, "storage", "default")
        if not os.path.exists(storage_base):
            logger.warning(f"Firefox storage directory not found: {storage_base}")
            return {}

        local_storage = {}

        for dir_name in os.listdir(storage_base):
            ls_path = os.path.join(storage_base, dir_name, "ls", "data.sqlite")
            if not os.path.exists(ls_path):
                continue

            # Check if this origin matches the filter
            if origin_filter:
                # dir_name format: https+++web.telegram.org
                origin_from_dir = dir_name.replace("+++", "://").replace("+", "/")
                if not (origin_from_dir == origin_filter or origin_from_dir.endswith(origin_filter)):
                    continue

            temp_db = self._copy_db(ls_path)
            try:
                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()

                cursor.execute("SELECT key, value FROM data ORDER BY key")
                for row in cursor.fetchall():
                    key, value = row
                    if isinstance(value, bytes):
                        try:
                            value = value.decode("utf-8")
                        except UnicodeDecodeError:
                            value = value.decode("utf-8", errors="replace")
                    local_storage[str(key)] = str(value)

                conn.close()
            except Exception as e:
                logger.warning(f"Failed to read localStorage from {dir_name}: {e}")
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
        """List origins from Firefox storage/default directories."""
        storage_base = os.path.join(self.profile_path, "storage", "default")
        if not os.path.exists(storage_base):
            return []

        origins = []
        for dir_name in os.listdir(storage_base):
            ls_path = os.path.join(storage_base, dir_name, "ls", "data.sqlite")
            if os.path.exists(ls_path):
                origin = dir_name.replace("+++", "://").replace("+", "/")
                origins.append(origin)

        return sorted(origins)

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
