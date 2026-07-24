"""Tests for Phase 63 — CloakBrowser integration."""

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from tokenade.core.browser.stealth.cloak import (
    CloakBrowserBackend,
    is_cloakbrowser_available,
    get_binary_info,
    get_stealth_backend_name,
)
from tokenade.core.browser.session_state import (
    tokenade_to_storage_state,
    storage_state_to_tokenade,
    load_as_storage_state,
)


# ─── Helper ─────────────────────────────────────────────────

def _make_tokenade_session(tmp_path, name="test", site="github",
                           cookie_count=5, has_local_storage=False):
    """Create a minimal .tokenade session file."""
    import time
    now = int(time.time())
    cookies = []
    for i in range(cookie_count):
        cookies.append({
            "name": f"cookie_{i}",
            "value": f"val_{i}",
            "domain": ".example.com",
            "path": "/",
            "expires": now + 86400 * 30,
            "secure": True,
            "httpOnly": False,
        })

    session = {
        "version": "2.0",
        "site_name": site,
        "auth_status": "logged_in",
        "created_at": "2026-07-01T00:00:00Z",
        "cookies": cookies,
    }
    if has_local_storage:
        session["local_storage"] = {"key1": "value1", "key2": "value2"}

    path = tmp_path / f"{name}.tokenade"
    path.write_text(json.dumps(session))
    return str(path)


# ─── CloakBrowser Availability Tests ────────────────────────

class TestCloakBrowserAvailability:
    @pytest.mark.skipif(not is_cloakbrowser_available(), reason="cloakbrowser not installed")
    def test_package_installed(self):
        """cloakbrowser should be installed in test env."""
        assert is_cloakbrowser_available() is True

    def test_binary_info_returns_dict(self):
        info = get_binary_info()
        assert isinstance(info, dict)
        assert "installed" in info

    def test_get_stealth_backend_name(self):
        name = get_stealth_backend_name()
        assert name in ("cloakbrowser", "playwright")

    def test_backend_init(self):
        backend = CloakBrowserBackend()
        assert backend is not None

    def test_backend_is_available(self):
        backend = CloakBrowserBackend()
        # May or may not be available depending on binary download
        result = backend.is_available()
        assert isinstance(result, bool)

    def test_backend_get_info(self):
        backend = CloakBrowserBackend()
        info = backend.get_info()
        assert isinstance(info, dict)
        assert "package_installed" in info
        assert "binary_ready" in info
        assert "stealth_backend" in info


# ─── Session State Conversion Tests ─────────────────────────

