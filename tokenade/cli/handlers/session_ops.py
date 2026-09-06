"""Session management CLI ops - list/health/refresh/share/sync/versions/mobile."""

import json
import logging
import os
import platform
import signal
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("tokenade")


def cmd_inspect(args):
    """Inspect a Session without exposing or activating credentials."""
    from tokenade.core.artifacts import ProfileArtifactManager
    from tokenade.core.importer.session_packager import SessionPackager

    try:
        package = SessionPackager().load(
            args.session,
            password=getattr(args, "decrypt_password", None),
        )
        inspection = ProfileArtifactManager.inspect(package)
    except Exception as exc:
        print(f"[ERROR] Session inspection failed: {exc}")
        return

    data = inspection.as_dict()
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2))
        return

    print("\n" + "=" * 64)
    print("TOKENADE - Session Inspection")
    print("=" * 64)
    print(f"Site: {data['site']}")
    print(f"Format: {data['format_version']}")
    print(f"Auth status: {data['auth_status']}")
    print(f"Created: {data['created_at']}")
    print(f"Access mode: {data['access_mode']}")
    print(f"Cookies: {data['cookie_count']}")
    print(f"Tokens: {data['token_count']}")
    print(f"localStorage origins: {data['local_storage_origins']}")
    print(f"sessionStorage origins: {data['session_storage_origins']}")
    artifacts = data["profile_artifacts"]
    print(
        f"Profile artifacts: {artifacts['count']} ({artifacts['uncompressed_bytes']} bytes)"
    )
    if artifacts["owners"]:
        print(f"Artifact owners: {', '.join(artifacts['owners'])}")
    for requirement in data["required_plugins"]:
        version = f" {requirement['version']}" if requirement.get("version") else ""
        print(f"Required plugin: {requirement['name']}{version}")
    for warning in data["warnings"]:
        print(f"[WARN] {warning}")


def cmd_sessions(args):
    """Manage multiple sessions."""
    from tokenade.core.importer.session_manager import SessionManager

    manager = SessionManager(args.dir if hasattr(args, "dir") else ".")

    if args.sessions_command == "list":
        sessions = manager.list_sessions(
            pattern=args.pattern,
            recursive=args.recursive,
        )

        if args.site or args.browser:
            sessions = manager.filter_sessions(
                sessions,
                site_name=args.site,
                browser=args.browser,
            )

        if not sessions:
            print("No sessions found")
            return

        print("\n" + "=" * 70)
        print(f"{'Site':<20} {'Cookies':<10} {'Browser':<12} {'Size':<10} {'Path'}")
        print("=" * 70)

        for s in sessions:
            size = (
                f"{s.file_size / 1024:.1f}K"
                if s.file_size < 1024 * 1024
                else f"{s.file_size / (1024 * 1024):.1f}M"
            )
            print(
                f"{s.site_name:<20} {s.cookie_count:<10} {s.source_browser or 'unknown':<12} {size:<10} {Path(s.path).name}"
            )

        print(f"\n{'=' * 70}")
        print(f"Total: {len(sessions)} sessions")
        print(f"{'=' * 70}\n")

    elif args.sessions_command == "merge":
        for f in args.files:
            if not Path(f).exists():
                print(f"[ERROR] File not found: {f}")
                return

        output = manager.merge_sessions(
            args.files,
            args.output,
            site_name=args.site_name,
        )

        print(f"[OK] Merged {len(args.files)} sessions into: {output}")

    elif args.sessions_command == "rotate":
        for f in args.files:
            if not Path(f).exists():
                print(f"[ERROR] File not found: {f}")
                return

        selected = manager.rotate_session(
            args.files,
            strategy=args.strategy,
            state_file=args.state_file,
        )

        print(f"[SYNC] Selected: {selected}")

    elif args.sessions_command == "stats":
        for f in args.files:
            if not Path(f).exists():
                print(f"[ERROR] File not found: {f}")
                return

        stats = manager.get_session_stats(args.files)

        print("\n" + "=" * 60)
        print("Session Statistics")
        print("=" * 60)
        print(f"Sessions: {stats['session_count']}")
        print(f"Total cookies: {stats['total_cookies']}")
        print(f"Total size: {stats['total_size_bytes'] / 1024:.1f} KB")
        print(f"Sites: {', '.join(stats['unique_sites']) or 'none'}")
        print(f"Browsers: {', '.join(stats['unique_browsers']) or 'none'}")
        print(f"{'=' * 60}\n")

    else:
        print("[ERROR] Specify a sessions subcommand: list, merge, rotate, stats")


def cmd_health(args):
    """Check session health."""
    from tokenade.core.refresh.health_checker import (
        SessionHealthChecker,
        generate_health_report,
    )

    print("\n" + "=" * 80)
    print("TOKENADE - Session Health Check")
    print("=" * 80)

    session_files = []

    if args.session:
        session_files = [args.session]
    elif args.sessions_dir:
        sessions_path = Path(args.sessions_dir)
        if not sessions_path.exists():
            print(f"[ERROR] Directory not found: {args.sessions_dir}")
            return
        session_files = (
            [str(f) for f in sessions_path.glob("*.tokenade")]
            + [str(f) for f in sessions_path.glob("*.session")]
            + [str(f) for f in sessions_path.glob("*.json")]
        )

    if not session_files:
        print("[ERROR] No session files found")
        return

    checker = SessionHealthChecker()

    healthy_count = 0
    unhealthy_count = 0

    for session_file in session_files:
        print(f"\n[DIR] Checking: {Path(session_file).name}")

        health = checker.check_session(session_file)

        if health.healthy:
            healthy_count += 1
        else:
            unhealthy_count += 1

        print(generate_health_report(health))

    print("\n" + "=" * 80)
    print(f"SUMMARY: {healthy_count} healthy, {unhealthy_count} unhealthy")


