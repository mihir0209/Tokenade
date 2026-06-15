"""
HTTP Forward Proxy Mode - Use Tokenade as HTTP_PROXY.

Configure browser: HTTP_PROXY=http://127.0.0.1:9223
All browser traffic goes through with donor cookies injected.

Supports:
- HTTP requests (GET, POST, etc.) with cookie injection
- HTTPS CONNECT tunneling
- Cookie injection per-site
"""

import asyncio
import logging
import time
from typing import Optional, Dict
from urllib.parse import urlparse

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)


class ForwardProxy:
    """HTTP forward proxy that forwards requests with donor fingerprint."""

    def __init__(self, session_package: Dict, port: int = 9223, host: str = "127.0.0.1"):
        self.session = session_package
        self.port = port
        self.host = host
        self._cookie_jar = None
        self._fingerprint = None
        self._tls_matcher = None
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._session_lock = asyncio.Lock()
        self.stats = {"requests": 0, "bytes_sent": 0, "bytes_received": 0, "errors": 0}

    async def start(self):
        """Start the forward proxy server."""
        from tokenade.core.runtime.engine import CookieJar, FingerprintMatcher
        from tokenade.core.runtime.tls_matcher import create_tls_matcher

        self._cookie_jar = CookieJar()
        self._cookie_jar.add_cookies(self.session.get("cookies", []))
        self._fingerprint = FingerprintMatcher(self.session.get("fingerprint"))

        tls_profile = self.session.get("tls_profile", {})
        self._tls_matcher = create_tls_matcher(
            browser=tls_profile.get("browser", "chrome"),
            version=tls_profile.get("version", "120"),
            impersonate=tls_profile.get("impersonate"),
        )

        app = web.Application()
        app.router.add_route("*", "/{path:.*}", self._handle_request)
        app.router.add_route("*", "", self._handle_request)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()

        logger.info(f"Forward proxy listening on {self.host}:{self.port}")
        print(f"\n🔒 Forward proxy ready on {self.host}:{self.port}")
        print(f"   Configure browser: HTTP_PROXY=http://{self.host}:{self.port}")
        print(f"   Or: export http_proxy=http://{self.host}:{self.port}")

        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            if self._http_session and not self._http_session.closed:
                await self._http_session.close()
            await runner.cleanup()

    async def _handle_request(self, request: web.Request) -> web.Response:
        """Handle proxied HTTP requests (including CONNECT tunneling)."""
        self.stats["requests"] += 1

        # Handle CONNECT method for HTTPS tunneling
        if request.method == "CONNECT":
            return await self._handle_connect(request)

        # Build target URL
        url = request.path_qs
        if not url.startswith(("http://", "https://")):
            # Regular proxy request: path contains the full URL
            url = f"http://{request.headers.get('Host', request.host)}{request.path_qs}"

        parsed = urlparse(url)
        if not parsed.hostname:
            return web.Response(text="Invalid URL", status=400)

        # Get cookies for this domain
        cookies = self._cookie_jar.get_for_request(url)

        # Build headers
        headers = dict(request.headers)
        headers.pop("Proxy-Connection", None)
        headers.pop("Proxy-Authorization", None)

        if cookies:
            headers["cookie"] = cookies

        # Read body
        body = await request.read() if request.method in ("POST", "PUT", "PATCH") else None

        try:
            async with self._get_session() as session:
                async with session.request(
                    method=request.method,
                    url=url,
                    headers=headers,
                    data=body,
                    ssl=False,
                    allow_redirects=False,
                ) as resp:
                    resp_body = await resp.read()
                    self.stats["bytes_received"] += len(resp_body)

                    # Filter response headers
                    resp_headers = dict(resp.headers)
                    resp_headers.pop("Transfer-Encoding", None)
                    resp_headers.pop("Content-Encoding", None)
                    resp_headers.pop("Connection", None)

                    return web.Response(
                        status=resp.status,
                        headers=resp_headers,
                        body=resp_body,
                    )
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Forward proxy error: {e}")
            return web.Response(text="Bad Gateway", status=502)

    async def _handle_connect(self, request: web.Request) -> web.Response:
        """Handle HTTPS CONNECT tunneling.

        When a browser sends CONNECT proxy.example.com:443, we:
        1. Open a TCP connection to the target host:port
        2. Send "200 Connection Established" back to the client
        3. Pipe data bidirectionally between client and target
        """
        # Parse target from Host header (host:port format)
        host_header = request.headers.get("Host", "")
        if ":" in host_header:
            target_host, target_port = host_header.rsplit(":", 1)
            target_port = int(target_port)
        else:
            target_host = host_header
            target_port = 443

        if not target_host:
            return web.Response(text="Missing target host", status=400)

        logger.debug(f"CONNECT tunnel to {target_host}:{target_port}")

        try:
            transport = request.transport
            if transport is None:
                return web.Response(text="No transport available", status=500)

            # Open TCP connection to target
            target_reader, target_writer = await asyncio.open_connection(
                target_host, target_port
            )
        except Exception as e:
            logger.error(f"CONNECT failed to {target_host}:{target_port}: {e}")
            self.stats["errors"] += 1
            return web.Response(text="Connection failed", status=502)

        try:
            # Send 200 Connection Established to client
            transport.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")

            # Get the raw socket from the transport for bidirectional piping
            # asyncio transports wrap a socket; we can get it via _sock or _protocol
            loop = asyncio.get_event_loop()
            sock = None

            # Try multiple ways to get the raw socket
            if hasattr(transport, '_sock') and transport._sock:
                sock = transport._sock
            elif hasattr(transport, 'get_extra_info'):
                sock = transport.get_extra_info('socket')

            if sock is None:
                logger.error("Could not get raw socket from transport")
                target_writer.close()
                return web.Response(text="Tunnel setup failed", status=500)

            # Set non-blocking for async reads
            sock.setblocking(False)

            async def pipe_client_to_target():
                """Read from client socket, write to target."""
                try:
                    while True:
                        data = await loop.sock_recv(sock, 65536)
                        if not data:
                            break
                        target_writer.write(data)
                        await target_writer.drain()
                        self.stats["bytes_sent"] += len(data)
                except Exception:
                    pass
                finally:
                    target_writer.close()

            async def pipe_target_to_client():
                """Read from target, write to client socket."""
                try:
                    while True:
                        data = await target_reader.read(65536)
                        if not data:
                            break
                        await loop.sock_sendall(sock, data)
                        self.stats["bytes_received"] += len(data)
                except Exception:
                    pass

            await asyncio.gather(
                pipe_client_to_target(),
                pipe_target_to_client(),
                return_exceptions=True,
            )

        except Exception as e:
            logger.error(f"CONNECT tunnel error: {e}")
            self.stats["errors"] += 1
        finally:
            target_writer.close()
            try:
                await target_writer.wait_closed()
            except Exception:
                pass

        return web.Response()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with thread-safe init."""
        async with self._session_lock:
            if self._http_session is None or self._http_session.closed:
                connector = aiohttp.TCPConnector(
                    ssl=False,
                    limit=100,
                    limit_per_host=30,
                    enable_cleanup_closed=True,
                )
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                self._http_session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout,
                    auto_decompress=False,
                )
            return self._http_session
