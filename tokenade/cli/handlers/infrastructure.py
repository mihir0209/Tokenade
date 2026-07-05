"""
Infrastructure CLI commands — fleet, container, k8s.
"""

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("tokenade")


def cmd_fleet(args):
    """Fleet management — unified view across containers/pods."""
    from tokenade.core.integration.fleet import FleetManager

    fleet_action = getattr(args, "fleet_action", "status")
    manager = FleetManager()

    if fleet_action == "status":
        report = manager.status()
        fmt = getattr(args, "format", "text")
        if fmt == "json":
            print(report.to_json())
        else:
            print(report.to_table())

    elif fleet_action == "health":
        report = manager.health()
        fmt = getattr(args, "format", "text")
        if fmt == "json":
            print(report.to_json())
        else:
            print(report.to_table())

    elif fleet_action == "refresh":
        print("🔄 Refreshing sessions in all running containers...")
        results = manager.refresh_all()
        if not results:
            print("No running containers found")
            return
        for r in results:
            icon = "✅" if r["success"] else "❌"
            print(f"  {icon} {r['container']}")
            if r.get("error"):
                print(f"      {r['error'][:200]}")

    elif fleet_action == "logs":
        container = getattr(args, "container", None)
        if not container:
            print("❌ Specify container: tokenade fleet logs <container>")
            return
        lines = getattr(args, "lines", 50)
        output = manager.logs(container, lines=lines)
        print(output)

    else:
        print("Usage: tokenade fleet {status|health|refresh|logs}")
