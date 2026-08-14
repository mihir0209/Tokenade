import json
import os
import time
from pathlib import Path

import pytest

from tokenade.core.sync import PeerConfig, PeerSync
from tokenade.core.sync.peer import LocalTransport, SFTPTransport


def session(path: Path, marker: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": "3.0",
                "created_at": "2026-08-10T00:00:00Z",
                "site_name": marker,
                "auth_status": "unknown",
                "cookies": [],
            }
        )
    )


def engine(tmp_path, require_encrypted=False):
    sync = PeerSync(str(tmp_path / "local"), str(tmp_path / "state"))
    sync.add_peer(
        PeerConfig(
            "backup",
            "local",
            str(tmp_path / "remote"),
            require_encrypted=require_encrypted,
        )
    )
    return sync


def test_local_only_file_plans_and_runs_push(tmp_path):
    sync = engine(tmp_path)
    session(tmp_path / "local/a.tokenade", "local")
    plan = sync.plan("backup")
    assert plan["actions"][0]["action"] == "push"
    result = sync.run("backup")
    assert result["errors"] == []
    assert (tmp_path / "remote/a.tokenade").exists()


def test_remote_only_file_pulls_atomically(tmp_path):
    sync = engine(tmp_path)
    session(tmp_path / "remote/a.tokenade", "remote")
    result = sync.run("backup")
    assert result["errors"] == []
    assert (
        json.loads((tmp_path / "local/a.tokenade").read_text())["site_name"] == "remote"
    )


def test_three_way_conflict_is_not_resolved_by_mtime(tmp_path):
    sync = engine(tmp_path)
    session(tmp_path / "local/a.tokenade", "base")
    sync.run("backup")
    session(tmp_path / "local/a.tokenade", "local-change")
    session(tmp_path / "remote/a.tokenade", "remote-change")
    plan = sync.plan("backup")
    assert plan["conflicts"][0]["action"] == "conflict"
    result = sync.run("backup")
    assert result["conflicts"]
    assert (
        json.loads((tmp_path / "local/a.tokenade").read_text())["site_name"]
        == "local-change"
    )
    assert (
        json.loads((tmp_path / "remote/a.tokenade").read_text())["site_name"]
        == "remote-change"
    )


def test_remote_change_since_plan_is_not_overwritten(tmp_path):
    sync = engine(tmp_path)
    session(tmp_path / "local/a.tokenade", "base")
    sync.run("backup")
    session(tmp_path / "local/a.tokenade", "new-local")
    plan = sync.plan("backup")
    session(tmp_path / "remote/a.tokenade", "raced")
    # A fresh run recognizes both changed and records a conflict.
    result = sync.run("backup")
    assert result["conflicts"]
    assert (
        json.loads((tmp_path / "remote/a.tokenade").read_text())["site_name"] == "raced"
    )


def test_remote_create_after_expected_absence_is_rejected(tmp_path):
    sync = engine(tmp_path)
    source = tmp_path / "local/a.tokenade"
    session(source, "local")
    transport = sync._transport(sync._peer("backup"))
    transport.probe()
    session(tmp_path / "remote/a.tokenade", "raced")
    try:
        transport.upload_atomic(source, "a.tokenade", None)
    except RuntimeError as exc:
        assert "changed" in str(exc)
    else:
        raise AssertionError("remote create race was overwritten")


def test_push_uploads_staged_snapshot_not_live_source(tmp_path, monkeypatch):
    sync = engine(tmp_path)
    source = tmp_path / "local/a.tokenade"
    session(source, "planned")
    transport = sync._transport(sync._peer("backup"))
    real_upload = transport.upload_atomic

    def mutate_then_upload(staged, name, expected):
        session(source, "mutated-after-stage")
        return real_upload(staged, name, expected)

    monkeypatch.setattr(sync, "_transport", lambda peer: transport)
    monkeypatch.setattr(transport, "upload_atomic", mutate_then_upload)
    result = sync.run("backup")
    assert result["errors"] == []
    assert (
        json.loads((tmp_path / "remote/a.tokenade").read_text())["site_name"]
        == "planned"
    )


def test_baseline_deletion_is_a_conflict(tmp_path):
    sync = engine(tmp_path)
    session(tmp_path / "local/a.tokenade", "base")
    sync.run("backup")
    (tmp_path / "remote/a.tokenade").unlink()
    assert sync.plan("backup")["conflicts"]


def test_remote_peer_blocks_plaintext_by_default(tmp_path):
    sync = engine(tmp_path, require_encrypted=True)
    session(tmp_path / "local/a.tokenade", "plain")
    result = sync.run("backup")
    assert "plaintext upload blocked" in result["errors"][0]["error"]
    assert not (tmp_path / "remote/a.tokenade").exists()


def test_failed_plaintext_pull_removes_temporary_file(tmp_path):
    sync = engine(tmp_path, require_encrypted=True)
    session(tmp_path / "remote/a.tokenade", "plain")
    result = sync.run("backup")
    assert "plaintext pull blocked" in result["errors"][0]["error"]
    assert not list((tmp_path / "local").glob(".*.tmp"))


def test_encrypted_detection_rejects_spoofed_magic_header(tmp_path):
    sync = engine(tmp_path, require_encrypted=True)
    spoofed = tmp_path / "local/spoof.tokenade"
    spoofed.write_bytes(b"TOKENADE_ENCRYPTED" + b"\x00" * 69)
    result = sync.run("backup")
    assert "plaintext upload blocked" in result["errors"][0]["error"]
    assert not (tmp_path / "remote/spoof.tokenade").exists()


