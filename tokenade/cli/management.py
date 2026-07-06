"""Session management CLI commands."""
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

# Import new handler functions (Phase 55-67 commands)
from tokenade.cli.handlers.infrastructure import cmd_fleet  # noqa: F401
from tokenade.cli.handlers.ci import (  # noqa: F401
    cmd_cicd, cmd_ci, cmd_autopsy, cmd_cloak, cmd_tui,
)
from tokenade.cli.handlers.misc import (  # noqa: F401
    cmd_monitor, cmd_analytics, cmd_daemon, _health_bar,
)


def cmd_sessions(args):
    """Manage multiple sessions."""
    from tokenade.core.importer.session_manager import SessionManager

    manager = SessionManager(args.dir if hasattr(args, 'dir') else ".")

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
            size = f"{s.file_size / 1024:.1f}K" if s.file_size < 1024 * 1024 else f"{s.file_size / (1024 * 1024):.1f}M"
            print(f"{s.site_name:<20} {s.cookie_count:<10} {s.source_browser or 'unknown':<12} {size:<10} {Path(s.path).name}")

        print(f"\n{'=' * 70}")
        print(f"Total: {len(sessions)} sessions")
        print(f"{'=' * 70}\n")

    elif args.sessions_command == "merge":
        for f in args.files:
            if not Path(f).exists():
                print(f"❌ File not found: {f}")
                return

        output = manager.merge_sessions(
            args.files,
            args.output,
            site_name=args.site_name,
        )

        print(f"✅ Merged {len(args.files)} sessions into: {output}")

    elif args.sessions_command == "rotate":
        for f in args.files:
            if not Path(f).exists():
                print(f"❌ File not found: {f}")
                return

        selected = manager.rotate_session(
            args.files,
            strategy=args.strategy,
            state_file=args.state_file,
        )

        print(f"🔄 Selected: {selected}")

    elif args.sessions_command == "stats":
        for f in args.files:
            if not Path(f).exists():
                print(f"❌ File not found: {f}")
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
        print("❌ Specify a sessions subcommand: list, merge, rotate, stats")


def cmd_health(args):
    """Check session health."""
    from tokenade.core.refresh.health_checker import SessionHealthChecker, generate_health_report

    print("\n" + "=" * 80)
    print("TOKENADE - Session Health Check")
    print("=" * 80)

    session_files = []

    if args.session:
        session_files = [args.session]
    elif args.sessions_dir:
        sessions_path = Path(args.sessions_dir)
        if not sessions_path.exists():
            print(f"❌ Directory not found: {args.sessions_dir}")
            return
        session_files = (
            [str(f) for f in sessions_path.glob("*.tokenade")]
            + [str(f) for f in sessions_path.glob("*.session")]
            + [str(f) for f in sessions_path.glob("*.json")]
        )

    if not session_files:
        print("❌ No session files found")
        return

    checker = SessionHealthChecker()

    healthy_count = 0
    unhealthy_count = 0

    for session_file in session_files:
        print(f"\n📁 Checking: {Path(session_file).name}")

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
            print("\n📡 Report sent to webhook")
        else:
            print("\n❌ Failed to send webhook")

    sys.exit(report.exit_code)


def cmd_refresh(args):
    """Refresh session from source browser."""
    print("\n" + "=" * 80)
    print("TOKENADE - Session Refresh")
    print("=" * 80)

    session_file = Path(args.session)
    if not session_file.exists():
        print(f"❌ Session file not found: {args.session}")
        return

    print(f"\n📂 Session: {args.session}")
    print(f"🌐 Source: {args.source_browser}")

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
            site_config=site_config
        )

        if result.success:
            print("\n✅ Refresh successful")
            print(f"   Refreshed: {result.cookies_refreshed}/{result.cookies_total} cookies")
        else:
            print("\n❌ Refresh failed")
            if result.error:
                print(f"   Error: {result.error}")

    except Exception as e:
        logger.error(f"Session refresh failed: {e}", exc_info=True)
        print("❌ Refresh failed — check source browser is running and session is valid")


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
    from tokenade.core.importer.session_sharer import SessionSharer, ShareConfig, generate_share_html
    from tokenade.core.importer.session_packager import SessionPackager

    session_file = Path(args.session)
    if not session_file.exists():
        print(f"❌ Session file not found: {args.session}")
        return

    packager = SessionPackager()
    session = packager.load(str(session_file))

    sharer = SessionSharer()
    config = ShareConfig(
        expiry_hours=args.expiry,
        max_uses=args.max_uses,
        password_protected=bool(args.password),
        password=args.password,
        email_recipients=args.email_to.split(",") if getattr(args, "email_to", None) else None,
        smtp_host=getattr(args, "smtp_host", None),
        smtp_port=getattr(args, "smtp_port", 587),
        smtp_user=getattr(args, "smtp_user", None),
        smtp_password=getattr(args, "smtp_password", None),
        webhook_url=getattr(args, "webhook_url", None),
    )

    print("\n" + "=" * 60)
    print("TOKENADE - Share Session")
    print("=" * 60)
    print(f"\n📂 Session: {args.session}")
    print(f"🔒 Expires: {args.expiry} hours")
    if args.max_uses:
        print(f"🔢 Max uses: {args.max_uses}")
    if args.password:
        print("🔑 Password protected: Yes")
    else:
        print("⚠️  WARNING: No password — anyone with the URL can access this session!")
        print("   Use --password to protect the share link.")

    # Warn about large payloads
    import json as _json
    size_kb = len(_json.dumps(session).encode()) / 1024
    if size_kb > 100:
        print(f"⚠️  WARNING: Session is {size_kb:.0f} KB — URL may be too long for QR/messaging")

    if args.format == "qr":
        output_path = args.output or f"{session_file.stem}_qr.png"
        sharer.create_qr_code(session, output_path, config)
        print(f"\n📱 QR code saved to: {output_path}")
    elif args.format == "html":
        output_path = args.output or f"{session_file.stem}_share.html"
        share_url, session_id = sharer.create_share_link(session, config)
        generate_share_html(session, output_path)
        print(f"\n📄 Share page saved to: {output_path}")
        print(f"⚠️  WARNING: HTML file contains session data in plaintext!")
        print(f"🆔 Session ID: {session_id}")
    else:
        share_url, session_id = sharer.create_share_link(session, config)
        print(f"\n🔗 Share URL: {share_url}")
        print(f"🆔 Session ID: {session_id}")

    # Email delivery
    if getattr(args, "email_to", None):
        recipients = [r.strip() for r in args.email_to.split(",")]
        print(f"\n📧 Sending to: {', '.join(recipients)}")
        try:
            sharer.send_email(session, config, recipients)
            print("   ✅ Email sent")
        except Exception as e:
            print(f"   ❌ Email failed: {e}")

    # Webhook delivery
    if getattr(args, "webhook_url", None):
        print(f"\n📡 Sending to webhook: {args.webhook_url}")
        try:
            sent = sharer.send_webhook(session, config)
            if sent:
                print("   ✅ Webhook sent")
            else:
                print("   ❌ Webhook failed")
        except Exception as e:
            print(f"   ❌ Webhook error: {e}")

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
            print(f"\n🆔 {s['session_id']}")
            print(f"   Created: {time.strftime('%Y-%m-%d %H:%M', time.localtime(s['created_at']))}")
            print(f"   Expires: {time.strftime('%Y-%m-%d %H:%M', time.localtime(s['expires_at']))}")
            print(f"   Uses: {s['use_count']}/{s['max_uses'] or '∞'}")
            print(f"   Password: {'Yes' if s['has_password'] else 'No'}")

        print(f"\n{'=' * 60}\n")
        return

    if sharer.revoke_share(args.session_id):
        print(f"✅ Revoked shared session: {args.session_id}")
    else:
        print(f"❌ Failed to revoke session: {args.session_id}")


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
        print(f"❌ Invalid share URL (must start with tokenade://share/)")
        return

    print(f"\n🔗 URL: {url[:60]}...")
    if password:
        print("🔑 Password: provided")

    sharer = SessionSharer()

    try:
        session = sharer.load_from_url(url, password=password)
    except ValueError as e:
        print(f"\n❌ Import failed: {e}")
        return
    except Exception as e:
        print(f"\n❌ Import failed: {e}")
        return

    cookies = session.get("cookies", [])
    site_name = session.get("site_name", "unknown")
    print(f"\n✅ Session loaded successfully")
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
    from tokenade.core.importer.session_sync import SessionSyncDaemon, SyncTarget

    daemon = SessionSyncDaemon.load_config()

    if args.sync_command == "add":
        if not args.name or not args.domains:
            print("❌ --name and --domains are required")
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
        print(f"✅ Sync target added: {target.name}")
        print(f"   Browser: {target.browser}")
        print(f"   Domains: {', '.join(target.domains)}")
        print(f"   Output: {target.output_dir}")

    elif args.sync_command == "remove":
        if not args.name:
            print("❌ --name is required")
            return
        daemon.remove_target(args.name)
        daemon.save_config()
        print(f"✅ Sync target removed: {args.name}")

    elif args.sync_command == "list":
        statuses = daemon.get_status()
        if not statuses:
            print("No sync targets configured")
            return
        print(f"\n{'=' * 60}")
        print("Session Sync Targets")
        print(f"{'=' * 60}")
        for s in statuses:
            print(f"\n📁 {s['name']}")
            print(f"   Browser: {s['browser']}")
            print(f"   Domains: {', '.join(s['domains'])}")
            print(f"   Last sync: {s['last_sync'] or 'never'}")
            print(f"   Cookies: {s['last_cookie_count']}")
            print(f"   Sync count: {s['sync_count']}")
            if s['error']:
                print(f"   Error: {s['error']}")
        print(f"\n{'=' * 60}\n")

    elif args.sync_command == "once":
        print("🔄 Running one-time sync...")
        results = daemon.check_once()
        for name, changed in results.items():
            status = "✅ synced" if changed else "⏭️  unchanged"
            print(f"   {name}: {status}")

    elif args.sync_command == "start":
        interval = args.interval or 60
        print(f"🔄 Starting sync daemon (interval: {interval}s)...")
        print(f"   Targets: {len(daemon._targets)}")
        print("   Press Ctrl+C to stop\n")
        try:
            daemon.start(interval=interval)
        except KeyboardInterrupt:
            daemon.stop()
            print("\n⏹️  Daemon stopped")




def _monitor_status(args):
    """Show current monitoring status."""
    from tokenade.core.monitoring.session_monitor import SessionMonitor, MonitorConfig

    config = MonitorConfig(
        sessions_dir=args.sessions_dir,
    )
    monitor = SessionMonitor(config)

    # Scan for sessions
    if args.sessions_dir:
        registered = monitor.scan_sessions_dir()
        if registered:
            print(f"\n📂 Found {len(registered)} sessions in {args.sessions_dir}")
        else:
            print(f"\n📂 No sessions found in {args.sessions_dir}")
            return
    elif args.session:
        sid = monitor.register_session_file(args.session)
        if not sid:
            print(f"❌ Failed to load session: {args.session}")
            return
    else:
        print("❌ Specify --sessions-dir or --session")
        return

    # Print status
    print("\n" + "=" * 80)
    print("TOKENADE - Session Monitor Status")
    print("=" * 80)

    for status in monitor.get_all_statuses():
        health_bar = _health_bar(status.health_score)
        print(f"\n  📋 {status.site_name} ({status.session_id})")
        print(f"     Health: {health_bar} {status.health_score}%")
        print(f"     Cookies: {status.cookie_count} total "
              f"({status.healthy_cookies} ok, {status.warning_cookies} warn, {status.expired_cookies} expired)")
        if status.issues:
            print(f"     Issues: {len(status.issues)}")
        if status.recommendations:
            print(f"     Recommendations: {len(status.recommendations)}")
        if status.source_path:
            print(f"     Source: {status.source_path}")

    summary = monitor.get_summary()
    print(f"\n{'=' * 80}")
    print(f"Total: {summary['total_sessions']} sessions, "
          f"{summary['total_cookies']} cookies, "
          f"Overall health: {summary['overall_health']}%")
    print(f"{'=' * 80}\n")


