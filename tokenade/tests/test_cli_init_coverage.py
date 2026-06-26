"""Tests for uncovered lines in tokenade/cli/__init__.py (lines 18-55, 60-126, 131-186, 528-540)."""
import unittest
from io import StringIO
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# cmd_config (lines 18-55)
# ---------------------------------------------------------------------------
class TestCmdConfig(unittest.TestCase):
    """Test the cmd_config function."""

    def _make_args(self, config_command, key=None, value=None):
        args = MagicMock()
        args.config_command = config_command
        args.key = key
        args.value = value
        return args

    @patch("tokenade.core.config.load_config")
    def test_path(self, mock_load):
        mock_config = MagicMock()
        mock_config.config_path = "/tmp/test.json"
        mock_load.return_value = mock_config

        from tokenade.cli import cmd_config
        args = self._make_args("path")

        with patch("builtins.print") as mock_print:
            cmd_config(args)
            mock_print.assert_called_once_with("/tmp/test.json")

    @patch("tokenade.core.config.load_config")
    def test_show(self, mock_load):
        mock_config = MagicMock()
        mock_config.config_path = "/tmp/test.json"
        mock_config.get.return_value = "val"
        mock_load.return_value = mock_config

        from tokenade.cli import cmd_config
        args = self._make_args("show")

        with patch("builtins.print") as mock_print, \
             patch("tokenade.core.config.DEFAULTS", {"key_a": "default", "key_b": "other"}):
            cmd_config(args)
            self.assertTrue(mock_print.call_count >= 3)

    @patch("tokenade.core.config.load_config")
    def test_get_with_key(self, mock_load):
        mock_config = MagicMock()
        mock_config.get.return_value = "some_value"
        mock_load.return_value = mock_config

        from tokenade.cli import cmd_config
        args = self._make_args("get", key="my_key")

        with patch("builtins.print") as mock_print:
            cmd_config(args)
            mock_print.assert_called_once_with("some_value")

    @patch("tokenade.core.config.load_config")
    def test_get_without_key(self, mock_load):
        mock_config = MagicMock()
        mock_config.config_path = "/tmp/test.json"
        mock_config.get.return_value = None
        mock_load.return_value = mock_config

        from tokenade.cli import cmd_config
        args = self._make_args("get", key=None)

        with patch("builtins.print") as mock_print:
            cmd_config(args)
            printed = mock_print.call_args[0][0]
            self.assertIn("Usage", printed)

    @patch("tokenade.core.config.load_config")
    def test_get_unknown_key(self, mock_load):
        mock_config = MagicMock()
        mock_config.config_path = "/tmp/test.json"
        mock_config.get.return_value = None
        mock_load.return_value = mock_config

        from tokenade.cli import cmd_config
        args = self._make_args("get", key="unknown")

        with patch("builtins.print") as mock_print:
            cmd_config(args)
            printed = mock_print.call_args[0][0]
            self.assertIn("Unknown", printed)

    @patch("tokenade.core.config.load_config")
    def test_set_valid_key_and_value(self, mock_load):
        mock_config = MagicMock()
        mock_config.config_path = "/tmp/test.json"
        mock_config.get.return_value = None
        mock_load.return_value = mock_config

        from tokenade.cli import cmd_config
        args = self._make_args("set", key="my_key", value="my_value")

        with patch("builtins.print") as mock_print:
            cmd_config(args)
            mock_config.set.assert_called_once_with("my_key", "my_value")
            mock_config.save.assert_called_once()
            printed = mock_print.call_args[0][0]
            self.assertIn("my_key", printed)

    @patch("tokenade.core.config.load_config")
    def test_set_without_key(self, mock_load):
        mock_config = MagicMock()
        mock_config.config_path = "/tmp/test.json"
        mock_config.get.return_value = None
        mock_load.return_value = mock_config

        from tokenade.cli import cmd_config
        args = self._make_args("set", key=None, value=None)

        with patch("builtins.print") as mock_print:
            cmd_config(args)
            printed = mock_print.call_args[0][0]
            self.assertIn("Usage", printed)

    @patch("tokenade.core.config.load_config")
    def test_set_bool_true(self, mock_load):
        mock_config = MagicMock()
        mock_config.config_path = "/tmp/test.json"
        mock_config.get.return_value = None
        mock_load.return_value = mock_config

        from tokenade.cli import cmd_config
        args = self._make_args("set", key="flag", value="true")

        with patch("builtins.print"):
            cmd_config(args)
            mock_config.set.assert_called_once_with("flag", True)
            mock_config.save.assert_called_once()

    @patch("tokenade.core.config.load_config")
    def test_set_bool_false(self, mock_load):
        mock_config = MagicMock()
        mock_config.config_path = "/tmp/test.json"
        mock_config.get.return_value = None
        mock_load.return_value = mock_config

        from tokenade.cli import cmd_config
        args = self._make_args("set", key="flag", value="false")

        with patch("builtins.print"):
            cmd_config(args)
            mock_config.set.assert_called_once_with("flag", False)

    @patch("tokenade.core.config.load_config")
    def test_set_int_value(self, mock_load):
        mock_config = MagicMock()
        mock_config.config_path = "/tmp/test.json"
        mock_config.get.return_value = None
        mock_load.return_value = mock_config

        from tokenade.cli import cmd_config
        args = self._make_args("set", key="port", value="8080")

        with patch("builtins.print"):
            cmd_config(args)
            mock_config.set.assert_called_once_with("port", 8080)

    @patch("tokenade.core.config.load_config")
    def test_set_string_value(self, mock_load):
        mock_config = MagicMock()
        mock_config.config_path = "/tmp/test.json"
        mock_config.get.return_value = None
        mock_load.return_value = mock_config

        from tokenade.cli import cmd_config
        args = self._make_args("set", key="name", value="hello_world")

        with patch("builtins.print"):
            cmd_config(args)
            mock_config.set.assert_called_once_with("name", "hello_world")


