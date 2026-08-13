import base64
import json
import os
import subprocess
import sys
import hashlib
import secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


ROOT = Path(__file__).parents[1]


def run(*args, env=None):
    merged = dict(os.environ)
    merged["PYTHONPATH"] = str(ROOT)
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, "-m", "tokenade", *args],
        cwd=ROOT,
        env=merged,
        text=True,
        capture_output=True,
    )


def test_vault_cli_roundtrip_and_failure_exit(tmp_path):
    source = tmp_path / "source.tokenade"
    source.write_text(json.dumps({"version": "3.0", "cookies": []}))
    key = base64.b64encode(b"k" * 32).decode()
    vault = tmp_path / "vault"
    output = tmp_path / "out.tokenade"
    vault_env = {"TOKENADE_VAULT_KEY": key}
    stored = run(
        "vault",
        "--vault-path",
        str(vault),
        "store",
        "primary",
        str(source),
        "--json",
        env=vault_env,
    )
    assert stored.returncode == 0, stored.stderr
    listed = run("vault", "--vault-path", str(vault), "list", "--json", env=vault_env)
    assert json.loads(listed.stdout)["data"][0]["name"] == "primary"
    retrieved = run(
        "vault",
        "--vault-path",
        str(vault),
        "retrieve",
        "primary",
        "--output",
        str(output),
        "--json",
        env=vault_env,
    )
    assert retrieved.returncode == 0 and output.read_bytes() == source.read_bytes()
    missing = run(
        "vault",
        "--vault-path",
        str(vault),
        "retrieve",
        "missing",
        "--json",
        env=vault_env,
    )
    assert missing.returncode == 1


def test_vault_cli_expands_quoted_home_in_store_path(tmp_path):
    home = tmp_path / "home"
    sessions = home / ".tokenade/sessions"
    sessions.mkdir(parents=True)
    source = sessions / "twitter.tokenade"
    source.write_text(json.dumps({"version": "3.0", "cookies": []}))
    key = base64.b64encode(b"k" * 32).decode()
    result = run(
        "vault",
        "--vault-path",
        str(home / ".tokenade/vault"),
        "store",
        "twitter",
        "~/.tokenade/sessions/twitter.tokenade",
        "--json",
        env={"HOME": str(home), "TOKENADE_VAULT_KEY": key},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["success"] is True


def test_vault_cli_missing_file_is_clean_json_and_does_not_create_vault(tmp_path):
    vault = tmp_path / "vault"
    result = run(
        "vault",
        "--vault-path",
        str(vault),
        "store",
        "missing",
        "~/missing.tokenade",
        "--json",
        env={"HOME": str(tmp_path)},
    )

    assert result.returncode == 1
    assert result.stderr == ""
    assert "Session file not found" in json.loads(result.stdout)["message"]
    assert not vault.exists()


def test_sync_cli_local_peer_roundtrip(tmp_path):
    home = tmp_path / "home"
    local = home / ".tokenade/sessions"
    remote = tmp_path / "remote"
    local.mkdir(parents=True)
    (local / "a.tokenade").write_text(
        json.dumps(
            {
                "version": "3.0",
                "created_at": "x",
                "site_name": "x",
                "auth_status": "unknown",
                "cookies": [],
            }
        )
    )
    env = {"HOME": str(home)}
    added = run(
        "sync",
        "peer",
        "add",
        "backup",
        "--transport",
        "local",
        "--path",
        str(remote),
        "--allow-plaintext",
        env=env,
    )
    assert added.returncode == 0, added.stderr
    plan = run("sync", "plan", "backup", "--json", env=env)
    assert json.loads(plan.stdout)["actions"][0]["action"] == "push"
    synced = run("sync", "run", "backup", "--allow-plaintext", "--json", env=env)
    assert synced.returncode == 0 and (remote / "a.tokenade").exists()


def test_sync_cli_missing_peer_is_clean_validation_error(tmp_path):
    result = run("sync", "plan", "missing", "--json", env={"HOME": str(tmp_path)})

    assert result.returncode == 1
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["error"] == "Peer 'missing' is not configured"
    assert "Traceback" not in result.stdout


def test_vault_cli_migrates_legacy_format(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    key = secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    data = b'{"cookies":[]}'
    encrypted = AESGCM(key).encrypt(nonce, data, None)
    (vault / "master.key").write_bytes(key)
    (vault / "entries.json").write_text(
        json.dumps({"old": {"name": "old", "metadata": {}}})
    )
    (vault / "old.enc").write_text(
        json.dumps(
            {
                "encrypted_data": base64.b64encode(encrypted[16:]).decode(),
                "iv": base64.b64encode(nonce).decode(),
                "tag": base64.b64encode(encrypted[:16]).decode(),
                "checksum": hashlib.sha256(data).hexdigest(),
            }
        )
    )

    migrated = run(
        "vault",
        "--vault-path",
        str(vault),
        "migrate",
        "--json",
        env={
            "TOKENADE_VAULT_KEY": base64.b64encode(b"k" * 32).decode(),
            "TOKENADE_VAULT_BACKUP_PASSPHRASE": "recovery password",
        },
    )

    assert migrated.returncode == 0, migrated.stderr
    assert json.loads(migrated.stdout)["metadata"]["entries_migrated"] == 1


def test_tui_command_builders():
    from tokenade.tui.cli_runner import (
        cmd_sync_action,
        cmd_sync_peer,
        cmd_vault,
    )

    assert cmd_vault("verify", vault_path="/vault")[-2:] == ["verify", "--json"]
    assert cmd_vault("migrate", vault_path="/vault")[-2:] == ["migrate", "--json"]
    assert cmd_sync_peer("add", name="p", transport="local", path="/remote")[:4] == [
        "sync",
        "peer",
        "add",
        "p",
    ]
    assert cmd_sync_action("run", "p")[:3] == ["sync", "run", "p"]
    vault_args = cmd_vault("backup", vault_path="/vault")
    assert "secret" not in " ".join(vault_args)
    assert "--key" not in vault_args
    assert "--passphrase" not in vault_args
