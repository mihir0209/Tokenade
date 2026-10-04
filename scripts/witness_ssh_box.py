#!/usr/bin/env python3
"""Live SSH-box witness: full ssh-reverse E2E against a real SSH server.

Needs a reachable SSH box (your VPS). Env:
    TOKENADE_SSH_HOST         (required)  SSH box hostname
    TOKENADE_SSH_USER         (default: $USER or root)
    TOKENADE_SSH_PORT         (default: 22)
    TOKENADE_SSH_KEY          (optional)  private key path
    TOKENADE_SSH_PASSWORD     (optional)  or use agent/keys
    TOKENADE_SSH_REMOTE_PORT  (required)  forwarded port on the box
    TOKENADE_ECHO_URL         (optional)  echo responder for egress check

Flow: origin reverse-forwards box:REMOTE_PORT (thread) -> consumer opens
SshTunnelSession -> echo/oracle/fetch checks -> verdict. Prints SKIP and
exits 0 when env is absent (no box available).
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def main() -> int:
    host = _env("TOKENADE_SSH_HOST")
    remote_port = _env("TOKENADE_SSH_REMOTE_PORT")
    if not host or not remote_port:
        print("[SKIP] witness_ssh_box: set TOKENADE_SSH_HOST and "
              "TOKENADE_SSH_REMOTE_PORT to run against a real box.")
        return 0

    from tokenade.core.tunnel.ssh_reverse import SshReverseOrigin, SshTunnelSession

    user = _env("TOKENADE_SSH_USER") or os.environ.get("USER", "root")
    port = int(_env("TOKENADE_SSH_PORT", "22") or 22)
    remote_port_i = int(remote_port)
    token = secrets.token_urlsafe(24)
    snapshot = {"navigator.platform": "WitnessOS"}

    origin = SshReverseOrigin(
        ssh_host=host, ssh_port=port, ssh_user=user,
        remote_port=remote_port_i,
        key_path=_env("TOKENADE_SSH_KEY") or None,
        password=_env("TOKENADE_SSH_PASSWORD") or None,
        consumer_tokens={token},
        snapshot_values=snapshot,
        oracle_allowlist=["navigator.platform"],
    )
    thread = threading.Thread(target=origin.serve_forever, kwargs={"poll_s": 1.0},
                              daemon=True)
    thread.start()

    failures = []
    try:
        import time

        time.sleep(3)  # let the reverse-forward establish
        session = SshTunnelSession(host, port, remote_port_i, token)
        session.open(timeout_s=30.0)
        try:
            value = session.query("navigator.platform", timeout_s=20.0)
            print(f"[OK] oracle: navigator.platform={value!r}")
            if value != "WitnessOS":
                failures.append(f"oracle value mismatch: {value!r}")
        except Exception as exc:
            failures.append(f"oracle query failed: {exc}")

        echo_url = _env("TOKENADE_ECHO_URL")
        if echo_url:
            try:
                echo = session._submit(
                    session._fetch_echo(echo_url), 25.0)
                print(f"[OK] echo: {echo}")
            except Exception as exc:
                failures.append(f"echo failed: {exc}")

        proxy = session.local_proxy["server"]
        print(f"[OK] listener: {proxy}")
        req = urllib.request.Request("http://example.com")
        req.set_proxy(proxy, "http")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read(200)
                ok = resp.status == 200 and b"Example" in body
                print(f"[{'OK' if ok else 'FAIL'}] via-box fetch: {resp.status}")
                if not ok:
                    failures.append("via-box fetch content mismatch")
        except Exception as exc:
            failures.append(f"via-box fetch failed: {exc}")
    except Exception as exc:
        failures.append(f"circuit open failed: {exc}")
    finally:
        try:
            session.close()
        except Exception:
            pass
        origin.stop()

    if failures:
        print("[FAIL] witness_ssh_box:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("[PASS] witness_ssh_box: ssh-reverse E2E through a real box")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
