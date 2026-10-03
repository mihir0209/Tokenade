"""
Pairing - Single-use codes binding a consumer to an origin's remote_ref.

Origin side: create_pairing(remote_ref, consumer_token) -> code. The code is
shown once (serve output / `tunnel share`) and handed to the consumer
out-of-band. Consumer side: redeem_pairing(code) is implicit — the consumer
just pastes the code into `tunnel pair <code>`, which stores
(remote_ref, relay_url, consumer_token) locally and pushes the token ref
into the OS keyring. Codes are single-use: redeeming deletes the record.

Storage: ~/.tokenade/tunnel/pairings.json (origin, 0o600) and
~/.tokenade/tunnel/consumers.json (consumer side, 0o600).
"""

import json
import logging
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional

from tokenade.core.tunnel.errors import PairingError

logger = logging.getLogger(__name__)

PAIRING_TTL_S = 15 * 60


def _tunnel_dir() -> Path:
    return Path.home() / ".tokenade" / "tunnel"


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    try:
        import os

        os.chmod(path, 0o600)
    except OSError:
        pass


def create_pairing(
    remote_ref: str,
    relay_url: str,
    consumer_token: Optional[str] = None,
    ttl_s: int = PAIRING_TTL_S,
    store: Optional[Path] = None,
) -> Dict[str, str]:
    """Create a single-use pairing code. Returns {code, remote_ref, ...}."""
    code = "tk-" + secrets.token_urlsafe(9)
    token = consumer_token or secrets.token_urlsafe(24)
    path = Path(store) if store else _tunnel_dir() / "pairings.json"
    data = _load_json(path)
    data[code] = {
        "remote_ref": remote_ref,
        "relay_url": relay_url,
        "consumer_token": token,
        "created_at": time.time(),
        "ttl_s": ttl_s,
    }
    _save_json(path, data)
    return {"code": code, "remote_ref": remote_ref, "relay_url": relay_url}


def redeem_pairing(code: str, store: Optional[Path] = None) -> Dict[str, str]:
    """Redeem a code once. Returns connection details; code is deleted."""
    path = Path(store) if store else _tunnel_dir() / "pairings.json"
    data = _load_json(path)
    record = data.get(code)
    if record is None:
        raise PairingError("unknown or already-used pairing code")
    if time.time() - float(record.get("created_at", 0)) > float(
        record.get("ttl_s", PAIRING_TTL_S)
    ):
        data.pop(code, None)
        _save_json(path, data)
        raise PairingError("pairing code expired")
    data.pop(code, None)
    _save_json(path, data)
    return {
        "remote_ref": record["remote_ref"],
        "relay_url": record["relay_url"],
        "consumer_token": record["consumer_token"],
    }


def save_consumer_record(
    remote_ref: str, relay_url: str, consumer_token: str,
    store: Optional[Path] = None,
) -> None:
    """Persist a redeemed pairing on the consumer side + keyring ref."""
    path = Path(store) if store else _tunnel_dir() / "consumers.json"
    data = _load_json(path)
    data[remote_ref] = {
        "relay_url": relay_url,
        "token_ref": f"keyring:tokenade-tunnel-{remote_ref}",
        "saved_at": time.time(),
    }
    _save_json(path, data)
    try:
        import keyring

        keyring.set_password("tokenade-tunnel", remote_ref, consumer_token)
    except Exception as exc:
        logger.warning("keyring unavailable, token kept in memory only: %s", exc)


def load_consumer_token(remote_ref: str, store: Optional[Path] = None) -> str:
    """Load a consumer token from the keyring (raises PairingError)."""
    try:
        import keyring

        token = keyring.get_password("tokenade-tunnel", remote_ref)
    except Exception as exc:
        raise PairingError(f"keyring unavailable: {exc}") from exc
    if not token:
        raise PairingError(f"no paired token for {remote_ref}; run `tunnel pair <code>`")
    return token
