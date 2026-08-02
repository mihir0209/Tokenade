"""Behavioral tests for plugin-backed site configs (Sprint 0)."""

import json
from pathlib import Path

from tokenade.core.importer.site_configs import (
    discover_plugin_site_configs,
    get_site_config,
    list_sites,
    load_site_config_file,
    normalize_site_config,
    config_from_plugin_instance,
)
from tokenade.plugin.base import SiteHandlerPlugin
from tokenade.plugin.api import PluginResult


class _StubHandler(SiteHandlerPlugin):
    name = "stub-handler"
    version = "0.0.1"
    description = "test"

    def extract_session(self, _browser_context, url: str) -> PluginResult:
        return PluginResult(success=True, data={})

    def inject_session(self, _browser_context, session: dict) -> PluginResult:
        return PluginResult(success=True, data={})


def test_normalize_site_config_aliases_and_defaults():
    cfg = normalize_site_config(
        {
            "name": "Acme",
            "domains": ["acme.com"],
            "critical_cookies": ["sid"],
            "dashboard_url": "https://acme.com/app",
            "login_indicator_css": "a[href='/login']",
        },
        plugin_name="acme-handler",
    )
    assert cfg["name"] == "Acme"
    assert cfg["domains"] == ["acme.com"]
    assert cfg["validate_url"] == "https://acme.com/app"
    assert cfg["logged_out_selectors"] == ["a[href='/login']"]
    assert cfg["preferred_plugin"] == "acme-handler"
    assert cfg["wait_seconds"] == 5


def test_get_site_config_unknown_returns_empty_dict():
    cfg = get_site_config("nonexistent_site_xyz_12345", plugins_dir=Path("/tmp/no-plugins-xyz"))
    assert cfg == {}
    assert isinstance(cfg, dict)


def test_discover_from_plugin_site_config_json(tmp_path):
    plugin = tmp_path / "acme-handler"
    plugin.mkdir()
    (plugin / "plugin.json").write_text(
        json.dumps(
            {
                "name": "acme-handler",
                "type": "handler",
                "entry_point": "plugin.py",
                "entry_class": "X",
            }
        )
    )
    (plugin / "site_config.json").write_text(
        json.dumps(
            {
                "name": "acme",
                "domains": ["acme.com", ".acme.com"],
                "critical_cookies": ["session"],
                "dashboard_url": "https://acme.com",
            }
        )
    )
    found = discover_plugin_site_configs(tmp_path)
    assert "acme" in found
    assert "acme-handler" in found
    assert found["acme"]["domains"] == ["acme.com", ".acme.com"]
    assert get_site_config("acme", plugins_dir=tmp_path)["critical_cookies"] == ["session"]
    assert "acme" in list_sites(plugins_dir=tmp_path)


def test_site_handler_loads_site_config_json(tmp_path):
    plugin = tmp_path / "acme-handler"
    plugin.mkdir()
    (plugin / "site_config.json").write_text(
        json.dumps(
            {
                "name": "acme",
                "domains": ["acme.com"],
                "critical_cookies": ["sid", "token"],
                "login_url": "https://acme.com/login",
                "dashboard_url": "https://acme.com/home",
            }
        )
    )
    h = _StubHandler()
    h.set_plugin_dir(plugin)
    assert h.get_export_domains() == ["acme.com"]
    assert h.get_critical_cookies() == ["sid", "token"]
    assert h.get_login_url() == "https://acme.com/login"
    assert h.get_dashboard_url() == "https://acme.com/home"
    assert h.can_handle("https://www.acme.com/path")
    assert not h.can_handle("https://other.example/")
    cfg = config_from_plugin_instance(h)
    assert cfg.get("name") == "acme"
    assert "sid" in cfg.get("critical_cookies", [])


def test_non_handler_plugin_site_config_ignored(tmp_path):
    plugin = tmp_path / "webhook-notify"
    plugin.mkdir()
    (plugin / "plugin.json").write_text(
        json.dumps({"name": "webhook-notify", "type": "notification", "entry_point": "plugin.py"})
    )
    (plugin / "site_config.json").write_text(
        json.dumps({"name": "should-not-load", "domains": ["x.com"]})
    )
    found = discover_plugin_site_configs(tmp_path)
    assert "should-not-load" not in found


def test_invalid_site_config_json_skipped(tmp_path):
    plugin = tmp_path / "broken-handler"
    plugin.mkdir()
    (plugin / "plugin.json").write_text(
        json.dumps({"name": "broken-handler", "type": "handler", "entry_point": "plugin.py"})
    )
    (plugin / "site_config.json").write_text("{not valid")
    assert load_site_config_file(plugin / "site_config.json") == {}
    assert discover_plugin_site_configs(tmp_path) == {}


def test_list_sites_sorted_unique_primary_names(tmp_path):
    plugin = tmp_path / "foo-handler"
    plugin.mkdir()
    (plugin / "plugin.json").write_text(
        json.dumps({"name": "foo-handler", "type": "handler", "entry_point": "p.py"})
    )
    (plugin / "site_config.json").write_text(
        json.dumps({"name": "foo", "domains": ["foo.com"], "critical_cookies": []})
    )
    sites = list_sites(plugins_dir=tmp_path)
    assert sites == sorted(sites)
    assert "foo" in sites


