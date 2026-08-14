"""Comprehensive tests for multi_site_proxy.py — targeting 60%+ coverage."""

import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from tokenade.core.proxy.multi_site_proxy import (
    MultiSiteProxy,
    SharedConnectionPool,
)


def _run_async(coro):
    return asyncio.run(coro)


_real_sleep = asyncio.sleep


async def _fast_sleep(_seconds):
    await _real_sleep(0)


def _make_session(name="github", domain=".github.com"):
    return {
        "version": "2.0",
        "site_name": name,
        "auth_status": "logged_in",
        "cookies": [{"name": "sid", "value": "abc", "domain": domain, "path": "/"}],
        "fingerprint": {"user_agent": "Mozilla/5.0", "platform": "Linux"},
        "tls_profile": {"browser": "chrome", "version": "120"},
    }


# ===========================================================================
# SharedConnectionPool
# ===========================================================================

class TestSharedConnectionPool:
    def test_get_session_creates_session(self):
        pool = SharedConnectionPool(max_connections=100, max_per_host=20, timeout=15)
        session = _run_async(pool.get_session())
        assert session is not None
        assert not session.closed
        assert pool._session is session
        _run_async(session.close())

    def test_get_session_reuses(self):
        pool = SharedConnectionPool()
        s1 = _run_async(pool.get_session())
        s2 = _run_async(pool.get_session())
        assert s1 is s2
        _run_async(s1.close())

    def test_get_session_recreates_after_close(self):
        pool = SharedConnectionPool()
        s1 = _run_async(pool.get_session())
        _run_async(s1.close())
        s2 = _run_async(pool.get_session())
        assert s2 is not s1
        _run_async(s2.close())

    def test_close_session(self):
        pool = SharedConnectionPool()
        s = _run_async(pool.get_session())
        assert not s.closed
        _run_async(pool.close())
        assert pool._session is None

    def test_close_no_session(self):
        pool = SharedConnectionPool()
        _run_async(pool.close())
        assert pool._session is None

    def test_close_already_closed_session(self):
        pool = SharedConnectionPool()
        s = _run_async(pool.get_session())
        _run_async(s.close())
        # When session is already closed, close() skips awaiting session.close()
        # and sets _session = None
        _run_async(pool.close())
        # After close, _session should be None because the `if` block was skipped
        # (session.closed is True) but _session is NOT set to None.
        # Actually: the code checks `if self._session and not self._session.closed`
        # If session is already closed, the if-block is skipped entirely.
        # So _session remains the closed session object.
        assert pool._session is s

    def test_stats_before_session(self):
        pool = SharedConnectionPool(max_connections=50, max_per_host=10)
        stats = pool.stats
        assert stats["active_connections"] == 0
        assert stats["max_connections"] == 50
        # max_per_host only present when session exists
        assert "max_per_host" not in stats

    def test_stats_after_session_created(self):
        pool = SharedConnectionPool(max_connections=50, max_per_host=10)
        _run_async(pool.get_session())
        stats = pool.stats
        assert "active_connections" in stats
        assert stats["max_connections"] == 50
        assert stats["max_per_host"] == 10
        _run_async(pool.close())

    def test_stores_config(self):
        pool = SharedConnectionPool(max_connections=300, max_per_host=60, timeout=45)
        assert pool._max_connections == 300
        assert pool._max_per_host == 60
        assert pool._timeout == 45


# ===========================================================================
# MultiSiteProxy — init
# ===========================================================================

class TestMultiSiteProxyInit:
    def test_creation(self):
        sessions = [_make_session("a"), _make_session("b", ".b.com")]
        proxy = MultiSiteProxy(sessions, base_port=9300, host="0.0.0.0")
        assert len(proxy.sessions) == 2
        assert proxy.base_port == 9300
        assert proxy.host == "0.0.0.0"

    def test_defaults(self):
        proxy = MultiSiteProxy([])
        assert proxy.base_port == 9222
        assert proxy.host == "127.0.0.1"
        assert proxy._proxies == []
        assert proxy._app is None

    def test_shared_pool_created(self):
        proxy = MultiSiteProxy([])
        assert isinstance(proxy._shared_pool, SharedConnectionPool)

    def test_sessions_preserved(self):
        s1 = _make_session("x")
        s2 = _make_session("y", ".y.com")
        proxy = MultiSiteProxy([s1, s2])
        assert proxy.sessions[0]["site_name"] == "x"
        assert proxy.sessions[1]["site_name"] == "y"


