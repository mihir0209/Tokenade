"""Session sharing CLI commands."""

import argparse
import json
import sys

from tokenade.cli import add_hidden_command


def cmd_share(args):
    """Handle share commands."""
    if not hasattr(args, "share_action"):
        print("Usage: tokenade share <action> [options]", file=sys.stderr)
        sys.exit(1)
    
    from tokenade.core.sharing import SessionSharer, ShareConfig
    
    config = ShareConfig(
        expiry_hours=args.expiry or 24,
        max_uses=args.max_uses or 0,
        require_password=args.password is not None,
    )
    
    sharer = SessionSharer(config)
    
    if args.share_action == "create":
        result = sharer.share_session(
            session_file=args.session,
            password=args.password,
        )
        
        if args.qr:
            qr_path = args.qr
            sharer.generate_qr(result.share_url, qr_path)
            print(f"QR code saved to: {qr_path}")
        
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"Share URL: {result.share_url}")
            print(f"Share ID: {result.share_id}")
            if result.expiry:
                import time
                print(f"Expires: {time.ctime(result.expiry)}")
    
    elif args.share_action == "retrieve":
        data = sharer.retrieve_session(
            share_id=args.share_id,
            password=args.password,
            output_path=args.output,
        )
        
        if data:
            if args.json:
                print(json.dumps({"success": True, "size": len(data)}, indent=2))
            else:
                print(f"Retrieved {len(data)} bytes")
                if args.output:
                    print(f"Saved to: {args.output}")
        else:
            print("Failed to retrieve session", file=sys.stderr)
            sys.exit(1)
    
    elif args.share_action == "revoke":
        success = sharer.revoke(args.share_id)
        if args.json:
            print(json.dumps({"success": success}, indent=2))
        else:
            if success:
                print(f"Revoked share: {args.share_id}")
            else:
                print(f"Share not found: {args.share_id}")
    
    elif args.share_action == "list":
        shares = sharer.list_shares()
        if args.json:
            print(json.dumps(shares, indent=2))
        else:
            if not shares:
                print("No active shares")
            else:
                for share in shares:
                    print(f"  {share['share_id']}: expires={share['expires_at']}, uses={share['current_uses']}/{share['max_uses']}")
    
    elif args.share_action == "cleanup":
        count = sharer.cleanup_expired()
        if args.json:
            print(json.dumps({"cleaned": count}, indent=2))
        else:
            print(f"Cleaned up {count} expired shares")
    
    else:
        print(f"Unknown share action: {args.share_action}", file=sys.stderr)
        sys.exit(1)


def register_share_parser(subparsers):
    """Register share parser."""
    share_parser = subparsers.add_parser(
        "share",
        help="Share sessions via encrypted URLs",
    )
    
    share_subparsers = share_parser.add_subparsers(dest="share_action")
    
    create_parser = share_subparsers.add_parser("create", help="Create share link")
    create_parser.add_argument("session", help="Session file to share")
    create_parser.add_argument("--password", help="Password protection")
    create_parser.add_argument("--expiry", type=int, help="Expiry in hours")
    create_parser.add_argument("--max-uses", type=int, help="Max uses (0=unlimited)")
    create_parser.add_argument("--qr", help="QR code output path")
    create_parser.add_argument("--json", action="store_true", help="JSON output")
    
    retrieve_parser = share_subparsers.add_parser("retrieve", help="Retrieve shared session")
    retrieve_parser.add_argument("share_id", help="Share ID")
    retrieve_parser.add_argument("--password", help="Password")
    retrieve_parser.add_argument("--output", help="Output file path")
    retrieve_parser.add_argument("--json", action="store_true", help="JSON output")
    
    revoke_parser = share_subparsers.add_parser("revoke", help="Revoke a share")
    revoke_parser.add_argument("share_id", help="Share ID to revoke")
    revoke_parser.add_argument("--json", action="store_true", help="JSON output")
    
    list_parser = share_subparsers.add_parser("list", help="List active shares")
    list_parser.add_argument("--json", action="store_true", help="JSON output")
    
    cleanup_parser = share_subparsers.add_parser("cleanup", help="Cleanup expired shares")
    cleanup_parser.add_argument("--json", action="store_true", help="JSON output")
    
    return share_parser