def _monitor_start(args):
    """Start background monitoring daemon."""
    from tokenade.core.monitoring.session_monitor import SessionMonitor, MonitorConfig

    config = MonitorConfig(
        check_interval=args.interval,
        sessions_dir=args.sessions_dir,
        auto_refresh=args.auto_refresh,
    )

    monitor = SessionMonitor(config)

    # Register sessions
    if args.sessions_dir:
        registered = monitor.scan_sessions_dir()
        print(f"📂 Monitoring {len(registered)} sessions from {args.sessions_dir}")
    elif args.session:
        sid = monitor.register_session_file(args.session)
        if not sid:
            print(f"❌ Failed to load session: {args.session}")
            return
        print(f"📂 Monitoring session: {args.session}")
    else:
        print("❌ Specify --sessions-dir or --session")
        return

    # Set up logging callback
    def on_health_change(session_id, status):
        print(f"  ⚠️  {session_id}: health changed to {status.health_score}%")

    monitor.on_health_change(on_health_change)

    # Start monitoring
    print(f"🔄 Starting monitor (interval: {args.interval}s)")
    print("   Press Ctrl+C to stop\n")

    monitor.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        monitor.stop()
        print("\n⏹️  Monitor stopped")


def _monitor_stop(args):
    """Stop a running monitor (by PID file)."""
    pid_file = Path("~/.tokenade/monitor.pid").expanduser()
    if not pid_file.exists():
        print("❌ No monitor process found (no PID file)")
        return

    try:
        pid = int(pid_file.read_text().strip())
        import os
        os.kill(pid, signal.SIGTERM)
        print(f"✅ Sent stop signal to monitor (PID: {pid})")
        pid_file.unlink(missing_ok=True)
    except (ProcessLookupError, ValueError) as e:
        print(f"❌ Failed to stop monitor: {e}")
        pid_file.unlink(missing_ok=True)


def _monitor_history(args):
    """Show monitor event history."""
    from tokenade.core.monitoring.session_monitor import SessionMonitor, MonitorConfig

    config = MonitorConfig(sessions_dir=args.sessions_dir)
    monitor = SessionMonitor(config)

    if args.sessions_dir:
        monitor.scan_sessions_dir()

    events = monitor.get_event_history(limit=args.limit)

    if not events:
        print("📜 No monitor events recorded")
        return

    print("\n" + "=" * 80)
    print("TOKENADE - Monitor Event History")
    print("=" * 80)

    for event in events:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(event["timestamp"]))
        print(f"\n  [{ts}] {event['event_type']}")
        print(f"    Session: {event['session_id']}")
        print(f"    {event['message']}")
        if event.get("health_score") is not None:
            print(f"    Health: {event['health_score']}%")

    print(f"\n{'=' * 80}")
    print(f"Total: {len(events)} events")
    print(f"{'=' * 80}\n")


def _monitor_predict(args):
    """Predict session expiry based on health trend."""
    from tokenade.core.monitoring.session_monitor import SessionMonitor, MonitorConfig

    config = MonitorConfig(sessions_dir=args.sessions_dir)
    monitor = SessionMonitor(config)

    if args.sessions_dir:
        monitor.scan_sessions_dir()
    elif args.session:
        monitor.register_session_file(args.session)

    for status in monitor.get_all_statuses():
        predicted = monitor.predict_expiry(status.session_id)
        if predicted:
            remaining = predicted - time.time()
            if remaining > 0:
                hours = remaining / 3600
                print(f"  ⏰ {status.session_id}: predicted unhealthy in {hours:.1f} hours")
            else:
                print(f"  ⚠️  {status.session_id}: predicted already unhealthy")
        else:
            print(f"  ℹ️  {status.session_id}: insufficient data for prediction")


def _health_bar(score: float, width: int = 20) -> str:
    """Create a visual health bar."""
    filled = int(score / 100 * width)
    empty = width - filled
    if score >= 80:
        char = "█"
    elif score >= 50:
        char = "▓"
    else:
        char = "░"
    return f"[{char * filled}{'.' * empty}]"




def _analytics_report(args, analytics):
    """Show usage report."""
    report = analytics.get_usage_report(days=args.days)

    if args.json_output:
        print(json.dumps(report, indent=2))
        return

    print("\n" + "=" * 70)
    print("TOKENADE - Session Analytics Report")
    print("=" * 70)
    print(f"\n📅 Period: Last {args.days} days")
    print(f"📊 Total events: {report['total_events']}")
    print(f"📋 Sessions tracked: {report['total_sessions']}")

    if report["events_by_type"]:
        print("\n📈 Events by type:")
        for event_type, count in sorted(
            report["events_by_type"].items(), key=lambda x: -x[1]
        ):
            print(f"   {event_type}: {count}")

    if report["top_sessions"]:
        print("\n🏆 Top sessions:")
        for item in report["top_sessions"]:
            print(f"   {item['session_id']}: {item['event_count']} events")

    if report["daily_activity"]:
        print("\n📅 Daily activity:")
        for day, count in sorted(report["daily_activity"].items()):
            bar = "█" * min(count, 30)
            print(f"   {day}: {bar} ({count})")

    if report["avg_session_lifetime_hours"] > 0:
        print(f"\n⏱️  Avg session lifetime: {report['avg_session_lifetime_hours']} hours")

    print(f"\n{'=' * 70}\n")


def _analytics_session(args, analytics):
    """Show analytics for a specific session."""
    data = analytics.get_session_analytics(args.session_id)

    if data["total_events"] == 0:
        print(f"📊 No analytics data for session: {args.session_id}")
        return

    print("\n" + "=" * 60)
    print(f"TOKENADE - Session Analytics: {args.session_id}")
    print("=" * 60)
    print(f"\n📊 Total events: {data['total_events']}")
    print(f"⏱️  Lifespan: {data['lifespan_hours']} hours")

    first = time.strftime("%Y-%m-%d %H:%M", time.localtime(data["first_seen"]))
    last = time.strftime("%Y-%m-%d %H:%M", time.localtime(data["last_seen"]))
    print(f"📅 First seen: {first}")
    print(f"📅 Last seen: {last}")

    if data["events_by_type"]:
        print("\n📈 Events:")
        for event_type, count in sorted(
            data["events_by_type"].items(), key=lambda x: -x[1]
        ):
            print(f"   {event_type}: {count}")

    print(f"\n{'=' * 60}\n")


def _analytics_cleanup(args, analytics):
    """Remove old analytics data."""
    analytics.cleanup(max_age_days=args.max_age)
    print(f"✅ Cleaned up analytics data older than {args.max_age} days")