def cmd_health_report(args):
    """Batch health report for CI/CD pipelines."""
    from tokenade.core.refresh.health_reporter import HealthReporter

    session_file = getattr(args, "session", None)
    sessions_dir = getattr(args, "sessions_dir", None)
    json_output = getattr(args, "json_output", False)
    min_health = getattr(args, "min_health", 0.5)
    max_expired = getattr(args, "max_expired", 0)
    webhook_url = getattr(args, "webhook", None)

    reporter = HealthReporter(min_health=min_health, max_expired=max_expired)

    session_files = [session_file] if session_file else None

    report = reporter.generate_report(
        sessions_dir=sessions_dir,
        session_files=session_files,
    )

    if json_output:
        print(report.to_json())
    else:
        print(report.summary())

    if webhook_url:
        sent = reporter.send_webhook(report, webhook_url)
        if sent:
            print("\n Report sent to webhook")
        else:
            print("\n[ERROR] Failed to send webhook")

    sys.exit(report.exit_code)


def cmd_refresh(args):
    """Refresh session from source browser."""
    print("\n" + "=" * 80)
    print("TOKENADE - Session Refresh")
    print("=" * 80)

    session_file = Path(args.session)
    if not session_file.exists():
        print(f"[ERROR] Session file not found: {args.session}")
        return

    print(f"\n[DIR] Session: {args.session}")
    print(f"[NET] Source: {args.source_browser}")

    site_config = None
    if args.site_config:
        with open(args.site_config) as f:
            import json

            site_config = json.load(f)
        if isinstance(site_config, list):
            site_config = site_config[0] if site_config else None

    try:
        from tokenade.core.refresh.health_checker import SessionRefresher

        refresher = SessionRefresher()
        result = refresher.refresh(
            session_file=str(session_file),
            source_browser=args.source_browser,
            source_browser_path=args.source_browser_path,
            source_profile=args.source_profile,
            site_config=site_config,
        )

        if result.success:
            print("\n[OK] Refresh successful")
            print(
                f"   Refreshed: {result.cookies_refreshed}/{result.cookies_total} cookies"
            )
        else:
            print("\n[ERROR] Refresh failed")
            if result.error:
                print(f"   Error: {result.error}")

    except Exception as e:
        logger.error(f"Session refresh failed: {e}", exc_info=True)
        print(
            "[ERROR] Refresh failed - check source browser is running and session is valid"
        )


def _resolve_upstream_proxy(args) -> Optional[str]:
    """Resolve upstream proxy from CLI args or config.

    Priority: --proxy > --proxy-file (with rotation) > config upstream_proxy

    Returns:
        Proxy URL string for browser --proxy-server flag, or None
    """
    from tokenade.core.proxy.rotation import ProxyPool, ProxyRotator, RotationStrategy
    from tokenade.core.config import load_config

    config = load_config()

    # Single proxy from --proxy flag
    proxy_url = getattr(args, "proxy", None)
    if proxy_url:
        return proxy_url

    # Proxy file with rotation
    proxy_file = getattr(args, "proxy_file", None)
    if proxy_file:
        try:
            pool = ProxyPool.from_file(proxy_file)
            if pool.size > 0:
                strategy_str = getattr(args, "proxy_strategy", "health-weighted")
                strategy = RotationStrategy(strategy_str)
                rotator = ProxyRotator(pool=pool, strategy=strategy)
                proxy = rotator.next()
                if proxy:
                    # Store rotator in args for later use (e.g., recording success/failure)
                    if not hasattr(args, "_proxy_rotator"):
                        args._proxy_rotator = rotator
                    if not hasattr(args, "_proxy_pool"):
                        args._proxy_pool = pool
                    return proxy.url
        except FileNotFoundError:
            logger.warning(f"Proxy file not found: {proxy_file}")
        except Exception as e:
            logger.warning(f"Failed to load proxy file: {e}")

    # Config fallback
    return config.get("upstream_proxy")


