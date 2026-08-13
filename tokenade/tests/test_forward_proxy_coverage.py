"""Comprehensive tests for forward_proxy.py — targeting 60%+ coverage."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from tokenade.core.proxy.forward_proxy import (
    ForwardProxy,
    _ForwardProxyProtocol,
)


def _run_async(coro):
    return asyncio.run(coro)


def _make_session():
    return {
        "version": "2.0",
        "site_name": "test",
        "auth_status": "logged_in",
        "cookies": [
            {"name": "sid", "value": "abc", "domain": ".example.com", "path": "/"},
        ],
        "fingerprint": {"user_agent": "Mozilla/5.0 TestAgent", "platform": "Linux"},
        "tls_profile": {"browser": "chrome", "version": "120"},
    }


def _make_protocol(proxy=None):
    if proxy is None:
        proxy = ForwardProxy(_make_session())
    return _ForwardProxyProtocol(proxy)


def _make_http_session(body=b"ok", headers=None):
    response = MagicMock()
    response.status = 200
    response.reason = "OK"
    response.headers = headers or {}
    response.read = AsyncMock(return_value=body)
    request_context = MagicMock()
    request_context.__aenter__ = AsyncMock(return_value=response)
    request_context.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.request.return_value = request_context
    return session


# ===========================================================================
# ForwardProxy unit tests
# ===========================================================================

class TestForwardProxyInit:
    def test_creation_custom_port_host(self):
        p = ForwardProxy(_make_session(), port=8888, host="0.0.0.0")
        assert p.port == 8888
        assert p.host == "0.0.0.0"

    def test_creation_defaults(self):
        p = ForwardProxy(_make_session())
        assert p.port == 9223
        assert p.host == "127.0.0.1"

    def test_stats_init(self):
        p = ForwardProxy(_make_session())
        assert p.stats == {"requests": 0, "bytes_sent": 0, "bytes_received": 0, "errors": 0}

    def test_internal_fields_none(self):
        p = ForwardProxy(_make_session())
        assert p._cookie_jar is None
        assert p._fingerprint is None
        assert p._tls_matcher is None
        assert p._http_session is None
        assert p._server is None

    def test_session_stored(self):
        s = _make_session()
        p = ForwardProxy(s)
        assert p.session is s
        assert p.session["site_name"] == "test"


# ===========================================================================
# _ForwardProxyProtocol — data_received / _process
# ===========================================================================

class TestProtocolDataReceived:
    def test_buffering_incomplete(self):
        proto = _make_protocol()
        proto.transport = MagicMock()
        proto.data_received(b"GET / HTTP/1.1\r\nHost: ex")
        assert proto._buffer == b"GET / HTTP/1.1\r\nHost: ex"
        proto.transport.close.assert_not_called()

    def test_complete_triggers_process(self):
        proto = _make_protocol()
        proto.transport = MagicMock()
        with patch("asyncio.ensure_future") as ef:
            proto.data_received(b"GET / HTTP/1.1\r\nHost: ex\r\n\r\n")
            ef.assert_called_once()
            ef.call_args.args[0].close()


class TestProtocolProcess:
    def test_invalid_request_line_too_few_parts(self):
        proto = _make_protocol()
        proto.transport = MagicMock()
        proto._buffer = b"BAD\r\n\r\n"
        _run_async(proto._process())
        proto.transport.close.assert_called_once()

    def test_connect_method(self):
        proto = _make_protocol()
        proto.transport = MagicMock()
        proto._buffer = b"CONNECT example.com:443 HTTP/1.1\r\n\r\n"
        with patch.object(proto, "_handle_connect", new_callable=AsyncMock) as hc:
            _run_async(proto._process())
            hc.assert_awaited_once()

    def test_http_method(self):
        proto = _make_protocol()
        proto.transport = MagicMock()
        proto._buffer = b"GET http://example.com/ HTTP/1.1\r\n\r\n"
        with patch.object(proto, "_handle_http", new_callable=AsyncMock) as hh:
            _run_async(proto._process())
            hh.assert_awaited_once_with(
                "GET", "http://example.com/", b"GET http://example.com/ HTTP/1.1\r\n\r\n"
            )

    def test_process_exception_closes_transport(self):
        proto = _make_protocol()
        proto.transport = MagicMock()
        proto._buffer = b"INVALID\r\n\r\n"
        with patch("asyncio.ensure_future"):
            _run_async(proto._process())
        proto.transport.close.assert_called()


# ===========================================================================
# _ForwardProxyProtocol — _handle_connect
# ===========================================================================

class TestHandleConnect:
    def test_connect_success(self):
        proto = _make_protocol()
        proto.transport = MagicMock()

        mock_target_reader = AsyncMock()
        mock_target_reader.read = AsyncMock(return_value=b"")
        mock_target_writer = MagicMock()
        mock_target_writer.write = MagicMock()
        mock_target_writer.drain = AsyncMock()
        mock_target_writer.close = MagicMock()
        mock_target_writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", new_callable=AsyncMock,
                   return_value=(mock_target_reader, mock_target_writer)):
            with patch("asyncio.StreamReader"):
                with patch("asyncio.StreamReaderProtocol"):
                    with patch("asyncio.get_event_loop"):
                        async def consume_gather(*coroutines, **kwargs):
                            for coroutine in coroutines:
                                await coroutine
                            return [None, None]

                        with patch("asyncio.gather", new=consume_gather):
                            _run_async(proto._handle_connect(b"", "example.com:443"))

        assert proto.proxy.stats["requests"] == 1

    def test_connect_without_port_defaults_443(self):
        proto = _make_protocol()
        proto.transport = MagicMock()

        error = OSError("Connection refused")
        with patch("asyncio.open_connection", new_callable=AsyncMock, side_effect=error):
            _run_async(proto._handle_connect(b"", "example.com"))

        written = proto.transport.write.call_args[0][0]
        assert b"502" in written
        assert proto.proxy.stats["errors"] == 1

    def test_connect_dns_failure(self):
        proto = _make_protocol()
        proto.transport = MagicMock()

        error = OSError("Name or service not known")
        with patch("asyncio.open_connection", new_callable=AsyncMock, side_effect=error):
            _run_async(proto._handle_connect(b"", "badhost.example.com:443"))

        written = proto.transport.write.call_args[0][0]
        assert b"502" in written
        assert proto.proxy.stats["errors"] == 1

    def test_connect_timeout_error(self):
        proto = _make_protocol()
        proto.transport = MagicMock()

        error = OSError("Connection timed out")
        with patch("asyncio.open_connection", new_callable=AsyncMock, side_effect=error):
            _run_async(proto._handle_connect(b"", "slow.host:443"))

        assert b"502" in proto.transport.write.call_args[0][0]
        assert proto.proxy.stats["errors"] == 1

    def test_connect_network_unreachable(self):
        proto = _make_protocol()
        proto.transport = MagicMock()

        error = OSError("Network is unreachable")
        with patch("asyncio.open_connection", new_callable=AsyncMock, side_effect=error):
            _run_async(proto._handle_connect(b"", "unreachable.host:443"))

        assert b"502" in proto.transport.write.call_args[0][0]

    def test_connect_connection_refused(self):
        proto = _make_protocol()
        proto.transport = MagicMock()

        error = OSError("Connection refused")
        with patch("asyncio.open_connection", new_callable=AsyncMock, side_effect=error):
            _run_async(proto._handle_connect(b"", "refused.host:443"))

        assert b"502" in proto.transport.write.call_args[0][0]

    def test_connect_tunnel_error_in_gather(self):
        proto = _make_protocol()
        proto.transport = MagicMock()

        mock_target_reader = AsyncMock()
        mock_target_writer = MagicMock()
        mock_target_writer.close = MagicMock()
        mock_target_writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", new_callable=AsyncMock,
                   return_value=(mock_target_reader, mock_target_writer)):
            with patch("asyncio.StreamReader"):
                with patch("asyncio.StreamReaderProtocol"):
                    with patch("asyncio.get_event_loop"):
                        async def failing_gather(*coroutines, **kwargs):
                            for coroutine in coroutines:
                                coroutine.close()
                            raise OSError("gather failed")

                        with patch("asyncio.gather", new=failing_gather):
                            _run_async(proto._handle_connect(b"", "example.com:443"))

        assert proto.proxy.stats["errors"] >= 1

    def test_connect_tunnel_piping(self):
        proto = _make_protocol()
        proto.transport = MagicMock()

        mock_target_reader = AsyncMock()
        mock_target_reader.read = AsyncMock(side_effect=[b"data-to-client", b""])

        mock_target_writer = MagicMock()
        mock_target_writer.write = MagicMock()
        mock_target_writer.drain = AsyncMock()
        mock_target_writer.close = MagicMock()
        mock_target_writer.wait_closed = AsyncMock()

        mock_client_reader = AsyncMock()
        mock_client_reader.read = AsyncMock(side_effect=[b"data-to-target", b""])

        with patch("asyncio.open_connection", new_callable=AsyncMock,
                   return_value=(mock_target_reader, mock_target_writer)):
            with patch("asyncio.StreamReader", return_value=mock_client_reader):
                with patch("asyncio.StreamReaderProtocol"):
                    with patch("asyncio.get_event_loop"):
                        async def mock_gather(*args, **kwargs):
                            for coro in args:
                                if asyncio.iscoroutine(coro):
                                    try:
                                        await coro
                                    except Exception:
                                        pass
                            return [None, None]

                        with patch("asyncio.gather", side_effect=mock_gather):
                            _run_async(proto._handle_connect(b"", "example.com:443"))

        assert proto.proxy.stats["bytes_sent"] == len(b"data-to-target")
        assert proto.proxy.stats["bytes_received"] == len(b"data-to-client")

    def test_connect_tunnel_pipe_exception_is_swallowed(self):
        proto = _make_protocol()
        proto.transport = MagicMock()

        mock_target_reader = AsyncMock()
        mock_target_reader.read = AsyncMock(side_effect=OSError("pipe broken"))

        mock_target_writer = MagicMock()
        mock_target_writer.close = MagicMock()
        mock_target_writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", new_callable=AsyncMock,
                   return_value=(mock_target_reader, mock_target_writer)):
            with patch("asyncio.StreamReader"):
                with patch("asyncio.StreamReaderProtocol"):
                    with patch("asyncio.get_event_loop"):
                        async def mock_gather(*args, **kwargs):
                            for coro in args:
                                if asyncio.iscoroutine(coro):
                                    try:
                                        await coro
                                    except Exception:
                                        pass
                            return [None, None]

                        with patch("asyncio.gather", side_effect=mock_gather):
                            _run_async(proto._handle_connect(b"", "example.com:443"))


# ===========================================================================
# _ForwardProxyProtocol — _handle_http
# ===========================================================================

class TestHandleHttp:
    def test_http_request_full_url(self):
        proto = _make_protocol()
        proto.transport = MagicMock()
        raw = (
            b"GET http://example.com/page HTTP/1.1\r\n"
            b"Host: example.com\r\n"
            b"Proxy-Connection: keep-alive\r\n"
            b"\r\n"
        )
        mock_session = _make_http_session(
            body=b"<html>OK</html>", headers={"Content-Type": "text/html"}
        )

        with patch.object(proto.proxy, "_get_session", new_callable=AsyncMock, return_value=mock_session):
            _run_async(proto._handle_http("GET", "http://example.com/page", raw))

        assert proto.proxy.stats["requests"] == 1
        proto.transport.write.assert_called()
        proto.transport.close.assert_called()

    def test_http_request_no_hostname_returns_400(self):
        proto = _make_protocol()
        proto.transport = MagicMock()
        raw = b"GET / HTTP/1.1\r\n\r\n"
        with patch.object(proto, "_parse_headers", return_value={}):
            _run_async(proto._handle_http("GET", "/", raw))
        written = proto.transport.write.call_args[0][0]
        assert b"400" in written
        proto.transport.close.assert_called()

    def test_http_request_cookie_injection(self):
        proto = _make_protocol()
        proto.transport = MagicMock()
        raw = b"GET http://example.com/ HTTP/1.1\r\nHost: example.com\r\n\r\n"

        mock_jar = MagicMock()
        mock_jar.get_for_request = MagicMock(return_value="sid=abc")
        proto.proxy._cookie_jar = mock_jar

        mock_session = _make_http_session()

        with patch.object(proto.proxy, "_get_session", new_callable=AsyncMock, return_value=mock_session):
            _run_async(proto._handle_http("GET", "http://example.com/", raw))

        call_kwargs = mock_session.request.call_args
        assert call_kwargs[1]["headers"].get("cookie") == "sid=abc"

    def test_http_request_body_for_post(self):
        proto = _make_protocol()
        proto.transport = MagicMock()
        raw = (
            b"POST http://example.com/submit HTTP/1.1\r\n"
            b"Host: example.com\r\n"
            b"Content-Type: application/x-www-form-urlencoded\r\n"
            b"\r\n"
            b"key=value"
        )

        mock_session = _make_http_session()

        with patch.object(proto.proxy, "_get_session", new_callable=AsyncMock, return_value=mock_session):
            _run_async(proto._handle_http("POST", "http://example.com/submit", raw))

        call_kwargs = mock_session.request.call_args
        assert call_kwargs[1]["data"] == b"key=value"

    def test_http_request_filters_transfer_encoding(self):
        proto = _make_protocol()
        proto.transport = MagicMock()
        raw = b"GET http://example.com/ HTTP/1.1\r\n\r\n"

        mock_session = _make_http_session(body=b"<html></html>", headers={
            "Transfer-Encoding": "chunked",
            "Content-Encoding": "gzip",
            "Connection": "close",
            "Content-Type": "text/html",
        })

        with patch.object(proto.proxy, "_get_session", new_callable=AsyncMock, return_value=mock_session):
            _run_async(proto._handle_http("GET", "http://example.com/", raw))

        written = proto.transport.write.call_args[0][0].decode("latin-1")
        assert "Transfer-Encoding" not in written.split("\r\n\r\n")[1]
        assert "Content-Encoding" not in written.split("\r\n\r\n")[1]
        assert "Connection" not in written.split("\r\n\r\n")[1]

    def test_http_request_exception_returns_502(self):
        proto = _make_protocol()
        proto.transport = MagicMock()
        raw = b"GET http://example.com/ HTTP/1.1\r\n\r\n"

        with patch.object(proto.proxy, "_get_session", new_callable=AsyncMock, side_effect=OSError("DNS failed")):
            _run_async(proto._handle_http("GET", "http://example.com/", raw))

        written = proto.transport.write.call_args[0][0]
        assert b"502" in written
        assert proto.proxy.stats["errors"] == 1

    def test_http_request_dns_error_hint(self):
        proto = _make_protocol()
        proto.transport = MagicMock()
        raw = b"GET http://bad.host/ HTTP/1.1\r\n\r\n"

        with patch.object(proto.proxy, "_get_session", new_callable=AsyncMock,
                          side_effect=OSError("Name or service not known")):
            _run_async(proto._handle_http("GET", "http://bad.host/", raw))

        written = proto.transport.write.call_args[0][0]
        assert b"502" in written

    def test_http_request_connection_refused_hint(self):
        proto = _make_protocol()
        proto.transport = MagicMock()
        raw = b"GET http://closed.host/ HTTP/1.1\r\n\r\n"

        with patch.object(proto.proxy, "_get_session", new_callable=AsyncMock,
                          side_effect=OSError("Connection refused")):
            _run_async(proto._handle_http("GET", "http://closed.host/", raw))

        assert b"502" in proto.transport.write.call_args[0][0]

    def test_http_request_timeout_hint(self):
        proto = _make_protocol()
        proto.transport = MagicMock()
        raw = b"GET http://slow.host/ HTTP/1.1\r\n\r\n"

        with patch.object(proto.proxy, "_get_session", new_callable=AsyncMock,
                          side_effect=OSError("timed out")):
            _run_async(proto._handle_http("GET", "http://slow.host/", raw))

        assert b"502" in proto.transport.write.call_args[0][0]

    def test_http_request_relative_url_builds_from_host(self):
        proto = _make_protocol()
        proto.transport = MagicMock()
        raw = (
            b"GET /path?q=1 HTTP/1.1\r\n"
            b"Host: example.com\r\n"
            b"\r\n"
        )

        mock_session = _make_http_session()

        with patch.object(proto.proxy, "_get_session", new_callable=AsyncMock, return_value=mock_session):
            _run_async(proto._handle_http("GET", "/path?q=1", raw))

        call_kwargs = mock_session.request.call_args
        assert call_kwargs[1]["url"] == "http://example.com/path?q=1"

    def test_http_request_no_body_for_get(self):
        proto = _make_protocol()
        proto.transport = MagicMock()
        raw = b"GET http://example.com/ HTTP/1.1\r\n\r\n"

        mock_session = _make_http_session()

        with patch.object(proto.proxy, "_get_session", new_callable=AsyncMock, return_value=mock_session):
            _run_async(proto._handle_http("GET", "http://example.com/", raw))

        call_kwargs = mock_session.request.call_args
        assert call_kwargs[1]["data"] is None

    def test_http_request_removes_proxy_connection(self):
        proto = _make_protocol()
        proto.transport = MagicMock()
        raw = (
            b"GET http://example.com/ HTTP/1.1\r\n"
            b"Proxy-Connection: keep-alive\r\n"
            b"\r\n"
        )

        mock_session = _make_http_session()

        with patch.object(proto.proxy, "_get_session", new_callable=AsyncMock, return_value=mock_session):
            _run_async(proto._handle_http("GET", "http://example.com/", raw))

        call_kwargs = mock_session.request.call_args
        headers = call_kwargs[1]["headers"]
        assert "proxy-connection" not in headers


# ===========================================================================
# _ForwardProxyProtocol — _parse_headers
# ===========================================================================

class TestParseHeaders:
    def test_parse_standard_headers(self):
        proto = _make_protocol()
        raw = (
            b"GET / HTTP/1.1\r\n"
            b"Host: example.com\r\n"
            b"Accept: text/html\r\n"
            b"X-Custom: value\r\n"
            b"\r\n"
        )
        headers = proto._parse_headers(raw)
        assert headers["host"] == "example.com"
        assert headers["accept"] == "text/html"
        assert headers["x-custom"] == "value"

    def test_parse_empty_headers(self):
        proto = _make_protocol()
        raw = b"GET / HTTP/1.1\r\n\r\n"
        headers = proto._parse_headers(raw)
        assert headers == {}

    def test_parse_header_with_colon_in_value(self):
        proto = _make_protocol()
        raw = b"GET / HTTP/1.1\r\nHost: example.com:8080\r\n\r\n"
        headers = proto._parse_headers(raw)
        assert headers["host"] == "example.com:8080"

    def test_parse_lines_without_colon_skipped(self):
        proto = _make_protocol()
        raw = b"GET / HTTP/1.1\r\nno-colon-here\r\nHost: x\r\n\r\n"
        headers = proto._parse_headers(raw)
        assert "host" in headers
        assert len(headers) == 1


# ===========================================================================
# _ForwardProxyProtocol — connection_made / connection_lost
# ===========================================================================

class TestProtocolConnectionLifecycle:
    def test_connection_made_stores_transport(self):
        proto = _make_protocol()
        transport = MagicMock()
        proto.connection_made(transport)
        assert proto.transport is transport

    def test_connection_lost_is_noop(self):
        proto = _make_protocol()
        proto.connection_lost(None)
        proto.connection_lost(Exception("test"))


# ===========================================================================
# ForwardProxy._get_session
# ===========================================================================

class TestGetSession:
    def test_creates_session_lazily(self):
        proxy = ForwardProxy(_make_session())
        session = _run_async(proxy._get_session())
        assert session is not None
        assert proxy._http_session is session
        _run_async(session.close())

    def test_reuses_existing_session(self):
        proxy = ForwardProxy(_make_session())
        s1 = _run_async(proxy._get_session())
        s2 = _run_async(proxy._get_session())
        assert s1 is s2
        _run_async(s1.close())

    def test_creates_new_if_closed(self):
        proxy = ForwardProxy(_make_session())
        s1 = _run_async(proxy._get_session())
        _run_async(s1.close())
        s2 = _run_async(proxy._get_session())
        assert s2 is not s1
        assert not s2.closed
        _run_async(s2.close())


# ===========================================================================
# ForwardProxy.start — startup/shutdown
# ===========================================================================

class TestForwardProxyStart:
    def test_start_initializes_jar_and_fingerprint(self):
        proxy = ForwardProxy(_make_session(), port=19999)
        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = AsyncMock()
            mock_server = MagicMock()
            mock_server.wait_closed = AsyncMock()
            mock_loop.create_server = AsyncMock(return_value=mock_server)
            mock_get_loop.return_value = mock_loop

            with patch("asyncio.Event") as mock_event_cls:
                mock_event = MagicMock()
                mock_event.wait = AsyncMock(side_effect=asyncio.CancelledError)
                mock_event_cls.return_value = mock_event

                _run_async(proxy.start())

        assert proxy._cookie_jar is not None
        assert proxy._fingerprint is not None
        assert proxy._tls_matcher is not None
        assert proxy._server is mock_server

    def test_start_closes_session_on_exit(self):
        proxy = ForwardProxy(_make_session(), port=19998)
        mock_session = AsyncMock()
        mock_session.closed = False
        proxy._http_session = mock_session

        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = AsyncMock()
            mock_server = MagicMock()
            mock_server.wait_closed = AsyncMock()
            mock_loop.create_server = AsyncMock(return_value=mock_server)
            mock_get_loop.return_value = mock_loop

            with patch("asyncio.Event") as mock_event_cls:
                mock_event = MagicMock()
                mock_event.wait = AsyncMock(side_effect=asyncio.CancelledError)
                mock_event_cls.return_value = mock_event

                _run_async(proxy.start())

        mock_session.close.assert_called_once()

    def test_start_closes_server_on_exit(self):
        proxy = ForwardProxy(_make_session(), port=19997)

        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = AsyncMock()
            mock_server = MagicMock()
            mock_server.wait_closed = AsyncMock()
            mock_loop.create_server = AsyncMock(return_value=mock_server)
            mock_get_loop.return_value = mock_loop

            with patch("asyncio.Event") as mock_event_cls:
                mock_event = MagicMock()
                mock_event.wait = AsyncMock(side_effect=asyncio.CancelledError)
                mock_event_cls.return_value = mock_event

                _run_async(proxy.start())

        mock_server.close.assert_called_once()

    def test_start_keyboard_interrupt_exits_cleanly(self):
        proxy = ForwardProxy(_make_session(), port=19996)

        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = AsyncMock()
            mock_server = MagicMock()
            mock_server.wait_closed = AsyncMock()
            mock_loop.create_server = AsyncMock(return_value=mock_server)
            mock_get_loop.return_value = mock_loop

            with patch("asyncio.Event") as mock_event_cls:
                mock_event = MagicMock()
                mock_event.wait = AsyncMock(side_effect=KeyboardInterrupt)
                mock_event_cls.return_value = mock_event

                _run_async(proxy.start())

        mock_server.close.assert_called_once()

    def test_start_no_session_close_when_none(self):
        proxy = ForwardProxy(_make_session(), port=19995)
        proxy._http_session = None

        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = AsyncMock()
            mock_server = MagicMock()
            mock_server.wait_closed = AsyncMock()
            mock_loop.create_server = AsyncMock(return_value=mock_server)
            mock_get_loop.return_value = mock_loop

            with patch("asyncio.Event") as mock_event_cls:
                mock_event = MagicMock()
                mock_event.wait = AsyncMock(side_effect=asyncio.CancelledError)
                mock_event_cls.return_value = mock_event

                _run_async(proxy.start())
