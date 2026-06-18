"""
Comprehensive tests for local_storage_extractor.py — LocalStorageExtractor
Chrome/Firefox extraction, origin listing, JSON parsing.
"""

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from tokenade.core.importer.local_storage_extractor import (
    LocalStorageExtractor,
)


class TestLocalStorageExtractorInit(unittest.TestCase):
    def test_init(self):
        ext = LocalStorageExtractor("/tmp/profile", "chrome")
        self.assertEqual(ext.profile_path, "/tmp/profile")
        self.assertEqual(ext.browser, "chrome")

    def test_init_lowercase(self):
        ext = LocalStorageExtractor("/tmp", "Firefox")
        self.assertEqual(ext.browser, "firefox")


class TestLocalStorageExtractorExtract(unittest.TestCase):
    def test_unsupported_browser(self):
        ext = LocalStorageExtractor("/tmp", "safari")
        result = ext.extract()
        self.assertEqual(result, {})

    def test_chrome_calls_extract_chrome(self):
        ext = LocalStorageExtractor("/tmp", "chrome")
        with patch.object(
            ext, "extract_chrome", return_value={"k": "v"}
        ) as mock:
            result = ext.extract()
            self.assertEqual(result, {"k": "v"})
            mock.assert_called_once()

    def test_firefox_calls_extract_firefox(self):
        ext = LocalStorageExtractor("/tmp", "firefox")
        with patch.object(
            ext, "extract_firefox", return_value={"k": "v"}
        ) as mock:
            result = ext.extract()
            self.assertEqual(result, {"k": "v"})
            mock.assert_called_once()


class TestLocalStorageExtractorExtractFirefox(unittest.TestCase):
    def test_no_storage_dir(self):
        ext = LocalStorageExtractor("/nonexistent", "firefox")
        result = ext.extract_firefox()
        self.assertEqual(result, {})

    def test_extract_with_data(self):
        ext = LocalStorageExtractor.__new__(LocalStorageExtractor)
        ext.profile_path = "/tmp"
        ext.browser = "firefox"

        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = os.path.join(
                tmpdir, "storage", "default", "https+++example.com", "ls"
            )
            os.makedirs(storage_dir)
            db_path = os.path.join(storage_dir, "data.sqlite")
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE data (key TEXT, value BLOB)")
            conn.execute("INSERT INTO data VALUES ('token', 'abc123')")
            conn.execute("INSERT INTO data VALUES ('user', 'john')")
            conn.commit()
            conn.close()

            ext.profile_path = tmpdir
            with patch.object(ext, "_copy_db", return_value=db_path):
                result = ext.extract_firefox()
                self.assertEqual(result["token"], "abc123")
                self.assertEqual(result["user"], "john")

    def test_extract_with_origin_filter(self):
        ext = LocalStorageExtractor.__new__(LocalStorageExtractor)
        ext.profile_path = "/tmp"
        ext.browser = "firefox"

        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = os.path.join(
                tmpdir, "storage", "default", "https+++example.com", "ls"
            )
            os.makedirs(storage_dir)
            db_path = os.path.join(storage_dir, "data.sqlite")
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE data (key TEXT, value BLOB)")
            conn.execute("INSERT INTO data VALUES ('token', 'abc')")
            conn.commit()
            conn.close()

            ext.profile_path = tmpdir
            with patch.object(ext, "_copy_db", return_value=db_path):
                result = ext.extract_firefox(
                    origin_filter="https://example.com"
                )
                self.assertEqual(result["token"], "abc")

    def test_extract_origin_filter_no_match(self):
        ext = LocalStorageExtractor.__new__(LocalStorageExtractor)
        ext.profile_path = "/tmp"
        ext.browser = "firefox"

        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = os.path.join(
                tmpdir, "storage", "default", "https+++example.com", "ls"
            )
            os.makedirs(storage_dir)
            db_path = os.path.join(storage_dir, "data.sqlite")
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE data (key TEXT, value BLOB)")
            conn.execute("INSERT INTO data VALUES ('token', 'abc')")
            conn.commit()
            conn.close()

            ext.profile_path = tmpdir
            with patch.object(ext, "_copy_db", return_value=db_path):
                result = ext.extract_firefox(origin_filter="https://other.com")
                self.assertEqual(result, {})

    def test_extract_bytes_value(self):
        ext = LocalStorageExtractor.__new__(LocalStorageExtractor)
        ext.profile_path = "/tmp"
        ext.browser = "firefox"

        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = os.path.join(
                tmpdir, "storage", "default", "https+++example.com", "ls"
            )
            os.makedirs(storage_dir)
            db_path = os.path.join(storage_dir, "data.sqlite")
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE data (key TEXT, value BLOB)")
            conn.execute("INSERT INTO data VALUES ('bin', X'DEADBEEF')")
            conn.commit()
            conn.close()

            ext.profile_path = tmpdir
            with patch.object(ext, "_copy_db", return_value=db_path):
                result = ext.extract_firefox()
                self.assertIn("bin", result)

    def test_no_ls_files(self):
        ext = LocalStorageExtractor.__new__(LocalStorageExtractor)
        ext.profile_path = "/tmp"
        ext.browser = "firefox"

        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = os.path.join(
                tmpdir, "storage", "default", "https+++example.com"
            )
            os.makedirs(storage_dir)
            ext.profile_path = tmpdir
            result = ext.extract_firefox()
            self.assertEqual(result, {})


