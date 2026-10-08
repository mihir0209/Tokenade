"""Session synchronization CLI commands."""

import argparse
import json
import sys

from tokenade.cli import add_hidden_command


def cmd_sync(args):
    """Handle sync commands."""
    if not hasattr(args, "sync_action"):
        print("Usage: tokenade sync <action> [options]", file=sys.stderr)
        sys.exit(1)

    from tokenade.core.sync import SessionSyncer, SyncConfig

    config = SyncConfig(
        remote_host=getattr(args, "remote_host", "") or "",
        remote_port=getattr(args, "remote_port", 22) or 22,
        remote_path=getattr(args, "remote_path", "~/.tokenade/sessions") or "~/.tokenade/sessions",
        local_path=getattr(args, "local_path", "~/.tokenade/sessions") or "~/.tokenade/sessions",
        conflict_resolution=getattr(args, "conflict", "newest") or "newest",
        transport=getattr(args, "transport", "ssh") or "ssh",
        s3_bucket=getattr(args, "s3_bucket", "") or "",
        s3_endpoint_url=getattr(args, "s3_endpoint", None),
        s3_region=getattr(args, "s3_region", "us-east-1") or "us-east-1",
    )

    syncer = SessionSyncer(config)

    if args.sync_action == "push":
        result = syncer.push()
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"Pushed {len(result.synced)} files")
            if result.errors:
                print(f"Errors: {len(result.errors)}")

    elif args.sync_action == "pull":
        result = syncer.pull()
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"Pulled {len(result.synced)} files")
            if result.errors:
                print(f"Errors: {len(result.errors)}")

    elif args.sync_action == "bidirectional":
        result = syncer.bidirectional()
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"Synced {len(result.synced)} files")
            if result.conflicts:
                print(f"Conflicts: {len(result.conflicts)}")

    elif args.sync_action == "status":
        status = syncer.status()
        if args.json:
            print(json.dumps(status, indent=2))
        else:
            print(f"Local files: {status['local_files']}")
            print(f"Remote files: {status['remote_files']}")
            print(f"Pending push: {status['pending_push']}")
            print(f"Pending pull: {status['pending_pull']}")
            print(f"Conflicts: {status['conflicts']}")

    else:
        print(f"Unknown sync action: {args.sync_action}", file=sys.stderr)
        sys.exit(1)


def register_sync_parser(subparsers):
    """Register sync parser."""
    sync_parser = subparsers.add_parser(
        "sync",
        help="Synchronize sessions across machines",
    )

    sync_subparsers = sync_parser.add_subparsers(dest="sync_action")

    for action, help_text in [
        ("push", "Push sessions to remote"),
        ("pull", "Pull sessions from remote"),
        ("bidirectional", "Bidirectional sync"),
        ("status", "Show sync status"),
    ]:
        p = sync_subparsers.add_parser(action, help=help_text)
        p.add_argument("--remote-host", help="Remote host")
        p.add_argument("--remote-port", type=int, help="Remote SSH port")
        p.add_argument("--remote-path", help="Remote path")
        p.add_argument("--local-path", help="Local path")
        p.add_argument("--transport", choices=["ssh", "rsync", "s3", "r2"], default="ssh", help="Sync transport")
        p.add_argument("--s3-bucket", help="S3 / R2 Bucket name")
        p.add_argument("--s3-endpoint", help="S3 / Cloudflare R2 endpoint URL")
        p.add_argument("--s3-region", default="us-east-1", help="S3 region")
        if action == "bidirectional":
            p.add_argument("--conflict", choices=["newest", "oldest", "local", "remote"], default="newest", help="Conflict resolution")
        p.add_argument("--json", action="store_true", help="JSON output")

    return sync_parser
