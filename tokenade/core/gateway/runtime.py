"""Gateway runtime binding route decisions to isolated browser contexts."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Protocol
from urllib.parse import urlparse

from tokenade.core.gateway.session_store import SessionRecord
from tokenade.core.importer.session_loader import SessionLoader

logger = logging.getLogger(__name__)

_MS_THRESHOLD = 1262304000000
_ALLOWED_URL_SCHEMES = frozenset(("http", "https"))
_MAX_LS_ENTRIES_PER_ORIGIN = 500
WINDOW_POLICIES = frozenset(("reuse-active-window", "new-tab", "new-context", "headless-context"))


class GatewayRuntimeError(RuntimeError):
    """Raised when isolated session context work fails."""


class GatewayContext(Protocol):
    """Small Playwright-compatible context interface used by gateway runtime."""

    def add_cookies(self, cookies: list[Dict[str, Any]]):
        ...

    def new_page(self):
        ...

    def close(self):
        ...


class GatewayContextFactory(Protocol):
    """Creates one isolated context per session."""

    def create_context(self, session: SessionRecord):
        ...

    def close(self):
        ...


@dataclass
class GatewaySessionContext:
    """Runtime state for one isolated session context."""

    session: SessionRecord
    context: Any
    created_at: float
    cookies_injected: int = 0
    local_storage_origins: list[str] = field(default_factory=list)
    page_count: int = 0
    active_page: Any = None
    lease_id: Optional[str] = None
    leased_by: Optional[str] = None
    lease_expires_at: Optional[float] = None
    draining: bool = False
    closed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session": self.session.to_dict(),
            "created_at": self.created_at,
            "cookie_count_injected": self.cookies_injected,
            "origins": list(self.local_storage_origins),
            "page_count": self.page_count,
            "lease_id": self.lease_id,
            "leased_by": self.leased_by,
            "lease_expires_at": self.lease_expires_at,
            "leased": self.lease_expires_at is not None and self.lease_expires_at > time.time(),
            "draining": self.draining,
            "closed": self.closed,
        }


class _ContextWrapper:
    """Lightweight wrapper around a Playwright browser context."""

    def __init__(self, context, config):
        self._context = context
        self.config = config

    def add_cookies(self, cookies: list[Dict[str, Any]]):
        if self._context:
            return self._context.add_cookies(cookies)
        return 0

    def new_page(self):
        if self._context:
            return self._context.new_page()
        raise GatewayRuntimeError("browser context is not active")

    def add_init_script(self, script: str):
        if self._context and hasattr(self._context, "add_init_script"):
            return self._context.add_init_script(script)

    def close(self):
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass


class BrowserManagerContextFactory:
    """Default factory that creates isolated browser-manager contexts.

    Uses a single browser instance and creates multiple isolated contexts from it.
    This avoids the Playwright asyncio event loop issue when creating multiple contexts.
    """

    def __init__(self, backend: str = "cloakbrowser", headless: bool = True):
        self.backend = backend
        self.headless = headless
        self._browser_manager = None
        self._contexts = []

    def _ensure_browser(self):
        """Ensure browser is launched, create on first call."""
        if self._browser_manager is None:
            from tokenade.core.browser.manager import BrowserFactory
            self._browser_manager = BrowserFactory.create(
                backend="cloakbrowser" if self.backend in ("cloak", "cloakbrowser") else "playwright",
                browser_type=self.backend,
                headless=self.headless,
            )
            self._browser_manager.launch()
            if getattr(self._browser_manager, "_browser", None):
                # BrowserManager.launch() creates a default context/page for single-session use.
                # Gateway creates per-session contexts itself, so close the throwaway startup
                # context to avoid an extra visible window.
                startup_context = getattr(self._browser_manager, "_context", None)
                if startup_context is not None:
                    try:
                        startup_context.close()
                    except Exception:
                        pass
                self._browser_manager._context = None
                if hasattr(self._browser_manager, "_page"):
                    self._browser_manager._page = None
        return self._browser_manager

    def create_context(self, session: SessionRecord):
        manager = self._ensure_browser()
        # Create a new isolated context from the same browser
        if hasattr(manager, '_browser') and manager._browser:
            context = manager._browser.new_context(viewport=manager.config.viewport)
            wrapper = _ContextWrapper(context, manager.config)
            self._contexts.append(context)
            return _BrowserManagerGatewayContext(wrapper)
        return _BrowserManagerGatewayContext(manager)

    def close(self):
        for context in list(self._contexts):
            try:
                context.close()
            except Exception:
                pass
        self._contexts.clear()
        if self._browser_manager is not None:
            try:
                self._browser_manager.close()
            except Exception:
                pass
            self._browser_manager = None


class _BrowserManagerGatewayContext:
    """Adapter from BrowserManager to the gateway context interface."""

    def __init__(self, manager):
        self.manager = manager

    def add_cookies(self, cookies: list[Dict[str, Any]]):
        return self.manager.add_cookies(cookies)

    def new_page(self):
        if getattr(self.manager, "_context", None) is None:
            raise GatewayRuntimeError("browser context is not active")
        return self.manager._context.new_page()

    def add_init_script(self, script: str):
        if getattr(self.manager, "_context", None) is None:
            raise GatewayRuntimeError("browser context is not active")
        if hasattr(self.manager._context, "add_init_script"):
            return self.manager._context.add_init_script(script)

    def close(self):
        return self.manager.close()


class GatewayRuntime:
    """Routes work to isolated per-session contexts."""

    def __init__(self, context_factory: GatewayContextFactory, target_url: Optional[str] = None, window_policy: str = "reuse-active-window"):
        self.context_factory = context_factory
        self._loader = SessionLoader()
        self._contexts: Dict[str, GatewaySessionContext] = {}
        self.active_context_id: Optional[str] = None
        self._target_origins = _target_origins(target_url)
        self.window_policy = _validate_window_policy(window_policy)
        self._work_queue: "queue.Queue[tuple[Any, ...]]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._worker_id: Optional[int] = None

    def _call_runtime(self, fn, *args, **kwargs):
        if threading.get_ident() == self._worker_id:
            return fn(*args, **kwargs)
        self._start_worker()
        done = threading.Event()
        item = [fn, args, kwargs, done, None, None]
        self._work_queue.put(item)
        done.wait()
        if item[5] is not None:
            raise item[5]
        return item[4]

    def _start_worker(self):
        if self._worker and self._worker.is_alive():
            return
        self._worker = threading.Thread(target=self._run_worker, name="tokenade-gateway-runtime", daemon=True)
        self._worker.start()

    def _run_worker(self):
        self._worker_id = threading.get_ident()
        while True:
            item = self._work_queue.get()
            if item is None:
                break
            fn, args, kwargs, done = item[:4]
            try:
                item[4] = fn(*args, **kwargs)
            except Exception as exc:
                item[5] = exc
            finally:
                done.set()

    def ensure_context(self, session: SessionRecord) -> GatewaySessionContext:
        return self._call_runtime(self._ensure_context, session)

    def _ensure_context(self, session: SessionRecord) -> GatewaySessionContext:
        existing = self._contexts.get(session.id)
        if existing and not existing.closed:
            return existing

        package = self._load_package(session.path)
        context = self.context_factory.create_context(session)
        runtime_context = GatewaySessionContext(session=session, context=context, created_at=time.time())
        runtime_context.cookies_injected = self._inject_cookies(context, package.get("cookies", []))
        runtime_context.local_storage_origins = self._inject_storage(context, package)
        self._contexts[session.id] = runtime_context
        return runtime_context

    def activate(self, session: SessionRecord) -> GatewaySessionContext:
        return self._call_runtime(self._activate, session)

    def _activate(self, session: SessionRecord) -> GatewaySessionContext:
        runtime_context = self._ensure_context(session)
        self.active_context_id = session.id
        return runtime_context

    def new_page(self, session: Optional[SessionRecord] = None, url: Optional[str] = None, window_policy: Optional[str] = None) -> Dict[str, Any]:
        return self._call_runtime(self._new_page, session, url, window_policy)

    def _new_page(self, session: Optional[SessionRecord] = None, url: Optional[str] = None, window_policy: Optional[str] = None) -> Dict[str, Any]:
        if session is not None:
            runtime_context = self._activate(session)
        elif self.active_context_id:
            runtime_context = self._contexts[self.active_context_id]
        else:
            raise GatewayRuntimeError("no active context")

        policy = _validate_window_policy(window_policy or self.window_policy)
        page, created = self._page_for_policy(runtime_context, policy)
        navigation_error = None
        if url and hasattr(page, "goto"):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                navigation_error = str(exc)
        if created:
            runtime_context.page_count += 1
        runtime_context.active_page = page
        result = {"success": True, "context": runtime_context.to_dict()}
        result["window_policy"] = policy
        result["page_reused"] = not created
        if navigation_error:
            result["navigation_error"] = navigation_error
        return result

    def _page_for_policy(self, runtime_context: GatewaySessionContext, policy: str):
        if policy == "reuse-active-window":
            page = runtime_context.active_page
            if page is not None and not _page_is_closed(page):
                return page, False
        return runtime_context.context.new_page(), True

    def lease(self, session: SessionRecord, ttl_seconds: float = 900, leased_by: Optional[str] = None) -> Dict[str, Any]:
        return self._call_runtime(self._lease, session, ttl_seconds, leased_by)

    def _lease(self, session: SessionRecord, ttl_seconds: float = 900, leased_by: Optional[str] = None) -> Dict[str, Any]:
        runtime_context = self._activate(session)
        runtime_context.lease_id = uuid.uuid4().hex
        runtime_context.leased_by = leased_by
        runtime_context.lease_expires_at = time.time() + max(float(ttl_seconds), 1.0)
        return {"success": True, "context": runtime_context.to_dict(), "lease_id": runtime_context.lease_id}

    def release(self, context_id: Optional[str] = None, lease_id: Optional[str] = None) -> Dict[str, Any]:
        return self._call_runtime(self._release, context_id, lease_id)

    def _release(self, context_id: Optional[str] = None, lease_id: Optional[str] = None) -> Dict[str, Any]:
        for session_id, runtime_context in self._contexts.items():
            if context_id and session_id != context_id:
                continue
            if lease_id and runtime_context.lease_id != lease_id:
                continue
            if not context_id and not lease_id:
                continue
            runtime_context.lease_id = None
            runtime_context.leased_by = None
            runtime_context.lease_expires_at = None
            return {"success": True, "context_id": session_id}
        raise GatewayRuntimeError("no matching leased context")

    def drain_inactive(self, force: bool = False) -> Dict[str, Any]:
        return self._call_runtime(self._drain_inactive, force)

    def _drain_inactive(self, force: bool = False) -> Dict[str, Any]:
        closed = []
        preserved = []
        now = time.time()
        for session_id, runtime_context in list(self._contexts.items()):
            if session_id == self.active_context_id or runtime_context.closed:
                continue
            if not force and runtime_context.lease_expires_at and runtime_context.lease_expires_at > now:
                preserved.append(session_id)
                continue
            runtime_context.draining = True
            try:
                runtime_context.context.close()
            finally:
                runtime_context.closed = True
                closed.append(session_id)
        return {"success": True, "closed": closed, "preserved": preserved, "active_context_id": self.active_context_id}

    def contexts(self) -> list[Dict[str, Any]]:
        return self._call_runtime(lambda: [runtime_context.to_dict() for runtime_context in self._contexts.values()])

    def close(self):
        if threading.get_ident() != self._worker_id and self._worker and self._worker.is_alive():
            self._call_runtime(self._close)
            self._work_queue.put(None)
            self._worker.join(timeout=5)
            self._worker = None
            self._worker_id = None
            return

        self._close()

    def _close(self):
        for runtime_context in self._contexts.values():
            if runtime_context.closed:
                continue
            try:
                runtime_context.context.close()
            finally:
                runtime_context.closed = True
        self.context_factory.close()

    def _load_package(self, path: str) -> Dict[str, Any]:
        session_path = Path(path).expanduser()
        with open(session_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise GatewayRuntimeError(f"invalid session package: {path}")
        return data

    def _inject_cookies(self, context: Any, cookies: list[Dict[str, Any]]) -> int:
        now = time.time()
        normalized = []
        skipped_expired = 0
        for cookie in cookies:
            if not isinstance(cookie, dict) or "name" not in cookie or "value" not in cookie:
                continue
            expires = cookie.get("expires")
            if expires and _is_expired(expires, now):
                skipped_expired += 1
                continue
            normalized.append(self._loader._normalize_cookie(cookie))
        if normalized:
            context.add_cookies(normalized)
        if skipped_expired:
            logger.info(
                "Skipped %d expired cookies during injection", skipped_expired
            )
        return len(normalized)

    def _inject_storage(self, context: Any, package: Dict[str, Any]) -> list[str]:
        origins = []
        storage = package.get("storage") if isinstance(package.get("storage"), dict) else {}
        local_by_origin = storage.get("local") if isinstance(storage.get("local"), dict) else {}

        target_origins = self._target_origins
        if not target_origins:
            return origins

        for origin, values in local_by_origin.items():
            if not isinstance(origin, str) or not isinstance(values, dict) or not values:
                continue
            if not _is_valid_origin(origin):
                logger.debug("Skipping invalid localStorage origin: %s", origin)
                continue
            if origin not in target_origins:
                logger.debug("Skipping non-target localStorage origin: %s", origin)
                continue
            injected = self._inject_local_storage_origin(context, origin, values)
            if injected:
                origins.append(origin)

        legacy_local_storage = package.get("local_storage")
        if isinstance(legacy_local_storage, dict) and legacy_local_storage:
            origin = self._loader._infer_origin(package)
            if origin and _is_valid_origin(origin):
                if origin in target_origins:
                    injected = self._inject_local_storage_origin(context, origin, legacy_local_storage)
                    if injected:
                        origins.append(origin)
            elif origin:
                logger.debug("Skipping invalid legacy localStorage origin: %s", origin)
        return origins

    def _relevant_domains(self, package: Dict[str, Any]) -> set[str]:
        """Extract the set of cookie/site domains relevant to this session."""
        domains: set[str] = set()
        for cookie in package.get("cookies", []):
            if isinstance(cookie, dict):
                domain = cookie.get("domain", "")
                if isinstance(domain, str) and domain.strip():
                    domains.add(domain.lstrip(".").lower())
        site_name = package.get("site_name", "")
        if isinstance(site_name, str) and site_name and site_name != "unknown":
            domains.add(site_name.lower())
        return domains

    def _inject_local_storage_origin(self, context: Any, origin: str, values: Dict[str, Any]) -> bool:
        if not values:
            return False
        batches = _batch_local_storage(values)
        if hasattr(context, "add_init_script"):
            try:
                for batch in batches:
                    payload = json.dumps({"origin": origin, "data": batch})
                    context.add_init_script(
                        f"""
                        (() => {{
                            const {{ origin, data }} = {payload};
                            if (window.location.origin !== origin) return;
                            for (const [key, value] of Object.entries(data)) {{
                                localStorage.setItem(key, value);
                            }}
                        }})();
                        """
                    )
                return True
            except Exception as exc:
                logger.warning("localStorage init script failed for %s: %s", origin, exc)
                return False
        page = context.new_page()
        try:
            if hasattr(page, "goto"):
                page.goto(origin, wait_until="domcontentloaded", timeout=15000)
            if hasattr(page, "evaluate"):
                for batch in batches:
                    page.evaluate(
                        """
                        (data) => {
                            for (const [key, value] of Object.entries(data)) {
                                localStorage.setItem(key, value);
                            }
                        }
                        """,
                        batch,
                    )
        except Exception as exc:
            logger.warning("localStorage injection failed for %s: %s", origin, exc)
            return False
        finally:
            if hasattr(page, "close"):
                page.close()
        return True


def _is_expired(expires: Any, now: float) -> bool:
    """Check if a cookie expiry value is in the past."""
    try:
        expires_int = int(expires)
    except (TypeError, ValueError):
        return False
    if expires_int <= 0:
        return False
    if expires_int > _MS_THRESHOLD:
        expires_int = expires_int // 1000
    return expires_int < now


def _is_valid_origin(origin: str) -> bool:
    """Check that an origin string has an http(s) scheme and a non-blocked host."""
    try:
        parsed = urlparse(origin)
    except Exception:
        return False
    if parsed.scheme not in _ALLOWED_URL_SCHEMES:
        return False
    if not parsed.hostname:
        return False
    return True


def _target_origins(target_url: Optional[str]) -> set[str]:
    if not isinstance(target_url, str) or not target_url.strip():
        return set()
    try:
        parsed = urlparse(target_url.strip())
    except Exception:
        return set()
    if parsed.scheme not in _ALLOWED_URL_SCHEMES or not parsed.hostname:
        return set()
    origin = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        origin = f"{origin}:{parsed.port}"
    return {origin}


def _validate_window_policy(window_policy: str) -> str:
    if window_policy not in WINDOW_POLICIES:
        raise GatewayRuntimeError(f"unsupported gateway window_policy: {window_policy}")
    return window_policy


def _page_is_closed(page: Any) -> bool:
    is_closed = getattr(page, "is_closed", None)
    if callable(is_closed):
        try:
            return bool(is_closed())
        except Exception:
            return False
    return bool(getattr(page, "closed", False))


def _origin_matches_domains(origin: str, domains: set[str]) -> bool:
    """Check if an origin's hostname is related to any of the given domains."""
    try:
        hostname = urlparse(origin).hostname or ""
    except Exception:
        return False
    hostname = hostname.lower()
    if not hostname:
        return False
    for domain in domains:
        if hostname == domain or hostname.endswith("." + domain):
            return True
    return False


def _batch_local_storage(values: Dict[str, Any], batch_size: int = _MAX_LS_ENTRIES_PER_ORIGIN) -> list[Dict[str, Any]]:
    """Split a localStorage dict into batches to avoid huge evaluate payloads."""
    items = list(values.items())
    if len(items) <= batch_size:
        return [dict(items)]
    batches = []
    for i in range(0, len(items), batch_size):
        batches.append(dict(items[i : i + batch_size]))
    return batches
