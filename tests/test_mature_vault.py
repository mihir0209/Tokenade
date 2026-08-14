import base64
import hashlib
import json
import multiprocessing
import secrets
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from tokenade.core.vault import SessionVault, VaultConfig


KEY = base64.b64encode(b"k" * 32).decode()


def vault(tmp_path):
    return SessionVault(
        VaultConfig(
            vault_path=str(tmp_path / "vault"),
            backup_path=str(tmp_path / "backups"),
            master_key=KEY,
        )
    )


def test_vault_encrypts_and_round_trips(tmp_path):
    store = vault(tmp_path)
    secret = b'{"cookies":[{"value":"DO_NOT_STORE_PLAINTEXT"}]}'
    assert store.store("primary", secret).success
    assert store.retrieve("primary").data == secret
    files = b"".join(
        path.read_bytes() for path in (tmp_path / "vault").rglob("*") if path.is_file()
    )
    assert b"DO_NOT_STORE_PLAINTEXT" not in files
    assert not (tmp_path / "vault/master.key").exists()


def test_rotation_preserves_multiple_entries(tmp_path):
    # Rotation is supported for keyring-backed vaults; emulate key persistence.
    keys = {}
    with (
        __import__("unittest.mock").mock.patch(
            "keyring.set_password",
            lambda service, name, value: keys.__setitem__(name, value),
        ),
        __import__("unittest.mock").mock.patch(
            "keyring.get_password", lambda service, name: keys.get(name)
        ),
        __import__("unittest.mock").mock.patch(
            "keyring.delete_password", lambda service, name: keys.pop(name, None)
        ),
    ):
        store = SessionVault(
            VaultConfig(
                vault_path=str(tmp_path / "vault"),
                backup_path=str(tmp_path / "backups"),
            )
        )
        assert store.store("one", b"one").success
        assert store.store("two", b"two-two").success
        result = store.rotate_key()
        assert result.success, result.message
        assert len(keys) == 1
        reopened = SessionVault(
            VaultConfig(
                vault_path=str(tmp_path / "vault"),
                backup_path=str(tmp_path / "backups"),
            )
        )
        assert reopened.retrieve("one").data == b"one"
        assert reopened.retrieve("two").data == b"two-two"
        assert reopened.verify().success


def test_explicit_key_rotation_fails_without_changing_data(tmp_path):
    store = vault(tmp_path)
    store.store("one", b"one")
    assert not store.rotate_key().success
    assert SessionVault(store.config).retrieve("one").data == b"one"


def test_restore_does_not_leave_raw_key_in_vault(tmp_path):
    store = vault(tmp_path)
    store.store("one", b"portable")
    backup = store.backup("portable", passphrase="password")
    restored = vault(tmp_path / "other")
    assert restored.restore(
        backup.metadata["backup_path"], passphrase="password"
    ).success
    assert not (tmp_path / "other/vault/vault.key").exists()


def test_concurrent_instances_reload_manifest_under_lock(tmp_path):
    first = vault(tmp_path)
    second = vault(tmp_path)
    assert first.store("one", b"one").success
    assert second.store("two", b"two").success
    reopened = vault(tmp_path)
    assert {entry["name"] for entry in reopened.list_entries().data} == {"one", "two"}
    assert {entry["name"] for entry in first.list_entries().data} == {"one", "two"}


def test_restore_keyring_failure_rolls_back_old_vault(tmp_path):
    source = vault(tmp_path / "source")
    source.store("backup-entry", b"backup")
    backup = source.backup("portable", passphrase="password")

    keys = {}
    from unittest.mock import patch

    with (
        patch(
            "keyring.set_password",
            lambda service, name, value: keys.__setitem__(name, value),
        ),
        patch("keyring.get_password", lambda service, name: keys.get(name)),
    ):
        destination = SessionVault(
            VaultConfig(
                vault_path=str(tmp_path / "target"),
                backup_path=str(tmp_path / "backups"),
            )
        )
        destination.store("original", b"original")
        with patch("keyring.set_password", side_effect=RuntimeError("keyring failed")):
            result = destination.restore(
                backup.metadata["backup_path"], passphrase="password"
            )
        assert not result.success
        reopened = SessionVault(
            VaultConfig(
                vault_path=str(tmp_path / "target"),
                backup_path=str(tmp_path / "backups"),
            )
        )
        assert reopened.retrieve("original").data == b"original"


