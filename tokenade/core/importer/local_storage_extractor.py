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
            conn = None
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
            except Exception as e:
                logger.warning(f"Failed to read localStorage from {dir_name}: {e}")
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
                if os.path.exists(temp_db):
                    try:
                        os.remove(temp_db)
                    except OSError:
                        pass

        logger.info(f"Extracted {len(local_storage)} localStorage entries from Firefox")
        return local_storage

    def _user_data_dir(self) -> str:
        """Directory holding ``Local State`` (parent of Default/Profile *)."""
        base = os.path.basename(os.path.normpath(self.profile_path))
        if base == "Default" or base.startswith("Profile ") or base in (
            "Guest Profile", "System Profile",
        ):
            return os.path.dirname(os.path.normpath(self.profile_path))
        return os.path.normpath(self.profile_path)

    def _oscrypt_key(self) -> Optional[bytes]:
        """Unwrap the OSCrypt key for encrypted (v10/v11) storage values."""
        try:
            from tokenade.core.crypto.cookie_crypto import CookieCryptoFactory

            key = CookieCryptoFactory.create().get_encryption_key(
                self._user_data_dir()
            )
            return key
        except Exception as e:
            logger.debug(f"OSCrypt key unavailable: {e}")
            return None

    def extract_chrome(self, origin_filter: Optional[str] = None) -> Dict[str, str]:
        """
        Extract localStorage from Chrome's LevelDB.

        Chrome stores localStorage in profile/Local Storage/leveldb/
        using Google's LevelDB format. Prefers plyvel when installed;
        otherwise uses the built-in pure-Python reader
        (:mod:`tokenade.core.importer.leveldb`), which also works on
        Windows/macOS and on locked (running browser) profiles.

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
            plyvel = None
        if plyvel is None:
            return self.extract_chrome_pure(origin_filter)

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
                            if actual_key.startswith("\x01"):
                                actual_key = actual_key[1:]

                            if origin_filter and origin_filter not in origin:
                                continue

                            # Decode value (may be JSON or plain string)
                            if value_bytes[:1] == b"\x01":
                                value = value_bytes[1:].decode("utf-8", errors="replace")
                            elif value_bytes[:1] == b"\x00":
                                value = value_bytes[1:].decode("utf-16-le", errors="replace")
                            else:
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

    def extract_chrome_pure(self, origin_filter: Optional[str] = None) -> Dict[str, str]:
        """Extract via the built-in pure-Python LevelDB reader (no plyvel).

        Same return shape as :meth:`extract_chrome`: with ``origin_filter``
        the plain ``{js_key: value}`` mapping, otherwise keys prefixed as
        ``[origin] key``.
        """
        from tokenade.core.importer import leveldb as _leveldb

        leveldb_path = os.path.join(self.profile_path, "Local Storage", "leveldb")
        if not os.path.exists(leveldb_path):
            logger.warning(f"Chrome LevelDB not found: {leveldb_path}")
            return {}
        key = self._oscrypt_key()
        local_storage: Dict[str, str] = {}
        if origin_filter:
            for origin in _leveldb.list_origins(leveldb_path):
                if origin_filter in origin:
                    for js_key, value in _leveldb.extract_origin(
                        leveldb_path, origin, oscrypt_key=key
                    ).items():
                        local_storage[js_key] = value
            logger.info(
                f"Extracted {len(local_storage)} localStorage entries "
                f"for {origin_filter} (pure reader)"
            )
            return local_storage
        for origin in _leveldb.list_origins(leveldb_path):
            for js_key, value in _leveldb.extract_origin(
                leveldb_path, origin, oscrypt_key=key
            ).items():
                local_storage[f"[{origin}] {js_key}"] = value
        logger.info(
            f"Extracted {len(local_storage)} localStorage entries (pure reader)"
        )
        return local_storage

    def extract(self, origin_filter: Optional[str] = None) -> Dict[str, str]:
        """
        Extract localStorage based on browser type.

        Args:
            origin_filter: Optional origin URL to filter by

        Returns:
            Dictionary of {key: value}
        """
        chromium_like = (
            "chrome", "chromium", "edge", "brave", "vivaldi", "opera", "arc",
        )
        if self.browser in chromium_like:
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
        chromium_like = (
            "chrome", "chromium", "edge", "brave", "vivaldi", "opera", "arc",
        )
        if self.browser == "firefox":
            return self._list_origins_firefox()
        elif self.browser in chromium_like:
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
            from tokenade.core.importer import leveldb as _leveldb

            return _leveldb.list_origins(leveldb_path)

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
