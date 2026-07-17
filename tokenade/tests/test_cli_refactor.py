"""Tests for CLI refactor - importability, dispatch, config, output, completions."""
import json
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Import tests - verify every command is importable from its new module
# ---------------------------------------------------------------------------

class TestCommandImports:
    """All 22 command functions must be importable from their submodules."""

    def test_session_commands(self):
        from tokenade.cli.session import cmd_extract, cmd_load, cmd_transfer, cmd_inject_profile
        from tokenade.cli.session_export import cmd_export
        for fn in (cmd_extract, cmd_export, cmd_load, cmd_transfer, cmd_inject_profile):
            assert callable(fn)

    def test_security_commands(self):
        from tokenade.cli.security import cmd_encrypt, cmd_decrypt, cmd_rekey
        for fn in (cmd_encrypt, cmd_decrypt, cmd_rekey):
            assert callable(fn)

    def test_proxy_commands(self):
        from tokenade.cli.proxy import cmd_proxy
        assert callable(cmd_proxy)

    def test_management_commands(self):
        from tokenade.cli.management import cmd_sessions, cmd_health, cmd_refresh, cmd_share, cmd_unshare
        for fn in (cmd_sessions, cmd_health, cmd_refresh, cmd_share, cmd_unshare):
            assert callable(fn)

    def test_advanced_commands(self):
        from tokenade.cli.advanced import (
            cmd_batch_export, cmd_batch_load, cmd_validate,
            cmd_validate_rules, cmd_diff, cmd_fingerprint, cmd_test, cmd_setup,
        )
        for fn in (cmd_batch_export, cmd_batch_load, cmd_validate,
                   cmd_validate_rules, cmd_diff, cmd_fingerprint, cmd_test, cmd_setup):
            assert callable(fn)

    def test_all_commands_reachable_from_package(self):
        from tokenade.cli import (
            cmd_extract, cmd_export, cmd_load, cmd_transfer, cmd_inject_profile,
            cmd_encrypt, cmd_decrypt, cmd_rekey,
            cmd_proxy,
            cmd_sessions, cmd_health, cmd_refresh, cmd_share, cmd_unshare,
            cmd_batch_export, cmd_batch_load, cmd_validate,
            cmd_validate_rules, cmd_diff, cmd_fingerprint, cmd_test, cmd_setup,
        )
        commands = [
            cmd_extract, cmd_export, cmd_load, cmd_transfer, cmd_inject_profile,
            cmd_encrypt, cmd_decrypt, cmd_rekey,
            cmd_proxy,
            cmd_sessions, cmd_health, cmd_refresh, cmd_share, cmd_unshare,
            cmd_batch_export, cmd_batch_load, cmd_validate,
            cmd_validate_rules, cmd_diff, cmd_fingerprint, cmd_test, cmd_setup,
        ]
        assert len(commands) == 22


# ---------------------------------------------------------------------------
# main() dispatch tests
# ---------------------------------------------------------------------------

class TestMainDispatch:
    """main() must set up argparse and dispatch to the correct command.

    Patches target ``tokenade.cli.<name>`` because ``main()`` binds the
    imported functions into a local ``commands`` dict at call time via
    ``from tokenade.cli.<mod> import <fn>`` which stores the reference
    on ``tokenade.cli``.
    """

    def test_main_is_callable(self):
        from tokenade.cli import main
        assert callable(main)

    def test_no_command_prints_help(self):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_version_flag(self):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    @patch("tokenade.cli.cmd_setup")
    def test_setup_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "setup"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_extract")
    def test_extract_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "extract"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_export")
    def test_export_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "export"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_load")
    def test_load_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "load", "-", "test.tokenade"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_transfer")
    def test_transfer_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "transfer", "-s", "test.tokenade"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_inject_profile")
    def test_inject_profile_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "inject-profile", "-s", "test.tokenade", "-p", "/tmp/profile"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_encrypt")
    def test_encrypt_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "encrypt", "-i", "test.tokenade"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_decrypt")
    def test_decrypt_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "decrypt", "-i", "test.tokenade"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_rekey")
    def test_rekey_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "rekey", "-i", "test.tokenade"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_proxy")
    def test_proxy_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "proxy"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_sessions")
    def test_sessions_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "sessions", "list"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_health")
    def test_health_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "health"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_refresh")
    def test_refresh_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "refresh", "-s", "test.tokenade", "-b", "chrome"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_share")
    def test_share_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "share", "-s", "test.tokenade"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_unshare")
    def test_unshare_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "unshare", "some-id"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_batch_export")
    def test_batch_export_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "batch-export", "-s", "sites.json"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_batch_load")
    def test_batch_load_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "batch-load", "-d", "sessions/"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_validate")
    def test_validate_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "validate"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_validate_rules")
    def test_validate_rules_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "validate-rules", "-s", "test.tokenade", "-r", "rules.json"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_diff")
    def test_diff_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "diff", "a.tokenade", "b.tokenade"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_fingerprint")
    def test_fingerprint_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "fingerprint", "list"]):
            main()
        mock_cmd.assert_called_once()

    @patch("tokenade.cli.cmd_test")
    def test_test_dispatch(self, mock_cmd):
        from tokenade.cli import main
        with patch("sys.argv", ["tokenade", "test", "-s", "test.tokenade"]):
            main()
        mock_cmd.assert_called_once()


