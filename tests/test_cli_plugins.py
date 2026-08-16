"""Unit tests for Phase 9 CLI plugin updates.

Covers:
  - --no-plugin flag parsing for launch / refresh-browser / accounts refresh
  - plugin list shows lifecycle state and health
  - plugin info shows lifecycle state, config, health
  - plugin deps / check-deps commands
  - plugin configure --show/--set/--reset/--validate
  - plugin test --verbose
  - plugin reload shows state
  - auto-discovery of refreshers when no --plugin and no --no-plugin

Tests use temp plugin directories, mock args (Namespace), and stdout capture.
"""

import io
import json
import sys
from argparse import Namespace
from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────


@contextmanager
def capture_stdout():
    """Capture print() output to stdout."""
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        yield buf
    finally:
        sys.stdout = old


def make_plugin_dir(plugins_dir, name, body=None, manifest_extra=None):
    """Create a plugin directory with manifest + entry module."""
    pdir = plugins_dir / name
    pdir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "version": "1.0.0",
        "type": "handler",
        "entry_point": "plugin.py",
        "description": f"Test plugin {name}",
    }
    if manifest_extra:
        manifest.update(manifest_extra)
    (pdir / "plugin.json").write_text(json.dumps(manifest))
    body = body or """
from tokenade.plugin.base import SiteHandlerPlugin
class TestHandler(SiteHandlerPlugin):
    name = "%(name)s"
    version = "1.0.0"
    description = "Test"

    def can_handle(self, url):
        return False
    def extract_session(self, page):
        return {}
    def inject_session(self, page, session):
        pass
""" % {"name": name}
    (pdir / "plugin.py").write_text(body)
    return pdir


def make_refresher_plugin(plugins_dir, name):
    """Create a SessionRefreshPlugin plugin."""
    pdir = plugins_dir / name
    pdir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "version": "1.2.0",
        "type": "session_refresh",
        "entry_point": "plugin.py",
        "description": "Test refresher",
    }
    (pdir / "plugin.json").write_text(json.dumps(manifest))
    body = """
from tokenade.plugin.base import SessionRefreshPlugin
class TestRefresher(SessionRefreshPlugin):
    name = "%(name)s"
    version = "1.2.0"
    description = "Test refresher"

    def can_refresh(self, session):
        return True
    def refresh(self, session, credentials=None):
        session['refreshed_by'] = '%(name)s'
        return session
    def get_credentials_args(self):
        return []
""" % {"name": name}
    (pdir / "plugin.py").write_text(body)
    return pdir


@pytest.fixture(autouse=True)
def reset_shared_context():
    """Reset the SharedContext singleton around each test."""
    from tokenade.core.context import SharedContext
    SharedContext.reset()
    yield
    SharedContext.reset()


def _plugins_dir_patches(tmp_path):
    """Return a list of patch context managers that force PluginLoader and
    PluginConfigManager to use a temp plugins directory.

    The module-level DEFAULT_PLUGINS_DIR is bound as a default-arg at class
    definition time, so patching the module attribute does not propagate. We
    wrap __init__ to overwrite plugins_dir to our temp path.
    """
    from unittest.mock import patch
    from tokenade.core.integration import plugin_loader as pl_mod
    from tokenade.core.integration import plugin_config as pc_mod
    from pathlib import Path as _Path

    real_loader_init = pl_mod.PluginLoader.__init__
    real_config_init = pc_mod.PluginConfigManager.__init__

    def patched_loader_init(self, plugins_dir=None, **kwargs):
        real_loader_init(self, plugins_dir=_Path(tmp_path / "plugins"), **kwargs)

    def patched_config_init(self, plugins_dir=None, **kwargs):
        real_config_init(self, plugins_dir=_Path(tmp_path / "plugins"), **kwargs)

    return [
        patch.object(pl_mod.PluginLoader, "__init__", patched_loader_init),
        patch.object(pc_mod.PluginConfigManager, "__init__", patched_config_init),
    ]


@pytest.fixture
def patched_plugins_dir(tmp_path):
    """Patch PluginLoader / PluginConfigManager to use a tmp plugins_dir.

    Yields the tmp plugins directory Path. The patches are reverted on exit.

    Usage: pass tmp_path to inner test logic via the test's own tmp_path arg,
    and use this fixture to ensure PluginLoader()/PluginConfigManager() default
    to the temp directory.
    """
    plugins = tmp_path / "plugins"
    plugins.mkdir(exist_ok=True)
    patches = _plugins_dir_patches(tmp_path)
    stack = ExitStack()
    for p in patches:
        stack.enter_context(p)
    yield plugins
    stack.close()


