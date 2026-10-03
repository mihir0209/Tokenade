"""
Egress policy - Per-jar tunnel policy with fail-closed default.

Precedence: explicit CLI flags > jar egress.policy > default deny (when a
tunnel was requested) / direct (when no tunnel is involved at all).

A jar WITHOUT an egress block combined with a tunnel request is a hard
error: there is nothing to verify the circuit against. The user must export
with --with-egress or pair the jar first.
"""

import logging
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

FALLBACK_DENY = "deny"
FALLBACK_WARN = "warn"
FALLBACK_DIRECT = "direct"


class EgressCheckError(Exception):
    """Raised when egress policy forbids proceeding (fail-closed)."""


def resolve_policy(package: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve the effective egress policy for a session package.

    Returns {"required": bool, "fallback": "deny"|"warn"|"direct"}.
    A jar carrying an egress block defaults to required+deny; the jar's own
    policy section may relax fallback to "warn". A jar with no egress block
    is not tunnel-bound (required=False).
    """
    egress = package.get("egress") if isinstance(package, dict) else None
    if not isinstance(egress, dict):
        return {"required": False, "fallback": FALLBACK_DIRECT}
    raw = egress.get("policy")
    policy = dict(raw) if isinstance(raw, dict) else {}
    fallback = str(policy.get("fallback", FALLBACK_DENY)).lower()
    if fallback not in (FALLBACK_DENY, FALLBACK_WARN):
        logger.warning("Unknown egress fallback %r; treating as deny", fallback)
        fallback = FALLBACK_DENY
    return {
        "required": bool(policy.get("required", True)),
        "fallback": fallback,
    }


def enforce_egress(
    echo: Dict[str, Any],
    hint: Dict[str, Any],
    policy: Dict[str, Any],
) -> Tuple[str, str]:
    """Compare a live egress echo against the jar's origin hint.

    echo/hint shape: {"country": "IN", "asn": "AS24560", "ip_hash": "sha256:..."}.
    Country and ASN must match. ip_hash mismatch is a warning-grade signal
    (residential DHCP renumbering is real) unless it is the only signal.

    Returns (action, message) where action is "ok", "warn", or "deny".
    Raises nothing; denial is expressed as the "deny" action so callers can
    attach context before raising EgressCheckError.
    """
    fallback = (policy or {}).get("fallback", FALLBACK_DENY)
    echo = echo or {}
    hint = hint or {}
    problems = []

    for field in ("country", "asn"):
        want = str(hint.get(field, "") or "").upper()
        got = str(echo.get(field, "") or "").upper()
        if want and got and want != got:
            problems.append(f"{field} mismatch: circuit={got or '?'} jar={want}")

    want_hash = str(hint.get("ip_hash", "") or "")
    got_hash = str(echo.get("ip_hash", "") or "")
    hash_note = ""
    if want_hash and got_hash and want_hash != got_hash:
        hash_note = " (egress IP rotated since export; country/ASN still match)"

    if problems:
        message = "Egress check failed: " + "; ".join(problems)
        if fallback == FALLBACK_WARN:
            return "warn", message + " — proceeding per jar policy fallback=warn"
        return "deny", message + " — refusing to launch (fallback=deny)"

    if hash_note:
        return "ok", "Egress check passed" + hash_note
    return "ok", "Egress check passed: country/ASN match origin hint"
