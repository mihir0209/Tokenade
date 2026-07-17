"""Unit tests for the internal recommend module.

Tests the three stage functions (recommend_site / recommend_plugin /
recommend_browser), the composite recommend(), and the public API
re-exports. Mix of pure tests (with synthetic inputs) and integration
checks (against the real installed marketplace plugins at ~/.tokenade).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from tokenade.core.recommend import (
    Recommendation,
    RecommendationConfig,
    recommend,
    recommend_browser,
    recommend_plugin,
    recommend_site,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GOOGLE_COOKIES = [
    {"name": "SID", "value": "x", "domain": ".google.com"},
    {"name": "HSID", "value": "y", "domain": ".google.com"},
    {"name": "SSID", "value": "z", "domain": ".google.com"},
    {"name": "APISID", "value": "w", "domain": ".google.com"},
]

CHATGPT_COOKIES = [
    {"name": "__Secure-next-auth.session-token", "value": "x", "domain": "chatgpt.com"},
    {"name": "oai-did", "value": "y", "domain": ".openai.com"},
]

GITHUB_COOKIES = [
    {"name": "user_session", "value": "x", "domain": "github.com"},
    {"name": "logged_in", "value": "yes", "domain": ".github.com"},
]


def _installed_plugin_dir() -> Path:
    return Path.home() / ".tokenade" / "plugins"


def _marketplace_installed() -> bool:
    """Return True if marketplace plugins are installed at ~/.tokenade/plugins."""
    pd = _installed_plugin_dir()
    return pd.is_dir() and (pd / "generic-handler" / "plugin.json").is_file()


# ---------------------------------------------------------------------------
# recommend_site
# ---------------------------------------------------------------------------


class TestRecommendSite:
    def test_session_metadata_site_name_wins(self):
        sess = {"site_name": "github", "cookies": GOOGLE_COOKIES}
        assert recommend_site(session=sess) == "github"

    def test_session_metadata_alias_normalized(self):
        sess = {"site_name": "openai", "cookies": []}
        # alias openai -> chatgpt
        assert recommend_site(session=sess) == "chatgpt"

    def test_cookie_detection_google(self):
        assert recommend_site(cookies=GOOGLE_COOKIES) == "google"

    def test_cookie_detection_chatgpt_via_domains(self):
        # chatgpt isn't in static SITE_DETECTION but is in installed site_configs
        if not _marketplace_installed():
            pytest.skip("marketplace plugins not installed")
        # SiteFilter.detect_site asks SITE_DETECTION first; if chatgpt isn't
        # there but cookies match nothing else, the domain cross-check against
        # installed site_configs trips in step 4.
        site = recommend_site(cookies=CHATGPT_COOKIES)
        assert site in {"chatgpt", "openai"}  # alias normalization

    def test_url_host_match(self):
        assert recommend_site(url="https://myaccount.google.com/foo") == "google"

    def test_url_with_unknown_host(self):
        assert recommend_site(url="https://random-example-xyz.com") is None

    def test_domains_match(self):
        if not _marketplace_installed():
            pytest.skip("marketplace plugins not installed")
        result = recommend_site(domains=["google.com", "accounts.google.com"])
        # google-flow-handler has labs.google only; google.com matches static SITE_DETECTION
        assert result == "google"

    def test_empty_input_returns_none(self):
        assert recommend_site() is None


# ---------------------------------------------------------------------------
# recommend_plugin
# ---------------------------------------------------------------------------


class TestRecommendPlugin:
    def test_session_embedded_site_handler_wins(self):
        session = {
            "site_name": "discord",
            "cookies": [],
            "metadata": {
                "site_handler": {
                    "plugin_name": "discord-handler",
                    "plugin_version": "1.2.0",
                }
            },
        }

        assert recommend_plugin(session=session) == "discord-handler"

    def test_google_prefers_flow_handler(self):
        if not _marketplace_installed():
            pytest.skip("marketplace plugins not installed")
        # google has a preferred_plugin set on its installed site_config.
        plugin = recommend_plugin(site="google")
        # Either google-flow-handler (preferred) or generic-handler (multisite);
        # the legacy installed google-flow-handler should win via preferred_plugin.
        assert plugin in {"google-flow-handler", "generic-handler"}, f"got {plugin!r}"

    def test_chatgpt_uses_generic_handler_multisite(self):
        if not _marketplace_installed():
            pytest.skip("marketplace plugins not installed")
        plugin = recommend_plugin(site="chatgpt")
        assert plugin == "generic-handler", f"got {plugin!r}"

    def test_github_uses_generic_handler_multisite(self):
        if not _marketplace_installed():
            pytest.skip("marketplace plugins not installed")
        plugin = recommend_plugin(site="github")
        assert plugin == "generic-handler", f"got {plugin!r}"

    def test_unknown_site_returns_none_or_catchall(self):
        # No installed handler; recommend_plugin returns None (or generic-handler
        # only if site is truthy — here the site is unknown).
        result = recommend_plugin(site="random-nonexistent-site")
        # generic-handler is installed; catch-all branch fires because site is set
        assert result in {"generic-handler", None}

    def test_url_only_finds_chatgpt(self):
        if not _marketplace_installed():
            pytest.skip("marketplace plugins not installed")
        plugin = recommend_plugin(url="https://chatgpt.com")
        assert plugin == "generic-handler", f"got {plugin!r}"

    def test_utility_handler_plugin_not_selected(self):
        # session-backup is a SiteHandlerPlugin with can_handle=True for everything
        # but it must not be recommended as the chatgpt handler.
        if not _marketplace_installed():
            pytest.skip("marketplace plugins not installed")
        plugin = recommend_plugin(
            site="chatgpt", cookies=CHATGPT_COOKIES, domains=["chatgpt.com"]
        )
        assert plugin != "session-backup"
        assert plugin != "session-merge"


# ---------------------------------------------------------------------------
# recommend_browser
# ---------------------------------------------------------------------------


class TestRecommendBrowser:
    def test_session_metadata_override(self):
        sess = {"metadata": {"automation_browser": "firefox"}}
        assert recommend_browser(session=sess) == "firefox"

    def test_per_site_override_google(self):
        assert recommend_browser(site="google") == "cloak"

    def test_per_site_override_discord(self):
        assert recommend_browser(site="discord") == "cloak"

    def test_per_site_override_chatgpt(self):
        assert recommend_browser(site="chatgpt") == "cloak"

    def test_plugin_manifest_browser_default(self):
        if not _marketplace_installed():
            pytest.skip("marketplace plugins not installed")
        # auto-refresh plugin.json has browser.default = cloak
        browser = recommend_browser(plugin="auto-refresh")
        assert browser == "cloak"

    def test_config_override(self):
        cfg = RecommendationConfig(automation_browser_override="brave")
        assert recommend_browser(site="github", config=cfg) == "brave"

    def test_falls_back_to_default(self):
        # No site, no plugin, no override -> config default (cloak from DEFAULTS)
        assert recommend_browser() == "cloak"


# ---------------------------------------------------------------------------
# recommend (composite)
# ---------------------------------------------------------------------------


class TestRecommendComposite:
    def test_session_embedded_site_handler_reason(self):
        session = {
            "site_name": "discord",
            "cookies": [],
            "metadata": {
                "site_handler": {
                    "plugin_name": "discord-handler",
                    "plugin_version": "1.2.0",
                }
            },
        }

        r = recommend(session=session)
        assert r.plugin == "discord-handler"
        assert any("metadata.site_handler" in reason for reason in r.reasons)

    def test_empty_input_returns_browser_only(self):
        r = recommend()
        assert r.site is None
        assert r.plugin is None
        assert r.browser == "cloak"
        assert 0.0 <= r.confidence <= 1.0
        assert isinstance(r.reasons, list) and len(r.reasons) >= 3
        assert isinstance(r, Recommendation)

    def test_google_session_full_recommendation(self):
        sess = {
            "site_name": "google",
            "cookies": GOOGLE_COOKIES,
            "metadata": {},
        }
        r = recommend(session=sess)
        assert r.site == "google"
        if _marketplace_installed():
            assert r.plugin in {"google-flow-handler", "generic-handler"}
        assert r.browser == "cloak"
        assert r.confidence > 0.5
        assert any("site" in reason or "cookies" in reason for reason in r.reasons)

    def test_chatgpt_url_full_recommendation(self):
        r = recommend(url="https://chatgpt.com")
        assert r.site == "chatgpt"
        if _marketplace_installed():
            assert r.plugin == "generic-handler"
        assert r.browser == "cloak"
        assert r.confidence > 0.5

    def test_session_metadata_browser_override_propagates(self):
        sess = {
            "site_name": "github",
            "cookies": GITHUB_COOKIES,
            "metadata": {"automation_browser": "firefox"},
        }
        r = recommend(session=sess)
        assert r.browser == "firefox"

    def test_reasons_explain_each_field(self):
        r = recommend(url="https://chatgpt.com")
        # at least one reason for site, plugin, and browser
        joined = " ".join(r.reasons).lower()
        assert "site matched" in joined or "site" in joined
        assert "plugin" in joined
        assert "browser" in joined

    def test_confidence_in_unit_interval(self):
        cases = [
            recommend(),
            recommend(url="https://chatgpt.com"),
            recommend(domains=["google.com", "accounts.google.com"]),
            recommend(cookies=GOOGLE_COOKIES),
            recommend(session={"site_name": "github", "cookies": GITHUB_COOKIES}),
        ]
        for r in cases:
            assert 0.0 <= r.confidence <= 1.0

    def test_returns_recommendation_type(self):
        r = recommend()
        assert isinstance(r, Recommendation)

    def test_as_dict_contains_all_fields(self):
        d = recommend().as_dict()
        assert set(d.keys()) == {"site", "plugin", "browser", "confidence", "reasons"}


# ---------------------------------------------------------------------------
# Public API re-exports
# ---------------------------------------------------------------------------


class TestPublicAPI:
    def test_tokenade_exports_recommend(self):
        import tokenade

        for name in (
            "Recommendation",
            "RecommendationConfig",
            "recommend",
            "recommend_site",
            "recommend_plugin",
            "recommend_browser",
        ):
            assert hasattr(tokenade, name), f"missing public export: {name}"

    def test_recommendation_is_callable(self):
        import tokenade

        r = tokenade.recommend()
        assert isinstance(r, tokenade.Recommendation)