def test_keyring_backed_restore_preserves_restored_manifest_entries(tmp_path):
    keys = {}
    from unittest.mock import patch

    with (
        patch(
            "keyring.set_password",
            lambda service, name, value: keys.__setitem__(name, value),
        ),
        patch("keyring.get_password", lambda service, name: keys.get(name)),
        patch("keyring.delete_password", lambda service, name: keys.pop(name, None)),
    ):
        source = SessionVault(
            VaultConfig(
                vault_path=str(tmp_path / "source"),
                backup_path=str(tmp_path / "backups"),
            )
        )
        assert source.store("one", b"one").success
        assert source.store("two", b"two").success
        backup = source.backup("portable", passphrase="recovery password")

        target_config = VaultConfig(
            vault_path=str(tmp_path / "target"),
            backup_path=str(tmp_path / "backups"),
        )
        target = SessionVault(target_config)
        restored = target.restore(
            backup.metadata["backup_path"], passphrase="recovery password"
        )

        assert restored.success, restored.message
        reopened = SessionVault(target_config)
        assert {entry["name"] for entry in reopened.list_entries().data} == {
            "one",
            "two",
        }
        assert reopened.retrieve("one").data == b"one"


def test_restore_into_same_vault_preserves_active_key_and_entries(tmp_path):
    keys = {}
    from unittest.mock import patch

    with (
        patch(
            "keyring.set_password",
            lambda service, name, value: keys.__setitem__(name, value),
        ),
        patch("keyring.get_password", lambda service, name: keys.get(name)),
        patch("keyring.delete_password", lambda service, name: keys.pop(name, None)),
    ):
        config = VaultConfig(
            vault_path=str(tmp_path / "vault"),
            backup_path=str(tmp_path / "backups"),
        )
        source = SessionVault(config)
        assert source.store("one", b"one").success
        backup = source.backup("portable", passphrase="recovery password")
        assert backup.success, backup.message
        assert source.store("two", b"two").success

        result = source.restore(
            backup.metadata["backup_path"], passphrase="recovery password"
        )
        assert result.success, result.message
        assert source.retrieve("one").data == b"one"

        reopened = SessionVault(config)
        assert {entry["name"] for entry in reopened.list_entries().data} == {"one"}
        manifest = json.loads((tmp_path / "vault/manifest.json").read_text())
        active = f"{manifest['vault_id']}:{manifest['active_key_id']}"
        assert active in keys
        assert (manifest["vault_id"], manifest["active_key_id"]) not in [
            (pending["vault_id"], pending["key_id"])
            for pending in manifest["pending_key_deletions"]
        ]
        assert not (tmp_path / "vault.pre-restore").exists()


def test_restore_into_same_vault_preserves_existing_backups(tmp_path):
    keys = {}
    from unittest.mock import patch

    with (
        patch(
            "keyring.set_password",
            lambda service, name, value: keys.__setitem__(name, value),
        ),
        patch("keyring.get_password", lambda service, name: keys.get(name)),
        patch("keyring.delete_password", lambda service, name: keys.pop(name, None)),
    ):
        config = VaultConfig(vault_path=str(tmp_path / "vault"))
        source = SessionVault(config)
        assert source.store("one", b"one").success
        first = source.backup("first", passphrase="recovery password")
        second = source.backup("second", passphrase="recovery password")
        assert first.success and second.success
        assert source.store("two", b"two").success

        result = source.restore("first", passphrase="recovery password")
        assert result.success, result.message

        backups = sorted(
            path.name for path in (tmp_path / "vault/backups").glob("*.tvbak")
        )
        assert backups == ["first.tvbak", "second.tvbak"]
        reopened = SessionVault(config)
        assert {entry["name"] for entry in reopened.list_entries().data} == {"one"}


