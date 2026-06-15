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

logger = logging.getLogger(__name__)


class _ForwardProxyProtocol(asyncio.Protocol):
    """Raw asyncio protocol handling HTTP proxy and CONNECT tunneling."""

    def __init__(self, proxy: "ForwardProxy"):
        self.proxy = proxy
        self.transport: Optional[asyncio.Transport] = None
        self._buffer = b""

    def connection_made(self, transport: asyncio.Transport):
        self.transport = transport

    def data_received(self, data: bytes):
        self._buffer += data
        # Check if we have a complete request
        if b"\r\n\r\n" in self._buffer:
            asyncio.ensure_future(self._process())

    async def _process(self):
        """Parse the incoming HTTP request and route it."""
        try:
            raw = self._buffer
            self._buffer = b""

            # Parse request line
            first_line = raw.split(b"\r\n", 1)[0].decode("latin-1")
            parts = first_line.split(" ", 2)
            if len(parts) < 3:
                self.transport.close()
                return

            method, target, _ = parts

            if method.upper() == "CONNECT":
                await self._handle_connect(raw, target)
            else:
                await self._handle_http(method, target, raw)
        except Exception as e:
            logger.error(f"Proxy protocol error: {e}")
            self.transport.close()

    async def _handle_connect(self, raw: bytes, target: str):
        """Handle HTTPS CONNECT tunneling."""
        self.proxy.stats["requests"] += 1

        # Parse host:port from target
        if ":" in target:
            host, port = target.rsplit(":", 1)
            port = int(port)
        else:
            host = target
            port = 443

        logger.debug(f"CONNECT tunnel to {host}:{port}")

        try:
            target_reader, target_writer = await asyncio.open_connection(host, port)
        except Exception as e:
            logger.error(f"CONNECT failed to {host}:{port}: {e}")
            self.proxy.stats["errors"] += 1
            self.transport.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            self.transport.close()
            return

        # Send 200 Connection Established
        self.transport.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")

        # Get raw socket for bidirectional piping
        sock = self.transport.get_extra_info("socket")
        if sock is None:
            target_writer.close()
            self.transport.close()
            return

        sock.setblocking(False)
        loop = asyncio.get_event_loop()

        async def pipe_client_to_target():
            try:
                while True:
                    data = await loop.sock_recv(sock, 65536)
                    if not data:
                        break
                    target_writer.write(data)
                    await target_writer.drain()
                    self.proxy.stats["bytes_sent"] += len(data)
            except Exception:
                pass
            finally:
                target_writer.close()

        async def pipe_target_to_client():
            try:
                while True:
                    data = await target_reader.read(65536)
                    if not data:
                        break
                    await loop.sock_sendall(sock, data)
                    self.proxy.stats["bytes_received"] += len(data)
            except Exception:
                pass

        try:
            await asyncio.gather(
                pipe_client_to_target(),
                pipe_target_to_client(),
                return_exceptions=True,
            )
        except Exception as e:
            logger.error(f"CONNECT tunnel error: {e}")
            self.proxy.stats["errors"] += 1
        finally:
            try:
                target_writer.close()
                await target_writer.wait_closed()
            except Exception:
                pass

    async def _handle_http(self, method: str, target: str, raw: bytes):
        """Handle regular HTTP proxy requests with cookie injection."""
        self.proxy.stats["requests"] += 1

        # Build target URL
        url = target
        if not url.startswith(("http://", "https://")):
            # Extract from raw headers
            headers = self._parse_headers(raw)
            host = headers.get("host", headers.get("Host", ""))
            url = f"http://{host}{target}"

        parsed = urlparse(url)
        if not parsed.hostname:
            self.transport.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            self.transport.close()
            return

        # Get cookies for this domain
        cookies = self.proxy._cookie_jar.get_for_request(url)

        # Parse headers from raw request
        headers = self._parse_headers(raw)
        headers.pop("Proxy-Connection", None)
        headers.pop("Proxy-Authorization", None)
        headers.pop("Proxy-Host", None)

        if cookies:
            headers["cookie"] = cookies

        # Extract body from raw bytes
        header_end = raw.find(b"\r\n\r\n")
        body = raw[header_end + 4 :] if header_end != -1 else None

        try:
            session = await self.proxy._get_session()
            async with session.request(
                method=method,
                url=url,
                headers=headers,
                data=body if method in ("POST", "PUT", "PATCH") else None,
                ssl=False,
                allow_redirects=False,
            ) as resp:
                resp_body = await resp.read()
                self.proxy.stats["bytes_received"] += len(resp_body)

                # Build response
                resp_line = f"HTTP/1.1 {resp.status} {resp.reason}\r\n"
                resp_headers = ""
                for k, v in resp.headers.items():
                    k_lower = k.lower()
                    if k_lower not in ("transfer-encoding", "content-encoding", "connection"):
                        resp_headers += f"{k}: {v}\r\n"

                response = resp_line.encode() + resp_headers.encode() + b"\r\n" + resp_body
                self.transport.write(response)
        except Exception as e:
            self.proxy.stats["errors"] += 1
            logger.error(f"HTTP proxy error: {e}")
            self.transport.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")

        self.transport.close()

    def _parse_headers(self, raw: bytes) -> Dict[str, str]:
        """Parse headers from raw HTTP request bytes."""
        header_section = raw.split(b"\r\n\r\n", 1)[0]
        lines = header_section.split(b"\r\n")[1:]  # Skip request line
        headers = {}
        for line in lines:
            if b":" in line:
                key, value = line.split(b":", 1)
                headers[key.decode("latin-1").strip().lower()] = value.decode("latin-1").strip()
        return headers

    def connection_lost(self, exc):
        pass


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
        self._server: Optional[asyncio.AbstractServer] = None
        self.stats = {"requests": 0, "bytes_sent": 0, "bytes_received": 0, "errors": 0}

    async def start(self):
        """Start the forward proxy server using raw asyncio for CONNECT support."""
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

        loop = asyncio.get_event_loop()
        self._server = await loop.create_server(
            lambda: _ForwardProxyProtocol(self),
            self.host,
            self.port,
        )

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
            if self._server:
                self._server.close()
                await self._server.wait_closed()

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
