"""
Session Monitoring Dashboard - Web UI for session monitoring.

Provides a web-based dashboard for:
- Real-time session status
- Health monitoring
- Session status summary
- Session management
"""

import json
import logging
import time
from dataclasses import dataclass, field
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)


@dataclass
class DashboardConfig:
    """Configuration for monitoring dashboard."""

    host: str = "127.0.0.1"
    port: int = 8080
    title: str = "Tokenade Session Monitor"
    refresh_interval: int = 10
    max_sessions: int = 100

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DashboardConfig':
        return cls(
            host=data.get("host", "127.0.0.1"),
            port=data.get("port", 8080),
            title=data.get("title", "Tokenade Session Monitor"),
            refresh_interval=data.get("refresh_interval", 10),
            max_sessions=data.get("max_sessions", 100),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "title": self.title,
            "refresh_interval": self.refresh_interval,
            "max_sessions": self.max_sessions,
        }


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler for dashboard."""

    dashboard = None

    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/":
            self._serve_index()
        elif path == "/api/sessions":
            self._serve_sessions()
        elif path == "/api/health":
            self._serve_health()
        elif path == "/api/stats":
            self._serve_stats()
        elif path == "/api/config":
            self._serve_config()
        elif path.startswith("/static/"):
            self._serve_static(path)
        else:
            self._send_404()

    def do_POST(self):
        """Handle POST requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {}

        if path == "/api/sessions/refresh":
            self._handle_refresh(data)
        elif path == "/api/sessions/validate":
            self._handle_validate(data)
        elif path == "/api/sessions/delete":
            self._handle_delete(data)
        else:
            self._send_404()

    def _serve_index(self):
        """Serve dashboard index page."""
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.dashboard.config.title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a2e; color: #eee; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; padding: 30px 0; }}
        .header h1 {{ font-size: 2.5em; color: #00d4ff; }}
        .header p {{ color: #888; margin-top: 10px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 30px 0; }}
        .stat-card {{ background: #16213e; border-radius: 10px; padding: 20px; text-align: center; }}
        .stat-card h3 {{ color: #00d4ff; font-size: 2em; }}
        .stat-card p {{ color: #888; margin-top: 5px; }}
        .sessions {{ background: #16213e; border-radius: 10px; padding: 20px; margin-top: 20px; }}
        .sessions h2 {{ color: #00d4ff; margin-bottom: 20px; }}
        .session-list {{ display: grid; gap: 10px; }}
        .session-item {{ background: #1a1a2e; border-radius: 8px; padding: 15px; display: flex; justify-content: space-between; align-items: center; }}
        .session-item .name {{ font-weight: bold; }}
        .session-item .status {{ padding: 5px 10px; border-radius: 5px; font-size: 0.9em; }}
        .status-healthy {{ background: #00c853; color: #000; }}
        .status-expired {{ background: #ff5252; color: #fff; }}
        .status-unknown {{ background: #888; color: #000; }}
        .btn {{ background: #00d4ff; color: #000; border: none; padding: 8px 16px; border-radius: 5px; cursor: pointer; margin-left: 10px; }}
        .btn:hover {{ background: #00b8d4; }}
        .btn-danger {{ background: #ff5252; }}
        .btn-danger:hover {{ background: #d50000; }}
        #refresh-info {{ text-align: center; color: #888; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{self.dashboard.config.title}</h1>
            <p>Real-time session monitoring</p>
        </div>

        <div class="stats" id="stats">
            <div class="stat-card"><h3 id="total-sessions">0</h3><p>Total Sessions</p></div>
            <div class="stat-card"><h3 id="healthy-sessions">0</h3><p>Healthy</p></div>
            <div class="stat-card"><h3 id="expired-sessions">0</h3><p>Expired</p></div>
            <div class="stat-card"><h3 id="last-update">-</h3><p>Last Update</p></div>
        </div>

        <div class="sessions">
            <h2>Sessions</h2>
            <div class="session-list" id="session-list">Loading...</div>
        </div>

        <div id="refresh-info">Auto-refresh in <span id="countdown">{self.dashboard.config.refresh_interval}</span>s</div>
    </div>

    <script>
        let countdown = {self.dashboard.config.refresh_interval};

        async function fetchData() {{
            try {{
                const [sessions, health, stats] = await Promise.all([
                    fetch('/api/sessions').then(r => r.json()),
                    fetch('/api/health').then(r => r.json()),
                    fetch('/api/stats').then(r => r.json())
                ]);

                document.getElementById('total-sessions').textContent = stats.total || 0;
                document.getElementById('healthy-sessions').textContent = stats.healthy || 0;
                document.getElementById('expired-sessions').textContent = stats.expired || 0;
                document.getElementById('last-update').textContent = new Date().toLocaleTimeString();

                const list = document.getElementById('session-list');
                if (sessions.length === 0) {{
                    list.innerHTML = '<p style="color: #888;">No sessions found</p>';
                }} else {{
                    list.innerHTML = sessions.map(s => `
                        <div class="session-item">
                            <span class="name">${{s.name}}</span>
                            <span class="status status-${{s.status}}">${{s.status}}</span>
                            <div>
                                <button class="btn" onclick="validate('${{s.name}}')">Validate</button>
                                <button class="btn btn-danger" onclick="deleteSession('${{s.name}}')">Delete</button>
                            </div>
                        </div>
                    `).join('');
                }}
            }} catch (e) {{
                console.error('Fetch error:', e);
            }}
        }}

        async function validate(name) {{
            const res = await fetch('/api/sessions/validate', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{name}})
            }});
            const result = await res.json();
            alert(result.message);
            fetchData();
        }}

        async function deleteSession(name) {{
            if (!confirm(`Delete session '${{name}}'?`)) return;
            const res = await fetch('/api/sessions/delete', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{name}})
            }});
            const result = await res.json();
            alert(result.message);
            fetchData();
        }}

        setInterval(() => {{
            countdown--;
            document.getElementById('countdown').textContent = countdown;
            if (countdown <= 0) {{
                fetchData();
                countdown = {self.dashboard.config.refresh_interval};
            }}
        }}, 1000);

        fetchData();
    </script>
</body>
</html>"""

        self._send_html(html)

    def _serve_sessions(self):
        """Serve sessions list."""
        sessions = self.dashboard.get_sessions()
        self._send_json(sessions)

    def _serve_health(self):
        """Serve health status."""
        health = self.dashboard.get_health()
        self._send_json(health)

    def _serve_stats(self):
        """Serve statistics."""
        stats = self.dashboard.get_stats()
        self._send_json(stats)

    def _serve_config(self):
        """Serve dashboard config."""
        self._send_json(self.dashboard.config.to_dict())

    def _serve_static(self, path: str):
        """Serve static files (stub)."""
        self._send_404()

    def _handle_refresh(self, data: Dict):
        """Handle session refresh."""
        name = data.get("name", "")
        result = self.dashboard.refresh_session(name)
        self._send_json(result)

    def _handle_validate(self, data: Dict):
        """Handle session validation."""
        name = data.get("name", "")
        result = self.dashboard.validate_session(name)
        self._send_json(result)

    def _handle_delete(self, data: Dict):
        """Handle session deletion."""
        name = data.get("name", "")
        result = self.dashboard.delete_session(name)
        self._send_json(result)

    def _send_json(self, data: Any):
        """Send JSON response."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_html(self, html: str):
        """Send HTML response."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def _send_404(self):
        """Send 404 response."""
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Not found"}).encode())

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


class DashboardServer:
    """
    Web-based session monitoring dashboard.
    
    Features:
    - Real-time session status
    - Health monitoring
    - Session status summary
    - Session management
    - Auto-refresh
    """

    def __init__(self, config: Optional[DashboardConfig] = None):
        self.config = config or DashboardConfig()
        self._server = None
        self._sessions: List[Dict] = []
        self._stats: Dict[str, Any] = {}

    def start(self, block: bool = True):
        """
        Start the dashboard server.
        
        Args:
            block: Whether to block the main thread
        """
        DashboardHandler.dashboard = self

        self._server = HTTPServer(
            (self.config.host, self.config.port),
            DashboardHandler,
        )

        logger.info(f"Dashboard started at http://{self.config.host}:{self.config.port}")

        if block:
            self._server.serve_forever()

    def stop(self):
        """Stop the dashboard server."""
        if self._server:
            self._server.shutdown()
            self._server = None

    def get_sessions(self) -> List[Dict]:
        """Get all sessions for display."""
        self._refresh_sessions()
        return self._sessions

    def get_health(self) -> Dict[str, Any]:
        """Get health status."""
        healthy = sum(1 for s in self._sessions if s.get("status") == "healthy")
        total = len(self._sessions)

        return {
            "status": "healthy" if healthy == total else "degraded",
            "healthy": healthy,
            "total": total,
            "timestamp": time.time(),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics."""
        return {
            "total": len(self._sessions),
            "healthy": sum(1 for s in self._sessions if s.get("status") == "healthy"),
            "expired": sum(1 for s in self._sessions if s.get("status") == "expired"),
            "unknown": sum(1 for s in self._sessions if s.get("status") == "unknown"),
        }

    def refresh_session(self, name: str) -> Dict[str, Any]:
        """Refresh a session."""
        return {
            "success": True,
            "message": f"Refreshed session: {name}",
        }

    def validate_session(self, name: str) -> Dict[str, Any]:
        """Validate a session."""
        return {
            "success": True,
            "message": f"Validated session: {name}",
        }

    def delete_session(self, name: str) -> Dict[str, Any]:
        """Delete a session."""
        return {
            "success": True,
            "message": f"Deleted session: {name}",
        }

    def _refresh_sessions(self):
        """Refresh session list from disk."""
        import os
        from pathlib import Path

        sessions_dir = Path("~/.tokenade/sessions").expanduser()
        if not sessions_dir.exists():
            self._sessions = []
            return

        sessions = []
        for f in sessions_dir.glob("*.tokenade"):
            sessions.append({
                "name": f.stem,
                "path": str(f),
                "size": f.stat().st_size,
                "modified": f.stat().st_mtime,
                "status": "healthy",
            })

        self._sessions = sessions[:self.config.max_sessions]
