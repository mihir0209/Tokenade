"""
Origin endpoint - Runs on the export machine (`tokenade tunnel serve`).

Holds one outbound websocket to the relay and:
  - dials target TCP endpoints on behalf of approved consumers (origin
    egress: the SYN leaves from THIS machine, so sites see the export IP);
  - answers fingerprint-oracle queries from the signed snapshot values
    (Phase 1: snapshot oracle; live-browser evaluation is Phase 2);
  - performs egress-echo fetches directly (same machine == same egress).

Consumer authorization lives HERE: a consumer id must present a token from
consumer_tokens before any open/query/echo is honored. Bearer tokens are
visible to the relay in transit — run your own relay (the default) and
rotate with `tunnel revoke`.
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Set

from tokenade.core.tunnel.errors import AuthError, TunnelError
from tokenade.core.tunnel.protocol import data_bytes, decode_frame, encode_frame

logger = logging.getLogger(__name__)


class SnapshotOracle:
    """Answers allowlisted scalar probes from signed snapshot values."""

    def __init__(self, values: Dict[str, Any], allowlist):
        self.values = dict(values or {})
        self.allowlist = set(allowlist or [])

    def answer(self, method: str):
        """Return (value, error). Deny-by-default on method."""
        if method not in self.allowlist:
            return None, f"denied: {method}"
        if method not in self.values:
            return None, f"unknown: {method}"
        return self.values[method], None


class OriginEndpoint:
    """Origin side of a remote_ref circuit."""

    def __init__(
        self,
        relay_url: str,
        remote_ref: str,
        consumer_tokens: Optional[Set[str]] = None,
        snapshot_values: Optional[Dict[str, Any]] = None,
        oracle_allowlist=None,
        dial_timeout: float = 10.0,
        echo_timeout: float = 15.0,
        live_oracle: bool = False,
    ):
        self.relay_url = relay_url
        self.remote_ref = remote_ref
        self.consumer_tokens = set(consumer_tokens or [])
        self.oracle = SnapshotOracle(snapshot_values or {}, oracle_allowlist or [])
        self.dial_timeout = dial_timeout
        self.echo_timeout = echo_timeout
        self._ws = None
        self._approved: Set[str] = set()
        self._streams: Dict[int, Dict[str, Any]] = {}
        self._tasks: Set[asyncio.Task] = set()
        self._live = None
        if live_oracle:
            from tokenade.core.tunnel.live_oracle import LiveBrowserOracle

            self._live = LiveBrowserOracle(oracle_allowlist)

    # -- lifecycle --

    async def start(self) -> None:
        """Connect and serve until the relay drops (caller reconnects)."""
        import websockets

        self._ws = await websockets.connect(
            self.relay_url, ping_interval=20, ping_timeout=20
        )
        try:
            await self._send(
                {"t": "hello", "role": "origin", "remote_ref": self.remote_ref, "token": ""}
            )
            frame = decode_frame(await self._ws.recv())
            if frame.get("t") != "welcome":
                raise AuthError(f"relay refused origin: {frame}")
            logger.info("origin attached for %s", self.remote_ref)
            async for raw in self._ws:
                if isinstance(raw, str):
                    await self._dispatch(decode_frame(raw))
        finally:
            await self._close_all_streams()
            self._ws = None

    async def stop(self) -> None:
        """Close the relay socket, streams, and live oracle browser."""
        await self._close_all_streams()
        if self._live is not None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._live.stop)
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    # -- frame handling --

    async def _send(self, frame: dict) -> None:
        await self._ws.send(encode_frame(frame))

    def _approved_consumer(self, frame: dict) -> Optional[str]:
        consumer = str(frame.get("consumer", ""))
        return consumer if consumer in self._approved else None

    async def _dispatch(self, frame: dict) -> None:
        ftype = frame.get("t")
        if ftype == "pair":
            await self._on_pair(frame)
        elif ftype == "open":
            await self._on_open(frame)
        elif ftype == "data":
            await self._on_data(frame)
        elif ftype == "close":
            await self._on_close(frame)
        elif ftype == "query":
            await self._on_query(frame)
        elif ftype == "echo_req":
            await self._on_echo(frame)

    async def _on_pair(self, frame: dict) -> None:
        consumer = str(frame.get("consumer", ""))
        token = str(frame.get("token", ""))
        if token and token in self.consumer_tokens:
            self._approved.add(consumer)
            await self._send({"t": "paired", "consumer": consumer})
            logger.info("origin approved consumer %s", consumer)
        else:
            await self._send(
                {"t": "reject", "consumer": consumer, "reason": "bad consumer token"}
            )

    async def _on_open(self, frame: dict) -> None:
        consumer = self._approved_consumer(frame)
        stream = int(frame.get("stream", 0))
        if consumer is None:
            await self._send(
                {"t": "refused", "consumer": str(frame.get("consumer", "")),
                 "stream": stream, "reason": "not paired"}
            )
            return
        host, port = str(frame.get("host", "")), int(frame.get("port", 0))
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=self.dial_timeout
            )
        except Exception as exc:
            await self._send(
                {"t": "refused", "consumer": consumer, "stream": stream,
                 "reason": f"dial failed: {exc}"}
            )
            return
        queue: asyncio.Queue = asyncio.Queue()
        self._streams[stream] = {"writer": writer, "queue": queue, "consumer": consumer}
        await self._send({"t": "opened", "consumer": consumer, "stream": stream})
        self._spawn(self._pump_tcp_to_ws(stream, reader, consumer))
        self._spawn(self._pump_ws_to_tcp(stream, queue, writer))

    async def _on_data(self, frame: dict) -> None:
        if self._approved_consumer(frame) is None:
            return
        stream = int(frame.get("stream", 0))
        entry = self._streams.get(stream)
        if entry is not None:
            entry["queue"].put_nowait(data_bytes(frame))

    async def _on_close(self, frame: dict) -> None:
        await self._teardown_stream(int(frame.get("stream", 0)))

    async def _on_query(self, frame: dict) -> None:
        consumer = self._approved_consumer(frame)
        qid = frame.get("id")
        if consumer is None:
            await self._send(
                {"t": "answer", "consumer": str(frame.get("consumer", "")),
                 "id": qid, "value": None, "error": "not paired", "source": "none"}
            )
            return
        value, error, source = await self._answer_query(str(frame.get("method", "")))
        await self._send(
            {"t": "answer", "consumer": consumer, "id": qid,
             "value": value, "error": error, "source": source}
        )

    async def _answer_query(self, method: str):
        """Answer a probe: live browser first, snapshot fallback.

        Returns (value, error, source) with source in
        live|snapshot|snapshot-fallback|none.
        """
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
            # Live failed (browser down, eval error): fall back to snapshot
            # rather than failing the session's fingerprint reads.
            value, snap_error = self.oracle.answer(method)
            if snap_error is None:
                logger.warning("live oracle failed (%s); snapshot fallback", error)
                return value, None, "snapshot-fallback"
            return None, error, "none"
        value, error = self.oracle.answer(method)
        return value, error, ("snapshot" if error is None else "none")

    async def _on_echo(self, frame: dict) -> None:
        consumer = self._approved_consumer(frame)
        qid = frame.get("id")
        if consumer is None:
            await self._send(
                {"t": "echo_rep", "consumer": str(frame.get("consumer", "")),
                 "id": qid, "body": None, "error": "not paired"}
            )
            return
        url = str(frame.get("url", ""))
        body, error = await self._fetch_echo(url)
        # Truncate: echo responders are tiny JSON; never shuttle bulk.
        await self._send(
            {"t": "echo_rep", "consumer": consumer, "id": qid,
             "body": (body or "")[:4096], "error": error}
        )

    def _fetch_echo(self, url: str):
        import urllib.request

        async def _run():
            loop = asyncio.get_running_loop()

            def _get():
                try:
                    with urllib.request.urlopen(url, timeout=self.echo_timeout) as resp:
                        return resp.read().decode("utf-8", "replace"), None
                except Exception as exc:
                    return None, str(exc)

            return await loop.run_in_executor(None, _get)

        return _run()

    # -- pumps --

    def _spawn(self, coro) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _pump_tcp_to_ws(self, stream: int, reader, consumer: str) -> None:
        try:
            while True:
                chunk = await reader.read(32768)
                if not chunk:
                    break
                await self._send(
                    {"t": "data", "consumer": consumer, "stream": stream, "bytes": chunk}
                )
        except Exception:
            pass
        finally:
            await self._teardown_stream(stream)
            try:
                await self._send({"t": "close", "consumer": consumer, "stream": stream})
            except Exception:
                pass

    async def _pump_ws_to_tcp(self, stream: int, queue: asyncio.Queue, writer) -> None:
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
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

    async def _teardown_stream(self, stream: int) -> None:
        entry = self._streams.pop(stream, None)
        if entry is not None:
            entry["queue"].put_nowait(None)
            try:
                entry["writer"].close()
            except Exception:
                pass

    async def _close_all_streams(self) -> None:
        for stream in list(self._streams):
            await self._teardown_stream(stream)
        for task in list(self._tasks):
            task.cancel()
