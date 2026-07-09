"""Tests for CLI proxy commands."""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from argparse import Namespace

from tokenade.cli.proxy import cmd_proxy


def _make_session_file(tmp_path, name="test", cookies=None, auth_status="logged_in"):
    if cookies is None:
        cookies = [{"name": "sid", "value": "abc", "domain": ".github.com"}]
    f = tmp_path / f"{name}.tokenade"
    f.write_text(json.dumps({
        "cookies": cookies, "site_name": name, "auth_status": auth_status,
    }))
    return f


def _make_args(**overrides):
    defaults = dict(
        all=False,
        session=None,
        sessions_dir=None,
        port=8080,
        host="127.0.0.1",
        mode="cdp",
        legacy=False,
        verbose=False,
        no_gui=False,
        visible=False,
        fingerprint=True,
        impersonate=None,
        auto_refresh=False,
        source_browser=None,
        source_profile=None,
        auto_navigate=False,
        target_url=None,
        no_open_browser=True,
        rotate=False,
        rotate_strategy="health-weighted",
        rotate_interval=300,
        timeout=30,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


# ─── Multi-site proxy mode (--all) ───────────────────────────────────────

class TestMultiSiteProxy:
    def test_no_sessions_found(self, tmp_path, capsys):
        args = _make_args(all=True, sessions_dir=str(tmp_path))
        cmd_proxy(args)
        assert "No session files found" in capsys.readouterr().out

    @patch("asyncio.run")
    @patch("tokenade.core.proxy.multi_site_proxy.MultiSiteProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_multi_site_starts(self, mock_packager_cls, mock_proxy_cls, mock_run, tmp_path, capsys):
        _make_session_file(tmp_path, "github")
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": [], "site_name": "github"}
        mock_packager_cls.return_value = mock_packager
        mock_proxy = MagicMock()
        mock_proxy_cls.return_value = mock_proxy
        args = _make_args(all=True, sessions_dir=str(tmp_path))
        cmd_proxy(args)
        mock_run.assert_called_once()

    @patch("asyncio.run")
    @patch("tokenade.core.proxy.multi_site_proxy.MultiSiteProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_multi_site_prints_header(self, mock_packager_cls, mock_proxy_cls, mock_run, tmp_path, capsys):
        _make_session_file(tmp_path, "github")
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": [], "site_name": "github"}
        mock_packager_cls.return_value = mock_packager
        mock_proxy = MagicMock()
        mock_proxy_cls.return_value = mock_proxy
        args = _make_args(all=True, sessions_dir=str(tmp_path))
        cmd_proxy(args)
        output = capsys.readouterr().out
        assert "Multi-Site Proxy" in output
        assert "1 sessions" in output

    @patch("asyncio.run")
    @patch("tokenade.core.proxy.multi_site_proxy.MultiSiteProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_multi_site_load_failure(self, mock_packager_cls, mock_proxy_cls, mock_run, tmp_path, capsys):
        _make_session_file(tmp_path, "good")
        _make_session_file(tmp_path, "bad")
        mock_packager = MagicMock()

        def load_side_effect(path):
            if "bad" in path:
                raise ValueError("corrupt session")
            return {"cookies": [], "site_name": "good"}
        mock_packager.load.side_effect = load_side_effect
        mock_packager_cls.return_value = mock_packager
        mock_proxy = MagicMock()
        mock_proxy_cls.return_value = mock_proxy
        args = _make_args(all=True, sessions_dir=str(tmp_path))
        cmd_proxy(args)
        output = capsys.readouterr().out
        assert "1 sessions" in output

    @patch("asyncio.run")
    @patch("tokenade.core.proxy.multi_site_proxy.MultiSiteProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_multi_site_default_search_dir(self, mock_packager_cls, mock_proxy_cls, mock_run, tmp_path, monkeypatch, capsys):
        _make_session_file(tmp_path, "github")
        monkeypatch.chdir(tmp_path)
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": [], "site_name": "github"}
        mock_packager_cls.return_value = mock_packager
        mock_proxy = MagicMock()
        mock_proxy_cls.return_value = mock_proxy
        args = _make_args(all=True, sessions_dir=None)
        cmd_proxy(args)
        mock_run.assert_called_once()

    @patch("asyncio.run")
    @patch("tokenade.core.proxy.multi_site_proxy.MultiSiteProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_multi_site_multiple_session_types(self, mock_packager_cls, mock_proxy_cls, mock_run, tmp_path, capsys):
        _make_session_file(tmp_path, "github")
        f2 = tmp_path / "twitter.session"
        f2.write_text(json.dumps({"cookies": [], "site_name": "twitter"}))
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": [], "site_name": "x"}
        mock_packager_cls.return_value = mock_packager
        mock_proxy = MagicMock()
        mock_proxy_cls.return_value = mock_proxy
        args = _make_args(all=True, sessions_dir=str(tmp_path))
        cmd_proxy(args)
        output = capsys.readouterr().out
        assert "2 sessions" in output

    @patch("asyncio.run")
    @patch("tokenade.core.proxy.multi_site_proxy.MultiSiteProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_multi_site_custom_port_and_host(self, mock_packager_cls, mock_proxy_cls, mock_run, tmp_path, capsys):
        _make_session_file(tmp_path, "github")
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": [], "site_name": "github"}
        mock_packager_cls.return_value = mock_packager
        mock_proxy = MagicMock()
        mock_proxy_cls.return_value = mock_proxy
        args = _make_args(all=True, sessions_dir=str(tmp_path), port=9090, host="0.0.0.0")
        cmd_proxy(args)
        call_kwargs = mock_proxy_cls.call_args
        assert call_kwargs[1]["base_port"] == 9090
        assert call_kwargs[1]["host"] == "0.0.0.0"


# ─── Missing session / session not found ──────────────────────────────────

class TestMissingSession:
    def test_no_session_no_all(self, capsys):
        args = _make_args()
        cmd_proxy(args)
        assert "--session required" in capsys.readouterr().out

    def test_session_not_found(self, capsys):
        args = _make_args(session="/nonexistent/file.tokenade")
        cmd_proxy(args)
        assert "Session file not found" in capsys.readouterr().out


# ─── Forward proxy mode ───────────────────────────────────────────────────

class TestForwardProxyMode:
    @patch("tokenade.core.proxy.forward_proxy.ForwardProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_forward_proxy_starts(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": []}
        mock_packager_cls.return_value = mock_packager
        mock_proxy = MagicMock()
        mock_proxy.start = AsyncMock()
        mock_proxy_cls.return_value = mock_proxy
        args = _make_args(session=str(f), mode="forward")
        cmd_proxy(args)
        mock_proxy.start.assert_called_once()

    @patch("tokenade.core.proxy.forward_proxy.ForwardProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_forward_proxy_prints_http_proxy(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": []}
        mock_packager_cls.return_value = mock_packager
        mock_proxy = MagicMock()
        mock_proxy.start = AsyncMock()
        mock_proxy_cls.return_value = mock_proxy
        args = _make_args(session=str(f), mode="forward")
        cmd_proxy(args)
        output = capsys.readouterr().out
        assert "HTTP_PROXY" in output

    @patch("tokenade.core.proxy.forward_proxy.ForwardProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_forward_proxy_no_engine_display(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": []}
        mock_packager_cls.return_value = mock_packager
        mock_proxy = MagicMock()
        mock_proxy.start = AsyncMock()
        mock_proxy_cls.return_value = mock_proxy
        args = _make_args(session=str(f), mode="forward")
        cmd_proxy(args)
        output = capsys.readouterr().out
        assert "CDP" not in output
        assert "Legacy" not in output

    @patch("tokenade.core.proxy.forward_proxy.ForwardProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_forward_uses_custom_host_port(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": []}
        mock_packager_cls.return_value = mock_packager
        mock_proxy = MagicMock()
        mock_proxy.start = AsyncMock()
        mock_proxy_cls.return_value = mock_proxy
        args = _make_args(session=str(f), mode="forward", host="0.0.0.0", port=3128)
        cmd_proxy(args)
        output = capsys.readouterr().out
        assert "0.0.0.0:3128" in output


# ─── Legacy proxy mode ────────────────────────────────────────────────────

class TestLegacyProxyMode:
    @patch("tokenade.core.proxy.server.TokenadeProxy")
    @patch("tokenade.core.proxy.server.ProxyConfig")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_legacy_proxy_starts(self, mock_packager_cls, mock_config_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), mode="cdp", legacy=True)
        cmd_proxy(args)
        mock_proxy_cls.from_session_file.assert_called_once()
        proxy_instance.run.assert_called_once()

    @patch("tokenade.core.proxy.server.TokenadeProxy")
    @patch("tokenade.core.proxy.server.ProxyConfig")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_legacy_gui_mode(self, mock_packager_cls, mock_config_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        mock_proxy_cls.from_session_file.return_value = MagicMock()
        args = _make_args(session=str(f), mode="cdp", legacy=True, no_gui=False)
        cmd_proxy(args)
        config_call = mock_config_cls.call_args
        assert config_call[1]["gui_mode"] is True

    @patch("tokenade.core.proxy.server.TokenadeProxy")
    @patch("tokenade.core.proxy.server.ProxyConfig")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_legacy_no_gui(self, mock_packager_cls, mock_config_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        mock_proxy_cls.from_session_file.return_value = MagicMock()
        args = _make_args(session=str(f), mode="cdp", legacy=True, no_gui=True)
        cmd_proxy(args)
        config_call = mock_config_cls.call_args
        assert config_call[1]["gui_mode"] is False

    @patch("tokenade.core.proxy.server.TokenadeProxy")
    @patch("tokenade.core.proxy.server.ProxyConfig")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_legacy_verbose(self, mock_packager_cls, mock_config_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        mock_proxy_cls.from_session_file.return_value = MagicMock()
        args = _make_args(session=str(f), mode="cdp", legacy=True, verbose=True)
        cmd_proxy(args)
        config_call = mock_config_cls.call_args
        assert config_call[1]["verbose"] is True

    @patch("tokenade.core.proxy.server.TokenadeProxy")
    @patch("tokenade.core.proxy.server.ProxyConfig")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_legacy_shows_engine_type(self, mock_packager_cls, mock_config_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        mock_proxy_cls.from_session_file.return_value = MagicMock()
        args = _make_args(session=str(f), mode="cdp", legacy=True)
        cmd_proxy(args)
        output = capsys.readouterr().out
        assert "Legacy" in output

    @patch("tokenade.core.proxy.server.TokenadeProxy")
    @patch("tokenade.core.proxy.server.ProxyConfig")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_legacy_no_fingerprint_line(self, mock_packager_cls, mock_config_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        mock_proxy_cls.from_session_file.return_value = MagicMock()
        args = _make_args(session=str(f), mode="cdp", legacy=True)
        cmd_proxy(args)
        output = capsys.readouterr().out
        assert "curl-cffi" not in output
        assert "Native browser" not in output

    @patch("tokenade.core.proxy.server.TokenadeProxy")
    @patch("tokenade.core.proxy.server.ProxyConfig")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_legacy_custom_port_and_host(self, mock_packager_cls, mock_config_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        mock_proxy_cls.from_session_file.return_value = MagicMock()
        args = _make_args(session=str(f), mode="cdp", legacy=True, port=5000, host="0.0.0.0")
        cmd_proxy(args)
        config_call = mock_config_cls.call_args
        assert config_call[1]["port"] == 5000
        assert config_call[1]["host"] == "0.0.0.0"


# ─── CDP proxy mode ───────────────────────────────────────────────────────

class TestCDPProxyMode:
    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_cdp_proxy_starts(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f))
        cmd_proxy(args)
        mock_proxy_cls.from_session_file.assert_called_once()
        proxy_instance.run.assert_called_once()

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_cdp_config_headless(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), visible=False)
        cmd_proxy(args)
        config_call = mock_proxy_cls.from_session_file.call_args
        config = config_call[0][1]
        assert config.headless is True

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_cdp_config_visible(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), visible=True)
        cmd_proxy(args)
        config_call = mock_proxy_cls.from_session_file.call_args
        config = config_call[0][1]
        assert config.headless is False

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_cdp_shows_engine_type(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f))
        cmd_proxy(args)
        output = capsys.readouterr().out
        assert "CDP" in output

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_cdp_fingerprint_matching(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), fingerprint=True)
        cmd_proxy(args)
        output = capsys.readouterr().out
        assert "curl-cffi" in output

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_cdp_no_fingerprint(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), fingerprint=False)
        cmd_proxy(args)
        output = capsys.readouterr().out
        assert "Native browser" in output

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_cdp_custom_port_displayed(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), port=9999)
        cmd_proxy(args)
        output = capsys.readouterr().out
        assert "9999" in output

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_cdp_session_path_shown(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f))
        cmd_proxy(args)
        output = capsys.readouterr().out
        assert str(f) in output


# ─── Auto-refresh options ─────────────────────────────────────────────────

class TestAutoRefresh:
    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_auto_refresh_enabled(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), auto_refresh=True)
        cmd_proxy(args)
        assert proxy_instance._auto_refresh_config.get("auto_refresh") is True

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_auto_refresh_with_source_browser(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), auto_refresh=True, source_browser="firefox")
        cmd_proxy(args)
        assert proxy_instance._auto_refresh_config.get("source_browser") == "firefox"
        output = capsys.readouterr().out
        assert "Auto-refresh" in output

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_auto_refresh_with_source_profile(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), auto_refresh=True, source_browser="chrome",
                          source_profile="/home/user/.config/google-chrome")
        cmd_proxy(args)
        assert proxy_instance._auto_refresh_config.get("source_profile") == "/home/user/.config/google-chrome"

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_auto_refresh_without_source_browser(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), auto_refresh=True, source_browser=None)
        cmd_proxy(args)
        assert proxy_instance._auto_refresh_config.get("auto_refresh") is True
        assert "source_browser" not in proxy_instance._auto_refresh_config

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_auto_refresh_with_source_browser_no_profile(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), auto_refresh=True, source_browser="chrome", source_profile=None)
        cmd_proxy(args)
        assert proxy_instance._auto_refresh_config.get("source_browser") == "chrome"
        assert "source_profile" not in proxy_instance._auto_refresh_config


