"""Comprehensive tests for local_storage_extractor.py to boost coverage from 58% to 80%+."""

import json
import os
import sqlite3
import tempfile
import shutil
from unittest.mock import MagicMock, patch

import pytest

from tokenade.core.importer.local_storage_extractor import LocalStorageExtractor


def _create_firefox_ls_db(base_dir, domain, entries):
    ls_dir = os.path.join(base_dir, "storage", "default", domain, "ls")
    os.makedirs(ls_dir, exist_ok=True)
    db_path = os.path.join(ls_dir, "data.sqlite")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS database (id INTEGER PRIMARY KEY, origin TEXT, usage INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS data (database_id INTEGER, key TEXT, value TEXT)")
    origin = domain.replace("+++", "://").replace("+", "/")
    c.execute("INSERT INTO database (id, origin) VALUES (1, ?)", (origin,))
    for k, v in entries:
        c.execute("INSERT INTO data (database_id, key, value) VALUES (1, ?, ?)", (k, v))
    conn.commit()
    conn.close()
    return db_path


class TestExtractFirefoxExtended:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        _create_firefox_ls_db(self.tmpdir, "https+++example.com", [("k1", "v1")])

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_bytes_value_decoded(self):
        ls_dir = os.path.join(self.tmpdir, "storage", "default", "https+++bin.org", "ls")
        os.makedirs(ls_dir, exist_ok=True)
        db_path = os.path.join(ls_dir, "data.sqlite")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS database (id INTEGER PRIMARY KEY, origin TEXT, usage INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS data (database_id INTEGER, key TEXT, value BLOB)")
        c.execute("INSERT INTO database (id, origin) VALUES (1, ?)", ("https://bin.org",))
        c.execute("INSERT INTO data (database_id, key, value) VALUES (1, ?, ?)", ("blobkey", b"binaryval"))
        conn.commit()
        conn.close()
        ext = LocalStorageExtractor(self.tmpdir, browser="firefox")
        result = ext.extract_firefox()
        assert "blobkey" in result
        assert result["blobkey"] == "binaryval"

    def test_unicode_decode_error_fallback(self):
        ls_dir = os.path.join(self.tmpdir, "storage", "default", "https+++badutf8.org", "ls")
        os.makedirs(ls_dir, exist_ok=True)
        db_path = os.path.join(ls_dir, "data.sqlite")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS database (id INTEGER PRIMARY KEY, origin TEXT, usage INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS data (database_id INTEGER, key TEXT, value BLOB)")
        c.execute("INSERT INTO database (id, origin) VALUES (1, ?)", ("https://badutf8.org",))
        c.execute("INSERT INTO data (database_id, key, value) VALUES (1, ?, ?)", ("bad", b"\xff\xfe"))
        conn.commit()
        conn.close()
        ext = LocalStorageExtractor(self.tmpdir, browser="firefox")
        result = ext.extract_firefox()
        assert "bad" in result

    def test_origin_filter_with_suffix_match(self):
        ext = LocalStorageExtractor(self.tmpdir, browser="firefox")
        result = ext.extract_firefox(origin_filter="example.com")
        assert "k1" in result

    def test_storage_base_not_exists(self):
        ext = LocalStorageExtractor("/nonexistent/path", browser="firefox")
        result = ext.extract_firefox()
        assert result == {}

    def test_no_ls_subdir(self):
        os.makedirs(os.path.join(self.tmpdir, "storage", "default", "https+++nolshere.com"), exist_ok=True)
        ext = LocalStorageExtractor(self.tmpdir, browser="firefox")
        result = ext.extract_firefox()
        assert "k1" in result

    def test_db_read_error(self):
        """Test when reading a specific ls database fails."""
        _create_firefox_ls_db(self.tmpdir, "https+++bad.db", [("k", "v")])
        ext = LocalStorageExtractor(self.tmpdir, browser="firefox")
        with patch("tokenade.core.importer.local_storage_extractor.sqlite3") as mock_sql:
            orig_connect = sqlite3.connect
            call_count = [0]

            def selective_connect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] > 1:
                    raise sqlite3.DatabaseError("corrupt")
                return orig_connect(*args, **kwargs)
            mock_sql.connect.side_effect = selective_connect
            result = ext.extract_firefox()
            assert isinstance(result, dict)


class TestExtractChromeExtended:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmpdir, "Local Storage", "leveldb"), exist_ok=True)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_plyvel_not_installed(self):
        ext = LocalStorageExtractor(self.tmpdir, browser="chrome")
        with patch.dict("sys.modules", {"plyvel": None}):
            result = ext.extract_chrome()
            assert result == {}

    def test_leveldb_not_exists(self):
        ext = LocalStorageExtractor("/nonexistent", browser="chrome")
        result = ext.extract_chrome()
        assert result == {}

    def test_successful_extraction(self):
        mock_plyvel = MagicMock()
        mock_db = MagicMock()
        entries = [
            (b"_https://example.com\x00\x01theme", b"dark"),
            (b"_https://other.com\x00\x01key", b"val"),
        ]
        mock_db.__iter__ = MagicMock(return_value=iter(entries))
        mock_plyvel.DB.return_value = mock_db

        ext = LocalStorageExtractor(self.tmpdir, browser="chrome")
        with patch.dict("sys.modules", {"plyvel": mock_plyvel}):
            result = ext.extract_chrome()
            assert "[https://example.com] \x01theme" in result
            assert result["[https://example.com] \x01theme"] == "dark"

    def test_origin_filter(self):
        mock_plyvel = MagicMock()
        mock_db = MagicMock()
        entries = [
            (b"_https://example.com\x00\x01key1", b"v1"),
            (b"_https://other.com\x00\x01key2", b"v2"),
        ]
        mock_db.__iter__ = MagicMock(return_value=iter(entries))
        mock_plyvel.DB.return_value = mock_db

        ext = LocalStorageExtractor(self.tmpdir, browser="chrome")
        with patch.dict("sys.modules", {"plyvel": mock_plyvel}):
            result = ext.extract_chrome(origin_filter="example.com")
            assert "\x01key1" in result
            assert "\x01key2" not in result

    def test_db_exception_returns_empty(self):
        mock_plyvel = MagicMock()
        mock_plyvel.DB.side_effect = Exception("db open failed")
        ext = LocalStorageExtractor(self.tmpdir, browser="chrome")
        with patch.dict("sys.modules", {"plyvel": mock_plyvel}):
            result = ext.extract_chrome()
            assert result == {}

    def test_entry_parse_exception(self):
        """Test when individual entry parsing fails."""
        mock_plyvel = MagicMock()
        mock_db = MagicMock()
        mock_db.__iter__ = MagicMock(return_value=iter([
            (b"\x00bad_key_no_underscore", b"v"),
        ]))
        mock_plyvel.DB.return_value = mock_db

        ext = LocalStorageExtractor(self.tmpdir, browser="chrome")
        with patch.dict("sys.modules", {"plyvel": mock_plyvel}):
            result = ext.extract_chrome()
            assert result == {}