# ---------------------------------------------------------------------------
# Config file tests
# ---------------------------------------------------------------------------

class TestTokenadeConfig:
    """Config load/save/get/set/delete operations."""

    def test_defaults_when_no_file(self, tmp_path):
        from tokenade.cli.config import TokenadeConfig
        cfg_file = tmp_path / "config.json"
        cfg = TokenadeConfig(config_file=cfg_file)
        assert cfg.get("browser") == "chrome"
        assert cfg.get("proxy_port") == 9222
        assert cfg.get("nonexistent") is None
        assert cfg.get("nonexistent", "fallback") == "fallback"

    def test_set_and_get(self, tmp_path):
        from tokenade.cli.config import TokenadeConfig
        cfg_file = tmp_path / "config.json"
        cfg = TokenadeConfig(config_file=cfg_file)
        cfg.set("browser", "firefox")
        assert cfg.get("browser") == "firefox"
        assert cfg_file.exists()

    def test_persistence(self, tmp_path):
        from tokenade.cli.config import TokenadeConfig
        cfg_file = tmp_path / "config.json"
        cfg = TokenadeConfig(config_file=cfg_file)
        cfg.set("browser", "edge")
        cfg2 = TokenadeConfig(config_file=cfg_file)
        assert cfg2.get("browser") == "edge"

    def test_delete(self, tmp_path):
        from tokenade.cli.config import TokenadeConfig
        cfg_file = tmp_path / "config.json"
        cfg = TokenadeConfig(config_file=cfg_file)
        cfg.set("browser", "brave")
        cfg.delete("browser")
        # Key removed from active config; re-load to get defaults merged
        cfg2 = TokenadeConfig(config_file=cfg_file)
        assert cfg2.get("browser") == "chrome"

    def test_delete_nonexistent(self, tmp_path):
        from tokenade.cli.config import TokenadeConfig
        cfg_file = tmp_path / "config.json"
        cfg = TokenadeConfig(config_file=cfg_file)
        cfg.delete("nonexistent_key")

    def test_list_all(self, tmp_path):
        from tokenade.cli.config import TokenadeConfig
        cfg_file = tmp_path / "config.json"
        cfg = TokenadeConfig(config_file=cfg_file)
        all_cfg = cfg.list_all()
        assert isinstance(all_cfg, dict)
        assert "browser" in all_cfg
        assert "proxy_port" in all_cfg

    def test_list_all_returns_copy(self, tmp_path):
        from tokenade.cli.config import TokenadeConfig
        cfg_file = tmp_path / "config.json"
        cfg = TokenadeConfig(config_file=cfg_file)
        all_cfg = cfg.list_all()
        all_cfg["browser"] = "modified"
        assert cfg.get("browser") == "chrome"

    def test_corrupt_file_raises(self, tmp_path):
        from tokenade.cli.config import TokenadeConfig
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text("not valid json {{{")
        with pytest.raises(json.JSONDecodeError):
            TokenadeConfig(config_file=cfg_file)


# ---------------------------------------------------------------------------
# Output color function tests
# ---------------------------------------------------------------------------