# ─── Impersonate option ──────────────────────────────────────────────────

class TestImpersonate:
    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_impersonate_set(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), impersonate="chrome120")
        cmd_proxy(args)
        assert proxy_instance._auto_refresh_config.get("impersonate") == "chrome120"
        output = capsys.readouterr().out
        assert "chrome120" in output

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_impersonate_none_not_set(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), impersonate=None)
        cmd_proxy(args)
        assert "impersonate" not in proxy_instance._auto_refresh_config


# ─── Auto-navigate options ────────────────────────────────────────────────

class TestAutoNavigate:
    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_auto_navigate_enabled(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), auto_navigate=True)
        cmd_proxy(args)
        assert proxy_instance._auto_refresh_config.get("target_url") == "https://example.com"
        output = capsys.readouterr().out
        assert "Auto-navigate" in output

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_auto_navigate_with_target_url(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), auto_navigate=False, target_url="https://custom.site")
        cmd_proxy(args)
        assert proxy_instance._auto_refresh_config.get("target_url") == "https://custom.site"
        output = capsys.readouterr().out
        assert "Auto-navigate" in output

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_auto_navigate_takes_priority_over_get_site_url(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), auto_navigate=True, target_url="https://override.site")
        cmd_proxy(args)
        assert proxy_instance._auto_refresh_config.get("target_url") == "https://override.site"
        proxy_instance._get_site_url.assert_not_called()

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_no_auto_navigate_and_no_target(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), auto_navigate=False, target_url=None)
        cmd_proxy(args)
        assert "target_url" not in proxy_instance._auto_refresh_config


