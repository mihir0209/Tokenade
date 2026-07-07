"""
Session state conversion between .tokenade and Playwright storage_state format.

Enables CloakBrowser to inject Tokenade sessions at launch time via
`launch_context(storage_state=...)` — no CDP proxy needed.

Usage:
    from tokenade.core.browser.session_state import (
        tokenade_to_storage_state,
        storage_state_to_tokenade,
        load_as_storage_state,
    )

    # Convert .tokenade → Playwright storage_state
    state = load_as_storage_state("gmail.tokenade")

    # Use with CloakBrowser
    from cloakbrowser import launch_context
    ctx = launch_context(storage_state="gmail_state.json")
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def tokenade_to_storage_state(
    session_file: str,
    password: Optional[str] = None,
    browser: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert a .tokenade session file to Playwright storage_state format.

    Args:
        session_file: Path to .tokenade file.
        password: Optional decryption password for encrypted files.
        browser: Source browser name (firefox/chrome/brave). Helps with expires conversion.

    Returns:
        Dict with "cookies" and "origins" keys (Playwright storage_state format).
    """
    with open(session_file) as f:
        session = json.load(f)

    # Handle encrypted files
    if session.get("encrypted") and password:
        try:
            from tokenade.core.crypto.at_rest import decrypt_session
            session = decrypt_session(session, password)
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")

    cookies = session.get("cookies", [])

    # Handle both v2.0 (flat) and v3.0 (per-origin) storage formats
    storage = session.get("storage", {})
    local_storage_flat = session.get("local_storage", {})

    # v3.0: storage.local is {origin: {key: value}}
    # v2.0: local_storage is flat {key: value}
    if storage.get("local"):
        local_storage_per_origin = storage["local"]
    elif local_storage_flat:
        # Convert flat to per-origin
        domain = _infer_origin_from_cookies(cookies)
        local_storage_per_origin = {domain: local_storage_flat}
    else:
        local_storage_per_origin = {}

    # Convert cookies to Playwright format
    pw_cookies = []
    for c in cookies:
        pw_cookie = {
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
            "secure": c.get("secure", False),
            "httpOnly": c.get("httpOnly", False),
        }

        # Handle sameSite
        ss = c.get("sameSite", c.get("samesite", ""))
        if ss:
            if isinstance(ss, int):
                ss_map = {0: "None", 1: "Lax", 2: "Strict", -1: "None"}
                ss = ss_map.get(ss, "None")
            pw_cookie["sameSite"] = ss
        else:
            pw_cookie["sameSite"] = "None"

        # Handle expires — different formats per browser
        # Firefox: milliseconds since Unix epoch (~1.8 trillion, 13 digits)
        # Chrome/Brave/Edge: microseconds since 1601-01-01 (~13 quadrillion, 16 digits)
        # Playwright expects: Unix timestamp in seconds
        expires = c.get("expires", 0)
        if expires and int(expires) > 0:
            exp_int = int(expires)
            # Heuristic: 14+ digits = Chrome epoch, 13 digits = Firefox ms
            if exp_int > 10000000000000:
                # Chrome epoch (microseconds since 1601) → Unix seconds
                exp_int = (exp_int // 1000000) - 11644473600
            elif exp_int > 1000000000000:
                # Firefox milliseconds → Unix seconds
                exp_int = exp_int // 1000
            pw_cookie["expires"] = exp_int
        else:
            pw_cookie["expires"] = -1

        pw_cookies.append(pw_cookie)

    # Convert localStorage to Playwright origins format
    origins = []
    if local_storage_per_origin:
        for origin, items in local_storage_per_origin.items():
            entries = [{"name": k, "value": str(v)} for k, v in items.items()]
            if entries:
                origins.append({
                    "origin": origin,
                    "localStorage": entries,
                })

    return {
        "cookies": pw_cookies,
        "origins": origins,
    }


def storage_state_to_tokenade(state_file: str) -> Dict[str, Any]:
    """Convert a Playwright storage_state JSON to .tokenade format.

    Args:
        state_file: Path to Playwright storage_state JSON file.

    Returns:
        Dict in .tokenade format.
    """
    with open(state_file) as f:
        state = json.load(f)

    cookies = state.get("cookies", [])
    origins = state.get("origins", [])

    # Convert cookies
    tk_cookies = []
    for c in cookies:
        tk_cookie = {
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
            "secure": c.get("secure", False),
            "httpOnly": c.get("httpOnly", False),
        }

        ss = c.get("sameSite", "None")
        if ss == "Lax":
            tk_cookie["samesite"] = 1
        elif ss == "Strict":
            tk_cookie["samesite"] = 2
        else:
            tk_cookie["samesite"] = -1

        expires = c.get("expires", -1)
        if expires and expires > 0:
            # Unix seconds → Firefox milliseconds
            tk_cookie["expires"] = int(expires) * 1000
        else:
            tk_cookie["expires"] = 0

        tk_cookies.append(tk_cookie)

    # Convert localStorage
    local_storage = {}
    for origin_data in origins:
        for entry in origin_data.get("localStorage", []):
            local_storage[entry["name"]] = entry["value"]

    return {
        "version": "2.0",
        "site_name": "imported",
        "auth_status": "unknown",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cookies": tk_cookies,
        "local_storage": local_storage,
        "metadata": {
            "source": "storage_state_import",
        },
    }


def load_as_storage_state(session_file: str, output_path: Optional[str] = None, password: Optional[str] = None) -> str:
    """Load a .tokenade file and write it as a Playwright storage_state JSON.

    Args:
        session_file: Path to .tokenade file.
        output_path: Where to write the JSON. If None, writes to a temp file.
        password: Optional decryption password.

    Returns:
        Path to the written storage_state JSON file.
    """
    state = tokenade_to_storage_state(session_file, password=password)

    if output_path is None:
        import tempfile
        fd, output_path = tempfile.mkstemp(suffix="_state.json", prefix="tokenade_")
        import os
        os.close(fd)

    with open(output_path, "w") as f:
        json.dump(state, f, indent=2)

    logger.info(
        f"Converted {session_file} → {output_path} "
        f"({len(state['cookies'])} cookies, {len(state['origins'])} origins)"
    )
    return output_path


def _infer_origin_from_cookies(cookies: List[Dict]) -> str:
    """Infer the origin URL from cookie domains."""
    for c in cookies:
        domain = c.get("domain", "")
        if domain.startswith("."):
            domain = domain[1:]
        if domain:
            return f"https://{domain}"
    return "https://unknown"


def _infer_domain(session: Dict[str, Any], key: str) -> str:
    """Infer the domain for a localStorage key from session metadata."""
    cookies = session.get("cookies", [])
    if cookies:
        # Use the first cookie's domain
        domain = cookies[0].get("domain", "")
        if domain.startswith("."):
            domain = domain[1:]
        return domain

    site_name = session.get("site_name", "unknown")
    domain_map = {
        "google": "mail.google.com",
        "github": "github.com",
        "discord": "discord.com",
        "reddit": "www.reddit.com",
        "twitter": "x.com",
        "openai": "chat.openai.com",
    }
    return domain_map.get(site_name, f"{site_name}.com")