def cmd_share(args):
    """Create shareable session link or QR code."""
    from tokenade.core.importer.session_sharer import (
        SessionSharer,
        ShareConfig,
        generate_share_html,
    )
    from tokenade.core.importer.session_packager import SessionPackager

    session_file = Path(args.session)
    if not session_file.exists():
        print(f"[ERROR] Session file not found: {args.session}")
        return

    packager = SessionPackager()
    session = packager.load(str(session_file))

    sharer = SessionSharer()
    config = ShareConfig(
        expiry_hours=args.expiry,
        max_uses=args.max_uses,
        password_protected=bool(args.password),
        password=args.password,
        email_recipients=args.email_to.split(",")
        if getattr(args, "email_to", None)
        else None,
        smtp_host=getattr(args, "smtp_host", None),
        smtp_port=getattr(args, "smtp_port", 587),
        smtp_user=getattr(args, "smtp_user", None),
        smtp_password=getattr(args, "smtp_password", None),
        webhook_url=getattr(args, "webhook_url", None),
    )

    print("\n" + "=" * 60)
    print("TOKENADE - Share Session")
    print("=" * 60)
    print(f"\n[DIR] Session: {args.session}")
    print(f"[LOCK] Expires: {args.expiry} hours")
    if args.max_uses:
        print(f" Max uses: {args.max_uses}")
    if args.password:
        print("[KEY] Password protected: Yes")
    else:
        print(
            "[WARN] WARNING: No password - anyone with the URL can access this session!"
        )
        print("   Use --password to protect the share link.")

    # Warn about large payloads
    import json as _json

    size_kb = len(_json.dumps(session).encode()) / 1024
    if size_kb > 100:
        print(
            f"[WARN] WARNING: Session is {size_kb:.0f} KB - URL may be too long for QR/messaging"
        )

    if args.format == "qr":
        output_path = args.output or f"{session_file.stem}_qr.png"
        sharer.create_qr_code(session, output_path, config)
        print(f"\n[MOBILE] QR code saved to: {output_path}")
    elif args.format == "html":
        output_path = args.output or f"{session_file.stem}_share.html"
        share_url, session_id = sharer.create_share_link(session, config)
        generate_share_html(session, output_path)
        print(f"\n[FILE] Share page saved to: {output_path}")
        print(f"[WARN] WARNING: HTML file contains session data in plaintext!")
        print(f" Session ID: {session_id}")
    else:
        share_url, session_id = sharer.create_share_link(session, config)
        print(f"\n[URL] Share URL: {share_url}")
        print(f" Session ID: {session_id}")

    # Email delivery
    if getattr(args, "email_to", None):
        recipients = [r.strip() for r in args.email_to.split(",")]
        print(f"\n Sending to: {', '.join(recipients)}")
        try:
            sharer.send_email(session, config, recipients)
            print("   [OK] Email sent")
        except Exception as e:
            print(f"   [ERROR] Email failed: {e}")

    # Webhook delivery
    if getattr(args, "webhook_url", None):
        print(f"\n Sending to webhook: {args.webhook_url}")
        try:
            sent = sharer.send_webhook(session, config)
            if sent:
                print("   [OK] Webhook sent")
            else:
                print("   [ERROR] Webhook failed")
        except Exception as e:
            print(f"   [ERROR] Webhook error: {e}")

    print(f"\n{'=' * 60}\n")


def cmd_unshare(args):
    """Revoke a shared session or list active shares."""
    from tokenade.core.importer.session_sharer import SessionSharer

    sharer = SessionSharer()

    if args.list:
        shares = sharer.list_shared()
        if not shares:
            print("No active shared sessions")
            return

        print("\n" + "=" * 60)
        print("Active Shared Sessions")
        print("=" * 60)

        for s in shares:
            print(f"\n {s['session_id']}")
            print(
                f"   Created: {time.strftime('%Y-%m-%d %H:%M', time.localtime(s['created_at']))}"
            )
            print(
                f"   Expires: {time.strftime('%Y-%m-%d %H:%M', time.localtime(s['expires_at']))}"
            )
            print(f"   Uses: {s['use_count']}/{s['max_uses'] or 'inf'}")
            print(f"   Password: {'Yes' if s['has_password'] else 'No'}")

        print(f"\n{'=' * 60}\n")
        return

    if sharer.revoke_share(args.session_id):
        print(f"[OK] Revoked shared session: {args.session_id}")
    else:
        print(f"[ERROR] Failed to revoke session: {args.session_id}")


def cmd_import(args):
    """Import a shared session from a URL."""
    from tokenade.core.importer.session_sharer import SessionSharer
    from tokenade.core.importer.session_packager import SessionPackager

    url = args.url
    password = args.password
    output = args.output

    print("\n" + "=" * 60)
    print("TOKENADE - Import Shared Session")
    print("=" * 60)

    if not url.startswith("tokenade://share/"):
        print(f"[ERROR] Invalid share URL (must start with tokenade://share/)")
        return

    print(f"\n[URL] URL: {url[:60]}...")
    if password:
        print("[KEY] Password: provided")

    sharer = SessionSharer()

    try:
        session = sharer.load_from_url(url, password=password)
    except ValueError as e:
        print(f"\n[ERROR] Import failed: {e}")
        return
    except Exception as e:
        print(f"\n[ERROR] Import failed: {e}")
        return

    cookies = session.get("cookies", [])
    site_name = session.get("site_name", "unknown")
    print(f"\n[OK] Session loaded successfully")
    print(f"   Site: {site_name}")
    print(f"   Cookies: {len(cookies)}")

    # Save to file
    if output:
        save_path = output
    else:
        save_path = f"{site_name}_imported.tokenade"

    packager = SessionPackager()
    packager.save(session, save_path)
    print(f"   Saved: {save_path}")

    print(f"\n{'=' * 60}\n")


