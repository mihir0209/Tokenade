"""
Batch CLI commands for Tokenade.

Provides batch export, load, and refresh capabilities.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional


def cmd_batch_export(args: argparse.Namespace) -> None:
    """Export all sessions from discovered browsers."""
    from tokenade.core.batch.operations import BatchExporter
    from tokenade.cli.output import print_json, print_section

    print_section("Tokenade Batch Export", style="bold blue")

    exporter = BatchExporter(max_workers=args.workers)
    result = exporter.export_all(
        output_dir=args.output_dir,
        browsers=args.browsers.split(",") if args.browsers else None,
        sites=args.sites.split(",") if args.sites else None,
    )

    if args.json:
        print_json(result.to_dict())
    else:
        print("\n[STATS] Results:")
        print(f"   Total: {result.total}")
        print(f"   [OK] Success: {len(result.successes)}")
        print(f"   [ERROR] Failed: {len(result.failures)}")
        print(f"   [TIME] Duration: {result.duration:.1f}s")

        if result.successes:
            print("\n[OK] Successful exports:")
            for item in result.successes:
                print(f"   - {item['browser']} -> {item.get('session_file', 'unknown')}")

        if result.failures:
            print("\n[ERROR] Failed exports:")
            for item in result.failures:
                print(f"   - {item['item']['browser']}: {item['error']}")

    sys.exit(0 if result.failures == 0 else 1)


def cmd_batch_load(args: argparse.Namespace) -> None:
    """Load all sessions from a directory."""
    from tokenade.core.batch.operations import BatchLoader
    from tokenade.cli.output import print_json, print_section

    print_section("Tokenade Batch Load", style="bold blue")

    loader = BatchLoader(max_workers=args.workers)
    result = loader.load_all(
        session_dir=args.session_dir,
        pattern=args.pattern,
        browser_name=args.browser,
        visible=args.visible,
    )

    if args.json:
        print_json(result.to_dict())
    else:
        print("\n[STATS] Results:")
        print(f"   Total: {result.total}")
        print(f"   [OK] Success: {len(result.successes)}")
        print(f"   [ERROR] Failed: {len(result.failures)}")
        print(f"   [TIME] Duration: {result.duration:.1f}s")

        if result.successes:
            print("\n[OK] Successful loads:")
            for item in result.successes:
                print(f"   - {item['session_file']} -> {item['browser']}")

        if result.failures:
            print("\n[ERROR] Failed loads:")
            for item in result.failures:
                print(f"   - {item['item']['session_file']}: {item['error']}")

    sys.exit(0 if result.failures == 0 else 1)


def cmd_batch_refresh(args: argparse.Namespace) -> None:
    """Refresh all sessions in a directory."""
    from tokenade.core.batch.operations import BatchRefresher
    from tokenade.cli.output import print_json, print_section

    print_section("Tokenade Batch Refresh", style="bold blue")

    refresher = BatchRefresher(max_workers=args.workers)
    result = refresher.refresh_all(
        session_dir=args.session_dir,
        pattern=args.pattern,
        output_dir=args.output_dir,
    )

    if args.json:
        print_json(result.to_dict())
    else:
        print("\n[STATS] Results:")
        print(f"   Total: {result.total}")
        print(f"   [OK] Success: {len(result.successes)}")
        print(f"   [ERROR] Failed: {len(result.failures)}")
        print(f"   [TIME] Duration: {result.duration:.1f}s")

        if result.successes:
            print("\n[OK] Successful refreshes:")
            for item in result.successes:
                print(f"   - {item['original']} -> {item['refreshed']}")

        if result.failures:
            print("\n[ERROR] Failed refreshes:")
            for item in result.failures:
                print(f"   - {item['item']['session_file']}: {item['error']}")

    sys.exit(0 if result.failures == 0 else 1)


def register_batch_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register batch subcommands."""

    batch_parser = subparsers.add_parser(
        "batch",
        help="Batch operations for multiple sessions",
        description="Batch export, load, and refresh sessions in parallel",
    )
    batch_subparsers = batch_parser.add_subparsers(dest="batch_command")

    # batch export
    export_parser = batch_subparsers.add_parser(
        "export",
        help="Export all sessions from discovered browsers",
        description="Export sessions from all discovered browsers in parallel",
    )
    export_parser.add_argument(
        "-o", "--output-dir",
        required=True,
        help="Output directory for exported sessions",
    )
    export_parser.add_argument(
        "--browsers",
        help="Comma-separated list of browser names (default: all)",
    )
    export_parser.add_argument(
        "--sites",
        help="Comma-separated list of sites (default: all)",
    )
    export_parser.add_argument(
        "-w", "--workers",
        type=int,
        default=4,
        help="Number of parallel workers (default: 4)",
    )
    export_parser.add_argument("--json", action="store_true", help="Output JSON")
    export_parser.set_defaults(func=cmd_batch_export)

    # batch load
    load_parser = batch_subparsers.add_parser(
        "load",
        help="Load all sessions from a directory",
        description="Load multiple sessions into browsers in parallel",
    )
    load_parser.add_argument(
        "session_dir",
        help="Directory containing session files",
    )
    load_parser.add_argument(
        "-p", "--pattern",
        default="*.tokenade",
        help="File pattern to match (default: *.tokenade)",
    )
    load_parser.add_argument(
        "-b", "--browser",
        help="Target browser name (default: auto-detect)",
    )
    load_parser.add_argument(
        "-w", "--workers",
        type=int,
        default=4,
        help="Number of parallel workers (default: 4)",
    )
    load_parser.add_argument(
        "--visible",
        action="store_true",
        help="Run browser in visible mode",
    )
    load_parser.add_argument("--json", action="store_true", help="Output JSON")
    load_parser.set_defaults(func=cmd_batch_load)

    # batch refresh
    refresh_parser = batch_subparsers.add_parser(
        "refresh",
        help="Refresh all sessions in a directory",
        description="Refresh multiple sessions in parallel",
    )
    refresh_parser.add_argument(
        "session_dir",
        help="Directory containing session files",
    )
    refresh_parser.add_argument(
        "-p", "--pattern",
        default="*.tokenade",
        help="File pattern to match (default: *.tokenade)",
    )
    refresh_parser.add_argument(
        "-o", "--output-dir",
        help="Output directory for refreshed sessions (default: in-place)",
    )
    refresh_parser.add_argument(
        "-w", "--workers",
        type=int,
        default=4,
        help="Number of parallel workers (default: 4)",
    )
    refresh_parser.add_argument("--json", action="store_true", help="Output JSON")
    refresh_parser.set_defaults(func=cmd_batch_refresh)
