"""Tests for local storage extractor."""

import os
import sqlite3
import pytest
from tokenade.core.importer.local_storage_extractor import LocalStorageExtractor


class TestLocalStorageExtractorFirefox:
    @pytest.fixture
    def firefox_profile(self, tmp_path):
        """Create a minimal Firefox profile with localStorage."""
        storage_base = tmp_path / "storage" / "default" / "https+++example.com" / "ls"
        storage_base.mkdir(parents=True)
        db_path = storage_base / "data.sqlite"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE data (
                key TEXT PRIMARY KEY,
                value BLOB NOT NULL
            )
        """)
        cursor.execute("INSERT INTO data (key, value) VALUES ('user', X'616C696365')")
        cursor.execute("INSERT INTO data (key, value) VALUES ('theme', X'6461726B')")
        conn.commit()
        conn.close()
        return str(tmp_path)

    def test_list_origins(self, firefox_profile):
        extractor = LocalStorageExtractor(firefox_profile, browser="firefox")
        origins = extractor.list_origins()
        assert len(origins) >= 1

    def test_extract_firefox(self, firefox_profile):
        extractor = LocalStorageExtractor(firefox_profile, browser="firefox")
        data = extractor.extract_firefox(origin_filter="example.com")
        assert len(data) >= 1

    def test_extract_with_filter(self, firefox_profile):
        extractor = LocalStorageExtractor(firefox_profile, browser="firefox")
        data = extractor.extract_firefox(origin_filter="nonexistent.com")
        assert len(data) == 0


class TestLocalStorageExtractorCreation:
    def test_creation_firefox(self, tmp_path):
        extractor = LocalStorageExtractor(str(tmp_path), browser="firefox")
        assert extractor is not None

    def test_creation_chrome(self, tmp_path):
        extractor = LocalStorageExtractor(str(tmp_path), browser="chrome")
        assert extractor is not None

    def test_unknown_browser(self, tmp_path):
        extractor = LocalStorageExtractor(str(tmp_path), browser="unknown")
        assert extractor is not None