def cmd_launch(args):
    """Launch undetectable system browser with CDP."""
    import asyncio

    from tokenade.core.browser.undetectable import SystemBrowserLauncher
    from tokenade.core.browser.cdp_connection import CDPConnection, get_undetectable_stealth_script
    from tokenade.core.importer.session_packager import SessionPackager

    print("\n" + "=" * 80)
    print("TOKENADE - Undetectable Browser")
    print("=" * 80)

    launcher = SystemBrowserLauncher()

    # Find browser
    browser_path = launcher.find_browser(args.browser)
    if not browser_path:
        print(f"❌ {args.browser} not found. Install it or specify --browser-path")
        return

    print(f"\n🌐 Browser: {args.browser} ({browser_path})")
    print(f"🔌 CDP Port: {args.port}")
    print(f"👁️  Visible: {args.visible}")

    # Resolve upstream proxy
    upstream_proxy = _resolve_upstream_proxy(args)
    if upstream_proxy:
        print(f"🔀 Upstream proxy: {upstream_proxy}")

    try:
        # Check if browser is already running (profile will be locked)
        import subprocess as _sp
        _ps_cmd = ["pgrep", "-c", args.browser] if platform.system() != "Windows" else ["tasklist", "/fi", f"imagename eq {args.browser}.exe"]
        try:
            _running = _sp.run(_ps_cmd, capture_output=True, text=True, timeout=3)
            _is_running = False
            if platform.system() != "Windows" and _running.returncode == 0:
                _is_running = int(_running.stdout.strip()) > 0
            elif platform.system() == "Windows" and args.browser.lower() in _running.stdout.lower():
                _is_running = True
            if _is_running:
                print(f"   ⚠️  {args.browser} is already running. Profile is locked.")
                print(f"   Close all {args.browser} windows first, then retry.")
                print(f"   Or start {args.browser} with: {args.browser} --remote-debugging-port={args.port}")
                return
        except Exception:
            pass  # If we can't check, just try to launch

        # Copy real profile only when NO session file (cookies come from profile)
        # When session file IS provided, use fresh profile (session cookies are authoritative)
        profile_dir = args.profile_dir
        if not profile_dir and not args.session:
            real_dir = launcher._get_default_profile_dir(args.browser)
            if real_dir:
                import tempfile
                profile_dir = tempfile.mkdtemp(prefix=f"tokenade_{args.browser}_")
                print(f"   📁 Copying profile from: {real_dir}")
                if launcher._copy_profile(args.browser, profile_dir):
                    print(f"   ✅ Profile copied to: {profile_dir}")
                else:
                    print(f"   ⚠️  Profile copy failed, using fresh profile")

        browser = launcher.launch(
            browser=args.browser,
            visible=args.visible,
            port=args.port,
            profile_dir=profile_dir,
            extra_args=args.extra_args.split(",") if args.extra_args else [],
            upstream_proxy=upstream_proxy,
        )

        print(f"\n✅ Browser launched (PID: {browser.pid})")
        print(f"   CDP URL: {browser.cdp_url}")
        print(f"   Profile: {browser.profile_dir}")

        # Inject session if provided — session file is ALWAYS authoritative
        if args.session:
            print(f"\n📂 Loading session: {args.session}")
            print(f"   ⚠️  This session can only be active on ONE device at a time.")
            print(f"   Google DBSC binds cookies to hardware — Chrome-to-Chrome will fail.")
            print(f"   ✅ Works: Brave/FF → Edge/FF/Brave (no DBSC)")
            print(f"   ❌ Fails: Chrome → Chrome (DBSC on Windows)")
            print(f"   For multi-device: use 'tokenade proxy --host 0.0.0.0' instead.")

            session_path = args.session
            decrypt_password = getattr(args, 'decrypt_password', None)
            if decrypt_password:
                import tempfile
                try:
                    from tokenade.core.crypto.at_rest import load_encrypted
                    session = load_encrypted(session_path, password=decrypt_password)
                    # Write decrypted to temp file
                    temp_path = tempfile.mktemp(suffix='.tokenade')
                    with open(temp_path, 'w') as f:
                        json.dump(session, f)
                    session_path = temp_path
                    print(f"   🔓 Decrypted with password")
                except Exception as e:
                    print(f"❌ Decryption failed: {e}")
                    return

            packager = SessionPackager()
            session = packager.load(session_path)

            cookies = session.get("cookies", [])
            source_browser = session.get("source_device", {}).get("browser", "unknown")
            print(f"   Cookies: {len(cookies)} (from {source_browser})")

            if source_browser != "unknown" and source_browser != args.browser:
                print(f"   ⚠️  Cross-browser: {source_browser} → {args.browser}")
                print(f"   💡 For best results, export from same browser you'll use")

            # Connect via CDP and inject (use actual port from browser)
            actual_port = browser.port

            # Create new tab synchronously before entering async
            import urllib.request as _urllib_req
            try:
                _req = _urllib_req.Request(
                    f"http://127.0.0.1:{actual_port}/json/new?about:blank",
                    method='PUT'
                )
                with _urllib_req.urlopen(_req, timeout=5) as _resp:
                    _new_tab = json.loads(_resp.read().decode())
                _tab_ws_url = _new_tab.get("webSocketDebuggerUrl")
                _tab_id = _new_tab.get("id")
            except Exception as e:
                print(f"❌ Failed to create new tab: {e}")
                _tab_ws_url = None
                _tab_id = None

            async def inject():
                import websockets

                msg_id_counter = [0]

                async def cdp_cmd(ws, method, params=None):
                    msg_id_counter[0] += 1
                    current_id = msg_id_counter[0]
                    msg = {"id": current_id, "method": method}
                    if params:
                        msg["params"] = params
                    await ws.send(json.dumps(msg))
                    deadline = time.time() + 30
                    while time.time() < deadline:
                        try:
                            raw = await asyncio.wait_for(
                                ws.recv(),
                                timeout=min(5, deadline - time.time()),
                            )
                        except asyncio.TimeoutError:
                            continue
                        data = json.loads(raw)
                        if "id" in data and data["id"] == current_id:
                            if "error" in data:
                                raise RuntimeError(data["error"].get("message", "CDP error"))
                            return data.get("result", {})
                    raise RuntimeError(f"CDP timeout: {method}")

                if not _tab_ws_url:
                    print("❌ Failed to create tab")
                    return

                print(f"   Tab: {_tab_id}")

                # Step 2: Connect to the new tab's WebSocket
                print("   Connecting to tab WS...")
                tab_ws = await websockets.connect(
                    _tab_ws_url,
                    max_size=10 * 1024 * 1024,
                    ping_interval=30,
                    ping_timeout=10,
                )
                print("   Connected.")

                # Step 3: Inject stealth FIRST (before page load)
                print("   Injecting stealth script...", flush=True)
                stealth_script = get_undetectable_stealth_script()

                await cdp_cmd(tab_ws, "Page.enable")
                await cdp_cmd(tab_ws, "Page.addScriptToEvaluateOnNewDocument", {"source": stealth_script})

                # Step 4: Inject cookies
                print(f"   Injecting {len(cookies)} cookies...", flush=True)
                cdp_cookies = []
                for cookie in cookies:
                    cdp_cookie = {
                        "name": cookie.get("name", ""),
                        "value": cookie.get("value", ""),
                        "domain": cookie.get("domain", ""),
                        "path": cookie.get("path", "/"),
                    }
                    if cookie.get("secure"):
                        cdp_cookie["secure"] = True
                    if cookie.get("httpOnly"):
                        cdp_cookie["httpOnly"] = True
                    if cookie.get("sameSite"):
                        same_site = cookie["sameSite"]
                        if same_site in ("Strict", "Lax", "None"):
                            cdp_cookie["sameSite"] = same_site
                    expires = cookie.get("expires", 0)
                    if expires and int(expires) > 0:
                        exp = int(expires)
                        if exp > 1262304000000:
                            exp = exp // 1000
                        cdp_cookie["expires"] = exp
                    # CDP requires secure=true when sameSite=None
                    if cdp_cookie.get("sameSite") == "None" and not cdp_cookie.get("secure"):
                        cdp_cookie["secure"] = True
                    cdp_cookies.append(cdp_cookie)

                await cdp_cmd(tab_ws, "Network.enable")
                await cdp_cmd(tab_ws, "Network.setCookies", {"cookies": cdp_cookies})

                # Step 5: Navigate to site
                if args.url:
                    print(f"   Navigating to: {args.url}", flush=True)
                    await cdp_cmd(tab_ws, "Page.navigate", {"url": args.url})

                    # Wait for page load
                    await asyncio.sleep(5)

                    # Step 6: Inject localStorage + sessionStorage (after navigation, on correct origin)
                    session_data = session.get("session_storage", {})
                    local_data = session.get("local_storage", {})

                    if local_data:
                        print(f"   Injecting {len(local_data)} localStorage entries...", flush=True)
                        ls_json = json.dumps(local_data)
                        await cdp_cmd(tab_ws, "Runtime.evaluate", {
                            "expression": f"(function(d){{Object.entries(d).forEach(function(e){{localStorage.setItem(e[0],e[1])}})}})({ls_json})",
                            "returnByValue": True,
                        })

                    if session_data:
                        print(f"   Injecting {len(session_data)} sessionStorage entries...", flush=True)
                        ss_json = json.dumps(session_data)
                        await cdp_cmd(tab_ws, "Runtime.evaluate", {
                            "expression": f"(function(d){{Object.entries(d).forEach(function(e){{sessionStorage.setItem(e[0],e[1])}})}})({ss_json})",
                            "returnByValue": True,
                        })

                    # Step 7: Re-navigate with full session state
                    if local_data or session_data:
                        print(f"   Re-navigating with full session state...", flush=True)
                        await cdp_cmd(tab_ws, "Page.navigate", {"url": args.url})
                        await asyncio.sleep(5)

                    # Step 8: If Google, also try accounts.google.com for auth state
                    if args.url and "google.com" in args.url:
                        print(f"   Injecting Google auth state on accounts.google.com...", flush=True)
                        await cdp_cmd(tab_ws, "Page.navigate", {"url": "https://accounts.google.com"})
                        await asyncio.sleep(3)
                        if local_data:
                            await cdp_cmd(tab_ws, "Runtime.evaluate", {
                                "expression": f"(function(d){{Object.entries(d).forEach(function(e){{localStorage.setItem(e[0],e[1])}})}})({ls_json})",
                                "returnByValue": True,
                            })
                        # Navigate back to target
                        await cdp_cmd(tab_ws, "Page.navigate", {"url": args.url})
                        await asyncio.sleep(5)

                    # Get page info
                    title_result = await cdp_cmd(
                        tab_ws, "Runtime.evaluate",
                        {"expression": "document.title", "returnByValue": True},
                    )
                    title = title_result.get("result", {}).get("value", "")

                    url_result = await cdp_cmd(
                        tab_ws, "Runtime.evaluate",
                        {"expression": "window.location.href", "returnByValue": True},
                    )
                    url = url_result.get("result", {}).get("value", "")

                    print(f"\n   📄 Page: {title}")
                    print(f"   🔗 URL: {url}")

                # Warn about session sharing
                print(f"\n   ⚠️  SESSION USAGE RULES:")
                print(f"   • This session can only be active on ONE device at a time")
                print(f"   • Google DBSC binds cookies to hardware — cross-device use will fail")
                print(f"   • For multi-device: use 'tokenade proxy --host 0.0.0.0' instead")
                print(f"   • To migrate: close browser here, re-export from the active device")

                await tab_ws.close()

            asyncio.run(inject())

        elif args.url:
            # Just navigate to URL — same PUT /json/new approach
            actual_port = browser.port

            async def navigate_only():
                import urllib.request
                import websockets

                msg_id_counter = [0]

                async def cdp_cmd(ws, method, params=None):
                    msg_id_counter[0] += 1
                    current_id = msg_id_counter[0]
                    msg = {"id": current_id, "method": method}
                    if params:
                        msg["params"] = params
                    await ws.send(json.dumps(msg))
                    deadline = time.time() + 30
                    while time.time() < deadline:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=min(5, deadline - time.time()))
                        except asyncio.TimeoutError:
                            continue
                        data = json.loads(raw)
                        if "id" in data and data["id"] == current_id:
                            return data.get("result", {})
                    return {}

                # Create new tab
                def _create_tab():
                    req = urllib.request.Request(
                        f"http://127.0.0.1:{actual_port}/json/new?about:blank",
                        method='PUT'
                    )
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        return json.loads(resp.read().decode())

                try:
                    new_tab = await asyncio.to_thread(_create_tab)
                    tab_ws_url = new_tab.get("webSocketDebuggerUrl")
                except Exception as e:
                    print(f"❌ Failed to create tab: {e}")
                    return

                tab_ws = await websockets.connect(
                    tab_ws_url, max_size=10 * 1024 * 1024,
                    ping_interval=30, ping_timeout=10,
                )

                # Inject stealth
                stealth_script = get_undetectable_stealth_script()
                await cdp_cmd(tab_ws, "Page.enable")
                await cdp_cmd(tab_ws, "Page.addScriptToEvaluateOnNewDocument", {"source": stealth_script})

                # Navigate
                print(f"\n   Navigating to: {args.url}")
                await cdp_cmd(tab_ws, "Page.navigate", {"url": args.url})
                await asyncio.sleep(4)

                title_result = await cdp_cmd(tab_ws, "Runtime.evaluate", {"expression": "document.title", "returnByValue": True})
                title = title_result.get("result", {}).get("value", "")

                url_result = await cdp_cmd(tab_ws, "Runtime.evaluate", {"expression": "window.location.href", "returnByValue": True})
                url = url_result.get("result", {}).get("value", "")

                print(f"\n   📄 Page: {title}")
                print(f"   🔗 URL: {url}")

                await tab_ws.close()

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(navigate_only())
            finally:
                loop.close()

        print(f"\n{'=' * 80}")
        print("Browser is running. You can:")
        print(f"  1. Open http://127.0.0.1:{browser.port} in another browser")
        print(f"  2. Use Chrome DevTools to connect to ws://127.0.0.1:{browser.port}")
        print("  3. Or let it run and control via CDP WebSocket")
        print("\nPress Ctrl+C to close the browser")
        print(f"{'=' * 80}\n")

        # Keep browser running
        try:
            browser.process.wait()
        except KeyboardInterrupt:
            print("\n⏹️  Closing browser...")
            browser.close()

    except RuntimeError as e:
        print(f"\n❌ {e}")
    except Exception as e:
        logger.error(f"Launch failed: {e}", exc_info=True)
        print(f"\n❌ Launch failed: {e}")


def cmd_validate_session(args):
    """Validate session files for CI/CD health gates."""
    from tokenade.core.refresh.session_validator import SessionValidator, create_ci_validation_rules
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
        print("❌ Specify --session or --sessions-dir")
        sys.exit(1)


def cmd_encrypted_refresh(args):
    """Refresh encrypted session files."""
    from tokenade.core.refresh.encrypted_refresh import EncryptedRefreshPipeline, batch_encrypted_refresh

    print("\n" + "=" * 80)
    print("TOKENADE - Encrypted Session Refresh")
    print("=" * 80)

    if args.sessions_dir:
        print(f"\n📂 Batch refreshing: {args.sessions_dir}")
        results = batch_encrypted_refresh(
            sessions_dir=args.sessions_dir,
            password=args.password,
            key_file=args.key_file,
            source_browser=args.source_browser,
            force=args.force,
        )

        for name, result in results.items():
            status = "✅" if result.success else "❌"
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
            print(f"\n✅ Refresh successful")
            print(f"   Method: {result.method}")
            print(f"   Encrypted: {result.was_encrypted}")
            print(f"   Duration: {result.duration_ms:.0f}ms")
        else:
            print(f"\n❌ Refresh failed")
            if result.error:
                print(f"   Error: {result.error}")

    else:
        print("❌ Specify --session or --sessions-dir")