class TestExtractDispatch:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_chromium_dispatch(self):
        ext = LocalStorageExtractor(self.tmpdir, browser="chromium")
        result = ext.extract()
        assert result == {}

    def test_edge_dispatch(self):
        ext = LocalStorageExtractor(self.tmpdir, browser="edge")
        result = ext.extract()
        assert result == {}


class TestListOriginsExtended:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_unsupported_browser_returns_empty(self):
        ext = LocalStorageExtractor(self.tmpdir, browser="opera")
        assert ext.list_origins() == []

    def test_firefox_no_storage_base(self):
        ext = LocalStorageExtractor("/nonexistent", browser="firefox")
        assert ext.list_origins() == []


class TestListOriginsChrome:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_leveldb_not_exists(self):
        ext = LocalStorageExtractor(self.tmpdir, browser="chrome")
        assert ext._list_origins_chrome() == []

    def test_plyvel_not_installed(self):
        ext = LocalStorageExtractor(self.tmpdir, browser="chrome")
        with patch.dict("sys.modules", {"plyvel": None}):
            assert ext._list_origins_chrome() == []

    def test_db_exception_returns_empty(self):
        mock_plyvel = MagicMock()
        mock_plyvel.DB.side_effect = Exception("open failed")
        ext = LocalStorageExtractor(self.tmpdir, browser="chrome")
        with patch.dict("sys.modules", {"plyvel": mock_plyvel}):
            assert ext._list_origins_chrome() == []


class TestParseJsonFileExtended:
    def test_non_dict_returns_empty(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(["a", "b"], f)
            path = f.name
        try:
            result = LocalStorageExtractor.parse_json_file(path)
            assert result == {}
        finally:
            os.unlink(path)

    def test_structured_with_non_list_data(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"data": "not_a_list"}, f)
            path = f.name
        try:
            result = LocalStorageExtractor.parse_json_file(path)
            assert result == {"data": "not_a_list"}
        finally:
            os.unlink(path)

    def test_structured_with_missing_keys(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"data": [{"nokey": 1}, {"key": "k", "value": "v"}]}, f)
            path = f.name
        try:
            result = LocalStorageExtractor.parse_json_file(path)
            assert result == {"k": "v"}
        finally:
            os.unlink(path)

    def test_json_file_read_error(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("")
            path = f.name
        try:
            with pytest.raises(json.JSONDecodeError):
                LocalStorageExtractor.parse_json_file(path)
        finally:
            os.unlink(path)
