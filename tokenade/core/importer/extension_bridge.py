"""Export sessions through the Tokenade browser extension's in-page bridge.

The extension ships a MAIN-world bridge (``window.Tokenade``) backed by an
isolated-world content script. That context can read Web Storage that page-JS
automation cannot see — e.g. ``discord.com`` deletes ``window.localStorage``
after boot, so CDP ``Runtime.evaluate`` and Playwright always come back
empty while the tab itself is logged in.

This module drives the bridge over CDP with ``window.postMessage``
roundtrips:

- localStorage / sessionStorage, pulled in small key batches (CDP inline
  result limits make single-shot big reads unreliable),
- cookies via the extension's ``chrome.cookies`` API (full values,
  HttpOnly included, no SQLite decryption involved).

Requires the unpacked ``extension/`` loaded in the target browser
(``chrome://extensions`` → Developer mode → Load unpacked) and a reachable
remote-debugging port. Raises :class:`ExtensionBridgeMissing` otherwise.
"""

import asyncio
import json
import logging
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_BRIDGE_PROBE = "typeof window.Tokenade"

# (ask message, answer message, answer field)
_CHANNELS = {
    "local": ("TOKENADE_GET_LOCALSTORAGE", "TOKENADE_LOCALSTORAGE_RESULT", "localStorage"),
    "session": ("TOKENADE_GET_SESSIONSTORAGE", "TOKENADE_SESSIONSTORAGE_RESULT", "sessionStorage"),
    "cookies": ("TOKENADE_GET_COOKIES", "TOKENADE_COOKIES_RESULT", "cookies"),
}

_SAME_SITE_MAP = {
    "no_restriction": "None",
    "lax": "Lax",
    "strict": "Strict",
    "unspecified": "Lax",
}


class ExtensionBridgeMissing(Exception):
    """The Tokenade extension bridge is not present in the target tab."""


def build_probe_expr() -> str:
    """JS expression reporting the bridge type (``object`` when loaded).

    Deliberately *not* JSON-wrapped: the caller compares the plain value.
    """
    return _BRIDGE_PROBE


def build_roundtrip_expr(ask: str, want: str, field: str,
                         only_keys: Optional[List[str]] = None) -> str:
    """JS that asks the content script for data and resolves small JSON.

    Args:
        ask: Outgoing ``window.postMessage`` type.
        want: Incoming answer message type.
        field: Answer payload field holding the data.
        only_keys: When given, only these keys are returned (keeps each
            response small enough for CDP inline results).
    """
    if only_keys is None:
        pick = "o=src;"
    else:
        pick = (
            "var F=%s;o={};"
            "for(var i=0;i<F.length;i++){"
            "if(src[F[i]]!==undefined)o[F[i]]=src[F[i]];}"
        ) % json.dumps(only_keys)
    return (
        "new Promise(res=>{"
        "window.addEventListener('message',function h(e){"
        f"if(e.data&&e.data.type==={json.dumps(want)}){{"
        "window.removeEventListener('message',h);"
        "try{"
        f"var src=e.data.{field}||{{}};"
        + pick +
        "res(JSON.stringify(o));"
        "}catch(err){res('SERFAIL');}"
        "}});"
        f"window.postMessage({{type:{json.dumps(ask)}}},'*');"
        "setTimeout(()=>res('TIMEOUT'),8000);})"
    )


def build_keys_expr(ask: str, want: str, field: str) -> str:
    """JS resolving to the JSON list of available keys (small response)."""
    return (
        "new Promise(res=>{"
        "window.addEventListener('message',function h(e){"
        f"if(e.data&&e.data.type==={json.dumps(want)}){{"
        "window.removeEventListener('message',h);"
        f"res(JSON.stringify(Object.keys(e.data.{field}||{{}})));}}}});"
        f"window.postMessage({{type:{json.dumps(ask)}}},'*');"
        "setTimeout(()=>res('TIMEOUT'),8000);})"
    )


