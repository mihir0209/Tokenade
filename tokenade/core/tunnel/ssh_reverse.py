"""
SSH-reverse transport - Origin egress through the user's own SSH box.

No Tokenade relay needed: the origin dials OUT to a user-provided SSH
server (paramiko, already a core dep) and asks it to listen on a remote
port (`ssh -R` semantics). The consumer opens plain TCP to
sshbox:remote_port and speaks HTTP-proxy protocol; the origin dials target
sites from the export machine (origin egress) and pipes bytes back.

  consumer ──TCP──▶ sshbox:remote_port ──SSH channel──▶ origin ──dial──▶ site

Authentication: Bearer consumer token checked by the origin proxy on every
request (407 otherwise). The SSH box itself is untrusted transport: it sees
CONNECT host:port, never content (TLS stays end-to-end).

Special hosts (answered by the origin, never dialed):
  tokenade.echo    GET http://tokenade.echo/?url=<echo-responder> → origin
                   fetches the responder directly (same egress) and returns
                   its body. Powers egress_echo on this transport.
  tokenade.oracle  GET http://tokenade.oracle/q?method=<probe> → snapshot
                   value (or 403 for denied/unknown). Powers live oracle
                   queries backed by the origin snapshot.

Oracle values are snapshot-backed on this transport (live-browser eval is
the WSS path's Phase-2 feature); the mode still reports "live" because
answers come from the running origin over a live channel.
"""

import asyncio
import json
import logging
import threading
from typing import Any, Dict, Optional, Set
from urllib.parse import urlparse, parse_qs

from tokenade.core.tunnel.errors import AuthError, TunnelError

logger = logging.getLogger(__name__)

ECHO_HOST = "tokenade.echo"
ORACLE_HOST = "tokenade.oracle"


