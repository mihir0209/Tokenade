"""Tests for legacy handler resolution (P3)."""

from tokenade.handlers.resolve import resolve_legacy_handler_class


def test_resolve_unknown_returns_none():
    """After cleanup, all concrete handlers removed — resolve returns None."""
    assert resolve_legacy_handler_class(None) is None
    assert resolve_legacy_handler_class("google") is None
    assert resolve_legacy_handler_class("gmail") is None
    assert resolve_legacy_handler_class("github") is None
    assert resolve_legacy_handler_class("gh") is None
    assert resolve_legacy_handler_class("youtube") is None
    assert resolve_legacy_handler_class("openai") is None


def test_resolve_strips_and_lowercases():
    """Whitespace/case normalization still works (returns None for all)."""
    assert resolve_legacy_handler_class("  GitHub  ") is None
    assert resolve_legacy_handler_class("GH") is None