def convert_bridge_cookies(raw_cookies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert ``chrome.cookies`` entries to tokenade cookie dicts."""
    out = []
    for c in raw_cookies or []:
        name = c.get("name", "")
        if not name:
            continue
        cookie = {
            "name": name,
            "value": c.get("value", ""),
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
            "secure": bool(c.get("secure", False)),
            "httpOnly": bool(c.get("httpOnly", False)),
        }
        same_site = str(c.get("sameSite", "unspecified")).lower()
        cookie["sameSite"] = _SAME_SITE_MAP.get(same_site, "None")
        expires = c.get("expirationDate", 0) or 0
        try:
            exp = int(float(expires))
        except (TypeError, ValueError):
            exp = 0
        if exp > 0:
            cookie["expires"] = exp
        out.append(cookie)
    return out


class _BridgeSession:
    """One CDP tab websocket with id-matched request/response."""

    def __init__(self, ws, timeout: float = 12.0):
        self._ws = ws
        self._timeout = timeout
        self._next_id = 0

    async def cmd(self, method, params=None):
        self._next_id += 1
        mid = self._next_id
        msg = {"id": mid, "method": method}
        if params:
            msg["params"] = params
        await self._ws.send(json.dumps(msg))
        import time as _time

        deadline = _time.time() + 30
        while _time.time() < deadline:
            try:
                raw = await asyncio.wait_for(
                    self._ws.recv(), timeout=min(4, deadline - _time.time())
                )
            except asyncio.TimeoutError:
                continue
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            if data.get("id") == mid:
                if "error" in data:
                    raise RuntimeError(data["error"].get("message", "CDP error"))
                return data.get("result", {})
        raise RuntimeError(f"CDP timeout: {method}")

    async def evaluate(self, expression, timeout: float = 25.0):
        """Evaluate and unwrap the inner value (None on timeout).

        Single send per attempt with a fresh id; a retry only starts
        after the previous attempt's deadline, so in-flight responses
        are never orphaned and eaten by a later call.
        """
        import time as _time

        deadline = _time.time() + timeout
        while _time.time() < deadline:
            self._next_id += 1
            mid = self._next_id
            await self._ws.send(json.dumps({
                "id": mid, "method": "Runtime.evaluate",
                "params": {"expression": expression, "awaitPromise": True,
                           "returnByValue": True},
            }))
            attempt_end = min(deadline, _time.time() + 12)
            while _time.time() < attempt_end:
                try:
                    raw = await asyncio.wait_for(
                        self._ws.recv(), timeout=min(4, attempt_end - _time.time())
                    )
                except asyncio.TimeoutError:
                    continue
                try:
                    data = json.loads(raw)
                except ValueError:
                    continue
                if data.get("id") == mid:
                    inner = data.get("result") or {}
                    return (inner.get("result") or {}).get("value")
        return None


def _tab_for_domain(port: int, domain: str, timeout: int = 10) -> Dict[str, Any]:
    """Return a tab on ``https://<domain>`` (reuse or create), else raise."""
    origin = f"https://{domain.lstrip('.')}"
    targets = json.loads(urllib.request.urlopen(
        f"http://127.0.0.1:{port}/json/list", timeout=timeout).read().decode())
    for target in targets:
        if target.get("type") == "page" and (target.get("url") or "").startswith(origin):
            return target
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/json/new?{origin}", method="PUT")
    tab = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())
    if not tab.get("webSocketDebuggerUrl"):
        raise RuntimeError(f"CDP could not open a tab for {origin}")
    return tab


