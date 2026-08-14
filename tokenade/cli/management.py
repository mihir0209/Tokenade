"""Session management CLI commands.

P1: thin facade - implementations live in tokenade.cli.handlers.*.
External imports of tokenade.cli.management.cmd_* remain valid.

Modules re-exported below so existing tests can patch
``tokenade.cli.management.time`` / helpers without breaking.
"""

import json  # noqa: F401
import logging
import os  # noqa: F401
import sys  # noqa: F401
import time  # noqa: F401 - patched by tests as management.time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("tokenade")

# Infrastructure / CI / misc (already split)
from tokenade.cli.handlers.infrastructure import (  # noqa: F401
    cmd_fleet,
    cmd_container,
    cmd_k8s,
)
from tokenade.cli.handlers.ci import (  # noqa: F401
    cmd_cicd,
    cmd_ci,
    cmd_autopsy,
    cmd_cloak,
    cmd_tui,
)
from tokenade.cli.handlers.misc import (  # noqa: F401
    cmd_monitor,
    cmd_daemon,
    _health_bar,
)

# Session + browser ops (P1 split)
from tokenade.cli.handlers.session_ops import (  # noqa: F401
    cmd_sessions,
    cmd_health,
    cmd_health_report,
    cmd_refresh,
    cmd_share,
    cmd_unshare,
    cmd_import,
    cmd_sync,
    cmd_validate_session,
    cmd_encrypted_refresh,
    cmd_refresh_oauth,
    cmd_oauth_config,
    cmd_batch_refresh,
    cmd_versions,
    cmd_rollback,
    cmd_session_diff,
    cmd_logs,
    cmd_mobile_import,
    cmd_clone_profile,
    cmd_share_url,
    _resolve_upstream_proxy,
    _run_post_refresh_plugins,
)
from tokenade.cli.handlers.browser_ops import (  # noqa: F401
    cmd_launch,
    cmd_refresh_browser,
    cmd_accounts,
    _refresh_session_cookies,
    _detect_url_from_cookies,
    _accounts_list,
    _accounts_status,
    _accounts_refresh,
)


