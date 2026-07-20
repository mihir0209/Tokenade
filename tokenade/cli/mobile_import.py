"""
Mobile Import CLI command.

Import browser sessions from mobile devices.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional


def cmd_mobile_import(args: argparse.Namespace) -> None:
    """Import sessions from mobile devices."""
    from tokenade.core.importer.mobile_importer import MobileImporter, MobileImportError
    from tokenade.cli.output import print_json, print_section

    print_section("Tokenade Mobile Import", style="bold blue")

    importer = MobileImporter()

    if args.list_devices:
        # List connected devices
        devices = importer.detect_devices()
        if not devices:
            print("\n❌ No mobile devices detected")
            print("\n💡 Tips:")
            print("   • Android: Enable USB debugging and connect via USB")
            print("   • iOS: Use iTunes backup or jailbreak for direct access")
            sys.exit(1)

        print(f"\n📱 Found {len(devices)} device(s):")
        for i, device in enumerate(devices):
            status = "✅ Connected" if device.connected else "❌ Disconnected"
            print(f"   {i+1}. {device.name} ({device.platform}) - {status}")

        if args.json:
            print_json({"devices": [
                {"name": d.name, "platform": d.platform, "connected": d.connected}
                for d in devices
            ]})
        sys.exit(0)

    if args.backup_path:
        # Import from backup
        try:
            session = importer.import_from_backup(
                backup_path=args.backup_path,
                platform=args.platform or "android",
                site_name=args.site,
                output_dir=args.output_dir,
            )

            output_file = importer.export_to_tokenade(session, args.output_dir or ".")
            print(f"\n✅ Session imported successfully")
            print(f"   Output: {output_file}")
            print(f"   Site: {session.site_name}")
            print(f"   Cookies: {len(session.cookies)}")
            print(f"   Platform: {session.platform}")

        except MobileImportError as e:
            print(f"\n❌ Import failed: {e}")
            sys.exit(1)

    else:
        # Import from connected device
        devices = importer.detect_devices()
        if not devices:
            print("\n❌ No mobile devices detected")
            sys.exit(1)

        device = devices[0]  # Use first connected device
        if args.device_index:
            idx = args.device_index - 1
            if 0 <= idx < len(devices):
                device = devices[idx]
            else:
                print(f"\n❌ Invalid device index: {args.device_index}")
                sys.exit(1)

        try:
            session = importer.import_from_device(
                device=device,
                site_name=args.site,
                output_dir=args.output_dir,
            )

            output_file = importer.export_to_tokenade(session, args.output_dir or ".")
            print(f"\n✅ Session imported successfully")
            print(f"   Output: {output_file}")
            print(f"   Device: {device.name}")
            print(f"   Site: {session.site_name}")
            print(f"   Cookies: {len(session.cookies)}")

        except MobileImportError as e:
            print(f"\n❌ Import failed: {e}")
            sys.exit(1)


def register_mobile_import_command(subparsers: argparse._SubParsersAction) -> None:
    """Register mobile-import command."""
    parser = subparsers.add_parser(
        "mobile-import",
        help="Import sessions from mobile devices",
        description="Import browser sessions from Android (ADB) or iOS (iTunes backup) devices",
    )

    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List connected mobile devices",
    )
    parser.add_argument(
        "--backup-path",
        help="Path to iOS/Android backup directory",
    )
    parser.add_argument(
        "--platform",
        choices=["android", "ios"],
        help="Platform type (for backup import)",
    )
    parser.add_argument(
        "--site",
        help="Specific site to import (default: all)",
    )
    parser.add_argument(
        "--device-index",
        type=int,
        help="Device index if multiple devices connected (1-based)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=".",
        help="Output directory for imported sessions",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")

    parser.set_defaults(func=cmd_mobile_import)