async def _export_one(session, origin: str,
                      batch_size: int = 8) -> Dict[str, Any]:
    """Pull cookies + storage from one tab session already on ``origin``."""
    stores: Dict[str, Dict[str, str]] = {}
    for kind in ("local", "session"):
        ask, want, field = _CHANNELS[kind]
        keys_raw = await session.evaluate(build_keys_expr(ask, want, field))
        try:
            keys = json.loads(keys_raw) if isinstance(keys_raw, str) else []
        except ValueError:
            keys = []
        merged: Dict[str, str] = {}
        for i in range(0, len(keys), batch_size):
            raw = await session.evaluate(
                build_roundtrip_expr(ask, want, field, keys[i:i + batch_size]))
            if not raw or raw in ("TIMEOUT", "SERFAIL"):
                continue
            try:
                part = json.loads(raw)
            except ValueError:
                continue
            if isinstance(part, dict):
                merged.update({k: v for k, v in part.items() if isinstance(v, str)})
        stores[kind] = merged
        print(f"   [EXT] {origin} {kind}Storage entries: {len(merged)}")
    raw_cookies = await session.evaluate(
        build_roundtrip_expr(*_CHANNELS["cookies"]))
    cookies: List[Dict[str, Any]] = []
    if raw_cookies and raw_cookies not in ("TIMEOUT", "SERFAIL"):
        try:
            parsed = json.loads(raw_cookies)
        except ValueError:
            parsed = []
        if isinstance(parsed, list):
            cookies = convert_bridge_cookies(parsed)
    print(f"   [EXT] {origin} cookies: {len(cookies)}")
    return {"cookies": cookies, "local": stores["local"],
            "session": stores["session"]}


async def _export_async(port: int, domains: List[str],
                        batch_size: int = 8) -> Dict[str, Any]:
    import websockets

    domains = [d.strip().lstrip(".") for d in domains if d and d.strip()]
    if not domains:
        raise ValueError("extension export needs at least one domain")
    all_cookies: List[Dict[str, Any]] = []
    seen_cookies = set()
    per_origin_local: Dict[str, Dict[str, str]] = {}
    per_origin_session: Dict[str, Dict[str, str]] = {}
    for domain in domains:
        origin = f"https://{domain}"
        tab = _tab_for_domain(port, domain)
        ws = await websockets.connect(tab["webSocketDebuggerUrl"],
                                      max_size=300 * 1024 * 1024)
        try:
            session = _BridgeSession(ws)
            # Fresh tabs may not have the content script yet; the extension
            # registers it on document load. Poll briefly before giving up.
            probe = None
            for _ in range(6):
                probe = await session.evaluate(build_probe_expr())
                if probe == "object":
                    break
                await asyncio.sleep(2)
            if probe != "object":
                raise ExtensionBridgeMissing(
                    "Tokenade extension bridge not found in the %s tab. "
                    "Load it first: open chrome://extensions (or brave://extensions, "
                    "edge://extensions), enable Developer mode, 'Load unpacked' the "
                    "repo's extension/ directory, then retry on a tab you opened "
                    "after loading it." % domain
                )
            await asyncio.sleep(2)
            one = await _export_one(session, origin, batch_size)
        finally:
            try:
                await ws.close()
            except Exception:
                pass
        for cookie in one["cookies"]:
            key = (cookie.get("domain"), cookie.get("name"), cookie.get("path"))
            if key not in seen_cookies:
                seen_cookies.add(key)
                all_cookies.append(cookie)
        if one["local"]:
            per_origin_local[origin] = one["local"]
        if one["session"]:
            per_origin_session[origin] = one["session"]
    flat_local = {k: v for entries in per_origin_local.values() for k, v in entries.items()}
    flat_session = {k: v for entries in per_origin_session.values() for k, v in entries.items()}
    print(f"   [EXT] Cookies: {len(all_cookies)}")
    return {
        "cookies": all_cookies,
        "local_storage": flat_local,
        "session_storage": flat_session,
        "storage": {"local": per_origin_local, "session": per_origin_session},
    }


def export_via_bridge_sync(port: int, domains: List[str]) -> Dict[str, Any]:
    """Synchronous wrapper for CLI use."""
    return asyncio.run(_export_async(port, domains))
