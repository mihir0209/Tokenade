"""Tunnel CLI - origin-egress circuits (`tokenade tunnel ...`).

Subcommands:
  serve    Run the origin daemon (export machine; outbound-only).
  share    Mint a pairing code + bundle for one consumer.
  pair     Redeem a code/bundle on the using machine.
  status   Show paired remotes, token presence, relay reachability.
  revoke   Remove a consumer token (origin side).
  token    Show where a remote's token lives (never prints the secret).
  relay    Run the self-hosted reference relay (rendezvous).
"""
import asyncio
import json
import logging
import socket
from pathlib import Path

logger = logging.getLogger("tokenade")

APPROVED_STORE = Path.home() / ".tokenade" / "tunnel" / "approved.json"


def _load_approved(store: Path = APPROVED_STORE) -> dict:
    if not store.exists():
        return {}
    try:
        data = json.loads(store.read_text())
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def _save_approved(data: dict, store: Path = APPROVED_STORE) -> None:
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps(data, indent=2))
    try:
        import os

        os.chmod(store, 0o600)
    except OSError:
        pass


def cmd_tunnel(args):
    """Dispatch `tokenade tunnel <action>`."""
    action = getattr(args, "tunnel_action", None) or "status"
    handler = {
        "serve": cmd_tunnel_serve,
        "share": cmd_tunnel_share,
        "pair": cmd_tunnel_pair,
        "status": cmd_tunnel_status,
        "revoke": cmd_tunnel_revoke,
        "token": cmd_tunnel_token,
        "relay": cmd_tunnel_relay,
    }.get(action)
    if handler is None:
        print(f"[ERROR] Unknown tunnel action: {action}")
        raise SystemExit(2)
    return handler(args)


def cmd_tunnel_serve(args):
    """Run the origin daemon: outbound-only, reconnects forever."""
    import time

    from tokenade.core.session_runtime.plan import ORACLE_ALLOWLIST
    from tokenade.core.tunnel.origin import OriginEndpoint

    relay_url = getattr(args, "relay", None)
    remote_ref = getattr(args, "remote_ref", None)
    if not relay_url or not remote_ref:
        print("[ERROR] serve needs --relay ws://host:port and --remote-ref NAME")
        raise SystemExit(2)

    snapshot_values = {}
    snapshot_file = getattr(args, "snapshot_file", None)
    if snapshot_file:
        try:
            snapshot_values = json.loads(Path(snapshot_file).read_text())
        except (ValueError, OSError) as exc:
            print(f"[ERROR] Cannot read --snapshot-file: {exc}")
            raise SystemExit(2)

    extra_tokens = getattr(args, "token", None) or []
    print("\n" + "=" * 80)
    print("TOKENADE - Tunnel Origin Daemon")
    print("=" * 80)
    print(f"   Relay:      {relay_url}")
    print(f"   Remote ref: {remote_ref}")
    print("   Mode:       outbound-only (no listening sockets)")
    print("   Stop:       Ctrl+C")
    print("=" * 80 + "\n")

    delay = 1.0
    try:
        while True:
            approved = _load_approved()
            tokens = set(approved.get(remote_ref, [])) | set(extra_tokens)
            if not tokens:
                print("[WARN] No consumer tokens approved for "
                      f"{remote_ref} — run `tokenade tunnel share` first. Retrying...")
            endpoint = OriginEndpoint(
                relay_url, remote_ref, consumer_tokens=tokens,
                snapshot_values=snapshot_values,
                oracle_allowlist=list(ORACLE_ALLOWLIST),
            )
            try:
                asyncio.run(endpoint.start())
                print("[WARN] Relay connection dropped; reconnecting...")
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                print(f"[WARN] Origin error ({exc}); retrying in {delay:.0f}s...")
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
    except KeyboardInterrupt:
        print("\n[STOP] Origin daemon stopped.")


def cmd_tunnel_share(args):
    """Mint a pairing code + cross-machine bundle; approve the token."""
    import secrets

    from tokenade.core.tunnel.pairing import create_pairing

    relay_url = getattr(args, "relay", None)
    remote_ref = getattr(args, "remote_ref", None)
    if not relay_url or not remote_ref:
        print("[ERROR] share needs --relay ws://host:port and --remote-ref NAME")
        raise SystemExit(2)
    token = getattr(args, "token", None) or secrets.token_urlsafe(24)
    created = create_pairing(remote_ref, relay_url, token)
    approved = _load_approved()
    approved.setdefault(remote_ref, [])
    if token not in approved[remote_ref]:
        approved[remote_ref].append(token)
    _save_approved(approved)
    bundle = json.dumps(
        {"relay_url": relay_url, "remote_ref": remote_ref, "consumer_token": token}
    )
    print("\n[OK] Pairing created (single-use code):")
    print(f"   Code:   {created['code']}")
    print("   Bundle (cross-machine; hand to the consumer out-of-band):")
    print(f"   {bundle}")
    print("\n   Consumer runs: tokenade tunnel pair '<bundle>'")
    print("   Origin daemon: tokenade tunnel serve --relay "
          f"{relay_url} --remote-ref {remote_ref}")


