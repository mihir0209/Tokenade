"""
CDP WebSocket Connection - Control system browser via Chrome DevTools Protocol.

Connects to the CDP WebSocket endpoint of a system browser and provides
methods for cookie injection, navigation, JavaScript evaluation, and
stealth script injection.

Usage:
    cdp = CDPConnection(port=9222)
    cdp.connect()
    cdp.inject_cookies(cookies)
    cdp.navigate("https://mail.google.com")
    cdp.inject_stealth()
    # ... do stuff ...
    cdp.close()
"""

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class CDPConnection:
    """
    Connect to a browser's CDP WebSocket and control it.

    This connects to the RAW CDP endpoint (not via Playwright),
    which means there are zero Playwright artifacts in the browser.

    Usage:
        cdp = CDPConnection(port=9222)
        cdp.connect()
        cdp.inject_cookies(cookies)
        cdp.navigate("https://mail.google.com")
    """

    def __init__(self, port: int = 9222, host: str = "127.0.0.1"):
        self.port = port
        self.host = host
        self._ws = None
        self._msg_id = 0
        self._callbacks: Dict[int, asyncio.Future] = {}
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._reader_task: Optional[asyncio.Task] = None

    @property
    def cdp_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    async def connect(self, target_page: bool = True) -> bool:
        """
        Connect to CDP WebSocket.

        Args:
            target_page: If True, connect to a page target (for Page.* commands).
                        If False, connect to browser target (for Browser.* commands).

        Returns:
            True if connected successfully
        """
        try:
            import websockets

            if target_page:
                # Get page target from /json/list
                ws_url = await self._get_page_ws_url()
            else:
                # Get browser target from /json/version
                ws_url = await self._get_ws_url()

            if not ws_url:
                logger.error("Could not get WebSocket URL from CDP")
                return False

            # Connect to WebSocket
            self._ws = await websockets.connect(
                ws_url,
                max_size=10 * 1024 * 1024,  # 10MB
                ping_interval=30,
                ping_timeout=10,
            )

            # Start reader task
            self._reader_task = asyncio.create_task(self._read_loop())

            logger.info(f"Connected to CDP at {ws_url}")
            return True

        except ImportError:
            logger.error("websockets package not installed: pip install websockets")
            return False
        except Exception as e:
            logger.error(f"CDP connection failed: {e}")
            return False

    async def _get_page_ws_url(self) -> Optional[str]:
        """Get WebSocket URL for a page target from /json/list."""
        import urllib.request

        try:
            # First try to get existing page targets
            req = urllib.request.Request(f"{self.cdp_url}/json/list")
            with urllib.request.urlopen(req, timeout=5) as resp:
                targets = json.loads(resp.read().decode())

            # Find a page target
            for target in targets:
                if target.get("type") == "page":
                    ws_url = target.get("webSocketDebuggerUrl")
                    if ws_url:
                        logger.debug(f"Found page target: {target.get('title', 'untitled')}")
                        return ws_url

            # No page target found, create a new tab (PUT for Brave compat)
            logger.debug("No page target found, creating new tab")
            req = urllib.request.Request(f"{self.cdp_url}/json/new?about:blank", method='PUT')
            with urllib.request.urlopen(req, timeout=5) as resp:
                new_target = json.loads(resp.read().decode())
                return new_target.get("webSocketDebuggerUrl")

        except Exception as e:
            logger.debug(f"Failed to get page WS URL: {e}")
            # Fallback to browser target
            return await self._get_ws_url()

    async def _get_ws_url(self) -> Optional[str]:
        """Get WebSocket debugger URL from CDP /json/version."""
        import urllib.request

        try:
            req = urllib.request.Request(f"{self.cdp_url}/json/version")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                return data.get("webSocketDebuggerUrl")
        except Exception as e:
            logger.debug(f"Failed to get WS URL: {e}")
            return None

    async def _read_loop(self):
        """Read messages from WebSocket and dispatch to callbacks."""
        try:
            async for message in self._ws:
                data = json.loads(message)

                if "id" in data:
                    # Response to a command
                    msg_id = data["id"]
                    if msg_id in self._callbacks:
                        if "error" in data:
                            self._callbacks[msg_id].set_exception(
                                RuntimeError(data["error"].get("message", "CDP error"))
                            )
                        else:
                            self._callbacks[msg_id].set_result(data.get("result", {}))

                elif "method" in data:
                    # Event
                    method = data["method"]
                    if method in self._event_handlers:
                        for handler in self._event_handlers[method]:
                            try:
                                handler(data.get("params", {}))
                            except Exception as e:
                                logger.warning(f"Event handler error: {e}")
        except Exception as e:
            if self._ws and not self._is_closed():
                logger.error(f"CDP read loop error: {e}")

    def _is_closed(self) -> bool:
        """Check if WebSocket is closed (compatible with websockets 16+)."""
        if self._ws is None:
            return True
        # websockets 16+ uses state attribute instead of closed
        if hasattr(self._ws, 'state'):
            from websockets.protocol import State
            return self._ws.state in (State.CLOSED, State.CLOSING)
        # Fallback for older versions
        if hasattr(self._ws, 'closed'):
            return self._ws.closed
        return False

    async def send_command(
        self,
        method: str,
        params: Optional[Dict] = None,
        timeout: float = 30.0,
        session_id: Optional[str] = None,
    ) -> Dict:
        """
        Send a CDP command and wait for response.

        Args:
            method: CDP method name (e.g., "Page.navigate")
            params: Command parameters
            timeout: Response timeout in seconds
            session_id: Optional session ID for target-level commands

        Returns:
            Response result dict
        """
        if self._is_closed():
            raise RuntimeError("CDP not connected")

        self._msg_id += 1
        msg_id = self._msg_id

        future = asyncio.get_event_loop().create_future()
        self._callbacks[msg_id] = future

        message = {"id": msg_id, "method": method}
        if params:
            message["params"] = params
        if session_id:
            message["sessionId"] = session_id

        await self._ws.send(json.dumps(message))

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._callbacks.pop(msg_id, None)
            raise RuntimeError(f"CDP command timed out: {method}")

    # ── High-level methods ────────────────────────────────────────

    async def navigate(self, url: str, wait_for_load: bool = True) -> Dict:
        """
        Navigate to a URL.

        Args:
            url: URL to navigate to
            wait_for_load: Wait for page load to complete

        Returns:
            Navigation result
        """
        result = await self.send_command("Page.navigate", {"url": url})

        if wait_for_load:
            await self.wait_for_load()

        return result

    async def wait_for_load(self, timeout: float = 30.0):
        """Wait for page to finish loading."""
        await self.send_command("Page.enable")

        # Use Page.loadEventFired event
        loaded = asyncio.Event()

        def on_load(params):
            loaded.set()

        self.on("Page.loadEventFired", on_load)

        try:
            await asyncio.wait_for(loaded.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Page load timed out")
        finally:
            self._event_handlers.get("Page.loadEventFired", []).remove(on_load)

    async def inject_cookies(self, cookies: List[Dict]):
        """
        Inject cookies via CDP Network.setCookies.

        Args:
            cookies: List of cookie dicts (Playwright format)
        """
        await self.send_command("Network.enable")

        # Convert to CDP format
        cdp_cookies = []
        for cookie in cookies:
            cdp_cookie = {
                "name": cookie.get("name", ""),
                "value": cookie.get("value", ""),
                "domain": cookie.get("domain", ""),
                "path": cookie.get("path", "/"),
            }

            # Optional fields
            if cookie.get("secure"):
                cdp_cookie["secure"] = True
            if cookie.get("httpOnly"):
                cdp_cookie["httpOnly"] = True
            if cookie.get("sameSite"):
                same_site = cookie["sameSite"]
                if same_site in ("Strict", "Lax", "None"):
                    cdp_cookie["sameSite"] = same_site

            expires = cookie.get("expires", 0)
            if expires and int(expires) > 0:
                exp = int(expires)
                if exp > 1262304000000:
                    exp = exp // 1000
                cdp_cookie["expires"] = exp

            cdp_cookies.append(cdp_cookie)

        await self.send_command("Network.setCookies", {"cookies": cdp_cookies})
        logger.info(f"Injected {len(cdp_cookies)} cookies via CDP")

    async def get_cookies(self) -> List[Dict]:
        """Get all cookies from the browser."""
        result = await self.send_command("Network.getCookies")
        return result.get("cookies", [])

    async def evaluate(self, expression: str) -> Any:
        """
        Evaluate JavaScript in the page context.

        Args:
            expression: JavaScript expression to evaluate

        Returns:
            Evaluation result
        """
        result = await self.send_command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        if "exceptionDetails" in result:
            raise RuntimeError(f"JS error: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")

    async def inject_stealth(self):
        """Inject comprehensive stealth script to hide automation."""
        stealth_script = get_undetectable_stealth_script()

        # Check if we're connected to a page or browser target
        # Page targets support Page.* commands, browser targets don't
        try:
            # Enable page events (only works on page targets)
            await self.send_command("Page.enable")

            # Add script to evaluate on new documents
            await self.send_command(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": stealth_script},
            )

            # Also evaluate in current page
            try:
                await self.evaluate(stealth_script)
            except Exception:
                pass  # May fail if no page loaded yet

            logger.info("Stealth script injected via CDP (page target)")

        except RuntimeError as e:
            if "wasn't found" in str(e):
                # We're connected to browser target, not page target
                # Use Target domain to inject into all pages
                logger.info("Connected to browser target, using Target domain for stealth")
                await self._inject_stealth_via_target(stealth_script)
            else:
                raise

    async def _inject_stealth_via_target(self, script: str):
        """Inject stealth script via Target domain (for browser-level connections)."""
        try:
            # Get all page targets
            import urllib.request
            req = urllib.request.Request(f"{self.cdp_url}/json/list")
            with urllib.request.urlopen(req, timeout=5) as resp:
                targets = json.loads(resp.read().decode())

            # Attach to each page target and inject
            for target in targets:
                if target.get("type") == "page":
                    target_id = target.get("id")
                    if target_id:
                        try:
                            # Attach to target
                            result = await self.send_command(
                                "Target.attachToTarget",
                                {"targetId": target_id, "flatten": True},
                            )
                            session_id = result.get("sessionId")
                            if session_id:
                                # Send Page.enable via session
                                await self.send_command(
                                    "Page.enable",
                                    session_id=session_id,
                                )
                                # Inject script via session
                                await self.send_command(
                                    "Page.addScriptToEvaluateOnNewDocument",
                                    {"source": script},
                                    session_id=session_id,
                                )
                                logger.info(f"Stealth injected into target: {target.get('title', 'untitled')}")
                        except Exception as e:
                            logger.debug(f"Failed to inject into target {target_id}: {e}")

        except Exception as e:
            logger.warning(f"Failed to inject stealth via Target domain: {e}")

    async def get_page_html(self) -> str:
        """Get current page HTML."""
        result = await self.evaluate("document.documentElement.outerHTML")
        return result or ""

    async def get_page_title(self) -> str:
        """Get current page title."""
        result = await self.evaluate("document.title")
        return result or ""

    async def get_page_url(self) -> str:
        """Get current page URL."""
        result = await self.evaluate("window.location.href")
        return result or ""

    async def screenshot(self, path: Optional[str] = None) -> bytes:
        """Take a screenshot of the current page."""
        import base64

        result = await self.send_command(
            "Page.captureScreenshot",
            {"format": "png"},
        )
        data = base64.b64decode(result.get("data", ""))

        if path:
            with open(path, "wb") as f:
                f.write(data)

        return data

    def on(self, event: str, handler: Callable):
        """Register an event handler."""
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    def off(self, event: str, handler: Callable):
        """Remove an event handler."""
        if event in self._event_handlers:
            self._event_handlers[event] = [
                h for h in self._event_handlers[event] if h != handler
            ]

    async def close(self):
        """Close CDP connection."""
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        if self._ws and not self._is_closed():
            await self._ws.close()

        # Cancel pending callbacks
        for future in self._callbacks.values():
            if not future.done():
                future.cancel()
        self._callbacks.clear()

        logger.info("CDP connection closed")


def get_undetectable_stealth_script() -> str:
    """
    Return comprehensive stealth JavaScript that makes the browser
    undetectable by anti-bot systems.

    This is the core of the undetectable browser feature.
    """
    return """
    // === UNDETECTABLE STEALTH SCRIPT ===
    // Makes system Chrome undetectable by anti-bot systems

    (function() {
        'use strict';

        // 1. Remove navigator.webdriver
        Object.defineProperty(Navigator.prototype, 'webdriver', {
            get: () => undefined,
            configurable: true
        });

        // Also override via getOwnPropertyDescriptor to fool deep checks
        const originalGetOwnPropertyDescriptor = Object.getOwnPropertyDescriptor;
        Object.getOwnPropertyDescriptor = function(obj, prop) {
            const result = originalGetOwnPropertyDescriptor.call(this, obj, prop);
            if (obj === Navigator.prototype && prop === 'webdriver') {
                return {
                    get: undefined,
                    set: undefined,
                    configurable: true,
                    enumerable: true
                };
            }
            return result;
        };

        // 2. Add window.chrome with all expected properties
        if (!window.chrome) {
            window.chrome = {};
        }
        if (!window.chrome.runtime) {
            window.chrome.runtime = {
                connect: function() {},
                sendMessage: function() {},
                onMessage: { addListener: function() {}, removeListener: function() {} },
                onConnect: { addListener: function() {}, removeListener: function() {} }
            };
        }
        if (!window.chrome.loadTimes) {
            window.chrome.loadTimes = function() {
                const now = Date.now() / 1000;
                return {
                    requestTime: now - Math.random() * 10,
                    startLoadTime: now - Math.random() * 5,
                    commitLoadTime: now - Math.random() * 3,
                    finishDocumentLoadTime: now,
                    finishLoadTime: now + 0.1,
                    firstPaintTime: now + 0.2,
                    firstPaintAfterLoadTime: 0,
                    navigationType: "Other",
                    wasFetchedViaSpdy: true,
                    wasNpnNegotiated: true,
                    npnNegotiatedProtocol: "h2",
                    wasAlternateProtocolAvailable: false,
                    connectionInfo: "h2"
                };
            };
        }
        if (!window.chrome.csi) {
            window.chrome.csi = function() {
                return {
                    onloadT: Date.now(),
                    pageT: Date.now() - Math.random() * 1000,
                    startE: Date.now() - Math.random() * 5000,
                    onloadE: Date.now()
                };
            };
        }

        // 3. Spoof navigator.plugins (Chrome has PDF viewer, etc.)
        Object.defineProperty(navigator, 'plugins', {
            get: function() {
                const plugins = [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
                ];
                plugins.length = 3;

                plugins.item = function(index) { return this[index] || null; };
                plugins.namedItem = function(name) {
                    return this.find(function(p) { return p.name === name; }) || null;
                };
                plugins.refresh = function() {};

                return plugins;
            },
            configurable: true
        });

        // 4. Spoof navigator.languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
            configurable: true
        });
        Object.defineProperty(navigator, 'language', {
            get: () => 'en-US',
            configurable: true
        });

        // 5. Spoof navigator.permissions.query for notifications
        const originalQuery = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = function(params) {
            if (params.name === 'notifications') {
                return Promise.resolve({ state: Notification.permission || 'default' });
            }
            return originalQuery(params);
        };

        // 6. Fix headless indicators
        if (window.outerWidth === 0) {
            Object.defineProperty(window, 'outerWidth', { get: () => window.innerWidth, configurable: true });
        }
        if (window.outerHeight === 0) {
            Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight + 85, configurable: true });
        }

        // 7. Spoof screen dimensions if zero
        if (screen.width === 0 || screen.height === 0) {
            Object.defineProperty(screen, 'width', { get: () => 1920, configurable: true });
            Object.defineProperty(screen, 'height', { get: () => 1080, configurable: true });
            Object.defineProperty(screen, 'availWidth', { get: () => 1920, configurable: true });
            Object.defineProperty(screen, 'availHeight', { get: () => 1040, configurable: true });
            Object.defineProperty(screen, 'colorDepth', { get: () => 24, configurable: true });
            Object.defineProperty(screen, 'pixelDepth', { get: () => 24, configurable: true });
        }

        // 8. Spoof WebGL renderer
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(param) {
            if (param === 37445) return 'Google Inc. (Intel)';
            if (param === 37446) return 'ANGLE (Intel, Mesa Intel(R) UHD Graphics 630, OpenGL 4.6)';
            return getParameter.call(this, param);
        };

        // Also handle WebGL2
        if (typeof WebGL2RenderingContext !== 'undefined') {
            const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(param) {
                if (param === 37445) return 'Google Inc. (Intel)';
                if (param === 37446) return 'ANGLE (Intel, Mesa Intel(R) UHD Graphics 630, OpenGL 4.6)';
                return getParameter2.call(this, param);
            };
        }

        // 9. Remove HeadlessChrome from user agent
        Object.defineProperty(navigator, 'userAgent', {
            get: function() {
                const ua = navigator.userAgent;
                if (ua.includes('HeadlessChrome')) {
                    return ua.replace('HeadlessChrome', 'Chrome');
                }
                return ua;
            },
            configurable: true
        });

        // 10. Spoof navigator.connection
        if (!navigator.connection) {
            Object.defineProperty(navigator, 'connection', {
                get: () => ({
                    effectiveType: '4g',
                    rtt: 50,
                    downlink: 10,
                    saveData: false
                }),
                configurable: true
            });
        }

        // 11. Delete CDC properties (Chrome DevTools Protocol artifacts)
        Object.keys(window).forEach(function(key) {
            if (key.startsWith('cdc_')) {
                delete window[key];
            }
        });

        // 12. Spoof navigator.hardwareConcurrency
        if (navigator.hardwareConcurrency === 0) {
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8,
                configurable: true
            });
        }

        // 13. Spoof navigator.deviceMemory
        if (navigator.deviceMemory === undefined) {
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8,
                configurable: true
            });
        }

        // 14. Spoof navigator.platform
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Linux x86_64',
            configurable: true
        });

        // 15. Spoof Notification.permission
        if (typeof Notification !== 'undefined') {
            Object.defineProperty(Notification, 'permission', {
                get: () => 'default',
                configurable: true
            });
        }

        // 16. Spoof navigator.mediaDevices
        if (!navigator.mediaDevices) {
            Object.defineProperty(navigator, 'mediaDevices', {
                get: () => ({
                    enumerateDevices: () => Promise.resolve([
                        { kind: 'audioinput', deviceId: 'default', label: '' },
                        { kind: 'videoinput', deviceId: 'default', label: '' }
                    ]),
                    getUserMedia: () => Promise.reject(new Error('Not implemented'))
                }),
                configurable: true
            });
        }

        // 17. Fix Function.prototype.toString for patched functions
        const originalToString = Function.prototype.toString;
        Function.prototype.toString = function() {
            if (this === navigator.permissions.query) {
                return 'function query() { [native code] }';
            }
            if (this === navigator.plugins.item) {
                return 'function item() { [native code] }';
            }
            return originalToString.call(this);
        };

        // 18. UA-CH (User-Agent Client Hints) spoofing
        if (navigator.userAgentData) {
            Object.defineProperty(navigator, 'userAgentData', {
                get: () => ({
                    brands: [
                        { brand: 'Not_A Brand', version: '8' },
                        { brand: 'Chromium', version: '120' },
                        { brand: 'Google Chrome', version: '120' }
                    ],
                    mobile: false,
                    platform: 'Linux'
                }),
                configurable: true
            });
        }

        // 19. Performance timing consistency
        if (window.performance && window.performance.timing) {
            const timing = window.performance.timing;
            if (timing.navigationStart === 0) {
                Object.defineProperty(timing, 'navigationStart', {
                    get: () => Date.now() - 1000,
                    configurable: true
                });
            }
        }

        // 20. document.hasFocus() - sometimes returns false for real users
        const originalHasFocus = document.hasFocus.bind(document);
        document.hasFocus = function() {
            // 5% chance of reporting unfocused (realistic)
            return Math.random() > 0.05 ? originalHasFocus() : false;
        };

        console.log('[Tokenade] Stealth injected successfully');
    })();
    """