class TestSessionStateConversion:
    def test_tokenade_to_storage_state(self, tmp_path):
        session_path = _make_tokenade_session(tmp_path, cookie_count=3)
        state = tokenade_to_storage_state(session_path)

        assert "cookies" in state
        assert "origins" in state
        assert len(state["cookies"]) == 3

    def test_cookie_format(self, tmp_path):
        session_path = _make_tokenade_session(tmp_path, cookie_count=1)
        state = tokenade_to_storage_state(session_path)

        cookie = state["cookies"][0]
        assert "name" in cookie
        assert "value" in cookie
        assert "domain" in cookie
        assert "path" in cookie
        assert "secure" in cookie
        assert "httpOnly" in cookie
        assert "sameSite" in cookie
        assert "expires" in cookie

    def test_cookie_sameSite_mapping(self, tmp_path):
        session_path = _make_tokenade_session(tmp_path, cookie_count=1)
        state = tokenade_to_storage_state(session_path)

        cookie = state["cookies"][0]
        assert cookie["sameSite"] in ("None", "Lax", "Strict")

    def test_cookie_expires_conversion(self, tmp_path):
        session_path = _make_tokenade_session(tmp_path, cookie_count=1)
        state = tokenade_to_storage_state(session_path)

        cookie = state["cookies"][0]
        # Should be a Unix timestamp (positive) or -1
        assert isinstance(cookie["expires"], (int, float))

    def test_local_storage_conversion(self, tmp_path):
        session_path = _make_tokenade_session(
            tmp_path, cookie_count=1, has_local_storage=True
        )
        state = tokenade_to_storage_state(session_path)

        assert len(state["origins"]) > 0
        origin = state["origins"][0]
        assert "origin" in origin
        assert "localStorage" in origin
        assert len(origin["localStorage"]) == 2

    def test_storage_state_to_tokenade(self, tmp_path):
        # Create a Playwright storage_state file
        state = {
            "cookies": [
                {
                    "name": "session",
                    "value": "abc",
                    "domain": ".github.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                    "sameSite": "Lax",
                    "expires": 1700000000,
                },
            ],
            "origins": [
                {
                    "origin": "https://github.com",
                    "localStorage": [
                        {"name": "key1", "value": "val1"},
                    ],
                },
            ],
        }
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps(state))

        session = storage_state_to_tokenade(str(state_path))

        assert session["version"] == "2.0"
        assert len(session["cookies"]) == 1
        assert session["cookies"][0]["name"] == "session"
        assert session["local_storage"]["key1"] == "val1"

    def test_roundtrip(self, tmp_path):
        """Convert .tokenade → storage_state → .tokenade preserves data."""
        session_path = _make_tokenade_session(tmp_path, cookie_count=5)

        # Convert to storage_state
        state = tokenade_to_storage_state(session_path)

        # Write storage_state
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps(state))

        # Convert back
        session = storage_state_to_tokenade(str(state_path))

        assert len(session["cookies"]) == 5

    def test_load_as_storage_state(self, tmp_path):
        session_path = _make_tokenade_session(tmp_path, cookie_count=3)
        output = load_as_storage_state(session_path)

        assert os.path.exists(output)
        with open(output) as f:
            state = json.load(f)
        assert len(state["cookies"]) == 3

        # Cleanup
        os.unlink(output)

    def test_load_as_storage_state_custom_path(self, tmp_path):
        session_path = _make_tokenade_session(tmp_path, cookie_count=2)
        output_path = str(tmp_path / "custom_state.json")
        result = load_as_storage_state(session_path, output_path)

        assert result == output_path
        assert os.path.exists(output_path)

    def test_empty_session(self, tmp_path):
        session_path = _make_tokenade_session(tmp_path, cookie_count=0)
        state = tokenade_to_storage_state(session_path)
        assert state["cookies"] == []

    def test_multiple_sites(self, tmp_path):
        for site in ["google", "github", "discord"]:
            session_path = _make_tokenade_session(tmp_path, name=site, site=site)
            state = tokenade_to_storage_state(session_path)
            assert len(state["cookies"]) == 5


# ─── CLI Parser Tests ──────────────────────────────────────

