"""Gateway runtime binding route decisions to isolated browser contexts."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

from tokenade.core.gateway.session_store import SessionRecord
from tokenade.core.importer.session_loader import SessionLoader


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
    draining: bool = False
    closed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session": self.session.to_dict(),
            "created_at": self.created_at,
            "cookie_count_injected": self.cookies_injected,
            "origins": list(self.local_storage_origins),
            "page_count": self.page_count,
            "draining": self.draining,
            "closed": self.closed,
        }


class BrowserManagerContextFactory:
    """Default factory that creates isolated browser-manager contexts.

    This keeps Phase 4 conservative: each context is isolated because it gets its
    own BrowserManager-backed browser context. Future work can replace this with
    a shared-browser context factory once CDP/CloakBrowser lifecycle is proven.
    """

    def __init__(self, backend: str = "cloakbrowser", headless: bool = True):
        self.backend = backend
        self.headless = headless
        self._managers = []

    def create_context(self, session: SessionRecord):
        from tokenade.core.browser.manager import BrowserFactory

        manager = BrowserFactory.create(
            backend="cloakbrowser" if self.backend in ("cloak", "cloakbrowser") else "playwright",
            browser_type=self.backend,
            headless=self.headless,
        )
        manager.launch()
        self._managers.append(manager)
        return _BrowserManagerGatewayContext(manager)

    def close(self):
        for manager in list(self._managers):
            try:
                manager.close()
            except Exception:
                pass
        self._managers.clear()


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

    def close(self):
        return self.manager.close()


class GatewayRuntime:
    """Prewarms and routes work to isolated per-session contexts."""

    def __init__(self, context_factory: GatewayContextFactory):
        self.context_factory = context_factory
        self._loader = SessionLoader()
        self._contexts: Dict[str, GatewaySessionContext] = {}
        self.active_context_id: Optional[str] = None

    def prewarm(self, sessions: list[SessionRecord]) -> Dict[str, Any]:
        started = time.perf_counter()
        created = []
        for session in sessions:
            if session.id not in self._contexts or self._contexts[session.id].closed:
                self.ensure_context(session)
                created.append(session.id)
        return {
            "success": True,
            "created": created,
            "context_count": len(self._contexts),
            "duration_ms": (time.perf_counter() - started) * 1000,
        }

    def ensure_context(self, session: SessionRecord) -> GatewaySessionContext:
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
        runtime_context = self.ensure_context(session)
        self.active_context_id = session.id
        return runtime_context

    def new_page(self, session: Optional[SessionRecord] = None, url: Optional[str] = None) -> Dict[str, Any]:
        if session is not None:
            runtime_context = self.activate(session)
        elif self.active_context_id:
            runtime_context = self._contexts[self.active_context_id]
        else:
            raise GatewayRuntimeError("no active context")

        page = runtime_context.context.new_page()
        navigation_error = None
        if url and hasattr(page, "goto"):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                navigation_error = str(exc)
        runtime_context.page_count += 1
        result = {"success": True, "context": runtime_context.to_dict()}
        if navigation_error:
            result["navigation_error"] = navigation_error
        return result

    def drain_inactive(self) -> Dict[str, Any]:
        closed = []
        for session_id, runtime_context in list(self._contexts.items()):
            if session_id == self.active_context_id or runtime_context.closed:
                continue
            runtime_context.draining = True
            try:
                runtime_context.context.close()
            finally:
                runtime_context.closed = True
                closed.append(session_id)
        return {"success": True, "closed": closed, "active_context_id": self.active_context_id}

    def contexts(self) -> list[Dict[str, Any]]:
        return [runtime_context.to_dict() for runtime_context in self._contexts.values()]

    def close(self):
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
        normalized = []
        for cookie in cookies:
            if not isinstance(cookie, dict) or "name" not in cookie or "value" not in cookie:
                continue
            normalized.append(self._loader._normalize_cookie(cookie))
        if normalized:
            context.add_cookies(normalized)
        return len(normalized)

    def _inject_storage(self, context: Any, package: Dict[str, Any]) -> list[str]:
        origins = []
        storage = package.get("storage") if isinstance(package.get("storage"), dict) else {}
        local_by_origin = storage.get("local") if isinstance(storage.get("local"), dict) else {}
        for origin, values in local_by_origin.items():
            if isinstance(origin, str) and isinstance(values, dict):
                self._inject_local_storage_origin(context, origin, values)
                origins.append(origin)

        legacy_local_storage = package.get("local_storage")
        if isinstance(legacy_local_storage, dict) and legacy_local_storage:
            origin = self._loader._infer_origin(package)
            if origin:
                self._inject_local_storage_origin(context, origin, legacy_local_storage)
                origins.append(origin)
        return origins

    def _inject_local_storage_origin(self, context: Any, origin: str, values: Dict[str, Any]):
        page = context.new_page()
        if hasattr(page, "goto"):
            page.goto(origin, wait_until="domcontentloaded", timeout=15000)
        if hasattr(page, "evaluate"):
            page.evaluate(
                """
                (data) => {
                    for (const [key, value] of Object.entries(data)) {
                        localStorage.setItem(key, value);
                    }
                }
                """,
                values,
            )
        if hasattr(page, "close"):
            page.close()
