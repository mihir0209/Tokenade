"""Tests for Phase 61 — Site Handler Plugins."""

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from tokenade.plugin.api import PluginResult


_plugins_installed = (Path.home() / ".tokenade" / "plugins").exists()


def _load_plugin(name):
    """Load a plugin by name from ~/.tokenade/plugins/ or official repo."""
    from tokenade.core.integration.plugin_loader import PluginLoader
    loader = PluginLoader()
    loader.load_all()
    all_plugins = loader.list_all()
    for p in all_plugins:
        if p.name == name:
            return p.instance
    # Try direct load
    import importlib.util
    import sys
    from pathlib import Path
    plugin_dir = Path.home() / ".tokenade" / "plugins" / name
    if not plugin_dir.exists():
        plugin_dir = Path.home() / "Projects" / "tokenade-plugins" / "plugins" / name
    plugin_file = plugin_dir / "plugin.py"
    if plugin_file.exists():
        spec = importlib.util.spec_from_file_location(
            f"{name}.plugin", str(plugin_file)
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"{name}.plugin"] = mod
        spec.loader.exec_module(mod)
        # Find the handler class
        import json
        manifest = plugin_dir / "plugin.json"
        if manifest.exists():
            with open(manifest) as f:
                meta = json.load(f)
            cls_name = meta.get("entry_class", "")
            if hasattr(mod, cls_name):
                inst = getattr(mod, cls_name)()
                if hasattr(inst, "set_plugin_dir"):
                    inst.set_plugin_dir(plugin_dir)
                return inst
    return None


def _plugin_available(name):
    """Check if a plugin is installed."""
    from pathlib import Path
    if (Path.home() / ".tokenade" / "plugins" / name).exists():
        return True
    # Check official repo layout
    sibling = Path.home() / "Projects" / "tokenade-plugins" / "plugins" / name
    if sibling.exists():
        return True
    return False


def _require_site(handler, site):
    """Select a generic-handler site catalog, skipping when the installed
    plugin revision does not ship that catalog (marketplace drift)."""
    if handler is not None and hasattr(handler, "set_site"):
        try:
            handler.set_site(site)
        except ValueError:
            pytest.skip(f"installed generic-handler lacks {site!r} catalog")
    return handler


# ─── Google Handler Tests ───────────────────────────────────

@pytest.mark.skipif(
    not _plugin_available("generic-handler"),
    reason="generic-handler not installed",
)
class TestGoogleHandler:
    def _get_handler(self):
        return _require_site(_load_plugin("generic-handler"), "google")

    def test_can_handle_google(self):
        h = self._get_handler()
        assert h.can_handle("https://mail.google.com") is True
        assert h.can_handle("https://accounts.google.com") is True
        assert h.can_handle("https://drive.google.com") is True
        assert h.can_handle("https://youtube.com") is True

    def test_cannot_handle_empty(self):
        h = self._get_handler()
        assert h.can_handle("") is False

    def test_extract_session(self):
        h = self._get_handler()
        ctx = MagicMock()
        ctx.cookies.return_value = [
            {"name": "SID", "value": "abc", "domain": ".google.com"},
            {"name": "HSID", "value": "def", "domain": ".google.com"},
            {"name": "other", "value": "xyz", "domain": ".example.com"},
        ]
        result = h.extract_session(ctx, "https://mail.google.com")
        cookies = result.data["cookies"] if isinstance(result, PluginResult) else result["cookies"]
        assert len(cookies) == 2

    def test_inject_session(self):
        h = self._get_handler()
        ctx = MagicMock()
        session = {
            "cookies": [
                {"name": "SID", "value": "abc", "domain": ".google.com",
                 "path": "/", "secure": True, "httpOnly": True,
                 "sameSite": "Lax", "expires": int(time.time()) + 86400},
            ]
        }
        result = h.inject_session(ctx, session)
        success = result.success if isinstance(result, PluginResult) else bool(result)
        assert success is True
        ctx.add_cookies.assert_called_once()

    def test_validate_healthy(self):
        h = self._get_handler()
        session = {
            "cookies": [
                {"name": c, "value": "abc", "domain": ".google.com",
                 "expires": int(time.time()) + 86400}
                for c in ["SID", "HSID", "SSID", "APISID", "SAPISID",
                          "__Secure-1PSID", "__Secure-3PSID",
                          "__Secure-1PAPISID", "__Secure-3PAPISID",
                          "NID", "OSID", "__Secure-OSID", "__Host-GAPS", "COMPASS"]
            ]
        }
        result = h.validate(session)
        data = result.data if isinstance(result, PluginResult) else result
        assert data.get("valid") is True or result.success is True
        assert data["score"] == 100

    def test_validate_missing_critical(self):
        h = self._get_handler()
        session = {
            "cookies": [
                {"name": "NID", "value": "abc", "domain": ".google.com",
                 "expires": int(time.time()) + 86400},
            ]
        }
        result = h.validate(session)
        data = result.data if isinstance(result, PluginResult) else result
        assert data.get("score", 100) < 100


# ─── GitHub Handler Tests ───────────────────────────────────

