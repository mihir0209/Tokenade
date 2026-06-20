"""Tests for encrypted session refresh pipeline."""
import json
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from tokenade.core.refresh.encrypted_refresh import (
    EncryptedRefreshPipeline,
    EncryptedRefreshResult,
    batch_encrypted_refresh,
)


class TestEncryptedRefreshResult:
    def test_success(self):
        result = EncryptedRefreshResult(
            success=True,
            session_file="test.tokenade",
            method="oauth",
        )
        assert result.success
        assert result.method == "oauth"

    def test_failure(self):
        result = EncryptedRefreshResult(
            success=False,
            session_file="test.tokenade",
            method="unknown",
            error="failed",
        )
        assert not result.success
        assert result.error == "failed"


class TestEncryptedRefreshPipeline:
    def test_file_not_found(self):
        pipeline = EncryptedRefreshPipeline()
        result = pipeline.refresh("/nonexistent/file.tokenade")

        assert not result.success
        assert "File not found" in result.error

    def test_unencrypted_session_no_refresh_needed(self, tmp_path):
        session_file = tmp_path / "test.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [
                {"name": "session", "value": "abc", "expires": time.time() + 86400},
            ],
            "tokens": [
                {"type": "access_token", "value": "acc", "expires_at": time.time() + 3600},
            ],
            "metadata": {},
        }
        session_file.write_text(json.dumps(session_data))

        pipeline = EncryptedRefreshPipeline()
        result = pipeline.refresh(str(session_file))

        assert result.success
        assert result.method == "none"
        assert not result.was_encrypted

    def test_unencrypted_session_needs_refresh(self, tmp_path):
        session_file = tmp_path / "test.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [
                {"name": "session", "value": "abc", "expires": time.time() - 100},
            ],
            "tokens": [],
            "metadata": {},
        }
        session_file.write_text(json.dumps(session_data))

        pipeline = EncryptedRefreshPipeline()
        result = pipeline.refresh(str(session_file), source_browser="firefox")

        # Will fail because no source browser, but tests the flow
        assert not result.success
        assert result.method == "cookie"

    def test_is_encrypted_json(self, tmp_path):
        session_file = tmp_path / "plain.tokenade"
        session_file.write_text('{"version": "2.0"}')

        pipeline = EncryptedRefreshPipeline()
        assert not pipeline._is_encrypted(session_file)

    def test_is_encrypted_binary(self, tmp_path):
        session_file = tmp_path / "encrypted.tokenade"
        session_file.write_bytes(b'\x00\x01\x02\x03\x04\x05')

        pipeline = EncryptedRefreshPipeline()
        assert pipeline._is_encrypted(session_file)

    def test_needs_refresh_oauth_expired(self):
        pipeline = EncryptedRefreshPipeline()
        session = {
            "tokens": [
                {"type": "access_token", "value": "acc", "expires_at": time.time() - 100},
            ],
            "cookies": [],
        }
        assert pipeline._needs_refresh(session)

    def test_needs_refresh_cookie_expired(self):
        pipeline = EncryptedRefreshPipeline()
        session = {
            "tokens": [],
            "cookies": [
                {"name": "c", "value": "v", "expires": int(time.time() - 100)},
            ],
        }
        assert pipeline._needs_refresh(session)

    def test_needs_refresh_not_expired(self):
        pipeline = EncryptedRefreshPipeline()
        session = {
            "tokens": [
                {"type": "access_token", "value": "acc", "expires_at": time.time() + 3600},
            ],
            "cookies": [
                {"name": "c", "value": "v", "expires": int(time.time() + 86400)},
            ],
        }
        assert not pipeline._needs_refresh(session)

    def test_encrypted_session_without_password(self, tmp_path):
        session_file = tmp_path / "encrypted.tokenade"
        session_file.write_bytes(b'encrypted data here')

        pipeline = EncryptedRefreshPipeline()
        result = pipeline.refresh(str(session_file))

        assert not result.success
        assert "encrypted" in result.error.lower()
        assert result.was_encrypted


class TestBatchEncryptedRefresh:
    def test_batch_nonexistent_dir(self):
        results = batch_encrypted_refresh("/nonexistent/dir")
        assert len(results) == 0

    def test_batch_empty_dir(self, tmp_path):
        results = batch_encrypted_refresh(str(tmp_path))
        assert len(results) == 0

    def test_batch_with_sessions(self, tmp_path):
        for name in ["a.tokenade", "b.tokenade"]:
            session_data = {
                "version": "2.0",
                "site_name": "test",
                "auth_status": "logged_in",
                "cookies": [{"name": "c", "value": "v", "expires": time.time() + 86400}],
                "tokens": [],
                "metadata": {},
            }
            (tmp_path / name).write_text(json.dumps(session_data))

        results = batch_encrypted_refresh(str(tmp_path))

        assert len(results) == 2
        assert all(r.success for r in results.values())
