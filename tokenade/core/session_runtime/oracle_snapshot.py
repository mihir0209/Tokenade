"""
Oracle snapshot - Ed25519-signed fingerprint snapshots for the v3.1 jar.

The origin daemon (`tokenade tunnel serve`) generates a keypair once and
signs fingerprint snapshots it embeds at export time. The consumer pins the
origin public key at `pair` time and verifies every snapshot before use.

Snapshot shape (stored under jar["oracle_snapshot"]):
    {"values": {...}, "collected_at": "<iso>", "ttl_s": 86400,
     "origin_pub": "<base64>", "origin_sig": "<base64>"}

The signature covers the canonical JSON of {values, collected_at, ttl_s}.
"""

import base64
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_SNAPSHOT_TTL_S = 24 * 3600


def _default_key_dir() -> Path:
    return Path.home() / ".tokenade" / "tunnel"


def origin_key_paths(key_dir: Optional[Path] = None) -> Tuple[Path, Path]:
    """Return (private_path, public_path) for the origin keypair."""
    directory = Path(key_dir) if key_dir else _default_key_dir()
    return directory / "origin_ed25519", directory / "origin_ed25519.pub"


def generate_origin_keypair(key_dir: Optional[Path] = None):
    """Generate (or load, if present) the origin Ed25519 keypair.

    Returns (private_key, public_key) cryptography objects. Private key is
    stored PEM/PKCS8 with 0o600 permissions.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv_path, pub_path = origin_key_paths(key_dir)
    if priv_path.exists() and pub_path.exists():
        return load_origin_private_key(priv_path), load_origin_public_key(pub_path)

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    priv_path.parent.mkdir(parents=True, exist_ok=True)
    priv_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    try:
        import os

        os.chmod(priv_path, 0o600)
    except OSError:
        pass
    pub_path.write_bytes(
        public_key.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
    )
    logger.info("Generated origin Ed25519 keypair at %s", priv_path)
    return private_key, public_key


def load_origin_private_key(path: Optional[Path] = None):
    """Load the origin Ed25519 private key from disk."""
    from cryptography.hazmat.primitives import serialization

    priv_path, _ = origin_key_paths(None)
    target = Path(path) if path else priv_path
    return serialization.load_pem_private_key(target.read_bytes(), password=None)


def load_origin_public_key(path: Optional[Path] = None):
    """Load the origin Ed25519 public key from disk (raw 32 bytes file)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    _, pub_path = origin_key_paths(None)
    target = Path(path) if path else pub_path
    return Ed25519PublicKey.from_public_bytes(target.read_bytes())


def public_key_b64(public_key) -> str:
    """Raw public key bytes as base64 (for embedding/pinning)."""
    from cryptography.hazmat.primitives import serialization

    raw = public_key.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(raw).decode("ascii")


def _canonical(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_snapshot(
    values: Dict[str, Any],
    private_key,
    ttl_s: int = DEFAULT_SNAPSHOT_TTL_S,
) -> Dict[str, Any]:
    """Sign a fingerprint snapshot; returns the embeddable snapshot dict."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    collected_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {"values": values, "collected_at": collected_at, "ttl_s": int(ttl_s)}
    signature = private_key.sign(_canonical(payload))
    public_key = private_key.public_key()
    assert isinstance(public_key, Ed25519PublicKey)
    return {
        **payload,
        "origin_pub": public_key_b64(public_key),
        "origin_sig": base64.b64encode(signature).decode("ascii"),
    }


def verify_snapshot(
    snapshot: Dict[str, Any],
    public_key=None,
) -> Tuple[bool, str, float]:
    """Verify signature, key pin, and TTL of an oracle snapshot.

    Returns (ok, reason, age_s). Reasons: "valid", "valid-stale" (signature
    good but TTL expired — usable only as a degraded hint, never silently),
    "bad-signature", "key-mismatch", "malformed".
    """
    try:
        values = snapshot["values"]
        collected_at = snapshot["collected_at"]
        ttl_s = int(snapshot.get("ttl_s", DEFAULT_SNAPSHOT_TTL_S))
        origin_pub = snapshot["origin_pub"]
        signature = base64.b64decode(snapshot["origin_sig"])
    except (KeyError, TypeError, ValueError) as exc:
        return False, f"malformed: {exc}", -1.0

    if public_key is not None and public_key_b64(public_key) != origin_pub:
        return False, "key-mismatch: snapshot not signed by pinned origin key", -1.0

    if public_key is None:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )

            public_key = Ed25519PublicKey.from_public_bytes(
                base64.b64decode(origin_pub)
            )
        except Exception as exc:
            return False, f"malformed: bad origin_pub ({exc})", -1.0

    try:
        public_key.verify(
            signature, _canonical({"values": values, "collected_at": collected_at, "ttl_s": ttl_s})
        )
    except Exception:
        return False, "bad-signature", -1.0

    try:
        collected = datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
        age_s = (datetime.now(timezone.utc) - collected).total_seconds()
    except ValueError:
        return False, "malformed: bad collected_at", -1.0

    if age_s > ttl_s:
        return False, "valid-stale: TTL expired", age_s
    return True, "valid", age_s