def test_encrypted_detection_rejects_truncated_envelope(tmp_path):
    from tokenade.core.crypto.encryptor import TokenadeEncryptor

    sync = engine(tmp_path, require_encrypted=True)
    real = TokenadeEncryptor().encrypt(b'{"site_name":"x"}', "password123")
    truncated = tmp_path / "local/trunc.tokenade"
    truncated.write_bytes(real[:30])
    result = sync.run("backup")
    assert "plaintext upload blocked" in result["errors"][0]["error"]
    assert not (tmp_path / "remote/trunc.tokenade").exists()


def test_encrypted_detection_accepts_real_envelope(tmp_path):
    from tokenade.core.crypto.encryptor import TokenadeEncryptor

    sync = engine(tmp_path, require_encrypted=True)
    real = TokenadeEncryptor().encrypt(
        b'{"site_name":"x","cookies":[]}', "password123"
    )
    (tmp_path / "local/real.tokenade").write_bytes(real)
    result = sync.run("backup")
    assert result["errors"] == []
    assert (tmp_path / "remote/real.tokenade").exists()


def test_remove_peer_clears_baselines_and_history(tmp_path):
    sync = engine(tmp_path)
    session(tmp_path / "local/a.tokenade", "base")
    sync.run("backup")
    assert sync._base("backup") != {}
    sync.remove_peer("backup")
    assert sync.list_peers() == []
    assert sync._base("backup") == {}


def test_recreated_file_after_both_sides_deleted_pushes(tmp_path):
    sync = engine(tmp_path)
    session(tmp_path / "local/a.tokenade", "base")
    sync.run("backup")
    (tmp_path / "local/a.tokenade").unlink()
    (tmp_path / "remote/a.tokenade").unlink()
    sync.run("backup")
    assert sync._base("backup") == {}
    session(tmp_path / "local/a.tokenade", "recreated")
    plan = sync.plan("backup")
    assert plan["actions"][0]["action"] == "push"
    result = sync.run("backup")
    assert result["errors"] == []
    assert (tmp_path / "remote/a.tokenade").exists()


def test_peer_and_baseline_persist_across_instances(tmp_path):
    first = engine(tmp_path)
    session(tmp_path / "local/a.tokenade", "base")
    first.run("backup")
    second = PeerSync(str(tmp_path / "local"), str(tmp_path / "state"))
    assert second.list_peers()[0].name == "backup"
    assert second.plan("backup")["actions"][0]["action"] == "noop"


def test_sftp_lock_is_opened_exclusive_and_writable(tmp_path, monkeypatch):
    opened = []

    class Handle:
        def write(self, value):
            assert value

        def close(self):
            pass

        def read(self):
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class SFTP:
        def open(self, path, mode):
            opened.append(mode)
            if mode == "x":
                raise OSError("File not open for writing")
            return Handle()

        def put(self, source, destination):
            pass

        def chmod(self, path, mode):
            pass

        def posix_rename(self, source, destination):
            pass

        def remove(self, path):
            pass

    transport = SFTPTransport(PeerConfig("p", "ssh", "remote"))
    transport.sftp = SFTP()
    monkeypatch.setattr(transport, "list_objects", lambda: {})
    source = tmp_path / "a.tokenade"
    source.write_text("{}")

    transport.upload_atomic(source, "a.tokenade", None)

    assert opened[0] == "wx"


# ── CR-09: advisory lock contention ───────────────────────────────────────────


def test_upload_atomic_fails_closed_when_locked(tmp_path):
    """A fresh lock held by another writer causes upload_atomic to fail closed."""
    root = tmp_path / "remote"
    root.mkdir()
    source = tmp_path / "local" / "a.tokenade"
    source.parent.mkdir()
    source.write_text("{}")

    lock = root / ".a.tokenade.tokenade-sync-lock"
    lock.write_text("other-owner")

    transport = LocalTransport(str(root))
    with pytest.raises(RuntimeError, match="remote object is locked"):
        transport.upload_atomic(source, "a.tokenade", None)


def test_upload_atomic_takes_over_stale_lock(tmp_path):
    """A stale lock (older than 10 minutes) is taken over and the upload succeeds."""
    root = tmp_path / "remote"
    root.mkdir()
    source = tmp_path / "local" / "a.tokenade"
    source.parent.mkdir()
    source.write_text('{"site_name":"stale-takeover"}')

    lock = root / ".a.tokenade.tokenade-sync-lock"
    lock.write_text("stale-owner")
    old = time.time() - 700
    os.utime(lock, (old, old))

    transport = LocalTransport(str(root))
    meta = transport.upload_atomic(source, "a.tokenade", None)

    assert meta.name == "a.tokenade"
    assert (root / "a.tokenade").read_text() == '{"site_name":"stale-takeover"}'
    assert not lock.exists()


def test_upload_atomic_cleans_up_lock_on_success(tmp_path):
    """The lock file is removed after a successful upload."""
    root = tmp_path / "remote"
    root.mkdir()
    source = tmp_path / "local" / "a.tokenade"
    source.parent.mkdir()
    source.write_text("{}")

    lock = root / ".a.tokenade.tokenade-sync-lock"
    transport = LocalTransport(str(root))
    transport.upload_atomic(source, "a.tokenade", None)

    assert not lock.exists()
