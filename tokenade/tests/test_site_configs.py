"""Behavioral tests for site_configs (mutation-oriented).

Replaces weak test_site_configs_coverage.py smoke asserts.
"""

import json
from pathlib import Path

from tokenade.core.importer.site_configs import (
    get_site_config,
    list_sites,
    SITE_CONFIGS,
)


def test_list_sites_includes_builtins_and_is_sorted():
    sites = list_sites()
    assert isinstance(sites, list)
    assert sites == sorted(sites)
    assert "github" in sites
    assert "google" in sites
    # built-in table is subset of list (JSON overlays may add more)
    for name in SITE_CONFIGS:
        assert name in sites


def test_get_site_config_unknown_returns_empty_dict():
    cfg = get_site_config("nonexistent_site_xyz_12345")
    assert cfg == {}
    # must not return None (callers use .get)
    assert isinstance(cfg, dict)


def test_get_site_config_github_has_critical_cookies_and_domains():
    cfg = get_site_config("github")
    assert cfg.get("name") or cfg.get("domains")
    domains = cfg.get("domains") or []
    assert any("github" in d for d in domains)
    critical = cfg.get("critical_cookies") or []
    assert "user_session" in critical or "logged_in" in critical


def test_get_site_config_case_insensitive():
    a = get_site_config("GitHub")
    b = get_site_config("github")
    assert a == b


def test_json_overlay_merges_preferred_plugin(tmp_path, monkeypatch):
    """JSON under CWD site_configs/ overlays built-in keys (P1 honesty path)."""
    overlay_dir = tmp_path / "site_configs"
    overlay_dir.mkdir()
    (overlay_dir / "github.json").write_text(
        json.dumps(
            {
                "name": "github",
                "preferred_plugin": "github-handler",
                "domains": ["github.com", ".github.com", "gist.github.com"],
            }
        )
    )
    monkeypatch.chdir(tmp_path)
    # Clear any cached state if added later — get_site_config reloads each call today
    cfg = get_site_config("github")
    assert cfg.get("preferred_plugin") == "github-handler"
    domains = cfg.get("domains") or []
    assert "gist.github.com" in domains


def test_site_configs_required_fields_and_wait_seconds():
    for name, cfg in SITE_CONFIGS.items():
        assert isinstance(name, str) and name
        assert "name" in cfg
        assert isinstance(cfg.get("domains"), list)
        assert isinstance(cfg.get("critical_cookies"), list)
        assert "wait_seconds" in cfg
        assert isinstance(cfg["wait_seconds"], int)
        assert cfg["wait_seconds"] > 0


def test_invalid_json_overlay_skipped(tmp_path, monkeypatch):
    overlay_dir = tmp_path / "site_configs"
    overlay_dir.mkdir()
    (overlay_dir / "broken.json").write_text("{not valid json")
    (overlay_dir / "custom.json").write_text(
        json.dumps({"name": "custom_overlay_site", "domains": ["example.com"]})
    )
    monkeypatch.chdir(tmp_path)
    assert get_site_config("broken") == {}
    cfg = get_site_config("custom_overlay_site")
    assert cfg.get("domains") == ["example.com"]
    assert "custom_overlay_site" in list_sites()
