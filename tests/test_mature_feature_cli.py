import base64
import json
import os
import subprocess
import sys
from pathlib import Path


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


def test_analytics_cli_opt_in_report_and_delete(tmp_path):
    env = {"TOKENADE_ANALYTICS_DIR": str(tmp_path / "analytics")}
    enabled = run("analytics", "enable", "--retention-days", "7", env=env)
    assert enabled.returncode == 0 and json.loads(enabled.stdout)["enabled"] is True
    status = run("analytics", "status", env=env)
    assert json.loads(status.stdout)["retention_days"] == 7
    report = run("analytics", "report", "--days", "1", env=env)
    assert json.loads(report.stdout)["schema_version"] == 1
    deleted = run("analytics", "delete", "--yes", env=env)
    assert deleted.returncode == 0


def test_tui_command_builders():
    from tokenade.tui.cli_runner import (
        cmd_analytics,
        cmd_sync_action,
        cmd_sync_peer,
        cmd_vault,
    )

    assert cmd_vault("verify", vault_path="/vault")[-2:] == ["verify", "--json"]
    assert cmd_sync_peer("add", name="p", transport="local", path="/remote")[:4] == [
        "sync",
        "peer",
        "add",
        "p",
    ]
    assert cmd_sync_action("run", "p")[:3] == ["sync", "run", "p"]
    assert cmd_analytics("enable", retention_days=14) == [
        "analytics",
        "enable",
        "--retention-days",
        "14",
    ]
    vault_args = cmd_vault("backup", vault_path="/vault")
    assert "secret" not in " ".join(vault_args)
    assert "--key" not in vault_args
    assert "--passphrase" not in vault_args
