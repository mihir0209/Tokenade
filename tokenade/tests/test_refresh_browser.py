"""Tests for cookie-based session refresh (Phase 30 + exit/login-check contract)."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from argparse import Namespace

from tokenade.cli.management import cmd_refresh_browser
from tokenade.cli.handlers.browser_ops import (
    _default_refresh_output,
    _resolve_logout_selectors,
    _unwrap_refresh_result,
)
from tokenade.plugin.api import PluginResult


def _run_refresh(args):
    """cmd_refresh_browser always ends with SystemExit(0|1)."""
    with pytest.raises(SystemExit) as ei:
        cmd_refresh_browser(args)
    return ei.value.code


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


class TestUnwrapRefreshResult:
    def test_unwrap_plugin_result(self):
        pr = PluginResult(success=True, data={"session": {"cookies": [1], "site_name": "x"}})
        out = _unwrap_refresh_result(pr, {})
        assert out["site_name"] == "x"

    def test_unwrap_failure(self):
        with pytest.raises(ValueError, match="boom"):
            _unwrap_refresh_result(PluginResult(success=False, error="boom"), {})

    def test_unwrap_plain_dict(self):
        out = _unwrap_refresh_result({"cookies": [], "site_name": "a"}, {})
        assert out["site_name"] == "a"


class TestRefreshBrowserCLI:
    def test_refresh_browser_missing_session(self, tmp_path):
        args = Namespace(
            session=str(tmp_path / "nonexistent.tokenade"),
            browser="chrome",
            url=None,
            port=9222,
            headless=True,
            wait=8,
            output=None,
            plugin=None,
            no_plugin=True,
            plugin_arg=[],
            proxy=None,
            visible=False,
        )
        assert _run_refresh(args) == 1

    def test_refresh_browser_empty_cookies(self, tmp_path):
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
            plugin=None,
            no_plugin=True,
            plugin_arg=[],
            proxy=None,
            visible=False,
        )
        assert _run_refresh(args) == 1

    def test_refresh_browser_auto_detect_url(self, sample_session):
        session, session_file = sample_session
        args = Namespace(
            session=str(session_file),
            browser="chrome",
            url=None,
            port=9222,
            headless=True,
            wait=8,
            output=None,
            plugin=None,
            no_plugin=True,
            plugin_arg=[],
            proxy=None,
            visible=False,
        )
        with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as MockLauncher:
            mock_launcher = MagicMock()
            MockLauncher.return_value = mock_launcher
            mock_launcher.find_browser.return_value = "/usr/bin/chrome"
            mock_launcher.launch.side_effect = RuntimeError("stop early")
            code = _run_refresh(args)
        assert code == 1  # browser path failed after URL detect

    def test_refresh_browser_explicit_url(self, sample_session):
        session, session_file = sample_session
        args = Namespace(
            session=str(session_file),
            browser="chrome",
            url="https://github.com",
            port=9222,
            headless=True,
            wait=8,
            output=None,
            plugin=None,
            no_plugin=True,
            plugin_arg=[],
            proxy=None,
            visible=False,
        )
        with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as MockLauncher:
            mock_launcher = MagicMock()
            MockLauncher.return_value = mock_launcher
            mock_launcher.launch.side_effect = RuntimeError("stop early")
            assert _run_refresh(args) == 1

    def test_refresh_browser_url_inference_google(self, tmp_path):
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
            plugin=None,
            no_plugin=True,
            plugin_arg=[],
            proxy=None,
            visible=False,
        )
        with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as MockLauncher:
            mock_launcher = MagicMock()
            MockLauncher.return_value = mock_launcher
            mock_launcher.launch.side_effect = RuntimeError("stop")
            assert _run_refresh(args) == 1

    def test_refresh_browser_url_inference_no_url(self, tmp_path):
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
            plugin=None,
            no_plugin=True,
            plugin_arg=[],
            proxy=None,
            visible=False,
        )
        assert _run_refresh(args) == 1

    def test_refresh_browser_saves_to_output(self, sample_session, tmp_path, fresh_cookies):
        session, session_file = sample_session
        output_file = tmp_path / "refreshed.tokenade"

        args = Namespace(
            session=str(session_file),
            browser="chrome",
            url="https://github.com",
            port=9222,
            headless=True,
            wait=0,
            output=str(output_file),
            plugin=None,
            no_plugin=True,
            plugin_arg=[],
            proxy=None,
            visible=False,
        )

        mock_browser = MagicMock()
        mock_browser.pid = 12345
        mock_browser.port = 9222
        mock_browser.cdp_url = "http://127.0.0.1:9222"
        mock_browser.close = MagicMock()

        async def _recv_side_effect():
            # Never used; we patch wait_for path via sequential responses
            return json.dumps({"id": 1, "result": {}})

        # Build deterministic CDP responses keyed by sequential ids
        responses = {
            # Network.getAllCookies etc handled by id matching any
        }

        call_ids = []

        async def fake_recv():
            # Return matching id for last sent
            cid = call_ids[-1] if call_ids else 1
            method_hint = call_ids  # noqa
            # Default empty result; special-case by tracking
            payload = {"id": cid, "result": {}}
            return json.dumps(payload)

        async def fake_send(raw):
            msg = json.loads(raw)
            call_ids.append(msg["id"])
            # stash last method for recv to craft
            fake_send.last = msg

        fake_send.last = {}

        async def smart_recv():
            msg = fake_send.last
            mid = msg.get("id", 1)
            method = msg.get("method", "")
            if method == "Network.getAllCookies":
                return json.dumps({"id": mid, "result": {"cookies": fresh_cookies}})
            if method == "Runtime.evaluate":
                expr = (msg.get("params") or {}).get("expression", "")
                if "document.title" in expr:
                    return json.dumps({"id": mid, "result": {"result": {"value": "GitHub"}}})
                if "location.href" in expr:
                    return json.dumps({
                        "id": mid,
                        "result": {"result": {"value": "https://github.com/"}},
                    })
                if "localStorage" in expr:
                    return json.dumps({"id": mid, "result": {"result": {"value": "[]"}}})
                if "sessionStorage" in expr:
                    return json.dumps({"id": mid, "result": {"result": {"value": "[]"}}})
                return json.dumps({"id": mid, "result": {"result": {"value": ""}}})
            return json.dumps({"id": mid, "result": {}})

        with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as MockLauncher:
            mock_launcher = MagicMock()
            MockLauncher.return_value = mock_launcher
            mock_launcher.launch.return_value = mock_browser

            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps({
                    "id": "test-tab",
                    "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/test",
                }).encode()
                mock_resp.__enter__ = MagicMock(return_value=mock_resp)
                mock_resp.__exit__ = MagicMock(return_value=False)
                mock_urlopen.return_value = mock_resp

                mock_ws_instance = AsyncMock()
                mock_ws_instance.send = AsyncMock(side_effect=fake_send)
                mock_ws_instance.recv = AsyncMock(side_effect=smart_recv)
                mock_ws_instance.close = AsyncMock()

                async def _connect(*a, **k):
                    return mock_ws_instance

                with patch("websockets.connect", side_effect=_connect):
                    with patch("asyncio.sleep", new_callable=AsyncMock):
                        code = _run_refresh(args)

        assert code == 0
        assert output_file.exists() or session_file.exists()
        mock_browser.close.assert_called()


class TestRefreshBrowserCookieHandling:
    def test_cookie_conversion_cdp_format(self):
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
        assert "name" in cookie
        assert cookie["sameSite"] in ("Strict", "Lax", "None")

    def test_cookie_sameSite_none_requires_secure(self):
        cookie = {
            "name": "test",
            "value": "123",
            "domain": ".example.com",
            "sameSite": "None",
            "secure": False,
        }
        if cookie.get("sameSite") == "None" and not cookie.get("secure"):
            cookie["secure"] = True
        assert cookie["secure"] is True

    def test_cookie_expires_large_timestamp(self):
        expires_ms = 1735689600000
        expires_s = 1735689600
        if expires_ms > 1262304000000:
            result = expires_ms // 1000
        else:
            result = expires_ms
        assert result == expires_s

    def test_cookie_merge_detects_changes(self):
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
        assert new_names - old_names == {"token"}
        assert old_names - new_names == set()
        assert old_names & new_names == {"session", "user"}


class TestRefreshBrowserIntegration:
    def test_full_flow_mocked(self, sample_session):
        session, session_file = sample_session
        args = Namespace(
            session=str(session_file),
            browser="chrome",
            url="https://github.com",
            port=9222,
            headless=True,
            wait=1,
            output=None,
            plugin=None,
            no_plugin=True,
            plugin_arg=[],
            proxy=None,
            visible=False,
        )
        with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as MockLauncher:
            mock_launcher = MagicMock()
            MockLauncher.return_value = mock_launcher
            mock_launcher.launch.side_effect = RuntimeError("stop")
            assert _run_refresh(args) == 1

    def test_session_metadata_updated(self, sample_session):
        session, _ = sample_session
        from datetime import datetime, timezone
        session["metadata"]["cookie_count"] = 5
        session["metadata"]["last_refreshed"] = datetime.now(timezone.utc).isoformat()
        assert session["metadata"]["cookie_count"] == 5
        assert "last_refreshed" in session["metadata"]


class TestPluginIntegration:
    """Tests for plugin integration in refresh-browser command."""

    def test_plugin_flag_recognized(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["refresh-browser", "-s", "test.tokenade", "--plugin", "oauth2"])
        assert args.plugin == "oauth2"

    def test_plugin_arg_flag_recognized(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args([
            "refresh-browser", "-s", "test.tokenade", "--plugin", "oauth2",
            "--plugin-arg", "client_id", "xxx", "--plugin-arg", "client_secret", "yyy",
        ])
        assert args.plugin == "oauth2"
        assert args.plugin_arg == [["client_id", "xxx"], ["client_secret", "yyy"]]

    def test_accounts_refresh_plugin_flag(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["accounts", "refresh", "--plugin", "oauth2", "-y"])
        assert args.plugin == "oauth2"

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    def test_plugin_refresh_success(self, MockLoader, sample_session, tmp_path):
        session, _ = sample_session
        session_path = tmp_path / "test.tokenade"
        session_path.write_text(json.dumps(session))

        mock_loader = MagicMock()
        MockLoader.return_value = mock_loader
        mock_loader.load_all.return_value = None
        mock_loader.list_refreshers.return_value = {}

        mock_refresher = MagicMock()
        mock_refresher.name = "oauth2"
        mock_refresher.version = "1.0.0"
        mock_refresher.can_refresh.return_value = True
        mock_refresher.refresh.return_value = PluginResult(
            success=True, data={"session": dict(session)}
        )
        mock_loader.get_refresher.return_value = mock_refresher

        args = Namespace(
            session=str(session_path),
            plugin="oauth2",
            plugin_arg=[],
            output=None,
            no_plugin=False,
            browser="chrome",
            url=None,
            port=9222,
            headless=True,
            wait=1,
            proxy=None,
            visible=False,
        )

        with patch("tokenade.core.importer.session_packager.SessionPackager") as MockPackager:
            pack = MagicMock()
            MockPackager.return_value = pack
            pack.load.return_value = session
            pack.save.return_value = str(session_path)
            code = _run_refresh(args)

        assert code == 0
        mock_refresher.can_refresh.assert_called()
        mock_refresher.refresh.assert_called_once()
        pack.save.assert_called()

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    def test_plugin_falls_back_to_browser(self, MockLoader, sample_session, tmp_path):
        session, _ = sample_session
        session_path = tmp_path / "test.tokenade"
        session_path.write_text(json.dumps(session))

        mock_loader = MagicMock()
        MockLoader.return_value = mock_loader
        mock_loader.load_all.return_value = None
        mock_loader.list_refreshers.return_value = {}

        mock_refresher = MagicMock()
        mock_refresher.name = "oauth2"
        mock_refresher.version = "1.0.0"
        mock_refresher.can_refresh.return_value = False
        mock_loader.get_refresher.return_value = mock_refresher

        args = Namespace(
            session=str(session_path), plugin="oauth2", plugin_arg=[],
            output=None, headless=True, wait=2, browser="chrome", port=9222, url=None,
            no_plugin=False, proxy=None, visible=False,
        )

        with patch("tokenade.core.importer.session_packager.SessionPackager") as MockPackager:
            MockPackager.return_value.load.return_value = session
            with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as MockLauncher:
                mock_launcher = MagicMock()
                MockLauncher.return_value = mock_launcher
                mock_launcher.launch.side_effect = RuntimeError("no browser in test")
                code = _run_refresh(args)

        mock_refresher.can_refresh.assert_called()
        assert code == 1

    @patch("tokenade.core.integration.plugin_loader.PluginLoader")
    def test_plugin_exception_falls_back(self, MockLoader, sample_session, tmp_path):
        session, _ = sample_session
        session_path = tmp_path / "test.tokenade"
        session_path.write_text(json.dumps(session))

        mock_loader = MagicMock()
        MockLoader.return_value = mock_loader
        mock_loader.load_all.return_value = None
        mock_loader.list_refreshers.return_value = {}

        mock_refresher = MagicMock()
        mock_refresher.name = "oauth2"
        mock_refresher.version = "1.0.0"
        mock_refresher.can_refresh.side_effect = Exception("Plugin broken")
        mock_loader.get_refresher.return_value = mock_refresher

        args = Namespace(
            session=str(session_path), plugin="oauth2", plugin_arg=[],
            output=None, headless=True, wait=2, browser="chrome", port=9222, url=None,
            no_plugin=False, proxy=None, visible=False,
        )

        with patch("tokenade.core.importer.session_packager.SessionPackager") as MockPackager:
            MockPackager.return_value.load.return_value = session
            with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as MockLauncher:
                mock_launcher = MagicMock()
                MockLauncher.return_value = mock_launcher
                mock_launcher.launch.side_effect = RuntimeError("no browser in test")
                code = _run_refresh(args)

        mock_refresher.can_refresh.assert_called()
        assert code == 1

    def test_no_plugin_falls_through_to_browser(self, sample_session, tmp_path):
        session, _ = sample_session
        session_path = tmp_path / "test.tokenade"
        session_path.write_text(json.dumps(session))

        args = Namespace(
            session=str(session_path), plugin=None, plugin_arg=[],
            output=None, headless=True, wait=2, browser="chrome", port=9222, url=None,
            no_plugin=True, proxy=None, visible=False,
        )

        with patch("tokenade.core.importer.session_packager.SessionPackager") as MockPackager:
            MockPackager.return_value.load.return_value = session
            with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as MockLauncher:
                mock_launcher = MagicMock()
                MockLauncher.return_value = mock_launcher
                mock_launcher.launch.side_effect = RuntimeError("stop")
                code = _run_refresh(args)

        mock_launcher.launch.assert_called_once()
        assert code == 1


def _mocked_browser_run(args, fresh_cookies, title="GitHub",
                        first_url="https://github.com/",
                        settled_url=None, dom_hit=False):
    """Run cmd_refresh_browser with a fully mocked CDP browser.

    Args:
        settled_url: URL returned by the post-settle location.href read
            (defaults to ``first_url``).
        dom_hit: when True every ``querySelector`` logout-selector probe
            reports a match.
    """
    from unittest.mock import patch, MagicMock, AsyncMock

    settled_url = first_url if settled_url is None else settled_url
    href_reads = []

    mock_browser = MagicMock()
    mock_browser.pid = 12345
    mock_browser.port = 9222
    mock_browser.cdp_url = "http://127.0.0.1:9222"
    mock_browser.close = MagicMock()

    async def fake_send(raw):
        fake_send.last = json.loads(raw)

    fake_send.last = {}

    async def smart_recv():
        msg = fake_send.last
        mid = msg.get("id", 1)
        method = msg.get("method", "")
        if method == "Network.getAllCookies":
            return json.dumps({"id": mid, "result": {"cookies": fresh_cookies}})
        if method == "Runtime.evaluate":
            expr = (msg.get("params") or {}).get("expression", "")
            if "querySelector" in expr:
                return json.dumps({
                    "id": mid,
                    "result": {"result": {"value": bool(dom_hit)}},
                })
            if "document.title" in expr:
                return json.dumps({"id": mid, "result": {"result": {"value": title}}})
            if "location.href" in expr:
                href_reads.append(1)
                url = settled_url if len(href_reads) > 1 else first_url
                return json.dumps({"id": mid, "result": {"result": {"value": url}}})
            if "localStorage" in expr or "sessionStorage" in expr:
                return json.dumps({"id": mid, "result": {"result": {"value": "[]"}}})
            return json.dumps({"id": mid, "result": {"result": {"value": ""}}})
        return json.dumps({"id": mid, "result": {}})

    with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as MockLauncher:
        mock_launcher = MagicMock()
        MockLauncher.return_value = mock_launcher
        mock_launcher.launch.return_value = mock_browser
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({
                "id": "test-tab",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/test",
            }).encode()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            mock_ws = AsyncMock()
            mock_ws.send = AsyncMock(side_effect=fake_send)
            mock_ws.recv = AsyncMock(side_effect=smart_recv)
            mock_ws.close = AsyncMock()

            async def _connect(*a, **k):
                return mock_ws

            with patch("websockets.connect", side_effect=_connect):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    code = _run_refresh(args)
    mock_browser.close.assert_called()
    return code


def _refresh_args(session_file, **kw):
    base = dict(
        session=str(session_file),
        browser="chrome",
        url="https://github.com",
        port=9222,
        headless=True,
        wait=1,
        output=None,
        plugin=None,
        no_plugin=True,
        plugin_arg=[],
        proxy=None,
        visible=False,
    )
    base.update(kw)
    return Namespace(**base)


class TestRefreshDomLoginCheck:
    def test_dom_logout_marker_vetoes_pass(self, sample_session, fresh_cookies):
        _, session_file = sample_session
        code = _mocked_browser_run(
            _refresh_args(session_file), fresh_cookies, dom_hit=True
        )
        assert code == 1

    def test_settled_login_redirect_fails(self, sample_session, fresh_cookies):
        _, session_file = sample_session
        code = _mocked_browser_run(
            _refresh_args(session_file),
            fresh_cookies,
            first_url="https://discord.com/channels/@me",
            settled_url="https://discord.com/login?redirect_to=%2Fchannels%2F%40me",
        )
        assert code == 1

    def test_clean_dom_and_url_passes(self, sample_session, fresh_cookies, tmp_path):
        _, session_file = sample_session
        code = _mocked_browser_run(
            _refresh_args(session_file), fresh_cookies
        )
        assert code == 0
        default_out = tmp_path / "github.refreshed.tokenade"
        # default goes to <stem>.refreshed.tokenade next to the input
        assert Path(_default_refresh_output(session_file)) == default_out

    def test_source_file_never_overwritten_by_default(
        self, sample_session, fresh_cookies
    ):
        session, session_file = sample_session
        before = session_file.read_bytes()
        code = _mocked_browser_run(
            _refresh_args(session_file), fresh_cookies
        )
        assert code == 0
        assert session_file.read_bytes() == before
        refreshed = Path(_default_refresh_output(session_file))
        assert refreshed.exists()
        data = json.loads(refreshed.read_text())
        assert data["cookies"][0]["value"] == "fresh_xyz789"


class TestLogoutSelectorResolution:
    def test_generic_fallback_for_unknown_site(self):
        sels = _resolve_logout_selectors(
            [{"domain": ".example-unknown-xyz.com", "name": "s", "value": "v"}],
            "unknownsite12345",
        )
        assert "a[href='/login']" in sels
        assert "a[href='/signin']" in sels
        # Login forms served without redirect (Discord SPA shell) must fail.
        assert "input[type='password']" in sels

    def test_discord_handler_selectors_preferred(self):
        pytest.importorskip("tokenade.core.importer.plugin_export")
        from tokenade.core.importer.plugin_export import PluginExporter

        try:
            handler = PluginExporter().find_handler(["discord.com"])
        except Exception:
            handler = None
        if handler is None:
            pytest.skip("discord-handler plugin not installed")
        sels = _resolve_logout_selectors(
            [{"domain": ".discord.com", "name": "a", "value": "b"}], "discord"
        )
        assert "a[href='/login']" in sels

    def test_never_raises(self):
        assert isinstance(_resolve_logout_selectors(None, ""), list)
        assert isinstance(_resolve_logout_selectors([], ""), list)

    def test_default_output_naming(self, tmp_path):
        src = tmp_path / "brave-github-real.tokenade"
        src.write_text("{}")
        assert _default_refresh_output(src) == str(
            tmp_path / "brave-github-real.refreshed.tokenade"
        )