# ── Sprint D: plugin match precedence ──────────────────────────


def test_discover_first_wins_when_two_plugins_claim_same_site(tmp_path):
    """First handler plugin by sorted path wins when two claim the same site name."""
    for plugin_name, critical in [("aaa-handler", ["aaa_cookie"]), ("zzz-handler", ["zzz"])]:
        d = tmp_path / plugin_name
        d.mkdir()
        (d / "plugin.json").write_text(
            json.dumps({"name": plugin_name, "type": "handler", "entry_point": "p.py"})
        )
        (d / "site_config.json").write_text(
            json.dumps({
                "name": "shared",
                "domains": ["shared.com"],
                "critical_cookies": critical,
            })
        )
    found = discover_plugin_site_configs(tmp_path)
    assert "shared" in found
    assert found["shared"]["critical_cookies"] == ["aaa_cookie"]


def test_get_site_config_fuzzy_substring_match(tmp_path):
    """get_site_config falls back to substring containment for unknown site names."""
    d = tmp_path / "acme-handler"
    d.mkdir()
    (d / "plugin.json").write_text(
        json.dumps({"name": "acme-handler", "type": "handler", "entry_point": "p.py"})
    )
    (d / "site_config.json").write_text(
        json.dumps({"name": "acme", "domains": ["acme.com"], "critical_cookies": ["sid"]})
    )
    assert get_site_config("acm", plugins_dir=tmp_path).get("critical_cookies") == ["sid"]
    assert get_site_config("acmeextra", plugins_dir=tmp_path).get("critical_cookies") == ["sid"]


def test_discover_multi_key_indexing_manifest_site_name_differs(tmp_path):
    """Manifest site_name and config name both indexed as separate site keys."""
    d = tmp_path / "custom"
    d.mkdir()
    (d / "plugin.json").write_text(
        json.dumps({
            "name": "custom", "type": "handler", "entry_point": "p.py",
            "site_name": "alt",
        })
    )
    (d / "site_config.json").write_text(
        json.dumps({"name": "primary", "domains": ["example.com"], "critical_cookies": ["tok"]})
    )
    found = discover_plugin_site_configs(tmp_path)
    assert "primary" in found
    assert "alt" in found
    assert "custom" in found
    assert found["primary"]["critical_cookies"] == ["tok"]


def test_discover_plugin_without_handler_suffix(tmp_path):
    """Plugin named 'acme' (no -handler suffix) still discovered as site 'acme'."""
    d = tmp_path / "acme"
    d.mkdir()
    (d / "plugin.json").write_text(
        json.dumps({"name": "acme", "type": "handler", "entry_point": "p.py"})
    )
    (d / "site_config.json").write_text(
        json.dumps({"name": "acme", "domains": ["acme.com"], "critical_cookies": ["sid"]})
    )
    found = discover_plugin_site_configs(tmp_path)
    assert "acme" in found
    assert found["acme"]["critical_cookies"] == ["sid"]


def test_discover_catalog_sites_without_root_site_config(tmp_path):
    """Handler plugins can expose multiple site configs via sites/*.json."""
    plugin = tmp_path / "generic-handler"
    sites = plugin / "sites"
    sites.mkdir(parents=True)
    (plugin / "plugin.json").write_text(
        json.dumps({"name": "generic-handler", "type": "handler", "entry_point": "plugin.py"})
    )
    (sites / "github.json").write_text(
        json.dumps({
            "name": "github",
            "domains": ["github.com", ".github.com"],
            "critical_cookies": ["user_session"],
            "session_check_url": "https://github.com/settings/profile",
        })
    )

    found = discover_plugin_site_configs(tmp_path)

    assert "github" in found
    assert found["github"]["session_check_url"] == "https://github.com/settings/profile"
    assert found["github"]["preferred_plugin"] == "generic-handler"


def test_discover_explicit_github_and_discord_probe_urls(tmp_path):
    """Catalog and standalone handler configs expose explicit probe URLs."""
    generic = tmp_path / "generic-handler"
    sites = generic / "sites"
    sites.mkdir(parents=True)
    (generic / "plugin.json").write_text(
        json.dumps({"name": "generic-handler", "type": "handler", "entry_point": "plugin.py"})
    )
    (sites / "github.json").write_text(json.dumps({
        "name": "github",
        "domains": ["github.com"],
        "session_check_url": "https://github.com/settings/profile",
    }))

    discord = tmp_path / "discord-handler"
    discord.mkdir()
    (discord / "plugin.json").write_text(
        json.dumps({"name": "discord-handler", "type": "handler", "entry_point": "plugin.py"})
    )
    (discord / "site_config.json").write_text(json.dumps({
        "name": "discord",
        "domains": ["discord.com"],
        "session_check_url": "https://discord.com/channels/@me",
    }))

    found = discover_plugin_site_configs(tmp_path)

    assert found["github"]["session_check_url"] == "https://github.com/settings/profile"
    assert found["discord"]["session_check_url"] == "https://discord.com/channels/@me"
