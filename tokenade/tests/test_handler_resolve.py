"""Tests for legacy handler resolution (P3)."""

from tokenade.plugin import PluginResult
from tokenade.handlers.resolve import resolve_legacy_handler_class


class _EmptyPluginLoader:
    def load_all(self):
        return []

    def get_handler(self, _site_name):
        return None


def _use_loader(monkeypatch, loader_cls):
    import tokenade.core.integration.plugin_loader as plugin_loader

    monkeypatch.setattr(plugin_loader, "PluginLoader", loader_cls)


def test_resolve_unknown_returns_none(monkeypatch):
    """After cleanup, all concrete handlers removed — resolve returns None."""
    _use_loader(monkeypatch, _EmptyPluginLoader)
    assert resolve_legacy_handler_class(None) is None
    assert resolve_legacy_handler_class("google") is None
    assert resolve_legacy_handler_class("gmail") is None
    assert resolve_legacy_handler_class("github") is None
    assert resolve_legacy_handler_class("gh") is None
    assert resolve_legacy_handler_class("youtube") is None
    assert resolve_legacy_handler_class("openai") is None


def test_resolve_strips_and_lowercases(monkeypatch):
    """Whitespace/case normalization still works (returns None for all)."""
    _use_loader(monkeypatch, _EmptyPluginLoader)
    assert resolve_legacy_handler_class("  GitHub  ") is None
    assert resolve_legacy_handler_class("GH") is None


def test_resolve_wraps_site_handler_plugin(monkeypatch):
    class FakePlugin:
        name = "discord-handler"

        def get_site_config(self):
            return {
                "name": "discord",
                "domains": ["discord.com"],
                "critical_cookies": ["sid"],
                "dashboard_url": "https://discord.com/channels/@me",
            }

        def get_export_domains(self):
            return ["discord.com"]

        def get_critical_cookies(self):
            return ["sid"]

        def validate(self, session):
            return PluginResult(
                success=True,
                data={"valid": bool(session.get("cookies")), "score": 100.0},
            )

        def inject_session(self, _context, _session):
            return PluginResult(success=True, data={"injected_count": 1})

    class PluginLoader:
        def load_all(self):
            return []

        def get_handler(self, site_name):
            return FakePlugin() if site_name == "discord" else None

    _use_loader(monkeypatch, PluginLoader)

    handler_class = resolve_legacy_handler_class("discord")
    assert handler_class is not None
    assert handler_class.SITE_NAME == "discord"
    assert handler_class.DOMAINS == ["discord.com"]
    assert handler_class.CRITICAL_COOKIES == ["sid"]
