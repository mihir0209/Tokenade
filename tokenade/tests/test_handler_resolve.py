"""Tests for legacy handler resolution (P3)."""

from tokenade.handlers.resolve import resolve_legacy_handler_class
from tokenade.handlers.google import GoogleHandler
from tokenade.handlers.github import GitHubHandler


def test_resolve_google_default():
    assert resolve_legacy_handler_class(None) is GoogleHandler
    assert resolve_legacy_handler_class("google") is GoogleHandler
    assert resolve_legacy_handler_class("gmail") is GoogleHandler


def test_resolve_github_aliases():
    assert resolve_legacy_handler_class("github") is GitHubHandler
    assert resolve_legacy_handler_class("gh") is GitHubHandler


def test_resolve_unknown_falls_back_to_google():
    assert resolve_legacy_handler_class("not-a-real-site") is GoogleHandler