def cmd_refresh_oauth(args):
    """Refresh OAuth tokens using stored refresh token."""
    print("\n" + "=" * 80)
    print("TOKENADE - OAuth Token Refresh")
    print("=" * 80)

    session_file = Path(args.session)
    if not session_file.exists():
        print(f"❌ Session file not found: {args.session}")
        return

    print(f"\n📂 Session: {args.session}")

    try:
        from tokenade.core.refresh.oauth_refresh import SessionOAuthManager

        manager = SessionOAuthManager(str(session_file))

        status = manager.get_status()
        print(f"🌐 Site: {status['site_name']}")
        print(f"🔑 Has OAuth config: {status['has_oauth_config']}")
        print(f"🔄 Has refresh token: {status['has_refresh_token']}")
        print(f"🎟️  Has access token: {status['has_access_token']}")

        if status["access_token_expired"]:
            print("⚠️  Access token is expired")
        elif status["expires_in"] is not None:
            print(f"⏰ Expires in: {status['expires_in']}s")

        if not manager.has_oauth_config():
            print("\n❌ No OAuth config in session")
            print("   Run: tokenade oauth-config --session <file> --client-id <id> --token-endpoint <url>")
            return

        if not manager.get_refresh_token():
            print("\n❌ No refresh token in session")
            print("   Re-export session with OAuth tokens")
            return

        print("\n🔄 Refreshing token...")
        result = manager.refresh()

        if result.success:
            print("\n✅ Token refreshed successfully")
            print(f"   New access token: {result.tokens.access_token[:20]}...")
            if result.tokens.expires_in:
                print(f"   Expires in: {result.tokens.expires_in}s")
            print(f"   Duration: {result.duration_ms:.0f}ms")
        else:
            print("\n❌ Token refresh failed")
            if result.error:
                print(f"   Error: {result.error}")

    except Exception as e:
        logger.error(f"OAuth refresh failed: {e}", exc_info=True)
        print("❌ Refresh failed — check OAuth configuration")


def cmd_oauth_config(args):
    """Configure OAuth settings for a session."""
    from tokenade.core.refresh.oauth_refresh import SessionOAuthManager, OAuthConfig

    session_file = Path(args.session)
    if not session_file.exists():
        print(f"❌ Session file not found: {args.session}")
        return

    manager = SessionOAuthManager(str(session_file))

    if args.show:
        config = manager.get_oauth_config()
        if config:
            print("\n" + "=" * 60)
            print("OAuth Configuration")
            print("=" * 60)
            print(f"  Token Endpoint: {config.token_endpoint}")
            print(f"  Client ID: {config.client_id[:20]}..." if len(config.client_id) > 20 else f"  Client ID: {config.client_id}")
            print(f"  Client Secret: {'*' * 10 if config.client_secret else '(not set)'}")
            print(f"  Scopes: {', '.join(config.scopes)}")
            print(f"  Grant Type: {config.grant_type}")
            print(f"{'=' * 60}\n")
        else:
            print("No OAuth config set for this session")
        return

    if not args.client_id or not args.token_endpoint:
        print("❌ --client-id and --token-endpoint are required")
        return

    config = OAuthConfig(
        token_endpoint=args.token_endpoint,
        client_id=args.client_id,
        client_secret=args.client_secret or "",
        scopes=args.scopes.split(",") if args.scopes else ["openid", "profile", "email"],
    )

    manager.set_oauth_config(config)
    manager.save()

    print(f"\n✅ OAuth config saved for: {args.session}")
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
    print(f"\n📂 Found {len(sessions)} sessions in {args.sessions_dir}")

    if not sessions:
        print("   No .tokenade files found")
        return

    for s in sessions:
        print(f"   • {s.name}")

    if not args.yes:
        response = input("\n🔄 Refresh all sessions? [y/N]: ").strip().lower()
        if response != "y":
            print("Cancelled")
            return

    print(f"\n🔄 Refreshing with {args.max_workers} workers...")
    report = batch.refresh_all(force=args.force)

    print("\n" + report.summary())
















def _run_post_refresh_plugins(loader, session):
    """Run post-refresh plugins (webhooks, notifications, etc.)."""
    refreshers = loader.list_refreshers()
    for name, refresher in refreshers.items():
        try:
            if hasattr(refresher, "_send_webhook") or (hasattr(refresher, "can_refresh") and refresher.can_refresh(session)):
                # Only run plugins that are pass-through notifiers (not the main refresher)
                if hasattr(refresher, "_send_webhook"):
                    refresher.refresh(session, {})
        except Exception as e:
            logger.warning(f"Post-refresh plugin {name} failed: {e}")


def cmd_refresh_browser(args):
    """Refresh session by launching undetectable browser, injecting cookies, navigating, and extracting fresh cookies."""
    from tokenade.core.importer.session_packager import SessionPackager
    from tokenade.core.browser.undetectable import SystemBrowserLauncher

    print("\n" + "=" * 80)
    print("TOKENADE - Cookie-Based Session Refresh")
    print("=" * 80)

    # 1. Load existing session
    session_file = Path(args.session)
    if not session_file.exists():
        print(f"❌ Session file not found: {args.session}")
        return

    packager = SessionPackager()
    try:
        session = packager.load(str(session_file))
    except Exception as e:
        print(f"❌ Failed to load session: {e}")
        return

    cookies = session.get("cookies", [])
    site_name = session.get("site_name", "unknown")
    source_browser = session.get("source_device", {}).get("browser", "unknown")

    if not cookies:
        print("❌ No cookies in session file")
        return

    # 2. Try plugin refresh first (if --plugin specified)
    plugin_name = getattr(args, "plugin", None)
    plugin_args_list = getattr(args, "plugin_arg", [])
    output = getattr(args, "output", None)

    if plugin_name:
        plugin_creds = {}
        for key, value in plugin_args_list:
            plugin_creds[key] = value

        try:
            from tokenade.core.integration.plugin_loader import PluginLoader
            loader = PluginLoader()
            loader.load_all()

            refresher = loader.get_refresher(plugin_name)
            if not refresher:
                print(f"⚠️  Plugin not found: {plugin_name}. Proceeding with browser refresh.")
            elif not refresher.can_refresh(session):
                print(f"⚠️  Plugin '{plugin_name}' cannot refresh this session. Proceeding with browser refresh.")
            else:
                print(f"\n🔌 Using plugin: {plugin_name} v{refresher.version}")

                # Collect credentials from plugin args if not provided
                if hasattr(refresher, "get_credentials_args"):
                    for cred_arg in refresher.get_credentials_args():
                        arg_name = cred_arg["name"].lstrip("-").replace("-", "_")
                        if arg_name not in plugin_creds and cred_arg.get("required"):
                            print(f"❌ Missing required plugin credential: {cred_arg['name']}")
                            print(f"   Use: --plugin-arg {arg_name} <value>")
                            return

                try:
                    session = refresher.refresh(session, plugin_creds)

                    # Save updated session
                    save_path = output or str(session_file)
                    packager.save(session, save_path)
                    print(f"✅ Session refreshed via plugin: {save_path}")

                    # Run post-refresh plugins (webhooks, etc.)
                    _run_post_refresh_plugins(loader, session)

                    return
                except Exception as e:
                    print(f"⚠️  Plugin refresh failed: {e}")
                    print("   Falling back to browser-based refresh...")
        except ImportError:
            print(f"⚠️  Plugin system not available. Proceeding with browser refresh.")
        except Exception as e:
            print(f"⚠️  Plugin error: {e}. Proceeding with browser refresh.")

    # Determine target URL
    target_url = args.url
    if not target_url:
        # Try to infer from cookies
        domains = {c.get("domain", "").lstrip(".") for c in cookies}
        if "google.com" in domains or "gmail.com" in domains:
            target_url = "https://mail.google.com"
        elif "github.com" in domains:
            target_url = "https://github.com"
        elif "twitter.com" in domains or "x.com" in domains:
            target_url = "https://x.com"
        elif "linkedin.com" in domains:
            target_url = "https://www.linkedin.com"
        else:
            # Use the first non-empty domain
            for d in sorted(domains):
                if d and "." in d:
                    target_url = f"https://{d}"
                    break
        if not target_url:
            print("❌ Could not determine target URL. Use --url to specify.")
            return

    print(f"\n📂 Session: {args.session}")
    print(f"   Site: {site_name}")
    print(f"   Cookies: {len(cookies)}")
    print(f"   Source: {source_browser}")
    print(f"\n🌐 Target: {target_url}")
    print(f"   Browser: {args.browser}")

    # 2. Check if browser is already running
    import subprocess as _sp
    _ps_cmd = ["pgrep", "-c", args.browser] if platform.system() != "Windows" else ["tasklist", "/fi", f"imagename eq {args.browser}.exe"]
    try:
        _running = _sp.run(_ps_cmd, capture_output=True, text=True, timeout=3)
        _is_running = False
        if platform.system() != "Windows" and _running.returncode == 0:
            _is_running = int(_running.stdout.strip()) > 0
        elif platform.system() == "Windows" and args.browser.lower() in _running.stdout.lower():
            _is_running = True
        if _is_running:
            print(f"\n   ⚠️  {args.browser} is already running. Close it first or use a different port.")
            return
    except Exception:
        pass

    # 3. Launch undetectable browser (headless for refresh)
    launcher = SystemBrowserLauncher()
    port = args.port
    browser = None

    # Resolve upstream proxy
    upstream_proxy = _resolve_upstream_proxy(args)
    if upstream_proxy:
        print(f"   🔀 Upstream proxy: {upstream_proxy}")

    try:
        print(f"\n🚀 Launching {args.browser} (headless={args.headless})...")
        browser = launcher.launch(
            browser=args.browser,
            visible=not args.headless,
            port=port,
            upstream_proxy=upstream_proxy,
        )
        print(f"   ✅ Browser ready (PID: {browser.pid}, CDP: {browser.cdp_url})")

        # 4. Inject cookies via CDP
        import asyncio
        import websockets

        # Create new tab
        import urllib.request as _urllib_req
        _req = _urllib_req.Request(
            f"http://127.0.0.1:{port}/json/new?about:blank",
            method="PUT",
        )
        _resp = _urllib_req.urlopen(_req, timeout=10)
        _tab_info = json.loads(_resp.read().decode())
        _tab_id = _tab_info.get("id")
        _tab_ws_url = _tab_info.get("webSocketDebuggerUrl")

        if not _tab_ws_url:
            print("❌ Failed to create tab")
            return

        async def refresh():
            msg_id_counter = [0]

            async def cdp_cmd(ws, method, params=None):
                msg_id_counter[0] += 1
                current_id = msg_id_counter[0]
                msg = {"id": current_id, "method": method}
                if params:
                    msg["params"] = params
                await ws.send(json.dumps(msg))
                deadline = time.time() + 30
                while time.time() < deadline:
                    try:
                        raw = await asyncio.wait_for(
                            ws.recv(),
                            timeout=min(5, deadline - time.time()),
                        )
                    except asyncio.TimeoutError:
                        continue
                    data = json.loads(raw)
                    if "id" in data and data["id"] == current_id:
                        if "error" in data:
                            raise RuntimeError(data["error"].get("message", "CDP error"))
                        return data.get("result", {})
                raise RuntimeError(f"CDP timeout: {method}")

            tab_ws = await websockets.connect(
                _tab_ws_url,
                max_size=10 * 1024 * 1024,
                ping_interval=30,
                ping_timeout=10,
            )

            # Inject stealth
            from tokenade.core.browser.cdp_connection import get_undetectable_stealth_script
            stealth_script = get_undetectable_stealth_script()
            await cdp_cmd(tab_ws, "Page.enable")
            await cdp_cmd(tab_ws, "Page.addScriptToEvaluateOnNewDocument", {"source": stealth_script})

            # Inject cookies
            print(f"\n🍪 Injecting {len(cookies)} cookies...")
            cdp_cookies = []
            for cookie in cookies:
                cdp_cookie = {
                    "name": cookie.get("name", ""),
                    "value": cookie.get("value", ""),
                    "domain": cookie.get("domain", ""),
                    "path": cookie.get("path", "/"),
                }
                if cookie.get("secure"):
                    cdp_cookie["secure"] = True
                if cookie.get("httpOnly"):
                    cdp_cookie["httpOnly"] = True
                if cookie.get("sameSite"):
                    same_site = cookie["sameSite"]
                    if same_site in ("Strict", "Lax", "None"):
                        cdp_cookie["sameSite"] = same_site
                expires = cookie.get("expires", 0)
                if expires and int(expires) > 0:
                    exp = int(expires)
                    if exp > 1262304000000:
                        exp = exp // 1000
                    cdp_cookie["expires"] = exp
                if cdp_cookie.get("sameSite") == "None" and not cdp_cookie.get("secure"):
                    cdp_cookie["secure"] = True
                cdp_cookies.append(cdp_cookie)

            await cdp_cmd(tab_ws, "Network.enable")
            await cdp_cmd(tab_ws, "Network.setCookies", {"cookies": cdp_cookies})
            print(f"   ✅ Cookies injected")

            # Navigate to target
            print(f"\n🌐 Navigating to: {target_url}")
            await cdp_cmd(tab_ws, "Page.navigate", {"url": target_url})

            # Wait for page load and "warm up" the session
            wait_time = args.wait
            print(f"   ⏳ Waiting {wait_time}s for session refresh...")
            await asyncio.sleep(wait_time)

            # Get page info
            title_result = await cdp_cmd(
                tab_ws, "Runtime.evaluate",
                {"expression": "document.title", "returnByValue": True},
            )
            title = title_result.get("result", {}).get("value", "")
            print(f"   📄 Page: {title}")

            # Extract fresh cookies
            print(f"\n🔄 Extracting refreshed cookies...")
            from tokenade.cli.session import _extract_via_cdp
            session_state = _extract_via_cdp(port, domain_filter=None)
            fresh_cookies = session_state["cookies"]
            fresh_ls = session_state.get("local_storage", {})
            fresh_ss = session_state.get("session_storage", {})

            await tab_ws.close()
            return fresh_cookies, fresh_ls, fresh_ss

        fresh_cookies, fresh_ls, fresh_ss = asyncio.run(refresh())

        if not fresh_cookies:
            print("\n❌ No cookies extracted after refresh. Session may be expired.")
            return

        print(f"\n   ✅ Extracted {len(fresh_cookies)} fresh cookies")
        if fresh_ls:
            print(f"   ✅ Extracted {len(fresh_ls)} localStorage entries")
        if fresh_ss:
            print(f"   ✅ Extracted {len(fresh_ss)} sessionStorage entries")

        # 5. Compare old vs new
        old_names = {c.get("name") for c in cookies}
        new_names = {c.get("name") for c in fresh_cookies}
        added = new_names - old_names
        removed = old_names - new_names
        kept = old_names & new_names

        print(f"\n📊 Cookie changes:")
        print(f"   Kept: {len(kept)}")
        if added:
            print(f"   Added: {len(added)} ({', '.join(sorted(added)[:5])}{'...' if len(added) > 5 else ''})")
        if removed:
            print(f"   Removed: {len(removed)} ({', '.join(sorted(removed)[:5])}{'...' if len(removed) > 5 else ''})")

        # 6. Update session file
        session["cookies"] = fresh_cookies
        if fresh_ls:
            session["local_storage"] = fresh_ls
        if fresh_ss:
            session["session_storage"] = fresh_ss

        # Update metadata
        if "metadata" not in session:
            session["metadata"] = {}
        session["metadata"]["cookie_count"] = len(fresh_cookies)
        session["metadata"]["local_storage_count"] = len(fresh_ls) if fresh_ls else 0
        session["metadata"]["session_storage_count"] = len(fresh_ss) if fresh_ss else 0

        from datetime import datetime, timezone
        session["metadata"]["last_refreshed"] = datetime.now(timezone.utc).isoformat()

        # Save
        output = args.output or str(session_file)
        packager.save(session, output)
        print(f"\n💾 Session saved: {output}")
        print(f"   Cookies: {len(fresh_cookies)}")
        if fresh_ls:
            print(f"   localStorage: {len(fresh_ls)} entries")
        if fresh_ss:
            print(f"   sessionStorage: {len(fresh_ss)} entries")

        print(f"\n✅ Session refreshed successfully!")

    except Exception as e:
        print(f"\n❌ Refresh failed: {e}")
        logger.error(f"Refresh failed: {e}", exc_info=True)
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass


