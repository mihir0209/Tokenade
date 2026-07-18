"""Tests for launch profile resolution semantics."""

from types import SimpleNamespace
from unittest.mock import patch

from tokenade.cli.handlers.browser_ops import _resolve_launch_profile


def _profile(name, path, browser="firefox", is_default=False):
    return SimpleNamespace(name=name, path=path, browser=browser, is_default=is_default)


def test_resolve_launch_profile_prefers_default_when_name_missing():
    default = _profile("default", "/profiles/default", is_default=True)
    other = _profile("Work", "/profiles/work")

    with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery") as cls:
        cls.return_value.discover_browser.return_value = [other, default]
        result = _resolve_launch_profile("firefox", None)

    assert result is default


def test_resolve_launch_profile_matches_display_name():
    work = _profile("Work", "/profiles/Profile 1")

    with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery") as cls:
        cls.return_value.discover_browser.return_value = [work]
        result = _resolve_launch_profile("firefox", "work")

    assert result is work


def test_resolve_launch_profile_matches_directory_name():
    work = _profile("Work", "/profiles/Profile 1")

    with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery") as cls:
        cls.return_value.discover_browser.return_value = [work]
        result = _resolve_launch_profile("firefox", "Profile 1")

    assert result is work


def test_resolve_launch_profile_refreshes_cache_when_requested():
    work = _profile("Work", "/profiles/Profile 1")

    with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery") as cls:
        cls.return_value.refresh_cache.return_value = {"firefox": [work]}
        result = _resolve_launch_profile("firefox", "Work", refresh_profiles=True)

    assert result is work
    cls.return_value.refresh_cache.assert_called_once()