def cmd_sync(args):
    """Sync session daemon commands."""
    if getattr(args, "sync_command", None) in {"peer", "plan", "run", "status"}:
        return _cmd_peer_sync(args)
    from tokenade.core.importer.session_sync import SessionSyncDaemon, SyncTarget

    daemon = SessionSyncDaemon.load_config()

    if args.sync_command == "add":
        if not args.name or not args.domains:
            print("[ERROR] --name and --domains are required")
            return

        domains = [d.strip() for d in args.domains.split(",")]
        target = SyncTarget(
            name=args.name,
            domains=domains,
            browser=args.browser or "firefox",
            browser_profile=args.profile,
            output_dir=args.output_dir or "~/.tokenade/synced",
        )
        daemon.add_target(target)
        daemon.save_config()
        print(f"[OK] Sync target added: {target.name}")
        print(f"   Browser: {target.browser}")
        print(f"   Domains: {', '.join(target.domains)}")
        print(f"   Output: {target.output_dir}")

    elif args.sync_command == "remove":
        if not args.name:
            print("[ERROR] --name is required")
            return
        daemon.remove_target(args.name)
        daemon.save_config()
        print(f"[OK] Sync target removed: {args.name}")

    elif args.sync_command == "list":
        statuses = daemon.get_status()
        if not statuses:
            print("No sync targets configured")
            return
        print(f"\n{'=' * 60}")
        print("Session Sync Targets")
        print(f"{'=' * 60}")
        for s in statuses:
            print(f"\n[DIR] {s['name']}")
            print(f"   Browser: {s['browser']}")
            print(f"   Domains: {', '.join(s['domains'])}")
            print(f"   Last sync: {s['last_sync'] or 'never'}")
            print(f"   Cookies: {s['last_cookie_count']}")
            print(f"   Sync count: {s['sync_count']}")
            if s["error"]:
                print(f"   Error: {s['error']}")
        print(f"\n{'=' * 60}\n")

    elif args.sync_command == "once":
        print("[SYNC] Running one-time sync...")
        results = daemon.check_once()
        for name, changed in results.items():
            status = "[OK] synced" if changed else "[SKIP] unchanged"
            print(f"   {name}: {status}")

    elif args.sync_command == "start":
        interval = args.interval or 60
        print(f"[SYNC] Starting sync daemon (interval: {interval}s)...")
        print(f"   Targets: {len(daemon._targets)}")
        print("   Press Ctrl+C to stop\n")
        try:
            daemon.start(interval=interval)
        except KeyboardInterrupt:
            daemon.stop()
            print("\n[STOP] Daemon stopped")


def _cmd_peer_sync(args):
    from tokenade.core.sync import PeerConfig, PeerSync
    from tokenade.core.utils.paths import tokenade_home

    sync = PeerSync(str(tokenade_home() / ".tokenade/sessions"))
    command = args.sync_command
    if command == "peer":
        action = getattr(args, "peer_action", None)
        if action == "add":
            if args.transport == "ssh" and not args.host:
                raise SystemExit("--host is required for SSH peers")
            sync.add_peer(
                PeerConfig(
                    args.name,
                    args.transport,
                    args.path,
                    args.host,
                    args.user,
                    args.port,
                    args.identity,
                    args.known_hosts,
                    require_encrypted=not args.allow_plaintext,
                )
            )
            print(f"[OK] Peer saved: {args.name}")
        elif action == "remove":
            sync.remove_peer(args.name)
            print(f"[OK] Peer removed: {args.name}")
        elif action == "list":
            for peer in sync.list_peers():
                print(
                    f"{peer.name}: {peer.transport} {peer.host or ''} {peer.root}".strip()
                )
        else:
            raise SystemExit("peer action is required")
        return
    try:
        if command == "plan":
            result = sync.plan(args.peer, args.direction)
        elif command == "status":
            result = sync.status(args.peer)
        elif command == "run":
            result = sync.run(args.peer, args.direction, args.dry_run, args.allow_plaintext)
        else:
            raise SystemExit("unsupported sync command")
    except KeyError:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": f"Peer '{args.peer}' is not configured",
                    "next_step": "Save the peer first, then preview the plan",
                },
                indent=2,
            )
        )
        raise SystemExit(1)
    print(json.dumps(result, indent=2))
    if command == "run":
        if result["errors"]:
            raise SystemExit(4)
        if result["conflicts"]:
            raise SystemExit(2)


def cmd_validate_session(args):
    """Validate session files for CI/CD health gates."""
    from tokenade.core.refresh.session_validator import (
        SessionValidator,
        create_ci_validation_rules,
    )
    import json as json_mod

    validator = SessionValidator()

    rules = create_ci_validation_rules(
        min_health=args.min_health,
        max_expired=args.max_expired,
        require_oauth=args.require_oauth,
        max_age_hours=args.max_age_hours,
    )

    if args.session:
        result = validator.validate(args.session, rules)

        if args.json_output:
            print(json_mod.dumps(result.to_dict(), indent=2))
        else:
            print(validator.ci_report([result]))

        sys.exit(result.exit_code)

    elif args.sessions_dir:
        results = validator.validate_directory(args.sessions_dir, rules)

        if args.json_output:
            output = {
                "total": len(results),
                "passed": sum(1 for r in results if r.valid),
                "failed": sum(1 for r in results if not r.valid),
                "results": [r.to_dict() for r in results],
            }
            print(json_mod.dumps(output, indent=2))
        else:
            print(validator.ci_report(results))

        failed = sum(1 for r in results if not r.valid)
        sys.exit(1 if failed > 0 else 0)

    else:
        print("[ERROR] Specify --session or --sessions-dir")
        sys.exit(1)


