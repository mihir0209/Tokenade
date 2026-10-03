"""
Synchronous bridge - TunnelSession for sync CLI flows (launch/load).

ConsumerCircuit is asyncio-native, but tokenade's CLI is synchronous and the
browser must stay up for minutes/hours while the circuit lives. TunnelSession
owns a background thread + event loop for the circuit's lifetime:

    session = open_tunnel_for_jar(package, mode="auto", echo_url=...)
    try:
        plan = RuntimePlanBuilder().build(package, tunnel={...session bits...},
                                          cli_overrides={"tunnel": "auto"})
        ... launch browser with plan ...
    finally:
        session.close()

Fail-closed: open() raises (AuthError / EgressCheckError / TunnelError) and
returns NO proxy when the circuit cannot be verified. There is no
direct-fallback path here by design.
"""

import asyncio
import hashlib
import logging
import threading
from typing import Any, Dict, Optional

from tokenade.core.session_runtime.policy import (
    EgressCheckError,
    enforce_egress,
    resolve_policy,
)
from tokenade.core.tunnel.consumer import ConsumerCircuit
from tokenade.core.tunnel.errors import TunnelError
from tokenade.core.tunnel.pairing import load_consumer_token

logger = logging.getLogger(__name__)


class TunnelSession:
    """A paired origin-egress circuit with a thread-owned event loop."""

    def __init__(
        self,
        relay_url: str,
        remote_ref: str,
        consumer_token: str,
        echo_url: Optional[str] = None,
        split: Optional[Dict[str, Any]] = None,
    ):
        self.relay_url = relay_url
        self.remote_ref = remote_ref
        self._consumer_token = consumer_token
        self.echo_url = echo_url
        self.split = split or {"enabled": False, "domains": [], "mode": "off"}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._circuit: Optional[ConsumerCircuit] = None
        self.echo: Dict[str, Any] = {}

    # -- lifecycle --

    def open(self, timeout_s: float = 30.0) -> "TunnelSession":
        """Connect, pair, start loopback listener, run egress echo."""
        import atexit

        atexit.register(self.close)
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, daemon=True,
                                  name=f"tokenade-tunnel-{self.remote_ref}")
        thread.start()
        self._loop = loop
        self._thread = thread
        try:
            self.echo = self._submit(self._setup(), timeout_s)
        except Exception:
            self.close()
            raise
        return self

    async def _setup(self) -> Dict[str, Any]:
        circuit = ConsumerCircuit(self.relay_url, self.remote_ref, self._consumer_token,
                                  split=self.split)
        await circuit.ensure_connected()
        await circuit.serve_local_listener()
        self._circuit = circuit
        if self.echo_url:
            return await circuit.egress_echo(self.echo_url)
        return {}

    def _submit(self, coro, timeout_s: float):
        if self._loop is None:
            raise TunnelError("tunnel session not open")
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout_s)

    def query(self, method: str, args: Any = None, timeout_s: float = 15.0) -> Any:
        """Thread-safe oracle query against the live circuit."""
        if self._circuit is None:
            raise TunnelError("tunnel session not open")
        return self._submit(self._circuit.query(method, args, timeout_s), timeout_s)

    @property
    def local_proxy(self) -> Optional[Dict[str, str]]:
        """Playwright-ready proxy dict (None until open)."""
        if self._circuit is None:
            return None
        return self._circuit.local_proxy

    @property
    def oracle(self) -> Dict[str, Any]:
        """Oracle config for RuntimePlanBuilder (live while open)."""
        from tokenade.core.session_runtime.plan import ORACLE_ALLOWLIST

        if self._circuit is None:
            return {"mode": "off", "allowlist": list(ORACLE_ALLOWLIST)}
        return {"mode": "live", "allowlist": list(ORACLE_ALLOWLIST)}

    def close(self) -> None:
        """Tear down circuit and thread (idempotent)."""
        try:
            if self._loop is not None and self._circuit is not None:
                fut = asyncio.run_coroutine_threadsafe(self._circuit.close(), self._loop)
                try:
                    fut.result(10)
                except Exception:
                    pass
        finally:
            self._circuit = None
            if self._loop is not None:
                try:
                    self._loop.call_soon_threadsafe(self._loop.stop)
                except Exception:
                    pass
            if self._thread is not None:
                self._thread.join(timeout=10)
                self._thread = None
            if self._loop is not None:
                try:
                    self._loop.close()
                except Exception:
                    pass
                self._loop = None


