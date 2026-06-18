"""
Tests for LocalStorageExtractor.

Covers:
- Firefox localStorage extraction from ls/data.sqlite
- Chrome LevelDB extraction (mocked)
- Origin filtering
- Origin listing
- JSON file parsing
"""

import json
import os
import sqlite3
import tempfile
import unittest

from tokenade.core.importer.local_storage_extractor import LocalStorageExtractor


class TestLocalStorageExtractor(unittest.TestCase):
    """Test LocalStorageExtractor functionality."""

    def setUp(self):
        """Create a temporary Firefox profile with localStorage database."""
        self.temp_dir = tempfile.mkdtemp()
        self.profile_path = self.temp_dir

        # Create Firefox-style storage/default/https+++domain/ls/data.sqlite
        storage_base = os.path.join(self.profile_path, "storage", "default")

        self.ls_dbs = {}

        for domain, entries in [
            ("https+++learner.pceterp.in", [("name", "PIMPRI CHINCHWAD EDUCATION TRUST"), ("token", "abc123xyz"), ("user_id", "12345")]),
            ("https+++example.com", [("theme", "dark")]),
        ]:
            ls_dir = os.path.join(storage_base, domain, "ls")
            os.makedirs(ls_dir, exist_ok=True)
            db_path = os.path.join(ls_dir, "data.sqlite")

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE database (
                    id INTEGER PRIMARY KEY,
                    origin TEXT NOT NULL,
                    usage INTEGER DEFAULT 0,
                    last_vacuum_time INTEGER DEFAULT 0,
                    last_analyze_time INTEGER DEFAULT 0,
                    last_vacuum_size INTEGER DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE TABLE data (
                    database_id INTEGER,
                    key TEXT NOT NULL,
                    utf16_length INTEGER DEFAULT 0,
                    conversion_type INTEGER DEFAULT 1,
                    compression_type INTEGER DEFAULT 0,
                    last_access_time INTEGER DEFAULT 0,
                    value TEXT
                )
            """)
            origin = domain.replace("+++", "://").replace("+", "/")
            cursor.execute("INSERT INTO database (id, origin, usage) VALUES (1, ?, 1024)", (origin,))
            for i, (key, val) in enumerate(entries, 1):
                cursor.execute("INSERT INTO data (database_id, key, value) VALUES (1, ?, ?)", (key, val))
            conn.commit()
            conn.close()
            self.ls_dbs[domain] = db_path

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_extract_firefox_all_origins(self):
        """Test extracting all localStorage from Firefox (no filter)."""
        extractor = LocalStorageExtractor(self.profile_path, browser="firefox")
        result = extractor.extract_firefox()

        # Should include all keys from all origins (flat, no prefix)
        self.assertIn("name", result)
        self.assertIn("token", result)
        self.assertIn("theme", result)
        self.assertEqual(result["name"], "PIMPRI CHINCHWAD EDUCATION TRUST")
        self.assertEqual(len(result), 4)

    def test_extract_firefox_filtered_origin(self):
        """Test extracting localStorage with origin filter."""
        extractor = LocalStorageExtractor(self.profile_path, browser="firefox")
        result = extractor.extract_firefox(origin_filter="https://learner.pceterp.in")

        # Should only include matching origin without prefix
        self.assertIn("name", result)
        self.assertIn("token", result)
        self.assertIn("user_id", result)
        self.assertNotIn("theme", result)
        self.assertEqual(len(result), 3)
        self.assertEqual(result["token"], "abc123xyz")

    def test_extract_firefox_no_match(self):
        """Test extracting with non-matching origin filter."""
        extractor = LocalStorageExtractor(self.profile_path, browser="firefox")
        result = extractor.extract_firefox(origin_filter="https://nonexistent.com")

        self.assertEqual(result, {})

    def test_list_origins_firefox(self):
        """Test listing origins from Firefox storage directories."""
        extractor = LocalStorageExtractor(self.profile_path, browser="firefox")
        origins = extractor.list_origins()

        self.assertEqual(len(origins), 2)
        self.assertIn("https://learner.pceterp.in", origins)
        self.assertIn("https://example.com", origins)

    def test_extract_method_dispatch(self):
        """Test that extract() dispatches to correct browser method."""
        extractor = LocalStorageExtractor(self.profile_path, browser="firefox")
        result = extractor.extract(origin_filter="https://learner.pceterp.in")

        self.assertEqual(len(result), 3)
        self.assertIn("name", result)

    def test_extract_chrome_no_leveldb(self):
        """Test Chrome extraction when LevelDB doesn't exist."""
        extractor = LocalStorageExtractor(self.profile_path, browser="chrome")
        result = extractor.extract_chrome()

        self.assertEqual(result, {})

    def test_parse_json_file_flat(self):
        """Test parsing flat JSON localStorage file."""
        json_path = os.path.join(self.temp_dir, "test_ls.json")
        with open(json_path, "w") as f:
            json.dump({"key1": "value1", "key2": "value2"}, f)

        result = LocalStorageExtractor.parse_json_file(json_path)
        self.assertEqual(result["key1"], "value1")
        self.assertEqual(result["key2"], "value2")

    def test_parse_json_file_structured(self):
        """Test parsing structured JSON localStorage file (Firefox export format)."""
        json_path = os.path.join(self.temp_dir, "test_ls_structured.json")
        data = {
            "database": [{"origin": "https://example.com"}],
            "data": [
                {"key": "name", "value": "Test"},
                {"key": "token", "value": "secret"},
            ]
        }
        with open(json_path, "w") as f:
            json.dump(data, f)

        result = LocalStorageExtractor.parse_json_file(json_path)
        self.assertEqual(result["name"], "Test")
        self.assertEqual(result["token"], "secret")

    def test_parse_json_file_not_found(self):
        """Test parsing non-existent JSON file raises error."""
        with self.assertRaises(FileNotFoundError):
            LocalStorageExtractor.parse_json_file("/nonexistent/path.json")

    def test_unsupported_browser(self):
        """Test unsupported browser returns empty dict."""
        extractor = LocalStorageExtractor(self.profile_path, browser="safari")
        result = extractor.extract()
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
