"""Tests for CLI advanced commands."""

import json
import pytest
from unittest.mock import patch, MagicMock
from argparse import Namespace

from tokenade.cli.advanced import (
    cmd_batch_export, cmd_batch_load, cmd_validate, cmd_validate_rules, cmd_diff, cmd_fingerprint,
    cmd_test, cmd_setup,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_file(tmp_path, name="test", cookies=None, auth_status="logged_in", tokens=None):
    if cookies is None:
        cookies = [{"name": "sid", "value": "abc", "domain": ".github.com"}]
    data = {"cookies": cookies, "site_name": name, "auth_status": auth_status}
    if tokens:
        data["tokens"] = tokens
    f = tmp_path / f"{name}.json"
    f.write_text(json.dumps(data))
    return f


# ---------------------------------------------------------------------------
# TestCmdBatchExport
# ---------------------------------------------------------------------------

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

    @patch("tokenade.core.batch.operations.generate_batch_report")
    @patch("tokenade.core.batch.operations.BatchExporter")
    @patch("tokenade.core.batch.operations.load_batch_config")
    def test_export_with_errors(self, mock_load, mock_exporter_cls, mock_report, tmp_path, capsys):
        mock_load.return_value = [{"name": "google", "domains": ["google.com"]}]
        mock_report.return_value = "Report: 1/3 failed"
        mock_exporter = MagicMock()
        result = MagicMock()
        result.success = False
        mock_exporter.export_batch.return_value = result
        mock_exporter_cls.return_value = mock_exporter

        args = Namespace(site_config=str(tmp_path / "sites.json"), browser="chrome",
                         output=None, browser_path=None, profile=None,
                         extract_local_storage=False)
        cmd_batch_export(args)
        assert "errors" in capsys.readouterr().out.lower()

    @patch("tokenade.core.batch.operations.load_batch_config")
    def test_export_exception(self, mock_load, capsys):
        mock_load.side_effect = RuntimeError("browser crash")
        args = Namespace(site_config="/bad/config.json", browser="chrome",
                         output=None, browser_path=None, profile=None,
                         extract_local_storage=False)
        cmd_batch_export(args)
        assert "failed" in capsys.readouterr().out.lower()

    @patch("tokenade.core.batch.operations.BatchExporter")
    @patch("tokenade.core.batch.operations.load_batch_config")
    def test_export_runtime_exception(self, mock_load, mock_exporter_cls, capsys):
        mock_load.return_value = [{"name": "google", "domains": ["google.com"]}]
        mock_exporter = MagicMock()
        mock_exporter.export_batch.side_effect = RuntimeError("browser crashed")
        mock_exporter_cls.return_value = mock_exporter

        args = Namespace(site_config="/tmp/sites.json", browser="chrome",
                         output=None, browser_path=None, profile=None,
                         extract_local_storage=False)
        cmd_batch_export(args)
        assert "failed" in capsys.readouterr().out.lower()

    @patch("tokenade.core.batch.operations.generate_batch_report")
    @patch("tokenade.core.batch.operations.BatchExporter")
    @patch("tokenade.core.batch.operations.load_batch_config")
    def test_export_default_output_dir(self, mock_load, mock_exporter_cls, mock_report, tmp_path, capsys):
        mock_load.return_value = [{"name": "google"}]
        mock_report.return_value = "Report OK"
        mock_exporter = MagicMock()
        result = MagicMock()
        result.success = True
        mock_exporter.export_batch.return_value = result
        mock_exporter_cls.return_value = mock_exporter

        args = Namespace(site_config=str(tmp_path / "sites.json"), browser="firefox",
                         output=None, browser_path="/usr/bin/firefox",
                         profile="default", extract_local_storage=True)
        cmd_batch_export(args)
        out = capsys.readouterr().out
        assert "firefox" in out
        assert "sessions_batch" in out


# ---------------------------------------------------------------------------
# TestCmdBatchLoad
# ---------------------------------------------------------------------------

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

    @patch("tokenade.core.batch.operations.generate_batch_report")
    @patch("tokenade.core.batch.operations.BatchLoader")
    def test_load_with_errors(self, mock_loader_cls, mock_report, capsys):
        mock_report.return_value = "Report: 2/5 failed"
        mock_loader = MagicMock()
        result = MagicMock()
        result.success = False
        mock_loader.load_batch.return_value = result
        mock_loader_cls.return_value = mock_loader

        args = Namespace(site_config=None, sessions_dir="/tmp/sessions",
                         target_browser="chrome", profile_dir=None,
                         validate=True, visible=False)
        cmd_batch_load(args)
        assert "errors" in capsys.readouterr().out.lower()

    @patch("tokenade.core.batch.operations.generate_batch_report")
    @patch("tokenade.core.batch.operations.BatchLoader")
    @patch("tokenade.core.batch.operations.load_batch_config")
    def test_load_with_site_config(self, mock_load, mock_loader_cls, mock_report, tmp_path, capsys):
        mock_load.return_value = [{"name": "google", "domains": ["google.com"]}]
        mock_report.return_value = "Report OK"
        mock_loader = MagicMock()
        result = MagicMock()
        result.success = True
        mock_loader.load_batch.return_value = result
        mock_loader_cls.return_value = mock_loader

        args = Namespace(site_config=str(tmp_path / "sites.json"), sessions_dir="/tmp/sessions",
                         target_browser="chrome", profile_dir=None,
                         validate=True, visible=True)
        cmd_batch_load(args)
        out = capsys.readouterr().out
        assert "site(s)" in out.lower() or "loaded" in out.lower()

    @patch("tokenade.core.batch.operations.load_batch_config")
    @patch("tokenade.core.batch.operations.generate_batch_report")
    @patch("tokenade.core.batch.operations.BatchLoader")
    def test_load_exception(self, mock_loader_cls, mock_report, mock_load, capsys):
        mock_load.return_value = [{"name": "google"}]
        mock_loader_cls.side_effect = RuntimeError("load error")
        args = Namespace(site_config=None, sessions_dir="/tmp/sessions",
                         target_browser="chrome", profile_dir=None,
                         validate=True, visible=False)
        cmd_batch_load(args)
        assert "failed" in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# TestCmdValidate
# ---------------------------------------------------------------------------

class TestCmdValidate:
    def test_dir_not_found(self, capsys):
        args = Namespace(sessions_dir="/nonexistent/dir")
        cmd_validate(args)
        assert "not found" in capsys.readouterr().out.lower()

    def test_valid_sessions(self, capsys, tmp_path):
        _make_session_file(tmp_path, "google")
        args = Namespace(sessions_dir=str(tmp_path))
        cmd_validate(args)
        assert "1 valid" in capsys.readouterr().out

    def test_invalid_sessions(self, capsys, tmp_path):
        s = tmp_path / "bad.json"
        s.write_text(json.dumps({"site_name": "test"}))
        args = Namespace(sessions_dir=str(tmp_path))
        cmd_validate(args)
        assert "1 invalid" in capsys.readouterr().out

    def test_corrupted_file(self, capsys, tmp_path):
        s = tmp_path / "corrupt.json"
        s.write_text("not json {{{")
        args = Namespace(sessions_dir=str(tmp_path))
        cmd_validate(args)
        assert "1 invalid" in capsys.readouterr().out

    def test_no_cookies_warning(self, capsys, tmp_path):
        _make_session_file(tmp_path, "empty", cookies=[], auth_status="logged_in")
        args = Namespace(sessions_dir=str(tmp_path))
        cmd_validate(args)
        out = capsys.readouterr().out
        assert "no cookies" in out.lower() or "0 cookies" in out.lower()

    def test_tokens_printed(self, capsys, tmp_path):
        _make_session_file(tmp_path, "tok", tokens=[{"access_token": "abc"}])
        args = Namespace(sessions_dir=str(tmp_path))
        cmd_validate(args)
        out = capsys.readouterr().out
        assert "1 tokens" in out

    def test_non_logged_in_status(self, capsys, tmp_path):
        _make_session_file(tmp_path, "expired", auth_status="expired")
        args = Namespace(sessions_dir=str(tmp_path))
        cmd_validate(args)
        out = capsys.readouterr().out
        assert "1 invalid" in out

    def test_multiple_files(self, capsys, tmp_path):
        _make_session_file(tmp_path, "good")
        _make_session_file(tmp_path, "bad", auth_status="expired")
        s = tmp_path / "corrupt.json"
        s.write_text("not json")
        args = Namespace(sessions_dir=str(tmp_path))
        cmd_validate(args)
        out = capsys.readouterr().out
        assert "1 valid" in out
        assert "2 invalid" in out

    def test_empty_directory(self, capsys, tmp_path):
        args = Namespace(sessions_dir=str(tmp_path))
        cmd_validate(args)
        out = capsys.readouterr().out
        assert "0 valid" in out
        assert "0 invalid" in out

    def test_non_json_files_ignored(self, capsys, tmp_path):
        (tmp_path / "readme.txt").write_text("not a session")
        args = Namespace(sessions_dir=str(tmp_path))
        cmd_validate(args)
        out = capsys.readouterr().out
        assert "0 valid" in out
        assert "0 invalid" in out


# ---------------------------------------------------------------------------
# TestCmdValidateRules
# ---------------------------------------------------------------------------

class TestCmdValidateRules:
    def test_session_not_found(self, capsys):
        args = Namespace(session="/nonexistent/session.json", rules="/nonexistent/rules.json",
                         url=None)
        cmd_validate_rules(args)
        assert "not found" in capsys.readouterr().out.lower()

    def test_rules_not_found(self, capsys, tmp_path):
        s = _make_session_file(tmp_path, "session")
        args = Namespace(session=str(s), rules="/nonexistent/rules.json", url=None)
        cmd_validate_rules(args)
        assert "not found" in capsys.readouterr().out.lower()

    @patch("tokenade.core.importer.advanced_validator.AdvancedValidator")
    @patch("tokenade.core.importer.advanced_validator.load_validation_rules")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_success_all_passed(self, mock_packager_cls, mock_load_rules, mock_adv_cls, tmp_path, capsys):
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": []}
        mock_packager_cls.return_value = mock_packager
        mock_load_rules.return_value = [{"name": "rule1"}]

        mock_validator = MagicMock()
        result1 = MagicMock()
        result1.passed = True
        result1.rule_name = "check_auth"
        result1.message = "Auth valid"
        result1.duration_ms = 12.5
        result1.details = {}
        mock_validator.validate_rules = MagicMock(return_value=[result1])
        mock_adv_cls.return_value = mock_validator

        rules = tmp_path / "rules.json"
        rules.write_text(json.dumps([{"name": "check_auth"}]))
        s = _make_session_file(tmp_path, "session")

        with patch("tokenade.cli.advanced.asyncio.run", return_value=[result1]):
            args = Namespace(session=str(s), rules=str(rules), url="https://google.com")
            cmd_validate_rules(args)

        out = capsys.readouterr().out
        assert "passed" in out.lower()

    @patch("tokenade.core.importer.advanced_validator.load_validation_rules")
    @patch("tokenade.core.importer.advanced_validator.AdvancedValidator")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    @patch("tokenade.cli.advanced.asyncio.run")
    def test_failure_exits(self, mock_run, mock_packager_cls, mock_adv_cls, mock_load_rules, tmp_path, capsys):
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": []}
        mock_packager_cls.return_value = mock_packager
        mock_load_rules.return_value = []

        failed_result = MagicMock()
        failed_result.passed = False
        failed_result.rule_name = "check_domain"
        failed_result.message = "Domain mismatch"
        failed_result.duration_ms = 5.0
        failed_result.details = {"expected": "google.com", "actual": "facebook.com"}
        mock_run.return_value = [failed_result]

        rules = tmp_path / "rules.json"
        rules.write_text(json.dumps([]))
        s = _make_session_file(tmp_path, "session")

        args = Namespace(session=str(s), rules=str(rules), url=None)
        with pytest.raises(SystemExit):
            cmd_validate_rules(args)

    @patch("tokenade.core.importer.advanced_validator.load_validation_rules")
    @patch("tokenade.core.importer.advanced_validator.AdvancedValidator")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    @patch("tokenade.cli.advanced.asyncio.run")
    def test_results_with_details(self, mock_run, mock_packager_cls, mock_adv_cls, mock_load_rules, tmp_path, capsys):
        mock_packager_cls.return_value = MagicMock(load=MagicMock(return_value={"cookies": []}))
        mock_load_rules.return_value = []

        failed_result = MagicMock()
        failed_result.passed = False
        failed_result.rule_name = "check_cookies"
        failed_result.message = "Missing required cookie"
        failed_result.duration_ms = None
        failed_result.details = {"missing": "session_id"}
        mock_run.return_value = [failed_result]

        rules = tmp_path / "rules.json"
        rules.write_text(json.dumps([]))
        s = _make_session_file(tmp_path, "session")

        args = Namespace(session=str(s), rules=str(rules), url=None)
        with pytest.raises(SystemExit):
            cmd_validate_rules(args)
        out = capsys.readouterr().out
        assert "missing" in out.lower() or "session_id" in out


# ---------------------------------------------------------------------------
# TestCmdDiff
# ---------------------------------------------------------------------------

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

    @patch("tokenade.core.importer.session_comparator.SessionComparator")
    def test_sessions_with_changes(self, mock_comp_cls, capsys, tmp_path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        a.write_text("{}")
        b.write_text("{}")
        mock_comp = MagicMock()
        result = MagicMock()
        result.has_changes = True
        result.summary.return_value = "3 cookies changed, 1 added"
        result.cookies_only_in_a = [{"name": "c1", "domain": ".a.com"}]
        result.cookies_only_in_b = [{"name": "c2", "domain": ".b.com"}]
        result.cookies_modified = [{"key": "sid", "a": {"value": "old"}, "b": {"value": "new"}}]
        result.localStorage_only_in_a = ["key_a"]
        result.localStorage_only_in_b = ["key_b"]
        result.localStorage_modified = {"theme": {"a": "dark", "b": "light"}}
        result.metadata_diffs = {"site_name": {"a": "old", "b": "new"}}
        mock_comp.compare_files.return_value = result
        mock_comp_cls.return_value = mock_comp

        args = Namespace(session_a=str(a), session_b=str(b), verbose=True)
        cmd_diff(args)
        out = capsys.readouterr().out
        assert "c1" in out
        assert "c2" in out
        assert "sid" in out
        assert "key_a" in out
        assert "key_b" in out
        assert "theme" in out
        assert "site_name" in out

    @patch("tokenade.core.importer.session_comparator.SessionComparator")
    def test_changes_not_verbose(self, mock_comp_cls, capsys, tmp_path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        a.write_text("{}")
        b.write_text("{}")
        mock_comp = MagicMock()
        result = MagicMock()
        result.has_changes = True
        result.summary.return_value = "1 changed"
        result.cookies_only_in_a = [{"name": "c1", "domain": ".a.com"}]
        result.cookies_only_in_b = []
        result.cookies_modified = []
        result.localStorage_only_in_a = []
        result.localStorage_only_in_b = []
        result.localStorage_modified = {}
        result.metadata_diffs = {}
        mock_comp.compare_files.return_value = result
        mock_comp_cls.return_value = mock_comp

        args = Namespace(session_a=str(a), session_b=str(b), verbose=False)
        cmd_diff(args)
        out = capsys.readouterr().out
        # verbose details should NOT appear when verbose=False
        assert "c1" not in out

    @patch("tokenade.core.importer.session_comparator.SessionComparator")
    def test_only_metadata_diffs(self, mock_comp_cls, capsys, tmp_path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        a.write_text("{}")
        b.write_text("{}")
        mock_comp = MagicMock()
        result = MagicMock()
        result.has_changes = True
        result.summary.return_value = "metadata changed"
        result.cookies_only_in_a = []
        result.cookies_only_in_b = []
        result.cookies_modified = []
        result.localStorage_only_in_a = []
        result.localStorage_only_in_b = []
        result.localStorage_modified = {}
        result.metadata_diffs = {"browser": {"a": "chrome", "b": "firefox"}}
        mock_comp.compare_files.return_value = result
        mock_comp_cls.return_value = mock_comp

        args = Namespace(session_a=str(a), session_b=str(b), verbose=True)
        cmd_diff(args)
        out = capsys.readouterr().out
        assert "browser" in out
        assert "chrome" in out
        assert "firefox" in out


# ---------------------------------------------------------------------------
# TestCmdFingerprint
# ---------------------------------------------------------------------------

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
        assert "chrome_profile" in out

    def test_list_empty(self, capsys):
        with patch("tokenade.core.fingerprint.manager.FingerprintManager") as mock_fp_cls:
            mock_fp = MagicMock()
            mock_fp.list.return_value = []
            mock_fp_cls.return_value = mock_fp
            args = Namespace(action="list", name=None, profile_dir=None)
            cmd_fingerprint(args)
        out = capsys.readouterr().out
        assert "fingerprint" in out.lower()

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
        assert "Mozilla/5.0" in out
        assert "Linux" in out
        assert "en-US" in out
        assert "8" in out
        assert "16" in out

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

    @patch("tokenade.core.fingerprint.manager.FingerprintCollector")
    @patch("tokenade.core.fingerprint.manager.FingerprintManager")
    @patch("tokenade.core.browser.manager.BrowserFactory")
    def test_collect_success(self, mock_bf_cls, mock_fp_cls, mock_collector_cls, capsys):
        mock_fp = MagicMock()
        mock_fp.save.return_value = "/saved/fp.json"
        mock_fp_cls.return_value = mock_fp

        mock_bf = MagicMock()
        mock_bf_cls.create.return_value = mock_bf

        fp_data = MagicMock()
        fp_data.user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        fp_data.screen_width = 1920
        fp_data.screen_height = 1080
        fp_data.platform = "Linux x86_64"
        mock_collector_cls.collect_from_browser.return_value = fp_data

        args = Namespace(action="collect", name="my_fp", profile_dir="/tmp/profile")
        cmd_fingerprint(args)
        out = capsys.readouterr().out
        assert "saved" in out.lower()
        mock_bf.launch.assert_called_once()
        mock_bf.close.assert_called_once()

    @patch("tokenade.core.fingerprint.manager.FingerprintCollector")
    @patch("tokenade.core.fingerprint.manager.FingerprintManager")
    @patch("tokenade.core.browser.manager.BrowserFactory")
    def test_collect_browser_error(self, mock_bf_cls, mock_fp_cls, mock_collector_cls, capsys):
        mock_bf = MagicMock()
        mock_bf.launch.side_effect = RuntimeError("Browser not found")
        mock_bf_cls.create.return_value = mock_bf

        mock_fp = MagicMock()
        mock_fp_cls.return_value = mock_fp

        args = Namespace(action="collect", name="my_fp", profile_dir="/tmp/profile")
        # The function doesn't catch this - it will propagate
        with pytest.raises(RuntimeError):
            cmd_fingerprint(args)

    def test_unknown_action(self, capsys):
        args = Namespace(action="unknown_action", name=None, profile_dir=None)
        cmd_fingerprint(args)
        # No output expected - just does nothing
        out = capsys.readouterr().out
        assert out == ""


# ---------------------------------------------------------------------------
# TestCmdTest
# ---------------------------------------------------------------------------

class TestCmdTest:
    def test_session_not_found(self, capsys):
        args = Namespace(session="/nonexistent/session.json", stealth_level="balanced",
                         variations=False, source_fp=None, target_fp="default",
                         test_api=False, validate_stealth=False, output=None)
        cmd_test(args)
        assert "not found" in capsys.readouterr().out.lower()

    @patch("tokenade.core.fingerprint.manager.FingerprintManager")
    def test_target_fp_not_found(self, mock_fp_cls, tmp_path, capsys):
        s = _make_session_file(tmp_path, "session")
        mock_fp = MagicMock()
        mock_fp.load.return_value = None
        mock_fp_cls.return_value = mock_fp

        args = Namespace(session=str(s), stealth_level="balanced",
                         variations=False, source_fp=None, target_fp="nonexistent",
                         test_api=False, validate_stealth=False, output=None)
        with patch("tokenade.core.fingerprint.manager.FingerprintManager", return_value=mock_fp):
            with patch("tokenade.tests.portability.PortabilityTester") as mock_tester_cls:
                mock_tester = MagicMock()
                result = MagicMock()
                mock_tester.test_session_transfer.return_value = result
                mock_tester.generate_report.return_value = "Report: passed"
                mock_tester_cls.return_value = mock_tester
                cmd_test(args)
        out = capsys.readouterr().out
        assert "testing transfer" in out.lower() or "target_fp" in out.lower() or "nonexistent" in out

    @patch("tokenade.core.fingerprint.manager.FingerprintManager")
    @patch("tokenade.tests.portability.PortabilityTester")
    def test_transfer_success(self, mock_tester_cls, mock_fp_cls, tmp_path, capsys):
        s = _make_session_file(tmp_path, "session")
        mock_fp = MagicMock()
        mock_fp.user_agent = "Mozilla/5.0 TestAgent"
        mock_fp.screen_width = 1920
        mock_fp.screen_height = 1080
        mock_fp_cls.return_value = mock_fp

        mock_tester = MagicMock()
        result = MagicMock()
        mock_tester.test_session_transfer.return_value = result
        mock_tester.generate_report.return_value = "Report: all passed"
        mock_tester_cls.return_value = mock_tester

        mock_fp_inst = MagicMock()
        mock_fp_inst.load.return_value = mock_fp
        with patch("tokenade.core.fingerprint.manager.FingerprintManager", return_value=mock_fp_inst):
            args = Namespace(session=str(s), stealth_level="balanced",
                             variations=False, source_fp=None, target_fp="chrome_v1",
                             test_api=True, validate_stealth=False, output=None)
            cmd_test(args)
        out = capsys.readouterr().out
        assert "transfer" in out.lower() or "testing" in out.lower()

    @patch("tokenade.core.fingerprint.manager.FingerprintManager")
    @patch("tokenade.tests.portability.PortabilityTester")
    def test_variations(self, mock_tester_cls, mock_fp_cls, tmp_path, capsys):
        s = _make_session_file(tmp_path, "session")
        mock_fp_inst = MagicMock()
        mock_fp_cls.return_value = mock_fp_inst

        mock_tester = MagicMock()
        mock_tester.test_fingerprint_variations.return_value = [MagicMock()]
        mock_tester.generate_report.return_value = "Report: variations tested"
        mock_tester_cls.return_value = mock_tester

        args = Namespace(session=str(s), stealth_level="balanced",
                         variations=True, source_fp="base_fp", target_fp=None,
                         test_api=False, validate_stealth=False, output=None)
        with patch("tokenade.core.fingerprint.manager.FingerprintManager", return_value=mock_fp_inst):
            cmd_test(args)
        out = capsys.readouterr().out
        assert "variations" in out.lower()

    @patch("tokenade.core.fingerprint.manager.FingerprintManager")
    @patch("tokenade.core.browser.manager.BrowserFactory")
    @patch("tokenade.core.fingerprint.injector.validate_injection")
    @patch("tokenade.tests.portability.PortabilityTester")
    def test_validate_stealth(self, mock_tester_cls, mock_validate, mock_bf_cls, mock_fp_cls, tmp_path, capsys):
        s = _make_session_file(tmp_path, "session")

        mock_bf = MagicMock()
        mock_bf.launch.return_value = MagicMock()
        mock_bf_cls.create.return_value = mock_bf
        mock_validate.return_value = {"valid": True}

        mock_tester = MagicMock()
        result = MagicMock()
        mock_tester.test_session_transfer.return_value = result
        mock_tester.generate_report.return_value = "Report OK"
        mock_tester_cls.return_value = mock_tester

        mock_fp_inst = MagicMock()
        fp_data = MagicMock()
        fp_data.to_dict.return_value = {"user_agent": "test"}
        fp_data.user_agent = "Mozilla/5.0 TestAgent"
        fp_data.screen_width = 1920
        fp_data.screen_height = 1080
        mock_fp_inst.load.return_value = fp_data
        with patch("tokenade.core.fingerprint.manager.FingerprintManager", return_value=mock_fp_inst):
            args = Namespace(session=str(s), stealth_level="maximum",
                             variations=False, source_fp=None, target_fp="test_fp",
                             test_api=False, validate_stealth=True, output=None)
            cmd_test(args)
        out = capsys.readouterr().out
        assert "stealth" in out.lower()
        mock_validate.assert_called_once()

    @patch("tokenade.core.fingerprint.manager.FingerprintManager")
    @patch("tokenade.core.browser.manager.BrowserFactory")
    @patch("tokenade.core.fingerprint.injector.validate_injection")
    @patch("tokenade.tests.portability.PortabilityTester")
    def test_validate_stealth_invalid(self, mock_tester_cls, mock_validate, mock_bf_cls, mock_fp_cls, tmp_path, capsys):
        s = _make_session_file(tmp_path, "session")

        mock_bf = MagicMock()
        mock_bf.launch.return_value = MagicMock()
        mock_bf_cls.create.return_value = mock_bf
        mock_validate.return_value = {"valid": False}

        mock_tester = MagicMock()
        result = MagicMock()
        mock_tester.test_session_transfer.return_value = result
        mock_tester.generate_report.return_value = "Report OK"
        mock_tester_cls.return_value = mock_tester

        mock_fp_inst = MagicMock()
        fp_data = MagicMock()
        fp_data.to_dict.return_value = {"user_agent": "test"}
        fp_data.user_agent = "Mozilla/5.0 TestAgent"
        fp_data.screen_width = 1920
        fp_data.screen_height = 1080
        mock_fp_inst.load.return_value = fp_data
        with patch("tokenade.core.fingerprint.manager.FingerprintManager", return_value=mock_fp_inst):
            args = Namespace(session=str(s), stealth_level="maximum",
                             variations=False, source_fp=None, target_fp="test_fp",
                             test_api=False, validate_stealth=True, output=None)
            cmd_test(args)
        out = capsys.readouterr().out
        assert "not be fully active" in out.lower() or "stealth" in out.lower()


# ---------------------------------------------------------------------------
# TestCmdSetup
# ---------------------------------------------------------------------------

class TestCmdSetup:
    @patch("tokenade.core.security.credentials.CredentialManager")
    def test_no_existing_accounts_decline(self, mock_cred_cls, capsys):
        mock_cred = MagicMock()
        mock_cred.load_accounts.return_value = []
        mock_cred_cls.return_value = mock_cred

        with patch("builtins.input", return_value="no"):
            args = Namespace()
            cmd_setup(args)
        out = capsys.readouterr().out
        assert "0" in out or "total accounts" in out.lower()

    @patch("tokenade.core.security.credentials.CredentialManager")
    def test_existing_accounts(self, mock_cred_cls, capsys):
        mock_cred = MagicMock()
        existing = MagicMock()
        mock_cred.load_accounts.return_value = [existing]
        mock_cred_cls.return_value = mock_cred

        with patch("builtins.input", return_value="no"):
            args = Namespace()
            cmd_setup(args)
        out = capsys.readouterr().out
        assert "1 existing" in out.lower() or "1 account" in out.lower() or "Found 1" in out

    @patch("tokenade.core.security.credentials.CredentialManager")
    def test_add_account_login_success(self, mock_cred_cls, tmp_path, capsys):
        mock_cred = MagicMock()
        mock_cred.load_accounts.return_value = []
        mock_cred._keyring_available = True
        mock_cred_cls.return_value = mock_cred

        with patch("builtins.input", side_effect=["yes", "test@example.com", "no"]):
            with patch("getpass.getpass", return_value="password123"):
                with patch("tokenade.core.browser.manager.BrowserFactory") as mock_bf_cls:
                    mock_bf = MagicMock()
                    mock_bf.launch.return_value = MagicMock()
                    mock_bf_cls.create.return_value = mock_bf

                    with patch("tokenade.handlers.google.GoogleHandler") as mock_handler_cls:
                        mock_handler = MagicMock()
                        login_result = MagicMock()
                        login_result.value = "logged_in"
                        mock_handler.login.return_value = login_result
                        mock_handler_cls.return_value = mock_handler

                        args = Namespace()
                        cmd_setup(args)
        out = capsys.readouterr().out
        assert "setup complete" in out.lower() or "account #1" in out.lower()

    @patch("tokenade.core.security.credentials.CredentialManager")
    def test_add_account_login_failure(self, mock_cred_cls, tmp_path, capsys):
        mock_cred = MagicMock()
        mock_cred.load_accounts.return_value = []
        mock_cred_cls.return_value = mock_cred

        with patch("builtins.input", side_effect=["yes", "test@example.com", "no"]):
            with patch("getpass.getpass", return_value="wrongpass"):
                with patch("tokenade.core.browser.manager.BrowserFactory") as mock_bf_cls:
                    mock_bf = MagicMock()
                    mock_bf.launch.return_value = MagicMock()
                    mock_bf_cls.create.return_value = mock_bf

                    with patch("tokenade.handlers.google.GoogleHandler") as mock_handler_cls:
                        mock_handler = MagicMock()
                        login_result = MagicMock()
                        login_result.value = "login_failed"
                        mock_handler.login.return_value = login_result
                        mock_handler_cls.return_value = mock_handler

                        args = Namespace()
                        cmd_setup(args)
        out = capsys.readouterr().out
        assert "login failed" in out.lower() or "failed" in out.lower()

    @patch("tokenade.core.security.credentials.CredentialManager")
    def test_empty_email_skipped(self, mock_cred_cls, capsys):
        mock_cred = MagicMock()
        mock_cred.load_accounts.return_value = []
        mock_cred_cls.return_value = mock_cred

        with patch("builtins.input", side_effect=["yes", "", "no"]):
            with patch("getpass.getpass", return_value=""):
                args = Namespace()
                cmd_setup(args)
        out = capsys.readouterr().out
        assert "required" in out.lower()

    @patch("tokenade.core.security.credentials.CredentialManager")
    def test_add_multiple_accounts(self, mock_cred_cls, capsys):
        mock_cred = MagicMock()
        mock_cred.load_accounts.return_value = []
        mock_cred._keyring_available = False
        mock_cred_cls.return_value = mock_cred

        with patch("builtins.input", side_effect=["yes", "a@test.com", "yes", "b@test.com", "no"]):
            with patch("getpass.getpass", side_effect=["pass1", "pass2"]):
                with patch("tokenade.core.browser.manager.BrowserFactory") as mock_bf_cls:
                    mock_bf = MagicMock()
                    mock_bf.launch.return_value = MagicMock()
                    mock_bf_cls.create.return_value = mock_bf

                    with patch("tokenade.handlers.google.GoogleHandler") as mock_handler_cls:
                        mock_handler = MagicMock()
                        login_result = MagicMock()
                        login_result.value = "logged_in"
                        mock_handler.login.return_value = login_result
                        mock_handler_cls.return_value = mock_handler

                        args = Namespace()
                        cmd_setup(args)
        out = capsys.readouterr().out
        assert "2" in out  # total accounts

    @patch("tokenade.core.security.credentials.CredentialManager")
    def test_no_keyring_warning(self, mock_cred_cls, capsys):
        mock_cred = MagicMock()
        mock_cred.load_accounts.return_value = []
        mock_cred._keyring_available = False
        mock_cred_cls.return_value = mock_cred

        with patch("builtins.input", side_effect=["yes", "test@test.com", "no"]):
            with patch("getpass.getpass", return_value="pass"):
                with patch("tokenade.core.browser.manager.BrowserFactory") as mock_bf_cls:
                    mock_bf = MagicMock()
                    mock_bf.launch.return_value = MagicMock()
                    mock_bf_cls.create.return_value = mock_bf

                    with patch("tokenade.handlers.google.GoogleHandler") as mock_handler_cls:
                        mock_handler = MagicMock()
                        login_result = MagicMock()
                        login_result.value = "logged_in"
                        mock_handler.login.return_value = login_result
                        mock_handler_cls.return_value = mock_handler

                        args = Namespace()
                        cmd_setup(args)
        out = capsys.readouterr().out
        assert "keyring" in out.lower()
