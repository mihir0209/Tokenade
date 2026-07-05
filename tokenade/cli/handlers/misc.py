"""
Misc CLI commands — tui, daemon, analytics, monitor.
"""

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("tokenade")


def cmd_monitor(args):
    """Session monitoring management."""
    from tokenade.core.monitoring.session_monitor import SessionMonitor

    monitor = SessionMonitor()

    if args.monitor_action == "start":
        monitor.start()
        print("✅ Session monitor started")
    elif args.monitor_action == "stop":
        monitor.stop()
        print("✅ Session monitor stopped")
    elif args.monitor_action == "status":
        status = monitor.get_status()
        print(f"Monitor status: {status}")
    elif args.monitor_action == "history":
        history = monitor.get_history()
        for event in history[-10:]:
            print(f"  {event}")
    else:
        print("Usage: tokenade monitor {start|stop|status|history}")


def cmd_analytics(args):
    """Session usage analytics."""
    from tokenade.core.monitoring.analytics import SessionAnalytics

    analytics = SessionAnalytics()

    if args.analytics_command == "report":
        report = analytics.get_report()
        print(json.dumps(report, indent=2))
    elif args.analytics_command == "cleanup":
        analytics.cleanup()
        print("✅ Analytics data cleaned up")
    else:
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