# ===========================================================================
# MultiSiteProxy._create_master_app
# ===========================================================================

class TestCreateMasterApp:
    def test_creates_app_with_routes(self):
        proxy = MultiSiteProxy([_make_session()])
        app = proxy._create_master_app()
        assert isinstance(app, web.Application)

    def test_routes_registered(self):
        proxy = MultiSiteProxy([_make_session()])
        app = proxy._create_master_app()
        routes = [r.resource.canonical for r in app.router.routes()]
        assert "/" in routes


# ===========================================================================
# MultiSiteProxy._handle_master_gui
# ===========================================================================

class TestHandleMasterGui:
    def test_returns_html_response(self):
        proxy = MultiSiteProxy([_make_session("site1"), _make_session("site2", ".b.com")])
        proxy._proxies = [
            {"proxy": MagicMock(), "port": 9223, "session": _make_session("site1")},
            {"proxy": MagicMock(), "port": 9224, "session": _make_session("site2", ".b.com")},
        ]
        request = make_mocked_request("GET", "/")
        resp = _run_async(proxy._handle_master_gui(request))
        assert isinstance(resp, web.Response)
        body = resp.text
        assert "site1" in body
        assert "site2" in body
        assert "Tokenade" in body

    def test_tab_structure(self):
        proxy = MultiSiteProxy([_make_session("my_site")])
        proxy._proxies = [
            {"proxy": MagicMock(), "port": 9223, "session": _make_session("my_site")},
        ]
        request = make_mocked_request("GET", "/")
        resp = _run_async(proxy._handle_master_gui(request))
        body = resp.text
        assert "tab" in body
        assert "iframe" in body
        assert "9223" in body

    def test_first_tab_active(self):
        proxy = MultiSiteProxy([_make_session("a"), _make_session("b", ".b.com")])
        proxy._proxies = [
            {"proxy": MagicMock(), "port": 9223, "session": _make_session("a")},
            {"proxy": MagicMock(), "port": 9224, "session": _make_session("b", ".b.com")},
        ]
        request = make_mocked_request("GET", "/")
        resp = _run_async(proxy._handle_master_gui(request))
        body = resp.text
        assert body.count("active") >= 1


# ===========================================================================
# MultiSiteProxy._handle_sessions_api
# ===========================================================================

class TestHandleSessionsApi:
    def test_returns_json_list(self):
        proxy = MultiSiteProxy([_make_session("github"), _make_session("gmail", ".google.com")])
        proxy._proxies = [
            {"proxy": MagicMock(), "port": 9223, "session": _make_session("github")},
            {"proxy": MagicMock(), "port": 9224, "session": _make_session("gmail", ".google.com")},
        ]
        request = make_mocked_request("GET", "/api/sessions")
        resp = _run_async(proxy._handle_sessions_api(request))
        assert resp.status == 200
        import json
        data = json.loads(resp.text)
        assert len(data) == 2
        assert data[0]["site_name"] == "github"
        assert data[1]["site_name"] == "gmail"
        assert data[0]["port"] == 9223

    def test_empty_proxies(self):
        proxy = MultiSiteProxy([])
        proxy._proxies = []
        request = make_mocked_request("GET", "/api/sessions")
        resp = _run_async(proxy._handle_sessions_api(request))
        import json
        data = json.loads(resp.text)
        assert data == []

    def test_session_with_default_site_name(self):
        proxy = MultiSiteProxy([{}])
        proxy._proxies = [
            {"proxy": MagicMock(), "port": 9223, "session": {}},
        ]
        request = make_mocked_request("GET", "/api/sessions")
        resp = _run_async(proxy._handle_sessions_api(request))
        import json
        data = json.loads(resp.text)
        assert data[0]["site_name"] == "unknown"


# ===========================================================================
# MultiSiteProxy._print_status
# ===========================================================================