# ─── Browser opening ──────────────────────────────────────────────────────

class TestBrowserOpening:
    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_browser_not_opened_when_disabled(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), no_open_browser=True)
        cmd_proxy(args)
        proxy_instance.run.assert_called_once()

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    @patch("tokenade.cli.proxy.webbrowser")
    @patch("tokenade.cli.proxy.threading.Thread")
    def test_browser_opened_when_enabled(self, mock_thread_cls, mock_webbrowser,
                                         mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), no_open_browser=False)
        cmd_proxy(args)
        mock_thread_cls.assert_called_once()
        mock_thread_cls.return_value.start.assert_called_once()

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    @patch("tokenade.cli.proxy.webbrowser")
    @patch("tokenade.cli.proxy.threading.Thread")
    def test_browser_opened_with_auto_navigate(self, mock_thread_cls, mock_webbrowser,
                                               mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), no_open_browser=False, auto_navigate=True, target_url=None)
        cmd_proxy(args)
        mock_thread_cls.assert_called_once()


# ─── Error handling ───────────────────────────────────────────────────────

class TestErrorHandling:
    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_keyboard_interrupt(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        proxy_instance.run.side_effect = KeyboardInterrupt()
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f))
        cmd_proxy(args)
        assert "Proxy stopped by user" in capsys.readouterr().out

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_port_in_use_error(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        proxy_instance.run.side_effect = OSError("Address already in use")
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), port=8080)
        with pytest.raises(SystemExit) as ei:
            cmd_proxy(args)
        assert ei.value.code == 1
        output = capsys.readouterr().out
        assert "8080" in output
        assert "already in use" in output

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_eaddrinuse_error(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        proxy_instance.run.side_effect = OSError("EADDRINUSE")
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), port=3000)
        with pytest.raises(SystemExit) as ei:
            cmd_proxy(args)
        assert ei.value.code == 1
        output = capsys.readouterr().out
        assert "3000" in output

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_session_not_found_error(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        proxy_instance.run.side_effect = FileNotFoundError("Session not found")
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f))
        with pytest.raises(SystemExit) as ei:
            cmd_proxy(args)
        assert ei.value.code == 1
        output = capsys.readouterr().out
        assert "Session file not found" in output

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_playwright_not_installed(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        proxy_instance.run.side_effect = RuntimeError("playwright not installed")
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f))
        with pytest.raises(SystemExit) as ei:
            cmd_proxy(args)
        assert ei.value.code == 1
        output = capsys.readouterr().out
        assert "Chromium" in output or "playwright install" in output

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_chromium_not_found(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        proxy_instance.run.side_effect = RuntimeError("chromium executable not found")
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f))
        with pytest.raises(SystemExit) as ei:
            cmd_proxy(args)
        assert ei.value.code == 1
        output = capsys.readouterr().out
        assert "Chromium" in output or "playwright install" in output

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_permission_error(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        proxy_instance.run.side_effect = PermissionError("Permission denied")
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f))
        with pytest.raises(SystemExit) as ei:
            cmd_proxy(args)
        assert ei.value.code == 1
        output = capsys.readouterr().out
        assert "Permission denied" in output

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_generic_error(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        proxy_instance.run.side_effect = RuntimeError("something unexpected")
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f))
        with pytest.raises(SystemExit) as ei:
            cmd_proxy(args)
        assert ei.value.code == 1
        output = capsys.readouterr().out
        assert "Proxy failed" in output
        assert "Check logs" in output

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_access_error(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        proxy_instance.run.side_effect = PermissionError("Access denied to session")
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f))
        with pytest.raises(SystemExit) as ei:
            cmd_proxy(args)
        assert ei.value.code == 1
        output = capsys.readouterr().out
        assert "Permission denied" in output

    @patch("asyncio.run", side_effect=KeyboardInterrupt())
    @patch("tokenade.core.proxy.forward_proxy.ForwardProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_forward_proxy_keyboard_interrupt(self, mock_packager_cls, mock_proxy_cls, mock_run, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": []}
        mock_packager_cls.return_value = mock_packager
        mock_proxy = MagicMock()
        mock_proxy_cls.return_value = mock_proxy
        args = _make_args(session=str(f), mode="forward")
        cmd_proxy(args)
        assert "Proxy stopped by user" in capsys.readouterr().out


