"""Session monitoring dashboard CLI commands."""

import argparse
import json
import sys

from tokenade.cli import add_hidden_command


def cmd_dashboard(args):
    """Handle dashboard commands."""
    if not hasattr(args, "dashboard_action"):
        print("Usage: tokenade dashboard <action> [options]", file=sys.stderr)
        sys.exit(1)
    
    from tokenade.core.dashboard import DashboardServer, DashboardConfig
    
    config = DashboardConfig(
        host=args.host or "127.0.0.1",
        port=args.port or 8080,
        title=args.title or "Tokenade Session Monitor",
        refresh_interval=args.refresh or 10,
    )
    
    server = DashboardServer(config)
    
    if args.dashboard_action == "start":
        print(f"Starting dashboard at http://{config.host}:{config.port}")
        print("Press Ctrl+C to stop")
        try:
            server.start(block=True)
        except KeyboardInterrupt:
            print("\nStopping dashboard...")
            server.stop()
    
    elif args.dashboard_action == "status":
        import urllib.request
        import urllib.error
        
        try:
            url = f"http://{config.host}:{config.port}/api/health"
            with urllib.request.urlopen(url) as response:
                data = json.loads(response.read())
                print(json.dumps(data, indent=2))
        except urllib.error.URLError as e:
            print(f"Dashboard not running: {e}", file=sys.stderr)
            sys.exit(1)
    
    elif args.dashboard_action == "sessions":
        import urllib.request
        import urllib.error
        
        try:
            url = f"http://{config.host}:{config.port}/api/sessions"
            with urllib.request.urlopen(url) as response:
                data = json.loads(response.read())
                if args.json:
                    print(json.dumps(data, indent=2))
                else:
                    if not data:
                        print("No sessions found")
                    else:
                        for session in data:
                            print(f"  {session['name']}: {session['status']}")
        except urllib.error.URLError as e:
            print(f"Dashboard not running: {e}", file=sys.stderr)
            sys.exit(1)
    
    else:
        print(f"Unknown dashboard action: {args.dashboard_action}", file=sys.stderr)
        sys.exit(1)


def register_dashboard_parser(subparsers):
    """Register dashboard parser."""
    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Session monitoring web dashboard",
    )
    
    dashboard_subparsers = dashboard_parser.add_subparsers(dest="dashboard_action")
    
    start_parser = dashboard_subparsers.add_parser("start", help="Start dashboard server")
    start_parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    start_parser.add_argument("--port", type=int, default=8080, help="Bind port")
    start_parser.add_argument("--title", help="Dashboard title")
    start_parser.add_argument("--refresh", type=int, help="Refresh interval (seconds)")
    
    status_parser = dashboard_subparsers.add_parser("status", help="Check dashboard status")
    status_parser.add_argument("--host", default="127.0.0.1", help="Dashboard host")
    status_parser.add_argument("--port", type=int, default=8080, help="Dashboard port")
    
    sessions_parser = dashboard_subparsers.add_parser("sessions", help="List sessions via dashboard")
    sessions_parser.add_argument("--host", default="127.0.0.1", help="Dashboard host")
    sessions_parser.add_argument("--port", type=int, default=8080, help="Dashboard port")
    sessions_parser.add_argument("--json", action="store_true", help="JSON output")
    
    return dashboard_parser
