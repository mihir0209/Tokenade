"""
Unit tests for CLI commands.
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tokenade.cli import setup_logging, main
from tokenade.cli.advanced import cmd_fingerprint, cmd_validate


class TestSetupLogging(unittest.TestCase):
    """Test logging setup."""

    def test_verbose_logging(self):
        """Test verbose logging sets DEBUG level."""
        with patch('tokenade.cli.logging.getLogger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            setup_logging(verbose=True)
            mock_logger.setLevel.assert_called_once_with(10)  # DEBUG

    def test_normal_logging(self):
        """Test normal logging sets INFO level."""
        with patch('tokenade.cli.logging.getLogger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            setup_logging(verbose=False)
            mock_logger.setLevel.assert_called_once_with(20)  # INFO


class TestCmdFingerprint(unittest.TestCase):
    """Test fingerprint command."""

    def setUp(self):
        self.args = MagicMock()

    @patch('tokenade.core.fingerprint.manager.FingerprintManager')
    def test_list_empty(self, mock_fp_manager):
        """Test listing fingerprints when none exist."""
        mock_instance = MagicMock()
        mock_instance.list.return_value = []
        mock_fp_manager.return_value = mock_instance

        self.args.action = "list"

        with patch('builtins.print') as mock_print:
            cmd_fingerprint(self.args)
            mock_print.assert_any_call("\n📋 Stored fingerprints:")

    @patch('tokenade.core.fingerprint.manager.FingerprintManager')
    def test_list_with_fingerprints(self, mock_fp_manager):
        """Test listing fingerprints."""
        mock_instance = MagicMock()
        mock_instance.list.return_value = ["desktop", "laptop"]
        mock_fp_manager.return_value = mock_instance

        self.args.action = "list"

        with patch('builtins.print') as mock_print:
            cmd_fingerprint(self.args)
            mock_print.assert_any_call("   • desktop")
            mock_print.assert_any_call("   • laptop")

    @patch('tokenade.core.fingerprint.manager.FingerprintManager')
    def test_show_found(self, mock_fp_manager):
        """Test showing existing fingerprint."""
        from tokenade.core.fingerprint.manager import BrowserFingerprint

        mock_instance = MagicMock()
        fp = BrowserFingerprint(
            user_agent="Mozilla/5.0",
            screen_width=1920,
            screen_height=1080
        )
        mock_instance.load.return_value = fp
        mock_fp_manager.return_value = mock_instance

        self.args.action = "show"
        self.args.name = "test_fp"

        with patch('builtins.print') as mock_print:
            cmd_fingerprint(self.args)
            mock_print.assert_any_call("\n🔍 Fingerprint: test_fp")

    @patch('tokenade.core.fingerprint.manager.FingerprintManager')
    def test_show_not_found(self, mock_fp_manager):
        """Test showing non-existent fingerprint."""
        mock_instance = MagicMock()
        mock_instance.load.return_value = None
        mock_fp_manager.return_value = mock_instance

        self.args.action = "show"
        self.args.name = "missing"

        with patch('builtins.print') as mock_print:
            cmd_fingerprint(self.args)
            mock_print.assert_any_call("❌ Fingerprint not found: missing")

    @patch('tokenade.core.fingerprint.manager.FingerprintManager')
    def test_delete_success(self, mock_fp_manager):
        """Test deleting fingerprint."""
        mock_instance = MagicMock()
        mock_instance.delete.return_value = True
        mock_fp_manager.return_value = mock_instance

        self.args.action = "delete"
        self.args.name = "test_fp"

        with patch('builtins.print') as mock_print:
            cmd_fingerprint(self.args)
            mock_print.assert_any_call("✅ Deleted: test_fp")

    @patch('tokenade.core.fingerprint.manager.FingerprintManager')
    def test_delete_not_found(self, mock_fp_manager):
        """Test deleting non-existent fingerprint."""
        mock_instance = MagicMock()
        mock_instance.delete.return_value = False
        mock_fp_manager.return_value = mock_instance

        self.args.action = "delete"
        self.args.name = "missing"

        with patch('builtins.print') as mock_print:
            cmd_fingerprint(self.args)
            mock_print.assert_any_call("❌ Not found: missing")


class TestCmdValidate(unittest.TestCase):
    """Test validate command."""

    def setUp(self):
        self.args = MagicMock()
        self.args.sessions_dir = "sessions"

    @patch('tokenade.cli.advanced.Path')
    def test_directory_not_found(self, mock_path):
        """Test when sessions directory doesn't exist."""
        mock_instance = MagicMock()
        mock_instance.exists.return_value = False
        mock_path.return_value = mock_instance

        with patch('builtins.print') as mock_print:
            cmd_validate(self.args)
            mock_print.assert_any_call("❌ Directory not found: sessions")

    @patch('tokenade.cli.advanced.Path')
    def test_valid_session(self, mock_path):
        """Test validating a valid session file."""
        mock_dir = MagicMock()
        mock_dir.exists.return_value = True
        mock_dir.glob.return_value = [Path("test_session.json")]
        mock_path.return_value = mock_dir

        session_data = {
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [{"name": "SID", "value": "test"}],
            "tokens": [{"token_type": "oauth", "token_value": "abc"}]
        }

        with patch('builtins.open', mock_open(read_data=json.dumps(session_data))):
            with patch('builtins.print') as mock_print:
                cmd_validate(self.args)
                mock_print.assert_any_call("   ✅ Status: logged_in")


class TestMain(unittest.TestCase):
    """Test main entry point."""

    @patch('tokenade.cli.argparse.ArgumentParser')
    def test_no_command(self, mock_parser_class):
        """Test exit when no command provided."""
        mock_parser = MagicMock()
        mock_parser.parse_args.return_value = MagicMock(command=None)
        mock_parser_class.return_value = mock_parser

        with self.assertRaises(SystemExit) as cm:
            main()
        self.assertEqual(cm.exception.code, 1)

    @patch('tokenade.cli.argparse.ArgumentParser')
    @patch('tokenade.cli.cmd_setup')
    def test_setup_command(self, mock_cmd_setup, mock_parser_class):
        """Test setup command dispatch."""
        mock_parser = MagicMock()
        mock_args = MagicMock()
        mock_args.command = "setup"
        mock_args.verbose = False
        mock_parser.parse_args.return_value = mock_args
        mock_parser_class.return_value = mock_parser

        main()
        mock_cmd_setup.assert_called_once()


if __name__ == "__main__":
    unittest.main()
