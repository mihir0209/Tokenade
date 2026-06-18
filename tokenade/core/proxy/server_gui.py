"""
Tokenade Legacy Proxy — GUI HTML templates.
"""

import html as html_module
from typing import TYPE_CHECKING
from urllib.parse import quote

from aiohttp import web
from tokenade.core.proxy.cdp_stealth import get_site_url

if TYPE_CHECKING:
    from tokenade.core.proxy.server import TokenadeProxy


async def handle_gui(proxy: "TokenadeProxy", request: web.Request) -> web.Response:
    """Serve the GUI landing page."""
    site_name = html_module.escape(proxy.session.get("site_name", "unknown"))
    source_device = proxy.session.get("source_device", {})
    browser = html_module.escape(source_device.get("browser", "unknown"))
    platform = html_module.escape(source_device.get("platform", "unknown"))
    default_url = html_module.escape(proxy._target_url or get_site_url(proxy.session))

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Tokenade Proxy - {site_name}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0a0a; color: #fff; min-height: 100vh;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
        }}
        .container {{ max-width: 800px; padding: 40px; width: 100%; }}
        h1 {{ font-size: 2.5em; margin-bottom: 10px; }}
        .subtitle {{ color: #888; font-size: 1.2em; margin-bottom: 40px; }}
        .card {{
            background: #1a1a1a; border-radius: 12px; padding: 24px;
            margin-bottom: 20px; border: 1px solid #333;
        }}
        .card h3 {{ color: #00ff88; margin-bottom: 12px; }}
        .info-row {{ display: flex; justify-content: space-between; margin: 8px 0; }}
        .info-label {{ color: #888; }}
        .info-value {{ color: #fff; font-weight: 500; }}
        .browse-form {{
            display: flex; gap: 10px; margin: 20px 0;
        }}
        .browse-input {{
            flex: 1; padding: 16px; border-radius: 8px; border: 1px solid #333;
            background: #0a0a0a; color: #fff; font-size: 1em; font-family: monospace;
        }}
        .browse-input:focus {{ outline: none; border-color: #00ff88; }}
        .browse-btn {{
            background: #00ff88; color: #000; padding: 16px 24px;
            border-radius: 8px; border: none; font-size: 1em; font-weight: 600;
            cursor: pointer; transition: transform 0.2s;
        }}
        .browse-btn:hover {{ transform: scale(1.05); }}
        .instructions {{ color: #888; line-height: 1.6; }}
        .instructions code {{
            background: #333; padding: 2px 6px; border-radius: 4px;
            font-family: monospace; color: #00ff88;
        }}
        .stats {{ display: flex; gap: 20px; margin-top: 20px; }}
        .stat {{ text-align: center; }}
        .stat-value {{ font-size: 2em; font-weight: bold; color: #00ff88; }}
        .stat-label {{ color: #888; font-size: 0.9em; }}
        .status {{
            padding: 8px 16px; border-radius: 20px;
            display: inline-block; margin: 10px 0;
        }}
        .status-ok {{ background: #00ff8822; color: #00ff88; border: 1px solid #00ff88; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Tokenade Proxy</h1>
        <p class="subtitle">Fingerprint-matched session proxy</p>

        <div class="card">
            <h3>Session Info</h3>
            <div class="info-row">
                <span class="info-label">Site</span>
                <span class="info-value">{site_name}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Source Browser</span>
                <span class="info-value">{browser}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Platform</span>
                <span class="info-value">{platform}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Cookies</span>
                <span class="info-value">{len(proxy.cookie_jar.to_list())}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Status</span>
                <span class="info-value"><span class="status status-ok">Running</span></span>
            </div>
        </div>

        <div class="card">
            <h3>Browse as Donor Device</h3>
            <p style="color: #888; margin-bottom: 15px;">Enter a URL to browse with the donor's fingerprint and cookies:</p>
            <form class="browse-form" action="/browse" method="POST">
                <input type="text" name="url" class="browse-input" value="{default_url}" placeholder="https://example.com">
                <button type="submit" class="browse-btn">Browse</button>
            </form>
        </div>

        <div class="card">
            <h3>Proxy Configuration</h3>
            <div class="info-row">
                <span class="info-label">HTTP Proxy</span>
                <span class="info-value" style="font-family: monospace;">http://127.0.0.1:{proxy.config.port}</span>
            </div>
            <div class="info-row">
                <span class="info-label">HTTPS Proxy</span>
                <span class="info-value" style="font-family: monospace;">http://127.0.0.1:{proxy.config.port}</span>
            </div>
        </div>

        <div class="card">
            <h3>Usage</h3>
            <div class="instructions">
                <p><strong>GUI Mode:</strong> Enter a URL above and click Browse</p>
                <p><strong>Proxy Mode:</strong> Configure your browser or terminal:</p>
                <p>Linux/Mac: <code>export HTTP_PROXY=http://127.0.0.1:{proxy.config.port}</code></p>
                <p>Windows: <code>set HTTP_PROXY=http://127.0.0.1:{proxy.config.port}</code></p>
                <p><strong>curl:</strong> <code>curl --proxy http://127.0.0.1:{proxy.config.port} https://example.com</code></p>
            </div>
        </div>

        <div class="stats" id="stats">
            <div class="stat">
                <div class="stat-value" id="requests">0</div>
                <div class="stat-label">Requests</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="bytes-in">0</div>
                <div class="stat-label">Received</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="bytes-out">0</div>
                <div class="stat-label">Sent</div>
            </div>
        </div>
    </div>

    <script>
        async function updateStats() {{
            try {{
                const resp = await fetch('/stats');
                const data = await resp.json();
                document.getElementById('requests').textContent = data.requests || 0;
                document.getElementById('bytes-in').textContent = formatBytes(data.bytes_received || 0);
                document.getElementById('bytes-out').textContent = formatBytes(data.bytes_sent || 0);
            }} catch(e) {{}}
        }}
        function formatBytes(bytes) {{
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
            return (bytes/(1024*1024)).toFixed(1) + ' MB';
        }}
        setInterval(updateStats, 2000);
        updateStats();
    </script>
</body>
</html>"""
    return web.Response(text=html, content_type='text/html')


async def handle_browse_page(proxy: "TokenadeProxy", request: web.Request) -> web.Response:
    """Show the browse page with URL input."""
    default_url = html_module.escape(proxy._target_url or get_site_url(proxy.session))

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Browse - Tokenade Proxy</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: monospace; background: #1a1a1a; color: #fff; }}
        .toolbar {{
            background: #0a0a0a; padding: 10px 20px; border-bottom: 1px solid #333;
            display: flex; align-items: center; gap: 10px;
        }}
        .toolbar input {{
            flex: 1; padding: 8px 12px; border-radius: 4px; border: 1px solid #333;
            background: #1a1a1a; color: #fff; font-family: monospace;
        }}
        .toolbar button {{
            background: #00ff88; color: #000; padding: 8px 16px;
            border: none; border-radius: 4px; cursor: pointer; font-weight: bold;
        }}
        .toolbar a {{ color: #00ff88; text-decoration: none; margin-left: 10px; }}
        .frame {{ width: 100%; height: calc(100vh - 50px); border: none; }}
    </style>
</head>
<body>
    <div class="toolbar">
        <form action="/browse" method="GET" style="display: flex; gap: 10px; flex: 1;">
            <input type="text" name="url" value="{default_url}" placeholder="Enter URL">
            <button type="submit">Go</button>
        </form>
        <a href="/">Back to Proxy</a>
    </div>
    <iframe class="frame" src="/proxy-frame?url={quote(default_url)}"></iframe>
</body>
</html>"""
    return web.Response(text=html, content_type='text/html')