def cmd_vault(args):
    """Handle vault commands."""
    from tokenade.core.vault import SessionVault, VaultConfig, VaultResult

    config = VaultConfig(
        vault_path=getattr(args, "vault_path", None) or "~/.tokenade/vault",
        master_key=os.environ.get("TOKENADE_VAULT_KEY"),
    )

    if not getattr(args, "vault_action", None):
        print("Error: vault action is required", file=sys.stderr)
        raise SystemExit(2)
    if args.vault_action == "migrate":
        migration_config = VaultConfig(
            vault_path=config.vault_path,
            backup_path=config.backup_path,
            max_backups=config.max_backups,
            master_key=config.master_key,
        )
        result = SessionVault.migrate_legacy(
            migration_config,
            passphrase=os.environ.get("TOKENADE_VAULT_BACKUP_PASSPHRASE"),
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(result.message, file=sys.stdout if result.success else sys.stderr)
        if not result.success:
            raise SystemExit(1)
        return

    source = None
    if args.vault_action == "store":
        source = Path(args.file).expanduser()
        if not source.is_absolute():
            source = Path.cwd() / source
        if not source.is_file():
            result = VaultResult(False, f"Session file not found: {source}")
            if args.json:
                print(json.dumps(result.to_dict(), indent=2))
            else:
                print(f"Error: {result.message}", file=sys.stderr)
            raise SystemExit(1)

    try:
        vault = SessionVault(config)
    except RuntimeError as exc:
        message = str(exc)
        if "system keyring" in message:
            message += (
                ". This Vault was opened without its original key. Restore the "
                "TOKENADE_VAULT_KEY used to create it or restore a passphrase-encrypted backup."
            )
        if getattr(args, "json", False):
            print(json.dumps({"success": False, "error": message}, indent=2))
        else:
            print(f"Error: {message}", file=sys.stderr)
        raise SystemExit(1)

    if args.vault_action == "store":
        result = vault.store(
            name=args.name,
            data=source.read_bytes(),
            metadata={},
            replace=getattr(args, "replace", False),
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            if result.success:
                print(f"Stored '{args.name}' in vault")
            else:
                print(f"Error: {result.message}", file=sys.stderr)

    elif args.vault_action == "retrieve":
        result = vault.retrieve(
            name=args.name,
            output_path=getattr(args, "output", None),
            overwrite=getattr(args, "overwrite", False),
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            if result.success:
                print(f"Retrieved '{args.name}'")
                if getattr(args, "output", None):
                    print(f"Saved to: {args.output}")
            else:
                print(f"Error: {result.message}", file=sys.stderr)

    elif args.vault_action == "delete":
        result = vault.delete(args.name)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            if result.success:
                print(f"Deleted '{args.name}'")
            else:
                print(f"Error: {result.message}", file=sys.stderr)

    elif args.vault_action == "list":
        result = vault.list_entries()
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            if result.data:
                for entry in result.data:
                    print(f"  {entry['name']}: created={entry['created_at']}")
            else:
                print("No entries in vault")

    elif args.vault_action == "rotate":
        result = vault.rotate_key()
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            if result.success:
                print(f"Rotated key: {result.message}")
            else:
                print(f"Error: {result.message}", file=sys.stderr)

    elif args.vault_action == "backup":
        result = vault.backup(
            getattr(args, "name", None),
            passphrase=os.environ.get("TOKENADE_VAULT_BACKUP_PASSPHRASE"),
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            if result.success:
                print(f"Created backup: {result.message}")
            else:
                print(f"Error: {result.message}", file=sys.stderr)

    elif args.vault_action == "restore":
        result = vault.restore(
            args.name,
            passphrase=os.environ.get("TOKENADE_VAULT_BACKUP_PASSPHRASE"),
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            if result.success:
                print(f"Restored: {result.message}")
            else:
                print(f"Error: {result.message}", file=sys.stderr)

    elif args.vault_action == "verify":
        result = vault.verify()
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(result.message)

    else:
        raise SystemExit(2)

    if not result.success:
        raise SystemExit(1)


def cmd_dashboard(args):
    """Handle dashboard commands."""
    from tokenade.core.dashboard import DashboardServer, DashboardConfig

    config = DashboardConfig(
        host=getattr(args, "host", None) or "127.0.0.1",
        port=getattr(args, "port", None) or 8080,
        title=getattr(args, "title", None) or "Tokenade Session Monitor",
        refresh_interval=getattr(args, "refresh", None) or 10,
    )

    server = DashboardServer(config)

    if args.dashboard_action == "start":
        print(f"Starting dashboard at http://{config.host}:{config.port}")
        print("Press Ctrl+C to stop")
        try:
            server.start(block=True)
        except KeyboardInterrupt:
            print("\nStopping dashboard...")
            server.stop()

    elif args.dashboard_action == "status":
        import urllib.request
        import urllib.error

        try:
            url = f"http://{config.host}:{config.port}/api/health"
            with urllib.request.urlopen(url) as response:
                data = json.loads(response.read())
                print(json.dumps(data, indent=2))
        except urllib.error.URLError as e:
            print(f"Dashboard not running: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.dashboard_action == "sessions":
        import urllib.request
        import urllib.error

        try:
            url = f"http://{config.host}:{config.port}/api/sessions"
            with urllib.request.urlopen(url) as response:
                data = json.loads(response.read())
                if getattr(args, "json", False):
                    print(json.dumps(data, indent=2))
                else:
                    if not data:
                        print("No sessions found")
                    else:
                        for session in data:
                            print(f"  {session['name']}: {session['status']}")
        except urllib.error.URLError as e:
            print(f"Dashboard not running: {e}", file=sys.stderr)
            sys.exit(1)


__all__ = [
    "cmd_sessions",
    "cmd_health",
    "cmd_health_report",
    "cmd_refresh",
    "cmd_share",
    "cmd_unshare",
    "cmd_import",
    "cmd_sync",
    "cmd_monitor",
    "cmd_daemon",
    "cmd_validate_session",
    "cmd_encrypted_refresh",
    "cmd_refresh_oauth",
    "cmd_oauth_config",
    "cmd_batch_refresh",
    "cmd_launch",
    "cmd_refresh_browser",
    "cmd_accounts",
    "cmd_versions",
    "cmd_rollback",
    "cmd_session_diff",
    "cmd_logs",
    "cmd_mobile_import",
    "cmd_clone_profile",
    "cmd_container",
    "cmd_k8s",
    "cmd_fleet",
    "cmd_cicd",
    "cmd_ci",
    "cmd_autopsy",
    "cmd_cloak",
    "cmd_tui",
    "cmd_vault",
    "cmd_dashboard",
    "_resolve_upstream_proxy",
    "_health_bar",
    "_refresh_session_cookies",
    "_detect_url_from_cookies",
    "_accounts_list",
    "_accounts_status",
    "_accounts_refresh",
    "_run_post_refresh_plugins",
]