class TokenGatedEgressProxy:
    """Loopback HTTP egress proxy: Bearer gate + special hosts + dial-out.

    Runs on the ORIGIN machine. Every request must carry
    `Proxy-Authorization: Bearer <token>` (else 407). Approved targets are
    dialed directly from this machine. tokenade.echo / tokenade.oracle are
    answered locally (see module docstring).
    """

    def __init__(
        self,
        consumer_tokens: Set[str],
        snapshot_values: Optional[Dict[str, Any]] = None,
        oracle_allowlist=None,
        echo_timeout: float = 15.0,
        host: str = "127.0.0.1",
        port: int = 0,
        live_oracle: bool = False,
    ):
        self.consumer_tokens = set(consumer_tokens or [])
        self.snapshot_values = dict(snapshot_values or {})
        self.oracle_allowlist = set(oracle_allowlist or [])
        self.echo_timeout = echo_timeout
        self.host = host
        self.port = port
        self._server = None
        self._client_tasks: Set[asyncio.Task] = set()
        self._live = None
        if live_oracle:
            from tokenade.core.tunnel.live_oracle import LiveBrowserOracle

            self._live = LiveBrowserOracle(oracle_allowlist)

    @property
    def bound_port(self) -> Optional[int]:
        """Actual port once serving, else None."""
        if self._server is None:
            return None
        sockets = getattr(self._server, "sockets", None) or []
        return sockets[0].getsockname()[1] if sockets else None

    async def serve(self, port: Optional[int] = None) -> int:
        """Start serving; returns the bound port."""
        async def _tracked(reader, writer) -> None:
            task = asyncio.current_task()
            self._client_tasks.add(task)
            try:
                await self._handle(reader, writer)
            finally:
                self._client_tasks.discard(task)
                try:
                    writer.close()
                except Exception:
                    pass

        self._server = await asyncio.start_server(
            _tracked, self.host, port if port is not None else self.port
        )
        return self.bound_port

    async def aclose(self) -> None:
        """Drop clients and stop listening."""
        for task in list(self._client_tasks):
            task.cancel()
        if self._client_tasks:
            await asyncio.gather(*self._client_tasks, return_exceptions=True)
            self._client_tasks.clear()
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None

    # -- request handling --

    def _bearer_ok(self, head: bytes) -> bool:
        try:
            text = head.decode("latin-1")
        except UnicodeDecodeError:
            return False
        for line in text.split("\r\n")[1:]:
            if line.lower().startswith("proxy-authorization:"):
                scheme, _, credential = line.split(":", 1)[1].strip().partition(" ")
                if scheme.lower() == "bearer" and credential.strip() in self.consumer_tokens:
                    return True
        return False

    async def _handle(self, reader, writer) -> None:
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=15)
        except (asyncio.LimitOverrunError, asyncio.TimeoutError,
                asyncio.IncompleteReadError):
            return
        if not self._bearer_ok(head):
            writer.write(b"HTTP/1.1 407 Proxy Auth Required\r\n"
                         b"Proxy-Authenticate: Bearer\r\n\r\n")
            await writer.drain()
            return
        try:
            request_line = head.split(b"\r\n", 1)[0].decode("latin-1")
            method, target = request_line.split(" ")[:2]
        except (ValueError, UnicodeDecodeError):
            return
        method = method.upper()
        if method == "CONNECT":
            host, port = self._split_host_port(target, 443)
        else:
            url = urlparse(target)
            if not url.hostname:
                writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                await writer.drain()
                return
            host, port = url.hostname, url.port or (443 if url.scheme == "https" else 80)

        lowered = host.lower()
        if lowered == ECHO_HOST:
            await self._serve_echo(writer, target)
            return
        if lowered == ORACLE_HOST:
            await self._serve_oracle(writer, target)
            return

        if method == "CONNECT":
            try:
                reader2, writer2 = await asyncio.wait_for(
                    asyncio.open_connection(host, port), timeout=10)
            except Exception:
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                await writer.drain()
                return
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            await self._pipe(reader, writer, reader2, writer2)
        else:
            try:
                reader2, writer2 = await asyncio.wait_for(
                    asyncio.open_connection(host, port), timeout=10)
            except Exception:
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                await writer.drain()
                return
            writer2.write(head)
            await writer2.drain()
            await self._pipe(reader, writer, reader2, writer2)

    async def _serve_echo(self, writer, target: str) -> None:
        """GET http://tokenade.echo/?url=<responder> → origin-fetched body."""
        import urllib.request

        query = parse_qs(urlparse(target).query)
        url = (query.get("url") or [""])[0]
        if not url:
            writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            await writer.drain()
            return
        loop = asyncio.get_running_loop()

        def _get():
            try:
                with urllib.request.urlopen(url, timeout=self.echo_timeout) as resp:
                    return 200, resp.read(4096)
            except Exception as exc:
                return 502, str(exc).encode()

        status, body = await loop.run_in_executor(None, _get)
        writer.write(f"HTTP/1.1 {status} OK\r\nContent-Type: application/json\r\n"
                     f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        await writer.drain()

    async def _serve_oracle(self, writer, target: str) -> None:
        """GET http://tokenade.oracle/q?method=<probe> → value JSON.

        Live browser first (when enabled), snapshot fallback — same policy
        as the WSS origin endpoint.
        """
        query = parse_qs(urlparse(target).query)
        method = (query.get("method") or [""])[0]
        value, error, source = await self._answer_oracle(method)
        status = 200 if error is None else (403 if (error or "").startswith("denied:") else 404)
        body = json.dumps({"value": value, "error": error,
                           "source": source}).encode()
        writer.write(f"HTTP/1.1 {status} OK\r\nContent-Type: application/json\r\n"
                     f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        await writer.drain()

    async def _answer_oracle(self, method: str):
        """Live-first, snapshot-fallback oracle answer + source label."""
        if method not in self.oracle_allowlist:
            return None, f"denied: {method}", "none"
        if self._live is not None:
            loop = asyncio.get_running_loop()

            def _ask():
                try:
                    self._live.start()
                except Exception as exc:
                    return None, f"oracle offline: {exc}"
                return self._live.answer(method)

            value, error = await loop.run_in_executor(None, _ask)
            if error is None:
                return value, None, "live"
            if error.startswith("denied:"):
                return None, error, "none"
            if method in self.snapshot_values:
                logger.warning("live oracle failed (%s); snapshot fallback", error)
                return self.snapshot_values[method], None, "snapshot-fallback"
            return None, error, "none"
        if method in self.snapshot_values:
            return self.snapshot_values[method], None, "snapshot"
        return None, f"unknown: {method}", "none"

    @staticmethod
    def _split_host_port(target: str, default: int):  # TokenGatedEgressProxy
        if ":" in target:
            host, port_s = target.rsplit(":", 1)
            try:
                return host, int(port_s)
            except ValueError:
                pass
        return target, default

    async def _pipe(self, reader, writer, reader2, writer2) -> None:
        # Half-close cascade: EOF upstream closes downstream, so FIN
        # propagates hop-by-hop and no idle pipe wedges wait_closed().
        async def _forward(src, dst):
            try:
                while True:
                    chunk = await src.read(32768)
                    if not chunk:
                        break
                    dst.write(chunk)
                    await dst.drain()
            except Exception:
                pass
            finally:
                try:
                    dst.close()
                except Exception:
                    pass

        await asyncio.gather(_forward(reader, writer2), _forward(reader2, writer))
        for w in (writer2, writer):
            try:
                w.close()
            except Exception:
                pass


class SshReverseOrigin:
    """Origin side: reverse-forward sshbox:remote_port → local egress proxy.

    Uses paramiko (client only). The SSH box needs `GatewayPorts` suitable
    for the consumer's reachability (default localhost-forward is fine when
    the consumer reaches the box itself; the consumer connects TO the box).
    Reconnects with backoff; approved tokens hot-reload from the approved
    store file so `tunnel share` works without restarting serve.
    """

    def __init__(
        self,
        ssh_host: str,
        ssh_port: int,
        ssh_user: str,
        remote_port: int,
        key_path: Optional[str] = None,
        password: Optional[str] = None,
        consumer_tokens: Optional[Set[str]] = None,
        snapshot_values: Optional[Dict[str, Any]] = None,
        oracle_allowlist=None,
        live_oracle: bool = False,
    ):
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.remote_port = remote_port
        self.key_path = key_path
        self.password = password
        self.consumer_tokens = set(consumer_tokens or [])
        self.snapshot_values = dict(snapshot_values or {})
        self.oracle_allowlist = list(oracle_allowlist or [])
        self.live_oracle = live_oracle
        self._stop = threading.Event()
        self._client = None

    def stop(self) -> None:
        """Signal the serve loop to exit and close the SSH client."""
        self._stop.set()
        client, self._client = self._client, None
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    def serve_forever(self, poll_s: float = 1.0) -> None:
        """Connect, forward, pump channels until stop() (blocking)."""
        import time

        delay = 1.0
        while not self._stop.is_set():
            try:
                self._serve_once(poll_s)
                delay = 1.0
            except Exception as exc:
                if self._stop.is_set():
                    break
                logger.warning("ssh origin error (%s); retrying in %.0fs...", exc, delay)
                self._stop.wait(delay)
                delay = min(delay * 2, 60.0)

    def _connect(self):
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        kwargs: Dict[str, Any] = {
            "hostname": self.ssh_host, "port": self.ssh_port,
            "username": self.ssh_user, "timeout": 15,
            "allow_agent": True, "look_for_keys": True,
        }
        if self.key_path:
            kwargs["key_filename"] = self.key_path
        if self.password:
            kwargs["password"] = self.password
        client.connect(**kwargs)
        return client

    def _serve_once(self, poll_s: float) -> None:
        import paramiko

        client = self._connect()
        self._client = client
        transport = client.get_transport()
        assert transport is not None
        proxy = AsyncProxyRunner(
            self.consumer_tokens, self.snapshot_values, self.oracle_allowlist,
            live_oracle=self.live_oracle,
        )
        proxy_port = proxy.start()
        logger.info("ssh origin: forwarding %s:%s → egress proxy :%s",
                    self.ssh_host, self.remote_port, proxy_port)
        try:
            transport.request_port_forward("", self.remote_port,
                                           handler=proxy.accepts_paramiko_channel)
            while not self._stop.is_set():
                self._stop.wait(poll_s)
        finally:
            try:
                transport.cancel_port_forward("", self.remote_port)
            except Exception:
                pass
            proxy.stop()
            client.close()
            self._client = None


class AsyncProxyRunner:
    """Runs a TokenGatedEgressProxy on a private thread-loop for paramiko.

    paramiko channels are blocking; each accepted channel is pumped to the
    local proxy over a loopback TCP socket in a worker thread.
    """

    def __init__(self, consumer_tokens, snapshot_values, oracle_allowlist,
                 live_oracle: bool = False):
        self.consumer_tokens = set(consumer_tokens or [])
        self.snapshot_values = dict(snapshot_values or {})
        self.oracle_allowlist = list(oracle_allowlist or [])
        self.live_oracle = live_oracle
        self._loop = None
        self._thread = None
        self._proxy = None

    def start(self) -> int:
        """Start proxy thread; returns bound loopback port."""
        import concurrent.futures

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True,
                                        name="tokenade-ssh-egress")
        self._thread.start()
        proxy = TokenGatedEgressProxy(self.consumer_tokens, self.snapshot_values,
                                      self.oracle_allowlist,
                                      live_oracle=self.live_oracle)

        async def _serve():
            return await proxy.serve(0)

        port = asyncio.run_coroutine_threadsafe(_serve(), self._loop).result(15)
        self._proxy = proxy
        return port

    def accepts_paramiko_channel(self, channel, origin, server):
        """paramiko port-forward handler: pump channel ↔ local proxy."""
        import socket as _socket

        def _pump():
            sock = None
            try:
                sock = _socket.create_connection(("127.0.0.1", self._proxy.bound_port),
                                                 timeout=10)
                channel.settimeout(60)
                while True:
                    data = channel.recv(32768)
                    if not data:
                        break
                    sock.sendall(data)
                    chunk = sock.recv(32768)
                    if not chunk:
                        break
                    channel.sendall(chunk)
            except Exception:
                pass
            finally:
                try:
                    if sock is not None:
                        sock.close()
                except Exception:
                    pass
                try:
                    channel.close()
                except Exception:
                    pass

        worker = threading.Thread(target=_pump, daemon=True)
        worker.start()

    def stop(self) -> None:
        """Stop proxy and thread."""
        try:
            if self._loop is not None and self._proxy is not None:
                fut = asyncio.run_coroutine_threadsafe(self._proxy.aclose(), self._loop)
                try:
                    fut.result(10)
                except Exception:
                    pass
        finally:
            self._proxy = None
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


class SshTunnelSession:
    """Consumer side of an ssh-reverse circuit (thread-owned, like TunnelSession).

    Opens plain TCP to sshbox:remote_port through a loopback HTTP listener
    that injects the Bearer token. Same surface as TunnelSession so
    RuntimePlanBuilder and callers treat both transports uniformly.
    """

    def __init__(
        self,
        ssh_host: str,
        ssh_port: int,
        remote_port: int,
        consumer_token: str,
        echo_url: Optional[str] = None,
        loopback_host: str = "127.0.0.1",
        split: Optional[Dict[str, Any]] = None,
    ):
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.remote_port = remote_port
        self._consumer_token = consumer_token
        self.echo_url = echo_url
        self.loopback_host = loopback_host
        self._loop = None
        self._thread = None
        self._owns_loop = False
        self._listener = None
        self._client_tasks: Set[asyncio.Task] = set()
        self.echo: Dict[str, Any] = {}
        self.split = split or {"enabled": False, "domains": [], "mode": "off"}
        self.split_stats = {"tunneled": 0, "direct": 0}

    # -- lifecycle --

    def open(self, timeout_s: float = 30.0) -> "SshTunnelSession":
        """Start loopback listener; verify reachability + token acceptance."""
        import atexit

        atexit.register(self.close)
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, daemon=True,
                                  name="tokenade-ssh-consumer")
        thread.start()
        self._loop = loop
        self._thread = thread
        self._owns_loop = True
        try:
            self._submit(self.aopen(timeout_s), timeout_s)
        except Exception:
            self.close()
            raise
        return self

    async def aopen(self, timeout_s: float = 30.0) -> "SshTunnelSession":
        """Native-async open on the CALLER's loop (tests, embedding).

        Unlike open(), this neither starts a thread nor takes ownership of
        the running loop — the caller owns teardown via aclose().
        """
        self._loop = asyncio.get_running_loop()
        self._owns_loop = False
        await asyncio.wait_for(self._setup(), timeout=timeout_s)
        if self.echo_url:
            self.echo = await asyncio.wait_for(
                self._fetch_echo(self.echo_url), timeout=timeout_s)
        return self

    async def _setup(self) -> None:
        async def _tracked(reader, writer) -> None:
            task = asyncio.current_task()
            self._client_tasks.add(task)
            try:
                await self._handle_client(reader, writer)
            finally:
                self._client_tasks.discard(task)
                try:
                    writer.close()
                except Exception:
                    pass

        self._listener = await asyncio.start_server(
            _tracked, self.loopback_host, 0
        )
        # Fail fast when the box is unreachable or the token is wrong.
        await self._probe()

    def _submit(self, coro, timeout_s: float):
        if self._loop is None:
            raise TunnelError("ssh tunnel session not open")
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout_s)

    def query(self, method: str, args: Any = None, timeout_s: float = 15.0) -> Any:
        """Oracle query via the tokenade.oracle special host."""
        import json as _json
        import urllib.parse as _up

        path = "/q?method=" + _up.quote(str(method), safe="")
        body = self._submit(self._http_via_box("GET", ORACLE_HOST, 80, path),
                            timeout_s)
        try:
            payload = _json.loads(body.split(b"\r\n\r\n", 1)[1].decode("utf-8"))
        except (ValueError, IndexError) as exc:
            raise TunnelError(f"oracle bad reply: {exc}") from exc
        if payload.get("error"):
            raise TunnelError(f"oracle denied {method}: {payload['error']}")
        return payload.get("value")

    @property
    def local_proxy(self) -> Optional[Dict[str, str]]:
        """Playwright-ready proxy dict (None until open)."""
        if self._listener is None:
            return None
        port = self._listener.sockets[0].getsockname()[1]
        return {"server": f"http://{self.loopback_host}:{port}"}

    @property
    def oracle(self) -> Dict[str, Any]:
        """Snapshot-backed live oracle config for RuntimePlanBuilder."""
        from tokenade.core.session_runtime.plan import ORACLE_ALLOWLIST

        if self._listener is None:
            return {"mode": "off", "allowlist": list(ORACLE_ALLOWLIST)}
        return {"mode": "live", "snapshot_backed": True,
                "allowlist": list(ORACLE_ALLOWLIST)}

    async def aclose(self) -> None:
        """Native-async teardown on the caller's loop (pairs with aopen)."""
        for task in list(self._client_tasks):
            task.cancel()
        if self._client_tasks:
            await asyncio.gather(*self._client_tasks, return_exceptions=True)
            self._client_tasks.clear()
        if self._listener is not None:
            self._listener.close()
            try:
                await self._listener.wait_closed()
            except Exception:
                pass
            self._listener = None

    def close(self) -> None:
        """Tear down listener and thread (idempotent)."""
        try:
            if self._loop is not None:
                fut = asyncio.run_coroutine_threadsafe(self.aclose(), self._loop)
                try:
                    fut.result(10)
                except Exception:
                    pass
        finally:
            self._listener = None
            if self._owns_loop:
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
            else:
                self._thread = None

    # -- box I/O --

    async def _probe(self) -> None:
        """Verify the box answers and the token is accepted (fail fast)."""
        body = await self._http_via_box(
            "GET", ECHO_HOST, 80, "/?url=http://127.0.0.1:9/none")
        if b"407" in body[:64] or not body:
            raise AuthError("ssh box rejected consumer token (407)")

    async def _fetch_echo(self, echo_url: str) -> Dict[str, Any]:
        """Ask the ORIGIN to GET echo_url (same egress that dials sites)."""
        return await self.fetch_echo(echo_url)

    async def fetch_echo(self, echo_url: str, timeout_s: float = 20.0) -> Dict[str, Any]:
        """Echo fetch usable on any running loop (entry/test parity)."""
        import hashlib
        import json as _json
        import urllib.parse as _up

        path = "/?url=" + _up.quote(echo_url, safe="")
        body = await self._http_via_box("GET", ECHO_HOST, 80, path)
        try:
            text = body.split(b"\r\n\r\n", 1)[1].decode("utf-8")
            data = _json.loads(text)
        except (ValueError, IndexError) as exc:
            raise TunnelError(f"egress echo not JSON: {exc}") from exc
        echo: Dict[str, Any] = {
            "country": str(data.get("country", "") or ""),
            "asn": str(data.get("asn", "") or ""),
        }
        if data.get("ip"):
            echo["ip_hash"] = "sha256:" + hashlib.sha256(
                str(data["ip"]).encode()).hexdigest()
        return echo

    async def _http_via_box(self, method: str, host: str, port: int,
                            path: str, timeout_s: float = 20.0) -> bytes:
        """Raw HTTP request through sshbox:remote_port; returns full reply."""
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.ssh_host, self.remote_port),
            timeout=timeout_s)
        try:
            request = (f"{method} http://{host}{path} HTTP/1.1\r\nHost: {host}\r\n"
                       f"Proxy-Authorization: Bearer {self._consumer_token}\r\n"
                       "Connection: close\r\n\r\n").encode()
            writer.write(request)
            await writer.drain()
            # Bounded read (never read(-1)): the box/origin may hold the
            # pipe open, so frame the reply by its Content-Length.
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"),
                                          timeout=timeout_s)
            length = 0
            for line in head.decode("latin-1").split("\r\n")[1:]:
                if line.lower().startswith("content-length:"):
                    try:
                        length = int(line.split(":", 1)[1].strip())
                    except ValueError:
                        length = 0
            body = await asyncio.wait_for(reader.readexactly(length),
                                          timeout=timeout_s) if length else b""
            return head + body
        finally:
            try:
                writer.close()
            except Exception:
                pass

    async def _handle_client(self, reader, writer) -> None:
        """Loopback listener: inject Bearer, forward to the box, pipe back."""
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=15)
        except (asyncio.LimitOverrunError, asyncio.TimeoutError,
                asyncio.IncompleteReadError):
            return
        try:
            request_line = head.split(b"\r\n", 1)[0].decode("latin-1")
            method, target = request_line.split(" ")[:2]
        except (ValueError, UnicodeDecodeError):
            return
        if method.upper() == "CONNECT":
            host, port = self._split_host_port(target, 443)
        else:
            url = urlparse(target)
            if not url.hostname:
                writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                await writer.drain()
                return
            host, port = url.hostname, url.port or 80
        # Split routing (explicit opt-in only): non-listed hosts dial
        # DIRECT from this machine instead of the SSH box. Origin-local
        # special hosts ALWAYS ride the circuit (undiallable directly).
        from tokenade.core.session_runtime.split import host_in_domains

        if self.split.get("enabled") and host.lower() not in (
                ECHO_HOST, ORACLE_HOST) and not host_in_domains(
                host, self.split.get("domains", [])):
            self.split_stats["direct"] += 1
            logger.info("split: direct %s", host)
            await self._handle_direct(reader, writer, method, head, host, port)
            return
        self.split_stats["tunneled"] += 1
        try:
            reader2, writer2 = await asyncio.wait_for(
                asyncio.open_connection(self.ssh_host, self.remote_port), timeout=10)
        except Exception:
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            await writer.drain()
            return
        try:
            head_lines = head.split(b"\r\n")
            injected = head_lines[:1] + [
                f"Proxy-Authorization: Bearer {self._consumer_token}".encode()
            ] + head_lines[1:]
            writer2.write(b"\r\n".join(injected))
            await writer2.drain()
            if method.upper() == "CONNECT":
                # Swallow the origin's 200 and send our own once linked.
                reply = await asyncio.wait_for(
                    reader2.readuntil(b"\r\n\r\n"), timeout=15)
                if b"200" not in reply.split(b"\r\n", 1)[0]:
                    writer.write(reply)
                    await writer.drain()
                    return
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
            await self._pipe(reader, writer, reader2, writer2)
        except TunnelError:
            try:
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                await writer.drain()
            except Exception:
                pass
        finally:
            try:
                writer2.close()
            except Exception:
                pass

    @staticmethod
    def _split_host_port(target: str, default: int):
        if ":" in target:
            host, port_s = target.rsplit(":", 1)
            try:
                return host, int(port_s)
            except ValueError:
                pass
        return target, default

    async def _handle_direct(self, reader, writer, method: str, head: bytes,
                             host: str, port: int) -> None:
        """Split-routing direct path: dial from THIS machine (opt-in only)."""
        try:
            reader2, writer2 = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=10)
        except Exception:
            try:
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                await writer.drain()
            except Exception:
                pass
            return
        try:
            if method.upper() == "CONNECT":
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
            else:
                writer2.write(head)
                await writer2.drain()
            await self._pipe(reader, writer, reader2, writer2)
        finally:
            try:
                writer2.close()
            except Exception:
                pass

    async def _pipe(self, reader, writer, reader2, writer2) -> None:
        # Half-close cascade (see TokenGatedEgressProxy._pipe).
        async def _forward(src, dst):
            try:
                while True:
                    chunk = await src.read(32768)
                    if not chunk:
                        break
                    dst.write(chunk)
                    await dst.drain()
            except Exception:
                pass
            finally:
                try:
                    dst.close()
                except Exception:
                    pass

        await asyncio.gather(_forward(reader, writer2), _forward(reader2, writer))
        for w in (writer2, writer):
            try:
                w.close()
            except Exception:
                pass