class TestCloakCLIParser:
    def test_cloak_info_parser(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["cloak", "info"])
        assert a.cloak_action == "info"

    def test_cloak_install_parser(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["cloak", "install"])
        assert a.cloak_action == "install"

    def test_cloak_serve_parser(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["cloak", "serve", "--port", "9222"])
        assert a.cloak_action == "serve"
        assert a.port == 9222

    def test_cloak_serve_with_proxy(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["cloak", "serve", "--proxy", "http://proxy:8080"])
        assert a.proxy == "http://proxy:8080"

    def test_launch_humanize_flag(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["launch", "-s", "test.tokenade", "--humanize"])
        assert a.humanize is True

    def test_launch_geoip_flag(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["launch", "-s", "test.tokenade", "--geoip"])
        assert a.geoip is True

    def test_launch_no_cloak_flag(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["launch", "-s", "test.tokenade", "--no-cloak"])
        assert a.no_cloak is True

    def test_launch_profile_flag(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["launch", "--browser", "firefox", "--profile", "default"])
        assert a.profile == "default"

    def test_launch_profile_safety_flags(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["launch", "--browser", "firefox", "--profile", "default", "--use-original-profile", "--refresh-profiles"])
        assert a.use_original_profile is True
        assert a.refresh_profiles is True

    def test_cloak_help(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        with pytest.raises(SystemExit):
            p.parse_args(["cloak", "--help"])


# ─── Backend Method Tests (mocked) ──────────────────────────

class TestCloakBackendMethods:
    @patch("tokenade.core.browser.stealth.cloak._cloakbrowser")
    @patch("tokenade.core.browser.stealth.cloak._CLOAKBROWSER_AVAILABLE", True)
    def test_launch_calls_cloakbrowser(self, mock_cb):
        mock_cb.launch = MagicMock(return_value="browser")
        mock_cb.binary_info.return_value = {"installed": True}

        backend = CloakBrowserBackend()
        result = backend.launch(headless=True, humanize=True)

        mock_cb.launch.assert_called_once()
        assert result == "browser"

    @patch("tokenade.core.browser.stealth.cloak._cloakbrowser")
    @patch("tokenade.core.browser.stealth.cloak._CLOAKBROWSER_AVAILABLE", True)
    def test_launch_context_with_storage_state(self, mock_cb):
        mock_cb.launch_context = MagicMock(return_value="context")
        mock_cb.binary_info.return_value = {"installed": True}

        backend = CloakBrowserBackend()
        backend.launch_context(storage_state="state.json")

        mock_cb.launch_context.assert_called_once()
        call_kwargs = mock_cb.launch_context.call_args
        assert call_kwargs[1]["storage_state"] == "state.json"

    @patch("tokenade.core.browser.stealth.cloak._cloakbrowser")
    @patch("tokenade.core.browser.stealth.cloak._CLOAKBROWSER_AVAILABLE", True)
    def test_launch_persistent(self, mock_cb):
        mock_cb.launch_persistent_context = MagicMock(return_value="ctx")
        mock_cb.binary_info.return_value = {"installed": True}

        backend = CloakBrowserBackend()
        backend.launch_persistent("./profile")

        mock_cb.launch_persistent_context.assert_called_once()

    @patch("tokenade.core.browser.stealth.cloak._CLOAKBROWSER_AVAILABLE", False)
    def test_launch_raises_when_not_available(self):
        backend = CloakBrowserBackend()
        with pytest.raises(RuntimeError, match="not available"):
            backend.launch()

    @patch("tokenade.core.browser.stealth.cloak._CLOAKBROWSER_AVAILABLE", False)
    def test_launch_context_raises_when_not_available(self):
        backend = CloakBrowserBackend()
        with pytest.raises(RuntimeError, match="not available"):
            backend.launch_context()

    @patch("tokenade.core.browser.stealth.cloak._CLOAKBROWSER_AVAILABLE", False)
    def test_launch_persistent_raises_when_not_available(self):
        backend = CloakBrowserBackend()
        with pytest.raises(RuntimeError, match="not available"):
            backend.launch_persistent("./profile")

    @patch("tokenade.core.browser.stealth.cloak._cloakbrowser")
    @patch("tokenade.core.browser.stealth.cloak._CLOAKBROWSER_AVAILABLE", True)
    def test_launch_with_fingerprint_seed(self, mock_cb):
        mock_cb.launch = MagicMock(return_value="browser")
        mock_cb.binary_info.return_value = {"installed": True}

        backend = CloakBrowserBackend()
        backend.launch(fingerprint_seed=42069)

        call_kwargs = mock_cb.launch.call_args
        assert "--fingerprint=42069" in call_kwargs[1]["args"]

    @patch("tokenade.core.browser.stealth.cloak.get_binary_info")
    @patch("tokenade.core.browser.stealth.cloak._cloakbrowser")
    @patch("tokenade.core.browser.stealth.cloak._CLOAKBROWSER_AVAILABLE", True)
    def test_serve_cdp(self, mock_cb, mock_info, tmp_path):
        binary = tmp_path / "chrome"
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)
        mock_info.return_value = {
            "installed": True,
            "binary_path": str(binary),
        }
        mock_cb.binary_info.return_value = mock_info.return_value

        backend = CloakBrowserBackend()
        mock_proc = MagicMock(pid=12345)
        mock_proc.poll.return_value = None
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            with patch("urllib.request.urlopen", return_value=mock_resp):
                with patch("time.sleep"):
                    proc = backend.serve_cdp(port=9222, headless=True)
        assert proc.pid == 12345
        cmd = mock_popen.call_args[0][0]
        assert str(binary) in cmd
        assert "--remote-debugging-port=9222" in cmd
        assert "--headless=new" in cmd
        assert "--no-sandbox" in cmd


# ─── Stealth Backend Detection Tests ────────────────────────

class TestStealthBackendDetection:
    @patch("tokenade.core.browser.stealth.cloak.is_binary_installed", return_value=True)
    def test_cloakbrowser_when_binary_installed(self, mock):
        assert get_stealth_backend_name() == "cloakbrowser"

    @patch("tokenade.core.browser.stealth.cloak.is_binary_installed", return_value=False)
    def test_playwright_when_binary_not_installed(self, mock):
        assert get_stealth_backend_name() == "playwright"