class TestOutputHelpers:
    """CLI output color helpers."""

    def test_color_disabled_when_not_tty(self):
        from tokenade.cli import output
        original = output.COLOR_ENABLED
        try:
            output.COLOR_ENABLED = False
            result = output._color("32", "hello")
            assert result == "hello"
        finally:
            output.COLOR_ENABLED = original

    def test_color_enabled(self):
        from tokenade.cli import output
        original = output.COLOR_ENABLED
        try:
            output.COLOR_ENABLED = True
            result = output._color("32", "hello")
            assert result == "\033[32mhello\033[0m"
        finally:
            output.COLOR_ENABLED = original

    def test_success_output(self, capsys):
        from tokenade.cli import output
        original = output.COLOR_ENABLED
        try:
            output.COLOR_ENABLED = False
            output.success("done")
            captured = capsys.readouterr()
            assert "done" in captured.out
            assert "\u2713" in captured.out
        finally:
            output.COLOR_ENABLED = original

    def test_error_output(self, capsys):
        from tokenade.cli import output
        original = output.COLOR_ENABLED
        try:
            output.COLOR_ENABLED = False
            output.error("oops")
            captured = capsys.readouterr()
            assert "oops" in captured.err
            assert "\u2717" in captured.err
        finally:
            output.COLOR_ENABLED = original

    def test_warning_output(self, capsys):
        from tokenade.cli import output
        original = output.COLOR_ENABLED
        try:
            output.COLOR_ENABLED = False
            output.warning("careful")
            captured = capsys.readouterr()
            assert "careful" in captured.out
        finally:
            output.COLOR_ENABLED = original

    def test_info_output(self, capsys):
        from tokenade.cli import output
        original = output.COLOR_ENABLED
        try:
            output.COLOR_ENABLED = False
            output.info("fyi")
            captured = capsys.readouterr()
            assert "fyi" in captured.out
        finally:
            output.COLOR_ENABLED = original

    def test_heading_output(self, capsys):
        from tokenade.cli import output
        original = output.COLOR_ENABLED
        try:
            output.COLOR_ENABLED = False
            output.heading("Title")
            captured = capsys.readouterr()
            assert "Title" in captured.out
        finally:
            output.COLOR_ENABLED = original


# ---------------------------------------------------------------------------
# Shell completion tests
# ---------------------------------------------------------------------------

class TestShellCompletions:
    """Shell completion script generation and installation."""

    def test_bash_completion_contains_commands(self):
        from tokenade.cli.completions import BASH_COMPLETION
        assert "tokenade" in BASH_COMPLETION
        assert "export" in BASH_COMPLETION
        assert "run" in BASH_COMPLETION
        assert "encrypt" in BASH_COMPLETION
        assert "proxy" not in BASH_COMPLETION

    def test_zsh_completion_contains_commands(self):
        from tokenade.cli.completions import ZSH_COMPLETION
        assert "tokenade" in ZSH_COMPLETION
        assert "export" in ZSH_COMPLETION
        assert "run" in ZSH_COMPLETION
        assert "proxy" not in ZSH_COMPLETION

    def test_fish_completion_contains_commands(self):
        from tokenade.cli.completions import FISH_COMPLETION
        assert "tokenade" in FISH_COMPLETION
        assert "export" in FISH_COMPLETION
        assert "run" in FISH_COMPLETION
        assert "proxy" not in FISH_COMPLETION

    def test_install_bash(self, tmp_path, monkeypatch):
        from tokenade.cli.completions import install_completion
        monkeypatch.setenv("HOME", str(tmp_path))
        install_completion("bash")
        comp_file = tmp_path / ".bash_completion.d" / "tokenade"
        assert comp_file.exists()
        content = comp_file.read_text()
        assert "tokenade" in content

    def test_install_zsh(self, tmp_path, monkeypatch):
        from tokenade.cli.completions import install_completion
        monkeypatch.setenv("HOME", str(tmp_path))
        install_completion("zsh")
        comp_file = tmp_path / ".zsh" / "completions" / "_tokenade"
        assert comp_file.exists()

    def test_install_fish(self, tmp_path, monkeypatch):
        from tokenade.cli.completions import install_completion
        monkeypatch.setenv("HOME", str(tmp_path))
        install_completion("fish")
        comp_file = tmp_path / ".config" / "fish" / "completions" / "tokenade.fish"
        assert comp_file.exists()