def test_restore_into_different_vault_removes_old_key_from_keyring(tmp_path):
    keys = {}
    from unittest.mock import patch

    with (
        patch(
            "keyring.set_password",
            lambda service, name, value: keys.__setitem__(name, value),
        ),
        patch("keyring.get_password", lambda service, name: keys.get(name)),
        patch("keyring.delete_password", lambda service, name: keys.pop(name, None)),
    ):
        source = SessionVault(
            VaultConfig(
                vault_path=str(tmp_path / "source"),
                backup_path=str(tmp_path / "backups"),
            )
        )
        assert source.store("one", b"one").success
        backup = source.backup("portable", passphrase="recovery password")
        assert backup.success, backup.message

        target = SessionVault(
            VaultConfig(
                vault_path=str(tmp_path / "target"),
                backup_path=str(tmp_path / "backups"),
            )
        )
        old_identity = (
            f"{target._manifest['vault_id']}:{target._manifest['active_key_id']}"
        )
        assert old_identity in keys

        result = target.restore(
            backup.metadata["backup_path"], passphrase="recovery password"
        )
        assert result.success, result.message
        assert old_identity not in keys

        reopened = SessionVault(
            VaultConfig(
                vault_path=str(tmp_path / "target"),
                backup_path=str(tmp_path / "backups"),
            )
        )
        assert reopened.retrieve("one").data == b"one"


def test_backup_is_portable_with_passphrase(tmp_path):
    store = vault(tmp_path)
    assert store.store("one", b"portable").success
    backup = store.backup("portable", passphrase="recovery password")
    assert backup.success, backup.message

    restored = SessionVault(
        VaultConfig(
            vault_path=str(tmp_path / "restored"),
            backup_path=str(tmp_path / "backups"),
            master_key=KEY,
        )
    )
    result = restored.restore(
        backup.metadata["backup_path"], passphrase="recovery password"
    )
    assert result.success, result.message
    assert restored.retrieve("one").data == b"portable"


def test_wrong_backup_passphrase_does_not_change_vault(tmp_path):
    store = vault(tmp_path)
    store.store("one", b"original")
    backup = store.backup("portable", passphrase="correct")
    result = store.restore(backup.metadata["backup_path"], passphrase="wrong")
    assert not result.success
    assert "incorrect passphrase or corrupted backup" in result.message
    assert store.retrieve("one").data == b"original"


def test_first_use_keyring_failure_removes_fresh_vault(tmp_path):
    from unittest.mock import patch

    with patch("keyring.set_password", side_effect=RuntimeError("no keyring backend")):
        with pytest.raises(RuntimeError) as excinfo:
            SessionVault(
                VaultConfig(
                    vault_path=str(tmp_path / "vault"),
                    backup_path=str(tmp_path / "backups"),
                )
            )
    assert "TOKENADE_VAULT_KEY" in str(excinfo.value)
    assert not (tmp_path / "vault").exists()


def test_duplicate_names_require_replace(tmp_path):
    store = vault(tmp_path)
    assert store.store("one", b"old").success
    assert not store.store("one", b"new").success
    assert store.store("one", b"new", replace=True).success
    assert store.retrieve("one").data == b"new"


def test_retrieve_refuses_overwrite(tmp_path):
    store = vault(tmp_path)
    store.store("one", b"secret")
    output = tmp_path / "out.tokenade"
    output.write_bytes(b"existing")
    assert not store.retrieve("one", str(output)).success
    assert output.read_bytes() == b"existing"


def test_legacy_vault_fails_closed(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "master.key").write_bytes(b"old")
    try:
        SessionVault(VaultConfig(vault_path=str(root), master_key=KEY))
    except RuntimeError as exc:
        assert "Legacy vault" in str(exc)
    else:
        raise AssertionError("legacy vault was opened")


