"""Safe Textual widget ids for dynamic names.

Session names (`nowsecure.nl`), plugin names, and vault entry ids can
contain dots, spaces, or other characters that Textual rejects in widget
ids (`BadIdentifier` crash at compose time). This module centralizes:

- :func:`safe_id` — build a valid, collision-free widget id for any raw
  string, remembering the mapping.
- :func:`resolve_id` — map a widget id back to the original raw string.

Pure stdlib so unit tests never need Textual installed.
"""

import re

_INVALID_CHARS = re.compile(r"[^A-Za-z0-9_-]")

# widget id -> original raw string
_REGISTRY: dict = {}


def safe_id(prefix, raw):
    """Return a valid Textual id of the form ``f"{prefix}{slug}"``.

    Args:
        prefix: Stable prefix including any trailing separator
            (e.g. ``"select-"``).
        raw: Arbitrary original string (session/plugin/entry name).

    The slug replaces every invalid character with ``-``; collisions
    between distinct raw strings get a numeric suffix. Re-registering
    the same raw string returns the same id.
    """
    original = str(raw)
    slug = _INVALID_CHARS.sub("-", original).strip("-") or "item"
    if slug[0].isdigit():
        slug = "n-" + slug
    base = "%s%s" % (prefix, slug)
    candidate = base
    suffix = 2
    while candidate in _REGISTRY and _REGISTRY[candidate] != original:
        candidate = "%s-%d" % (base, suffix)
        suffix += 1
    _REGISTRY[candidate] = original
    return candidate


def resolve_id(widget_id, prefix):
    """Return the original string for a widget id built by :func:`safe_id`.

    Falls back to stripping ``prefix`` so ids built before this helper
    existed (or static ids) keep working.
    """
    if widget_id in _REGISTRY:
        return _REGISTRY[widget_id]
    if widget_id.startswith(prefix):
        return widget_id[len(prefix):]
    return widget_id


def clear_registry():
    """Forget all mappings (tests only)."""
    _REGISTRY.clear()
