"""
Origin-egress tunnel - Reverse SOCKS-over-websocket transport.

Both sides dial OUT to a rendezvous relay (nothing listens on the open
internet). The origin side dials target sites from the export machine, so
replayed sessions egress from the original IP/ASN. The consumer side gets a
localhost-only HTTP proxy that Playwright points at per context.

Trust model: the relay routes opaque frames by remote_ref. Consumer tokens
are verified END-TO-END by the origin (paired/ready vs reject), so a
malicious relay can drop traffic but cannot impersonate either side. Relay
sees CONNECT host:port (SNI-equivalent), never content.
"""

from tokenade.core.tunnel.errors import (
    AuthError,
    PairingError,
    TunnelError,
)
from tokenade.core.tunnel.protocol import (
    decode_frame,
    encode_frame,
    new_stream_id,
)

__all__ = [
    "AuthError",
    "PairingError",
    "TunnelError",
    "decode_frame",
    "encode_frame",
    "new_stream_id",
]