# ---------------------------------------------------------------------------
# cmd_completion (lines 60-126)
# ---------------------------------------------------------------------------
class TestCmdCompletion(unittest.TestCase):
    """Test the cmd_completion function."""

    def _make_args(self, shell):
        args = MagicMock()
        args.shell = shell
        return args

    def test_bash(self):
        from tokenade.cli import cmd_completion
        args = self._make_args("bash")
        out = StringIO()
        with patch("sys.stdout", out):
            cmd_completion(args)
        self.assertIn("complete -F _tokenade tokenade", out.getvalue())

    def test_zsh(self):
        from tokenade.cli import cmd_completion
        args = self._make_args("zsh")
        out = StringIO()
        with patch("sys.stdout", out):
            cmd_completion(args)
        self.assertIn("compdef _tokenade tokenade", out.getvalue())

    def test_fish(self):
        from tokenade.cli import cmd_completion
        args = self._make_args("fish")
        out = StringIO()
        with patch("sys.stdout", out):
            cmd_completion(args)
        self.assertIn("complete -c tokenade", out.getvalue())

    def test_unsupported_shell_exits(self):
        from tokenade.cli import cmd_completion
        args = self._make_args("powershell")
        with self.assertRaises(SystemExit) as cm:
            cmd_completion(args)
        self.assertEqual(cm.exception.code, 1)

    def test_unsupported_shell_message(self):
        from tokenade.cli import cmd_completion
        args = self._make_args("powershell")
        out = StringIO()
        with patch("sys.stdout", out), self.assertRaises(SystemExit):
            cmd_completion(args)
        self.assertIn("Unsupported shell", out.getvalue())


