import base64
import hashlib
import json
import secrets
from pathlib import Path
from unittest.mock import patch

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
    assert store.retrieve("one").data == b"original"


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
            VaultConfig(vault_path=str(root))
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
            VaultConfig(vault_path=str(root))
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
