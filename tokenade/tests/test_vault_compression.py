"""
Tests for vault compression and diffing.
"""

import gzip
import json
import tempfile
import zlib
from pathlib import Path

import pytest

from tokenade.core.importer.session_vault import SessionVault


class TestVaultCompression:
    """Tests for gzip and zlib compression in SessionVault."""

    def test_vault_gzip_compression(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = SessionVault(vault_dir=tmp_dir, compression="gzip")
            sample_session = {
                "version": "3.0",
                "site_name": "example.com",
                "cookies": [{"name": "c1", "value": "v1" * 50}],
            }
            with tempfile.NamedTemporaryFile(mode="w", delete=False) as tf:
                json.dump(sample_session, tf)
                tf_path = tf.name

            sid = vault.add(tf_path)
            stored_file = Path(tmp_dir) / f"{sid}.tokenade"
            # Verify file is actually gzip compressed
            decompressed = gzip.decompress(stored_file.read_bytes())
            assert b"example.com" in decompressed

            # Verify retrieval
            retrieved = vault.get(sid)
            assert retrieved is not None
            assert retrieved["site_name"] == "example.com"

    def test_vault_zlib_compression(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = SessionVault(vault_dir=tmp_dir, compression="zlib")
            sample_session = {
                "version": "3.0",
                "site_name": "zlib.test",
                "cookies": [{"name": "c2", "value": "v2" * 50}],
            }
            with tempfile.NamedTemporaryFile(mode="w", delete=False) as tf:
                json.dump(sample_session, tf)
                tf_path = tf.name

            sid = vault.add(tf_path)
            retrieved = vault.get(sid)
            assert retrieved is not None
            assert retrieved["site_name"] == "zlib.test"
