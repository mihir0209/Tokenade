"""
Multi-Site Session Bundler - Serve multiple sessions from one proxy.

Loads multiple .tokenade files and serves each on its own port.
A master GUI at the base port shows tabs for all active sessions.

Features:
- Shared connection pool across all proxy instances
- Reuse of aiohttp.ClientSession for connection efficiency
- Centralized session status and refresh endpoints

Usage:
    tokenade proxy --all --sessions-dir ./sessions/
    tokenade proxy --all -s session1.tokenade -s session2.tokenade
"""

import asyncio
import logging
from typing import Optional, Dict, List

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)


class SharedConnectionPool:
    """
    Shared aiohttp connection pool for multiple CDPProxy instances.

    Avoids creating separate TCP connectors per proxy, reducing
    file descriptor usage and enabling connection reuse across sites.
    """

    def __init__(
        self,
        max_connections: int = 200,
        max_per_host: int = 50,
        timeout: int = 30,
    ):
        self._max_connections = max_connections
        self._max_per_host = max_per_host
        self._timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create the shared aiohttp session."""
        async with self._lock:
            if self._session is None or self._session.closed:
                connector = aiohttp.TCPConnector(
                    ssl=False,
                    limit=self._max_connections,
                    limit_per_host=self._max_per_host,
                    enable_cleanup_closed=True,
                )
                timeout = aiohttp.ClientTimeout(total=self._timeout, connect=10)
                self._session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout,
                    auto_decompress=False,
                )
                logger.info(
                    "Shared connection pool created: "
                    f"max={self._max_connections}, per_host={self._max_per_host}"
                )
            return self._session

    async def close(self):
        """Close the shared session."""
        async with self._lock:
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None
                logger.info("Shared connection pool closed")

    @property
    def stats(self) -> Dict:
        """Get pool statistics."""
        if self._session and not self._session.closed:
            connector = self._session.connector
            return {
                "active_connections": len(connector._conns) if hasattr(connector, '_conns') else 0,
                "max_connections": self._max_connections,
                "max_per_host": self._max_per_host,
            }
        return {"active_connections": 0, "max_connections": self._max_connections}


class MultiSiteProxy:
    """Serve multiple .tokenade sessions from one command."""

    def __init__(self, sessions: List[Dict], base_port: int = 9222, host: str = "127.0.0.1"):
        self.sessions = sessions
        self.base_port = base_port
        self.host = host
        self._proxies = []
        self._app = None
        self._shared_pool = SharedConnectionPool()

    def _on_proxy_task_done(self, task):
        if task.cancelled():
            return
        try:
            task.exception()
        except asyncio.CancelledError:
            pass

    async def start(self):
        """Start all proxy instances and the master GUI."""
        from tokenade.core.proxy.cdp_proxy import CDPProxy, CDPProxyConfig

        tasks = []
        runner = None
        try:
            shared_session = await self._shared_pool.get_session()

            for i, session in enumerate(self.sessions):
                # Each CDPProxy also reserves port + 1 for Chromium's CDP endpoint.
                port = self.base_port + (i * 2) + 1
                site_name = session.get("site_name", f"site_{i}")
                logger.info(f"Starting proxy for {site_name} on port {port}")

                config = CDPProxyConfig(
                    port=port,
                    host=self.host,
                    headless=True,
                    timeout=30,
                    use_fingerprint=False,
                )
                proxy = CDPProxy(session, config)
                proxy._shared_http_session = shared_session
                self._proxies.append({"proxy": proxy, "port": port, "session": session})

            for item in self._proxies:
                task = asyncio.create_task(item["proxy"].start())
                task.add_done_callback(self._on_proxy_task_done)
                tasks.append(task)

            try:
                await asyncio.wait_for(asyncio.gather(*tasks), timeout=30)
            except asyncio.TimeoutError as exc:
                raise RuntimeError("Timed out starting multi-site proxies") from exc
            except Exception as exc:
                failed_site = next(
                    (
                        item["session"].get("site_name", "unknown")
                        for task, item in zip(tasks, self._proxies)
                        if task.done() and not task.cancelled() and task.exception() is not None
                    ),
                    "unknown",
                )
                raise RuntimeError(
                    f"Proxy for site '{failed_site}' failed to start: {exc}"
                ) from exc

            self._app = self._create_master_app()
            runner = web.AppRunner(self._app)
            await runner.setup()
            site = web.TCPSite(runner, self.host, self.base_port)
            await site.start()

            self._print_status()

            try:
                await asyncio.Event().wait()
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            for task in tasks:
                try:
                    await task
                except BaseException:
                    pass
            for item in self._proxies:
                try:
                    await item["proxy"].stop()
                except Exception:
                    pass
            try:
                if runner is not None:
                    await runner.cleanup()
            finally:
                await self._shared_pool.close()

    def _create_master_app(self) -> web.Application:
        """Create the master GUI application."""
        app = web.Application()
        app.router.add_get("/", self._handle_master_gui)
        app.router.add_get("/api/sessions", self._handle_sessions_api)
        return app

    async def _handle_master_gui(self, request: web.Request) -> web.Response:
        """Serve the master multi-site GUI."""
        tabs_html = ""
        for i, item in enumerate(self._proxies):
            active = "active" if i == 0 else ""
            site_name = item["session"].get("site_name", "unknown")
            cookies = len(item["session"].get("cookies", []))
            port = item["port"]
            tabs_html += f'''
            <div class="tab {active}" onclick="switchTab({i}, {port})">
                <span class="site-name">{site_name}</span>
                <span class="cookie-count">{cookies} cookies</span>
            </div>'''

        iframe_html = ""
        for i, item in enumerate(self._proxies):
            display = "block" if i == 0 else "none"
            port = item["port"]
            iframe_html += f'''
            <iframe id="frame{i}" src="http://{self.host}:{port}"
                    style="display:{display};width:100%;height:calc(100vh - 60px);border:none;"
                    frameborder="0"></iframe>'''

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Tokenade Multi-Site Proxy</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: #0a0a0a; color: #fff; height: 100vh; overflow: hidden; }}
        .tab-bar {{
            display: flex; background: #1a1a1a; border-bottom: 2px solid #333;
            padding: 0 10px; height: 50px; align-items: stretch;
        }}
        .tab {{
            display: flex; flex-direction: column; justify-content: center;
            padding: 8px 16px; cursor: pointer; border-bottom: 2px solid transparent;
            transition: all 0.2s; margin-right: 2px;
        }}
        .tab:hover {{ background: #222; }}
        .tab.active {{ border-bottom-color: #4a9eff; background: #1a1a2e; }}
        .site-name {{ font-weight: 600; font-size: 13px; }}
        .cookie-count {{ font-size: 10px; color: #888; }}
        .header {{ display: flex; align-items: center; gap: 10px; padding: 0 16px; }}
        .header h1 {{ font-size: 14px; font-weight: 600; color: #4a9eff; white-space: nowrap; }}
    </style>
</head>
<body>
    <div class="tab-bar">
        <div class="header">
            <h1>Tokenade</h1>
        </div>
        {tabs_html}
    </div>
    {iframe_html}
    <script>
        function switchTab(index, port) {{
            document.querySelectorAll('.tab').forEach((t, i) => {{
                t.classList.toggle('active', i === index);
            }});
            for (let i = 0; i < {len(self._proxies)}; i++) {{
                const frame = document.getElementById('frame' + i);
                if (frame) frame.style.display = (i === index) ? 'block' : 'none';
            }}
        }}
    </script>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def _handle_sessions_api(self, request: web.Request) -> web.Response:
        """Return session info as JSON."""
        sessions = []
        for i, item in enumerate(self._proxies):
            sessions.append({
                "index": i,
                "site_name": item["session"].get("site_name", "unknown"),
                "port": item["port"],
                "cookies": len(item["session"].get("cookies", [])),
                "auth_status": item["session"].get("auth_status", "unknown"),
            })
        return web.json_response(sessions)

    def _print_status(self):
        """Print startup status."""
        print(f"\n{'=' * 60}")
        print("Tokenade Multi-Site Proxy")
        print(f"{'=' * 60}")
        print(f"Master GUI: http://{self.host}:{self.base_port}")
        print(f"Sessions: {len(self._proxies)}")
        print()
        for item in self._proxies:
            site = item["session"].get("site_name", "unknown")
            cookies = len(item["session"].get("cookies", []))
            print(f"  - {site}: {cookies} cookies -> port {item['port']}")
        print(f"\n{'=' * 60}\n")
