"""Wire protocol - JSON text frames over websocket.

Control frames (dicts):
  hello:    {"t": "hello", "role": "origin"|"consumer",
             "remote_ref": str, "token": str}
  welcome:  {"t": "welcome", "role": str}            # relay accepted the socket
  paired:   {"t": "paired", "consumer": str}        # origin accepted consumer
  reject:   {"t": "reject", "reason": str}          # relay or origin refused
  open:     {"t": "open", "stream": int, "host": str, "port": int,
             "consumer": str}
  opened:   {"t": "opened", "stream": int}
  refused:  {"t": "refused", "stream": int, "reason": str}
  data:     {"t": "data", "stream": int, "b64": str}
  close:    {"t": "close", "stream": int}
  query:    {"t": "query", "id": int, "method": str, "args": any}
  answer:   {"t": "answer", "id": int, "value": any, "error": str|None}

Binary payloads ride base64 inside data frames (Phase 1 simplicity over
throughput; bulk session traffic is small).
"""

import base64
import itertools
import json
from typing import Any, Dict

_stream_ids = itertools.count(1)


def new_stream_id() -> int:
    """Allocate a locally-unique stream id (consumer side)."""
    return next(_stream_ids)


def encode_frame(frame: Dict[str, Any]) -> str:
    """Serialize a control frame (bytes payloads as base64)."""
    frame = dict(frame)
    payload = frame.get("bytes")
    if isinstance(payload, (bytes, bytearray)):
        frame = dict(frame)
        frame["b64"] = base64.b64encode(bytes(payload)).decode("ascii")
        del frame["bytes"]
    return json.dumps(frame, separators=(",", ":"))


def decode_frame(raw: str) -> Dict[str, Any]:
    """Parse a control frame; raises TunnelError on malformed input."""
    from tokenade.core.tunnel.errors import TunnelError

    try:
        frame = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise TunnelError(f"malformed frame: {exc}") from exc
    if not isinstance(frame, dict) or "t" not in frame:
        raise TunnelError("malformed frame: missing 't'")
    return frame


def data_bytes(frame: Dict[str, Any]) -> bytes:
    """Extract payload bytes from a data frame."""
    from tokenade.core.tunnel.errors import TunnelError

    try:
        return base64.b64decode(frame.get("b64", ""))
    except (ValueError, TypeError) as exc:
        raise TunnelError(f"malformed data frame: {exc}") from exc