# ---------------------------------------------------------------------------
# cmd_plugin (lines 131-186)
# ---------------------------------------------------------------------------
class TestCmdPlugin(unittest.TestCase):
    """Test the cmd_plugin function."""

    def _make_args(self, plugin_command, name=None, available=False):
        args = MagicMock()
        args.plugin_command = plugin_command
        args.name = name
        args.available = available
        return args

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    @patch("tokenade.core.integration.plugin_registry.PluginRegistry")
    def test_list_installed(self, MockReg, MockLoader):
        mock_loader = MagicMock()
        mock_loader.discover.return_value = [
            {"name": "p1", "version": "1.0", "type": "ext", "description": "A plugin"},
        ]
        MockLoader.return_value = mock_loader

        from tokenade.cli import cmd_plugin
        args = self._make_args("list", available=False)

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        self.assertIn("Installed plugins", out.getvalue())
        self.assertIn("p1", out.getvalue())

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    @patch("tokenade.core.integration.plugin_registry.PluginRegistry")
    def test_list_installed_empty(self, MockReg, MockLoader):
        mock_loader = MagicMock()
        mock_loader.discover.return_value = []
        MockLoader.return_value = mock_loader

        from tokenade.cli import cmd_plugin
        args = self._make_args("list", available=False)

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        self.assertIn("No plugins installed", out.getvalue())

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    @patch("tokenade.core.integration.plugin_registry.PluginRegistry")
    def test_list_available(self, MockReg, MockLoader):
        mock_registry = MagicMock()
        mock_registry.search.return_value = [
            {"name": "r1", "version": "2.0", "description": "Registry plugin"},
        ]
        MockReg.return_value = mock_registry

        from tokenade.cli import cmd_plugin
        args = self._make_args("list", available=True)

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        self.assertIn("Available plugins", out.getvalue())
        self.assertIn("r1", out.getvalue())

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    @patch("tokenade.core.integration.plugin_registry.PluginRegistry")
    def test_list_available_empty(self, MockReg, MockLoader):
        mock_registry = MagicMock()
        mock_registry.search.return_value = []
        MockReg.return_value = mock_registry

        from tokenade.cli import cmd_plugin
        args = self._make_args("list", available=True)

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        self.assertIn("No plugins found", out.getvalue())

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    @patch("tokenade.core.integration.plugin_registry.PluginRegistry")
    def test_install_success(self, MockReg, MockLoader):
        mock_registry = MagicMock()
        mock_registry.install.return_value = True
        MockReg.return_value = mock_registry

        from tokenade.cli import cmd_plugin
        args = self._make_args("install", name="my_plugin")

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        mock_registry.install.assert_called_once_with("my_plugin")
        self.assertIn("installed successfully", out.getvalue())

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    @patch("tokenade.core.integration.plugin_registry.PluginRegistry")
    def test_install_failure(self, MockReg, MockLoader):
        mock_registry = MagicMock()
        mock_registry.install.return_value = False
        MockReg.return_value = mock_registry

        from tokenade.cli import cmd_plugin
        args = self._make_args("install", name="my_plugin")

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        self.assertIn("Failed to install", out.getvalue())

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    @patch("tokenade.core.integration.plugin_registry.PluginRegistry")
    def test_uninstall_success(self, MockReg, MockLoader):
        mock_registry = MagicMock()
        mock_registry.uninstall.return_value = True
        MockReg.return_value = mock_registry

        from tokenade.cli import cmd_plugin
        args = self._make_args("uninstall", name="my_plugin")

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        mock_registry.uninstall.assert_called_once_with("my_plugin")
        self.assertIn("uninstalled successfully", out.getvalue())

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    @patch("tokenade.core.integration.plugin_registry.PluginRegistry")
    def test_uninstall_failure(self, MockReg, MockLoader):
        mock_registry = MagicMock()
        mock_registry.uninstall.return_value = False
        MockReg.return_value = mock_registry

        from tokenade.cli import cmd_plugin
        args = self._make_args("uninstall", name="my_plugin")

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        self.assertIn("Failed to uninstall", out.getvalue())

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    @patch("tokenade.core.integration.plugin_registry.PluginRegistry")
    def test_info_found(self, MockReg, MockLoader):
        mock_loader = MagicMock()
        mock_loader.discover.return_value = [
            {
                "name": "my_plugin",
                "version": "1.0",
                "type": "ext",
                "author": "Test Author",
                "description": "A test plugin",
                "dependencies": ["dep1", "dep2"],
            },
        ]
        MockLoader.return_value = mock_loader

        from tokenade.cli import cmd_plugin
        args = self._make_args("info", name="my_plugin")

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        self.assertIn("Plugin: my_plugin", out.getvalue())
        self.assertIn("1.0", out.getvalue())
        self.assertIn("dep1", out.getvalue())

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    @patch("tokenade.core.integration.plugin_registry.PluginRegistry")
    def test_info_not_found(self, MockReg, MockLoader):
        mock_loader = MagicMock()
        mock_loader.discover.return_value = []
        MockLoader.return_value = mock_loader
        mock_reg = MagicMock()
        mock_reg.get_plugin_details.return_value = None
        MockReg.return_value = mock_reg

        from tokenade.cli import cmd_plugin
        args = self._make_args("info", name="nonexistent")

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        self.assertIn("not found", out.getvalue())

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    @patch("tokenade.core.integration.plugin_registry.PluginRegistry")
    def test_info_no_dependencies(self, MockReg, MockLoader):
        mock_loader = MagicMock()
        mock_loader.discover.return_value = [
            {
                "name": "simple_plugin",
                "version": "1.0",
                "type": "ext",
                "author": "Author",
                "description": "Simple",
            },
        ]
        MockLoader.return_value = mock_loader

        from tokenade.cli import cmd_plugin
        args = self._make_args("info", name="simple_plugin")

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        self.assertIn("simple_plugin", out.getvalue())
        self.assertNotIn("Dependencies", out.getvalue())

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    @patch("tokenade.core.integration.plugin_registry.PluginRegistry")
    def test_else_branch(self, MockReg, MockLoader):
        from tokenade.cli import cmd_plugin
        args = self._make_args("invalid_command")

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        self.assertIn("Usage", out.getvalue())

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    @patch("tokenade.core.integration.plugin_registry.PluginRegistry")
    def test_enable_success(self, MockReg, MockLoader):
        mock_loader = MagicMock()
        mock_loader.enable.return_value = True
        MockLoader.return_value = mock_loader

        from tokenade.cli import cmd_plugin
        args = self._make_args("enable", name="my_plugin")

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        mock_loader.enable.assert_called_once_with("my_plugin")
        self.assertIn("enabled", out.getvalue())

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    @patch("tokenade.core.integration.plugin_registry.PluginRegistry")
    def test_enable_not_found(self, MockReg, MockLoader):
        mock_loader = MagicMock()
        mock_loader.enable.return_value = False
        MockLoader.return_value = mock_loader

        from tokenade.cli import cmd_plugin
        args = self._make_args("enable", name="nonexistent")

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        self.assertIn("not found", out.getvalue())

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    @patch("tokenade.core.integration.plugin_registry.PluginRegistry")
    def test_disable_success(self, MockReg, MockLoader):
        mock_loader = MagicMock()
        mock_loader.disable.return_value = True
        MockLoader.return_value = mock_loader

        from tokenade.cli import cmd_plugin
        args = self._make_args("disable", name="my_plugin")

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        mock_loader.disable.assert_called_once_with("my_plugin")
        self.assertIn("disabled", out.getvalue())

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    @patch("tokenade.core.integration.plugin_registry.PluginRegistry")
    def test_disable_not_found(self, MockReg, MockLoader):
        mock_loader = MagicMock()
        mock_loader.disable.return_value = False
        MockLoader.return_value = mock_loader

        from tokenade.cli import cmd_plugin
        args = self._make_args("disable", name="nonexistent")

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        self.assertIn("not found", out.getvalue())

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    @patch("tokenade.core.integration.plugin_registry.PluginRegistry")
    def test_reload_success(self, MockReg, MockLoader):
        mock_loader = MagicMock()
        mock_plugin = MagicMock()
        mock_plugin.version = "1.0"
        mock_loader.reload.return_value = mock_plugin
        MockLoader.return_value = mock_loader

        from tokenade.cli import cmd_plugin
        args = self._make_args("reload", name="my_plugin")

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        self.assertIn("reloaded", out.getvalue())

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    @patch("tokenade.core.integration.plugin_registry.PluginRegistry")
    def test_reload_failure(self, MockReg, MockLoader):
        mock_loader = MagicMock()
        mock_loader.reload.return_value = None
        MockLoader.return_value = mock_loader

        from tokenade.cli import cmd_plugin
        args = self._make_args("reload", name="nonexistent")

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        self.assertIn("Failed", out.getvalue())


