"""launch --timeout: auto-close instead of waiting for Ctrl+C forever."""
import time
from argparse import Namespace
from unittest.mock import MagicMock, patch


def _args(**kw):
    base = dict(
        browser="chrome", session=None, url=None, port=9222,
        profile_dir=None, visible=True, headless=False, extra_args="",
        browser_path=None, proxy=None, proxy_file=None, proxy_rotate=False,
        proxy_strategy="health-weighted", humanize=False, geoip=False,
        no_cloak=False, profile=None, decrypt_password=None,
        plugin=None, no_plugin=True, timeout=0,
    )
    base.update(kw)
    return Namespace(**base)


def _run_launch(args):
    from tokenade.cli.handlers.browser_ops import cmd_launch

    with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as mock_launcher_cls, \
         patch("tokenade.cli.handlers.browser_ops._resolve_upstream_proxy", return_value=None), \
         patch("tokenade.core.browser.cdp_connection.CDPConnection"), \
         patch("tokenade.core.importer.session_packager.SessionPackager"):
        mock_launcher = MagicMock()
        mock_launcher.find_browser.return_value = "/usr/bin/chrome"
        browser = MagicMock(
            pid=1, cdp_url="ws://x", port=9222, profile_dir="/tmp/x",
        )
        browser.process = MagicMock()
        browser.process.poll.return_value = None
        browser.process.wait.side_effect = KeyboardInterrupt
        mock_launcher.launch.return_value = browser
        mock_launcher_cls.return_value = mock_launcher
        try:
            cmd_launch(args)
        except KeyboardInterrupt:
            pass
        return browser


class TestLaunchTimeout:
    def test_timeout_closes_without_interrupt(self):
        start = time.monotonic()
        browser = _run_launch(_args(timeout=2))
        elapsed = time.monotonic() - start
        assert elapsed < 15
        browser.close.assert_called()

    def test_timeout_zero_waits_for_interrupt(self):
        browser = _run_launch(_args(timeout=0))
        # Falls through to process.wait(), which raises KeyboardInterrupt.
        browser.process.wait.assert_called()
        browser.close.assert_called()

    def test_missing_timeout_attr_defaults_to_wait(self):
        args = _args()
        del args.timeout
        browser = _run_launch(args)
        browser.process.wait.assert_called()

    def test_invalid_timeout_treated_as_zero(self):
        browser = _run_launch(_args(timeout="soon"))
        browser.process.wait.assert_called()

    def test_dead_process_exits_early(self):
        start = time.monotonic()
        from tokenade.cli.handlers.browser_ops import cmd_launch
        args = _args(timeout=60)
        with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as mock_launcher_cls, \
             patch("tokenade.cli.handlers.browser_ops._resolve_upstream_proxy", return_value=None), \
             patch("tokenade.core.browser.cdp_connection.CDPConnection"), \
             patch("tokenade.core.importer.session_packager.SessionPackager"):
            mock_launcher = MagicMock()
            mock_launcher.find_browser.return_value = "/usr/bin/chrome"
            browser = MagicMock(pid=1, cdp_url="ws://x", port=9222, profile_dir="/tmp/x")
            browser.process = MagicMock()
            browser.process.poll.return_value = 0  # already exited
            mock_launcher.launch.return_value = browser
            mock_launcher_cls.return_value = mock_launcher
            try:
                cmd_launch(args)
            except KeyboardInterrupt:
                pass
        assert time.monotonic() - start < 15
        browser.close.assert_called()
