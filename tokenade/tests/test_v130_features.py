"""
Tests for v1.3.0 features:
1. Extension store bundler (zip/xpi packaging)
2. Git-based remote plugin installation
3. S3/R2 Cloud storage transport for session sync
"""

import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tokenade.core.browser.extension_bundler import ExtensionBundler
from tokenade.core.integration.plugin_registry import PluginRegistry
from tokenade.core.sync.syncer import S3Transport, SessionSyncer, SyncConfig


class TestExtensionBundler:
    """Tests for Chrome and Firefox store packaging."""

    def test_bundler_validation_and_build(self):
        repo_root = Path(__file__).resolve().parents[2]
        ext_dir = repo_root / "extension"

        bundler = ExtensionBundler(source_dir=ext_dir)
        valid, errors = bundler.validate_source()
        assert valid is True, f"Validation errors: {errors}"

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)
            chrome_zip = bundler.build_chrome_zip(out_path / "test-chrome.zip")
            assert chrome_zip.is_file()

            # Verify zip content
            with zipfile.ZipFile(chrome_zip, "r") as zf:
                names = zf.namelist()
                assert "manifest.json" in names
                assert "background.js" in names
                assert "popup.html" in names
                # Excluded dev files
                assert not any(n.endswith(".py") or n.endswith(".pyc") for n in names)

            firefox_xpi = bundler.build_firefox_xpi(out_path / "test-firefox.xpi")
            assert firefox_xpi.is_file()

            with zipfile.ZipFile(firefox_xpi, "r") as zf:
                manifest_content = json.loads(zf.read("manifest.json").decode("utf-8"))
                assert "browser_specific_settings" in manifest_content
                assert manifest_content["browser_specific_settings"]["gecko"]["id"] == "tokenade@tokenade.dev"


class TestGitPluginInstaller:
    """Tests for git-based plugin installation."""

    def test_install_from_git_local_simulation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            plugins_dir = tmp_path / "plugins"
            plugins_dir.mkdir()

            registry = PluginRegistry(plugins_dir=plugins_dir)

            # Create a mock git repository structure
            repo_dir = tmp_path / "mock-git-repo"
            repo_dir.mkdir()
            manifest = {
                "name": "git-test-plugin",
                "version": "1.0.0",
                "description": "Installed via git",
                "type": "handler",
                "entry_point": "plugin:GitTestPlugin",
            }
            (repo_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
            (repo_dir / "plugin.py").write_text("class GitTestPlugin: pass\n", encoding="utf-8")

            # Mock subprocess.run to simulate git clone by copying mock repo
            def mock_clone(cmd, **kwargs):
                dest = Path(cmd[-1])
                shutil.copytree(repo_dir, dest, dirs_exist_ok=True)
                return MagicMock(returncode=0)

            with patch("subprocess.run", side_effect=mock_clone):
                success = registry.install_from_git("https://github.com/example/git-test-plugin.git")
                assert success is True
                assert (plugins_dir / "git-test-plugin" / "plugin.json").is_file()
                assert (plugins_dir / "git-test-plugin" / "plugin.py").is_file()


class TestS3SyncTransport:
    """Tests for S3/R2 cloud storage sync transport."""

    def test_s3_transport_mocked(self):
        mock_boto3 = MagicMock()
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            transport = S3Transport(
                bucket="test-bucket",
                endpoint_url="https://example.r2.cloudflarestorage.com",
                region="auto",
                access_key_id="test-key",
                secret_access_key="test-secret",
            )
            assert transport.connect() is True
            mock_boto3.client.assert_called_once_with(
                "s3",
                endpoint_url="https://example.r2.cloudflarestorage.com",
                region_name="auto",
                aws_access_key_id="test-key",
                aws_secret_access_key="test-secret",
            )

            with tempfile.NamedTemporaryFile() as tmp_file:
                transport.upload(Path(tmp_file.name), "session1.tokenade")
                mock_client.upload_file.assert_called_once_with(
                    tmp_file.name, "test-bucket", "session1.tokenade"
                )

                transport.download("session1.tokenade", Path(tmp_file.name))
                mock_client.download_file.assert_called_once_with(
                    "test-bucket", "session1.tokenade", tmp_file.name
                )

                mock_client.list_objects_v2.return_value = {
                    "Contents": [{"Key": "sessions/s1.tokenade"}, {"Key": "sessions/s2.tokenade"}]
                }
                files = transport.list_remote("sessions")
                assert "s1.tokenade" in files
                assert "s2.tokenade" in files

    def test_syncer_with_s3_config(self):
        config = SyncConfig(
            transport="s3",
            s3_bucket="my-tokenade-vault",
            s3_endpoint_url="https://my-r2.cloudflarestorage.com",
        )
        syncer = SessionSyncer(config)
        transport = syncer._get_transport()
        assert isinstance(transport, S3Transport)
        assert transport.bucket == "my-tokenade-vault"
        assert transport.endpoint_url == "https://my-r2.cloudflarestorage.com"
