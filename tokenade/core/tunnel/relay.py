"""
Reference relay - Self-hostable rendezvous server (self-host decision).

Pairs one origin socket with N consumer sockets per remote_ref and shuttles
frames between them. The relay holds NO credentials: it routes by
(remote_ref) and forwards hello/open/query frames to the origin, which
accepts or rejects end-to-end. A malicious relay can drop traffic but
cannot complete pairing on either side's behalf.

Run:  python -m tokenade.core.tunnel.relay --host 0.0.0.0 --port 8765
Docker: see deploy/tunnel-relay/ (Phase 1 ships the server + compose).
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)


class RelayServer:
    """Websocket rendezvous relay."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self._circuits: Dict[str, Dict[str, Any]] = {}
        self._server = None
        self._handlers: Set[asyncio.Task] = set()

    def _circuit(self, remote_ref: str) -> Dict[str, Any]:
        return self._circuits.setdefault(
            remote_ref, {"origin": None, "consumers": set()}
        )

    async def _send(self, ws, frame: dict) -> None:
        from tokenade.core.tunnel.protocol import encode_frame

        await ws.send(encode_frame(frame))

    async def _handle_origin(self, ws, circuit: dict, frame: dict) -> None:
        from tokenade.core.tunnel.protocol import decode_frame  # noqa: F401

        ftype = frame.get("t")
        if ftype in ("paired", "reject", "opened", "refused", "data", "close",
                        "answer", "echo_rep"):
            target = frame.get("consumer")
            for consumer_ws in list(circuit["consumers"]):
                if target is None or getattr(consumer_ws, "_consumer_id", None) == target:
                    try:
                        await self._send(consumer_ws, frame)
                    except Exception:
                        pass
        else:
            await self._send(ws, {"t": "reject", "reason": f"bad origin frame: {ftype}"})

    async def _handle_consumer(self, ws, circuit: dict, frame: dict) -> None:
        origin = circuit.get("origin")
        if origin is None:
            await self._send(ws, {"t": "reject", "reason": "origin offline"})
            return
        frame = dict(frame)
        frame.setdefault("consumer", getattr(ws, "_consumer_id", "unknown"))
        try:
            await self._send(origin, frame)
        except Exception:
            await self._send(ws, {"t": "reject", "reason": "origin unreachable"})

    async def _connection(self, ws) -> None:
        from tokenade.core.tunnel.protocol import decode_frame

        role: Optional[str] = None
        circuit: Optional[dict] = None
        try:
            async for raw in ws:
                if not isinstance(raw, str):
                    continue
                try:
                    frame = decode_frame(raw)
                except Exception:
                    continue
                if role is None:
                    if frame.get("t") != "hello":
                        await self._send(ws, {"t": "reject", "reason": "hello first"})
                        break
                    role = frame.get("role")
                    remote_ref = str(frame.get("remote_ref", ""))
                    if role not in ("origin", "consumer") or not remote_ref:
                        await self._send(ws, {"t": "reject", "reason": "bad hello"})
                        break
                    circuit = self._circuit(remote_ref)
                    if role == "origin":
                        if circuit["origin"] is not None:
                            await self._send(ws, {"t": "reject", "reason": "origin already attached"})
                            break
                        circuit["origin"] = ws
                    else:
                        ws._consumer_id = str(frame.get("token", ""))[:64] or "anon"
                        circuit["consumers"].add(ws)
                    await self._send(ws, {"t": "welcome", "role": role})
                    logger.info("relay: %s attached for %s", role, remote_ref)
                    continue
                if role == "origin":
                    await self._handle_origin(ws, circuit, frame)
                else:
                    await self._handle_consumer(ws, circuit, frame)
        finally:
            if circuit is not None:
                if role == "origin" and circuit.get("origin") is ws:
                    circuit["origin"] = None
                elif role == "consumer":
                    circuit["consumers"].discard(ws)

    async def start(self) -> None:
        """Start serving (returns when serve_forever is cancelled)."""
        import websockets

        async def _tracked(ws) -> None:
            task = asyncio.current_task()
            self._handlers.add(task)
            try:
                await self._connection(ws)
            finally:
                self._handlers.discard(task)

        self._server = await websockets.serve(_tracked, self.host, self.port)
        logger.info("relay listening on %s:%s", self.host, self.port)
        await self._server.wait_closed()

    async def aclose(self) -> None:
        """Stop accepting AND drop existing connections (for clean shutdown)."""
        self.close()
        for task in list(self._handlers):
            task.cancel()
        if self._handlers:
            await asyncio.gather(*self._handlers, return_exceptions=True)
            self._handlers.clear()

    def close(self) -> None:
        """Stop accepting (existing sockets drain)."""
        if self._server is not None:
            self._server.close()


def main(argv=None) -> int:
    """CLI entry for the reference relay."""
    import argparse

    parser = argparse.ArgumentParser(description="Tokenade tunnel reference relay")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    server = RelayServer(args.host, args.port)
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
