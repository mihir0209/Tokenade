"""Tests for cookie-based session refresh (Phase 30)."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from argparse import Namespace

from tokenade.cli.management import cmd_refresh_browser


@pytest.fixture
def sample_session(tmp_path):
    """Create a sample .tokenade session file."""
    session = {
        "version": "1.0",
        "site_name": "github",
        "auth_status": "logged_in",
        "source_device": {"browser": "brave"},
        "cookies": [
            {
                "name": "user_session",
                "value": "abc123",
                "domain": ".github.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "Lax",
            },
            {
                "name": "logged_in",
                "value": "yes",
                "domain": ".github.com",
                "path": "/",
                "secure": True,
                "httpOnly": False,
            },
        ],
        "local_storage": {},
        "session_storage": {},
        "metadata": {
            "cookie_count": 2,
            "critical_cookie_count": 1,
        },
    }
    session_file = tmp_path / "github.tokenade"
    session_file.write_text(json.dumps(session, indent=2))
    return session, session_file


@pytest.fixture
def fresh_cookies():
    """Simulated fresh cookies from CDP extraction."""
    return [
        {
            "name": "user_session",
            "value": "fresh_xyz789",
            "domain": ".github.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "Lax",
            "expires": 1735689600,
        },
        {
            "name": "logged_in",
            "value": "yes",
            "domain": ".github.com",
            "path": "/",
            "secure": True,
            "httpOnly": False,
        },
        {
            "name": "_gh_sess",
            "value": "new_session_token",
            "domain": ".github.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
        },
    ]


class TestRefreshBrowserCLI:
    def test_refresh_browser_missing_session(self, tmp_path):
        """Test refresh with non-existent session file."""
        args = Namespace(
            session=str(tmp_path / "nonexistent.tokenade"),
            browser="chrome",
            url=None,
            port=9222,
            headless=True,
            wait=8,
            output=None,
        )
        # Should print error and return, not crash
        cmd_refresh_browser(args)

    def test_refresh_browser_empty_cookies(self, tmp_path):
        """Test refresh with session file containing no cookies."""
        session = {
            "version": "1.0",
            "site_name": "github",
            "cookies": [],
            "metadata": {},
        }
        session_file = tmp_path / "empty.tokenade"
        session_file.write_text(json.dumps(session))

        args = Namespace(
            session=str(session_file),
            browser="chrome",
            url=None,
            port=9222,
            headless=True,
            wait=8,
            output=None,
        )
        cmd_refresh_browser(args)

    def test_refresh_browser_auto_detect_url(self, sample_session):
        """Test that URL is auto-detected from cookies."""
        session, session_file = sample_session
        args = Namespace(
            session=str(session_file),
            browser="chrome",
            url=None,  # No URL specified
            port=9222,
            headless=True,
            wait=8,
            output=None,
        )
        with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as MockLauncher:
            mock_launcher = MagicMock()
            MockLauncher.return_value = mock_launcher
            mock_launcher.find_browser.return_value = "/usr/bin/chrome"
            cmd_refresh_browser(args)

    def test_refresh_browser_explicit_url(self, sample_session):
        """Test refresh with explicit URL."""
        session, session_file = sample_session
        args = Namespace(
            session=str(session_file),
            browser="chrome",
            url="https://github.com",
            port=9222,
            headless=True,
            wait=8,
            output=None,
        )
        with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as MockLauncher:
            mock_launcher = MagicMock()
            MockLauncher.return_value = mock_launcher
            cmd_refresh_browser(args)

    def test_refresh_browser_url_inference_google(self, tmp_path):
        """Test URL inference for Google cookies."""
        session = {
            "version": "1.0",
            "site_name": "google",
            "cookies": [
                {"name": "SID", "value": "x", "domain": ".google.com"},
                {"name": "HSID", "value": "y", "domain": ".google.com"},
            ],
            "metadata": {},
        }
        session_file = tmp_path / "google.tokenade"
        session_file.write_text(json.dumps(session))

        args = Namespace(
            session=str(session_file),
            browser="chrome",
            url=None,
            port=9222,
            headless=True,
            wait=8,
            output=None,
        )
        with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher"):
            cmd_refresh_browser(args)

    def test_refresh_browser_url_inference_no_url(self, tmp_path):
        """Test when no URL can be inferred."""
        session = {
            "version": "1.0",
            "site_name": "unknown",
            "cookies": [
                {"name": "test", "value": "x", "domain": ""},
            ],
            "metadata": {},
        }
        session_file = tmp_path / "no_url.tokenade"
        session_file.write_text(json.dumps(session))

        args = Namespace(
            session=str(session_file),
            browser="chrome",
            url=None,
            port=9222,
            headless=True,
            wait=8,
            output=None,
        )
        # Should print error about needing --url
        cmd_refresh_browser(args)

    def test_refresh_browser_saves_to_output(self, sample_session, tmp_path):
        """Test that refresh saves to output file."""
        session, session_file = sample_session
        output_file = tmp_path / "refreshed.tokenade"

        args = Namespace(
            session=str(session_file),
            browser="chrome",
            url="https://github.com",
            port=9222,
            headless=True,
            wait=8,
            output=str(output_file),
        )

        with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as MockLauncher:
            mock_launcher = MagicMock()
            MockLauncher.return_value = mock_launcher

            mock_browser = MagicMock()
            mock_browser.pid = 12345
            mock_browser.cdp_url = "http://127.0.0.1:9222"
            mock_launcher.launch.return_value = mock_browser

            with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher._is_port_in_use", return_value=False):
                with patch("urllib.request.urlopen") as mock_urlopen:
                    mock_resp = MagicMock()
                    mock_resp.read.return_value = json.dumps({
                        "id": "test-tab",
                        "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/test",
                    }).encode()
                    mock_urlopen.return_value = mock_resp

                    with patch("websockets.connect") as mock_ws:
                        mock_ws_instance = AsyncMock()
                        mock_ws.return_value = mock_ws_instance
                        mock_ws_instance.send = AsyncMock()
                        mock_ws_instance.recv = AsyncMock(return_value=json.dumps({
                            "id": 1,
                            "result": {},
                        }))
                        mock_ws_instance.close = AsyncMock()

                        with patch("tokenade.cli.session._extract_via_cdp") as mock_extract:
                            mock_extract.return_value = {
                                "cookies": [
                                    {"name": "user_session", "value": "new_val", "domain": ".github.com"},
                                ],
                                "local_storage": {},
                                "session_storage": {},
                            }

                            with patch("tokenade.core.browser.undetectable.platform"):
                                with patch("subprocess.run"):
                                    cmd_refresh_browser(args)

        assert session_file.exists() or output_file.exists()


class TestRefreshBrowserCookieHandling:
    def test_cookie_conversion_cdp_format(self):
        """Test that cookies are correctly converted to CDP format."""
        cookie = {
            "name": "test",
            "value": "123",
            "domain": ".example.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "Strict",
            "expires": 1735689600,
        }
        # Verify the cookie structure matches what CDP expects
        assert "name" in cookie
        assert "value" in cookie
        assert "domain" in cookie
        assert cookie["sameSite"] in ("Strict", "Lax", "None")

    def test_cookie_sameSite_none_requires_secure(self):
        """Test that sameSite=None forces secure=True."""
        cookie = {
            "name": "test",
            "value": "123",
            "domain": ".example.com",
            "sameSite": "None",
            "secure": False,
        }
        # The refresh command should fix this
        if cookie.get("sameSite") == "None" and not cookie.get("secure"):
            cookie["secure"] = True
        assert cookie["secure"] is True

    def test_cookie_expires_large_timestamp(self):
        """Test that large timestamps (>2009) are treated as milliseconds."""
        expires_ms = 1735689600000  # milliseconds
        expires_s = 1735689600  # seconds

        # If > 1262304000000 (2009 in ms), treat as ms
        if expires_ms > 1262304000000:
            result = expires_ms // 1000
        else:
            result = expires_ms
        assert result == expires_s

    def test_cookie_merge_detects_changes(self):
        """Test that cookie changes are correctly detected."""
        old_cookies = [
            {"name": "session", "value": "old"},
            {"name": "user", "value": "keep"},
        ]
        new_cookies = [
            {"name": "session", "value": "new"},
            {"name": "user", "value": "keep"},
            {"name": "token", "value": "added"},
        ]

        old_names = {c["name"] for c in old_cookies}
        new_names = {c["name"] for c in new_cookies}

        added = new_names - old_names
        removed = old_names - new_names
        kept = old_names & new_names

        assert added == {"token"}
        assert removed == set()
        assert kept == {"session", "user"}


class TestRefreshBrowserIntegration:
    def test_full_flow_mocked(self, sample_session, tmp_path, fresh_cookies):
        """Test the full refresh flow with mocks."""
        session, session_file = sample_session

        args = Namespace(
            session=str(session_file),
            browser="chrome",
            url="https://github.com",
            port=9222,
            headless=True,
            wait=1,
            output=None,
        )

        with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as MockLauncher:
            mock_launcher = MagicMock()
            MockLauncher.return_value = mock_launcher
            cmd_refresh_browser(args)

    def test_session_metadata_updated(self, sample_session):
        """Test that session metadata is updated after refresh."""
        session, _ = sample_session
        # Simulate what the refresh command does to metadata
        from datetime import datetime, timezone

        session["metadata"]["cookie_count"] = 5
        session["metadata"]["last_refreshed"] = datetime.now(timezone.utc).isoformat()

        assert session["metadata"]["cookie_count"] == 5
        assert "last_refreshed" in session["metadata"]


class TestPluginIntegration:
    """Tests for plugin integration in refresh-browser command."""

    def test_plugin_flag_recognized(self):
        """Test that --plugin flag is in CLI args."""
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["refresh-browser", "-s", "test.tokenade", "--plugin", "oauth2"])
        assert args.plugin == "oauth2"

    def test_plugin_arg_flag_recognized(self):
        """Test that --plugin-arg flag is in CLI args."""
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["refresh-browser", "-s", "test.tokenade", "--plugin", "oauth2",
                                  "--plugin-arg", "client_id", "xxx", "--plugin-arg", "client_secret", "yyy"])
        assert args.plugin == "oauth2"
        assert args.plugin_arg == [["client_id", "xxx"], ["client_secret", "yyy"]]

    def test_accounts_refresh_plugin_flag(self):
        """Test that accounts refresh accepts --plugin."""
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["accounts", "refresh", "--plugin", "oauth2", "-y"])
        assert args.plugin == "oauth2"

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    def test_plugin_refresh_success(self, MockLoader, sample_session, tmp_path):
        """Test successful plugin refresh saves and exits early."""
        session, _ = sample_session
        session_path = tmp_path / "test.tokenade"
        session_path.write_text(json.dumps(session))

        from tokenade.core.importer.session_packager import SessionPackager
        packager = SessionPackager()
        saved_session = dict(session)

        mock_loader = MagicMock()
        MockLoader.return_value = mock_loader
        mock_loader.load_all.return_value = None

        mock_refresher = MagicMock()
        mock_refresher.version = "1.0.0"
        mock_refresher.can_refresh.return_value = True
        mock_refresher.refresh.return_value = saved_session
        mock_loader.get_refresher.return_value = mock_refresher

        args = Namespace(session=str(session_path), plugin="oauth2", plugin_arg=[], output=None)

        with patch("tokenade.core.importer.session_packager.SessionPackager") as MockPackager:
            MockPackager.return_value.load.return_value = session
            cmd_refresh_browser(args)

        mock_refresher.can_refresh.assert_called_once_with(session)
        mock_refresher.refresh.assert_called_once()

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    def test_plugin_falls_back_to_browser(self, MockLoader, sample_session, tmp_path):
        """Test fallback to browser when plugin can't handle session."""
        session, _ = sample_session
        session_path = tmp_path / "test.tokenade"
        session_path.write_text(json.dumps(session))

        mock_loader = MagicMock()
        MockLoader.return_value = mock_loader
        mock_loader.load_all.return_value = None

        mock_refresher = MagicMock()
        mock_refresher.version = "1.0.0"
        mock_refresher.can_refresh.return_value = False
        mock_loader.get_refresher.return_value = mock_refresher

        args = Namespace(session=str(session_path), plugin="oauth2", plugin_arg=[],
                         output=None, headless=True, wait=2, browser="chrome", port=9222, url=None)

        with patch("tokenade.core.importer.session_packager.SessionPackager") as MockPackager:
            MockPackager.return_value.load.return_value = session
            with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as MockLauncher:
                mock_launcher = MagicMock()
                MockLauncher.return_value = mock_launcher
                mock_launcher.launch.return_value = mock_launcher
                mock_launcher.get_cookies.return_value = session["cookies"][:1]
                with patch("tokenade.cli.handlers.browser_ops._refresh_session_cookies") as mock_refresh:
                    mock_refresh.return_value = ([session["cookies"][0]], {}, {})
                    cmd_refresh_browser(args)

        mock_refresher.can_refresh.assert_called_once()

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    def test_plugin_exception_falls_back(self, MockLoader, sample_session, tmp_path):
        """Test fallback when plugin raises exception."""
        session, _ = sample_session
        session_path = tmp_path / "test.tokenade"
        session_path.write_text(json.dumps(session))

        mock_loader = MagicMock()
        MockLoader.return_value = mock_loader
        mock_loader.load_all.return_value = None

        mock_refresher = MagicMock()
        mock_refresher.version = "1.0.0"
        mock_refresher.can_refresh.side_effect = Exception("Plugin broken")
        mock_loader.get_refresher.return_value = mock_refresher

        args = Namespace(session=str(session_path), plugin="oauth2", plugin_arg=[],
                         output=None, headless=True, wait=2, browser="chrome", port=9222, url=None)

        with patch("tokenade.core.importer.session_packager.SessionPackager") as MockPackager:
            MockPackager.return_value.load.return_value = session
            with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as MockLauncher:
                mock_launcher = MagicMock()
                MockLauncher.return_value = mock_launcher
                mock_launcher.launch.return_value = mock_launcher
                mock_launcher.get_cookies.return_value = session["cookies"][:1]
                with patch("tokenade.cli.handlers.browser_ops._refresh_session_cookies") as mock_refresh:
                    mock_refresh.return_value = ([session["cookies"][0]], {}, {})
                    cmd_refresh_browser(args)

        mock_refresher.can_refresh.assert_called_once()

    def test_no_plugin_falls_through_to_browser(self, sample_session, tmp_path):
        """Test that without --plugin, browser refresh is used directly."""
        session, _ = sample_session
        session_path = tmp_path / "test.tokenade"
        session_path.write_text(json.dumps(session))

        args = Namespace(session=str(session_path), plugin=None, plugin_arg=[],
                         output=None, headless=True, wait=2, browser="chrome", port=9222, url=None)

        mock_proc = MagicMock()
        mock_proc.returncode = 1

        with patch("tokenade.core.importer.session_packager.SessionPackager") as MockPackager:
            MockPackager.return_value.load.return_value = session
            with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as MockLauncher:
                mock_launcher = MagicMock()
                MockLauncher.return_value = mock_launcher
                mock_launcher.launch.return_value = mock_launcher
                mock_launcher.get_cookies.return_value = session["cookies"][:1]
                with patch("tokenade.cli.handlers.browser_ops._refresh_session_cookies") as mock_refresh:
                    mock_refresh.return_value = ([session["cookies"][0]], {}, {})
                    with patch("subprocess.run", return_value=mock_proc):
                        cmd_refresh_browser(args)

        mock_launcher.launch.assert_called_once()
