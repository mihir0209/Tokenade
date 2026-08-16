#!/usr/bin/env python3
"""CI witness for real multi-site proxy startup, routing, and cleanup."""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import sys
import urllib.request
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tokenade.core.proxy.multi_site_proxy import MultiSiteProxy


def _free_base_port() -> int:
    for base in range(19000, 29000, 10):
        ports = range(base, base + 5)
        sockets = []
        try:
            for port in ports:
                sock = socket.socket()
                sock.bind(("127.0.0.1", port))
                sockets.append(sock)
            return base
        except OSError:
            pass
        finally:
            for sock in sockets:
                sock.close()
    raise RuntimeError("Could not reserve a five-port range")


def _get_json(url: str):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read())


def _probe(url: str) -> None:
    with urllib.request.urlopen(url, timeout=5) as response:
        response.read(1)


async def main() -> int:
    sessions = [
        {
            "site_name": "witness-a",
            "auth_status": "unknown",
            "cookies": [
                {"name": "a", "value": "1", "domain": ".example.com", "path": "/"}
            ],
        },
        {
            "site_name": "witness-b",
            "auth_status": "unknown",
            "cookies": [
                {"name": "b", "value": "2", "domain": ".example.org", "path": "/"}
            ],
        },
    ]
    base = _free_base_port()
    proxy = MultiSiteProxy(sessions, base_port=base)
    task = asyncio.create_task(proxy.start())
    try:
        for _ in range(60):
            try:
                items = await asyncio.to_thread(
                    _get_json, f"http://127.0.0.1:{base}/api/sessions"
                )
                break
            except Exception:
                if task.done():
                    await task
                await asyncio.sleep(1)
        else:
            raise RuntimeError("Multi-site master API did not become ready")

        expected_ports = [base + 1, base + 3]
        if [item["port"] for item in items] != expected_ports:
            raise RuntimeError(f"Unexpected child ports: {items}")

        for port in [base, *expected_ports]:
            await asyncio.to_thread(_probe, f"http://127.0.0.1:{port}/")
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    for port in range(base, base + 5):
        with closing(socket.socket()) as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(f"Port {port} remains open after shutdown")

    print(f"Multi-site witness passed on ports {base}-{base + 4}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(asyncio.run(main()))
