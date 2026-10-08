"""Session sharing CLI commands."""

import argparse
import json
import sys
import time


def _supabase_from_args(args):
    """Build optional SupabaseConfig from CLI flags / env / defaults."""
    from tokenade.core.sharing.supabase_store import SupabaseConfig

    url = getattr(args, "supabase_url", None) or None
    key = getattr(args, "supabase_key", None) or None
    no_remote = bool(getattr(args, "no_remote", False))
    if no_remote:
        return SupabaseConfig(url="", anon_key="", source="none")
    if url or key:
        return SupabaseConfig.from_env(url=url or "", anon_key=key or "")
    return SupabaseConfig.from_env()


def _print_create_result(result: dict, *, json_mode: bool) -> None:
    if json_mode:
        # Never dump full ciphertext in accidental logs via session keys
        out = {k: v for k, v in result.items() if k != "session"}
        print(json.dumps(out, indent=2))
        return
    if not result.get("success"):
        print(f"Error: {result.get('error', 'Unknown error')}", file=sys.stderr)
        sys.exit(1)

    full_url = result.get("full_url") or result.get("original_url") or ""
    short_url = result.get("short_url") or ""
    short_id = result.get("short_id") or ""
    transport = result.get("transport") or "embedded"
    remote_src = result.get("remote_source") or ""

    print()
    print("=" * 60)
    print("TOKENADE SHARE")
    print("=" * 60)
    print(f"Short ID:   {short_id}")
    print(f"Short ref:  {short_url}")
    if full_url:
        print(f"Full URL:   {full_url[:100]}{'...' if len(full_url) > 100 else ''}")
    print(f"Transport:  {transport}" + (f" ({remote_src})" if remote_src else ""))
    print("Password:   never uploaded (local only)")
    if result.get("expires_at"):
        print(f"Expires:    {time.ctime(result['expires_at'])}")
    out_name = result.get("file_name") or "received.tokenade"
    print()
    print("Receiver (short id - needs same remote / public default):")
    print(f"  python3 -m tokenade share-url retrieve {short_id} \\")
    print(f"      --password 'YOUR_PASSWORD' -o {out_name}")
    print()
    print("Receiver (full URL - works offline, no server):")
    print("  python3 -m tokenade share-url retrieve '<full_url>' \\")
    print(f"      --password 'YOUR_PASSWORD' -o {out_name}")
    print()
    print(f"Then: python3 -m tokenade load --file {out_name} --visible")
    print("Note: tokenade:// is CLI-only - not a browser protocol.")
    if result.get("message"):
        print()
        print(result["message"])
    print("=" * 60)
    print()


def cmd_share(args):
    """Handle share commands (legacy SessionSharer)."""
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
        from tokenade.core.artifacts import ProfileArtifactManager
        from tokenade.core.importer.session_packager import SessionPackager
        inspection = ProfileArtifactManager.inspect(SessionPackager().load(args.session))
        if not args.json:
            print(f"Access mode: {inspection.access_mode.value}")
            for warning in inspection.warnings:
                print(f"[WARN] {warning}")
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
                print(f"Expires: {time.ctime(result.expiry)}")

    elif args.share_action == "retrieve":
        data = sharer.retrieve_session(
            share_id=args.share_id,
            password=args.password,
            output_path=args.output,
        )

        if data:
            try:
                from tokenade.core.artifacts import ProfileArtifactManager
                package = json.loads(data.decode("utf-8"))
                inspection = ProfileArtifactManager.inspect(package)
                if not args.json:
                    print(f"Access mode: {inspection.access_mode.value}")
                    for warning in inspection.warnings:
                        print(f"[WARN] {warning}")
            except Exception:
                pass
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
                    print(
                        f"  {share['share_id']}: expires={share['expires_at']}, "
                        f"uses={share['current_uses']}/{share['max_uses']}"
                    )

    elif args.share_action == "cleanup":
        count = sharer.cleanup_expired()
        if args.json:
            print(json.dumps({"cleaned": count}, indent=2))
        else:
            print(f"Cleaned up {count} expired shares")

    else:
        print(f"Unknown share action: {args.share_action}", file=sys.stderr)
        sys.exit(1)


