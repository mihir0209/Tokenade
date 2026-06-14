"""
REST API server for Tokenade.

Provides HTTP API endpoints for session management, proxy control,
and integration with external tools.
"""
import json
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class APIServerConfig:
    """API server configuration."""
    host: str = "127.0.0.1"
    port: int = 9224
    api_key: Optional[str] = None
    sessions_dir: str = "~/.tokenade/sessions"
    cors_origins: List[str] = None
    
    def __post_init__(self):
        if self.cors_origins is None:
            self.cors_origins = ["*"]


class TokenadeAPIServer:
    """REST API server for Tokenade."""
    
    def __init__(self, config: Optional[APIServerConfig] = None):
        self.config = config or APIServerConfig()
        self.sessions_dir = Path(self.config.sessions_dir).expanduser()
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._app = None
        self._runner = None
    
    def _check_auth(self, request) -> bool:
        """Check API key authentication."""
        if not self.config.api_key:
            return True
        
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:] == self.config.api_key
        
        api_key = request.headers.get("X-API-Key", "")
        return api_key == self.config.api_key
    
    def _json_response(self, data: Dict, status: int = 200):
        """Create a JSON response with CORS headers."""
        from aiohttp import web
        
        response = web.json_response(data, status=status)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-API-Key"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        return response
    
    def _error_response(self, message: str, status: int = 400):
        """Create an error response."""
        return self._json_response({"error": message}, status=status)
    
    async def _handle_sessions_list(self, request):
        """GET /api/sessions - List all sessions."""
        if not self._check_auth(request):
            return self._error_response("Unauthorized", 401)
        
        from tokenade.core.importer.session_manager import SessionManager
        manager = SessionManager(str(self.sessions_dir))
        sessions = manager.list_sessions()
        
        return self._json_response({
            "sessions": [
                {
                    "path": s.path,
                    "site_name": s.site_name,
                    "cookie_count": s.cookie_count,
                    "created_at": s.created_at,
                    "source_browser": s.source_browser,
                    "file_size": s.file_size,
                }
                for s in sessions
            ],
            "total": len(sessions),
        })
    
    async def _handle_session_get(self, request):
        """GET /api/sessions/{id} - Get session details."""
        if not self._check_auth(request):
            return self._error_response("Unauthorized", 401)
        
        session_id = request.match_info["id"]
        
        session_files = list(self.sessions_dir.glob(f"*{session_id}*"))
        if not session_files:
            return self._error_response("Session not found", 404)
        
        session_file = session_files[0]
        with open(session_file) as f:
            session = json.load(f)
        
        return self._json_response({
            "id": session_id,
            "file": str(session_file),
            "session": session,
        })
    
    async def _handle_session_delete(self, request):
        """DELETE /api/sessions/{id} - Delete a session."""
        if not self._check_auth(request):
            return self._error_response("Unauthorized", 401)
        
        session_id = request.match_info["id"]
        session_files = list(self.sessions_dir.glob(f"*{session_id}*"))
        
        if not session_files:
            return self._error_response("Session not found", 404)
        
        session_files[0].unlink()
        return self._json_response({"deleted": True})
    
    async def _handle_health_check(self, request):
        """GET /api/health - Health check endpoint."""
        return self._json_response({
            "status": "healthy",
            "version": "3.3.0",
            "sessions_dir": str(self.sessions_dir),
        })
    
    async def _handle_proxy_status(self, request):
        """GET /api/proxy/status - Proxy status."""
        return self._json_response({
            "proxy_running": False,
            "message": "Use 'tokenade proxy' to start the proxy",
        })
    
    async def _handle_export(self, request):
        """POST /api/export - Export session."""
        if not self._check_auth(request):
            return self._error_response("Unauthorized", 401)
        
        try:
            data = await request.json()
        except Exception:
            return self._error_response("Invalid JSON")
        
        browser = data.get("browser", "chrome")
        domains = data.get("domains", [])
        output = data.get("output")
        
        import subprocess
        cmd = ["tokenade", "export", "--browser-name", browser]
        if domains:
            cmd.extend(["--domains", ",".join(domains)])
        if output:
            cmd.extend(["-o", output])
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            return self._json_response({"success": True, "output": result.stdout})
        else:
            return self._error_response(result.stderr, 500)
    
    async def _handle_share_create(self, request):
        """POST /api/share - Create shareable link."""
        if not self._check_auth(request):
            return self._error_response("Unauthorized", 401)
        
        try:
            data = await request.json()
        except Exception:
            return self._error_response("Invalid JSON")
        
        session_file = data.get("session_file")
        password = data.get("password")
        expiry_hours = data.get("expiry_hours", 24)
        
        if not session_file:
            return self._error_response("session_file required")
        
        import subprocess
        cmd = ["tokenade", "share", "-s", session_file]
        if password:
            cmd.extend(["--password", password])
        if expiry_hours:
            cmd.extend(["--expiry", str(expiry_hours)])
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            return self._json_response({"success": True, "output": result.stdout})
        else:
            return self._error_response(result.stderr, 500)
    
    async def _handle_options(self, request):
        """Handle CORS preflight."""
        from aiohttp import web
        return web.Response(status=204)
    
    def create_app(self):
        """Create the aiohttp application."""
        from aiohttp import web
        
        self._app = web.Application()
        
        self._app.router.add_get("/api/sessions", self._handle_sessions_list)
        self._app.router.add_get("/api/sessions/{id}", self._handle_session_get)
        self._app.router.add_delete("/api/sessions/{id}", self._handle_session_delete)
        self._app.router.add_get("/api/health", self._handle_health_check)
        self._app.router.add_get("/api/proxy/status", self._handle_proxy_status)
        self._app.router.add_post("/api/export", self._handle_export)
        self._app.router.add_post("/api/share", self._handle_share_create)
        
        self._app.router.add_route("*", "/api/{tail:.*}", self._handle_options)
        
        return self._app
    
    async def start(self):
        """Start the API server."""
        from aiohttp import web
        
        app = self.create_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        
        site = web.TCPSite(self._runner, self.config.host, self.config.port)
        await site.start()
        
        logger.info(f"API server listening on http://{self.config.host}:{self.config.port}")
    
    async def stop(self):
        """Stop the API server."""
        if self._runner:
            await self._runner.cleanup()
    
    def get_endpoints(self) -> List[Dict]:
        """List all API endpoints."""
        return [
            {"method": "GET", "path": "/api/health", "description": "Health check"},
            {"method": "GET", "path": "/api/sessions", "description": "List sessions"},
            {"method": "GET", "path": "/api/sessions/{id}", "description": "Get session"},
            {"method": "DELETE", "path": "/api/sessions/{id}", "description": "Delete session"},
            {"method": "GET", "path": "/api/proxy/status", "description": "Proxy status"},
            {"method": "POST", "path": "/api/export", "description": "Export session"},
            {"method": "POST", "path": "/api/share", "description": "Create share link"},
        ]