def open_tunnel_for_jar(
    package: Dict[str, Any],
    *,
    mode: str = "auto",
    relay_url: Optional[str] = None,
    echo_url: Optional[str] = None,
    timeout_s: float = 30.0,
    allow_unpaired: bool = False,
    tunnel_split: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Open a verified tunnel session for a jar (or None when mode=off).

    Returns the tunnel-state dict consumed by RuntimePlanBuilder, with an
    extra "_session" key holding the TunnelSession (caller MUST close it).
    Raises EgressCheckError / AuthError / TunnelError fail-closed.
    """
    from tokenade.core.session_runtime.policy import FALLBACK_DIRECT
    from tokenade.core.session_runtime.split import resolve_split

    if str(mode).lower() == "off":
        return None
    split = resolve_split(package, tunnel_split)
    if split["enabled"] and not split["domains"]:
        raise EgressCheckError(
            "Split routing enabled but no domains resolved — refusing, "
            "because an empty list would send EVERYTHING direct."
        )
    egress = package.get("egress") if isinstance(package, dict) else None
    if not isinstance(egress, dict):
        if allow_unpaired:
            return None
        raise EgressCheckError(
            "Tunnel requested but jar has no egress block. Export with "
            "--with-egress (or pair the jar) so the circuit can be verified; "
            "refusing to proceed."
        )
    relay = egress.get("relay", {}) if isinstance(egress.get("relay"), dict) else {}
    remote_ref = str(relay.get("remote_ref", "") or "")
    rendezvous = relay_url or str(relay.get("rendezvous", "") or "")
    if not remote_ref or not rendezvous:
        raise EgressCheckError(
            "Jar egress block is missing relay.remote_ref/rendezvous; "
            "re-export with --with-egress."
        )
    token = load_consumer_token(remote_ref)
    transport = str(relay.get("transport", "wss-reverse")).lower()
    if transport == "ssh-reverse":
        session = _open_ssh_session(relay, remote_ref, token,
                                    echo_url or relay.get("echo_url"),
                                    timeout_s, split)
    elif transport == "wss-reverse":
        session = TunnelSession(
            rendezvous, remote_ref, token,
            echo_url=echo_url or relay.get("echo_url"),
            split=split,
        )
        session.open(timeout_s=timeout_s)
    else:
        raise EgressCheckError(
            f"Unknown egress transport {transport!r} (want wss-reverse|ssh-reverse)."
        )
    hint = egress.get("origin_hint", {}) if isinstance(egress.get("origin_hint"), dict) else {}
    policy = resolve_policy(package)
    state: Dict[str, Any] = {
        "local_proxy": session.local_proxy,
        "oracle": session.oracle,
        "egress_echo": session.echo,
        "split": split,
        "_session": session,
    }
    if session.echo:
        action, message = enforce_egress(session.echo, hint, policy)
        state["egress_check"] = {"action": action, "message": message}
        if action == "deny":
            session.close()
            raise EgressCheckError(message)
        if action == "warn":
            logger.warning(message)
    else:
        state["egress_check"] = {
            "action": "unverified" if policy.get("fallback") != FALLBACK_DIRECT else "skipped",
            "message": ("paired but egress unverified (no echo_url); "
                        "pass --tunnel-echo-url for a verified check"),
        }
        logger.warning(state["egress_check"]["message"])
    return state


def _open_ssh_session(relay: Dict[str, Any], remote_ref: str, token: str,
                      echo_url: Optional[str], timeout_s: float,
                      split: Optional[Dict[str, Any]] = None):
    """Open an ssh-reverse consumer session from a jar relay block."""
    from urllib.parse import urlparse as _urlparse

    from tokenade.core.tunnel.ssh_reverse import SshTunnelSession

    ssh_host = str(relay.get("ssh_host", "") or "")
    ssh_port = int(relay.get("ssh_port", 22) or 22)
    rendezvous = str(relay.get("rendezvous", "") or "")
    if rendezvous.startswith("ssh://") and not ssh_host:
        parsed = _urlparse(rendezvous)
        ssh_host = parsed.hostname or ""
        ssh_port = parsed.port or 22
    try:
        remote_port = int(relay.get("ssh_remote_port", 0) or 0)
    except (TypeError, ValueError):
        remote_port = 0
    if not ssh_host or not remote_port:
        raise EgressCheckError(
            "SSH egress block needs relay.ssh_host and relay.ssh_remote_port; "
            "re-export with --egress-transport ssh-reverse --egress-ssh-host H "
            "--egress-ssh-remote-port R."
        )
    session = SshTunnelSession(ssh_host, ssh_port, remote_port, token,
                               echo_url=echo_url,
                               split=split or {"enabled": False, "domains": [],
                                               "mode": "off"})
    session.open(timeout_s=timeout_s)
    return session


def snapshot_values_from_fingerprint(fingerprint: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Project a jar fingerprint dict onto oracle answer values.

    Only scalar/metadata fields (the oracle-allowlisted tier). Render-tier
    values are never snapshotted — see plan doc §3.2.
    """
    if not isinstance(fingerprint, dict):
        return {}
    mapping = {
        "navigator.userAgent": "user_agent",
        "navigator.platform": "platform",
        "navigator.language": "language",
        "navigator.languages": "languages",
        "navigator.hardwareConcurrency": "hardware_concurrency",
        "navigator.deviceMemory": "device_memory",
        "navigator.maxTouchPoints": "max_touch_points",
        "screen.width": "screen_width",
        "screen.height": "screen_height",
        "screen.colorDepth": "color_depth",
        "window.devicePixelRatio": "device_pixel_ratio",
        "window.innerWidth": "viewport_width",
        "window.innerHeight": "viewport_height",
        "Intl.timeZone": "timezone",
        "Intl.locale": "language",
        "webgl.vendor": "webgl_vendor",
        "webgl.renderer": "webgl_renderer",
        "fonts.list": "fonts",
    }
    values: Dict[str, Any] = {}
    for probe, field in mapping.items():
        value = fingerprint.get(field)
        if value is None or value == "" or value == []:
            continue
        values[probe] = value
    return values


def capture_egress_block(
    *,
    relay_url: str,
    remote_ref: str,
    fingerprint: Optional[Dict[str, Any]] = None,
    echo_url: Optional[str] = None,
    policy_fallback: str = "deny",
    timeout_s: float = 20.0,
    transport: str = "wss-reverse",
    ssh_host: str = "",
    ssh_port: int = 22,
    ssh_remote_port: int = 0,
) -> Dict[str, Any]:
    """Build a v3.1 egress block + signed oracle snapshot for export.

    Reuses capture_source_network for country/ASN; the raw IP is hashed
    (sha256) and never stored. Returns {"egress": ..., "oracle_snapshot": ...}.
    """
    import hashlib as _hashlib

    from tokenade.core.network.source_context import capture_source_network
    from tokenade.core.session_runtime.oracle_snapshot import (
        generate_origin_keypair,
        sign_snapshot,
    )

    network = capture_source_network(include_source_ip=True)
    hint: Dict[str, Any] = {
        "country": network.get("approx_country") or "",
        "asn": network.get("asn") or "",
    }
    raw_ip = network.get("ip") or ""
    if raw_ip:
        hint["ip_hash"] = "sha256:" + _hashlib.sha256(raw_ip.encode()).hexdigest()
    relay: Dict[str, Any] = {
        "transport": transport,
        "rendezvous": relay_url,
        "remote_ref": remote_ref,
        **({"echo_url": echo_url} if echo_url else {}),
    }
    if transport == "ssh-reverse":
        relay.update({"ssh_host": ssh_host, "ssh_port": ssh_port,
                      "ssh_remote_port": ssh_remote_port})
    egress = {
        "mode": "origin-relay",
        "relay": relay,
        "origin_hint": hint,
        "policy": {"required": True, "fallback": policy_fallback},
    }
    values = snapshot_values_from_fingerprint(fingerprint)
    _priv, _pub = generate_origin_keypair()
    snapshot = sign_snapshot(values, _priv)
    return {"egress": egress, "oracle_snapshot": snapshot}
