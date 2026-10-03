"""
Consumer circuit - Runs on the using machine (`load/launch --tunnel auto`).

Outbound websocket to the relay, paired end-to-end by the origin. Exposes:
  - open_stream(host, port): a tunneled TCP stream (origin dials = origin
    egress);
  - query(method, args): fingerprint-oracle query over the control channel;
  - egress_echo(url): ask the ORIGIN to GET an echo responder directly
    (same machine that dials sites == same egress IP) and return the body;
  - serve_local_listener(): localhost-only HTTP proxy (CONNECT + absolute
    URI) that Playwright uses as its per-context proxy.

Fail-closed: any circuit failure surfaces as TunnelError to the caller and
as a closed/502 socket to the local listener. The listener NEVER falls back
to direct dial — there is no direct-dial code path in this module at all.
"""

import asyncio
import hashlib
import json
import logging
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from tokenade.core.tunnel.errors import AuthError, TunnelError
from tokenade.core.tunnel.protocol import (
    data_bytes,
    decode_frame,
    encode_frame,
    new_stream_id,
)

logger = logging.getLogger(__name__)


class TunnelStream:
    """A tunneled TCP stream (reader/writer facade over frame queues)."""

    def __init__(self, circuit: "ConsumerCircuit", stream_id: int):
        self.circuit = circuit
        self.stream_id = stream_id
        self.queue: asyncio.Queue = asyncio.Queue()
        self.closed = False

    async def read(self, n: int = 32768) -> bytes:
        """Read up to n bytes; b"" means EOF."""
        buf = bytearray()
        first = await self.queue.get()
        if first is None:
            return b""
        buf += first
        while len(buf) < n and not self.queue.empty():
            nxt = self.queue.get_nowait()
            if nxt is None:
                break
            buf += nxt
        return bytes(buf[:n])

    async def write(self, data: bytes) -> None:
        if self.closed:
            raise TunnelError("stream closed")
        await self.circuit._send(
            {"t": "data", "stream": self.stream_id, "bytes": data}
        )

    async def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.queue.put_nowait(None)
            try:
                await self.circuit._send({"t": "close", "stream": self.stream_id})
            except Exception:
                pass