class TestPrintStatus:
    def test_prints_status(self, capsys):
        proxy = MultiSiteProxy([_make_session("site1"), _make_session("site2", ".b.com")])
        proxy._proxies = [
            {"proxy": MagicMock(), "port": 9223, "session": _make_session("site1")},
            {"proxy": MagicMock(), "port": 9224, "session": _make_session("site2", ".b.com")},
        ]
        proxy._print_status()
        captured = capsys.readouterr()
        assert "site1" in captured.out
        assert "site2" in captured.out
        assert "9223" in captured.out
        assert "9224" in captured.out

    def test_prints_empty_status(self, capsys):
        proxy = MultiSiteProxy([])
        proxy._proxies = []
        proxy._print_status()
        captured = capsys.readouterr()
        assert "Sessions: 0" in captured.out


# ===========================================================================
# MultiSiteProxy.start — full lifecycle
# (CDPProxy/CDPProxyConfig are imported locally inside start())
# ===========================================================================

_real_event_cls = asyncio.Event


async def _stall_forever():
    await _real_event_cls().wait()


class TestMultiSiteProxyStart:
    @staticmethod
    def _default_runner():
        runner = MagicMock()
        runner.setup = AsyncMock()
        runner.cleanup = AsyncMock()
        return runner

    @staticmethod
    def _default_site():
        site = MagicMock()
        site.start = AsyncMock()
        return site

    @contextmanager
    def _env(self, mock_cdp, mock_runner=None, mock_site=None):
        with patch(
            "tokenade.core.proxy.multi_site_proxy.web.AppRunner",
            return_value=mock_runner or self._default_runner(),
        ):
            with patch(
                "tokenade.core.proxy.multi_site_proxy.web.TCPSite",
                return_value=mock_site or self._default_site(),
            ):
                with patch("tokenade.core.proxy.cdp_proxy.CDPProxy", return_value=mock_cdp):
                    with patch("tokenade.core.proxy.cdp_proxy.CDPProxyConfig"):
                        with patch("asyncio.sleep", new_callable=AsyncMock, side_effect=_fast_sleep):
                            yield

    def _running_proxy(self, mock_cdp):
        mock_cdp.start = AsyncMock(side_effect=_stall_forever)
        mock_cdp.stop = AsyncMock()
        return mock_cdp

    def _cancelled_event(self):
        event = MagicMock()
        event.wait = AsyncMock(side_effect=asyncio.CancelledError)
        return event

    def test_start_creates_proxies_and_app(self):
        proxy = MultiSiteProxy([_make_session("site1")], base_port=19300)
        mock_runner = MagicMock()
        mock_runner.setup = AsyncMock()
        mock_runner.cleanup = AsyncMock()
        mock_site = MagicMock()
        mock_site.start = AsyncMock()
        mock_cdp = self._running_proxy(MagicMock())

        with self._env(mock_cdp, mock_runner, mock_site):
            with patch("asyncio.Event", return_value=self._cancelled_event()):
                _run_async(proxy.start())

        assert len(proxy._proxies) == 1
        assert proxy._app is not None
        mock_cdp.stop.assert_awaited_once()
        mock_runner.cleanup.assert_awaited_once()

    def test_start_stops_each_proxy_on_exit(self):
        proxy = MultiSiteProxy(
            [_make_session("site1"), _make_session("site2", ".b.com")],
            base_port=19301,
        )
        mock_runner = MagicMock()
        mock_runner.setup = AsyncMock()
        mock_runner.cleanup = AsyncMock()
        mock_site = MagicMock()
        mock_site.start = AsyncMock()
        first = MagicMock()
        second = MagicMock()

        def _proxy_for(session, config):
            return first if session.get("site_name") == "site1" else second

        with patch("tokenade.core.proxy.cdp_proxy.CDPProxy", side_effect=_proxy_for):
            first.start = AsyncMock(side_effect=_stall_forever)
            first.stop = AsyncMock()
            second.start = AsyncMock(side_effect=_stall_forever)
            second.stop = AsyncMock()
            with patch("tokenade.core.proxy.cdp_proxy.CDPProxyConfig"):
                with patch(
                    "tokenade.core.proxy.multi_site_proxy.web.AppRunner",
                    return_value=mock_runner,
                ):
                    with patch(
                        "tokenade.core.proxy.multi_site_proxy.web.TCPSite",
                        return_value=mock_site,
                    ):
                        with patch(
                            "asyncio.sleep",
                            new_callable=AsyncMock,
                            side_effect=_fast_sleep,
                        ):
                            with patch(
                                "asyncio.Event", return_value=self._cancelled_event()
                            ):
                                _run_async(proxy.start())

        first.stop.assert_awaited_once()
        second.stop.assert_awaited_once()

    def test_child_start_failure_aborts_startup_and_stops_all(self):
        proxy = MultiSiteProxy(
            [_make_session("a"), _make_session("b", ".b.com")], base_port=19302
        )
        mock_cdp = MagicMock()
        mock_cdp.start = AsyncMock(side_effect=RuntimeError("boom"))
        mock_cdp.stop = AsyncMock()
        proxy._shared_pool.get_session = AsyncMock()
        proxy._shared_pool.close = AsyncMock()

        with self._env(mock_cdp):
            with patch("asyncio.Event", return_value=self._cancelled_event()):
                try:
                    _run_async(proxy.start())
                except RuntimeError as exc:
                    assert "failed to start" in str(exc)
                    assert "boom" in str(exc)
                else:
                    raise AssertionError("child start failure was swallowed")

        assert proxy._app is None
        assert mock_cdp.stop.await_count == 2
        proxy._shared_pool.close.assert_awaited_once()

    def test_start_keyboard_interrupt(self):
        proxy = MultiSiteProxy([_make_session("site1")], base_port=19303)
        mock_runner = MagicMock()
        mock_runner.setup = AsyncMock()
        mock_runner.cleanup = AsyncMock()
        mock_site = MagicMock()
        mock_site.start = AsyncMock()
        mock_cdp = self._running_proxy(MagicMock())
        event = MagicMock()
        event.wait = AsyncMock(side_effect=KeyboardInterrupt)

        with self._env(mock_cdp, mock_runner, mock_site):
            with patch("asyncio.Event", return_value=event):
                _run_async(proxy.start())

        mock_cdp.stop.assert_awaited_once()

    def test_start_exception_during_stop_is_swallowed(self):
        proxy = MultiSiteProxy([_make_session("site1")], base_port=19304)
        mock_cdp = self._running_proxy(MagicMock())
        mock_cdp.stop = AsyncMock(side_effect=RuntimeError("stop failed"))

        with self._env(mock_cdp):
            with patch("asyncio.Event", return_value=self._cancelled_event()):
                _run_async(proxy.start())

        mock_cdp.stop.assert_awaited_once()

    def test_ports_increment(self):
        sessions = [
            _make_session("a"),
            _make_session("b", ".b.com"),
            _make_session("c", ".c.com"),
        ]
        proxy = MultiSiteProxy(sessions, base_port=19400)
        mock_cdp = self._running_proxy(MagicMock())

        with self._env(mock_cdp):
            with patch("asyncio.Event", return_value=self._cancelled_event()):
                _run_async(proxy.start())

        assert len(proxy._proxies) == 3
        assert proxy._proxies[0]["port"] == 19401
        assert proxy._proxies[1]["port"] == 19402
        assert proxy._proxies[2]["port"] == 19403

    def test_startup_failure_closes_shared_pool(self):
        proxy = MultiSiteProxy([_make_session("site1")], base_port=19305)
        mock_session = MagicMock()
        mock_cdp = MagicMock()
        mock_cdp.start = AsyncMock()
        mock_cdp.stop = AsyncMock()
        proxy._shared_pool.get_session = AsyncMock(return_value=mock_session)
        proxy._shared_pool.close = AsyncMock()

        with self._env(mock_cdp):
            with patch(
                "asyncio.sleep",
                new_callable=AsyncMock,
                side_effect=RuntimeError("startup failed"),
            ):
                with patch("asyncio.Event", return_value=self._cancelled_event()):
                    try:
                        _run_async(proxy.start())
                    except RuntimeError as exc:
                        assert str(exc) == "startup failed"
                    else:
                        raise AssertionError("startup failure was swallowed")

        mock_cdp.stop.assert_awaited_once()
        proxy._shared_pool.close.assert_awaited_once()