# ─── Timeout option ───────────────────────────────────────────────────────

class TestTimeoutOption:
    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_timeout_passed_to_config(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), timeout=60)
        cmd_proxy(args)
        config_call = mock_proxy_cls.from_session_file.call_args
        config = config_call[0][1]
        assert config.timeout == 60

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_default_timeout(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f))
        cmd_proxy(args)
        config_call = mock_proxy_cls.from_session_file.call_args
        config = config_call[0][1]
        assert config.timeout == 30


# ─── Header display ───────────────────────────────────────────────────────

class TestHeaderDisplay:
    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_session_path_shown(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f))
        cmd_proxy(args)
        output = capsys.readouterr().out
        assert str(f) in output

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_port_shown(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), port=8080)
        cmd_proxy(args)
        output = capsys.readouterr().out
        assert "8080" in output

    @patch("tokenade.core.proxy.forward_proxy.ForwardProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_mode_shown(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": []}
        mock_packager_cls.return_value = mock_packager
        mock_proxy = MagicMock()
        mock_proxy.start = AsyncMock()
        mock_proxy_cls.return_value = mock_proxy
        args = _make_args(session=str(f), mode="forward")
        cmd_proxy(args)
        output = capsys.readouterr().out
        assert "forward" in output

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_mode_cdp_displayed(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), mode="cdp")
        cmd_proxy(args)
        output = capsys.readouterr().out
        assert "cdp" in output.lower()


# ─── Extension bridge options (target_url for browse proxy) ────────────────

class TestExtensionBridge:
    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    @patch("tokenade.cli.proxy.webbrowser")
    @patch("tokenade.cli.proxy.threading.Thread")
    def test_browser_url_with_target(self, mock_thread_cls, mock_webbrowser,
                                     mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), no_open_browser=False, target_url="https://example.com")
        cmd_proxy(args)
        thread_target = mock_thread_cls.call_args[1]["target"]
        assert callable(thread_target)

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_no_browser_url_without_target(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager
        proxy_instance = MagicMock()
        proxy_instance._auto_refresh_config = {}
        proxy_instance._get_site_url.return_value = "https://example.com"
        mock_proxy_cls.from_session_file.return_value = proxy_instance
        args = _make_args(session=str(f), no_open_browser=True)
        cmd_proxy(args)
        output = capsys.readouterr().out
        assert "Starting proxy server" in output
