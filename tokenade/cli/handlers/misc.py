"""
Misc CLI commands — tui, daemon, analytics, monitor.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger("tokenade")


def _health_bar(score: float, width: int = 20) -> str:
    """Render a health score bar."""
    filled = int(score / 100 * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {score:.0f}%"


def cmd_monitor(args):
    """Session monitoring management."""
    from pathlib import Path

    action = getattr(args, "monitor_command", None) or getattr(args, "monitor_action", None)

    if action == "start":
        _monitor_start(args)
    elif action == "stop":
        _monitor_stop()
    elif action == "status":
        _monitor_status(args)
    elif action == "history":
        _monitor_history()
    elif action == "predict":
        _monitor_predict(args)
    else:
        print("❌ Specify a monitor subcommand: status, start, stop, history, predict")


def _monitor_start(args):
    """Start background monitoring."""
    import time
    from tokenade.core.monitoring.session_monitor import SessionMonitor, MonitorConfig

    session = getattr(args, "session", None)
    sessions_dir = getattr(args, "sessions_dir", None)
    interval = getattr(args, "interval", 60)

    config = MonitorConfig(check_interval=interval)
    monitor = SessionMonitor(config)

    if session:
        session_id = monitor.register_session_file(session)
        if session_id:
            print(f"✅ Monitoring session: {session_id}")
        else:
            print(f"❌ Failed to register: {session}")
            return
    elif sessions_dir:
        config.sessions_dir = sessions_dir
        monitor = SessionMonitor(config)
        registered = monitor.scan_sessions_dir()
        if registered:
            print(f"✅ Monitoring {len(registered)} sessions")
        else:
            print(f"❌ No sessions found in {sessions_dir}")
            return
    else:
        print("❌ Specify --session or --sessions-dir")
        return

    monitor.start()
    print("✅ Monitor started (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(interval)
    except KeyboardInterrupt:
        monitor.stop()
        print("\n✅ Monitor stopped")


def _monitor_stop():
    """Stop a running monitor (by PID file)."""
    import os
    import signal
    pid_file = Path("~/.tokenade/monitor.pid").expanduser()
    if not pid_file.exists():
        print("❌ No monitor process found (no PID file)")
        return

    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        print(f"✅ Sent stop signal to monitor (PID: {pid})")
        pid_file.unlink(missing_ok=True)
    except (ProcessLookupError, ValueError) as e:
        print(f"❌ Failed to stop monitor: {e}")
        pid_file.unlink(missing_ok=True)


def _monitor_status(args):
    """Show current monitoring status."""
    from tokenade.core.monitoring.session_monitor import SessionMonitor, MonitorConfig

    session = getattr(args, "session", None)
    sessions_dir = getattr(args, "sessions_dir", None)

    print("\n" + "=" * 60)
    print("TOKENADE - Session Monitor Status")
    print("=" * 60)

    config = MonitorConfig(sessions_dir=sessions_dir)
    monitor = SessionMonitor(config)

    if session:
        # Register the session if not already monitored
        session_id = monitor.register_session_file(session)
        if session_id:
            status = monitor.get_status(session_id)
        else:
            status = None
        if status:
            site = status.site_name or session_id
            bar = _health_bar(status.health_score)
            print(f"\n📊 {site}")
            print(f"   Health: {bar}")
            print(f"   Cookies: {status.cookie_count}")
            print(f"   Expired: {status.expired_cookies}")
        else:
            print(f"❌ No status for: {session}")
    elif sessions_dir:
        registered = monitor.scan_sessions_dir()
        if not registered:
            print(f"📂 No sessions found in {sessions_dir}")
        else:
            statuses = monitor.get_all_statuses()
            print(f"\n📂 {len(statuses)} sessions in {sessions_dir}\n")
            for s in statuses:
                bar = _health_bar(s.health_score)
                print(f"  {s.session_id}: {bar}")
    else:
        statuses = monitor.get_all_statuses()
        if not statuses:
            print("❌ No sessions registered. Use --session or --sessions-dir")
        else:
            print(f"\n📊 {len(statuses)} monitored sessions\n")
            for s in statuses:
                bar = _health_bar(s.health_score)
                print(f"  {s.session_id}: {bar}")


def _monitor_history():
    """Show monitor event history."""
    from tokenade.core.monitoring.session_monitor import SessionMonitor

    monitor = SessionMonitor()
    history = monitor.get_event_history()
    if not history:
        print("No monitor events recorded yet")
        return
    print(f"\n📋 Last {min(10, len(history))} events:\n")
    for event in history[-10:]:
        print(f"  {event}")


def _monitor_predict(args):
    """Predict session expiry."""
    from tokenade.core.monitoring.session_monitor import SessionMonitor

    session = getattr(args, "session", None)
    monitor = SessionMonitor()

    if session:
        status = monitor.get_status(session)
        if status and status.predicted_expiry:
            print(f"⏰ {session}: predicted expiry in {status.predicted_expiry}")
        else:
            print("insufficient data for prediction")
    else:
        print("insufficient data for prediction")


def cmd_analytics(args):
    """Session usage analytics."""
    from tokenade.core.monitoring.analytics import SessionAnalytics

    analytics = SessionAnalytics()

    if args.analytics_command == "report":
        days = getattr(args, "days", 30)
        report = analytics.get_usage_report(days=days)
        print(json.dumps(report, indent=2))
    elif args.analytics_command == "cleanup":
        analytics.cleanup()
        print("✅ Analytics data cleaned up")
    else:
        print("Usage: tokenade analytics {report|cleanup}")
        print("Usage: tokenade analytics {report|cleanup}")


def cmd_daemon(args):
    """Background daemon management."""
    from tokenade.core.daemon.session_daemon import SessionDaemon

    daemon = SessionDaemon()

    if args.daemon_action == "start":
        daemon.start()
        print("✅ Daemon started")
    elif args.daemon_action == "stop":
        daemon.stop()
        print("✅ Daemon stopped")
    elif args.daemon_action == "status":
        status = daemon.get_status()
        print(f"Daemon status: {status}")
    else:
        print("Usage: tokenade daemon {start|stop|status}")