def cmd_accounts(args):
    """Multi-account orchestration — list, status, refresh multiple sessions."""
    from tokenade.core.importer.session_manager import SessionManager

    sessions_dir = args.sessions_dir or "."
    manager = SessionManager(sessions_dir)

    subcommand = args.accounts_action

    if subcommand == "list":
        _accounts_list(manager, args)
    elif subcommand == "status":
        _accounts_status(manager, args)
    elif subcommand == "refresh":
        _accounts_refresh(manager, args)
    else:
        print(f"❌ Unknown action: {subcommand}")
        print("   Use: list, status, or refresh")


def _accounts_list(manager, args):
    """List all session files with metadata."""
    sessions = manager.list_sessions()

    if not sessions:
        print(f"\n📂 No .tokenade files found in {manager.sessions_dir}")
        return

    # Filter by site if specified
    if args.site:
        sessions = [s for s in sessions if args.site.lower() in s.site_name.lower()]

    # Filter by browser if specified
    if args.browser:
        sessions = [s for s in sessions if s.source_browser == args.browser]

    print(f"\n{'=' * 80}")
    print(f"TOKENADE - Accounts ({len(sessions)} sessions)")
    print(f"{'=' * 80}")

    if not sessions:
        print("   No matching sessions found")
        return

    # Print table
    print(f"\n{'Site':<15} {'Cookies':<10} {'Browser':<12} {'Size':<10} {'Path'}")
    print(f"{'-' * 15} {'-' * 10} {'-' * 12} {'-' * 10} {'-' * 30}")

    total_cookies = 0
    for s in sessions:
        size_kb = s.file_size / 1024
        browser = s.source_browser or "unknown"
        path_display = Path(s.path).name
        if len(path_display) > 35:
            path_display = "..." + path_display[-32:]
        print(f"{s.site_name:<15} {s.cookie_count:<10} {browser:<12} {size_kb:>7.1f}KB  {path_display}")
        total_cookies += s.cookie_count

    print(f"\n   Total: {len(sessions)} sessions, {total_cookies} cookies")

    # Show unique sites
    sites = {s.site_name for s in sessions}
    if len(sites) > 1:
        print(f"   Sites: {', '.join(sorted(sites))}")

    # Show unique browsers
    browsers = {s.source_browser for s in sessions if s.source_browser}
    if len(browsers) > 1:
        print(f"   Browsers: {', '.join(sorted(browsers))}")


def _accounts_status(manager, args):
    """Show health/status of all sessions."""
    sessions = manager.list_sessions()

    if not sessions:
        print(f"\n📂 No .tokenade files found in {manager.sessions_dir}")
        return

    if args.site:
        sessions = [s for s in sessions if args.site.lower() in s.site_name.lower()]

    print(f"\n{'=' * 80}")
    print(f"TOKENADE - Account Status ({len(sessions)} sessions)")
    print(f"{'=' * 80}")

    from tokenade.core.importer.session_packager import SessionPackager
    packager = SessionPackager()

    print(f"\n{'Site':<15} {'Cookies':<10} {'Auth':<12} {'Critical':<10} {'Last Refreshed':<20} {'Status'}")
    print(f"{'-' * 15} {'-' * 10} {'-' * 12} {'-' * 10} {'-' * 20} {'-' * 10}")

    healthy = 0
    expiring = 0
    expired = 0

    for s in sessions:
        try:
            session = packager.load(s.path)
            cookies = session.get("cookies", [])
            auth_status = session.get("auth_status", "unknown")
            critical = session.get("metadata", {}).get("critical_cookie_count", 0)
            last_refreshed = session.get("metadata", {}).get("last_refreshed", "never")

            if last_refreshed and last_refreshed != "never":
                # Parse ISO timestamp
                try:
                    from datetime import datetime, timezone
                    dt = datetime.fromisoformat(last_refreshed.replace("Z", "+00:00"))
                    age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
                    if age_hours < 1:
                        last_display = f"{int(age_hours * 60)}m ago"
                        status = "🟢 FRESH"
                        healthy += 1
                    elif age_hours < 24:
                        last_display = f"{int(age_hours)}h ago"
                        status = "🟡 OK"
                        healthy += 1
                    elif age_hours < 72:
                        last_display = f"{int(age_hours / 24)}d ago"
                        status = "🟠 STALE"
                        expiring += 1
                    else:
                        last_display = f"{int(age_hours / 24)}d ago"
                        status = "🔴 OLD"
                        expired += 1
                except (ValueError, TypeError):
                    last_display = last_refreshed
                    status = "❓ UNKNOWN"
            else:
                last_display = "never"
                status = "⚪ UNUSED"

            print(f"{s.site_name:<15} {len(cookies):<10} {auth_status:<12} {critical:<10} {last_display:<20} {status}")

        except Exception as e:
            print(f"{s.site_name:<15} {'?':<10} {'?':<12} {'?':<10} {'?':<20} ❌ ERROR: {e}")

    print(f"\n   🟢 Fresh: {healthy}  🟠 Stale: {expiring}  🔴 Old: {expired}")
    print(f"   💡 Run 'tokenade accounts refresh' to refresh stale sessions")


