"""Transactional encrypted local Session Vault."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import secrets
import shutil
import tempfile
import time
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


SCHEMA_VERSION = 1
KEYRING_SERVICE = "tokenade-vault"


@dataclass
class VaultConfig:
    vault_path: str = "~/.tokenade/vault"
    backup_path: Optional[str] = None
    master_key: Optional[str] = None
    max_backups: int = 10

    def __post_init__(self):
        if self.backup_path is None:
            self.backup_path = str(Path(self.vault_path).expanduser() / "backups")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VaultConfig":
        return cls(
            **{
                k: data[k]
                for k in ("vault_path", "backup_path", "master_key", "max_backups")
                if k in data
            }
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vault_path": self.vault_path,
            "backup_path": self.backup_path,
            "max_backups": self.max_backups,
        }


@dataclass
class VaultResult:
    success: bool = True
    message: str = ""
    data: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = (
            self.data
            if isinstance(self.data, (dict, list, str, int, float, bool, type(None)))
            else None
        )
        return {
            "success": self.success,
            "message": self.message,
            "data": data,
            "metadata": self.metadata,
        }


@dataclass
class VaultEntry:
    entry_id: str
    name: str
    created_at: float
    updated_at: float
    key_id: str
    size: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "key_id": self.key_id,
            "size": self.size,
            "metadata": self.metadata,
        }


class SessionVault:
    @classmethod
    def migrate_legacy(
        cls, config: Optional[VaultConfig] = None, passphrase: Optional[str] = None
    ) -> VaultResult:
        config = config or VaultConfig()
        if not passphrase:
            return VaultResult(False, "Legacy migration requires a recovery passphrase")
        vault_dir = Path(config.vault_path).expanduser().resolve()
        migration_config = VaultConfig(
            vault_path=str(vault_dir),
            backup_path=config.backup_path,
            max_backups=config.max_backups,
        )
        key_path = vault_dir / "master.key"
        index_path = vault_dir / "entries.json"
        if not key_path.is_file() or not index_path.is_file():
            return VaultResult(False, "Legacy vault requires master.key and entries.json")

        try:
            key = key_path.read_bytes()
            if len(key) != 32:
                raise ValueError("legacy master.key must contain exactly 32 bytes")
            index = json.loads(index_path.read_text())
            if not isinstance(index, dict):
                raise ValueError("legacy entries.json must contain an object")

            plaintext_entries = []
            failed_entries = []
            for entry_id, metadata in index.items():
                try:
                    if not isinstance(metadata, dict):
                        raise ValueError("invalid metadata")
                    envelope_path = vault_dir / f"{entry_id}.enc"
                    envelope = json.loads(envelope_path.read_text())
                    nonce = base64.b64decode(envelope["iv"], validate=True)
                    tag = base64.b64decode(envelope["tag"], validate=True)
                    ciphertext = base64.b64decode(
                        envelope["encrypted_data"], validate=True
                    )
                    data = AESGCM(key).decrypt(nonce, tag + ciphertext, None)
                    if hashlib.sha256(data).hexdigest() != envelope.get("checksum"):
                        raise ValueError("checksum mismatch")
                    name = metadata.get("name") or entry_id
                    cls._validate_name(name)
                    plaintext_entries.append(
                        (name, data, metadata.get("metadata", {}))
                    )
                except Exception as exc:
                    failed_entries.append(
                        {"entry_id": entry_id, "error": type(exc).__name__}
                    )

            if index and not plaintext_entries:
                raise ValueError("no legacy entries could be decrypted")

            archive = vault_dir.with_name(
                f"{vault_dir.name}.legacy-{time.strftime('%Y%m%d-%H%M%S')}"
            )
            suffix = 2
            while archive.exists() or archive.with_name(f"{archive.name}.tvbak").exists():
                archive = vault_dir.with_name(
                    f"{vault_dir.name}.legacy-{time.strftime('%Y%m%d-%H%M%S')}-{suffix}"
                )
                suffix += 1
            os.replace(vault_dir, archive)
            try:
                migrated = cls(migration_config)
                for name, data, metadata in plaintext_entries:
                    result = migrated.store(name, data, metadata=metadata)
                    if not result.success:
                        raise RuntimeError(result.message)
                verification = migrated.verify()
                if not verification.success:
                    raise RuntimeError(verification.message)
                archive_bytes = io.BytesIO()
                with zipfile.ZipFile(
                    archive_bytes, "w", zipfile.ZIP_DEFLATED
                ) as archive_zip:
                    for path in archive.rglob("*"):
                        if path.is_file():
                            archive_zip.write(path, path.relative_to(archive))
                salt = secrets.token_bytes(16)
                recovery_key = hashlib.scrypt(
                    passphrase.encode(),
                    salt=salt,
                    n=2**15,
                    r=8,
                    p=1,
                    dklen=32,
                    maxmem=64 * 1024 * 1024,
                )
                nonce = secrets.token_bytes(12)
                sealed_archive = archive.with_name(f"{archive.name}.tvbak")
                migrated._atomic_write_bytes(
                    sealed_archive,
                    b"TVLG1"
                    + salt
                    + nonce
                    + AESGCM(recovery_key).encrypt(
                        nonce,
                        archive_bytes.getvalue(),
                        b"tokenade-legacy-vault-backup-v1",
                    ),
                )
                shutil.rmtree(archive)
            except Exception:
                shutil.rmtree(vault_dir, ignore_errors=True)
                if archive.exists():
                    os.replace(archive, vault_dir)
                raise
            message = f"Migrated {len(plaintext_entries)} legacy entries"
            if failed_entries:
                message += (
                    f"; {len(failed_entries)} unrecoverable entries remain in the legacy archive"
                )
            return VaultResult(
                True,
                message,
                metadata={
                    "entries_migrated": len(plaintext_entries),
                    "entries_skipped": len(failed_entries),
                    "skipped_entries": failed_entries,
                    "legacy_archive": str(sealed_archive),
                },
            )
        except Exception as exc:
            detail = str(exc) or type(exc).__name__
            return VaultResult(False, f"Legacy migration failed: {detail}")

    @classmethod
    def recover_legacy_archive(
        cls, archive_path: str, destination: str, passphrase: Optional[str] = None
    ) -> VaultResult:
        """Decrypt a migration archive into a separate legacy Vault directory."""
        if not passphrase:
            return VaultResult(False, "Legacy recovery requires the recovery passphrase")
        source = Path(archive_path).expanduser().resolve()
        target = Path(destination).expanduser().resolve()
        if not source.is_file():
            return VaultResult(False, f"Legacy archive not found: {source}")
        if target.exists():
            return VaultResult(False, f"Recovery destination already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".legacy-recovery-", dir=str(target.parent)))
        try:
            raw = source.read_bytes()
            if raw[:5] != b"TVLG1":
                raise ValueError("invalid legacy archive format")
            salt, nonce, ciphertext = raw[5:21], raw[21:33], raw[33:]
            key = hashlib.scrypt(
                passphrase.encode(),
                salt=salt,
                n=2**15,
                r=8,
                p=1,
                dklen=32,
                maxmem=64 * 1024 * 1024,
            )
            archive = AESGCM(key).decrypt(
                nonce, ciphertext, b"tokenade-legacy-vault-backup-v1"
            )
            with zipfile.ZipFile(io.BytesIO(archive)) as archive_zip:
                for item in archive_zip.infolist():
                    path = Path(item.filename)
                    if path.is_absolute() or ".." in path.parts:
                        raise ValueError("unsafe legacy archive path")
                archive_zip.extractall(stage)
            if not (stage / "master.key").is_file() or not (stage / "entries.json").is_file():
                raise ValueError("legacy archive is incomplete")
            os.replace(stage, target)
            return VaultResult(
                True,
                f"Recovered legacy Vault to: {target}",
                metadata={"recovery_path": str(target)},
            )
        except Exception as exc:
            shutil.rmtree(stage, ignore_errors=True)
            return VaultResult(False, f"Legacy recovery failed: {exc}")

    def __init__(self, config: Optional[VaultConfig] = None):
        self.config = config or VaultConfig()
        self._vault_dir = Path(self.config.vault_path).expanduser().resolve()
        self._backup_dir = Path(self.config.backup_path).expanduser().resolve()
        self._entries_dir = self._vault_dir / "entries"
        self._manifest_path = self._vault_dir / "manifest.json"
        self._recover_transaction()
        self._vault_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._entries_dir.mkdir(mode=0o700, exist_ok=True)
        self._backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._chmod_private(self._vault_dir, directory=True)
        if (self._vault_dir / "master.key").exists() or (
            self._vault_dir / "entries.json"
        ).exists():
            raise RuntimeError(
                "Legacy vault detected; migrate it before opening with the mature Vault"
            )
        self._manifest = self._load_or_create_manifest()
        self._entries = {
            entry_id: VaultEntry(entry_id=entry_id, **data)
            for entry_id, data in self._manifest["entries"].items()
        }
        self._key = self._load_key(self._manifest["active_key_id"])
        self._retry_key_deletions()

    def store(
        self,
        name: str,
        data: bytes,
        metadata: Optional[Dict[str, Any]] = None,
        replace: bool = False,
    ) -> VaultResult:
        try:
            self._validate_name(name)
            existing = self._find_entry(name)
            if existing and not replace:
                return VaultResult(False, f"Entry already exists: {name}")
            entry_id = existing.entry_id if existing else uuid.uuid4().hex
            now = time.time()
            entry = VaultEntry(
                entry_id,
                name,
                existing.created_at if existing else now,
                now,
                self._manifest["active_key_id"],
                len(data),
                self._safe_metadata(metadata),
            )
            envelope = self._encrypt_entry(entry, data, self._key)
            with self._lock():
                self._reload_manifest()
                self._key = self._load_key(self._manifest["active_key_id"])
                existing = self._find_entry(name)
                if existing and not replace:
                    return VaultResult(False, f"Entry already exists: {name}")
                entry_id = existing.entry_id if existing else entry_id
                entry.entry_id = entry_id
                envelope = self._encrypt_entry(entry, data, self._key)
                destination = self._entries_dir / f"{entry_id}.tvlt"
                staged = destination.with_suffix(".staged")
                previous = destination.with_suffix(".previous")
                self._atomic_write_json(staged, envelope)
                self._entries[entry_id] = entry
                try:
                    if destination.exists():
                        os.replace(destination, previous)
                    os.replace(staged, destination)
                    self._commit_manifest()
                    previous.unlink(missing_ok=True)
                except Exception:
                    staged.unlink(missing_ok=True)
                    if previous.exists():
                        destination.unlink(missing_ok=True)
                        os.replace(previous, destination)
                    elif not existing:
                        destination.unlink(missing_ok=True)
                    self._reload_manifest()
                    raise
            return VaultResult(
                True, f"Stored '{name}' in vault", metadata=entry.to_dict()
            )
        except Exception as exc:
            return VaultResult(False, f"Failed to store: {exc}")

    def retrieve(
        self, name: str, output_path: Optional[str] = None, overwrite: bool = False
    ) -> VaultResult:
        try:
            with self._lock():
                self._reload_manifest()
                self._key = self._load_key(self._manifest["active_key_id"])
                entry = self._find_entry(name)
                if not entry:
                    return VaultResult(False, f"Entry not found: {name}")
                data = self._decrypt_entry(entry, self._key)
            if output_path:
                destination = Path(output_path).expanduser()
                if destination.exists() and not overwrite:
                    return VaultResult(False, f"Output already exists: {destination}")
                self._atomic_write_bytes(destination, data)
            return VaultResult(
                True,
                f"Retrieved '{name}' from vault",
                data=data,
                metadata=entry.to_dict(),
            )
        except Exception as exc:
            return VaultResult(False, f"Failed to retrieve: {exc}")

    def delete(self, name: str) -> VaultResult:
        try:
            with self._lock():
                self._reload_manifest()
                entry = self._find_entry(name)
                if not entry:
                    return VaultResult(False, f"Entry not found: {name}")
                source = self._entries_dir / f"{entry.entry_id}.tvlt"
                trash = source.with_suffix(".deleting")
                os.replace(source, trash)
                self._entries.pop(entry.entry_id)
                try:
                    self._commit_manifest()
                except Exception:
                    os.replace(trash, source)
                    self._entries[entry.entry_id] = entry
                    raise
                trash.unlink(missing_ok=True)
            return VaultResult(True, f"Deleted '{name}' from vault")
        except Exception as exc:
            return VaultResult(False, f"Failed to delete: {exc}")

    def list_entries(self) -> VaultResult:
        with self._lock():
            self._reload_manifest()
            entries = [
                entry.to_dict()
                for entry in sorted(
                    self._entries.values(), key=lambda item: item.name.lower()
                )
            ]
        return VaultResult(True, f"Found {len(entries)} entries", data=entries)

    def verify(self) -> VaultResult:
        errors = []
        with self._lock():
            self._reload_manifest()
            self._key = self._load_key(self._manifest["active_key_id"])
            for entry in self._entries.values():
                try:
                    self._decrypt_entry(entry, self._key)
                except Exception as exc:
                    errors.append(f"{entry.entry_id}: {type(exc).__name__}")
        return VaultResult(
            not errors,
            "Vault verified" if not errors else "Vault verification failed",
            data=errors,
            metadata={"entries_checked": len(self._entries), "errors": len(errors)},
        )

    def rotate_key(self) -> VaultResult:
        if self.config.master_key:
            return VaultResult(
                False,
                "Explicit-key vaults cannot rotate internally; provide a new vault and migrate entries",
            )
        try:
            with self._lock():
                self._reload_manifest()
                self._key = self._load_key(self._manifest["active_key_id"])
                old_key_id = self._manifest["active_key_id"]
                new_key = secrets.token_bytes(32)
                new_key_id = uuid.uuid4().hex
                stage = Path(
                    tempfile.mkdtemp(prefix=".rotate-", dir=str(self._vault_dir))
                )
                for entry in self._entries.values():
                    plaintext = self._decrypt_entry(entry, self._key)
                    rotated = VaultEntry(
                        **{
                            **entry.__dict__,
                            "key_id": new_key_id,
                            "updated_at": time.time(),
                        }
                    )
                    self._atomic_write_json(
                        stage / f"{entry.entry_id}.tvlt",
                        self._encrypt_entry(rotated, plaintext, new_key),
                    )
                old_dir = self._entries_dir.with_name("entries.old")
                if old_dir.exists():
                    shutil.rmtree(old_dir)
                journal = self._vault_dir / "transaction.json"
                self._atomic_write_json(
                    journal,
                    {
                        "type": "rotate",
                        "old_key_id": self._manifest["active_key_id"],
                        "new_key_id": new_key_id,
                    },
                )
                self._store_key(new_key_id, new_key)
                os.replace(self._entries_dir, old_dir)
                os.replace(stage, self._entries_dir)
                for entry in self._entries.values():
                    entry.key_id = new_key_id
                    entry.updated_at = time.time()
                self._manifest["active_key_id"] = new_key_id
                try:
                    self._commit_manifest()
                except Exception:
                    os.replace(self._entries_dir, stage)
                    os.replace(old_dir, self._entries_dir)
                    self._delete_key(new_key_id)
                    raise
                shutil.rmtree(old_dir)
                journal.unlink(missing_ok=True)
                self._key = new_key
                self._schedule_key_deletion(self._manifest["vault_id"], old_key_id)
            return VaultResult(
                True,
                f"Rotated key and re-encrypted {len(self._entries)} entries",
                metadata={"re_encrypted_count": len(self._entries)},
            )
        except Exception as exc:
            if "stage" in locals():
                shutil.rmtree(stage, ignore_errors=True)
            if "new_key_id" in locals():
                self._delete_key(new_key_id)
            return VaultResult(False, f"Key rotation failed: {exc}")

    def backup(
        self, name: Optional[str] = None, passphrase: Optional[str] = None
    ) -> VaultResult:
        if not passphrase:
            return VaultResult(False, "Backup requires a recovery passphrase")
        try:
            with self._lock():
                self._reload_manifest()
                self._key = self._load_key(self._manifest["active_key_id"])
                backup_name = name or f"backup-{int(time.time())}"
                self._validate_name(backup_name)
                archive = io.BytesIO()
                with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr("manifest.json", self._manifest_path.read_bytes())
                    for entry in self._entries.values():
                        zf.write(
                            self._entries_dir / f"{entry.entry_id}.tvlt",
                            f"entries/{entry.entry_id}.tvlt",
                        )
                    zf.writestr("vault.key", self._key)
            salt = secrets.token_bytes(16)
            key = hashlib.scrypt(
                passphrase.encode(),
                salt=salt,
                n=2**15,
                r=8,
                p=1,
                dklen=32,
                maxmem=64 * 1024 * 1024,
            )
            nonce = secrets.token_bytes(12)
            envelope = (
                b"TVBK1"
                + salt
                + nonce
                + AESGCM(key).encrypt(
                    nonce, archive.getvalue(), b"tokenade-vault-backup-v1"
                )
            )
            destination = self._backup_dir / f"{backup_name}.tvbak"
            self._atomic_write_bytes(destination, envelope)
            self._cleanup_old_backups()
            return VaultResult(
                True,
                f"Created backup: {backup_name}",
                metadata={"backup_path": str(destination)},
            )
        except Exception as exc:
            return VaultResult(False, f"Backup failed: {exc}")

    def restore(
        self, backup_name: str, passphrase: Optional[str] = None
    ) -> VaultResult:
        if not passphrase:
            return VaultResult(False, "Restore requires the recovery passphrase")
        source = Path(backup_name).expanduser()
        if not source.is_file():
            source = self._backup_dir / f"{backup_name.removesuffix('.tvbak')}.tvbak"
        if not source.is_file():
            return VaultResult(False, f"Backup not found: {backup_name}")
        stage = Path(
            tempfile.mkdtemp(prefix=".restore-", dir=str(self._vault_dir.parent))
        )
        try:
            raw = source.read_bytes()
            if raw[:5] != b"TVBK1":
                raise ValueError("invalid backup format")
            salt, nonce, ciphertext = raw[5:21], raw[21:33], raw[33:]
            key = hashlib.scrypt(
                passphrase.encode(),
                salt=salt,
                n=2**15,
                r=8,
                p=1,
                dklen=32,
                maxmem=64 * 1024 * 1024,
            )
            archive = AESGCM(key).decrypt(
                nonce, ciphertext, b"tokenade-vault-backup-v1"
            )
            with zipfile.ZipFile(io.BytesIO(archive)) as zf:
                for item in zf.infolist():
                    path = Path(item.filename)
                    if path.is_absolute() or ".." in path.parts:
                        raise ValueError("unsafe backup path")
                zf.extractall(stage)
            manifest = json.loads((stage / "manifest.json").read_text())
            restored_key = (stage / "vault.key").read_bytes()
            (stage / "vault.key").unlink()
            self._validate_manifest(manifest)
            explicit = self._explicit_key()
            if explicit is not None and not secrets.compare_digest(
                explicit, restored_key
            ):
                raise ValueError(
                    "backup key does not match the explicitly configured Vault key"
                )
            for entry_id, entry_data in manifest["entries"].items():
                self._decrypt_envelope(
                    stage / "entries" / f"{entry_id}.tvlt",
                    restored_key,
                    entry_id,
                    entry_data,
                    vault_id=manifest["vault_id"],
                )
            with self._lock():
                old_vault_id = self._manifest["vault_id"]
                old_key_id = self._manifest["active_key_id"]
                backup_live = self._vault_dir.with_name(
                    self._vault_dir.name + ".pre-restore"
                )
                if backup_live.exists():
                    shutil.rmtree(backup_live)
                restore_journal = (
                    self._vault_dir.parent / f".{self._vault_dir.name}.restore.json"
                )
                self._atomic_write_json(
                    restore_journal,
                    {
                        "target": str(self._vault_dir),
                        "backup": str(backup_live),
                        "phase": "prepared",
                        "new_vault_id": manifest["vault_id"],
                        "new_key_id": manifest["active_key_id"],
                        "old_vault_id": self._manifest["vault_id"],
                        "old_key_id": self._manifest["active_key_id"],
                    },
                )
                os.replace(self._vault_dir, backup_live)
                try:
                    os.replace(stage, self._vault_dir)
                    self._store_key(
                        manifest["active_key_id"],
                        restored_key,
                        vault_id=manifest["vault_id"],
                    )
                    self._atomic_write_json(
                        restore_journal,
                        {
                            "target": str(self._vault_dir),
                            "backup": str(backup_live),
                            "phase": "committed",
                            "new_vault_id": manifest["vault_id"],
                            "new_key_id": manifest["active_key_id"],
                            "old_vault_id": self._manifest["vault_id"],
                            "old_key_id": self._manifest["active_key_id"],
                        },
                    )
                except Exception:
                    if self._vault_dir.exists():
                        shutil.rmtree(self._vault_dir)
                    os.replace(backup_live, self._vault_dir)
                    try:
                        self._delete_key_for(
                            manifest["vault_id"], manifest["active_key_id"]
                        )
                    except Exception:
                        pass
                    raise
                self._manifest = manifest
                self._entries = {
                    eid: VaultEntry(entry_id=eid, **data)
                    for eid, data in manifest["entries"].items()
                }
                self._schedule_key_deletion(old_vault_id, old_key_id)
                shutil.rmtree(backup_live)
                restore_journal.unlink(missing_ok=True)
            self._entries_dir = self._vault_dir / "entries"
            self._manifest_path = self._vault_dir / "manifest.json"
            self._manifest = manifest
            self._key = restored_key
            return VaultResult(
                True,
                f"Restored from backup: {source.name}",
                metadata={"entries_restored": len(self._entries)},
            )
        except Exception as exc:
            shutil.rmtree(stage, ignore_errors=True)
            return VaultResult(False, f"Restore failed: {exc}")

    def _load_or_create_manifest(self) -> Dict[str, Any]:
        if self._manifest_path.exists():
            manifest = json.loads(self._manifest_path.read_text())
            self._validate_manifest(manifest)
            return manifest
        vault_id, key_id = str(uuid.uuid4()), uuid.uuid4().hex
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "vault_id": vault_id,
            "active_key_id": key_id,
            "created_at": time.time(),
            "entries": {},
            "pending_key_deletions": [],
        }
        key = self._explicit_key() or secrets.token_bytes(32)
        self._store_key(key_id, key, vault_id=vault_id)
        self._atomic_write_json(self._manifest_path, manifest)
        return manifest

    def _load_key(self, key_id: str) -> bytes:
        explicit = self._explicit_key()
        if explicit:
            return explicit
        import keyring

        value = keyring.get_password(
            KEYRING_SERVICE, f"{self._manifest['vault_id']}:{key_id}"
        )
        if not value:
            raise RuntimeError("Vault key is unavailable from the system keyring")
        return base64.b64decode(value)

    def _store_key(
        self, key_id: str, key: bytes, vault_id: Optional[str] = None
    ) -> None:
        if self.config.master_key:
            return
        import keyring

        keyring.set_password(
            KEYRING_SERVICE,
            f"{vault_id or self._manifest['vault_id']}:{key_id}",
            base64.b64encode(key).decode(),
        )

    def _delete_key(self, key_id: str) -> None:
        self._delete_key_for(self._manifest["vault_id"], key_id)

    def _delete_key_for(self, vault_id: str, key_id: str) -> None:
        if self.config.master_key:
            return
        import keyring

        keyring.delete_password(KEYRING_SERVICE, f"{vault_id}:{key_id}")

    def _schedule_key_deletion(self, vault_id: str, key_id: str) -> None:
        if self.config.master_key:
            return
        pending = self._manifest.setdefault("pending_key_deletions", [])
        item = {"vault_id": vault_id, "key_id": key_id}
        if item not in pending:
            pending.append(item)
            self._commit_manifest()
        self._retry_key_deletions()

    def _retry_key_deletions(self) -> None:
        if self.config.master_key:
            return
        pending = list(self._manifest.get("pending_key_deletions", []))
        remaining = []
        for item in pending:
            try:
                self._delete_key_for(item["vault_id"], item["key_id"])
            except Exception:
                remaining.append(item)
        if remaining != pending:
            self._manifest["pending_key_deletions"] = remaining
            self._commit_manifest()

    def _explicit_key(self) -> Optional[bytes]:
        if not self.config.master_key:
            return None
        try:
            raw = base64.b64decode(self.config.master_key, validate=True)
        except Exception:
            raw = hashlib.sha256(self.config.master_key.encode()).digest()
        if len(raw) != 32:
            raw = hashlib.sha256(raw).digest()
        return raw

    def _encrypt_entry(
        self, entry: VaultEntry, data: bytes, key: bytes
    ) -> Dict[str, Any]:
        nonce = secrets.token_bytes(12)
        aad = self._aad(entry)
        return {
            "format_version": 1,
            "entry_id": entry.entry_id,
            "key_id": entry.key_id,
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(
                AESGCM(key).encrypt(nonce, data, aad)
            ).decode(),
        }

    def _decrypt_entry(self, entry: VaultEntry, key: bytes) -> bytes:
        return self._decrypt_envelope(
            self._entries_dir / f"{entry.entry_id}.tvlt",
            key,
            entry.entry_id,
            entry.to_dict(),
        )

    def _decrypt_envelope(
        self,
        path: Path,
        key: bytes,
        entry_id: str,
        data: Dict[str, Any],
        vault_id: Optional[str] = None,
    ) -> bytes:
        env = json.loads(path.read_text())
        if env.get("entry_id") != entry_id or env.get("key_id") != data["key_id"]:
            raise ValueError("entry identity mismatch")
        entry = (
            VaultEntry(entry_id=entry_id, **data)
            if "entry_id" not in data
            else VaultEntry(**data)
        )
        return AESGCM(key).decrypt(
            base64.b64decode(env["nonce"]),
            base64.b64decode(env["ciphertext"]),
            self._aad(entry, vault_id=vault_id),
        )

    def _aad(self, entry: VaultEntry, vault_id: Optional[str] = None) -> bytes:
        return json.dumps(
            {
                "v": 1,
                "vault": vault_id or self._manifest["vault_id"],
                "entry": entry.entry_id,
                "key": entry.key_id,
                "name": entry.name,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def _commit_manifest(self):
        self._manifest["entries"] = {
            eid: {k: v for k, v in e.to_dict().items() if k != "entry_id"}
            for eid, e in self._entries.items()
        }
        self._atomic_write_json(self._manifest_path, self._manifest)

    def _reload_manifest(self):
        manifest = json.loads(self._manifest_path.read_text())
        self._validate_manifest(manifest)
        self._manifest = manifest
        self._entries = {
            entry_id: VaultEntry(entry_id=entry_id, **data)
            for entry_id, data in manifest["entries"].items()
        }

    def _find_entry(self, name: str) -> Optional[VaultEntry]:
        return next(
            (
                entry
                for entry in self._entries.values()
                if entry.name == name or entry.entry_id == name
            ),
            None,
        )

    @staticmethod
    def _safe_metadata(metadata):
        data = metadata or {}
        return {
            str(k): v
            for k, v in data.items()
            if isinstance(v, (str, int, float, bool, type(None)))
        }

    @staticmethod
    def _validate_name(name: str):
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name) > 128
            or any(c in name for c in ("/", "\\", "\x00", ".."))
        ):
            raise ValueError("invalid vault name")

    @staticmethod
    def _validate_manifest(manifest):
        if manifest.get("schema_version") != SCHEMA_VERSION or not isinstance(
            manifest.get("entries"), dict
        ):
            raise ValueError("unsupported or corrupt vault manifest")

    @contextmanager
    def _lock(self):
        lock = self._vault_dir.parent / f".{self._vault_dir.name}.lock"
        owner = f"{os.getpid()}:{uuid.uuid4().hex}"
        for attempt in range(2):
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(fd, owner.encode())
                break
            except FileExistsError as exc:
                if attempt or self._pid_lock_alive(lock):
                    raise RuntimeError("vault is locked by another process") from exc
                lock.unlink(missing_ok=True)
        os.close(fd)
        try:
            yield
        finally:
            try:
                if lock.read_text() == owner:
                    lock.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _pid_lock_alive(lock: Path) -> bool:
        try:
            os.kill(int(lock.read_text().split(":", 1)[0]), 0)
            return True
        except ProcessLookupError:
            return False
        except Exception:
            return True

    def _atomic_write_json(self, path: Path, data):
        self._atomic_write_bytes(
            path, json.dumps(data, indent=2, ensure_ascii=False).encode()
        )

    def _atomic_write_bytes(self, path: Path, data: bytes):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp, 0o600)
            os.replace(temp, path)
        except Exception:
            try:
                os.unlink(temp)
            except OSError:
                pass
            raise

    @staticmethod
    def _chmod_private(path: Path, directory=False):
        if os.name != "nt":
            os.chmod(path, 0o700 if directory else 0o600)

    def _cleanup_old_backups(self):
        backups = sorted(
            self._backup_dir.glob("*.tvbak"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for backup in backups[self.config.max_backups :]:
            backup.unlink()

    def _recover_transaction(self):
        restore_journal = (
            self._vault_dir.parent / f".{self._vault_dir.name}.restore.json"
        )
        if restore_journal.exists():
            data = json.loads(restore_journal.read_text())
            backup = Path(data["backup"])
            phase = data.get("phase", "prepared")
            if phase != "committed" and backup.exists():
                if self._vault_dir.exists():
                    shutil.rmtree(self._vault_dir)
                os.replace(backup, self._vault_dir)
                try:
                    self._delete_key_for(data["new_vault_id"], data["new_key_id"])
                except Exception:
                    return
            elif self._vault_dir.exists() and backup.exists():
                shutil.rmtree(backup)
            if phase == "committed":
                try:
                    self._delete_key_for(data["old_vault_id"], data["old_key_id"])
                except Exception:
                    return
            restore_journal.unlink(missing_ok=True)
        journal = self._vault_dir / "transaction.json"
        old = self._vault_dir / "entries.old"
        if journal.exists() and old.exists():
            data = json.loads(journal.read_text())
            manifest = json.loads((self._vault_dir / "manifest.json").read_text())
            if manifest.get("active_key_id") != data.get("new_key_id"):
                current = self._vault_dir / "entries"
                if current.exists():
                    shutil.rmtree(current)
                os.replace(old, current)
                try:
                    self._delete_key_for(manifest["vault_id"], data["new_key_id"])
                except Exception:
                    return
            else:
                shutil.rmtree(old)
                try:
                    self._delete_key_for(manifest["vault_id"], data["old_key_id"])
                except Exception:
                    return
            journal.unlink(missing_ok=True)