def cmd_encrypted_refresh(args):
    """Refresh encrypted session files."""
    from tokenade.core.refresh.encrypted_refresh import (
        EncryptedRefreshPipeline,
        batch_encrypted_refresh,
    )

    print("\n" + "=" * 80)
    print("TOKENADE - Encrypted Session Refresh")
    print("=" * 80)

    if args.sessions_dir:
        print(f"\n[DIR] Batch refreshing: {args.sessions_dir}")
        results = batch_encrypted_refresh(
            sessions_dir=args.sessions_dir,
            password=args.password,
            key_file=args.key_file,
            source_browser=args.source_browser,
            force=args.force,
        )

        for name, result in results.items():
            status = "[OK]" if result.success else "[ERROR]"
            method = f"[{result.method}]" if result.success else ""
            encrypted = "(encrypted)" if result.was_encrypted else ""
            print(f"  {status} {name} {method} {encrypted}")

        succeeded = sum(1 for r in results.values() if r.success)
        print(f"\n{'=' * 80}")
        print(f"Total: {len(results)}, Succeeded: {succeeded}")
        print(f"{'=' * 80}\n")

    elif args.session:
        pipeline = EncryptedRefreshPipeline()
        result = pipeline.refresh(
            session_file=args.session,
            password=args.password,
            key_file=args.key_file,
            source_browser=args.source_browser,
            force=args.force,
        )

        if result.success:
            print(f"\n[OK] Refresh successful")
            print(f"   Method: {result.method}")
            print(f"   Encrypted: {result.was_encrypted}")
            print(f"   Duration: {result.duration_ms:.0f}ms")
        else:
            print(f"\n[ERROR] Refresh failed")
            if result.error:
                print(f"   Error: {result.error}")

    else:
        print("[ERROR] Specify --session or --sessions-dir")


def cmd_refresh_oauth(args):
    """Refresh OAuth tokens using stored refresh token."""
    print("\n" + "=" * 80)
    print("TOKENADE - OAuth Token Refresh")
    print("=" * 80)

    session_file = Path(args.session)
    if not session_file.exists():
        print(f"[ERROR] Session file not found: {args.session}")
        return

    print(f"\n[DIR] Session: {args.session}")

    try:
        from tokenade.core.refresh.oauth_refresh import SessionOAuthManager

        manager = SessionOAuthManager(str(session_file))

        status = manager.get_status()
        print(f"[NET] Site: {status['site_name']}")
        print(f"[KEY] Has OAuth config: {status['has_oauth_config']}")
        print(f"[SYNC] Has refresh token: {status['has_refresh_token']}")
        print(f"  Has access token: {status['has_access_token']}")

        if status["access_token_expired"]:
            print("[WARN] Access token is expired")
        elif status["expires_in"] is not None:
            print(f"[TIME] Expires in: {status['expires_in']}s")

        if not manager.has_oauth_config():
            print("\n[ERROR] No OAuth config in session")
            print(
                "   Run: tokenade oauth-config --session <file> --client-id <id> --token-endpoint <url>"
            )
            return

        if not manager.get_refresh_token():
            print("\n[ERROR] No refresh token in session")
            print("   Re-export session with OAuth tokens")
            return

        print("\n[SYNC] Refreshing token...")
        result = manager.refresh()

        if result.success:
            print("\n[OK] Token refreshed successfully")
            print(f"   New access token: {result.tokens.access_token[:20]}...")
            if result.tokens.expires_in:
                print(f"   Expires in: {result.tokens.expires_in}s")
            print(f"   Duration: {result.duration_ms:.0f}ms")
        else:
            print("\n[ERROR] Token refresh failed")
            if result.error:
                print(f"   Error: {result.error}")

    except Exception as e:
        logger.error(f"OAuth refresh failed: {e}", exc_info=True)
        print("[ERROR] Refresh failed - check OAuth configuration")


def cmd_oauth_config(args):
    """Configure OAuth settings for a session."""
    from tokenade.core.refresh.oauth_refresh import SessionOAuthManager, OAuthConfig

    session_file = Path(args.session)
    if not session_file.exists():
        print(f"[ERROR] Session file not found: {args.session}")
        return

    manager = SessionOAuthManager(str(session_file))

    if args.show:
        config = manager.get_oauth_config()
        if config:
            print("\n" + "=" * 60)
            print("OAuth Configuration")
            print("=" * 60)
            print(f"  Token Endpoint: {config.token_endpoint}")
            print(
                f"  Client ID: {config.client_id[:20]}..."
                if len(config.client_id) > 20
                else f"  Client ID: {config.client_id}"
            )
            print(
                f"  Client Secret: {'*' * 10 if config.client_secret else '(not set)'}"
            )
            print(f"  Scopes: {', '.join(config.scopes)}")
            print(f"  Grant Type: {config.grant_type}")
            print(f"{'=' * 60}\n")
        else:
            print("No OAuth config set for this session")
        return

    if not args.client_id or not args.token_endpoint:
        print("[ERROR] --client-id and --token-endpoint are required")
        return

    config = OAuthConfig(
        token_endpoint=args.token_endpoint,
        client_id=args.client_id,
        client_secret=args.client_secret or "",
        scopes=args.scopes.split(",")
        if args.scopes
        else ["openid", "profile", "email"],
    )

    manager.set_oauth_config(config)
    manager.save()

    print(f"\n[OK] OAuth config saved for: {args.session}")
    print(f"   Token Endpoint: {config.token_endpoint}")
    print(f"   Client ID: {config.client_id[:20]}...")
    print(f"   Scopes: {', '.join(config.scopes)}")


