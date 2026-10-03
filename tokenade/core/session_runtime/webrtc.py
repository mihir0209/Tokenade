"""
WebRTC lockdown - Chromium launch flags that keep real IPs out of ICE.

The leak that undoes everything else: WebRTC gathers ICE candidates (host /
srflx) at the protocol layer, below any JavaScript spoofing, and can hand a
detector the machine's true IP through STUN even when the page believes it
is on the tunnel. Forcing non-proxied UDP off makes WebRTC ride the
configured (tunneled) proxy instead of the raw interface.

Deliberately NOT touched: mDNS hostname obfuscation stays at the browser
default (modern Chromium hides local IPs behind .local names out of the
box; disabling that feature would LEAK more, not less).

Phase 2 hardening (per plan): a native flag in the CloakBrowser backend for
ICE-level guarantees. These launch args are the Phase 1 portable layer.
"""

from typing import List, Optional

# Force WebRTC traffic through the proxy; host/srflx candidates gathered
# outside the proxy are suppressed.
WEBRTC_LOCKDOWN_ARGS = [
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
]


def webrtc_lockdown_args(existing: Optional[List[str]] = None) -> List[str]:
    """Merge WebRTC lockdown flags into an existing launch-arg list.

    Idempotent: already-present flags (matched by --name= prefix) are kept
    as-is so explicit user values always win.
    """
    merged = list(existing or [])
    present = {a.split("=", 1)[0] for a in merged}
    for arg in WEBRTC_LOCKDOWN_ARGS:
        if arg.split("=", 1)[0] not in present:
            merged.append(arg)
    return merged
