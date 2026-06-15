"""Tests for CLI advanced commands."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from argparse import Namespace

from tokenade.cli.advanced import (
    cmd_batch_export, cmd_batch_load, cmd_validate, cmd_validate_rules, cmd_diff, cmd_fingerprint
)


class TestCmdBatchExport:
    def test_bad_config(self, capsys):
        args = Namespace(site_config="/nonexistent/config.json", browser="chrome",
                         output=None, browser_path=None, profile=None,
                         extract_local_storage=False)
        cmd_batch_export(args)
        assert "failed" in capsys.readouterr().out.lower()

    @patch("tokenade.core.batch.operations.BatchExporter")
    @patch("tokenade.core.batch.operations.load_batch_config")
    def test_export_success(self, mock_load, mock_exporter_cls, tmp_path, capsys):
        mock_load.return_value = [{"name": "google", "domains": ["google.com"]}]
        mock_exporter = MagicMock()
        result = MagicMock()
        result.success = True
        mock_exporter.export_batch.return_value = result
        mock_exporter_cls.return_value = mock_exporter

        args = Namespace(site_config=str(tmp_path / "sites.json"), browser="chrome",
                         output=str(tmp_path / "output"), browser_path=None,
                         profile=None, extract_local_storage=False)
        cmd_batch_export(args)
        assert "success" in capsys.readouterr().out.lower()


class TestCmdBatchLoad:
    def test_bad_config(self, capsys):
        args = Namespace(site_config="/nonexistent/config.json",
                         sessions_dir="/tmp/sessions", target_browser="chrome",
                         profile_dir=None, validate=True, visible=False)
        cmd_batch_load(args)
        assert "failed to load" in capsys.readouterr().out.lower()

    @patch("tokenade.core.batch.operations.generate_batch_report")
    @patch("tokenade.core.batch.operations.BatchLoader")
    def test_load_success(self, mock_loader_cls, mock_report, capsys):
        mock_report.return_value = "Report: 5/5 loaded"
        mock_loader = MagicMock()
        result = MagicMock()
        result.success = True
        mock_loader.load_batch.return_value = result
        mock_loader_cls.return_value = mock_loader

        args = Namespace(site_config=None, sessions_dir="/tmp/sessions",
                         target_browser="chrome", profile_dir=None,
                         validate=True, visible=False)
        cmd_batch_load(args)
        assert "success" in capsys.readouterr().out.lower()


class TestCmdValidate:
    def test_dir_not_found(self, capsys):
        args = Namespace(sessions_dir="/nonexistent/dir")
        cmd_validate(args)
        assert "not found" in capsys.readouterr().out.lower()

    def test_valid_sessions(self, capsys, tmp_path):
        s = tmp_path / "session.json"
        s.write_text(json.dumps({
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [{"name": "SID", "value": "abc"}],
        }))
        args = Namespace(sessions_dir=str(tmp_path))
        cmd_validate(args)
        out = capsys.readouterr().out
        assert "1 valid" in out

    def test_invalid_sessions(self, capsys, tmp_path):
        s = tmp_path / "bad.json"
        s.write_text(json.dumps({"site_name": "test"}))
        args = Namespace(sessions_dir=str(tmp_path))
        cmd_validate(args)
        out = capsys.readouterr().out
        assert "1 invalid" in out

    def test_corrupted_file(self, capsys, tmp_path):
        s = tmp_path / "corrupt.json"
        s.write_text("not json {{{")
        args = Namespace(sessions_dir=str(tmp_path))
        cmd_validate(args)
        out = capsys.readouterr().out
        assert "1 invalid" in out


class TestCmdValidateRules:
    def test_session_not_found(self, capsys):
        args = Namespace(session="/nonexistent/session.json", rules="/nonexistent/rules.json",
                         url=None)
        cmd_validate_rules(args)
        assert "not found" in capsys.readouterr().out.lower()

    def test_rules_not_found(self, capsys, tmp_path):
        s = tmp_path / "session.json"
        s.write_text(json.dumps({"site_name": "test", "auth_status": "logged_in", "cookies": []}))
        args = Namespace(session=str(s), rules="/nonexistent/rules.json", url=None)
        cmd_validate_rules(args)
        assert "not found" in capsys.readouterr().out.lower()


class TestCmdDiff:
    def test_file_a_not_found(self, capsys):
        args = Namespace(session_a="/nonexistent/a.json", session_b="/nonexistent/b.json",
                         verbose=False)
        cmd_diff(args)
        assert "not found" in capsys.readouterr().out.lower()

    def test_file_b_not_found(self, capsys, tmp_path):
        a = tmp_path / "a.json"
        a.write_text("{}")
        args = Namespace(session_a=str(a), session_b="/nonexistent/b.json", verbose=False)
        cmd_diff(args)
        assert "not found" in capsys.readouterr().out.lower()

    @patch("tokenade.core.importer.session_comparator.SessionComparator")
    def test_identical_sessions(self, mock_comp_cls, capsys, tmp_path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        a.write_text("{}")
        b.write_text("{}")
        mock_comp = MagicMock()
        result = MagicMock()
        result.has_changes = False
        mock_comp.compare_files.return_value = result
        mock_comp_cls.return_value = mock_comp

        args = Namespace(session_a=str(a), session_b=str(b), verbose=False)
        cmd_diff(args)
        assert "identical" in capsys.readouterr().out.lower()


class TestCmdFingerprint:
    def test_list(self, capsys):
        with patch("tokenade.core.fingerprint.manager.FingerprintManager") as mock_fp_cls:
            mock_fp = MagicMock()
            mock_fp.list.return_value = ["default", "chrome_profile"]
            mock_fp_cls.return_value = mock_fp
            args = Namespace(action="list", name=None, profile_dir=None)
            cmd_fingerprint(args)
        out = capsys.readouterr().out
        assert "default" in out

    def test_show_not_found(self, capsys):
        with patch("tokenade.core.fingerprint.manager.FingerprintManager") as mock_fp_cls:
            mock_fp = MagicMock()
            mock_fp.load.return_value = None
            mock_fp_cls.return_value = mock_fp
            args = Namespace(action="show", name="nonexistent", profile_dir=None)
            cmd_fingerprint(args)
        assert "not found" in capsys.readouterr().out.lower()

    def test_show_found(self, capsys):
        with patch("tokenade.core.fingerprint.manager.FingerprintManager") as mock_fp_cls:
            mock_fp = MagicMock()
            fp_data = MagicMock()
            fp_data.user_agent = "Mozilla/5.0 (X11; Linux x86_64)"
            fp_data.screen_width = 1920
            fp_data.screen_height = 1080
            fp_data.viewport_width = 1920
            fp_data.viewport_height = 1080
            fp_data.platform = "Linux x86_64"
            fp_data.language = "en-US"
            fp_data.timezone = "America/New_York"
            fp_data.hardware_concurrency = 8
            fp_data.device_memory = 16
            mock_fp.load.return_value = fp_data
            mock_fp_cls.return_value = mock_fp
            args = Namespace(action="show", name="my_fp", profile_dir=None)
            cmd_fingerprint(args)
        out = capsys.readouterr().out
        assert "1920" in out

    def test_delete(self, capsys):
        with patch("tokenade.core.fingerprint.manager.FingerprintManager") as mock_fp_cls:
            mock_fp = MagicMock()
            mock_fp.delete.return_value = True
            mock_fp_cls.return_value = mock_fp
            args = Namespace(action="delete", name="old_fp", profile_dir=None)
            cmd_fingerprint(args)
        assert "deleted" in capsys.readouterr().out.lower()

    def test_delete_not_found(self, capsys):
        with patch("tokenade.core.fingerprint.manager.FingerprintManager") as mock_fp_cls:
            mock_fp = MagicMock()
            mock_fp.delete.return_value = False
            mock_fp_cls.return_value = mock_fp
            args = Namespace(action="delete", name="nonexistent", profile_dir=None)
            cmd_fingerprint(args)
        assert "not found" in capsys.readouterr().out.lower()