def cmd_batch_refresh(args):
    """Refresh multiple sessions with rate limiting."""
    print("\n" + "=" * 80)
    print("TOKENADE - Batch Session Refresh")
    print("=" * 80)

    from tokenade.core.refresh.batch_refresh import BatchRefresher

    batch = BatchRefresher(
        sessions_dir=args.sessions_dir,
        max_workers=args.max_workers,
        delay_between=args.delay,
        source_browser=args.source_browser,
        source_profile=args.source_profile,
    )

    sessions = batch.discover_sessions()
    print(f"\n[DIR] Found {len(sessions)} sessions in {args.sessions_dir}")

    if not sessions:
        print("   No .tokenade files found")
        return

    for s in sessions:
        print(f"   - {s.name}")

    if not args.yes:
        response = input("\n[SYNC] Refresh all sessions? [y/N]: ").strip().lower()
        if response != "y":
            print("Cancelled")
            return

    print(f"\n[SYNC] Refreshing with {args.max_workers} workers...")
    report = batch.refresh_all(force=args.force)

    print("\n" + report.summary())


def _run_post_refresh_plugins(loader, session):
    """Run post-refresh plugins (webhooks, notifications, etc.)."""
    from tokenade.plugin.base import NotificationPlugin

    refreshers = loader.list_refreshers()
    for name, refresher in refreshers.items():
        try:
            # Notification plugins: call send() for post-refresh events
            if isinstance(refresher, NotificationPlugin):
                refresher.send("refresh_completed", {"session": session})
            # Session refresh plugins: only run if they can handle this session
            elif hasattr(refresher, "can_refresh") and refresher.can_refresh(session):
                pass  # Already handled by the main refresh flow
        except Exception as e:
            logger.warning(f"Post-refresh plugin {name} failed: {e}")


def cmd_versions(args):
    """List or create session versions."""
    action = getattr(args, "version_action", "list") or "list"

    if action == "list":
        _versions_list(args)
    elif action == "create":
        _versions_create(args)
    elif action == "delete":
        _versions_delete(args)
    else:
        print("Usage: tokenade versions <list|create|delete> <session>")


def _versions_list(args):
    """List versions for a session."""
    from tokenade.core.storage.session_versions import SessionVersionManager

    session_path = args.session
    mgr = SessionVersionManager()
    versions = mgr.list_versions(session_path)

    if not versions:
        print(f"[DIR] No versions for {Path(session_path).name}")
        print(f"   Create one: tokenade versions create {session_path}")
        return

    print(f"\n{'=' * 70}")
    print(f"TOKENADE - Versions for {Path(session_path).name} ({len(versions)})")
    print(f"{'=' * 70}")

    for v in versions:
        print(
            f"   v{v.version}: {v.cookie_count} cookies | {v.size_bytes} bytes | {v.created_at[:19]}"
        )
        if v.description:
            print(f"         {v.description}")
    print()


def _versions_create(args):
    """Create a new version of a session."""
    from tokenade.core.storage.session_versions import SessionVersionManager

    session_path = args.session
    description = getattr(args, "description", "") or ""

    if not Path(session_path).exists():
        print(f"[ERROR] Session file not found: {session_path}")
        return

    mgr = SessionVersionManager()
    version = mgr.create_version(session_path, description)
    print(f"[OK] Created version {version.version} of {Path(session_path).name}")
    print(f"   Cookies: {version.cookie_count} | Size: {version.size_bytes} bytes")


def _versions_delete(args):
    """Delete a specific version."""
    from tokenade.core.storage.session_versions import SessionVersionManager

    session_path = args.session
    version = args.version

    mgr = SessionVersionManager()
    if mgr.delete_version(session_path, version):
        print(f"[OK] Deleted version {version}")
    else:
        print(f"[ERROR] Version {version} not found")


def cmd_rollback(args):
    """Rollback a session to a specific version."""
    from tokenade.core.storage.session_versions import SessionVersionManager

    session_path = args.session
    version = args.version

    if not Path(session_path).exists():
        print(f"[ERROR] Session file not found: {session_path}")
        return

    mgr = SessionVersionManager()

    # Show what we're rolling back to
    versions = mgr.list_versions(session_path)
    target = None
    for v in versions:
        if v.version == version:
            target = v
            break

    if not target:
        print(f"[ERROR] Version {version} not found")
        return

    print(f"[SYNC] Rolling back {Path(session_path).name} to version {version}")
    print(f"   {target.cookie_count} cookies | {target.created_at[:19]}")

    if mgr.rollback(session_path, version):
        print(f"[OK] Rollback complete")
    else:
        print(f"[ERROR] Rollback failed")


def cmd_session_diff(args):
    """Compare two versions of a session."""
    from tokenade.core.storage.session_versions import SessionVersionManager

    session_path = args.session
    version_a = args.version_a
    version_b = args.version_b

    mgr = SessionVersionManager()
    diff = mgr.diff(session_path, version_a, version_b)

    print(f"\n{'=' * 70}")
    print(f"TOKENADE - Diff: v{diff.version_a} -> v{diff.version_b}")
    print(f"{'=' * 70}")

    if not diff.has_changes and not diff.storage_changes:
        print("   No differences found")
        return

    if diff.cookies_added:
        print(f"\n   Added ({len(diff.cookies_added)}):")
        for c in diff.cookies_added:
            print(f"     + {c['name']} ({c['domain']})")

    if diff.cookies_removed:
        print(f"\n   Removed ({len(diff.cookies_removed)}):")
        for c in diff.cookies_removed:
            print(f"     - {c['name']} ({c['domain']})")

    if diff.cookies_modified:
        print(f"\n   Modified ({len(diff.cookies_modified)}):")
        for c in diff.cookies_modified:
            print(f"     ~ {c['name']} ({c['domain']})")

    print(f"\n   Unchanged: {diff.cookies_unchanged}")

    if diff.storage_changes:
        print(f"\n   Storage changes:")
        for key, change in diff.storage_changes.items():
            print(f"     {key}: changed")
    print()