# ---------------------------------------------------------------------------
# main() error handling (lines 528-540)
# ---------------------------------------------------------------------------
class TestMainErrorHandling(unittest.TestCase):
    """Test the main() function error handling branches (lines 528-540)."""

    def test_keyboard_interrupt(self):
        with patch("sys.argv", ["tokenade", "config", "path"]), \
             patch("tokenade.cli.cmd_config", side_effect=KeyboardInterrupt), \
             patch("sys.exit") as mock_exit:
            from tokenade.cli import main
            main()
            mock_exit.assert_called_once_with(130)

    def test_tokenade_error(self):
        from tokenade.core.errors import TokenadeError

        err = TokenadeError("test error message")
        out = StringIO()
        with patch("sys.argv", ["tokenade", "config", "path"]), \
             patch("tokenade.cli.cmd_config", side_effect=err), \
             patch("sys.exit") as mock_exit, \
             patch("sys.stdout", out):
            from tokenade.cli import main
            main()
            mock_exit.assert_called_once_with(1)
            self.assertIn("test error message", out.getvalue())

    def test_generic_exception(self):
        err = RuntimeError("something broke")
        out = StringIO()
        with patch("sys.argv", ["tokenade", "config", "path"]), \
             patch("tokenade.cli.cmd_config", side_effect=err), \
             patch("sys.exit") as mock_exit, \
             patch("sys.stdout", out):
            from tokenade.cli import main
            main()
            mock_exit.assert_called_once_with(1)
            output = out.getvalue()
            self.assertIn("something broke", output)
            self.assertIn("Unexpected error", output)


