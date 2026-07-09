"""localStorage extractor tests with mocked plyvel/LevelDB paths.

Formerly test_local_storage_extractor_coverage2 — unique browser DB edge cases.
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from tokenade.core.importer.local_storage_extractor import (
    LocalStorageExtractor,
)


def _make_mock_plyvel(entries):
    """Build a MagicMock that behaves like the plyvel module.

    *entries* is a list of (key_bytes, value_bytes) tuples returned when
    iterating over the DB.
    """
    mock_plyvel = MagicMock()
    mock_db = MagicMock()
    mock_db.__iter__ = MagicMock(return_value=iter(entries))
    mock_plyvel.DB.return_value = mock_db
    return mock_plyvel, mock_db


# ---------------------------------------------------------------------------
# Lines 93-94 — extract_firefox error path
# ---------------------------------------------------------------------------
class TestExtractFirefoxErrorPath(unittest.TestCase):
    """Lines 93-94: exception inside the try/except block is caught and
    logged as a warning, and extraction continues for remaining origins."""

    def test_corrupt_table_triggers_warning(self):
        """A valid SQLite file without a ``data`` table causes
        sqlite3.OperationalError, caught on lines 93-94."""
        ext = LocalStorageExtractor.__new__(LocalStorageExtractor)
        ext.profile_path = "/tmp"
        ext.browser = "firefox"

        with tempfile.TemporaryDirectory() as tmpdir:
            storage_base = os.path.join(tmpdir, "storage", "default")

            # --- bad origin: valid SQLite but no 'data' table ---
            bad_dir = os.path.join(storage_base, "https+++bad.example.com", "ls")
            os.makedirs(bad_dir)
            bad_db = os.path.join(bad_dir, "data.sqlite")
            conn = sqlite3.connect(bad_db)
            conn.execute("CREATE TABLE other_table (x TEXT)")
            conn.execute("INSERT INTO other_table VALUES ('nope')")
            conn.commit()
            conn.close()

            # --- good origin: has 'data' table with real data ---
            good_dir = os.path.join(storage_base, "https+++good.example.com", "ls")
            os.makedirs(good_dir)
            good_db = os.path.join(good_dir, "data.sqlite")
            conn = sqlite3.connect(good_db)
            conn.execute("CREATE TABLE data (key TEXT, value BLOB)")
            conn.execute("INSERT INTO data VALUES ('ok', 'yes')")
            conn.commit()
            conn.close()

            ext.profile_path = tmpdir

            # Mock _copy_db to return the real file in-place (no temp copy)
            def fake_copy(path):
                return path

            with patch.object(ext, "_copy_db", side_effect=fake_copy):
                with self.assertLogs(level="WARNING") as cm:
                    result = ext.extract_firefox()

            # Good origin data is still captured despite bad origin failing
            self.assertEqual(result, {"ok": "yes"})
            self.assertTrue(
                any("bad.example.com" in msg for msg in cm.output)
            ), f"Expected warning about bad.example.com, got: {cm.output}"

    def test_non_sqlite_file_triggers_warning(self):
        """A file that is not a valid SQLite DB triggers a warning."""
        ext = LocalStorageExtractor.__new__(LocalStorageExtractor)
        ext.profile_path = "/tmp"
        ext.browser = "firefox"

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = os.path.join(
                tmpdir, "storage", "default", "https+++example.com", "ls"
            )
            os.makedirs(storage)
            not_db = os.path.join(storage, "data.sqlite")
            with open(not_db, "w") as f:
                f.write("this is not a database")

            ext.profile_path = tmpdir
            with patch.object(ext, "_copy_db", return_value=not_db):
                with self.assertLogs(level="WARNING"):
                    result = ext.extract_firefox()
            self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# Lines 127-169 — extract_chrome with mocked plyvel
# ---------------------------------------------------------------------------
class TestExtractChromeMockedPlyvel(unittest.TestCase):
    """Lines 127-169: full Chrome LevelDB extraction with plyvel mocked."""

    def _make_ext(self, tmpdir):
        leveldb = os.path.join(tmpdir, "Local Storage", "leveldb")
        os.makedirs(leveldb)
        return LocalStorageExtractor(tmpdir, "chrome")

    def test_normal_key_no_filter(self):
        """_prefix + \\x00 separator → origin parsed, key = [origin] actual_key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = self._make_ext(tmpdir)
            entries = [
                (b"_https://example.com\x00mykey", b"myvalue"),
            ]
            mock_plyvel, mock_db = _make_mock_plyvel(entries)

            with patch.dict(sys.modules, {"plyvel": mock_plyvel}):
                result = ext.extract_chrome()

            self.assertEqual(result, {"[https://example.com] mykey": "myvalue"})
            mock_db.close.assert_called_once()

    def test_matching_origin_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = self._make_ext(tmpdir)
            entries = [
                (b"_https://example.com\x00token", b"abc"),
            ]
            mock_plyvel, mock_db = _make_mock_plyvel(entries)

            with patch.dict(sys.modules, {"plyvel": mock_plyvel}):
                result = ext.extract_chrome(origin_filter="https://example.com")

            self.assertEqual(result, {"token": "abc"})

    def test_non_matching_origin_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = self._make_ext(tmpdir)
            entries = [
                (b"_https://example.com\x00token", b"abc"),
            ]
            mock_plyvel, mock_db = _make_mock_plyvel(entries)

            with patch.dict(sys.modules, {"plyvel": mock_plyvel}):
                result = ext.extract_chrome(origin_filter="https://other.com")

            self.assertEqual(result, {})

    def test_non_utf8_value_bytes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = self._make_ext(tmpdir)
            entries = [
                (b"_https://example.com\x00bad", b"\xff\xfe\x00\x01"),
            ]
            mock_plyvel, mock_db = _make_mock_plyvel(entries)

            with patch.dict(sys.modules, {"plyvel": mock_plyvel}):
                result = ext.extract_chrome()

            self.assertIn("[https://example.com] bad", result)
            self.assertIsInstance(result["[https://example.com] bad"], str)

    def test_non_underscore_prefix_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = self._make_ext(tmpdir)
            entries = [
                (b"no_underscore\x00value", b"v"),
            ]
            mock_plyvel, mock_db = _make_mock_plyvel(entries)

            with patch.dict(sys.modules, {"plyvel": mock_plyvel}):
                result = ext.extract_chrome()

            self.assertEqual(result, {})

    def test_key_without_null_separator_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = self._make_ext(tmpdir)
            entries = [
                (b"_noseparatorkey", b"v"),
            ]
            mock_plyvel, mock_db = _make_mock_plyvel(entries)

            with patch.dict(sys.modules, {"plyvel": mock_plyvel}):
                result = ext.extract_chrome()

            self.assertEqual(result, {})

    def test_db_open_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = self._make_ext(tmpdir)
            mock_plyvel = MagicMock()
            mock_plyvel.DB.side_effect = RuntimeError("DB locked")

            with patch.dict(sys.modules, {"plyvel": mock_plyvel}):
                with self.assertLogs(level="ERROR"):
                    result = ext.extract_chrome()

            self.assertEqual(result, {})

    def test_multiple_entries_mixed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = self._make_ext(tmpdir)
            entries = [
                (b"_https://a.com\x00k1", b"v1"),
                (b"_https://b.com\x00k2", b"v2"),
                (b"_https://a.com\x00k3", b"v3"),
            ]
            mock_plyvel, mock_db = _make_mock_plyvel(entries)

            with patch.dict(sys.modules, {"plyvel": mock_plyvel}):
                result = ext.extract_chrome(origin_filter="https://a.com")

            self.assertEqual(result, {"k1": "v1", "k3": "v3"})

    def test_json_value(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = self._make_ext(tmpdir)
            entries = [
                (
                    b"_https://example.com\x00cfg",
                    b'{"theme":"dark","lang":"en"}',
                ),
            ]
            mock_plyvel, mock_db = _make_mock_plyvel(entries)

            with patch.dict(sys.modules, {"plyvel": mock_plyvel}):
                result = ext.extract_chrome()

            self.assertEqual(
                result,
                {"[https://example.com] cfg": '{"theme":"dark","lang":"en"}'},
            )

    def test_key_decode_failure_logged(self):
        """If key_bytes.decode raises, lines 158-159 log debug and continue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = self._make_ext(tmpdir)

            class BadKey:
                def decode(self, *a, **kw):
                    raise RuntimeError("decode boom")

            entries = [(BadKey(), b"v")]
            mock_plyvel, mock_db = _make_mock_plyvel(entries)

            with patch.dict(sys.modules, {"plyvel": mock_plyvel}):
                with self.assertLogs(level="DEBUG"):
                    result = ext.extract_chrome()

            self.assertEqual(result, {})

    def test_origin_filter_partial_match(self):
        """origin_filter checks ``origin_filter not in origin``."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = self._make_ext(tmpdir)
            entries = [
                (b"_https://sub.example.com\x00k1", b"v1"),
                (b"_https://example.com\x00k2", b"v2"),
            ]
            mock_plyvel, mock_db = _make_mock_plyvel(entries)

            with patch.dict(sys.modules, {"plyvel": mock_plyvel}):
                result = ext.extract_chrome(origin_filter="example.com")

            # Both origins contain "example.com"
            self.assertEqual(result, {"k1": "v1", "k2": "v2"})


# ---------------------------------------------------------------------------
# Lines 229-246 — _list_origins_chrome with mocked plyvel
# ---------------------------------------------------------------------------
class TestListOriginsChromeMockedPlyvel(unittest.TestCase):
    """Lines 229-246: _list_origins_chrome with plyvel mocked."""

    def _make_ext(self, tmpdir):
        leveldb = os.path.join(tmpdir, "Local Storage", "leveldb")
        os.makedirs(leveldb)
        return LocalStorageExtractor(tmpdir, "chrome")

    def test_origins_extracted_and_sorted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = self._make_ext(tmpdir)
            entries = [
                (b"_https://z.com\x00k1", b"v1"),
                (b"_https://a.com\x00k2", b"v2"),
                (b"_https://m.com\x00k3", b"v3"),
                (b"not_prefixed\x00foo", b"bar"),
            ]
            mock_plyvel, mock_db = _make_mock_plyvel(entries)

            with patch.dict(sys.modules, {"plyvel": mock_plyvel}):
                result = ext._list_origins_chrome()

            self.assertEqual(
                result, ["https://a.com", "https://m.com", "https://z.com"]
            )
            mock_db.close.assert_called_once()

    def test_plyvel_import_error_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = self._make_ext(tmpdir)
            with patch.dict(sys.modules, {"plyvel": None}):
                result = ext._list_origins_chrome()
            self.assertEqual(result, [])

    def test_db_raises_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = self._make_ext(tmpdir)
            mock_plyvel = MagicMock()
            mock_plyvel.DB.side_effect = RuntimeError("locked")

            with patch.dict(sys.modules, {"plyvel": mock_plyvel}):
                result = ext._list_origins_chrome()

            self.assertEqual(result, [])

    def test_key_decode_error_skipped(self):
        """Lines 234-241: exception during key decode → continue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = self._make_ext(tmpdir)

            class BadKey:
                def decode(self, *a, **kw):
                    raise RuntimeError("bad")

            entries = [
                (BadKey(), b"v"),
                (b"_https://ok.com\x00k", b"v"),
            ]
            mock_plyvel, mock_db = _make_mock_plyvel(entries)

            with patch.dict(sys.modules, {"plyvel": mock_plyvel}):
                result = ext._list_origins_chrome()

            self.assertEqual(result, ["https://ok.com"])

    def test_duplicate_origins_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = self._make_ext(tmpdir)
            entries = [
                (b"_https://same.com\x00k1", b"v1"),
                (b"_https://same.com\x00k2", b"v2"),
            ]
            mock_plyvel, mock_db = _make_mock_plyvel(entries)

            with patch.dict(sys.modules, {"plyvel": mock_plyvel}):
                result = ext._list_origins_chrome()

            self.assertEqual(result, ["https://same.com"])

    def test_non_prefixed_keys_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = self._make_ext(tmpdir)
            entries = [
                (b"metadata\x00foo", b"bar"),
                (b"version\x001", b""),
            ]
            mock_plyvel, mock_db = _make_mock_plyvel(entries)

            with patch.dict(sys.modules, {"plyvel": mock_plyvel}):
                result = ext._list_origins_chrome()

            self.assertEqual(result, [])

    def test_key_without_null_separator_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = self._make_ext(tmpdir)
            entries = [
                (b"_noseparator", b"v"),
            ]
            mock_plyvel, mock_db = _make_mock_plyvel(entries)

            with patch.dict(sys.modules, {"plyvel": mock_plyvel}):
                result = ext._list_origins_chrome()

            self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# extract with unsupported browser
# ---------------------------------------------------------------------------
class TestExtractUnsupportedBrowser(unittest.TestCase):
    def test_safari_returns_empty(self):
        ext = LocalStorageExtractor("/tmp", "safari")
        result = ext.extract()
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