# -- Logs Command ------------------------------------------------


def cmd_logs(args):
    """View structured logs."""
    from tokenade.core.logging.structured import LogManager

    if getattr(args, "cleanup", None):
        days = args.cleanup
        removed = LogManager.cleanup_old_logs(retention_days=days)
        print(f"Removed {removed} log file(s) older than {days} days")
        return

    if getattr(args, "list_files", False):
        files = LogManager.get_log_files()
        if not files:
            print("No log files found")
            return
        print(f"\n{'=' * 70}")
        print("TOKENADE - Log Files")
        print(f"{'=' * 70}")
        for f in files:
            size_kb = f["size_bytes"] / 1024
            print(f"   {f['name']:<30} {size_kb:>8.1f} KB  {f['modified'][:19]}")
        print(f"{'=' * 70}\n")
        return

    log_file = getattr(args, "log_file", None)
    lines_count = getattr(args, "lines", 50) or 50
    search_query = getattr(args, "search", None)
    json_output = getattr(args, "json_output", False)
    follow = getattr(args, "follow", False)

    if follow:
        log_path = (
            Path(log_file) if log_file else LogManager.get_log_dir() / "tokenade.log"
        )
        if not log_path.exists():
            print("No log file found. Run a tokenade command first to generate logs.")
            return
        print(f"Following {log_path} (Ctrl+C to stop)...")
        try:
            import subprocess

            subprocess.run(["tail", "-f", str(log_path)])
        except KeyboardInterrupt:
            print("\nStopped following logs")
        return

    if search_query:
        results = LogManager.search(search_query, log_file=log_file)
        if not results:
            print(f"No matches found for: {search_query}")
            return
        if json_output:
            print(json.dumps([_parse_log_line(line) for line in results], indent=2))
        else:
            for line in results[-lines_count:]:
                print(line)
        return

    recent = LogManager.read_recent(lines=lines_count, log_file=log_file)
    if not recent:
        print("No log entries found. Run a tokenade command first to generate logs.")
        return

    if json_output:
        print(json.dumps([_parse_log_line(line) for line in recent], indent=2))
    else:
        for line in recent:
            print(line)


def _parse_log_line(line):
    """Try to parse a JSON log line; return raw string on failure."""
    try:
        return json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return {"raw": line}


# -- Mobile Import ------------------------------------------------


def cmd_mobile_import(args):
    """Import sessions from mobile devices (Android/iOS)."""
    from tokenade.core.importer.mobile_import import MobileImportManager

    manager = MobileImportManager()

    if not manager.is_available():
        print("[ERROR] No mobile extraction method available")
        if platform.system() != "Darwin":
            print("   Install ADB: https://developer.android.com/tools/adb")
            print("   Or use macOS for iOS extraction")
        else:
            print("   Install ADB for Android: https://developer.android.com/tools/adb")
            print("   Install pymobiledevice3 for iOS: pip install pymobiledevice3")
        return

    # List devices mode
    if getattr(args, "list_devices", False):
        _mobile_list_devices(manager)
        return

    # Auto mode
    if getattr(args, "auto", False):
        _mobile_auto_extract(manager, args)
        return

    # Specific device
    device_serial = getattr(args, "device", None)
    if not device_serial:
        # No device specified - list and prompt
        devices = manager.list_devices()
        if not devices:
            print("[ERROR] No mobile devices connected")
            print("   Connect a device via USB and enable USB debugging (Android)")
            return
        if len(devices) == 1:
            device = devices[0]
        else:
            print("Multiple devices found:")
            for i, d in enumerate(devices):
                print(f"  [{i + 1}] {d.model} ({d.serial}) - {d.platform}")
            print("  Specify --device <serial> to choose")
            return
    else:
        # Find the device
        devices = manager.list_devices()
        device = None
        for d in devices:
            if d.serial == device_serial:
                device = d
                break
        if not device:
            print(f"[ERROR] Device not found: {device_serial}")
            print("   Connected devices:")
            for d in devices:
                print(f"     {d.serial} - {d.model}")
            return

    browser = getattr(args, "browser", "auto")
    domains = getattr(args, "domains", None)
    if domains:
        domains = [d.strip() for d in domains.split(",")]

    output = getattr(args, "output", None)
    site_name = getattr(args, "site_name", None)

    print(f"\n{'=' * 60}")
    print("TOKENADE - Mobile Import")
    print(f"{'=' * 60}")
    print(f"   Device: {device.model} ({device.serial})")
    print(f"   Platform: {device.platform} {device.os_version}")
    print(f"   Browsers: {', '.join(device.available_browsers) or 'none detected'}")
    if domains:
        print(f"   Domains: {', '.join(domains)}")

    if browser == "auto" and device.available_browsers:
        browser = device.available_browsers[0]
        print(f"   Auto-selected browser: {browser}")

    print(f"\n[SYNC] Extracting cookies...")

    result = manager.extract(
        device=device,
        browser=browser,
        domains=domains,
        output_file=output,
        site_name=site_name,
    )

    if result.success:
        print(f"\n[OK] Extraction successful")
        print(f"   Browser: {result.browser}")
        print(f"   Cookies: {result.cookie_count}")
        print(f"   Site: {result.site_name}")
        print(f"   Auth: {result.auth_status}")
        print(f"   Domains: {', '.join(result.domains[:10])}")
        if result.session_file:
            print(f"   Saved: {result.session_file}")
    else:
        print(f"\n[ERROR] Extraction failed: {result.error}")
        if "ADB" in str(result.error):
            print("   Ensure USB debugging is enabled and device is authorized")