class ConsumerCircuit:
    """Consumer side of a remote_ref circuit."""

    def __init__(
        self,
        relay_url: str,
        remote_ref: str,
        consumer_token: str,
        loopback_host: str = "127.0.0.1",
        open_timeout: float = 10.0,
        split: Optional[Dict[str, Any]] = None,
    ):
        self.relay_url = relay_url
        self.remote_ref = remote_ref
        self.consumer_token = consumer_token
        self.loopback_host = loopback_host
        self.open_timeout = open_timeout
        self.split = split or {"enabled": False, "domains": [], "mode": "off"}
        self.split_stats = {"tunneled": 0, "direct": 0}
        self._ws = None
        self._reader_task: Optional[asyncio.Task] = None
        self._streams: Dict[int, TunnelStream] = {}
        self._pending_open: Dict[int, asyncio.Future] = {}
        self._pending_query: Dict[int, asyncio.Future] = {}
        self._pending_echo: Dict[int, asyncio.Future] = {}
        self._paired = asyncio.Event()
        self._pair_error: Optional[str] = None
        self._query_ids = 0
        self._listener = None
        self._client_tasks: set = set()

    @property
    def consumer_id(self) -> str:
        return self.consumer_token[:64] or "anon"

    @property
    def local_proxy(self) -> Optional[Dict[str, str]]:
        """Playwright-ready proxy dict once the listener is up, else None."""
        if self._listener is None:
            return None
        port = self._listener.sockets[0].getsockname()[1]
        return {"server": f"http://{self.loopback_host}:{port}"}

    # -- connection --

    async def connect(self, timeout: float = 15.0) -> None:
        """Open relay socket, hello, pair. Raises AuthError/TunnelError."""
        import websockets

        self._paired.clear()
        self._pair_error = None
        self._ws = await asyncio.wait_for(
            websockets.connect(self.relay_url, ping_interval=20, ping_timeout=20),
            timeout=timeout,
        )
        self._reader_task = asyncio.ensure_future(self._reader())
        await self._send(
            {"t": "hello", "role": "consumer",
             "remote_ref": self.remote_ref, "token": self.consumer_token}
        )
        await self._send({"t": "pair", "token": self.consumer_token})
        try:
            await asyncio.wait_for(self._paired.wait(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise TunnelError("pairing timed out (origin offline?)") from exc
        if self._pair_error:
            raise AuthError(f"origin rejected pairing: {self._pair_error}")
        logger.info("consumer paired for %s", self.remote_ref)

    async def ensure_connected(self, retries: int = 5, base_delay: float = 1.0) -> None:
        """Connect with backoff. Raises the last TunnelError when exhausted."""
        last: Optional[Exception] = None
        for attempt in range(retries):
            try:
                await self.connect()
                return
            except AuthError:
                raise  # credentials never fix themselves by retrying
            except Exception as exc:
                last = exc
                await asyncio.sleep(base_delay * (2 ** attempt))
        raise TunnelError(f"could not pair after {retries} tries: {last}")

    async def close(self) -> None:
        """Tear down listener, streams, and socket."""
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
        for stream in list(self._streams.values()):
            stream.closed = True
            stream.queue.put_nowait(None)
        self._streams.clear()
        if self._reader_task is not None:
            self._reader_task.cancel()
            self._reader_task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def _send(self, frame: dict) -> None:
        if self._ws is None:
            raise TunnelError("circuit down")
        await self._ws.send(encode_frame(frame))

    async def _reader(self) -> None:
        try:
            async for raw in self._ws:
                if not isinstance(raw, str):
                    continue
                try:
                    frame = decode_frame(raw)
                except TunnelError:
                    continue
                await self._dispatch(frame)
        except Exception:
            pass
        finally:
            self._fail_all(TunnelError("circuit down"))

    def _fail_all(self, exc: Exception) -> None:
        for fut in list(self._pending_open.values()) + list(
            self._pending_query.values()
        ) + list(self._pending_echo.values()):
            if not fut.done():
                fut.set_exception(exc)
        for stream in self._streams.values():
            stream.closed = True
            stream.queue.put_nowait(None)

    async def _dispatch(self, frame: dict) -> None:
        ftype = frame.get("t")
        if ftype == "welcome":
            return
        if ftype == "paired":
            self._paired.set()
        elif ftype == "reject":
            self._pair_error = str(frame.get("reason", "rejected"))
            self._paired.set()
        elif ftype in ("opened", "refused"):
            fut = self._pending_open.pop(int(frame.get("stream", -1)), None)
            if fut and not fut.done():
                fut.set_result(frame)
        elif ftype == "data":
            stream = self._streams.get(int(frame.get("stream", -1)))
            if stream is not None:
                stream.queue.put_nowait(data_bytes(frame))
        elif ftype == "close":
            stream = self._streams.pop(int(frame.get("stream", -1)), None)
            if stream is not None:
                stream.closed = True
                stream.queue.put_nowait(None)
        elif ftype == "answer":
            fut = self._pending_query.pop(int(frame.get("id", -1)), None)
            if fut and not fut.done():
                fut.set_result(frame)
        elif ftype == "echo_rep":
            fut = self._pending_echo.pop(int(frame.get("id", -1)), None)
            if fut and not fut.done():
                fut.set_result(frame)

    # -- streams / oracle / echo --

    async def open_stream(self, host: str, port: int) -> TunnelStream:
        """Open a tunneled TCP stream (origin dials host:port)."""
        stream_id = new_stream_id()
        stream = TunnelStream(self, stream_id)
        self._streams[stream_id] = stream
        fut = asyncio.get_running_loop().create_future()
        self._pending_open[stream_id] = fut
        await self._send({"t": "open", "stream": stream_id, "host": host, "port": port})
        try:
            frame = await asyncio.wait_for(fut, timeout=self.open_timeout)
        except asyncio.TimeoutError as exc:
            self._streams.pop(stream_id, None)
            raise TunnelError(f"open {host}:{port} timed out") from exc
        if frame.get("t") != "opened":
            self._streams.pop(stream_id, None)
            raise TunnelError(f"origin refused {host}:{port}: {frame.get('reason')}")
        return stream

    async def query(self, method: str, args: Any = None, timeout: float = 15.0) -> Any:
        """Oracle query. Returns value or raises TunnelError on denial."""
        self._query_ids += 1
        qid = self._query_ids
        fut = asyncio.get_running_loop().create_future()
        self._pending_query[qid] = fut
        await self._send({"t": "query", "id": qid, "method": method, "args": args})
        try:
            frame = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise TunnelError(f"oracle query {method} timed out") from exc
        if frame.get("error"):
            raise TunnelError(f"oracle denied {method}: {frame['error']}")
        return frame.get("value")

    async def egress_echo(self, echo_url: str, timeout: float = 20.0) -> Dict[str, Any]:
        """Ask the origin to GET echo_url directly; parse {ip,country,asn}.

        The origin dials from the export machine, so the responder sees the
        same egress IP that target sites will see.
        """
        self._query_ids += 1
        qid = self._query_ids
        fut = asyncio.get_running_loop().create_future()
        self._pending_echo[qid] = fut
        await self._send({"t": "echo_req", "id": qid, "url": echo_url})
        try:
            frame = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise TunnelError("egress echo timed out") from exc
        if frame.get("error"):
            raise TunnelError(f"egress echo failed at origin: {frame['error']}")
        try:
            data = json.loads(frame.get("body") or "{}")
        except ValueError as exc:
            raise TunnelError(f"egress echo not JSON: {exc}") from exc
        echo: Dict[str, Any] = {
            "country": str(data.get("country", "") or ""),
            "asn": str(data.get("asn", "") or ""),
        }
        if data.get("ip"):
            echo["ip_hash"] = "sha256:" + hashlib.sha256(
                str(data["ip"]).encode()
            ).hexdigest()
        return echo

    def check_egress(self, echo: Dict[str, Any], hint: Dict[str, Any],
                     policy: Dict[str, Any]) -> Tuple[str, str]:
        """Compare an echo against the jar origin_hint under policy."""
        from tokenade.core.session_runtime.policy import enforce_egress

        return enforce_egress(echo, hint, policy)

    # -- localhost listener --

    async def serve_local_listener(self, port: int = 0) -> Dict[str, str]:
        """Start the loopback HTTP proxy; returns the Playwright proxy dict."""
        async def _tracked(reader, writer) -> None:
            task = asyncio.current_task()
            self._client_tasks.add(task)
            try:
                await self._handle_client(reader, writer)
            finally:
                self._client_tasks.discard(task)
                # Always release the socket: a leaked connection keeps
                # Server.wait_closed() (and loop teardown) hanging forever.
                try:
                    writer.close()
                except Exception:
                    pass

        self._listener = await asyncio.start_server(
            _tracked, self.loopback_host, port
        )
        return self.local_proxy

    async def _handle_client(self, reader, writer) -> None:
        try:
            head = await self._read_head(reader)
            if head is None:
                writer.close()
                return
            request_line = head.split(b"\r\n", 1)[0].decode("latin-1")
            parts = request_line.split(" ")
            if len(parts) < 2:
                writer.close()
                return
            method, target = parts[0].upper(), parts[1]
            if method == "CONNECT":
                host, port = self._split_host_port(target, 443)
            else:
                url = urlparse(target)
                if not url.hostname:
                    writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                    writer.close()
                    return
                host, port = url.hostname, url.port or (443 if url.scheme == "https" else 80)
            # Split routing (explicit opt-in only): non-listed hosts dial
            # DIRECT from this machine. Without --tunnel-split everything
            # rides the circuit (fail-closed default).
            from tokenade.core.session_runtime.split import host_in_domains

            if self.split.get("enabled") and not host_in_domains(
                    host, self.split.get("domains", [])):
                self.split_stats["direct"] += 1
                logger.info("split: direct %s", host)
                await self._handle_direct(reader, writer, method, head, host, port)
                return
            self.split_stats["tunneled"] += 1
            stream = await self.open_stream(host, port)
            if method == "CONNECT":
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
            else:
                await stream.write(head)
            await self._pipe(reader, writer, stream)
        except TunnelError:
            try:
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            except Exception:
                pass
            writer.close()
        except Exception:
            writer.close()

    async def _read_head(self, reader) -> Optional[bytes]:
        try:
            return await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=15)
        except (asyncio.LimitOverrunError, asyncio.TimeoutError, asyncio.IncompleteReadError):
            return None

    @staticmethod
    def _split_host_port(target: str, default: int) -> Tuple[str, int]:
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
            except Exception:
                pass
            writer.close()
            return
        try:
            if method == "CONNECT":
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
            else:
                writer2.write(head)
                await writer2.drain()
            await self._pipe_sockets(reader, writer, reader2, writer2)
        finally:
            try:
                writer2.close()
            except Exception:
                pass

    async def _pipe_sockets(self, reader, writer, reader2, writer2) -> None:
        """Bidirectional pipe between two local socket pairs.

        Half-close cascade: EOF upstream closes downstream so FIN propagates
        hop-by-hop and idle pipes can't wedge wait_closed().
        """
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
        try:
            writer.close()
        except Exception:
            pass

    async def _pipe(self, reader, writer, stream: TunnelStream) -> None:
        async def _up():
            try:
                while True:
                    chunk = await reader.read(32768)
                    if not chunk:
                        break
                    await stream.write(chunk)
            except Exception:
                pass

        async def _down():
            try:
                while True:
                    chunk = await stream.read()
                    if not chunk:
                        break
                    writer.write(chunk)
                    await writer.drain()
            except Exception:
                pass
            finally:
                try:
                    writer.close()
                except Exception:
                    pass

        await asyncio.gather(_up(), _down())
        await stream.close()