# ---------------------------------------------------------------------------
# cmd_plugin → plugin test (Phase 48)
# ---------------------------------------------------------------------------
class TestCmdPluginTest(unittest.TestCase):
    """Test the plugin test CLI command."""

    def test_plugin_test_no_plugins(self):
        """plugin test with no plugins prints message."""
        from tokenade.cli import _plugin_test
        from tokenade.core.integration.plugin_testing import PluginTestRunner
        args = MagicMock()
        args.name = None
        with patch.object(PluginTestRunner, 'test_all', return_value=[]):
            out = StringIO()
            with patch("sys.stdout", out):
                _plugin_test(args)
            self.assertIn("No plugins found", out.getvalue())

    def test_plugin_test_single_pass(self):
        """plugin test with a single passing plugin."""
        from tokenade.cli import _plugin_test
        from tokenade.core.integration.plugin_testing import PluginTestSuite, PluginTestResult
        args = MagicMock()
        args.name = "my-plugin"
        suite = PluginTestSuite(
            plugin_name="my-plugin",
            results=[
                PluginTestResult("manifest_exists", True),
                PluginTestResult("entry_point_exists", True),
            ],
        )
        with patch("tokenade.core.integration.plugin_testing.PluginTestRunner.test_plugin", return_value=suite):
            out = StringIO()
            with patch("sys.stdout", out):
                _plugin_test(args)
            self.assertIn("2 passed", out.getvalue())
            self.assertIn("✓", out.getvalue())

    def test_plugin_test_single_fail(self):
        """plugin test with a failing plugin."""
        from tokenade.cli import _plugin_test
        from tokenade.core.integration.plugin_testing import PluginTestSuite, PluginTestResult
        args = MagicMock()
        args.name = "bad-plugin"
        suite = PluginTestSuite(
            plugin_name="bad-plugin",
            results=[
                PluginTestResult("manifest_exists", True),
                PluginTestResult("entry_point_exists", False, "file missing"),
            ],
        )
        with patch("tokenade.core.integration.plugin_testing.PluginTestRunner.test_plugin", return_value=suite):
            out = StringIO()
            with patch("sys.stdout", out):
                _plugin_test(args)
            self.assertIn("1 failed", out.getvalue())
            self.assertIn("✗", out.getvalue())
            self.assertIn("file missing", out.getvalue())


if __name__ == "__main__":
    unittest.main()
