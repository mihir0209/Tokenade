"""Session management CLI commands."""
import json
import logging
import platform
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

            packager = SessionPackager()
            session = packager.load(args.session)

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
                    tab_ws_url, max_size=10*1024*1024,
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
        print(f"  3. Or let it run and control via CDP WebSocket")
        print(f"\nPress Ctrl+C to close the browser")
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


def cmd_cicd(args):
    """Generate CI/CD workflow files."""
    from tokenade.core.cicd.workflow_generator import WorkflowConfig, WorkflowGenerator, generate_all_workflows

    print("\n" + "=" * 80)
    print("TOKENADE - CI/CD Workflow Generator")
    print("=" * 80)

    if args.generate_all:
        print(f"\n📂 Sessions directory: {args.sessions_dir}")
        print(f"⏰ Refresh interval: {args.interval_hours} hours")
        print(f"🌐 Source browser: {args.source_browser}")
        print(f"📁 Output directory: {args.output_dir}")

        workflows = generate_all_workflows(
            sessions_dir=args.sessions_dir,
            refresh_interval_hours=args.interval_hours,
            source_browser=args.source_browser,
            output_dir=args.output_dir,
        )

        print(f"\n✅ Generated {len(workflows)} workflow files:")
        for filename in workflows:
            print(f"   • {args.output_dir}/{filename}")

        print(f"\n📖 Next steps:")
        print(f"   1. Copy .github/workflows/ to your repository")
        print(f"   2. Add your .tokenade files to {args.sessions_dir}/")
        print(f"   3. For OAuth refresh, add oauth_config to your sessions:")
        print(f"      tokenade oauth-config -s <session> --client-id <id> --token-endpoint <url>")
        print(f"   4. Push to GitHub — workflows will run automatically")
        return

    if args.workflow_type == "github":
        config = WorkflowConfig(
            sessions_dir=args.sessions_dir,
            refresh_interval_hours=args.interval_hours,
            source_browser=args.source_browser,
        )
        generator = WorkflowGenerator()
        workflow = generator.generate_github_actions(config)

        output_path = args.output or ".github/workflows/refresh-sessions.yml"
        generator.save(workflow, output_path)
        print(f"\n✅ Generated GitHub Actions workflow: {output_path}")

    elif args.workflow_type == "gitlab":
        config = WorkflowConfig(
            sessions_dir=args.sessions_dir,
            refresh_interval_hours=args.interval_hours,
            source_browser=args.source_browser,
        )
        generator = WorkflowGenerator()
        workflow = generator.generate_gitlab_ci(config)

        output_path = args.output or ".gitlab-ci.yml"
        generator.save(workflow, output_path)
        print(f"\n✅ Generated GitLab CI pipeline: {output_path}")

    elif args.workflow_type == "cron":
        config = WorkflowConfig(
            sessions_dir=args.sessions_dir,
            refresh_interval_hours=args.interval_hours,
            source_browser=args.source_browser,
        )
        generator = WorkflowGenerator()
        script = generator.generate_cron_script(config)

        output_path = args.output or f"{args.sessions_dir}/refresh.sh"
        generator.save(script, output_path)
        print(f"\n✅ Generated cron script: {output_path}")
        print(f"\n📖 Add to crontab:")
        print(f"   0 */{args.interval_hours} * * * {output_path}")


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

    try:
        print(f"\n🚀 Launching {args.browser} (headless={args.headless})...")
        browser = launcher.launch(
            browser=args.browser,
            visible=not args.headless,
            port=port,
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
    """Refresh sessions — uses refresh-browser for each."""
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
            # Use the refresh-browser logic inline
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
