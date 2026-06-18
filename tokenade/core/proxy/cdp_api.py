"""
CDP Proxy — API endpoint handlers (CDP passthrough, status, stats, stealth.js).
"""

import logging
import time
from typing import TYPE_CHECKING

from aiohttp import web

from tokenade.core.proxy.cdp_stealth import COMPREHENSIVE_STEALTH_SCRIPT

if TYPE_CHECKING:
    from tokenade.core.proxy.cdp_proxy import CDPProxy

logger = logging.getLogger(__name__)


async def handle_cdp_version(proxy: "CDPProxy", request: web.Request) -> web.Response:
    """Proxy /json/version to the actual Chrome CDP endpoint."""
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{proxy._cdp_port}/json/version") as resp:
                data = await resp.json()
                return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=502)


async def handle_cdp_list(proxy: "CDPProxy", request: web.Request) -> web.Response:
    """Proxy /json/list to the actual Chrome CDP endpoint."""
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{proxy._cdp_port}/json/list") as resp:
                data = await resp.json()
                return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=502)


async def handle_stealth_js(proxy: "CDPProxy", request: web.Request) -> web.Response:
    """Return the comprehensive stealth script as JavaScript."""
    return web.Response(text=COMPREHENSIVE_STEALTH_SCRIPT, content_type='application/javascript')


async def handle_status(proxy: "CDPProxy", request: web.Request) -> web.Response:
    """Return proxy status as JSON."""
    return web.json_response({
        "status": "running",
        "site": proxy.session.get("site_name", "unknown"),
        "cookies": len(proxy.cookie_jar.to_list()),
        "tls_profile": proxy.session.get("tls_profile", {}),
        "uptime": time.time() - (proxy.stats["start_time"] or time.time())
    })


async def handle_stats(proxy: "CDPProxy", request: web.Request) -> web.Response:
    """Return proxy statistics as JSON."""
    return web.json_response(proxy.stats)


async def handle_session_status(proxy: "CDPProxy", request: web.Request) -> web.Response:
    """Return session expiry status as JSON."""
    if not proxy._refresher:
        return web.json_response({"error": "Refresh monitor not active"}, status=503)

    status = proxy._refresher.get_status()
    return web.json_response(status)


async def handle_session_refresh(proxy: "CDPProxy", request: web.Request) -> web.Response:
    """Trigger a manual session refresh from source browser."""
    if not proxy._refresher:
        return web.json_response({"error": "Refresh monitor not active"}, status=503)

    try:
        await proxy._refresher._attempt_refresh()
        return web.json_response({
            "status": "refreshed",
            "cookies": len(proxy.session.get("cookies", [])),
        })
    except Exception:
        return web.json_response({"error": "Refresh failed"}, status=500)


async def handle_old_sw(proxy: "CDPProxy", request: web.Request) -> web.Response:
    """Return a service worker that unregisters itself."""
    sw_code = """
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', () => {
    self.registration.unregister();
    clients.matchAll().then(clients => clients.forEach(c => c.navigate(c.url)));
});
"""
    return web.Response(text=sw_code, content_type='application/javascript')
