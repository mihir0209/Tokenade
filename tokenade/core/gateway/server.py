"""Lightweight HTTP control plane for hidden gateway requests."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

from tokenade.core.gateway.session_router import RoutingConfig, RoutingDecision, SessionRouter, SessionRoutingError
from tokenade.core.gateway.session_store import SessionRecord, SessionStore
from tokenade.core.request_config import RequestConfig


class GatewayConfigError(ValueError):
    """Raised when a gateway request cannot create a control plane."""


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
    ):
        self.server_config = server_config
        self.routing_config = routing_config
        self.sessions = list(sessions)
        self.plugins = plugins or []
        self.router = SessionRouter(self.sessions, routing_config)
        self.active_session: Optional[SessionRecord] = None

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
            },
            "plugins": self.plugins,
        }

    def session_list(self) -> Dict[str, Any]:
        return {
            "success": True,
            "operation": "gateway",
            "sessions": [session.to_dict() for session in self.sessions],
        }

    def route_next(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        decision = self.router.select(context=context)
        self.active_session = decision.session
        return self._decision_response(decision)

    def route_select(self, selector: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(selector, dict):
            raise GatewayConfigError("selector must be an object")

        selected = self._find_session(selector)
        if selected is None:
            raise GatewayConfigError("no session matched selector")

        self.active_session = selected
        decision = RoutingDecision(
            session=selected,
            strategy=self.routing_config.strategy,
            reason="manual-select",
            selected_at=time.time(),
        )
        return self._decision_response(decision)

    def make_handler(self):
        control_plane = self

        class GatewayRequestHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/status":
                    self._send_json(200, control_plane.status())
                elif self.path == "/sessions":
                    self._send_json(200, control_plane.session_list())
                else:
                    self._send_json(404, {"success": False, "error": "not found"})

            def do_POST(self):
                try:
                    payload = self._read_json()
                    if self.path == "/route/next":
                        self._send_json(200, control_plane.route_next(payload))
                    elif self.path == "/route/select":
                        self._send_json(200, control_plane.route_select(payload))
                    else:
                        self._send_json(404, {"success": False, "error": "not found"})
                except (GatewayConfigError, SessionRoutingError, json.JSONDecodeError) as exc:
                    self._send_json(400, {"success": False, "error": str(exc)})

            def log_message(self, format, *args):
                return

            def _read_json(self):
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length == 0:
                    return {}
                body = self.rfile.read(length).decode("utf-8")
                return json.loads(body)

            def _send_json(self, status_code: int, payload: Dict[str, Any]):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return GatewayRequestHandler

    def serve_forever(self):
        httpd = ThreadingHTTPServer((self.server_config.host, self.server_config.port), self.make_handler())
        try:
            httpd.serve_forever()
        finally:
            httpd.server_close()

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

    def _decision_response(self, decision: RoutingDecision) -> Dict[str, Any]:
        return {
            "success": True,
            "operation": "gateway",
            "decision": decision.to_dict(),
        }


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
        }
        for plugin in request.plugins
    ]
    return GatewayControlPlane(server_config, routing_config, sessions, plugins)