def cmd_share_url(args):
    """Handle share-url commands (password + full URL + optional Supabase)."""
    if not hasattr(args, "share_action") or not args.share_action:
        print("Usage: tokenade share-url <create|retrieve|revoke|list|cleanup|status> ...", file=sys.stderr)
        sys.exit(1)

    from tokenade.core.sharing.url_shortener import SessionURLShortener, URLShortenerConfig

    config = URLShortenerConfig(
        backend=getattr(args, "backend", None) or "local",
        api_key=getattr(args, "api_key", None),
        custom_domain=getattr(args, "domain", None),
        expiry_hours=getattr(args, "expiry", None) or 24,
        require_password=True,
        password_min_length=getattr(args, "password_min_length", None) or 8,
        max_uses=getattr(args, "max_uses", None) or 0,
    )

    sb = _supabase_from_args(args)
    shortener = SessionURLShortener(config, supabase_config=sb)

    if args.share_action == "status":
        from tokenade.core.sharing.supabase_store import SupabaseConfig, PUBLIC_SUPABASE_URL

        info = {
            "enabled": sb.enabled,
            "source": sb.source,
            "url": sb.url if sb.enabled else None,
            "is_public_default": sb.is_public_default,
            "public_default_url": PUBLIC_SUPABASE_URL,
        }
        if getattr(args, "json", False):
            print(json.dumps(info, indent=2))
        else:
            if not sb.enabled:
                print("Remote share: OFF (embedded full URL still works)")
            else:
                label = {
                    "public": "public default",
                    "config": "private (config.json)",
                    "env": "private (env)",
                    "override": "CLI override",
                }.get(sb.source, sb.source)
                print(f"Remote share: ON ({label})")
                print(f"  URL: {sb.url}")
                print("  Access: RPC-only (ciphertext; password never stored)")
                print("  Limits (public): 30 creates/IP/hour, max 7d expiry, max_uses<=50")
        return

    if args.share_action == "create":
        if not args.password:
            print("Error: --password is required for URL shortener sharing", file=sys.stderr)
            sys.exit(1)

        result = shortener.create_share(
            session_file=args.session,
            password=args.password,
            expiry_hours=getattr(args, "expiry", None),
            max_uses=getattr(args, "max_uses", None),
            include_request_json=getattr(args, "include_request", False),
        )
        _print_create_result(result, json_mode=bool(getattr(args, "json", False)))
        if not result.get("success"):
            sys.exit(1)

    elif args.share_action == "retrieve":
        if not args.password:
            print("Error: --password is required to retrieve session", file=sys.stderr)
            sys.exit(1)

        from pathlib import Path as _Path

        out = getattr(args, "output", None) or None
        default_dir = str(_Path.home() / ".tokenade" / "sessions")
        result = shortener.retrieve_session(
            short_url=args.share_url,
            password=args.password,
            output_path=out,
            default_dir=default_dir if not out else None,
        )

        if getattr(args, "json", False):
            safe = {k: v for k, v in result.items() if k != "session"}
            if result.get("session") is not None:
                safe["session_keys"] = list(result["session"].keys()) if isinstance(result["session"], dict) else True
            print(json.dumps(safe, indent=2))
        else:
            if result.get("success"):
                print("Session retrieved successfully!")
                print(f"  Source: {result.get('source', '?')}")
                saved = result.get("output_path")
                if saved:
                    print(f"  Saved:  {saved}")
                remaining = result.get("remaining_uses")
                if remaining is not None:
                    print(f"  Remaining uses: {remaining}")
            else:
                print(f"Error: {result.get('error', 'Unknown error')}", file=sys.stderr)
                sys.exit(1)

    elif args.share_action == "revoke":
        success = shortener.revoke(args.share_id)
        # Also try remote
        try:
            from tokenade.core.sharing.supabase_store import SupabaseShareStore
            store = SupabaseShareStore(sb)
            if store.available:
                success = store.revoke(args.share_id) or success
        except Exception:
            pass
        if getattr(args, "json", False):
            print(json.dumps({"success": success}, indent=2))
        else:
            if success:
                print(f"Revoked share: {args.share_id}")
            else:
                print(f"Share not found: {args.share_id}")

    elif args.share_action == "list":
        shares = shortener.list_shares()
        if getattr(args, "json", False):
            print(json.dumps(shares, indent=2))
        else:
            if not shares:
                print("No local active shares (remote shares are not listable)")
            else:
                for share in shares:
                    print(f"  {share['short_id']}: {share['short_url']}")
                    print(
                        f"    Expires: {share['expires_at']}, "
                        f"Uses: {share['current_uses']}/{share['max_uses']}"
                    )

    elif args.share_action == "cleanup":
        stats = shortener.cleanup_local_store()
        if getattr(args, "json", False):
            print(json.dumps({"success": True, **stats}, indent=2))
        else:
            print(
                "Cleaned local share store: "
                f"expired={stats.get('expired', 0)}, "
                f"stripped_embeds={stats.get('stripped', 0)}, "
                f"removed={stats.get('removed', 0)}, "
                f"remaining={stats.get('remaining', 0)}"
            )

    else:
        print(f"Unknown share-url action: {args.share_action}", file=sys.stderr)
        sys.exit(1)