def _accounts_refresh(manager, args):
    """Refresh sessions — uses refresh-browser for each, with optional plugin support."""
    sessions = manager.list_sessions()

    if not sessions:
        print(f"\n📂 No .tokenade files found in {manager.sessions_dir}")
        return

    if args.site:
        sessions = [s for s in sessions if args.site.lower() in s.site_name.lower()]

    if args.browser:
        sessions = [s for s in sessions if s.source_browser == args.browser]

    if not sessions:
        print("   No matching sessions to refresh")
        return

    # If specific files given, filter to those
    if args.files:
        session_paths = {str(Path(f).resolve()) for f in args.files}
        sessions = [s for s in sessions if str(Path(s.path).resolve()) in session_paths]

    print(f"\n{'=' * 80}")
    print(f"TOKENADE - Refresh {len(sessions)} Accounts")
    print(f"{'=' * 80}")

    for s in sessions:
        print(f"   • {s.site_name} ({s.cookie_count} cookies) — {Path(s.path).name}")

    if not args.yes:
        response = input(f"\n🔄 Refresh all {len(sessions)} sessions? [y/N]: ").strip().lower()
        if response != "y":
            print("Cancelled")
            return

    # Refresh each session
    browser = args.browser or "chrome"
    headless = not args.visible
    wait = args.wait
    port = args.port

    # Load plugin if specified
    plugin_name = getattr(args, "plugin", None)
    plugin_args_list = getattr(args, "plugin_arg", [])
    plugin_creds = {}
    for key, value in plugin_args_list:
        plugin_creds[key] = value

    plugin_loader = None
    refresher = None
    if plugin_name:
        try:
            from tokenade.core.integration.plugin_loader import PluginLoader
            plugin_loader = PluginLoader()
            plugin_loader.load_all()
            refresher = plugin_loader.get_refresher(plugin_name)
            if refresher:
                print(f"\n🔌 Using plugin: {plugin_name} v{refresher.version}")
            else:
                print(f"\n⚠️  Plugin not found: {plugin_name}. Using browser refresh only.")
        except Exception as e:
            print(f"\n⚠️  Plugin error: {e}. Using browser refresh only.")

    succeeded = 0
    failed = 0
    skipped = 0

    for i, s in enumerate(sessions):
        print(f"\n{'─' * 60}")
        print(f"[{i + 1}/{len(sessions)}] Refreshing: {s.site_name} ({Path(s.path).name})")

        # Check if browser is already running
        import subprocess as _sp
        _ps_cmd = ["pgrep", "-c", browser] if platform.system() != "Windows" else ["tasklist", "/fi", f"imagename eq {browser}.exe"]
        try:
            _running = _sp.run(_ps_cmd, capture_output=True, text=True, timeout=3)
            _is_running = False
            if platform.system() != "Windows" and _running.returncode == 0:
                _is_running = int(_running.stdout.strip()) > 0
            elif platform.system() == "Windows" and browser.lower() in _running.stdout.lower():
                _is_running = True
            if _is_running:
                print(f"   ⚠️  {browser} is running. Close it first or use --port for next session.")
                skipped += 1
                continue
        except Exception:
            pass

        try:
            # Try plugin refresh first
            if refresher:
                try:
                    session = packager.load(s.path)
                    if refresher.can_refresh(session):
                        print(f"   🔌 Trying plugin {plugin_name}...")
                        session = refresher.refresh(session, plugin_creds)
                        __import__("tokenade.core.importer.session_packager", fromlist=["SessionPackager"]).SessionPackager().save(session, s.path)
                        print(f"   ✅ Plugin refresh: {s.site_name}")
                        succeeded += 1
                        _run_post_refresh_plugins(plugin_loader, session)
                        continue
                    else:
                        print(f"   ⚠️  Plugin can't handle this session, falling back to browser")
                except Exception as e:
                    print(f"   ⚠️  Plugin refresh failed: {e}, falling back to browser")

            # Browser-based refresh (existing logic)
            from tokenade.core.browser.undetectable import SystemBrowserLauncher

            session = packager = __import__("tokenade.core.importer.session_packager", fromlist=["SessionPackager"]).SessionPackager().load(s.path)
            cookies = session.get("cookies", [])

            if not cookies:
                print(f"   ⚠️  No cookies, skipping")
                skipped += 1
                continue

            # Auto-detect URL
            target_url = _detect_url_from_cookies(cookies)
            if not target_url:
                print(f"   ⚠️  Could not detect URL, skipping")
                skipped += 1
                continue

            # Use unique port per session to avoid conflicts
            session_port = port + i

            launcher = SystemBrowserLauncher()
            browser_proc = launcher.launch(
                browser=browser,
                visible=not headless,
                port=session_port,
                upstream_proxy=_resolve_upstream_proxy(args),
            )

            # Inject → navigate → extract → save
            fresh_cookies, fresh_ls, fresh_ss = _refresh_session_cookies(
                browser_proc, session_port, cookies, target_url, wait
            )

            browser_proc.close()

            if fresh_cookies:
                session["cookies"] = fresh_cookies
                if fresh_ls:
                    session["local_storage"] = fresh_ls
                if fresh_ss:
                    session["session_storage"] = fresh_ss

                if "metadata" not in session:
                    session["metadata"] = {}
                session["metadata"]["cookie_count"] = len(fresh_cookies)
                session["metadata"]["last_refreshed"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()

                __import__("tokenade.core.importer.session_packager", fromlist=["SessionPackager"]).SessionPackager().save(session, s.path)
                print(f"   ✅ Refreshed: {len(fresh_cookies)} cookies")
                succeeded += 1
                if plugin_loader:
                    _run_post_refresh_plugins(plugin_loader, session)
            else:
                print(f"   ❌ No cookies extracted")
                failed += 1

        except Exception as e:
            print(f"   ❌ Failed: {e}")
            logger.error(f"Refresh failed for {s.path}: {e}", exc_info=True)
            failed += 1

    # Summary
    print(f"\n{'=' * 80}")
    print(f"REFRESH COMPLETE")
    print(f"{'=' * 80}")
    print(f"   ✅ Succeeded: {succeeded}")
    print(f"   ❌ Failed: {failed}")
    print(f"   ⏭️  Skipped: {skipped}")
    print(f"   Total: {len(sessions)}")


def _detect_url_from_cookies(cookies):
    """Auto-detect target URL from cookie domains."""
    domains = {c.get("domain", "").lstrip(".") for c in cookies}

    if "google.com" in domains or "gmail.com" in domains:
        return "https://mail.google.com"
    elif "github.com" in domains:
        return "https://github.com"
    elif "twitter.com" in domains or "x.com" in domains:
        return "https://x.com"
    elif "linkedin.com" in domains:
        return "https://www.linkedin.com"
    elif "reddit.com" in domains:
        return "https://www.reddit.com"
    elif "facebook.com" in domains:
        return "https://www.facebook.com"
    elif "instagram.com" in domains:
        return "https://www.instagram.com"
    elif "slack.com" in domains:
        return "https://slack.com"

    # Fallback: use first non-empty domain
    for d in sorted(domains):
        if d and "." in d:
            return f"https://{d}"
    return None


def _refresh_session_cookies(browser_proc, port, cookies, target_url, wait_time):
    """Refresh cookies by injecting into browser, navigating, and extracting."""
    import asyncio
    import json
    import websockets
    import urllib.request as _urllib_req

    # Create new tab
    _req = _urllib_req.Request(
        f"http://127.0.0.1:{port}/json/new?about:blank",
        method="PUT",
    )
    _resp = _urllib_req.urlopen(_req, timeout=10)
    _tab_info = json.loads(_resp.read().decode())
    _tab_ws_url = _tab_info.get("webSocketDebuggerUrl")

    if not _tab_ws_url:
        raise RuntimeError("Failed to create tab")

    async def _do_refresh():
        msg_id_counter = [0]

        async def cdp_cmd(ws, method, params=None):
            msg_id_counter[0] += 1
            current_id = msg_id_counter[0]
            msg = {"id": current_id, "method": method}
            if params:
                msg["params"] = params
            await ws.send(json.dumps(msg))
            deadline = time.time() + 30
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(
                        ws.recv(),
                        timeout=min(5, deadline - time.time()),
                    )
                except asyncio.TimeoutError:
                    continue
                data = json.loads(raw)
                if "id" in data and data["id"] == current_id:
                    if "error" in data:
                        raise RuntimeError(data["error"].get("message", "CDP error"))
                    return data.get("result", {})
            raise RuntimeError(f"CDP timeout: {method}")

        tab_ws = await websockets.connect(
            _tab_ws_url,
            max_size=10 * 1024 * 1024,
            ping_interval=30,
            ping_timeout=10,
        )

        # Inject stealth
        from tokenade.core.browser.cdp_connection import get_undetectable_stealth_script
        stealth_script = get_undetectable_stealth_script()
        await cdp_cmd(tab_ws, "Page.enable")
        await cdp_cmd(tab_ws, "Page.addScriptToEvaluateOnNewDocument", {"source": stealth_script})

        # Inject cookies
        cdp_cookies = []
        for cookie in cookies:
            cdp_cookie = {
                "name": cookie.get("name", ""),
                "value": cookie.get("value", ""),
                "domain": cookie.get("domain", ""),
                "path": cookie.get("path", "/"),
            }
            if cookie.get("secure"):
                cdp_cookie["secure"] = True
            if cookie.get("httpOnly"):
                cdp_cookie["httpOnly"] = True
            if cookie.get("sameSite"):
                ss = cookie["sameSite"]
                if ss in ("Strict", "Lax", "None"):
                    cdp_cookie["sameSite"] = ss
            expires = cookie.get("expires", 0)
            if expires and int(expires) > 0:
                exp = int(expires)
                if exp > 1262304000000:
                    exp = exp // 1000
                cdp_cookie["expires"] = exp
            if cdp_cookie.get("sameSite") == "None" and not cdp_cookie.get("secure"):
                cdp_cookie["secure"] = True
            cdp_cookies.append(cdp_cookie)

        await cdp_cmd(tab_ws, "Network.enable")
        await cdp_cmd(tab_ws, "Network.setCookies", {"cookies": cdp_cookies})

        # Navigate
        await cdp_cmd(tab_ws, "Page.navigate", {"url": target_url})
        await asyncio.sleep(wait_time)

        # Extract fresh cookies
        from tokenade.cli.session import _extract_via_cdp
        session_state = _extract_via_cdp(port, domain_filter=None)

        await tab_ws.close()
        return session_state["cookies"], session_state.get("local_storage", {}), session_state.get("session_storage", {})

    return asyncio.run(_do_refresh())


def cmd_patch_chrome(args):
    """Patch Chrome/Chromium binary to remove cdc_ artifacts."""
    from tokenade.core.browser.patcher import ChromePatcher

    patcher = ChromePatcher()
    browser = getattr(args, "browser", "chrome")
    binary_path = getattr(args, "binary", None)
    output_path = getattr(args, "output", None)
    action = getattr(args, "patch_action", "scan")

    # Find binary if not specified
    if not binary_path:
        binary_path = patcher.find_browser_binary(browser)
        if not binary_path:
            print(f"❌ Could not find {browser} binary. Use --binary to specify path.")
            return
        print(f"🔍 Found {browser}: {binary_path}")

    if action == "scan":
        print(f"\n🔍 Scanning {binary_path} for cdc_ artifacts...")
        result = patcher.scan(binary_path)
        if result.get("error"):
            print(f"❌ {result['error']}")
            return
        matches = result.get("matches", [])
        if not matches:
            print("✅ Binary is clean — no cdc_ artifacts found")
        else:
            print(f"⚠️  Found {len(matches)} cdc_ artifact(s):")
            for i, m in enumerate(matches, 1):
                raw_preview = m["raw"][:60]
                if len(m["raw"]) > 60:
                    raw_preview += b"..."
                print(f"   {i}. Offset {m['offset']} ({m['length']} bytes): {raw_preview}")

    elif action == "patch":
        print(f"\n🔧 Patching {binary_path}...")
        result = patcher.patch(binary_path, output_path=output_path)
        if result.success:
            print(f"✅ {result.summary}")
            if result.backup_path:
                print(f"📦 Backup: {result.backup_path}")
        else:
            print(f"❌ {result.summary}")

    elif action == "restore":
        print(f"\n♻️  Restoring {binary_path} from backup...")
        if patcher.restore(binary_path):
            print(f"✅ Restored {binary_path}")
        else:
            print(f"❌ No backup found for {binary_path}")

    elif action == "verify":
        print(f"\n🔎 Verifying {binary_path}...")
        result = patcher.verify(binary_path)
        if result["patched"]:
            print("✅ Binary is patched (no cdc_ artifacts)")
        else:
            print(f"⚠️  Binary is NOT patched ({result['remaining_artifacts']} artifact(s) remain)")
        if result["has_backup"]:
            print(f"📦 Backup available: {binary_path}.backup")
        if result["has_patched_variant"]:
            print(f"🔧 Patched variant: {binary_path}.patched")


# ── Daemon Commands ─────────────────────────────────────────────



def _daemon_start(args):
    """Start the daemon in background."""
    from tokenade.core.daemon.session_daemon import SessionDaemon, DaemonConfig

    print("\n" + "=" * 60)
    print("TOKENADE - Session Auto-Refresh Daemon")
    print("=" * 60)

    config = DaemonConfig.load()
    if not config.sessions:
        print("⚠️  No sessions configured. Add sessions first:")
        print("   tokenade daemon add <session.tokenade>")
        return

    daemon = SessionDaemon(config)

    # Override config from args
    if hasattr(args, "interval") and args.interval:
        config.check_interval_minutes = args.interval
    if hasattr(args, "webhook") and args.webhook:
        config.webhook_url = args.webhook

    daemon.config.save()
    success = daemon.start(daemonize=True)

    if success:
        print(f"✅ Daemon started")
        print(f"   Watching {len(config.sessions)} session(s)")
        print(f"   Check interval: {config.check_interval_minutes} minutes")
        if config.webhook_url:
            print(f"   Webhook: {config.webhook_url}")
        print(f"   Logs: ~/.tokenade/logs/daemon.log")
        print(f"   PID file: ~/.tokenade/daemon.pid")
    else:
        print("❌ Failed to start daemon")


def _daemon_stop(args):
    """Stop the daemon."""
    from tokenade.core.daemon.session_daemon import SessionDaemon

    print("\nStopping daemon...")
    daemon = SessionDaemon()
    if daemon.stop():
        print("✅ Daemon stopped")
    else:
        print("❌ Failed to stop daemon")


def _daemon_status(args):
    """Show daemon status."""
    from tokenade.core.daemon.session_daemon import SessionDaemon

    daemon = SessionDaemon()
    status = daemon.status()

    print("\n" + "=" * 60)
    print("TOKENADE - Daemon Status")
    print("=" * 60)

    if status["running"]:
        print(f"   🟢 Running (PID {status['pid']})")
    else:
        print(f"   🔴 Stopped")

    print(f"   State: {status['state']}")
    print(f"   Sessions watched: {status['sessions_watched']}")
    print(f"   Sessions enabled: {status['sessions_enabled']}")
    print(f"   Check interval: {status['check_interval_minutes']} min")
    print(f"   Webhook: {'configured' if status['webhook_configured'] else 'not configured'}")
    print(f"   History entries: {status['history_count']}")
    print(f"   Config: {status['config_file']}")

    # Show recent history
    history = daemon.get_history(limit=5)
    if history:
        print(f"\n   Recent Activity:")
        for h in reversed(history):
            icon = "✅" if h["success"] else "❌"
            print(f"   {icon} {h['site_name']} — {h['cookies_before']}→{h['cookies_after']} cookies ({h['duration_seconds']:.1f}s)")


def _daemon_run_once(args):
    """Run a single refresh cycle (foreground)."""
    from tokenade.core.daemon.session_daemon import SessionDaemon, DaemonConfig

    print("\n" + "=" * 60)
    print("TOKENADE - Single Refresh Cycle")
    print("=" * 60)

    config = DaemonConfig.load()
    if not config.sessions:
        print("⚠️  No sessions configured")
        return

    enabled = [s for s in config.sessions if s.enabled]
    print(f"   Sessions to refresh: {len(enabled)}")

    daemon = SessionDaemon(config)
    results = daemon.run_once()

    # Print results
    print(f"\n{'─' * 60}")
    succeeded = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)

    for r in results:
        icon = "✅" if r.success else "❌"
        detail = f"{r.cookies_before}→{r.cookies_after} cookies" if r.success else r.error
        print(f"   {icon} {r.site_name} — {detail} ({r.duration_seconds:.1f}s)")

    print(f"\n{'─' * 60}")
    print(f"   Total: {len(results)} | ✅ {succeeded} | ❌ {failed}")
    print()


