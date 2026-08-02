"""Lightweight HTTP control plane for hidden gateway requests."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from tokenade.core.gateway.session_router import RoutingConfig, RoutingDecision, SessionRouter, SessionRoutingError
from tokenade.core.gateway.session_store import SessionRecord, SessionStore
from tokenade.core.gateway.runtime import BrowserManagerContextFactory, GatewayRuntime, GatewayRuntimeError
from tokenade.core.proxy.provider import ProxyProviderError, ProxyProviderResolver
from tokenade.core.request_config import RequestConfig
from tokenade.core.events.bus import EventBus
from tokenade.core.events.scheduler import Scheduler
from tokenade.core.events.types import EventType


logger = logging.getLogger(__name__)


class GatewayConfigError(ValueError):
    """Raised when a gateway request cannot create a control plane."""


class _RateLimiter:
    """Simple per-IP rate limiter using sliding window."""

    def __init__(self, requests_per_minute: int = 60, burst: int = 10):
        self.requests_per_minute = requests_per_minute
        self.burst = burst
        self._windows: Dict[str, list] = {}
        self._lock = threading.Lock()

    def allow(self, ip: str) -> bool:
        """Check if request is allowed for IP. Returns True if allowed."""
        now = time.time()
        window_start = now - 60  # 1-minute window
        with self._lock:
            if ip not in self._windows:
                self._windows[ip] = []
            # Clean old requests
            self._windows[ip] = [t for t in self._windows[ip] if t > window_start]
            # Check limit
            if len(self._windows[ip]) >= self.requests_per_minute:
                return False
            # Allow and record
            self._windows[ip].append(now)
            return True

    def cleanup(self):
        """Clean up old entries."""
        now = time.time()
        window_start = now - 60
        with self._lock:
            for ip in list(self._windows.keys()):
                self._windows[ip] = [t for t in self._windows[ip] if t > window_start]
                if not self._windows[ip]:
                    del self._windows[ip]


@dataclass(frozen=True)
class GatewayServerConfig:
    """Network settings for the gateway control plane."""

    host: str = "127.0.0.1"
    port: int = 9222
    backend: str = "cdp"

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "GatewayServerConfig":
        raw = data or {}
        if not isinstance(raw, dict):
            raise GatewayConfigError("request.gateway must be an object")

        host = raw.get("host", "127.0.0.1")
        if not isinstance(host, str) or not host.strip():
            raise GatewayConfigError("request.gateway.host must be a string")

        port = raw.get("port", 9222)
        if not isinstance(port, int) or isinstance(port, bool) or port < 0 or port > 65535:
            raise GatewayConfigError("request.gateway.port must be an integer from 0 to 65535")

        backend = raw.get("backend", "cdp")
        if not isinstance(backend, str) or not backend.strip():
            raise GatewayConfigError("request.gateway.backend must be a string")

        return cls(host=host.strip(), port=port, backend=backend.strip())


class GatewayControlPlane:
    """Hidden gateway API backed by sanitized sessions and SessionRouter."""

    def __init__(
        self,
        server_config: GatewayServerConfig,
        routing_config: RoutingConfig,
        sessions: list[SessionRecord],
        plugins: Optional[list[Dict[str, Any]]] = None,
        runtime: Optional[GatewayRuntime] = None,
        upstream_proxies: Optional[list[Dict[str, Any]]] = None,
        state_file: Optional[str] = None,
        webhooks: Optional[Dict[str, str]] = None,
        rate_limit_config: Optional[Dict[str, int]] = None,
    ):
        self.server_config = server_config
        self.routing_config = routing_config
        self.sessions = list(sessions)
        self.plugins = plugins or []
        self.router = SessionRouter(self.sessions, routing_config)
        self.active_session: Optional[SessionRecord] = None
        self.runtime = runtime
        self.upstream_proxies = upstream_proxies or []
        self.state_file = state_file

        # Webhooks
        self.webhooks = webhooks or {}
        self._webhook_secret = self.webhooks.get("secret", "")

        # Rate limiting
        self._rate_limiter = _RateLimiter(
            requests_per_minute=rate_limit_config.get("requests_per_minute", 60) if rate_limit_config else 60,
            burst=rate_limit_config.get("burst", 10) if rate_limit_config else 10,
        ) if rate_limit_config else None

        # Probe config: timeout (seconds) and per-domain rate limit (min interval between probes)
        self._probe_timeout = 8.0
        self._probe_min_interval = 60.0  # seconds between probes to same domain
        self._probe_last_run: Dict[str, float] = {}  # domain -> last probe timestamp

        # Load previous state if state_file exists
        if state_file:
            self._load_state()

        # Auto-rotation + health timers (must live on the instance, not inside webhook send)
        self._auto_rotate_timer: Optional[threading.Timer] = None
        self._auto_rotate_interval = routing_config.switch_interval_seconds
        if self._auto_rotate_interval and self._auto_rotate_interval > 0:
            self._start_auto_rotate_timer()

        self._health_timer: Optional[threading.Timer] = None
        if routing_config.health_check_interval_seconds:
            self._start_health_monitor()

        # Events + scheduler for cron-based tasks
        self.event_bus = EventBus()
        self.scheduler = Scheduler(self.event_bus, check_interval=10)
        self._scheduler_started = False

    def _fire_webhook(self, event: str, data: Dict[str, Any]):
        """Fire a webhook notification (async, fire-and-forget)."""
        if not self.webhooks.get(f"on_{event}"):
            return
        url = self.webhooks[f"on_{event}"]
        payload = {
            "event": event,
            "timestamp": time.time(),
            "gateway": {
                "host": self.server_config.host,
                "port": self.server_config.port,
            },
            "data": data,
        }
        body = json.dumps(payload).encode("utf-8")

        # Compute HMAC signature
        headers = {"Content-Type": "application/json"}
        if self._webhook_secret:
            import hmac
            import hashlib
            signature = hmac.new(
                self._webhook_secret.encode("utf-8"),
                body,
                hashlib.sha256,
            ).hexdigest()
            headers["X-Tokenade-Signature"] = f"sha256={signature}"

        # Fire-and-forget in background thread
        def _send():
            try:
                import urllib.request
                req = urllib.request.Request(url, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status >= 400:
                        logger.warning("Webhook %s returned status %d", url, resp.status)
            except Exception as exc:
                logger.debug("Webhook fire failed for %s: %s", event, exc)

        thread = threading.Thread(target=_send, daemon=True)
        thread.start()

    def _start_auto_rotate_timer(self):
        """Start background timer for auto-rotation."""
        if self._auto_rotate_interval and self._auto_rotate_interval > 0:
            self._auto_rotate_timer = threading.Timer(
                self._auto_rotate_interval,
                self._auto_rotate_callback
            )
            self._auto_rotate_timer.daemon = True
            self._auto_rotate_timer.start()

    def _auto_rotate_callback(self):
        """Background timer callback for auto-rotation."""
        try:
            self._auto_rotate_next()
        except Exception:
            logger.debug("Auto-rotation failed", exc_info=True)
        finally:
            self._start_auto_rotate_timer()

    def _auto_rotate_next(self):
        """Rotate the active session record without touching browser runtime APIs."""
        decision = self.router.select()
        self.active_session = decision.session
        self._save_state()
        self._fire_webhook("rotate", {
            "session": decision.session.to_dict(),
            "strategy": decision.strategy,
            "reason": decision.reason,
        })
        self.event_bus.emit(EventType.PROXY_ROTATED, {
            "session": decision.session.to_dict(),
            "strategy": decision.strategy,
            "reason": decision.reason,
        }, source="gateway")

    def _cancel_auto_rotate_timer(self):
        """Cancel the auto-rotation timer."""
        if self._auto_rotate_timer:
            self._auto_rotate_timer.cancel()
            self._auto_rotate_timer = None

    def reset_auto_rotate_timer(self):
        """Reset the auto-rotation timer (call on manual rotation)."""
        self._cancel_auto_rotate_timer()
        self._start_auto_rotate_timer()

    # Health monitoring
    def _start_health_monitor(self):
        """Start background health monitoring."""
        interval = self.routing_config.health_check_interval_seconds
        if interval and interval > 0:
            self._health_timer = threading.Timer(interval, self._health_check_callback)
            self._health_timer.daemon = True
            self._health_timer.start()

    def _health_check_callback(self):
        """Background timer callback for health checks."""
        try:
            self._check_all_sessions_health()
        except Exception:
            pass  # Silently ignore health check errors
        finally:
            # Schedule next health check
            self._start_health_monitor()

    def _check_all_sessions_health(self):
        """Check health of all sessions and mark unhealthy ones."""
        from tokenade.core.refresh.health_checker import SessionHealthChecker
        checker = SessionHealthChecker()

        for session in self.sessions:
            try:
                health = checker.check_session(session.path)
                was_healthy = getattr(session, '_healthy', True)
                if not health.healthy:
                    failures = getattr(session, '_health_failures', 0) + 1
                    object.__setattr__(session, '_health_failures', failures)
                    if failures >= self.routing_config.unhealthy_threshold:
                        object.__setattr__(session, '_healthy', False)
                        if was_healthy:
                            self.event_bus.emit(EventType.HEALTH_DEGRADED, {
                                "session_id": session.id,
                                "site_name": session.site_name,
                                "health_failures": failures,
                                "health_score": health.health_score,
                            }, source="gateway")
                else:
                    object.__setattr__(session, '_health_failures', 0)
                    object.__setattr__(session, '_healthy', True)
                    if not was_healthy:
                        self.event_bus.emit(EventType.HEALTH_RECOVERED, {
                            "session_id": session.id,
                            "site_name": session.site_name,
                        }, source="gateway")
                self._probe_session_health(session, was_healthy)
            except Exception:
                failures = getattr(session, '_health_failures', 0) + 1
                object.__setattr__(session, '_health_failures', failures)
                if failures >= self.routing_config.unhealthy_threshold:
                    object.__setattr__(session, '_healthy', False)

    def _probe_session_health(self, session, was_healthy: bool):
        """Run a server-side probe to detect cookie invalidation beyond expiry.

        Emits HEALTH_DEGRADED when the probe returns False (server rejected cookies)
        or HEALTH_RECOVERED when it returns True after being degraded.
        Rate-limited per domain to avoid overwhelming target sites.
        """
        from tokenade.core.refresh.health_checker import SessionProbe, _resolve_probe_url

        try:
            import json as _json
            with open(session.path, encoding="utf-8") as f:
                session_data = _json.load(f)
            probe_url = _resolve_probe_url(session_data)
            if not probe_url:
                return

            from urllib.parse import urlparse
            domain = urlparse(probe_url).hostname or ""
            if not domain:
                return

            # Per-domain rate limiting
            now = time.time()
            last = self._probe_last_run.get(domain, 0)
            if now - last < self._probe_min_interval:
                logger.debug("Probe rate-limited for domain %s (last %.1fs ago)", domain, now - last)
                return
            self._probe_last_run[domain] = now
        except Exception:
            return

        try:
            result = SessionProbe.probe(session.path, timeout=self._probe_timeout)
        except Exception as exc:
            logger.debug("Session probe failed for %s: %s", session.id, exc)
            return

        if result is None:
            return

        if result is False:
            failures = getattr(session, '_health_failures', 0) + 1
            object.__setattr__(session, '_health_failures', failures)
            if failures >= self.routing_config.unhealthy_threshold:
                object.__setattr__(session, '_healthy', False)
                if was_healthy:
                    self.event_bus.emit(EventType.HEALTH_DEGRADED, {
                        "session_id": session.id,
                        "site_name": session.site_name,
                        "health_failures": failures,
                        "probe": "server_invalidated",
                    }, source="gateway")
        elif result is True:
            if not was_healthy:
                object.__setattr__(session, '_health_failures', 0)
                object.__setattr__(session, '_healthy', True)
                self.event_bus.emit(EventType.HEALTH_RECOVERED, {
                    "session_id": session.id,
                    "site_name": session.site_name,
                    "probe": "server_valid",
                }, source="gateway")

    def _save_state(self):
        """Save gateway state to disk (atomic write)."""
        if not self.state_file:
            return
        try:
            state = {
                "active_session": self.active_session.path if self.active_session else None,
                "active_session_id": self.active_session.id if self.active_session else None,
                "runtime_enabled": self.runtime is not None,
                "context_count": len(self.runtime.contexts()) if self.runtime else 0,
                "saved_at": time.time(),
            }
            state_dir = Path(self.state_file).parent
            state_dir.mkdir(parents=True, exist_ok=True)
            temp_file = self.state_file + ".tmp"
            with open(temp_file, "w") as f:
                json.dump(state, f, indent=2)
            Path(temp_file).replace(self.state_file)
        except Exception as exc:
            logger.warning("Failed to save gateway state: %s", exc)

    def _load_state(self):
        """Load gateway state from disk."""
        if not self.state_file or not Path(self.state_file).exists():
            return
        try:
            with open(self.state_file) as f:
                state = json.load(f)
            active_path = state.get("active_session") or state.get("active_session_id")
            if active_path:
                for session in self.sessions:
                    if session.path == active_path or session.id == active_path:
                        self.active_session = session
                        logger.info("Restored active session: %s", session.site_name)
                        break
        except Exception as exc:
            logger.warning("Failed to load gateway state: %s", exc)

    def status(self) -> Dict[str, Any]:
        return {
            "success": True,
            "operation": "gateway",
            "active_session": self.active_session.to_dict() if self.active_session else None,
            "session_count": len(self.sessions),
            "gateway": {
                "host": self.server_config.host,
                "port": self.server_config.port,
                "backend": self.server_config.backend,
            },
            "routing": {
                "object": self.routing_config.object,
                "strategy": self.routing_config.strategy,
                "switch_interval_seconds": self.routing_config.switch_interval_seconds,
                "sticky_by": self.routing_config.sticky_by,
                "failover": self.routing_config.failover,
                "drain_existing_tabs": self.routing_config.drain_existing_tabs,
                "default_scope": self.routing_config.default_scope,
            },
            "plugins": self.plugins,
            "runtime": {
                "enabled": self.runtime is not None,
                "active_context_id": self.runtime.active_context_id if self.runtime else None,
                "context_count": len(self.runtime.contexts()) if self.runtime else 0,
            },
            "upstream_proxies": self.upstream_proxies,
            "scheduler": {
                "running": self._scheduler_started,
                "task_count": len(self.scheduler.get_tasks()),
            },
        }

    def session_list(self) -> Dict[str, Any]:
        return {
            "success": True,
            "operation": "gateway",
            "sessions": [session.to_dict() for session in self.sessions],
        }

    def route_next(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        decision = self.router.select(context=context)
        self.active_session = decision.session
        runtime_context = self._apply_route_scope(decision.session, context)
        # Reset auto-rotate timer on manual rotation
        self.reset_auto_rotate_timer()
        # Save state after rotation
        self._save_state()
        # Fire webhook
        self._fire_webhook("rotate", {
            "session": decision.session.to_dict(),
            "strategy": decision.strategy,
            "reason": decision.reason,
        })
        # Emit event
        self.event_bus.emit(EventType.PROXY_ROTATED, {
            "session": decision.session.to_dict(),
            "strategy": decision.strategy,
            "reason": decision.reason,
        }, source="gateway")
        return self._decision_response(decision, runtime_context)

    def route_select(self, selector: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(selector, dict):
            raise GatewayConfigError("selector must be an object")

        selected = self._find_session(selector)
        if selected is None:
            raise GatewayConfigError("no session matched selector")

        self.active_session = selected
        runtime_context = self._apply_route_scope(selected, selector)
        decision = RoutingDecision(
            session=selected,
            strategy=self.routing_config.strategy,
            reason="manual-select",
            selected_at=time.time(),
        )
        # Reset auto-rotate timer on manual selection
        self.reset_auto_rotate_timer()
        # Save state after selection
        self._save_state()
        # Fire webhook
        self._fire_webhook("select", {
            "session": decision.session.to_dict(),
            "strategy": decision.strategy,
            "reason": decision.reason,
        })
        # Emit event
        self.event_bus.emit(EventType.SESSION_VALIDATED, {
            "session": decision.session.to_dict(),
            "strategy": decision.strategy,
            "reason": decision.reason,
        }, source="gateway")
        return self._decision_response(decision, runtime_context)

    def _apply_route_scope(self, session: SessionRecord, payload: Dict[str, Any]):
        if not self.runtime:
            return None
        scope = payload.get("scope", self.routing_config.default_scope)
        if scope == "future-only":
            return None
        if scope == "activate-context":
            return self.runtime.activate(session)
        if scope == "open-target":
            url = payload.get("url") if isinstance(payload.get("url"), str) else None
            window_policy = payload.get("window_policy") if isinstance(payload.get("window_policy"), str) else None
            return self.runtime.new_page(session, url=url, window_policy=window_policy)
        raise GatewayConfigError("scope must be future-only, activate-context, or open-target")

    def context_list(self) -> Dict[str, Any]:
        if not self.runtime:
            return {"success": True, "operation": "gateway", "runtime_enabled": False, "contexts": []}
        return {
            "success": True,
            "operation": "gateway",
            "runtime_enabled": True,
            "contexts": self.runtime.contexts(),
        }

    def contexts_drain(self, force: bool = False) -> Dict[str, Any]:
        if not self.runtime:
            raise GatewayConfigError("gateway runtime is not enabled")
        result = self.runtime.drain_inactive(force=force)
        return {"success": True, "operation": "gateway", "runtime": result}

    def contexts_lease(self, selector: Dict[str, Any]) -> Dict[str, Any]:
        if not self.runtime:
            raise GatewayConfigError("gateway runtime is not enabled")
        session = self._find_session(selector) if selector else None
        if session is None:
            session = self.active_session
        if session is None:
            raise GatewayConfigError("no session selected for lease")
        ttl = selector.get("ttl_seconds", 900)
        if not isinstance(ttl, (int, float)) or isinstance(ttl, bool):
            raise GatewayConfigError("ttl_seconds must be a number")
        leased_by = selector.get("leased_by") if isinstance(selector.get("leased_by"), str) else None
        result = self.runtime.lease(session, ttl_seconds=float(ttl), leased_by=leased_by)
        return {"success": True, "operation": "gateway", "runtime": result}

    def contexts_release(self, selector: Dict[str, Any]) -> Dict[str, Any]:
        if not self.runtime:
            raise GatewayConfigError("gateway runtime is not enabled")
        context_id = selector.get("context_id") if isinstance(selector.get("context_id"), str) else None
        lease_id = selector.get("lease_id") if isinstance(selector.get("lease_id"), str) else None
        if not context_id and not lease_id:
            session = self._find_session(selector)
            if session is None:
                session = self.active_session
            context_id = session.id if session is not None else None
        if not context_id and not lease_id:
            raise GatewayConfigError("context_id, lease_id, or session selector is required")
        result = self.runtime.release(context_id=context_id, lease_id=lease_id)
        return {"success": True, "operation": "gateway", "runtime": result}

    def tabs_new(self, selector: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.runtime:
            raise GatewayConfigError("gateway runtime is not enabled")
        selector = selector or {}
        has_session_selector = any(key in selector for key in ("id", "session_id", "path", "site", "site_name"))
        session = self._find_session(selector) if has_session_selector else self.active_session
        if session is None:
            raise GatewayConfigError("no active session selected")
        url = selector.get("url") if isinstance(selector.get("url"), str) else None
        window_policy = selector.get("window_policy") if isinstance(selector.get("window_policy"), str) else None
        return {"success": True, "operation": "gateway", "runtime": self.runtime.new_page(session, url=url, window_policy=window_policy)}

    def make_handler(self):
        control_plane = self

        class GatewayRequestHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if not control_plane._rate_limiter:
                    self._handle_get()
                    return
                client_ip = self.client_address[0]
                if not control_plane._rate_limiter.allow(client_ip):
                    retry_after = 60
                    self._send_json(429, {"success": False, "error": "rate limit exceeded"},
                                    {"Retry-After": str(retry_after)})
                    return
                self._handle_get()

            def _handle_get(self):
                if self.path == "/status":
                    self._send_json(200, control_plane.status())
                elif self.path == "/sessions":
                    self._send_json(200, control_plane.session_list())
                elif self.path == "/contexts":
                    self._send_json(200, control_plane.context_list())
                else:
                    self._send_json(404, {"success": False, "error": "not found"})

            def do_POST(self):
                if control_plane._rate_limiter:
                    client_ip = self.client_address[0]
                    if not control_plane._rate_limiter.allow(client_ip):
                        retry_after = 60
                        self._send_json(429, {"success": False, "error": "rate limit exceeded"},
                                        {"Retry-After": str(retry_after)})
                        return
                try:
                    payload = self._read_json()
                    if self.path == "/route/next":
                        self._send_json(200, control_plane.route_next(payload))
                    elif self.path == "/route/select":
                        self._send_json(200, control_plane.route_select(payload))
                    elif self.path == "/contexts/drain":
                        force = bool(payload.get("force")) if isinstance(payload, dict) else False
                        self._send_json(200, control_plane.contexts_drain(force=force))
                    elif self.path == "/contexts/lease":
                        self._send_json(200, control_plane.contexts_lease(payload))
                    elif self.path == "/contexts/release":
                        self._send_json(200, control_plane.contexts_release(payload))
                    elif self.path == "/tabs/new":
                        self._send_json(200, control_plane.tabs_new(payload))
                    else:
                        self._send_json(404, {"success": False, "error": "not found"})
                except (GatewayConfigError, GatewayRuntimeError, SessionRoutingError, json.JSONDecodeError) as exc:
                    self._send_json(400, {"success": False, "error": str(exc)})

            def log_message(self, format, *args):
                return

            def _read_json(self):
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length == 0:
                    return {}
                body = self.rfile.read(length).decode("utf-8")
                return json.loads(body)

            def _send_json(self, status_code: int, payload: Dict[str, Any], extra_headers: Optional[Dict[str, str]] = None):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                if extra_headers:
                    for key, value in extra_headers.items():
                        self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)

        return GatewayRequestHandler

    def serve_forever(self):
        httpd = HTTPServer((self.server_config.host, self.server_config.port), self.make_handler())
        self._server = httpd
        try:
            httpd.serve_forever()
        finally:
            self.close()
            httpd.server_close()
            self._server = None

    def shutdown(self):
        httpd = getattr(self, "_server", None)
        if httpd is not None:
            httpd.shutdown()

    def _find_session(self, selector: Dict[str, Any]) -> Optional[SessionRecord]:
        session_id = selector.get("id") or selector.get("session_id")
        path = selector.get("path")
        site_name = selector.get("site") or selector.get("site_name")

        for session in self.sessions:
            if session_id is not None and session.id == str(session_id):
                return session
            if path is not None and session.path == str(path):
                return session
            if site_name is not None and session.site_name == str(site_name):
                return session
        return None

    def _decision_response(self, decision: RoutingDecision, runtime_context=None) -> Dict[str, Any]:
        response = {
            "success": True,
            "operation": "gateway",
            "decision": decision.to_dict(),
            "runtime_context": None,
        }
        if runtime_context is not None:
            response["runtime_context"] = runtime_context if isinstance(runtime_context, dict) else runtime_context.to_dict()
        return response

    def close(self):
        self._save_state()
        self._cancel_auto_rotate_timer()
        if self._health_timer:
            self._health_timer.cancel()
            self._health_timer = None
        if self._scheduler_started:
            self.scheduler.stop()
            self._scheduler_started = False
        if self.runtime:
            self.runtime.close()

    def register_scheduler_tasks(self):
        """Register cron-based tasks from plugin config and start the scheduler."""
        self._plugin_configs = {}
        for plugin in self.plugins:
            roles = plugin.get("roles", {})
            refresher_config = roles.get("session_refresher", {})
            if not refresher_config.get("enabled"):
                continue
            plugin_name = plugin.get("name", "")
            plugin_config = plugin.get("config", {})
            self._plugin_configs[plugin_name] = plugin_config
            interval = refresher_config.get("refresh_interval_seconds", 3600)
            methods = refresher_config.get("methods", [])
            for session in self.sessions:
                task_name = f"refresh-{session.id}"
                self.scheduler.add_interval_task(
                    name=task_name,
                    event_type=EventType.REFRESH_STARTED,
                    data={
                        "session_id": session.id,
                        "session_path": session.path,
                        "methods": methods,
                        "plugin_name": plugin_name,
                    },
                    interval_seconds=float(interval),
                    source="gateway",
                )
                logger.info("Registered refresh task: %s (every %ss)", task_name, interval)
        if self.scheduler.get_tasks() and not self._scheduler_started:
            self.event_bus.on(EventType.REFRESH_STARTED, self._on_refresh_task_fired)
            self.scheduler.start()
            self._scheduler_started = True

    def _on_refresh_task_fired(self, event):
        """Event handler that actually executes the refresh plugin."""
        data = event.data
        session_path = data.get("session_path")
        plugin_name = data.get("plugin_name", "")
        if not session_path or not plugin_name:
            logger.warning("Refresh event missing session_path or plugin_name")
            return

        try:
            from tokenade.core.integration.plugin_loader import get_or_create_shared_loader
            loader = get_or_create_shared_loader()
            refresher = loader.get_refresher(plugin_name)
            if refresher is None:
                logger.warning("Plugin '%s' not loaded or not a refresher", plugin_name)
                return

            with open(session_path, encoding="utf-8") as f:
                session_data = json.load(f)

            if not refresher.can_refresh(session_data):
                logger.info("Plugin '%s' cannot refresh session %s", plugin_name, session_path)
                return

            credentials = self._plugin_configs.get(plugin_name, {})
            result = refresher.refresh(session_data, credentials)

            if result.success:
                updated = result.data.get("session", session_data)
                with open(session_path, "w", encoding="utf-8") as f:
                    json.dump(updated, f, indent=2, ensure_ascii=False)
                logger.info("Session refreshed: %s (plugin=%s)", session_path, plugin_name)
                self.event_bus.emit(EventType.SESSION_REFRESHED, {
                    "session_path": session_path,
                    "plugin_name": plugin_name,
                }, source="gateway")
            else:
                logger.warning("Refresh failed for %s: %s", session_path, result.error)
                self.event_bus.emit(EventType.REFRESH_FAILED, {
                    "session_path": session_path,
                    "plugin_name": plugin_name,
                    "error": result.error,
                }, source="gateway")
        except Exception as exc:
            logger.error("Refresh handler error for %s: %s", session_path, exc)
            self.event_bus.emit(EventType.REFRESH_FAILED, {
                "session_path": session_path,
                "plugin_name": plugin_name,
                "error": str(exc),
            }, source="gateway")


def create_gateway_control_plane(request: RequestConfig) -> GatewayControlPlane:
    """Create a gateway control plane from a validated request config."""
    if request.operation != "gateway":
        raise GatewayConfigError("request.operation must be 'gateway' for tokenade gateway")

    sessions_config = request.raw.get("sessions", {})
    if not isinstance(sessions_config, dict):
        raise GatewayConfigError("request.sessions must be an object")
    sessions_dir = sessions_config.get("dir")
    if not isinstance(sessions_dir, str) or not sessions_dir.strip():
        raise GatewayConfigError("request.sessions.dir is required")
    pattern = sessions_config.get("pattern", "*.tokenade")
    if not isinstance(pattern, str) or not pattern.strip():
        raise GatewayConfigError("request.sessions.pattern must be a string")

    try:
        store = SessionStore()
        sessions = store.load_directory(sessions_dir, pattern.strip())
        server_config = GatewayServerConfig.from_dict(request.raw.get("gateway"))
        routing_config = RoutingConfig.from_dict(request.raw.get("routing"))
    except (FileNotFoundError, SessionRoutingError) as exc:
        raise GatewayConfigError(str(exc)) from exc

    if not sessions:
        raise GatewayConfigError("request.sessions did not load any routable sessions")
    plugins = [
        {
            "name": plugin.name,
            "required": plugin.required,
            "roles": dict(plugin.roles),
            "config": dict(plugin.config),
        }
        for plugin in request.plugins
    ]
    runtime = _create_runtime(request.raw.get("gateway"))
    upstream_proxies = _resolve_proxy_providers(request, sessions)
    gateway_raw = request.raw.get("gateway", {})
    state_file = gateway_raw.get("state_file")
    webhooks = gateway_raw.get("webhooks", {})
    rate_limit_config = gateway_raw.get("rate_limit", {})
    health_config = gateway_raw.get("health", {})
    plane = GatewayControlPlane(
        server_config,
        routing_config,
        sessions,
        plugins,
        runtime=runtime,
        upstream_proxies=upstream_proxies,
        state_file=state_file,
        webhooks=webhooks,
        rate_limit_config=rate_limit_config,
    )
    if isinstance(health_config, dict):
        if isinstance(health_config.get("probe_timeout_seconds"), (int, float)):
            plane._probe_timeout = float(health_config["probe_timeout_seconds"])
        if isinstance(health_config.get("probe_min_interval_seconds"), (int, float)):
            plane._probe_min_interval = float(health_config["probe_min_interval_seconds"])
    plane.register_scheduler_tasks()
    return plane


def _create_runtime(gateway_config: Any) -> Optional[GatewayRuntime]:
    raw = gateway_config or {}
    if not isinstance(raw, dict):
        return None
    runtime_config = raw.get("runtime", {})
    if not isinstance(runtime_config, dict):
        raise GatewayConfigError("request.gateway.runtime must be an object")
    if runtime_config.get("enabled") is not True:
        return None

    backend = runtime_config.get("backend", raw.get("backend", "cloakbrowser"))
    if not isinstance(backend, str) or not backend.strip():
        raise GatewayConfigError("request.gateway.runtime.backend must be a string")
    headless = runtime_config.get("headless", True)
    if not isinstance(headless, bool):
        raise GatewayConfigError("request.gateway.runtime.headless must be a boolean")
    target_url = runtime_config.get("url") or runtime_config.get("start_url") or runtime_config.get("target_url")
    if target_url is not None and not isinstance(target_url, str):
        raise GatewayConfigError("request.gateway.runtime.url must be a string")
    window_policy = runtime_config.get("window_policy", "reuse-active-window")
    if not isinstance(window_policy, str):
        raise GatewayConfigError("request.gateway.runtime.window_policy must be a string")
    return GatewayRuntime(
        BrowserManagerContextFactory(backend=backend.strip(), headless=headless),
        target_url=target_url,
        window_policy=window_policy,
    )


def _resolve_proxy_providers(request: RequestConfig, sessions: list[SessionRecord]) -> list[Dict[str, Any]]:
    provider_plugins = request.plugins_for_role("proxy_provider")
    if not provider_plugins:
        return []

    resolver = ProxyProviderResolver()
    session_metadata = {
        "session_count": len(sessions),
        "sites": sorted({session.site_name for session in sessions}),
    }
    source_network = _source_network_from_sessions(sessions)
    resolved = []
    for plugin in provider_plugins:
        try:
            proxy = resolver.resolve(plugin, session_metadata=session_metadata, source_network=source_network)
        except ProxyProviderError as exc:
            if plugin.required:
                raise GatewayConfigError(str(exc)) from exc
            resolved.append({
                "plugin_name": plugin.name,
                "skipped": True,
                "reason": str(exc),
            })
            continue
        resolved.append({"plugin_name": plugin.name, "proxy": proxy.to_dict(show_secrets=False)})
    return resolved


def _source_network_from_sessions(sessions: list[SessionRecord]) -> Dict[str, Any]:
    for session in sessions:
        source_network = session.metadata.get("source_network")
        if isinstance(source_network, dict):
            return dict(source_network)
    return {}