def test_legacy_vault_migration_preserves_entries_and_source_archive(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    key = secrets.token_bytes(32)
    data = b'{"site_name":"example.com","cookies":[]}'
    entry_id = "legacy-entry"
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(key).encrypt(nonce, data, None)
    (root / "master.key").write_bytes(key)
    (root / "entries.json").write_text(
        json.dumps(
            {
                entry_id: {
                    "name": "example",
                    "created_at": 1,
                    "updated_at": 1,
                    "metadata": {"site": "example.com"},
                }
            }
        )
    )
    (root / f"{entry_id}.enc").write_text(
        json.dumps(
            {
                "encrypted_data": base64.b64encode(encrypted[16:]).decode(),
                "iv": base64.b64encode(nonce).decode(),
                "tag": base64.b64encode(encrypted[:16]).decode(),
                "checksum": hashlib.sha256(data).hexdigest(),
            }
        )
    )

    keys = {}
    config = VaultConfig(vault_path=str(root), master_key=KEY)
    with (
        patch(
            "keyring.set_password",
            lambda service, name, value: keys.__setitem__(name, value),
        ),
        patch("keyring.get_password", lambda service, name: keys.get(name)),
    ):
        result = SessionVault.migrate_legacy(config, passphrase="recovery password")
        migrated_data = SessionVault(
            VaultConfig(vault_path=str(root), master_key=KEY)
        ).retrieve("example").data

    assert result.success, result.message
    assert result.metadata["entries_migrated"] == 1
    archive = Path(result.metadata["legacy_archive"])
    assert archive.is_file()
    assert archive.read_bytes().startswith(b"TVLG1")
    assert key not in archive.read_bytes()
    recovered = tmp_path / "recovered-legacy"
    recovery = SessionVault.recover_legacy_archive(
        str(archive), str(recovered), passphrase="recovery password"
    )
    assert recovery.success, recovery.message
    assert (recovered / "master.key").read_bytes() == key
    assert (recovered / f"{entry_id}.enc").is_file()
    assert migrated_data == data
    assert not (root / "master.key").exists()


def test_legacy_vault_migration_archives_and_reports_corrupt_entries(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    key = secrets.token_bytes(32)
    data = b"recoverable"
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(key).encrypt(nonce, data, None)
    (root / "master.key").write_bytes(key)
    (root / "entries.json").write_text(
        json.dumps(
            {
                "good": {"name": "good", "metadata": {}},
                "bad": {"name": "bad", "metadata": {}},
            }
        )
    )
    (root / "good.enc").write_text(
        json.dumps(
            {
                "encrypted_data": base64.b64encode(encrypted[16:]).decode(),
                "iv": base64.b64encode(nonce).decode(),
                "tag": base64.b64encode(encrypted[:16]).decode(),
                "checksum": hashlib.sha256(data).hexdigest(),
            }
        )
    )
    (root / "bad.enc").write_text("{}")

    keys = {}
    config = VaultConfig(vault_path=str(root), master_key=KEY)
    with (
        patch(
            "keyring.set_password",
            lambda service, name, value: keys.__setitem__(name, value),
        ),
        patch("keyring.get_password", lambda service, name: keys.get(name)),
    ):
        result = SessionVault.migrate_legacy(config, passphrase="recovery password")
        migrated_data = SessionVault(
            VaultConfig(vault_path=str(root), master_key=KEY)
        ).retrieve("good").data

    assert result.success, result.message
    assert result.metadata["entries_migrated"] == 1
    assert result.metadata["entries_skipped"] == 1
    assert result.metadata["skipped_entries"][0]["entry_id"] == "bad"
    assert Path(result.metadata["legacy_archive"]).read_bytes().startswith(b"TVLG1")
    assert migrated_data == data


def test_legacy_vault_recovery_rejects_wrong_passphrase(tmp_path):
    archive = tmp_path / "legacy.tvbak"
    archive.write_bytes(b"TVLG1" + b"0" * 64)

    result = SessionVault.recover_legacy_archive(
        str(archive), str(tmp_path / "recovered"), passphrase="wrong"
    )

    assert not result.success
    assert not (tmp_path / "recovered").exists()


def _child_probe_vault(vault_dir, master_key, result_q):
    """Single attempt from a fresh process: fork inherits the parent's
    in-memory lock set, so clear it to simulate an external process."""
    from tokenade.core.vault import SessionVault, VaultConfig
    from tokenade.core.vault.vault import _HELD_LOCKS

    _HELD_LOCKS.clear()
    try:
        vault = SessionVault(VaultConfig(vault_path=vault_dir, master_key=master_key))
        result = vault.list_entries()
        result_q.put(("ok", result.success))
    except Exception as exc:
        result_q.put(("err", str(exc)))


def _child_poll_vault(vault_dir, master_key, result_q):
    from tokenade.core.vault import SessionVault, VaultConfig
    from tokenade.core.vault.vault import _HELD_LOCKS

    _HELD_LOCKS.clear()
    outcomes = []
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            vault = SessionVault(
                VaultConfig(vault_path=vault_dir, master_key=master_key)
            )
            result = vault.list_entries()
            outcomes.append(("ok", result.success))
            break
        except RuntimeError as exc:
            outcomes.append(("locked", str(exc)))
        except Exception as exc:
            outcomes.append(("err", str(exc)))
        time.sleep(0.02)
    else:
        outcomes.append(("timeout", "never succeeded"))
    result_q.put(outcomes)


def test_other_process_is_refused_while_vault_dir_locked(tmp_path):
    root = tmp_path / "vault"
    config = VaultConfig(vault_path=str(root), master_key=KEY)
    vault = SessionVault(config)
    assert vault.store("one", b"payload", metadata={}).success

    ctx = multiprocessing.get_context("fork")
    with SessionVault._vault_dir_lock(root):
        queue = ctx.Queue()
        child = ctx.Process(
            target=_child_probe_vault, args=(str(root), KEY, queue)
        )
        child.start()
        child.join(timeout=60)
        assert child.exitcode == 0
        kind, payload = queue.get(timeout=10)
        assert kind == "err"
        assert "locked by another process" in payload

    queue2 = ctx.Queue()
    child2 = ctx.Process(
        target=_child_probe_vault, args=(str(root), KEY, queue2)
    )
    child2.start()
    child2.join(timeout=60)
    assert child2.exitcode == 0
    kind, payload = queue2.get(timeout=10)
    assert kind == "ok"
    assert payload is True


def test_operations_blocked_until_migration_completes(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    key = secrets.token_bytes(32)
    data = b'{"site_name":"example.com","cookies":[]}'
    entry_id = "legacy-entry"
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(key).encrypt(nonce, data, None)
    (root / "master.key").write_bytes(key)
    (root / "entries.json").write_text(
        json.dumps(
            {
                entry_id: {
                    "name": "example",
                    "created_at": 1,
                    "updated_at": 1,
                    "metadata": {"site": "example.com"},
                }
            }
        )
    )
    (root / f"{entry_id}.enc").write_text(
        json.dumps(
            {
                "encrypted_data": base64.b64encode(encrypted[16:]).decode(),
                "iv": base64.b64encode(nonce).decode(),
                "tag": base64.b64encode(encrypted[:16]).decode(),
                "checksum": hashlib.sha256(data).hexdigest(),
            }
        )
    )

    real_write = SessionVault._atomic_write_bytes

    def slow_seal_write(self, path, blob):
        if str(path).endswith(".tvbak"):
            time.sleep(0.2)
        return real_write(self, path, blob)

    ctx = multiprocessing.get_context("fork")
    queue = ctx.Queue()
    poller = ctx.Process(
        target=_child_poll_vault, args=(str(root), KEY, queue)
    )
    poller.start()

    keys = {}
    with (
        patch(
            "keyring.set_password",
            lambda service, name, value: keys.__setitem__(name, value),
        ),
        patch("keyring.get_password", lambda service, name: keys.get(name)),
        patch(
            "tokenade.core.vault.vault.SessionVault._atomic_write_bytes",
            slow_seal_write,
        ),
    ):
        result = SessionVault.migrate_legacy(
            VaultConfig(vault_path=str(root), master_key=KEY),
            passphrase="recovery password",
        )
        poller.join(timeout=30)
        outcomes = queue.get(timeout=10)

    assert result.success, result.message
    assert poller.exitcode == 0
    locked_seen = any(
        kind == "locked" and "locked by another process" in payload
        for kind, payload in outcomes
    )
    assert locked_seen, f"other process never hit the lock: {outcomes!r}"
    assert outcomes[-1] == ("ok", True), outcomes


def test_documented_vault_cli_commands_run(tmp_path, monkeypatch, capsys):
    """CR-13: every vault CLI command documented in USER_GUIDE parses and runs."""
    from argparse import Namespace

    from tokenade.cli.management import cmd_vault

    monkeypatch.setenv("TOKENADE_VAULT_KEY", KEY)
    monkeypatch.setenv("TOKENADE_VAULT_BACKUP_PASSPHRASE", "test-passphrase")
    vault_path = str(tmp_path / "vault")

    session_file = tmp_path / "session.tokenade"
    session_file.write_text('{"version":"3.0","site_name":"test","cookies":[]}')

    cmd_vault(Namespace(
        vault_action="store", vault_path=vault_path, name="test",
        file=str(session_file), json=True, replace=False,
    ))
    captured = capsys.readouterr()
    assert json.loads(captured.out)["success"] is True

    cmd_vault(Namespace(
        vault_action="list", vault_path=vault_path, json=True,
    ))
    captured = capsys.readouterr()
    assert "test" in captured.out

    output_file = str(tmp_path / "retrieved.tokenade")
    cmd_vault(Namespace(
        vault_action="retrieve", vault_path=vault_path, name="test",
        output=output_file, json=True, overwrite=False,
    ))
    captured = capsys.readouterr()
    assert json.loads(captured.out)["success"] is True
    assert Path(output_file).read_text() == session_file.read_text()

    cmd_vault(Namespace(
        vault_action="verify", vault_path=vault_path, json=True,
    ))
    captured = capsys.readouterr()
    assert json.loads(captured.out)["success"] is True

    cmd_vault(Namespace(
        vault_action="backup", vault_path=vault_path, name="snap",
        json=True,
    ))
    captured = capsys.readouterr()
    assert json.loads(captured.out)["success"] is True

    cmd_vault(Namespace(
        vault_action="restore", vault_path=vault_path, name="snap",
        json=True,
    ))
    captured = capsys.readouterr()
    assert json.loads(captured.out)["success"] is True

    cmd_vault(Namespace(
        vault_action="delete", vault_path=vault_path, name="test",
        json=True,
    ))
    captured = capsys.readouterr()
    assert json.loads(captured.out)["success"] is True


def test_documented_vault_rotate_runs_on_explicit_key(tmp_path, monkeypatch, capsys):
    """CR-13: vault rotate parses and runs; explicit-key vaults report cleanly."""
    from argparse import Namespace

    from tokenade.cli.management import cmd_vault

    monkeypatch.setenv("TOKENADE_VAULT_KEY", KEY)
    vault_path = str(tmp_path / "vault")

    session_file = tmp_path / "s.tokenade"
    session_file.write_text('{"version":"3.0","cookies":[]}')
    cmd_vault(Namespace(
        vault_action="store", vault_path=vault_path, name="x",
        file=str(session_file), json=True, replace=False,
    ))
    capsys.readouterr()

    try:
        cmd_vault(Namespace(
            vault_action="rotate", vault_path=vault_path, json=True,
        ))
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("rotate on explicit-key vault should not succeed")
    captured = capsys.readouterr()
    body = json.loads(captured.out)
    assert body["success"] is False
    assert "rotate" in body["message"].lower()