def cmd_tunnel_pair(args):
    """Redeem a code (same machine) or bundle (cross-machine)."""
    from tokenade.core.tunnel.pairing import redeem_pairing, save_consumer_record

    code = (getattr(args, "code", None) or "").strip()
    bundle_file = getattr(args, "bundle_file", None)
    if bundle_file:
        try:
            code = Path(bundle_file).read_text().strip()
        except OSError as exc:
            print(f"[ERROR] Cannot read --bundle-file: {exc}")
            raise SystemExit(2)
    if not code:
        print("[ERROR] pair needs a code or bundle: tokenade tunnel pair '<code>'")
        raise SystemExit(2)
    if code.startswith("{"):
        try:
            details = json.loads(code)
            record = {
                "remote_ref": details["remote_ref"],
                "relay_url": details["relay_url"],
                "consumer_token": details["consumer_token"],
            }
        except (ValueError, KeyError) as exc:
            print(f"[ERROR] Bad bundle: {exc}")
            raise SystemExit(2)
    else:
        try:
            record = redeem_pairing(code)
        except Exception as exc:
            print(f"[ERROR] Pairing failed: {exc}")
            raise SystemExit(2)
    save_consumer_record(record["remote_ref"], record["relay_url"], record["consumer_token"])
    print(f"\n[OK] Paired '{record['remote_ref']}' via {record['relay_url']}")
    print("   Token stored in OS keyring (never in the jar).")
    print(f"   Use: tokenade load session.tokenade --tunnel auto")


def cmd_tunnel_status(args):
    """Show paired remotes, token presence, relay reachability."""
    from tokenade.core.tunnel.pairing import _tunnel_dir

    consumers_path = _tunnel_dir() / "consumers.json"
    try:
        records = json.loads(consumers_path.read_text())
    except (ValueError, OSError):
        records = {}
    want = getattr(args, "remote_ref", None)
    if want:
        records = {want: records.get(want, {})} if want in records else {}

    if not records:
        print("No paired remotes. Run `tokenade tunnel pair '<bundle>'` first.")
        return
    for ref, rec in records.items():
        relay_url = (rec or {}).get("relay_url", "?")
        try:
            from tokenade.core.tunnel.pairing import load_consumer_token

            load_consumer_token(ref)
            token_state = "present (keyring)"
        except Exception as exc:
            token_state = f"MISSING ({exc})"
        host, port = _relay_host_port(relay_url)
        reachable = _tcp_probe(host, port)
        print(f"   {ref}: relay={relay_url} token={token_state} "
              f"relay_reachable={reachable}")


def cmd_tunnel_revoke(args):
    """Remove a consumer token (origin side) so it can no longer pair."""
    remote_ref = getattr(args, "remote_ref", None)
    token = getattr(args, "token", None)
    if not remote_ref:
        print("[ERROR] revoke needs --remote-ref NAME [--token ...]")
        raise SystemExit(2)
    approved = _load_approved()
    tokens = approved.get(remote_ref, [])
    if token:
        approved[remote_ref] = [t for t in tokens if t != token]
    else:
        approved.pop(remote_ref, None)
    _save_approved(approved)
    print(f"[OK] Revoked {remote_ref} ({'one token' if token else 'all tokens'}). "
          "Restart `tunnel serve` or wait for its approved-store reload.")


def cmd_tunnel_token(args):
    """Show where a remote's token lives (never prints the secret)."""
    remote_ref = getattr(args, "remote_ref", None)
    if not remote_ref:
        print("[ERROR] token needs --remote-ref NAME (or use `tunnel status`)")
        raise SystemExit(2)
    print(f"   {remote_ref}: keyring service=tokenade-tunnel account={remote_ref}")


def cmd_tunnel_relay(args):
    """Run the self-hosted reference relay (rendezvous)."""
    from tokenade.core.tunnel.relay import RelayServer

    host = getattr(args, "host", None) or "127.0.0.1"
    port = int(getattr(args, "port", None) or 8765)
    print(f"Relay on {host}:{port} (Ctrl+C to stop)")
    server = RelayServer(host, port)
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        pass


def _relay_host_port(relay_url: str):
    try:
        from urllib.parse import urlparse

        parsed = urlparse(relay_url)
        return parsed.hostname or "?", parsed.port or 0
    except Exception:
        return "?", 0


def _tcp_probe(host: str, port: int) -> bool:
    if not host or host == "?" or not port:
        return False
    try:
        with socket.create_connection((host, port), timeout=5):
            return True
    except OSError:
        return False
