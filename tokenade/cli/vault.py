"""Session vault CLI commands."""

import argparse
import json
import sys

from tokenade.cli import add_hidden_command


def cmd_vault(args):
    """Handle vault commands."""
    if not hasattr(args, "vault_action"):
        print("Usage: tokenade vault <action> [options]", file=sys.stderr)
        sys.exit(1)
    
    from tokenade.core.vault import SessionVault, VaultConfig
    
    config = VaultConfig(
        vault_path=args.vault_path or "~/.tokenade/vault",
    )
    
    vault = SessionVault(config)
    
    if args.vault_action == "store":
        result = vault.store(
            name=args.name,
            data=open(args.file, "rb").read(),
            metadata={"source": args.file},
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
            output_path=args.output,
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            if result.success:
                print(f"Retrieved '{args.name}'")
                if args.output:
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
        result = vault.backup(args.name)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            if result.success:
                print(f"Created backup: {result.message}")
            else:
                print(f"Error: {result.message}", file=sys.stderr)
    
    elif args.vault_action == "restore":
        result = vault.restore(args.name)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            if result.success:
                print(f"Restored: {result.message}")
            else:
                print(f"Error: {result.message}", file=sys.stderr)
    
    else:
        print(f"Unknown vault action: {args.vault_action}", file=sys.stderr)
        sys.exit(1)


def register_vault_parser(subparsers):
    """Register vault parser."""
    vault_parser = subparsers.add_parser(
        "vault",
        help="Encrypted session storage",
    )
    
    vault_subparsers = vault_parser.add_subparsers(dest="vault_action")
    
    store_parser = vault_subparsers.add_parser("store", help="Store session in vault")
    store_parser.add_argument("name", help="Entry name")
    store_parser.add_argument("file", help="Session file to store")
    store_parser.add_argument("--vault-path", help="Vault path")
    store_parser.add_argument("--json", action="store_true", help="JSON output")
    
    retrieve_parser = vault_subparsers.add_parser("retrieve", help="Retrieve from vault")
    retrieve_parser.add_argument("name", help="Entry name")
    retrieve_parser.add_argument("--output", help="Output file path")
    retrieve_parser.add_argument("--vault-path", help="Vault path")
    retrieve_parser.add_argument("--json", action="store_true", help="JSON output")
    
    delete_parser = vault_subparsers.add_parser("delete", help="Delete from vault")
    delete_parser.add_argument("name", help="Entry name")
    delete_parser.add_argument("--vault-path", help="Vault path")
    delete_parser.add_argument("--json", action="store_true", help="JSON output")
    
    list_parser = vault_subparsers.add_parser("list", help="List vault entries")
    list_parser.add_argument("--vault-path", help="Vault path")
    list_parser.add_argument("--json", action="store_true", help="JSON output")
    
    rotate_parser = vault_subparsers.add_parser("rotate", help="Rotate encryption key")
    rotate_parser.add_argument("--vault-path", help="Vault path")
    rotate_parser.add_argument("--json", action="store_true", help="JSON output")
    
    backup_parser = vault_subparsers.add_parser("backup", help="Backup vault")
    backup_parser.add_argument("--name", help="Backup name")
    backup_parser.add_argument("--vault-path", help="Vault path")
    backup_parser.add_argument("--json", action="store_true", help="JSON output")
    
    restore_parser = vault_subparsers.add_parser("restore", help="Restore vault from backup")
    restore_parser.add_argument("name", help="Backup name")
    restore_parser.add_argument("--vault-path", help="Vault path")
    restore_parser.add_argument("--json", action="store_true", help="JSON output")
    
    return vault_parser