def _mobile_list_devices(manager):
    """List all connected mobile devices."""
    devices = manager.list_devices()

    print(f"\n{'=' * 60}")
    print(f"TOKENADE - Mobile Devices")
    print(f"{'=' * 60}")

    if not devices:
        print("\n   No devices connected")
        print("   Android: Enable USB debugging and connect via USB")
        print("   iOS: Connect via USB (macOS only, requires pymobiledevice3)")
        return

    for d in devices:
        print(f"\n   [MOBILE] {d.model} ({d.platform.upper()})")
        print(f"      Serial: {d.serial}")
        print(f"      OS: {d.os_version}")
        if d.available_browsers:
            print(f"      Browsers: {', '.join(d.available_browsers)}")
        else:
            print(f"      Browsers: none detected")

    print(f"\n{'=' * 60}")
    print(f"Total: {len(devices)} device(s)")
    print(f"{'=' * 60}\n")


def _mobile_auto_extract(manager, args):
    """Auto-detect and extract from the first available device."""
    devices = manager.list_devices()

    if not devices:
        print("[ERROR] No mobile devices connected")
        return

    device = devices[0]
    print(f"   Auto-detected: {device.model} ({device.serial})")

    domains = getattr(args, "domains", None)
    if domains:
        domains = [d.strip() for d in domains.split(",")]

    result = manager.extract(
        device=device,
        browser="auto",
        domains=domains,
        output_file=getattr(args, "output", None),
        site_name=getattr(args, "site_name", None),
    )

    if result.success:
        print(f"[OK] Extracted {result.cookie_count} cookies from {result.browser}")
        if result.session_file:
            print(f"   Saved: {result.session_file}")
    else:
        print(f"[ERROR] Failed: {result.error}")


def cmd_clone_profile(args):
    """Clone a browser profile to a new location."""
    from tokenade.core.browser.profile_cloner import ProfileCloner

    cloner = ProfileCloner()

    # List profiles mode
    if getattr(args, "list_profiles", False):
        _clone_list_profiles(cloner, args)
        return

    # Clone mode
    source = getattr(args, "source", None)
    dest = getattr(args, "dest", None)
    browser = getattr(args, "browser", "chrome") or "chrome"
    session = getattr(args, "session", None)
    profile_name = getattr(args, "profile", None)

    if not dest:
        print("[ERROR] --dest is required")
        return

    print(f"\n{'=' * 60}")
    print("TOKENADE - Browser Profile Cloner")
    print(f"{'=' * 60}")

    if source:
        # Clone from specific source
        print(f"   Source: {source}")
        print(f"   Dest: {dest}")
        print(f"   Browser: {browser}")
        if session:
            print(f"   Session: {session}")

        result = cloner.clone_profile(source, dest, browser, session)
    else:
        # Clone from system default
        print(f"   Browser: {browser}")
        print(f"   Dest: {dest}")
        if session:
            print(f"   Session: {session}")

        result = cloner.clone_default_profile(dest, browser, profile_name, session)

    if result.success:
        print(f"\n[OK] Profile cloned successfully")
        print(f"   Files: {result.files_copied}")
        print(f"   Size: {result.size_bytes / (1024 * 1024):.1f} MB")
        if result.session_injected:
            print(f"   Cookies injected: {result.cookies_injected}")
        print(f"   Location: {result.dest_path}")
        print(f"\n   Launch with:")
        print(
            f"   tokenade launch --browser {browser} --profile-dir {result.dest_path}"
        )
    else:
        print(f"\n[ERROR] Clone failed:")
        for err in result.errors:
            print(f"   {err}")

    print(f"{'=' * 60}\n")


def _clone_list_profiles(cloner, args):
    """List available browser profiles."""
    browser = getattr(args, "browser", "chrome") or "chrome"
    profiles = cloner.list_profiles(browser)

    print(f"\n{'=' * 60}")
    print(f"TOKENADE - {browser.title()} Profiles")
    print(f"{'=' * 60}")

    if not profiles:
        print(f"\n   No {browser} profiles found")
        return

    for p in profiles:
        default = " (default)" if p["is_default"] else ""
        print(f"\n   {p['name']}{default}")
        print(f"   Path: {p['path']}")
        if p["last_used"]:
            print(f"   Last used: {p['last_used']}")

    print(f"\n{'=' * 60}")
    print(f"Total: {len(profiles)} profile(s)")
    print(f"{'=' * 60}\n")


# ---------------------------------------------------------------------------
# URL Shortener share commands
# ---------------------------------------------------------------------------


def cmd_share_url(args):
    """Share sessions via URL shortener with password protection."""
    from tokenade.cli.share import cmd_share_url as _impl

    return _impl(args)


# ---------------------------------------------------------------------------
# Container management commands
# ---------------------------------------------------------------------------