class TestLocalStorageExtractorExtractChrome(unittest.TestCase):
    def test_no_leveldb(self):
        ext = LocalStorageExtractor("/nonexistent", "chrome")
        result = ext.extract_chrome()
        self.assertEqual(result, {})

    def test_no_plyvel(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            leveldb_path = os.path.join(tmpdir, "Local Storage", "leveldb")
            os.makedirs(leveldb_path)
            ext = LocalStorageExtractor(tmpdir, "chrome")
            with patch.dict("sys.modules", {"plyvel": None}):
                result = ext.extract_chrome()
                self.assertEqual(result, {})


class TestLocalStorageExtractorListOrigins(unittest.TestCase):
    def test_list_origins_unsupported(self):
        ext = LocalStorageExtractor("/tmp", "safari")
        result = ext.list_origins()
        self.assertEqual(result, [])

    def test_list_origins_firefox_no_dir(self):
        ext = LocalStorageExtractor("/nonexistent", "firefox")
        result = ext.list_origins()
        self.assertEqual(result, [])

    def test_list_origins_firefox(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = os.path.join(
                tmpdir, "storage", "default", "https+++example.com", "ls"
            )
            os.makedirs(storage_dir)
            open(os.path.join(storage_dir, "data.sqlite"), "w").close()
            ext = LocalStorageExtractor(tmpdir, "firefox")
            result = ext.list_origins()
            self.assertEqual(len(result), 1)
            self.assertIn("example.com", result[0])

    def test_list_origins_chrome_no_dir(self):
        ext = LocalStorageExtractor("/nonexistent", "chrome")
        result = ext.list_origins()
        self.assertEqual(result, [])

    def test_list_origins_chrome_no_plyvel(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            leveldb_path = os.path.join(tmpdir, "Local Storage", "leveldb")
            os.makedirs(leveldb_path)
            ext = LocalStorageExtractor(tmpdir, "chrome")
            with patch.dict("sys.modules", {"plyvel": None}):
                result = ext.list_origins()
                self.assertEqual(result, [])


class TestLocalStorageExtractorParseJsonFile(unittest.TestCase):
    def test_parse_flat_dict(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            import json

            json.dump({"token": "abc", "user": "john"}, f)
            f.flush()
            try:
                result = LocalStorageExtractor.parse_json_file(f.name)
                self.assertEqual(result["token"], "abc")
            finally:
                os.unlink(f.name)

    def test_parse_structured_format(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            import json

            json.dump(
                {
                    "data": [
                        {"key": "token", "value": "abc"},
                        {"key": "user", "value": "john"},
                    ]
                },
                f,
            )
            f.flush()
            try:
                result = LocalStorageExtractor.parse_json_file(f.name)
                self.assertEqual(result["token"], "abc")
            finally:
                os.unlink(f.name)

    def test_parse_empty_dict(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            import json

            json.dump({}, f)
            f.flush()
            try:
                result = LocalStorageExtractor.parse_json_file(f.name)
                self.assertEqual(result, {})
            finally:
                os.unlink(f.name)

    def test_parse_non_dict(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            import json

            json.dump([], f)
            f.flush()
            try:
                result = LocalStorageExtractor.parse_json_file(f.name)
                self.assertEqual(result, {})
            finally:
                os.unlink(f.name)

    def test_parse_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            LocalStorageExtractor.parse_json_file("/nonexistent/file.json")


if __name__ == "__main__":
    unittest.main()