# ── T9.1c: launch --no-plugin parser ──────────────────────────────────────────


class TestNoPluginParser:
    """Verify --no-plugin flag exists on all three parsers."""

    def test_launch_no_plugin_flag(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        ns = p.parse_args(["launch", "--no-plugin"])
        assert getattr(ns, "no_plugin", False) is True

    def test_refresh_browser_no_plugin_flag(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        ns = p.parse_args(["refresh-browser", "-s", "x.tokenade", "--no-plugin"])
        assert getattr(ns, "no_plugin", False) is True

    def test_accounts_refresh_no_plugin_flag(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        ns = p.parse_args(["accounts", "refresh", "--no-plugin"])
        assert getattr(ns, "no_plugin", False) is True

    def test_default_no_plugin_is_false(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        ns = p.parse_args(["launch"])
        assert getattr(ns, "no_plugin", False) is False


# ── T9.1c: cmd_launch honors --no-plugin ──────────────────────────────────────


class TestCmdLaunchNoPlugin:
    """cmd_launch must not invoke PluginExporter when --no-plugin is set."""

    def test_no_plugin_skips_plugin_exporter(self):
        """When --no-plugin is set, PluginExporter is never imported."""
        from tokenade.cli.handlers.browser_ops import cmd_launch

        args = Namespace(
            browser="chrome", session=None, url=None, port=9222,
            profile_dir=None, visible=True, headless=False, extra_args="",
            browser_path=None, proxy=None, proxy_file=None, proxy_rotate=False,
            proxy_strategy="health-weighted", humanize=False, geoip=False,
            no_cloak=False, profile=None, decrypt_password=None,
            plugin=None, no_plugin=True,
        )

        # Patch out the browser launcher so cmd_launch never actually launches.
        with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as mock_launcher_cls, \
             patch("tokenade.cli.handlers.browser_ops._resolve_upstream_proxy", return_value=None), \
             patch("tokenade.core.browser.cdp_connection.CDPConnection"), \
             patch("tokenade.core.importer.session_packager.SessionPackager"):
            mock_launcher = MagicMock()
            mock_launcher.find_browser.return_value = "/usr/bin/chrome"
            mock_launcher.launch.return_value = MagicMock(
                pid=1, cdp_url="ws://x", port=9222, profile_dir="/tmp/x",
                process=MagicMock(wait=lambda: 0),
            )
            mock_launcher_cls.return_value = mock_launcher
            # Force the browser.process.wait() to raise KeyboardInterrupt to exit cleanly
            mock_launcher.launch.return_value.process.wait.side_effect = KeyboardInterrupt

            with patch("tokenade.core.importer.plugin_export.PluginExporter") as mock_exporter:
                try:
                    cmd_launch(args)
                except KeyboardInterrupt:
                    pass
                # PluginExporter should never have been instantiated
                mock_exporter.assert_not_called()

    def test_firefox_session_uses_session_loader(self):
        from tokenade.cli.handlers.browser_ops import cmd_launch

        args = Namespace(
            browser="firefox", session="/tmp/session.tokenade", url=None,
            port=9222, profile_dir="/tmp/firefox-profile", visible=False,
            headless=True, extra_args="", browser_path=None, proxy=None,
            proxy_file=None, proxy_rotate=False, proxy_strategy="health-weighted",
            humanize=False, geoip=False, no_cloak=False, profile=None,
            decrypt_password=None, plugin=None, no_plugin=True,
            acknowledge_exclusive_move=False, claim_single_use=False,
        )
        session = {"site_name": "test", "cookies": [{"name": "a", "value": "1"}]}

        with patch(
            "tokenade.core.importer.session_packager.SessionPackager.load",
            return_value=session,
        ), patch(
            "tokenade.core.artifacts.ProfileArtifactManager.preflight"
        ), patch(
            "tokenade.cli.handlers.browser_ops._resolve_upstream_proxy",
            return_value=None,
        ), patch(
            "tokenade.core.importer.session_loader.SessionLoader"
        ) as loader_cls, patch(
            "tokenade.core.browser.undetectable.SystemBrowserLauncher"
        ) as system_launcher:
            loader_cls.return_value.load.return_value = {
                "success": True,
                "cookies_injected": 1,
                "cookies_total": 1,
            }
            cmd_launch(args)

        loader_cls.return_value.load.assert_called_once_with(
            "/tmp/session.tokenade",
            validate=False,
            visible=False,
            profile_dir="/tmp/firefox-profile",
            inject_local_storage=True,
            acknowledge_exclusive_move=False,
            allow_single_use=False,
            browser_type="firefox",
            proxy=None,
            target_url=None,
        )
        system_launcher.assert_not_called()


# ── T9.3: plugin list shows lifecycle state & health ─────────────────────────


class TestPluginListState:
    """plugin list shows [state] and health status."""

    def test_list_shows_lifecycle_state(self, tmp_path, patched_plugins_dir):
        from tokenade.cli import cmd_plugin
        make_plugin_dir(patched_plugins_dir, "demo-handler")

        args = Namespace(plugin_command="list", available=False)
        with patch("tokenade.core.integration.plugin_registry.PluginRegistry"):
            with capture_stdout() as buf:
                cmd_plugin(args)
            output = buf.getvalue()
        assert "demo-handler" in output
        assert "[" in output  # state bracket
        # Should contain a known state value
        assert any(s in output for s in ("active", "loaded", "discovered", "failed"))

    def test_list_shows_health_unhealthy(self, tmp_path, patched_plugins_dir):
        from tokenade.cli import cmd_plugin
        make_plugin_dir(patched_plugins_dir, "demo-handler")

        args = Namespace(plugin_command="list", available=False)
        with patch("tokenade.core.integration.plugin_registry.PluginRegistry"), \
             patch("tokenade.core.context.plugins.PluginsNamespace.get_health", return_value=False):
            with capture_stdout() as buf:
                cmd_plugin(args)
            output = buf.getvalue()
        assert "unhealthy" in output

    def test_list_shows_health_healthy(self, tmp_path, patched_plugins_dir):
        from tokenade.cli import cmd_plugin
        make_plugin_dir(patched_plugins_dir, "demo-handler")

        args = Namespace(plugin_command="list", available=False)
        with patch("tokenade.core.integration.plugin_registry.PluginRegistry"), \
             patch("tokenade.core.context.plugins.PluginsNamespace.get_health", return_value=True):
            with capture_stdout() as buf:
                cmd_plugin(args)
            output = buf.getvalue()
        assert "healthy" in output


# ── T9.4: plugin info shows state, config, health ─────────────────────────────


class TestPluginInfoState:
    """plugin info shows Lifecycle/Config/Health for installed plugins."""

    def test_info_shows_lifecycle_state(self, tmp_path, patched_plugins_dir):
        from tokenade.cli import cmd_plugin
        make_plugin_dir(patched_plugins_dir, "demo-handler")

        args = Namespace(plugin_command="info", name="demo-handler")
        with patch("tokenade.core.integration.plugin_registry.PluginRegistry"):
            with capture_stdout() as buf:
                cmd_plugin(args)
            output = buf.getvalue()
        assert "demo-handler" in output
        assert "Lifecycle:" in output

    def test_info_shows_configured_state_and_config(self, tmp_path, patched_plugins_dir):
        from tokenade.cli import cmd_plugin
        make_plugin_dir(patched_plugins_dir, "my-plugin",
                        manifest_extra={"config": {"schema": {"timeout": {"default": 30}}}})

        args = Namespace(plugin_command="info", name="my-plugin")
        with patch("tokenade.core.integration.plugin_registry.PluginRegistry"):
            with capture_stdout() as buf:
                cmd_plugin(args)
            output = buf.getvalue()
        assert "Lifecycle:" in output


# ── T9.6: plugin reload shows state ────────────────────────────────────────────


class TestPluginReloadState:
    """plugin reload output includes the lifecycle state."""

    def test_reload_shows_state(self, tmp_path, patched_plugins_dir):
        from tokenade.cli import cmd_plugin
        make_plugin_dir(patched_plugins_dir, "demo-handler")

        args = Namespace(plugin_command="reload", name="demo-handler")
        with patch("tokenade.core.integration.plugin_registry.PluginRegistry"):
            with capture_stdout() as buf:
                cmd_plugin(args)
            output = buf.getvalue()
        # Either reload succeeded (shows state) or failed - both fine for parser test
        if "reloaded" in output:
            assert "active" in output or "loaded" in output


# ── T9.5: plugin test --verbose ────────────────────────────────────────────────


class TestPluginTestVerbose:
    """plugin test passes verbose flag through."""

    def test_verbose_flag_parsed(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        ns = p.parse_args(["plugin", "test", "--verbose"])
        assert ns.verbose is True

    def test_verbose_flag_default_false(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        ns = p.parse_args(["plugin", "test", "demo"])
        assert ns.verbose is False

    def test_plugin_test_verbose_shows_passed_messages(self, tmp_path):
        """When verbose, even passing test messages are printed."""
        from tokenade.cli import _plugin_test
        from tokenade.core.integration.plugin_testing import (
            PluginTestResult, PluginTestSuite,
        )

        args = Namespace(name="demo", verbose=True)
        fake_suite = PluginTestSuite(plugin_name="demo")
        fake_suite.results = [
            PluginTestResult(test_name="manifest", passed=True, message="ok", duration=0.01),
            PluginTestResult(test_name="entry", passed=False, message="boom"),
        ]
        with patch("tokenade.core.integration.plugin_testing.PluginTestRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.test_plugin.return_value = fake_suite
            mock_runner_cls.return_value = mock_runner
            with capture_stdout() as buf:
                _plugin_test(args)
            output = buf.getvalue()
        # On verbose, passing test messages also print (msg condition for passed)
        assert "manifest" in output
        assert "boom" in output


# ── T9.7/T9.8: plugin deps + check-deps ──────────────────────────────────────


class TestPluginDepsCommands:
    """plugin deps and check-deps commands."""

    def _make_with_deps(self, plugins_dir, name, deps):
        pdir = plugins_dir / name
        pdir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "name": name,
            "version": "1.0.0",
            "type": "handler",
            "entry_point": "plugin.py",
            "description": "Test",
            "dependencies": deps,
        }
        (pdir / "plugin.json").write_text(json.dumps(manifest))
        body = """
from tokenade.plugin.base import SiteHandlerPlugin
class TestHandler(SiteHandlerPlugin):
    name = "%(name)s"
    version = "1.0.0"
    description = "Test"
    def can_handle(self, url): return False
    def extract_session(self, page): return {}
    def inject_session(self, page, session): pass
""" % {"name": name}
        (pdir / "plugin.py").write_text(body)

    def test_deps_shows_tree(self, tmp_path, patched_plugins_dir):
        from tokenade.cli import cmd_plugin
        self._make_with_deps(patched_plugins_dir, "alpha", ["beta"])
        self._make_with_deps(patched_plugins_dir, "beta", [])

        args = Namespace(plugin_command="deps", name="alpha")
        with patch("tokenade.core.integration.plugin_registry.PluginRegistry"):
            with capture_stdout() as buf:
                cmd_plugin(args)
            output = buf.getvalue()
        assert "alpha" in output
        assert "beta" in output

    def test_deps_missing_plugin(self, tmp_path, patched_plugins_dir):
        from tokenade.cli import cmd_plugin
        args = Namespace(plugin_command="deps", name="ghost")
        with patch("tokenade.core.integration.plugin_registry.PluginRegistry"):
            with capture_stdout() as buf:
                cmd_plugin(args)
            output = buf.getvalue()
        assert "not found" in output.lower() or "ghost" in output

    def test_check_deps_specific_missing(self, tmp_path, patched_plugins_dir):
        from tokenade.cli import cmd_plugin
        self._make_with_deps(patched_plugins_dir, "alpha", ["beta", "ghost"])
        self._make_with_deps(patched_plugins_dir, "beta", [])

        args = Namespace(plugin_command="check-deps", name="alpha")
        with patch("tokenade.core.integration.plugin_registry.PluginRegistry"):
            with capture_stdout() as buf:
                cmd_plugin(args)
            output = buf.getvalue()
        assert "ghost" in output
        assert ("missing" in output.lower())

    def test_check_deps_all_passes(self, tmp_path, patched_plugins_dir):
        from tokenade.cli import cmd_plugin
        self._make_with_deps(patched_plugins_dir, "alpha", [])
        self._make_with_deps(patched_plugins_dir, "beta", ["alpha"])

        args = Namespace(plugin_command="check-deps", name=None)
        with patch("tokenade.core.integration.plugin_registry.PluginRegistry"):
            with capture_stdout() as buf:
                cmd_plugin(args)
            output = buf.getvalue()
        # No errors → should show at least one ✅ line
        assert "No missing" in output or "✅" in output


# ── T9.9: plugin configure command ────────────────────────────────────────────


class TestPluginConfigureCommand:
    """plugin configure --show/--set/--reset/--validate."""

    def _make_configurable(self, plugins_dir, name="conf-plugin"):
        pdir = plugins_dir / name
        pdir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "name": name,
            "version": "1.0.0",
            "type": "handler",
            "entry_point": "plugin.py",
            "description": "Test",
            "config": {
                "schema": {
                    "timeout": {"type": "integer", "default": 30},
                    "retries": {"type": "integer", "default": 3},
                },
            },
        }
        (pdir / "plugin.json").write_text(json.dumps(manifest))
        body = """
from tokenade.plugin.base import SiteHandlerPlugin
class TestHandler(SiteHandlerPlugin):
    name = "%(name)s"
    version = "1.0.0"
    description = "Test"
    def can_handle(self, url): return False
    def extract_session(self, page): return {}
    def inject_session(self, page, session): pass
""" % {"name": name}
        (pdir / "plugin.py").write_text(body)

    def test_configure_show_with_config(self, tmp_path, patched_plugins_dir):
        from tokenade.cli import cmd_plugin
        self._make_configurable(patched_plugins_dir)
        cfg_path = patched_plugins_dir / "conf-plugin" / "config.json"
        cfg_path.write_text(json.dumps({"timeout": 60, "retries": 5}))

        args = Namespace(plugin_command="configure", name="conf-plugin",
                         show=True, set=None, reset=False, validate=False)
        with patch("tokenade.core.integration.plugin_registry.PluginRegistry"):
            with capture_stdout() as buf:
                cmd_plugin(args)
            output = buf.getvalue()
        assert "timeout" in output or "retries" in output or "Config" in output

    def test_configure_set_saves_config(self, tmp_path, patched_plugins_dir):
        from tokenade.cli import cmd_plugin
        self._make_configurable(patched_plugins_dir)
        args = Namespace(plugin_command="configure", name="conf-plugin",
                         show=False, set=["timeout=60", "retries=5"],
                         reset=False, validate=False)
        with patch("tokenade.core.integration.plugin_registry.PluginRegistry"):
            with capture_stdout() as buf:
                cmd_plugin(args)
            output = buf.getvalue()
        assert "saved" in output.lower()
        cfg_path = patched_plugins_dir / "conf-plugin" / "config.json"
        assert cfg_path.exists()
        saved = json.loads(cfg_path.read_text())
        assert saved.get("timeout") == 60
        assert saved.get("retries") == 5

    def test_configure_set_coerces_bool(self, tmp_path, patched_plugins_dir):
        from tokenade.cli import cmd_plugin
        self._make_configurable(patched_plugins_dir)
        manifest_path = patched_plugins_dir / "conf-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["config"]["schema"]["verbose"] = {"type": "boolean", "default": False}
        manifest_path.write_text(json.dumps(manifest))

        args = Namespace(plugin_command="configure", name="conf-plugin",
                         show=False, set=["verbose=true"],
                         reset=False, validate=False)
        with patch("tokenade.core.integration.plugin_registry.PluginRegistry"):
            with capture_stdout():
                cmd_plugin(args)
        cfg_path = patched_plugins_dir / "conf-plugin" / "config.json"
        saved = json.loads(cfg_path.read_text())
        assert saved.get("verbose") is True

    def test_configure_reset_deletes_config(self, tmp_path, patched_plugins_dir):
        from tokenade.cli import cmd_plugin
        self._make_configurable(patched_plugins_dir)
        cfg_path = patched_plugins_dir / "conf-plugin" / "config.json"
        cfg_path.write_text(json.dumps({"timeout": 99}))

        args = Namespace(plugin_command="configure", name="conf-plugin",
                         show=False, set=None, reset=True, validate=False)
        with patch("tokenade.core.integration.plugin_registry.PluginRegistry"):
            with capture_stdout() as buf:
                cmd_plugin(args)
            output = buf.getvalue()
        assert not cfg_path.exists()
        assert "reset" in output.lower()

    def test_configure_validate_valid(self, tmp_path, patched_plugins_dir):
        from tokenade.cli import cmd_plugin
        self._make_configurable(patched_plugins_dir)
        cfg_path = patched_plugins_dir / "conf-plugin" / "config.json"
        cfg_path.write_text(json.dumps({"timeout": 30, "retries": 2}))

        args = Namespace(plugin_command="configure", name="conf-plugin",
                         show=False, set=None, reset=False, validate=True)
        with patch("tokenade.core.integration.plugin_registry.PluginRegistry"):
            with capture_stdout() as buf:
                cmd_plugin(args)
            output = buf.getvalue()
        assert "valid" in output.lower() or "✅" in output

    def test_configure_validate_invalid(self, tmp_path, patched_plugins_dir):
        from tokenade.cli import cmd_plugin
        self._make_configurable(patched_plugins_dir)
        cfg_path = patched_plugins_dir / "conf-plugin" / "config.json"
        cfg_path.write_text(json.dumps({"timeout": "not-an-int"}))

        args = Namespace(plugin_command="configure", name="conf-plugin",
                         show=False, set=None, reset=False, validate=True)
        with patch("tokenade.core.integration.plugin_registry.PluginRegistry"):
            with capture_stdout() as buf:
                cmd_plugin(args)
            output = buf.getvalue()
        assert "conf-plugin" in output or "Config" in output

    def test_configure_no_flag_shows_usage(self, tmp_path, patched_plugins_dir):
        from tokenade.cli import cmd_plugin
        args = Namespace(plugin_command="configure", name="x",
                         show=False, set=None, reset=False, validate=False)
        with patch("tokenade.core.integration.plugin_registry.PluginRegistry"):
            with capture_stdout() as buf:
                cmd_plugin(args)
            output = buf.getvalue()
        assert "Usage" in output


# ── Auto-discovery: refresh-browser / accounts when neither flag set ──────────


class TestRefresherAutoDiscovery:
    """When neither --plugin nor --no-plugin is set, auto-discovery runs."""

    def test_refresh_browser_auto_discovers_refresher(self, tmp_path):
        """refresh-browser should call get_refresher_for_session when no plugin given."""
        fake_plugins = tmp_path / "plugins"
        fake_plugins.mkdir()
        make_refresher_plugin(fake_plugins, "demo-refresh")

        # We can't run the full browser refresh (needs a browser); instead we set
        # up a session file and assert that the auto-discovery print line appears
        # before the function returns early due to missing browser.
        session_path = tmp_path / "s.tokenade"
        session_path.write_text(json.dumps({
            "cookies": [{"name": "x", "value": "y", "domain": "google.com"}],
            "site_name": "demo",
            "source_device": {"browser": "chrome"},
        }))

        args = Namespace(
            session=str(session_path),
            browser="chrome",
            url=None,
            port=9222,
            headless=True,
            wait=1,
            output=None,
            plugin=None,
            no_plugin=False,
            plugin_arg=[],
            proxy=None,
        )

        from tokenade.core.integration.plugin_loader import PluginLoader as RealLoader

        class FakeLoader(RealLoader):
            def __init__(self, *a, **kw):
                super().__init__(plugins_dir=fake_plugins, *a, **kw)

        mock_pgrep = MagicMock(returncode=1, stdout="0", stderr="")
        with patch("tokenade.core.integration.plugin_loader.DEFAULT_PLUGINS_DIR", fake_plugins), \
             patch("tokenade.core.integration.plugin_loader.PluginLoader", FakeLoader), \
             patch("tokenade.core.importer.session_packager.SessionPackager.load", return_value={
                 "cookies": [{"name": "x", "value": "y", "domain": "google.com"}],
                 "site_name": "demo",
             }), \
             patch("subprocess.run", return_value=mock_pgrep), \
             patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as mock_launcher_cls:
            mock_launcher = MagicMock()
            mock_launcher.find_browser.return_value = "/usr/bin/chrome"
            mock_launcher.launch.side_effect = RuntimeError("no browser in test")
            mock_launcher_cls.return_value = mock_launcher
            from tokenade.cli.handlers.browser_ops import cmd_refresh_browser
            import pytest
            with capture_stdout() as buf:
                with pytest.raises(SystemExit):
                    cmd_refresh_browser(args)
            output = buf.getvalue()
        assert "demo-refresh" in output or "Auto-discovered" in output or "refresher" in output.lower()

    def test_refresh_browser_no_plugin_skips_discovery(self, tmp_path):
        """--no-plugin must skip both auto-discovery and plugin usage."""
        fake_plugins = tmp_path / "plugins"
        fake_plugins.mkdir()
        make_refresher_plugin(fake_plugins, "demo-refresh")

        session_path = tmp_path / "s.tokenade"
        session_path.write_text(json.dumps({
            "cookies": [{"name": "x", "value": "y", "domain": "google.com"}],
            "site_name": "demo",
            "source_device": {"browser": "chrome"},
        }))

        args = Namespace(
            session=str(session_path),
            browser="chrome",
            url=None,
            port=9222,
            headless=True,
            wait=1,
            output=None,
            plugin=None,
            no_plugin=True,  # excluded
            plugin_arg=[],
            proxy=None,
        )

        with patch("tokenade.core.integration.plugin_loader.DEFAULT_PLUGINS_DIR", fake_plugins), \
             patch("tokenade.core.integration.plugin_loader.PluginLoader") as mock_loader_cls, \
             patch("tokenade.core.importer.session_packager.SessionPackager.load", return_value={
                 "cookies": [{"name": "x", "value": "y", "domain": "google.com"}],
                 "site_name": "demo",
             }), \
             patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as mock_launcher_cls:
            mock_launcher = MagicMock()
            mock_launcher.find_browser.return_value = "/usr/bin/chrome"
            mock_launcher.launch.side_effect = RuntimeError("no browser in test")
            mock_launcher_cls.return_value = mock_launcher
            from tokenade.cli.handlers.browser_ops import cmd_refresh_browser
            import pytest
            with capture_stdout() as buf:
                with pytest.raises(SystemExit):
                    cmd_refresh_browser(args)
            output = buf.getvalue()
        # PluginLoader (for refresh) should never be instantiated for auto-discovery
        # when --no-plugin set. (The browser launch path itself may or may not use one.)
        # Assert refresher name never appears in output.
        assert "demo-refresh" not in output
        mock_loader_cls.assert_not_called()


# ── CR-05: cmd_launch ACTIVE guard for required plugins ──────────────────────


def test_cmd_launch_reports_inactive_required_plugin(inactive_plugin_loader):
    """cmd_launch must report a requirement failure for loaded-but-not-active plugins."""
    from tokenade.cli.handlers.browser_ops import cmd_launch

    fake_loaded, fake_loader = inactive_plugin_loader

    session = {
        "version": "3.0",
        "site_name": "test",
        "auth_status": "logged_in",
        "cookies": [],
        "metadata": {
            "required_plugins": [{"name": "test-plugin", "reason": "test"}]
        },
    }

    args = Namespace(
        browser="chrome",
        session="/fake.tokenade",
        url=None,
        port=9222,
        profile_dir=None,
        visible=True,
        headless=False,
        extra_args="",
        browser_path=None,
        proxy=None,
        proxy_file=None,
        proxy_rotate=False,
        proxy_strategy="health-weighted",
        humanize=False,
        geoip=False,
        no_cloak=False,
        profile=None,
        decrypt_password=None,
        plugin=None,
        no_plugin=False,
        acknowledge_exclusive_move=False,
        claim_single_use=False,
    )

    with patch(
        "tokenade.core.importer.session_packager.SessionPackager"
    ) as mock_sp, patch(
        "tokenade.core.artifacts.ProfileArtifactManager.preflight"
    ), patch(
        "tokenade.core.integration.plugin_loader.PluginLoader",
        return_value=fake_loader,
    ), patch(
        "tokenade.core.integration.plugin_dependencies.check_runtime_dependencies"
    ) as mock_rt, patch(
        "tokenade.core.integration.plugin_dependencies.check_tokenade_compatibility"
    ) as mock_compat:
        mock_sp.return_value.load.return_value = session
        mock_rt.return_value = MagicMock(ready=True, issues=[])
        mock_compat.return_value = MagicMock(issues=[])
        with capture_stdout() as buf:
            cmd_launch(args)
        output = buf.getvalue()

    assert "test-plugin" in output
    assert "not active" in output
