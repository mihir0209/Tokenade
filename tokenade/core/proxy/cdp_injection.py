"""
CDP Proxy — Cookie, stealth, and localStorage injection via CDP/WebSocket.
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from tokenade.core.proxy.cdp_stealth import COMPREHENSIVE_STEALTH_SCRIPT

if TYPE_CHECKING:
    from tokenade.core.proxy.cdp_proxy import CDPProxy

logger = logging.getLogger(__name__)


async def inject_via_cdp(proxy: "CDPProxy"):
    """Inject stealth script and cookies via CDP protocol (browser-level)."""
    from tokenade.core.errors import InjectionError

    if not proxy._cdp_session:
        raise InjectionError(
            "No CDP session available for cookie injection",
            operation="inject_via_cdp",
        )

    try:
        await proxy._cdp_session.send("Page.addScriptToEvaluateOnNewDocument", {
            "source": COMPREHENSIVE_STEALTH_SCRIPT
        })
        logger.info("Injected stealth script via CDP (browser-level)")
    except Exception as e:
        logger.warning("CDP stealth injection failed: %s", e)

    try:
        await proxy._cdp_session.send("Network.enable")
    except Exception as e:
        logger.debug("Network.enable failed (continuing): %s", e)

    cookies = proxy.session.get("cookies", [])
    injected = 0
    failed = 0
    last_error = None
    for cookie in cookies:
        try:
            params = {
                "name": cookie.get("name", ""),
                "value": cookie.get("value", ""),
                "domain": cookie.get("domain", ""),
                "path": cookie.get("path", "/"),
            }
            if cookie.get("secure"):
                params["secure"] = True
            if cookie.get("httpOnly"):
                params["httpOnly"] = True

            same_site = cookie.get("sameSite", "").lower()
            if same_site == "strict":
                params["sameSite"] = "Strict"
            elif same_site == "lax":
                params["sameSite"] = "Lax"
            elif same_site == "none":
                params["sameSite"] = "None"

            expires = cookie.get("expires")
            if expires:
                if isinstance(expires, (int, float)) and expires > 1262304000000:
                    expires = expires / 1000
                params["expires"] = expires

            await proxy._cdp_session.send("Network.setCookie", params)
            injected += 1
        except Exception as e:
            failed += 1
            last_error = e
            logger.debug(
                "Cookie inject failed for %s@%s: %s",
                cookie.get("name"),
                cookie.get("domain"),
                e,
            )

    logger.info(
        "Injected %s/%s cookies via CDP (failed=%s)",
        injected,
        len(cookies),
        failed,
    )
    if cookies and injected == 0:
        raise InjectionError(
            f"Failed to inject any of {len(cookies)} cookies via CDP",
            operation="inject_via_cdp",
            cause=last_error,
        )


async def inject_via_raw_cdp(proxy: "CDPProxy"):
    """Inject cookies and stealth via raw CDP WebSocket at the browser level."""
    import json as json_mod
    try:
        import websockets
    except ImportError:
        logger.warning("websockets not installed, skipping raw CDP injection")
        return

    try:
        import urllib.request
        resp = urllib.request.urlopen(f"http://127.0.0.1:{proxy._cdp_port}/json/version", timeout=5)
        version_info = json_mod.loads(resp.read())
        ws_url = version_info.get("webSocketDebuggerUrl")
        if not ws_url:
            return
    except Exception as e:
        logger.warning(f"Failed to get CDP WebSocket URL: {e}")
        return

    fp_data = proxy.session.get("fingerprint") or {}
    user_agent = fp_data.get("user_agent",
                             "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    user_agent = user_agent.replace("HeadlessChrome", "Chrome")
    cookies = proxy.session.get("cookies", [])

    try:
        async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:
            msg_counter = [0]
            buffered_events = []

            async def send_cdp_and_wait(method, params=None, session_id=None):
                msg_counter[0] += 1
                mid = msg_counter[0]
                msg = {"id": mid, "method": method}
                if params:
                    msg["params"] = params
                if session_id:
                    msg["sessionId"] = session_id
                await ws.send(json_mod.dumps(msg))

                deadline = time.time() + 10
                while time.time() < deadline:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=10)
                        data = json_mod.loads(raw)
                        if "id" in data and data["id"] == mid:
                            return data
                        elif "method" in data:
                            buffered_events.append(data)
                    except asyncio.TimeoutError:
                        break
                return None

            # 1. Inject cookies
            await send_cdp_and_wait("Storage.enable")

            storage_cookies = []
            for cookie in cookies:
                try:
                    c = {
                        "name": cookie.get("name", ""),
                        "value": cookie.get("value", ""),
                        "domain": cookie.get("domain", ""),
                        "path": cookie.get("path", "/"),
                    }
                    if cookie.get("secure"):
                        c["secure"] = True
                    if cookie.get("httpOnly"):
                        c["httpOnly"] = True
                    ss = cookie.get("sameSite", "").lower()
                    if ss in ("strict", "lax", "none"):
                        c["sameSite"] = ss.capitalize()
                    exp = cookie.get("expires")
                    if exp:
                        if isinstance(exp, (int, float)) and exp > 1262304000000:
                            exp = exp / 1000
                        c["expires"] = exp
                    storage_cookies.append(c)
                except Exception:
                    pass

            r = await send_cdp_and_wait("Storage.setCookies", {"cookies": storage_cookies})
            logger.info(f"Raw CDP: Storage.setCookies result: {r}")

            # 2. Auto-attach
            r = await send_cdp_and_wait("Target.setAutoAttach", {
                "autoAttach": True,
                "waitForDebuggerOnStart": False,
                "flatten": True,
            })
            logger.info(f"Raw CDP: Target.setAutoAttach result: {r}")

            # 3. Event loop — inject stealth into new targets
            logger.info(f"CDP monitor started: {len(cookies)} cookies, watching for targets")
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    if raw is None:
                        continue
                    data = json_mod.loads(raw)

                    method = data.get("method", "")
                    params = data.get("params", {})

                    if method == "Target.attachedToTarget":
                        session_id = params.get("sessionId")
                        target_info = params.get("targetInfo", {})
                        if session_id and target_info.get("type") == "page":
                            try:
                                msg_counter[0] += 1
                                mid = msg_counter[0]
                                await ws.send(json_mod.dumps({
                                    "id": mid,
                                    "method": "Page.addScriptToEvaluateOnNewDocument",
                                    "params": {"source": COMPREHENSIVE_STEALTH_SCRIPT, "runImmediately": True},
                                    "sessionId": session_id,
                                }))
                                msg_counter[0] += 1
                                mid2 = msg_counter[0]
                                await ws.send(json_mod.dumps({
                                    "id": mid2,
                                    "method": "Network.enable",
                                    "sessionId": session_id,
                                }))
                                logger.debug(f"Injected stealth into target: {session_id}")
                            except Exception as e:
                                logger.debug(f"Failed to inject into target: {e}")

                    elif method == "Target.targetDestroyed":
                        pass

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.debug(f"CDP monitor event error: {e}")
                    break

    except Exception as e:
        logger.error(f"Raw CDP injection failed: {e}")


async def inject_stealth_script(proxy: "CDPProxy"):
    """Inject stealth script into all pages via Playwright context."""
    if not proxy._context:
        return

    try:
        script = COMPREHENSIVE_STEALTH_SCRIPT

        for page_id, page in proxy._pages.items():
            try:
                await page.evaluate(script)
                logger.debug(f"Injected stealth into page {page_id}")
            except Exception as e:
                logger.debug(f"Failed to inject stealth into page {page_id}: {e}")

        try:
            await proxy._context.add_init_script(COMPREHENSIVE_STEALTH_SCRIPT)
        except Exception as e:
            logger.debug(f"Failed to add init script: {e}")

    except Exception as e:
        logger.warning(f"Stealth injection failed: {e}")


async def inject_cookies(proxy: "CDPProxy"):
    """Inject cookies into the browser context."""
    from tokenade.core.errors import InjectionError

    cookies = proxy.session.get("cookies", [])
    if not proxy._context:
        if cookies:
            raise InjectionError(
                "No browser context available for cookie injection",
                operation="inject_cookies",
            )
        return

    playwright_cookies = []
    process_failures = 0

    for cookie in cookies:
        try:
            pc = {
                "name": cookie.get("name", ""),
                "value": cookie.get("value", ""),
                "domain": cookie.get("domain", ""),
                "path": cookie.get("path", "/"),
            }

            if cookie.get("secure"):
                pc["secure"] = True
            if cookie.get("httpOnly"):
                pc["httpOnly"] = True

            same_site = cookie.get("sameSite", "").lower()
            if same_site == "strict":
                pc["sameSite"] = "Strict"
            elif same_site == "lax":
                pc["sameSite"] = "Lax"
            elif same_site == "none":
                pc["sameSite"] = "None"

            expires = cookie.get("expires")
            if expires:
                if isinstance(expires, (int, float)):
                    if expires > 1262304000000:
                        expires = expires / 1000
                    pc["expires"] = float(expires)

            playwright_cookies.append(pc)
        except Exception as e:
            process_failures += 1
            logger.debug("Failed to process cookie: %s", e)

    if cookies and not playwright_cookies:
        raise InjectionError(
            f"Failed to process any of {len(cookies)} cookies for injection "
            f"(process_failures={process_failures})",
            operation="inject_cookies",
        )

    if playwright_cookies:
        try:
            await proxy._context.add_cookies(playwright_cookies)
            logger.info(
                "Injected %s cookies into browser context",
                len(playwright_cookies),
            )
        except Exception as e:
            raise InjectionError(
                f"Failed to inject {len(playwright_cookies)} cookies into browser context",
                operation="inject_cookies",
                cause=e,
            ) from e


async def inject_local_storage(proxy: "CDPProxy", page):
    """Inject localStorage into a page after navigation."""
    from tokenade.core.errors import InjectionError

    local_storage = proxy.session.get("local_storage", {})
    if not local_storage:
        return

    domain_ls = {}
    for key, value in local_storage.items():
        if isinstance(value, dict):
            for k, v in value.items():
                domain_ls[k] = v
        else:
            domain_ls[key] = value

    if not domain_ls:
        return

    try:
        js_code = "(() => {"
        for key, value in domain_ls.items():
            escaped_key = key.replace("'", "\\'")
            escaped_val = str(value).replace("'", "\\'")
            js_code += f"localStorage.setItem('{escaped_key}', '{escaped_val}');"
        js_code += "})();"

        await page.evaluate(js_code)
        logger.info("Injected %s localStorage items", len(domain_ls))
    except Exception as e:
        raise InjectionError(
            f"localStorage injection failed ({len(domain_ls)} keys)",
            operation="inject_local_storage",
            cause=e,
        ) from e
