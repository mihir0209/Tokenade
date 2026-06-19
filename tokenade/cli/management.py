"""Session management CLI commands."""
import json
import logging
import signal
import time
from pathlib import Path

logger = logging.getLogger("tokenade")


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

    if args.format == "qr":
        output_path = args.output or f"{session_file.stem}_qr.png"
        sharer.create_qr_code(session, output_path, config)
        print(f"\n📱 QR code saved to: {output_path}")
    elif args.format == "html":
        output_path = args.output or f"{session_file.stem}_share.html"
        share_url, session_id = sharer.create_share_link(session, config)
        generate_share_html(session, output_path)
        print(f"\n📄 Share page saved to: {output_path}")
        print(f"🆔 Session ID: {session_id}")
    else:
        share_url, session_id = sharer.create_share_link(session, config)
        print(f"\n🔗 Share URL: {share_url}")
        print(f"🆔 Session ID: {session_id}")

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


def cmd_monitor(args):
    """Session monitoring commands."""
    if args.monitor_command == "status":
        _monitor_status(args)
    elif args.monitor_command == "start":
        _monitor_start(args)
    elif args.monitor_command == "stop":
        _monitor_stop(args)
    elif args.monitor_command == "history":
        _monitor_history(args)
    elif args.monitor_command == "predict":
        _monitor_predict(args)
    else:
        print("❌ Specify a monitor subcommand: status, start, stop, history, predict")


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


def cmd_analytics(args):
    """Session analytics commands."""
    from tokenade.core.monitoring.analytics import SessionAnalytics

    analytics = SessionAnalytics()

    if args.analytics_command == "report":
        _analytics_report(args, analytics)
    elif args.analytics_command == "session":
        _analytics_session(args, analytics)
    elif args.analytics_command == "cleanup":
        _analytics_cleanup(args, analytics)
    else:
        print("❌ Specify an analytics subcommand: report, session, cleanup")


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
