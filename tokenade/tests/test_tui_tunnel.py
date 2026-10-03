"""Tests for the Tunnel TUI tab (logic-level; no display needed)."""
import json


def _fake_keyring(monkeypatch, tokens):
    class _FakeKeyring:
        @staticmethod
        def set_password(service, user, pw):
            tokens[(service, user)] = pw

        @staticmethod
        def get_password(service, user):
            return tokens.get((service, user))

    monkeypatch.setitem(__import__("sys").modules, "keyring", _FakeKeyring)


def test_collect_status_empty(tmp_path, monkeypatch):
    from tokenade.cli.tunnel import collect_tunnel_status

    monkeypatch.setattr(
        "tokenade.core.tunnel.pairing._tunnel_dir", lambda: tmp_path)
    assert collect_tunnel_status() == []


def test_collect_status_rows(tmp_path, monkeypatch):
    from tokenade.cli.tunnel import collect_tunnel_status

    monkeypatch.setattr(
        "tokenade.core.tunnel.pairing._tunnel_dir", lambda: tmp_path)
    (tmp_path / "consumers.json").write_text(json.dumps({
        "r1": {"relay_url": "ws://127.0.0.1:9", "token_ref": "k",
               "saved_at": 0},
        "r2": {"relay_url": "", "token_ref": "k", "saved_at": 0,
               "ssh": {"host": "127.0.0.1", "port": 22, "remote_port": 9}},
    }))
    _fake_keyring(monkeypatch, {("tokenade-tunnel", "r1"): "tok"})
    rows = {row["remote_ref"]: row for row in collect_tunnel_status()}
    assert rows["r1"]["token_state"] == "present (keyring)"
    assert rows["r1"]["transport"] == "wss-reverse"
    assert rows["r1"]["relay_reachable"] is False  # nothing on port 9
    assert rows["r2"]["transport"] == "ssh-reverse"
    assert rows["r2"]["token_state"].startswith("MISSING")


def test_collect_status_filters_remote(tmp_path, monkeypatch):
    from tokenade.cli.tunnel import collect_tunnel_status

    monkeypatch.setattr(
        "tokenade.core.tunnel.pairing._tunnel_dir", lambda: tmp_path)
    (tmp_path / "consumers.json").write_text(json.dumps({
        "r1": {"relay_url": "ws://x", "token_ref": "k", "saved_at": 0},
    }))
    assert len(collect_tunnel_status("r1")) == 1
    assert collect_tunnel_status("nope") == []


def test_format_status_rows():
    from tokenade.tui.views.tunnel import format_status_rows

    assert "No paired remotes" in format_status_rows([])
    text = format_status_rows([{
        "remote_ref": "r1", "relay_url": "ws://h:1",
        "token_state": "present (keyring)", "relay_reachable": True,
        "transport": "wss-reverse"}])
    assert "r1" in text and "reachable" in text


async def test_tunnel_view_mounts():
    from textual.app import App

    from tokenade.tui.views.tunnel import TunnelView

    class _Tiny(App):
        def compose(self):
            yield TunnelView()

    app = _Tiny()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one("#tunnel-refresh") is not None
        assert app.query_one("#tunnel-status") is not None
        app.query_one(TunnelView).render_status([])
        text = str(app.query_one("#tunnel-status").render())
        assert "No paired remotes" in text


def test_tunnel_ids_are_safe():
    # Static ids (no dotted names) need no sanitizing; resolve_id falls back
    # to prefix-stripping for them. The mount test proves Textual accepts them.
    from tokenade.tui.ids import resolve_id

    assert resolve_id("tunnel-refresh", "tunnel-") == "refresh"
