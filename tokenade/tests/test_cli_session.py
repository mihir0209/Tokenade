"""Tests for CLI session commands."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from argparse import Namespace

from tokenade.cli.session import (
    cmd_export, cmd_load, cmd_transfer, cmd_inject_profile, cmd_extract
)


class TestCmdExport:
    def test_no_browser_no_profile(self, capsys):
        args = Namespace(list_profiles=False, browser_path=None, browser_name=None,
                         profile=None, site_config=None, domains=None,
                         file_path=None, format=None, extract_local_storage=False,
                         local_storage_origin=None, output=None)
        with patch("tokenade.cli.session.BrowserProfileDiscovery") as mock_disc:
            mock_disc.return_value.discover_all.return_value = {}
            cmd_export(args)
        out = capsys.readouterr().out.lower()
        assert "no profile found" in out or "no browser path" in out

    def test_list_profiles(self, capsys):
        args = Namespace(list_profiles=True, browser_path=None, browser_name=None,
                         profile=None, site_config=None, domains=None,
                         file_path=None, format=None, extract_local_storage=False,
                         local_storage_origin=None, output=None)
        with patch("tokenade.cli.session.BrowserProfileDiscovery") as mock_disc:
            mock_disc.return_value.discover_all.return_value = {}
            cmd_export(args)
        assert "no browser profiles found" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session.CookieExtractor")
    @patch("tokenade.cli.session.SessionPackager")
    def test_no_cookies(self, mock_packager_cls, mock_extractor_cls, tmp_path, capsys):
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = []
        mock_extractor_cls.return_value = mock_extractor

        args = Namespace(list_profiles=False, browser_path=str(tmp_path), browser_name="chrome",
                         profile=None, site_config=None, domains=None,
                         file_path=None, format=None, extract_local_storage=False,
                         local_storage_origin=None, output=None)
        cmd_export(args)
        assert "no cookies" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session.BrowserProfileDiscovery")
    def test_browser_name_not_found(self, mock_disc, capsys):
        mock_disc.return_value.discover_all.return_value = {}
        args = Namespace(list_profiles=False, browser_path=None, browser_name="brave",
                         profile=None, site_config=None, domains=None,
                         file_path=None, format=None, extract_local_storage=False,
                         local_storage_origin=None, output=None)
        cmd_export(args)
        assert "no profile found" in capsys.readouterr().out.lower()


class TestCmdLoad:
    def test_file_not_found(self, capsys):
        args = Namespace(file="/nonexistent/session.tokenade", site_config=None,
                         fingerprint=None, stealth_level="balanced", validate=True,
                         visible=False, profile_dir=None, no_local_storage=False,
                         runtime=False)
        cmd_load(args)
        assert "not found" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session.SessionLoader")
    def test_load_success(self, mock_loader_cls, tmp_path, capsys):
        f = tmp_path / "session.tokenade"
        f.write_text('{"cookies": []}')
        mock_loader = MagicMock()
        mock_loader.load.return_value = {
            "success": True,
            "site_name": "test",
            "cookies_injected": 5,
            "cookies_total": 5,
            "local_storage_injected": 0,
            "local_storage_total": 0,
            "validation": {"auth_status": "logged_in", "valid": True},
        }
        mock_loader_cls.return_value = mock_loader

        args = Namespace(file=str(f), site_config=None, fingerprint=None,
                         stealth_level="balanced", validate=True, visible=False,
                         profile_dir=None, no_local_storage=False, runtime=False)
        cmd_load(args)
        assert "success" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session.SessionLoader")
    def test_load_failure(self, mock_loader_cls, tmp_path, capsys):
        f = tmp_path / "session.tokenade"
        f.write_text('{"cookies": []}')
        mock_loader = MagicMock()
        mock_loader.load.return_value = {
            "success": False,
            "error": "Browser not found",
        }
        mock_loader_cls.return_value = mock_loader

        args = Namespace(file=str(f), site_config=None, fingerprint=None,
                         stealth_level="balanced", validate=True, visible=False,
                         profile_dir=None, no_local_storage=False, runtime=False)
        cmd_load(args)
        assert "failed" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session.SessionLoader")
    def test_load_exception(self, mock_loader_cls, tmp_path, capsys):
        f = tmp_path / "session.tokenade"
        f.write_text('{"cookies": []}')
        mock_loader = MagicMock()
        mock_loader.load.side_effect = Exception("Corrupted")
        mock_loader_cls.return_value = mock_loader

        args = Namespace(file=str(f), site_config=None, fingerprint=None,
                         stealth_level="balanced", validate=True, visible=False,
                         profile_dir=None, no_local_storage=False, runtime=False)
        cmd_load(args)
        assert "failed" in capsys.readouterr().out.lower()


class TestCmdTransfer:
    def test_session_not_found(self, capsys):
        args = Namespace(session="/nonexistent/session.json", fingerprint=None,
                         visible=False, stealth_level="balanced", validate_stealth=False,
                         profile_dir=None)
        cmd_transfer(args)
        assert "not found" in capsys.readouterr().out.lower()

    @patch("tokenade.core.fingerprint.manager.FingerprintManager")
    @patch("tokenade.cli.session.BrowserFactory")
    @patch("tokenade.cli.session.GoogleHandler")
    def test_transfer_success(self, mock_handler_cls, mock_browser_cls, mock_fp_cls, tmp_path, capsys):
        f = tmp_path / "session.json"
        f.write_text(json.dumps({
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [{"name": "SID", "value": "abc", "domain": ".google.com"}],
        }))
        mock_browser = MagicMock()
        mock_browser_cls.create.return_value = mock_browser
        mock_handler = MagicMock()
        mock_handler.inject_session.return_value = True
        mock_handler_cls.return_value = mock_handler
        mock_fp = MagicMock()
        mock_fp_cls.return_value = mock_fp
        mock_fp.load.return_value = None

        args = Namespace(session=str(f), fingerprint=None, visible=False,
                         stealth_level="balanced", validate_stealth=False,
                         profile_dir=None)
        cmd_transfer(args)
        assert "successful" in capsys.readouterr().out.lower()

    @patch("tokenade.core.fingerprint.manager.FingerprintManager")
    @patch("tokenade.cli.session.BrowserFactory")
    @patch("tokenade.cli.session.GoogleHandler")
    def test_transfer_failure(self, mock_handler_cls, mock_browser_cls, mock_fp_cls, tmp_path, capsys):
        f = tmp_path / "session.json"
        f.write_text(json.dumps({
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [],
        }))
        mock_browser = MagicMock()
        mock_browser_cls.create.return_value = mock_browser
        mock_handler = MagicMock()
        mock_handler.inject_session.return_value = False
        mock_handler_cls.return_value = mock_handler
        mock_fp = MagicMock()
        mock_fp_cls.return_value = mock_fp
        mock_fp.load.return_value = None

        args = Namespace(session=str(f), fingerprint=None, visible=False,
                         stealth_level="balanced", validate_stealth=False,
                         profile_dir=None)
        cmd_transfer(args)
        assert "failed" in capsys.readouterr().out.lower()


class TestCmdInjectProfile:
    def test_session_not_found(self, capsys):
        args = Namespace(session="/nonexistent/session.json", browser="chrome",
                         profile="/tmp/profile", dry_run=True, no_backup=False)
        cmd_inject_profile(args)
        assert "not found" in capsys.readouterr().out.lower()

    def test_dry_run(self, capsys, tmp_path):
        f = tmp_path / "session.json"
        f.write_text(json.dumps({
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [
                {"name": "SID", "value": "abc", "domain": ".google.com"},
                {"name": "HSID", "value": "def", "domain": ".google.com"},
            ],
        }))
        args = Namespace(session=str(f), browser="chrome",
                         profile="/tmp/profile", dry_run=True, no_backup=False)
        cmd_inject_profile(args)
        out = capsys.readouterr().out
        assert "dry run" in out.lower()

    @patch("tokenade.cli.session.inject_session_to_profile")
    def test_inject_success(self, mock_inject, capsys, tmp_path):
        f = tmp_path / "session.json"
        f.write_text(json.dumps({"site_name": "google", "auth_status": "logged_in", "cookies": []}))
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.cookies_injected = 5
        mock_result.cookies_total = 5
        mock_result.backup_path = "/tmp/backup"
        mock_inject.return_value = mock_result

        args = Namespace(session=str(f), browser="chrome",
                         profile="/tmp/profile", dry_run=False, no_backup=False)
        cmd_inject_profile(args)
        assert "successful" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session.inject_session_to_profile")
    def test_inject_failure(self, mock_inject, capsys, tmp_path):
        f = tmp_path / "session.json"
        f.write_text(json.dumps({"site_name": "google", "auth_status": "logged_in", "cookies": []}))
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "Profile locked"
        mock_inject.return_value = mock_result

        args = Namespace(session=str(f), browser="chrome",
                         profile="/tmp/profile", dry_run=False, no_backup=False)
        cmd_inject_profile(args)
        assert "failed" in capsys.readouterr().out.lower()


class TestCmdExtract:
    def test_no_accounts(self, capsys):
        with patch("tokenade.core.security.credentials.CredentialManager") as mock_mgr_cls:
            mock_mgr = MagicMock()
            mock_mgr.load_accounts.return_value = []
            mock_mgr_cls.return_value = mock_mgr
            args = Namespace(visible=False)
            cmd_extract(args)
        assert "no accounts configured" in capsys.readouterr().out.lower()

    def test_encrypted_accounts(self, capsys):
        with patch("tokenade.core.security.credentials.CredentialManager") as mock_mgr_cls:
            mock_mgr = MagicMock()
            mock_mgr.load_accounts.side_effect = ValueError("Encrypted")
            mock_mgr_cls.return_value = mock_mgr
            args = Namespace(visible=False)
            cmd_extract(args)
        assert "encrypted" in capsys.readouterr().out.lower()
