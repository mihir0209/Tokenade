"""TUI widget ids must survive hostile names (dots, spaces, leading digits).

Regression test for the ``BadIdentifier: 'select-nowsecure.nl'`` crash:
session/plugin/vault names flow into Textual Button ids, which only allow
``[A-Za-z0-9_-]`` and must not start with a digit.
"""

import re

import pytest

from tokenade.tui.ids import clear_registry, resolve_id, safe_id

_VALID = re.compile(r"^[A-Za-z_-][A-Za-z0-9_-]*$")

NASTY = [
    "nowsecure.nl",          # the original crash (dots)
    "github.com",
    "my session",            # spaces
    "9lives",                # leading digit
    "a/b\\c:d;e@f",          # path/URL junk
    "",                      # empty
    "UPPER.Name-1_x",        # mixed valid + dot
    "discord-handler",       # normal (control)
]

PREFIXES = [
    "select-", "health-", "delete-",
    "install-", "details-",
    "reload-", "configure-", "uninstall-",
    "vault-retrieve-", "vault-delete-",
]


@pytest.fixture(autouse=True)
def _clean():
    clear_registry()
    yield
    clear_registry()


@pytest.mark.parametrize("raw", NASTY)
@pytest.mark.parametrize("prefix", PREFIXES)
def test_safe_id_is_valid_and_roundtrips(raw, prefix):
    wid = safe_id(prefix, raw)
    assert _VALID.match(wid), wid
    assert resolve_id(wid, prefix) == str(raw)


def test_safe_id_collision_disambiguates():
    a = safe_id("select-", "a.b")
    b = safe_id("select-", "a-b")
    assert a != b
    assert resolve_id(a, "select-") == "a.b"
    assert resolve_id(b, "select-") == "a-b"


def test_safe_id_stable_for_same_raw():
    assert safe_id("delete-", "x.y") == safe_id("delete-", "x.y")


def test_resolve_id_falls_back_to_prefix_strip():
    assert resolve_id("select-plain", "select-") == "plain"


def _iter_buttons(widget):
    from textual.widgets import Button

    found = []
    stack = [widget]
    seen = set()
    while stack:
        w = stack.pop()
        if id(w) in seen:
            continue
        seen.add(id(w))
        if isinstance(w, Button):
            found.append(w)
        for attr in ("children", "_pending_children"):
            kids = getattr(w, attr, None)
            if kids:
                try:
                    stack.extend(list(kids))
                except TypeError:
                    pass
    return found


def _assert_compose_buttons_ok(tile):
    yielded = list(tile.compose())
    buttons = []
    for item in yielded:
        buttons.extend(_iter_buttons(item))
    assert buttons, "expected buttons in composed tile"
    for b in buttons:
        assert b.id and _VALID.match(b.id), b.id


def test_session_tile_compose_with_dotted_name():
    pytest.importorskip("textual")
    from tokenade.tui.views.sessions import SessionTile

    tile = SessionTile(
        {
            "name": "nowsecure.nl",
            "file": "/tmp/nowsecure.nl.tokenade",
            "site": "nowsecure.nl",
            "auth": "session_expired",
            "cookies": 1,
            "expired": 0,
            "health": 100.0,
            "url": "https://nowsecure.nl",
            "corrupt": False,
            "size": 1849,
        }
    )
    list(tile.compose())  # raised BadIdentifier before the fix
    _assert_compose_buttons_ok(tile)


def test_session_tile_compose_with_nasty_names():
    pytest.importorskip("textual")
    from tokenade.tui.views.sessions import SessionTile

    for raw in NASTY:
        clear_registry()
        tile = SessionTile({"name": raw or "?", "health": 50.0})
        list(tile.compose())
        _assert_compose_buttons_ok(tile)


def test_plugin_card_compose_with_dotted_name():
    pytest.importorskip("textual")
    from tokenade.tui.views.marketplace import PluginCard

    card = PluginCard({"name": "my.plugin", "version": "1.0"})
    list(card.compose())
    _assert_compose_buttons_ok(card)


def test_installed_row_compose_with_dotted_name():
    pytest.importorskip("textual")
    from tokenade.tui.views.installed import InstalledRow

    row = InstalledRow({"name": "my.plugin", "version": "1.0"})
    list(row.compose())
    _assert_compose_buttons_ok(row)
