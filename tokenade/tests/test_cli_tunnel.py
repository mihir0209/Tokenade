"""Tests for `tokenade tunnel ...` (offline paths; no relay needed)."""
import json
from types import SimpleNamespace

import pytest

from tokenade.cli import tunnel as tunnel_mod
from tokenade.cli.tunnel import cmd_tunnel


def _args(**kw):
    base = {"tunnel_action": "status", "relay": None, "remote_ref": None,
            "token": None, "code": None, "snapshot_file": None,
            "host": "127.0.0.1", "port": 8765}
    base.update(kw)
    return SimpleNamespace(**base)


def test_unknown_action_exits():
    with pytest.raises(SystemExit):
        cmd_tunnel(_args(tunnel_action="bogus"))


def test_serve_needs_relay_and_ref():
    with pytest.raises(SystemExit):
        cmd_tunnel(_args(tunnel_action="serve"))
    with pytest.raises(SystemExit):
        cmd_tunnel(_args(tunnel_action="serve", relay="ws://x"))


def test_share_and_pair_roundtrip(tmp_path, monkeypatch, capsys):
    pairings = tmp_path / "pairings.json"
    approved = {}

    def fake_create(remote_ref, relay_url, token, store=None):
        assert store is None
        pairings.write_text(json.dumps({"CODE-1": {
            "remote_ref": remote_ref, "relay_url": relay_url,
            "consumer_token": token, "created_at": 0, "ttl_s": 999999999}}))
        return {"code": "CODE-1", "remote_ref": remote_ref, "relay_url": relay_url}

    def fake_redeem(code, store=None):
        data = json.loads(pairings.read_text())
        record = data.pop(code)
        pairings.write_text(json.dumps(data))
        return record

    saved = {}

    def fake_save(ref, url, token, store=None, ssh=None):
        saved.update(ref=ref, url=url, token=token, ssh=ssh)

    monkeypatch.setattr("tokenade.core.tunnel.pairing.create_pairing", fake_create)
    monkeypatch.setattr("tokenade.core.tunnel.pairing.redeem_pairing", fake_redeem)
    monkeypatch.setattr(
        "tokenade.core.tunnel.pairing.save_consumer_record", fake_save)
    monkeypatch.setattr(tunnel_mod, "_load_approved", lambda store=None: approved)
    monkeypatch.setattr(tunnel_mod, "_save_approved",
                        lambda data, store=None: approved.update(data))

    cmd_tunnel(_args(tunnel_action="share", relay="ws://r:1", remote_ref="ref-9"))
    out = capsys.readouterr().out
    assert "CODE-1" in out and "ref-9" in approved

    cmd_tunnel(_args(tunnel_action="pair", code="CODE-1"))
    assert saved["ref"] == "ref-9" and saved["token"]


def test_pair_bundle_json(monkeypatch, capsys):
    saved = {}
    monkeypatch.setattr(
        "tokenade.core.tunnel.pairing.save_consumer_record",
        lambda ref, url, token, store=None, ssh=None: saved.update(
            ref=ref, token=token, ssh=ssh),
    )
    bundle = json.dumps({"relay_url": "ws://r:1", "remote_ref": "b1",
                         "consumer_token": "tok",
                         "ssh": {"host": "box", "port": 22, "remote_port": 18080}})
    cmd_tunnel(_args(tunnel_action="pair", code=bundle))
    assert saved == {"ref": "b1", "token": "tok",
                     "ssh": {"host": "box", "port": 22, "remote_port": 18080}}
    assert "Paired" in capsys.readouterr().out


def test_pair_bad_bundle_exits():
    with pytest.raises(SystemExit):
        cmd_tunnel(_args(tunnel_action="pair", code="{bad json"))


def test_pair_bundle_file(tmp_path, monkeypatch, capsys):
    saved = {}
    monkeypatch.setattr(
        "tokenade.core.tunnel.pairing.save_consumer_record",
        lambda ref, url, token, store=None, ssh=None: saved.update(
            ref=ref, token=token),
    )
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps({"relay_url": "ws://r:1", "remote_ref": "f1",
                                  "consumer_token": "tok"}))
    cmd_tunnel(_args(tunnel_action="pair", code=None, bundle_file=str(bundle)))
    assert saved == {"ref": "f1", "token": "tok"}
    assert "Paired" in capsys.readouterr().out


def test_pair_bundle_file_missing_exits(tmp_path):
    with pytest.raises(SystemExit):
        cmd_tunnel(_args(tunnel_action="pair", code=None,
                         bundle_file=str(tmp_path / "nope.json")))


def test_pair_missing_code_exits():
    with pytest.raises(SystemExit):
        cmd_tunnel(_args(tunnel_action="pair", code=""))


def test_status_no_remotes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "tokenade.core.tunnel.pairing._tunnel_dir", lambda: tmp_path)
    cmd_tunnel(_args(tunnel_action="status"))
    assert "pair" in capsys.readouterr().out


def test_revoke_clears_token(monkeypatch, capsys):
    approved = {"ref-9": ["a", "b"]}
    monkeypatch.setattr(tunnel_mod, "_load_approved", lambda store=None: approved)
    monkeypatch.setattr(tunnel_mod, "_save_approved",
                        lambda data, store=None: approved.update(data))
    cmd_tunnel(_args(tunnel_action="revoke", remote_ref="ref-9", token="a"))
    assert approved["ref-9"] == ["b"]
    cmd_tunnel(_args(tunnel_action="revoke", remote_ref="ref-9"))
    assert "ref-9" not in approved
    assert "Revoked" in capsys.readouterr().out


def test_revoke_needs_ref():
    with pytest.raises(SystemExit):
        cmd_tunnel(_args(tunnel_action="revoke"))


def test_token_points_at_keyring(capsys):
    cmd_tunnel(_args(tunnel_action="token", remote_ref="ref-9"))
    out = capsys.readouterr().out
    assert "keyring" in out and "ref-9" in out