@pytest.mark.skipif(
    not _plugin_available("generic-handler"),
    reason="generic-handler not installed",
)
class TestGitHubHandler:
    def _get_handler(self):
        return _require_site(_load_plugin("generic-handler"), "github")

    def test_can_handle_github(self):
        h = self._get_handler()
        assert h.can_handle("https://github.com") is True
        assert h.can_handle("https://gist.github.com") is True

    def test_cannot_handle_empty(self):
        h = self._get_handler()
        assert h.can_handle("") is False

    def test_extract_session(self):
        h = self._get_handler()
        ctx = MagicMock()
        ctx.cookies.return_value = [
            {"name": "user_session", "value": "abc", "domain": ".github.com"},
            {"name": "logged_in", "value": "yes", "domain": ".github.com"},
            {"name": "other", "value": "xyz", "domain": ".example.com"},
        ]
        result = h.extract_session(ctx, "https://github.com")
        cookies = result.data["cookies"] if isinstance(result, PluginResult) else result["cookies"]
        assert len(cookies) == 2

    def test_validate_healthy(self):
        h = self._get_handler()
        session = {
            "cookies": [
                {"name": c, "value": "abc", "domain": ".github.com",
                 "expires": int(time.time()) + 86400}
                for c in ["user_session", "__Host-user_session_same_site",
                          "__Host-device_id", "has_recent_activity",
                          "logged_in", "_gh_sess"]
            ]
        }
        result = h.validate(session)
        data = result.data if isinstance(result, PluginResult) else result
        assert data["valid"] is True
        assert data["score"] == 100


# ─── Discord Handler Tests ──────────────────────────────────

@pytest.mark.skipif(
    not _plugin_available("discord-handler"),
    reason="discord-handler not installed",
)
class TestDiscordHandler:
    def _get_handler(self):
        return _load_plugin("discord-handler")

    def test_can_handle_discord(self):
        h = self._get_handler()
        assert h.can_handle("https://discord.com") is True
        assert h.can_handle("https://discordapp.com") is True

    def test_cannot_handle_other(self):
        h = self._get_handler()
        assert h.can_handle("https://google.com") is False

    def test_validate_with_token(self):
        h = self._get_handler()
        session = {
            "cookies": [
                {"name": "__dcfduid", "value": "abc", "domain": ".discord.com"},
            ],
            "local_storage": {"token": "abc123"},
        }
        result = h.validate(session)
        assert result["valid"] is True
        assert result["score"] >= 60

    def test_validate_without_token(self):
        h = self._get_handler()
        session = {
            "cookies": [],
            "local_storage": {},
        }
        result = h.validate(session)
        assert result["valid"] is False


# ─── Generic Handler Tests ──────────────────────────────────

@pytest.mark.skipif(
    not _plugin_available("generic-handler"),
    reason="generic-handler not installed",
)
class TestGenericHandler:
    def _get_handler(self):
        return _load_plugin("generic-handler")

    def test_can_handle_any_url(self):
        h = self._get_handler()
        assert h.can_handle("https://example.com") is True
        assert h.can_handle("https://any-site.org") is True

    def test_extract_session(self):
        h = self._get_handler()
        ctx = MagicMock()
        ctx.cookies.return_value = [
            {"name": "session", "value": "abc", "domain": "example.com"},
            {"name": "token", "value": "xyz", "domain": "example.com"},
        ]
        session = h.extract_session(ctx, "https://example.com")
        assert session["auth_status"] == "logged_in"
        assert len(session["cookies"]) == 2

    def test_validate_healthy(self):
        h = self._get_handler()
        session = {
            "cookies": [
                {"name": "session", "value": "abc", "domain": "example.com",
                 "expires": int(time.time()) + 86400},
            ]
        }
        result = h.validate(session)
        assert result["valid"] is True
        assert result["score"] == 100

    def test_validate_expired(self):
        h = self._get_handler()
        session = {
            "cookies": [
                {"name": "session", "value": "abc", "domain": "example.com",
                 "expires": int(time.time()) - 3600},
            ]
        }
        result = h.validate(session)
        assert result["score"] == 50.0

    def test_validate_empty(self):
        h = self._get_handler()
        session = {"cookies": []}
        result = h.validate(session)
        assert result["valid"] is False


# ─── Plugin Discovery Tests ────────────────────────────────

@pytest.mark.skipif(not _plugins_installed, reason="~/.tokenade/plugins/ not present (CI)")
class TestPluginDiscovery:
    def test_google_flow_handler_installed(self):
        from pathlib import Path
        assert (Path.home() / ".tokenade" / "plugins" / "google-flow-handler").exists()

    def test_oauth_flow_handler_installed(self):
        from pathlib import Path
        assert (Path.home() / ".tokenade" / "plugins" / "oauth-flow-handler").exists()

    def test_discord_handler_installed(self):
        from pathlib import Path
        assert (Path.home() / ".tokenade" / "plugins" / "discord-handler").exists()

    def test_generic_handler_installed(self):
        from pathlib import Path
        assert (Path.home() / ".tokenade" / "plugins" / "generic-handler").exists()

    def test_all_handlers_loadable(self):
        for name in ["google-flow-handler", "oauth-flow-handler", "discord-handler", "generic-handler"]:
            handler = _load_plugin(name)
            assert handler is not None, f"Failed to load {name}"
            assert hasattr(handler, "can_handle")
            assert hasattr(handler, "extract_session")
            assert hasattr(handler, "inject_session")
            assert hasattr(handler, "validate")

    def test_registry_has_all_handlers(self):
        """Offline snapshot — avoid flaky live GitHub registry (429 / vanity metrics)."""
        from unittest.mock import patch
        from tokenade.core.integration.plugin_registry import PluginRegistry
        offline = [
            {"name": n, "version": "1.0.0", "description": "x"}
            for n in (
                "google-flow-handler", "oauth-flow-handler",
                "discord-handler", "generic-handler",
            )
        ]
        reg = PluginRegistry()
        with patch.object(reg, "search", return_value=offline):
            plugins = reg.get_popular(limit=100)
        names = {p.get("name") for p in plugins}
        assert "google-flow-handler" in names
        assert "oauth-flow-handler" in names
        assert "discord-handler" in names
        assert "generic-handler" in names