def _daemon_add(args):
    """Add a session to the daemon watch list."""
    from tokenade.core.daemon.session_daemon import SessionDaemon, DaemonConfig

    session_path = args.session
    browser = getattr(args, "browser", "chrome") or "chrome"
    refresh_before = getattr(args, "refresh_before", 2.0) or 2.0
    target_url = getattr(args, "url", "") or ""
    site_name = getattr(args, "site_name", "") or ""

    daemon = SessionDaemon()
    if daemon.add_session(session_path, browser, refresh_before, target_url, site_name):
        print(f"✅ Added: {Path(session_path).name}")
        print(f"   Browser: {browser}")
        print(f"   Refresh before: {refresh_before}h before expiry")
        if target_url:
            print(f"   Target URL: {target_url}")
    else:
        print(f"❌ Failed to add session")


def _daemon_remove(args):
    """Remove a session from the daemon watch list."""
    from tokenade.core.daemon.session_daemon import SessionDaemon

    daemon = SessionDaemon()
    if daemon.remove_session(args.session):
        print(f"✅ Removed: {args.session}")
    else:
        print(f"❌ Session not found in watch list")


def _daemon_list(args):
    """List all watched sessions."""
    from tokenade.core.daemon.session_daemon import SessionDaemon

    daemon = SessionDaemon()
    sessions = daemon.list_sessions()

    if not sessions:
        print("📂 No sessions configured. Add with: tokenade daemon add <file>")
        return

    print(f"\n{'=' * 70}")
    print(f"TOKENADE - Daemon Watch List ({len(sessions)} sessions)")
    print(f"{'=' * 70}")

    for s in sessions:
        status = "🟢" if s["enabled"] else "🔴"
        exists = "📄" if s["file_exists"] else "⚠️ "
        print(f"   {status} {exists} {s['site_name']} ({Path(s['path']).name})")
        print(f"      Browser: {s['browser']} | Refresh before: {s['refresh_before_hours']}h")
        if s["last_refreshed"]:
            print(f"      Last refreshed: {s['last_refreshed']}")
        if s["last_error"]:
            print(f"      Last error: {s['last_error']}")
        print()


def _daemon_logs(args):
    """View daemon logs."""
    from tokenade.core.daemon.session_daemon import DAEMON_LOG_FILE

    log_file = DAEMON_LOG_FILE
    if not log_file.exists():
        print("📂 No daemon logs found. Start the daemon first.")
        return

    lines = getattr(args, "lines", 50) or 50
    follow = getattr(args, "follow", False)

    if follow:
        print(f"Following {log_file} (Ctrl+C to stop)...")
        try:
            import subprocess
            subprocess.run(["tail", "-f", str(log_file)])
        except KeyboardInterrupt:
            print("\nStopped following logs")
    else:
        # Read last N lines
        content = log_file.read_text()
        log_lines = content.strip().split("\n")
        for line in log_lines[-lines:]:
            print(line)


# ── Versioning Commands ─────────────────────────────────────────

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
        print(f"📂 No versions for {Path(session_path).name}")
        print(f"   Create one: tokenade versions create {session_path}")
        return

    print(f"\n{'=' * 70}")
    print(f"TOKENADE - Versions for {Path(session_path).name} ({len(versions)})")
    print(f"{'=' * 70}")

    for v in versions:
        print(f"   v{v.version}: {v.cookie_count} cookies | {v.size_bytes} bytes | {v.created_at[:19]}")
        if v.description:
            print(f"         {v.description}")
    print()


def _versions_create(args):
    """Create a new version of a session."""
    from tokenade.core.storage.session_versions import SessionVersionManager

    session_path = args.session
    description = getattr(args, "description", "") or ""

    if not Path(session_path).exists():
        print(f"❌ Session file not found: {session_path}")
        return

    mgr = SessionVersionManager()
    version = mgr.create_version(session_path, description)
    print(f"✅ Created version {version.version} of {Path(session_path).name}")
    print(f"   Cookies: {version.cookie_count} | Size: {version.size_bytes} bytes")


def _versions_delete(args):
    """Delete a specific version."""
    from tokenade.core.storage.session_versions import SessionVersionManager

    session_path = args.session
    version = args.version

    mgr = SessionVersionManager()
    if mgr.delete_version(session_path, version):
        print(f"✅ Deleted version {version}")
    else:
        print(f"❌ Version {version} not found")


def cmd_rollback(args):
    """Rollback a session to a specific version."""
    from tokenade.core.storage.session_versions import SessionVersionManager

    session_path = args.session
    version = args.version

    if not Path(session_path).exists():
        print(f"❌ Session file not found: {session_path}")
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
        print(f"❌ Version {version} not found")
        return

    print(f"🔄 Rolling back {Path(session_path).name} to version {version}")
    print(f"   {target.cookie_count} cookies | {target.created_at[:19]}")

    if mgr.rollback(session_path, version):
        print(f"✅ Rollback complete")
    else:
        print(f"❌ Rollback failed")


def cmd_session_diff(args):
    """Compare two versions of a session."""
    from tokenade.core.storage.session_versions import SessionVersionManager

    session_path = args.session
    version_a = args.version_a
    version_b = args.version_b

    mgr = SessionVersionManager()
    diff = mgr.diff(session_path, version_a, version_b)

    print(f"\n{'=' * 70}")
    print(f"TOKENADE - Diff: v{diff.version_a} → v{diff.version_b}")
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


# ── Logs Command ────────────────────────────────────────────────

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
        log_path = Path(log_file) if log_file else LogManager.get_log_dir() / "tokenade.log"
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


# ── Mobile Import ────────────────────────────────────────────────

def cmd_mobile_import(args):
    """Import sessions from mobile devices (Android/iOS)."""
    from tokenade.core.importer.mobile_import import MobileImportManager

    manager = MobileImportManager()

    if not manager.is_available():
        print("❌ No mobile extraction method available")
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
        # No device specified — list and prompt
        devices = manager.list_devices()
        if not devices:
            print("❌ No mobile devices connected")
            print("   Connect a device via USB and enable USB debugging (Android)")
            return
        if len(devices) == 1:
            device = devices[0]
        else:
            print("Multiple devices found:")
            for i, d in enumerate(devices):
                print(f"  [{i + 1}] {d.model} ({d.serial}) — {d.platform}")
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
            print(f"❌ Device not found: {device_serial}")
            print("   Connected devices:")
            for d in devices:
                print(f"     {d.serial} — {d.model}")
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

    print(f"\n🔄 Extracting cookies...")

    result = manager.extract(
        device=device,
        browser=browser,
        domains=domains,
        output_file=output,
        site_name=site_name,
    )

    if result.success:
        print(f"\n✅ Extraction successful")
        print(f"   Browser: {result.browser}")
        print(f"   Cookies: {result.cookie_count}")
        print(f"   Site: {result.site_name}")
        print(f"   Auth: {result.auth_status}")
        print(f"   Domains: {', '.join(result.domains[:10])}")
        if result.session_file:
            print(f"   Saved: {result.session_file}")
    else:
        print(f"\n❌ Extraction failed: {result.error}")
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
        print(f"\n   📱 {d.model} ({d.platform.upper()})")
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
        print("❌ No mobile devices connected")
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
        print(f"✅ Extracted {result.cookie_count} cookies from {result.browser}")
        if result.session_file:
            print(f"   Saved: {result.session_file}")
    else:
        print(f"❌ Failed: {result.error}")


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
        print("❌ --dest is required")
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
        print(f"\n✅ Profile cloned successfully")
        print(f"   Files: {result.files_copied}")
        print(f"   Size: {result.size_bytes / (1024 * 1024):.1f} MB")
        if result.session_injected:
            print(f"   Cookies injected: {result.cookies_injected}")
        print(f"   Location: {result.dest_path}")
        print(f"\n   Launch with:")
        print(f"   tokenade launch --browser {browser} --profile-dir {result.dest_path}")
    else:
        print(f"\n❌ Clone failed:")
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
# Container management commands
# ---------------------------------------------------------------------------

