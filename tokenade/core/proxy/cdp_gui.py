"""
CDP Proxy — GUI HTML templates and page browsing handlers.
"""

import asyncio
import html as html_mod
import logging
import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from aiohttp import web

from tokenade.core.proxy.cdp_stealth import is_safe_url, get_site_url

if TYPE_CHECKING:
    from tokenade.core.proxy.cdp_proxy import CDPProxy

logger = logging.getLogger(__name__)


async def handle_gui(proxy: "CDPProxy", request: web.Request) -> web.Response:
    """Serve the GUI landing page."""
    site_name = html_mod.escape(proxy.session.get("site_name", "unknown"))
    source_device = proxy.session.get("source_device", {})
    browser_name = html_mod.escape(source_device.get("browser", "unknown"))
    platform = html_mod.escape(source_device.get("platform", "unknown"))

    default_url = html_mod.escape(get_site_url(proxy.session))

    gui_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Tokenade CDP Proxy - {site_name}</title>
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
        .architecture {{ color: #888; line-height: 1.8; margin-top: 10px; }}
        .architecture strong {{ color: #00ff88; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Tokenade CDP Proxy</h1>
        <p class="subtitle">Playwright-based session proxy with TLS fingerprint matching</p>

        <div class="card">
            <h3>Session Info</h3>
            <div class="info-row">
                <span class="info-label">Site</span>
                <span class="info-value">{site_name}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Source Browser</span>
                <span class="info-value">{browser_name}</span>
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
                <span class="info-label">TLS Profile</span>
                <span class="info-value">{proxy.session.get("tls_profile", {}).get("impersonate", "unknown")}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Status</span>
                <span class="info-value"><span class="status status-ok">Running</span></span>
            </div>
            <div id="expiry-info" style="margin-top: 10px; padding: 10px; border-radius: 8px; background: #1a1a1a;"></div>
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
            <h3>Architecture</h3>
            <div class="architecture">
                <p><strong>How it works:</strong></p>
                <p>1. Playwright Chromium renders the target page</p>
                <p>2. <code>page.route()</code> intercepts ALL browser requests</p>
                <p>3. Each request is forwarded via <strong>curl-cffi</strong> with the donor's TLS fingerprint</p>
                <p>4. Donor cookies are injected into the browser context</p>
                <p>5. Browser renders everything natively - no URL rewriting needed</p>
            </div>
        </div>

        <div class="card">
            <h3>Usage</h3>
            <div class="instructions">
                <p><strong>GUI Mode:</strong> Enter a URL above and click Browse</p>
                <p><strong>Proxy Mode:</strong> Configure your browser:</p>
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
        if ('serviceWorker' in navigator) {{
            navigator.serviceWorker.getRegistrations().then(regs => {{
                regs.forEach(r => {{ r.unregister(); }});
            }});
        }}
        async function updateStats() {{
            try {{
                const resp = await fetch('/stats');
                const data = await resp.json();
                document.getElementById('requests').textContent = data.requests || 0;
                document.getElementById('bytes-in').textContent = formatBytes(data.bytes_received || 0);
                document.getElementById('bytes-out').textContent = formatBytes(data.bytes_sent || 0);
            }} catch(e) {{}}
        }}
        async function updateSessionStatus() {{
            try {{
                const resp = await fetch('/session/status');
                const data = await resp.json();
                const el = document.getElementById('expiry-info');
                if (data.expired_count > 0) {{
                    el.innerHTML = '<span style="color: #ff6b6b;">' + data.expired_count + ' expired cookies</span>' +
                        '<button onclick="refreshSession()" style="margin-left: 10px; padding: 4px 8px; background: #ff6b6b; color: #fff; border: none; border-radius: 4px; cursor: pointer;">Refresh</button>';
                }} else if (data.critical_count > 0) {{
                    el.innerHTML = '<span style="color: #ffa500;">' + data.critical_count + ' cookies expiring soon (' + (data.next_expiry_human || 'unknown') + ')</span>' +
                        '<button onclick="refreshSession()" style="margin-left: 10px; padding: 4px 8px; background: #ffa500; color: #000; border: none; border-radius: 4px; cursor: pointer;">Refresh</button>';
                }} else if (data.expiring_soon_count > 0) {{
                    el.innerHTML = '<span style="color: #888;">' + data.expiring_soon_count + ' cookies expiring in ' + data.next_expiry_human + '</span>';
                }} else {{
                    el.innerHTML = '<span style="color: #00ff88;">All cookies valid</span>';
                }}
            }} catch(e) {{}}
        }}
        async function refreshSession() {{
            try {{
                const resp = await fetch('/session/refresh', {{ method: 'POST' }});
                const data = await resp.json();
                if (data.status === 'refreshed') {{
                    updateSessionStatus();
                }}
            }} catch(e) {{}}
        }}
        function formatBytes(bytes) {{
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
            return (bytes/(1024*1024)).toFixed(1) + ' MB';
        }}
        setInterval(updateStats, 2000);
        setInterval(updateSessionStatus, 60000);
        updateStats();
        updateSessionStatus();
    </script>
</body>
</html>"""
    return web.Response(text=gui_html, content_type='text/html')


async def handle_browse_post(proxy: "CDPProxy", request: web.Request) -> web.Response:
    """Handle POST to /browse - create a new page and navigate."""
    try:
        data = await request.post()
        url = data.get("url", "")

        if not url:
            return web.Response(text="No URL provided", status=400)

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        parsed = urlparse(url)
        if not parsed.hostname:
            return web.Response(text="Invalid URL", status=400)

        if not is_safe_url(url):
            return web.Response(text="URL blocked: internal/private network target", status=403)

        proxy._cleanup_expired_pages()

        if len(proxy._pages) >= proxy._max_pages:
            oldest_id = min(proxy._page_meta, key=lambda k: proxy._page_meta[k]["created"])
            await proxy._close_page(oldest_id)

        page_id = str(int(time.time() * 1000))

        page = await proxy._context.new_page()
        proxy._pages[page_id] = page
        proxy._page_meta[page_id] = {"created": time.time()}

        if proxy.config.use_fingerprint:
            from tokenade.core.proxy.cdp_routing import handle_route
            await page.route("**/*", lambda route: handle_route(proxy, route))

        asyncio.create_task(proxy._navigate_page(page_id, url))

        raise web.HTTPFound(f"/page/{page_id}")

    except web.HTTPFound:
        raise
    except Exception:
        logger.exception("Failed to process browse request")
        return web.Response(text="Failed to process request", status=500)


async def handle_page(proxy: "CDPProxy", request: web.Request) -> web.Response:
    """Serve a page that displays the browser content via screenshot."""
    page_id = request.match_info["page_id"]

    page = proxy._pages.get(page_id)
    if not page:
        return web.Response(
            text="<html><body><h1>Page not found</h1><p>The page may still be loading.</p></body></html>",
            content_type="text/html",
            status=404
        )

    try:
        current_url = html_mod.escape(page.url or "")

        page_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Tokenade - Browsing</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: monospace; background: #1a1a1a; color: #fff; }}
        .toolbar {{
            background: #0a0a0a; padding: 10px 20px; border-bottom: 1px solid #333;
            display: flex; align-items: center; gap: 10px;
        }}
        .toolbar .url {{
            flex: 1; padding: 8px 12px; border-radius: 4px; border: 1px solid #333;
            background: #1a1a1a; color: #00ff88; font-family: monospace; font-size: 14px;
        }}
        .toolbar a {{ color: #00ff88; text-decoration: none; padding: 8px 16px; }}
        .toolbar a:hover {{ background: #00ff8822; border-radius: 4px; }}
        .screenshot-container {{
            display: flex; justify-content: center; align-items: flex-start;
            padding: 10px; overflow: auto; height: calc(100vh - 50px);
        }}
        .screenshot-container img {{
            max-width: 100%; height: auto; border: 1px solid #333; border-radius: 4px;
        }}
        .loading {{
            display: flex; align-items: center; justify-content: center;
            height: calc(100vh - 50px); color: #888; font-size: 1.2em;
        }}
    </style>
</head>
<body>
    <div class="toolbar">
        <span class="url">{current_url}</span>
        <a href="/">Back</a>
    </div>
    <div id="content">
        <div class="loading">Loading screenshot...</div>
    </div>
    <script>
        async function refreshScreenshot() {{
            try {{
                const resp = await fetch('/api/page/{page_id}/screenshot');
                if (resp.ok) {{
                    const blob = await resp.blob();
                    const url = URL.createObjectURL(blob);
                    document.getElementById('content').innerHTML = '';
                    const img = document.createElement('img');
                    img.src = url;
                    img.className = 'screenshot-container';
                    document.getElementById('content').appendChild(img);
                }}
            }} catch(e) {{
                console.error('Screenshot refresh failed:', e);
            }}
        }}

        setTimeout(refreshScreenshot, 2000);
        setInterval(refreshScreenshot, 5000);
    </script>
</body>
</html>"""
        return web.Response(text=page_html, content_type='text/html')

    except Exception:
        return web.Response(text="Error loading page", status=500)