def _add_supabase_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--supabase-url",
        help="Private Supabase project URL (overrides default public store)",
    )
    parser.add_argument(
        "--supabase-key",
        help="Private Supabase anon/publishable key (never service_role)",
    )
    parser.add_argument(
        "--no-remote",
        action="store_true",
        help="Disable remote store (embedded full URL only)",
    )


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


def register_share_url_parser(subparsers):
    """Register share-url parser for URL shortener integration."""
    share_url_parser = subparsers.add_parser(
        "share-url",
        help="Share sessions via password-protected URL (full URL + optional Supabase short-id)",
    )

    share_url_subparsers = share_url_parser.add_subparsers(dest="share_action")

    create_parser = share_url_subparsers.add_parser(
        "create", help="Create password-protected share link"
    )
    create_parser.add_argument("session", help="Session file to share")
    create_parser.add_argument("--password", required=True, help="Password for encryption (required)")
    create_parser.add_argument("--expiry", type=int, help="Expiry in hours (default: 24)")
    create_parser.add_argument("--max-uses", type=int, help="Max uses (0=server default)")
    create_parser.add_argument(
        "--backend",
        choices=["local", "bitly", "tinyurl"],
        default="local",
        help="Optional HTTP shortener backend (payload still uses tokenade://)",
    )
    create_parser.add_argument("--api-key", help="API key for URL shortener (for bitly)")
    create_parser.add_argument("--domain", help="Custom domain for shortener")
    create_parser.add_argument(
        "--password-min-length", type=int, default=8, help="Minimum password length"
    )
    create_parser.add_argument(
        "--include-request", action="store_true", help="Include request.json in session"
    )
    create_parser.add_argument("--json", action="store_true", help="JSON output")
    _add_supabase_flags(create_parser)

    retrieve_parser = share_url_subparsers.add_parser(
        "retrieve", help="Retrieve session with password"
    )
    retrieve_parser.add_argument("share_url", help="Share URL, short id, or full tokenade:// URL")
    retrieve_parser.add_argument(
        "--password", required=True, help="Password for decryption (required)"
    )
    retrieve_parser.add_argument("-o", "--output", help="Output file path")
    retrieve_parser.add_argument("--json", action="store_true", help="JSON output")
    _add_supabase_flags(retrieve_parser)

    revoke_parser = share_url_subparsers.add_parser("revoke", help="Revoke a share link")
    revoke_parser.add_argument("share_id", help="Share ID to revoke")
    revoke_parser.add_argument("--json", action="store_true", help="JSON output")
    _add_supabase_flags(revoke_parser)

    list_parser = share_url_subparsers.add_parser("list", help="List local share links")
    list_parser.add_argument("--json", action="store_true", help="JSON output")

    cleanup_parser = share_url_subparsers.add_parser(
        "cleanup", help="Cleanup expired local share links"
    )
    cleanup_parser.add_argument("--json", action="store_true", help="JSON output")

    status_parser = share_url_subparsers.add_parser(
        "status", help="Show remote share (Supabase) configuration"
    )
    status_parser.add_argument("--json", action="store_true", help="JSON output")
    _add_supabase_flags(status_parser)

    return share_url_parser
