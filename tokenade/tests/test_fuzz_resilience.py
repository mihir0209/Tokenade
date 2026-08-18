"""
Property-based fuzzing and resilience tests for session packaging,
storage schemas, and malformed archives using Hypothesis.
"""

import json
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tokenade.core.importer.session_packager import SessionPackager
from tokenade.core.browser.extension_bundler import ExtensionBundler


class TestHypothesisFuzzing:
    """Fuzz testing on dynamic payload serialization and malformed inputs."""

    @settings(max_examples=50, deadline=1000)
    @given(
        cookie_name=st.text(min_size=1, max_size=50),
        cookie_val=st.text(min_size=0, max_size=100),
        storage_key=st.text(min_size=1, max_size=50),
        storage_val=st.text(min_size=0, max_size=100),
        idb_db=st.text(min_size=1, max_size=30),
        idb_store=st.text(min_size=1, max_size=30),
    )
    def test_fuzz_storage_packager_roundtrip(
        self, cookie_name, cookie_val, storage_key, storage_val, idb_db, idb_store
    ):
        packager = SessionPackager()
        cookies = [{"name": cookie_name, "value": cookie_val, "domain": "fuzz.example"}]
        idb = {
            idb_db: {
                "version": 1,
                "stores": {
                    idb_store: {storage_key: storage_val}
                }
            }
        }
        pkg = packager.package(
            cookies=cookies,
            local_storage={storage_key: storage_val},
            session_storage={storage_key: storage_val},
            indexeddb=idb,
        )

        assert pkg["version"] == "3.0"
        assert "storage" in pkg
        assert "indexeddb" in pkg["storage"]
        assert "local" in pkg["storage"]
        assert "session" in pkg["storage"]

    @settings(max_examples=30, deadline=1000)
    @given(raw_text=st.text())
    def test_fuzz_extension_bundler_resilience(self, raw_text):
        """Ensure bundler gracefully handles corrupted/random files in extension dir."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            (tmp_path / "manifest.json").write_text(raw_text, encoding="utf-8", errors="ignore")
            (tmp_path / "background.js").write_text(raw_text, encoding="utf-8", errors="ignore")

            bundler = ExtensionBundler(source_dir=tmp_path)
            valid, errors = bundler.validate_source()
            # If invalid, it should return False with errors, never raise unhandled crashes
            if not valid:
                assert len(errors) > 0
