"""Session synchronization across machines CLI commands."""

import argparse
import json
import sys


def cmd_sync_remote(args):
    """Handle remote sync commands."""
    if not hasattr(args, "sync_action"):
        print("Usage: tokenade sync-remote <action> [options]", file=sys.stderr)
        sys.exit(1)
    
    from tokenade.core.sync import SessionSyncer, SyncConfig
    
    config = SyncConfig(
        remote_host=args.remote_host or "",
        remote_port=args.remote_port or 22,
        remote_path=args.remote_path or "~/.tokenade/sessions",
        local_path=args.local_path or "~/.tokenade/sessions",
        conflict_resolution=getattr(args, 'conflict', None) or "newest",
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


def register_sync_remote_parser(subparsers):
    """Register sync-remote parser."""
    sync_parser = subparsers.add_parser(
        "sync-remote",
        help="Synchronize sessions across machines (SSH/rsync)",
    )
    
    sync_subparsers = sync_parser.add_subparsers(dest="sync_action")
    
    push_parser = sync_subparsers.add_parser("push", help="Push sessions to remote")
    push_parser.add_argument("--remote-host", required=True, help="Remote host")
    push_parser.add_argument("--remote-port", type=int, default=22, help="Remote SSH port")
    push_parser.add_argument("--remote-path", default="~/.tokenade/sessions", help="Remote path")
    push_parser.add_argument("--local-path", default="~/.tokenade/sessions", help="Local path")
    push_parser.add_argument("--json", action="store_true", help="JSON output")
    
    pull_parser = sync_subparsers.add_parser("pull", help="Pull sessions from remote")
    pull_parser.add_argument("--remote-host", required=True, help="Remote host")
    pull_parser.add_argument("--remote-port", type=int, default=22, help="Remote SSH port")
    pull_parser.add_argument("--remote-path", default="~/.tokenade/sessions", help="Remote path")
    pull_parser.add_argument("--local-path", default="~/.tokenade/sessions", help="Local path")
    pull_parser.add_argument("--json", action="store_true", help="JSON output")
    
    bidi_parser = sync_subparsers.add_parser("bidirectional", help="Bidirectional sync")
    bidi_parser.add_argument("--remote-host", required=True, help="Remote host")
    bidi_parser.add_argument("--remote-port", type=int, default=22, help="Remote SSH port")
    bidi_parser.add_argument("--remote-path", default="~/.tokenade/sessions", help="Remote path")
    bidi_parser.add_argument("--local-path", default="~/.tokenade/sessions", help="Local path")
    bidi_parser.add_argument("--conflict", choices=["newest", "oldest", "local", "remote"],
                           default="newest", help="Conflict resolution")
    bidi_parser.add_argument("--json", action="store_true", help="JSON output")
    
    status_parser = sync_subparsers.add_parser("status", help="Show sync status")
    status_parser.add_argument("--remote-host", required=True, help="Remote host")
    status_parser.add_argument("--remote-port", type=int, default=22, help="Remote SSH port")
    status_parser.add_argument("--remote-path", default="~/.tokenade/sessions", help="Remote path")
    status_parser.add_argument("--local-path", default="~/.tokenade/sessions", help="Local path")
    status_parser.add_argument("--json", action="store_true", help="JSON output")
    
    return sync_parser