def cmd_container(args):
    """Docker container management."""
    action = getattr(args, "container_action", None)

    if action == "start":
        _container_start(args)
    elif action == "stop":
        _container_stop(args)
    elif action == "restart":
        _container_restart(args)
    elif action == "status":
        _container_status(args)
    elif action == "logs":
        _container_logs(args)
    elif action == "refresh":
        _container_refresh(args)
    elif action == "scale":
        _container_scale(args)
    elif action == "cleanup":
        _container_cleanup(args)
    elif action == "health":
        _container_health(args)
    elif action == "generate":
        _container_generate(args)
    else:
        print("Usage: tokenade container {start|stop|restart|status|logs|refresh|scale|cleanup|health|generate}")


def _container_start(args):
    """Start proxy and optionally API containers."""
    from tokenade.core.integration.docker_manager import DockerSessionManager
    from tokenade.core.integration.container_orchestrator import generate_compose_override
    from pathlib import Path

    docker = DockerSessionManager()
    if not docker.is_available():
        print("❌ Docker is not available. Install Docker and try again.")
        return

    sessions_dir = Path(args.sessions_dir)
    session_files = list(sessions_dir.glob("*.tokenade"))

    if not session_files:
        print(f"❌ No .tokenade files found in {sessions_dir}")
        return

    print("\n" + "=" * 60)
    print("TOKENADE - Container Start")
    print("=" * 60)
    print(f"\n📂 Sessions: {len(session_files)}")
    print(f"🔌 Proxy port: {args.proxy_port}")

    # Create network
    docker.create_network()

    # Start proxy containers
    results = docker.run_batch(
        session_files=[str(f) for f in session_files],
        prefix="tokenade",
    )

    for r in results:
        status = "✅" if r["status"] == "running" else "❌"
        print(f"   {status} {r['name']} (port {r['port']})")

    # Start API server if requested
    if not args.no_api:
        print(f"\n🌐 Starting API server on port {args.api_port}...")
        import subprocess
        try:
            subprocess.run([
                "docker", "run", "-d",
                "--name", "tokenade-api",
                "-p", f"{args.api_port}:9224",
                "-v", f"{sessions_dir.absolute()}:/app/sessions",
                "-e", "TOKENADE_DATA_DIR=/app",
                "-e", "PYTHONUNBUFFERED=1",
                docker.image_name,
                "python", "-c",
                "from tokenade.core.api.server import TokenadeAPIServer; import asyncio; s=TokenadeAPIServer(); asyncio.run(s.start())",
            ], capture_output=True, text=True, check=True, timeout=30)
            print(f"   ✅ API server started")
        except Exception as e:
            print(f"   ❌ API server failed: {e}")

    print(f"\n{'=' * 60}\n")


def _container_stop(args):
    """Stop containers."""
    from tokenade.core.integration.docker_manager import DockerSessionManager

    docker = DockerSessionManager()
    if not docker.is_available():
        print("❌ Docker is not available")
        return

    name = getattr(args, "name", None)
    if name:
        if docker.stop_container(name):
            print(f"✅ Stopped {name}")
        else:
            print(f"❌ Failed to stop {name}")
    else:
        count = docker.cleanup(remove_all=False)
        print(f"✅ Stopped {count} container(s)")


def _container_restart(args):
    """Restart containers."""
    from tokenade.core.integration.container_orchestrator import ContainerOrchestrator

    orch = ContainerOrchestrator()
    health_list = orch.check_all_health()

    for h in health_list:
        if orch.restart_container(h.name):
            print(f"✅ Restarted {h.name}")
        else:
            print(f"❌ Failed to restart {h.name}")


def _container_status(args):
    """Show container status."""
    from tokenade.core.integration.container_orchestrator import ContainerOrchestrator

    orch = ContainerOrchestrator()
    summary = orch.get_status_summary()

    print("\n" + "=" * 60)
    print("TOKENADE - Container Status")
    print("=" * 60)
    print(f"\n📊 Total: {summary['total']} | Healthy: {summary['healthy']} | Unhealthy: {summary['unhealthy']} | Stopped: {summary['stopped']}")

    for c in summary["containers"]:
        icon = "🟢" if c["healthy"] else ("🔴" if c["status"] == "running" else "⚫")
        print(f"\n   {icon} {c['name']}")
        print(f"      Status: {c['status']}")
        print(f"      Restarts: {c['restart_count']}")
        if c["error"]:
            print(f"      Error: {c['error']}")

    print(f"\n{'=' * 60}\n")


def _container_logs(args):
    """Tail container logs."""
    import subprocess

    cmd = ["docker", "logs", "--tail", str(args.tail)]
    if args.follow:
        cmd.append("-f")
    cmd.append(args.name)

    try:
        subprocess.run(cmd, timeout=30)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"❌ Failed to get logs: {e}")


def _container_refresh(args):
    """Refresh sessions inside a container."""
    from tokenade.core.integration.container_orchestrator import ContainerOrchestrator

    orch = ContainerOrchestrator()
    results = orch.refresh_all_in_container(args.name, args.sessions_dir)

    for r in results:
        if r.get("success"):
            print(f"✅ {r.get('session', 'unknown')}: refreshed")
        else:
            print(f"❌ {r.get('session', 'unknown')}: {r.get('error', 'failed')}")


def _container_scale(args):
    """Scale proxy containers."""
    from tokenade.core.integration.docker_manager import DockerSessionManager
    from pathlib import Path

    docker = DockerSessionManager()
    if not docker.is_available():
        print("❌ Docker is not available")
        return

    sessions_dir = Path(args.sessions_dir)
    session_files = list(sessions_dir.glob("*.tokenade"))[:args.replicas]

    if not session_files:
        print(f"❌ No .tokenade files found")
        return

    # Stop existing
    docker.cleanup(remove_all=False)

    # Start new batch
    results = docker.run_batch(
        session_files=[str(f) for f in session_files],
        prefix="tokenade",
    )

    running = sum(1 for r in results if r["status"] == "running")
    print(f"✅ Scaled to {running}/{args.replicas} containers")


def _container_cleanup(args):
    """Stop and remove all tokenade containers."""
    from tokenade.core.integration.docker_manager import DockerSessionManager

    docker = DockerSessionManager()
    if not docker.is_available():
        print("❌ Docker is not available")
        return

    count = docker.cleanup(remove_all=True)
    print(f"✅ Cleaned up {count} container(s)")


def _container_health(args):
    """Check container health."""
    from tokenade.core.integration.container_orchestrator import ContainerOrchestrator

    orch = ContainerOrchestrator()

    if args.watch:
        print(f"🔍 Monitoring containers (interval: {args.interval}s, max restarts: {args.max_restarts})")
        print("   Press Ctrl+C to stop\n")
        try:
            orch.auto_restart_unhealthy(
                max_restarts=args.max_restarts,
                check_interval=args.interval,
            )
        except KeyboardInterrupt:
            orch.stop()
            print("\n✅ Monitor stopped")
    else:
        summary = orch.get_status_summary()
        print(f"\n📊 {summary['total']} containers: {summary['healthy']} healthy, {summary['unhealthy']} unhealthy")
        for c in summary["containers"]:
            icon = "🟢" if c["healthy"] else "🔴"
            print(f"   {icon} {c['name']} — {c['status']}")


def _container_generate(args):
    """Generate docker-compose override."""
    from tokenade.core.integration.container_orchestrator import generate_compose_override
    from pathlib import Path

    sessions_dir = Path(args.sessions_dir)
    session_files = [f.name for f in sessions_dir.glob("*.tokenade")]

    if not session_files:
        print(f"❌ No .tokenade files found in {sessions_dir}")
        return

    yaml_content = generate_compose_override(
        sessions=session_files,
        base_port=args.base_port,
    )

    if args.output:
        Path(args.output).write_text(yaml_content)
        print(f"✅ Generated {args.output}")
    else:
        print(yaml_content)


# ---------------------------------------------------------------------------
# Kubernetes management commands
# ---------------------------------------------------------------------------

def cmd_k8s(args):
    """Kubernetes deployment management."""
    action = getattr(args, "k8s_action", None)

    if action == "deploy":
        _k8s_deploy(args)
    elif action == "status":
        _k8s_status(args)
    elif action == "scale":
        _k8s_scale(args)
    elif action == "logs":
        _k8s_logs(args)
    elif action == "delete":
        _k8s_delete(args)
    elif action == "pods":
        _k8s_pods(args)
    else:
        print("Usage: tokenade k8s {deploy|status|scale|logs|delete|pods}")


def _k8s_deploy(args):
    """Generate and apply K8s manifests."""
    from tokenade.core.integration.kubernetes import KubernetesManager, KubernetesConfig

    config = KubernetesConfig(
        namespace=args.namespace,
        image=args.image,
        replicas=args.replicas,
        port=args.port,
    )
    k8s = KubernetesManager(config)

    deployment_yaml = k8s.generate_deployment_yaml()
    service_yaml = k8s.generate_service_yaml()
    full_yaml = deployment_yaml + "\n---\n" + service_yaml

    if args.dry_run or args.output:
        if args.output:
            Path(args.output).write_text(full_yaml)
            print(f"✅ Generated {args.output}")
        else:
            print(full_yaml)
        return

    print("\n🚀 Deploying to Kubernetes...")
    if k8s.apply_manifests(full_yaml):
        print("✅ Applied successfully")
    else:
        print("❌ Failed to apply manifests")


def _k8s_status(args):
    """Show deployment status."""
    from tokenade.core.integration.kubernetes import KubernetesManager, KubernetesConfig

    config = KubernetesConfig(namespace=args.namespace)
    k8s = KubernetesManager(config)

    status = k8s.get_deployment_status()
    if not status.get("available"):
        print(f"❌ {status.get('error', 'Deployment not found')}")
        return

    print(f"\n📊 Deployment: {status['name']}")
    print(f"   Replicas: {status['ready_replicas']}/{status['replicas']} ready")
    for c in status.get("conditions", []):
        print(f"   {c['type']}: {c['status']} — {c['message']}")


def _k8s_scale(args):
    """Scale deployment."""
    from tokenade.core.integration.kubernetes import KubernetesManager, KubernetesConfig

    config = KubernetesConfig(namespace=args.namespace)
    k8s = KubernetesManager(config)

    if k8s.scale_deployment(args.replicas):
        print(f"✅ Scaled to {args.replicas} replicas")
    else:
        print("❌ Failed to scale")


def _k8s_logs(args):
    """Tail pod logs."""
    from tokenade.core.integration.kubernetes import KubernetesManager, KubernetesConfig

    config = KubernetesConfig(namespace=args.namespace)
    k8s = KubernetesManager(config)

    pods = k8s.get_pods()
    for pod in pods:
        print(f"\n--- {pod['name']} ---")
        logs = k8s.get_logs(pod["name"], tail=args.tail)
        print(logs)


def _k8s_delete(args):
    """Delete deployment and service."""
    from tokenade.core.integration.kubernetes import KubernetesManager, KubernetesConfig

    config = KubernetesConfig(namespace=args.namespace)
    k8s = KubernetesManager(config)

    if k8s.delete_deployment():
        print("✅ Deleted deployment and service")
    else:
        print("❌ Failed to delete")


def _k8s_pods(args):
    """List pods."""
    from tokenade.core.integration.kubernetes import KubernetesManager, KubernetesConfig

    config = KubernetesConfig(namespace=args.namespace)
    k8s = KubernetesManager(config)

    pods = k8s.get_pods()
    if not pods:
        print("No pods found")
        return

    for pod in pods:
        status_icon = "🟢" if pod["status"] == "Running" else "🔴"
        print(f"   {status_icon} {pod['name']} — {pod['status']} (restarts: {pod['restart_count']})")
