# Vault And Sync

## Session Vault

The mature Vault is a local single-user encrypted store.

```bash
export TOKENADE_VAULT_KEY="$(python -c 'import base64; print(base64.b64encode(b"replace-with-32-byte-key-here!!").decode())')"
tokenade vault store github github.tokenade
tokenade vault list --json
tokenade vault retrieve github --output restored.tokenade
tokenade vault verify
tokenade vault rotate
export TOKENADE_VAULT_BACKUP_PASSPHRASE='recovery passphrase'
tokenade vault backup --name monthly
tokenade vault restore monthly
```

Desktop use defaults to the OS keyring. Headless use must provide `--key` or
`TOKENADE_VAULT_KEY`. The key is never stored beside the vault.

Properties:

- AES-256-GCM with entry identity bound as associated data.
- Versioned manifest and encrypted entry envelopes.
- Atomic writes and a cross-process Vault lock.
- Journaled multi-entry key rotation with startup recovery.
- Portable passphrase-encrypted backups.
- Legacy migration requires the same user-supplied recovery passphrase and seals
  the untouched old Vault into a uniquely named encrypted recovery archive.
- `SessionVault.recover_legacy_archive(...)` decrypts that archive into a separate
  directory without replacing the active Vault.
- Duplicate names and output overwrite are rejected by default.
- Legacy `master.key`/`entries.json` vaults fail closed and require migration.

The manifest intentionally keeps entry display names, byte sizes, and timestamps
in plaintext so entries can be listed without decryption. Session payload bytes
and Session contents remain authenticated and encrypted.

Not currently provided: multi-user ACLs, automatic scheduled rotation, expiry,
or version history.

## Peer Sync

Peer Sync synchronizes opaque `.tokenade` files between repositories.

```bash
tokenade sync peer add backup --transport local --path /mnt/private/tokenade --allow-plaintext
tokenade sync plan backup --direction two-way --json
tokenade sync run backup --direction two-way --allow-plaintext --json
tokenade sync status backup --json
```

SSH/SFTP peers require an existing trusted host key:

```bash
tokenade sync peer add workstation \
  --transport ssh --host workstation.example --user alice \
  --path .tokenade/sessions --identity ~/.ssh/id_ed25519 \
  --known-hosts ~/.ssh/known_hosts
```

Rules:

- Content hashes and a persisted three-way baseline determine actions.
- Mtime never chooses a winner.
- Both-sides-changed produces an unresolved conflict and exit code `2`.
- Local writes use temporary files and atomic rename. SFTP uses POSIX rename when
  supported and otherwise fails rather than claiming universal atomic overwrite.
- Non-local peers require encrypted Session files unless explicitly allowed.
- Unknown SSH host keys are rejected.
- Remote paths use SFTP and are never interpolated into shell commands.

The older `sync add/list/once/start` commands package browser sources and remain
separate from peer repository synchronization.
