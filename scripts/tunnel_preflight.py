#!/usr/bin/env python3
"""Preflight checks for a tunnel handoff (either side, no circuit opened).

Usage:  python scripts/tunnel_preflight.py session.tokenade [--echo-url URL]

Checks (each PASS/FAIL/WARN, exit 0 only when nothing FAILs):
  1. jar loads and carries a v3.1 egress block with a known transport
  2. oracle snapshot present and signature/TTL-verified (when embedded)
  3. consumer token paired locally for the jar's remote_ref (consumer side)
  4. rendezvous reachable by TCP (relay host:port, or SSH box host:port)
  5. fingerprint present (warn when absent: native tier won't replay)

Run this on BOTH machines before attempting the handoff.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _tcp_reachable(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def _relay_host_port(relay_url: str) -> Tuple[str, int]:
    from urllib.parse import urlparse

    try:
        parsed = urlparse(relay_url)
        return parsed.hostname or "?", parsed.port or 0
    except Exception:
        return "?", 0


def check_jar(jar_path: str) -> Tuple[Dict[str, Any], List[Tuple[str, str]]]:
    """Load jar, return (package, checks). Pure offline."""
    from tokenade.core.importer.session_packager import SessionPackager
    from tokenade.core.session_runtime.oracle_snapshot import verify_snapshot

    checks: List[Tuple[str, str]] = []
    try:
        package = SessionPackager().load(jar_path)
    except Exception as exc:
        return {}, [("FAIL", f"jar unreadable: {exc}")]

    egress = package.get("egress")
    if not isinstance(egress, dict):
        return package, [("FAIL", "no egress block: re-export with --with-egress")]
    relay = egress.get("relay", {})
    transport = str(relay.get("transport", "") or "").lower()
    if transport not in ("wss-reverse", "ssh-reverse"):
        checks.append(("FAIL", f"unknown transport {transport!r}"))
    else:
        checks.append(("PASS", f"egress block: {transport}"))
    if not relay.get("remote_ref"):
        checks.append(("FAIL", "egress relay has no remote_ref"))
    if not package.get("fingerprint"):
        checks.append(("WARN", "no fingerprint: native tier will not replay"))
    else:
        checks.append(("PASS", "fingerprint embedded"))

    snapshot = package.get("oracle_snapshot")
    if isinstance(snapshot, dict):
        ok, reason, age = verify_snapshot(snapshot)
        checks.append((
            "PASS" if ok else ("WARN" if reason.startswith("valid-stale") else "FAIL"),
            f"oracle snapshot: {reason} (age {age:.0f}s)",
        ))
    else:
        checks.append(("WARN", "no oracle snapshot: scalar oracle answers unavailable"))
    return package, checks


def check_pairing(package: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Consumer-side token presence (offline, keyring only)."""
    from tokenade.core.tunnel.pairing import load_consumer_token

    relay = (package.get("egress") or {}).get("relay", {})
    ref = str(relay.get("remote_ref", "") or "")
    if not ref:
        return [("FAIL", "no remote_ref to look up")]
    try:
        load_consumer_token(ref)
        return [("PASS", f"consumer token paired for {ref!r} (keyring)")]
    except Exception as exc:
        return [("FAIL", f"no paired token for {ref!r}: {exc}; run tunnel pair")]


def check_reachability(package: Dict[str, Any]) -> List[Tuple[str, str]]:
    """TCP reachability of the rendezvous (no auth, no circuit)."""
    relay = (package.get("egress") or {}).get("relay", {})
    transport = str(relay.get("transport", "") or "").lower()
    if transport == "ssh-reverse":
        host = str(relay.get("ssh_host", "") or "")
        port = int(relay.get("ssh_port", 22) or 22)
        label = f"ssh box {host}:{port}"
    else:
        host, port = _relay_host_port(str(relay.get("rendezvous", "") or ""))
        label = f"relay {host}:{port}"
    if not host or host == "?" or not port:
        return [("FAIL", f"no address in egress block ({label})")]
    if _tcp_reachable(host, port):
        return [("PASS", f"{label} reachable")]
    return [("FAIL", f"{label} unreachable (origin/relay offline or firewalled?)")]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Tunnel handoff preflight checks")
    parser.add_argument("jar", help="Path to .tokenade file")
    args = parser.parse_args(argv)

    package, checks = check_jar(args.jar)
    if package:
        checks += check_pairing(package)
        checks += check_reachability(package)

    failed = 0
    for status, message in checks:
        print(f"[{status}] {message}")
        if status == "FAIL":
            failed += 1
    print(f"preflight: {'READY' if not failed else 'NOT READY'} "
          f"({len(checks) - failed}/{len(checks)} checks green)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
