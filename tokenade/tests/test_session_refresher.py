"""Tests for session auto-refresher with WebSocket notifications and multi-browser fallback."""

import asyncio
import json
import time
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from tokenade.core.importer.session_refresher import (
    SessionRefresher,
    RefreshConfig,
    CookieExpiryInfo,
)


def _run_async(coro):
    """Run an async coroutine synchronously, handling existing event loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            def _in_new_loop():
                new_loop = asyncio.new_event_loop()
                try:
                    return new_loop.run_until_complete(coro)
                finally:
                    new_loop.close()
            future = pool.submit(_in_new_loop)
            return future.result(timeout=10)
    else:
        return asyncio.run(coro)


class TestRefreshConfig:
    def test_default_config(self):
        config = RefreshConfig()
        assert config.check_interval == 300
        assert config.expiry_warning_days == 7
        assert config.expiry_critical_days == 1
        assert config.auto_refresh is False
        assert config.source_browser is None
        assert config.source_profile is None
        assert config.domains is None
        assert config.fallback_browsers == []
        assert config.notify_ws is None

    def test_custom_config(self):
        config = RefreshConfig(
            check_interval=60,
            expiry_warning_days=3,
            expiry_critical_days=2,
            auto_refresh=True,
            source_browser="firefox",
            source_profile="default",
            domains="example.com,test.com",
            fallback_browsers=["chrome", "edge"],
        )
        assert config.check_interval == 60
        assert config.source_browser == "firefox"
        assert config.fallback_browsers == ["chrome", "edge"]


class TestCookieExpiryInfo:
    def test_dataclass_fields(self):
        info = CookieExpiryInfo(
            total_cookies=50,
            expired_count=5,
            expiring_soon_count=10,
            critical_count=2,
            next_expiry_epoch=time.time() + 3600,
            next_expiry_human="1 hours",
        )
        assert info.total_cookies == 50
        assert info.expired_count == 5
        assert info.next_expiry_human == "1 hours"


class TestSessionRefresher:
    @pytest.fixture
    def session(self):
        now = time.time()
        return {
            "version": "2.0",
            "site_name": "test_site",
            "source_device": {"browser": "firefox", "profile": "default"},
            "cookies": [
                {
                    "name": "valid_cookie",
                    "value": "abc",
                    "domain": ".example.com",
                    "path": "/",
                    "expires": int(now + 86400 * 30),
                },
                {
                    "name": "expired_cookie",
                    "value": "def",
                    "domain": ".example.com",
                    "path": "/",
                    "expires": int(now - 3600),
                },
                {
                    "name": "expiring_soon_cookie",
                    "value": "ghi",
                    "domain": ".example.com",
                    "path": "/",
                    "expires": int(now + 86400 * 3),
                },
                {
                    "name": "critical_cookie",
                    "value": "jkl",
                    "domain": ".example.com",
                    "path": "/",
                    "expires": int(now + 3600 * 12),
                },
                {
                    "name": "session_cookie",
                    "value": "mno",
                    "domain": ".example.com",
                    "path": "/",
                    "expires": 0,
                },
            ],
        }

    @pytest.fixture
    def refresher(self, session):
        return SessionRefresher(session=session)

    def test_check_expiry(self, refresher):
        info = refresher.check_expiry()
        assert info.total_cookies == 5
        assert info.expired_count == 1
        assert info.expiring_soon_count == 1
        assert info.critical_count == 1
        assert info.next_expiry_human is not None

    def test_check_expiry_empty_session(self):
        refresher = SessionRefresher(session={"cookies": []})
        info = refresher.check_expiry()
        assert info.total_cookies == 0
        assert info.expired_count == 0
        assert info.next_expiry_epoch is None

    def test_check_expiry_no_cookies_key(self):
        refresher = SessionRefresher(session={})
        info = refresher.check_expiry()
        assert info.total_cookies == 0

    def test_check_expiry_firefox_millisecond_format(self):
        now = time.time()
        session = {
            "cookies": [
                {
                    "name": "ff_cookie",
                    "value": "x",
                    "domain": ".example.com",
                    "expires": int((now + 86400) * 1000),
                },
            ],
        }
        refresher = SessionRefresher(session=session)
        info = refresher.check_expiry()
        assert info.total_cookies == 1
        assert info.expired_count == 0

    def test_get_status(self, refresher):
        status = refresher.get_status()
        assert "total_cookies" in status
        assert "expired_count" in status
        assert "auto_refresh_enabled" in status
        assert "source_browser" in status
        assert "fallback_browsers" in status
        assert "last_check" in status

    def test_update_session(self, refresher, session):
        new_session = {**session, "cookies": []}
        refresher.update_session(new_session)
        assert refresher.session == new_session
        assert refresher._last_status is None

    def test_register_unregister_ws_client(self, refresher):
        queue = refresher.register_ws_client()
        assert queue is not None
        assert len(refresher._ws_clients) == 1

        refresher.unregister_ws_client(queue)
        assert len(refresher._ws_clients) == 0

    def test_unregister_nonexistent_client(self, refresher):
        queue = asyncio.Queue()
        refresher.unregister_ws_client(queue)
        assert len(refresher._ws_clients) == 0

    def test_notify_ws_clients(self, refresher):
        async def _test():
            queue = refresher.register_ws_client()
            event = {"type": "test_event", "data": "test"}
            await refresher._notify_ws_clients(event)
            assert queue.qsize() == 1
            received = queue.get_nowait()
            assert received == event
        _run_async(_test())

    def test_notify_ws_clients_queue_full(self, refresher):
        async def _test():
            queue = refresher.register_ws_client()
            for _ in range(100):
                try:
                    queue.put_nowait({"filler": True})
                except asyncio.QueueFull:
                    break
            event = {"type": "test"}
            await refresher._notify_ws_clients(event)
        _run_async(_test())

    def test_start_stop(self, refresher):
        async def _test():
            await refresher.start()
            assert refresher._running is True
            assert refresher._task is not None
            await refresher.stop()
            assert refresher._running is False
        _run_async(_test())

    def test_start_idempotent(self, refresher):
        async def _test():
            await refresher.start()
            task1 = refresher._task
            await refresher.start()
            assert refresher._task is task1
            await refresher.stop()
        _run_async(_test())

    def test_monitor_loop_logs_expired(self, refresher, caplog):
        async def _test():
            refresher.config.check_interval = 0.01
            await refresher.start()
            await asyncio.sleep(0.1)
            await refresher.stop()
        _run_async(_test())
        assert "expired" in caplog.text.lower() or "expired" in str(caplog.records).lower()

    def test_attempt_refresh_no_config(self, session):
        async def _test():
            refresher = SessionRefresher(
                session=session,
                config=RefreshConfig(auto_refresh=True),
            )
            await refresher._attempt_refresh()
        _run_async(_test())

    def test_attempt_refresh_no_fallback_browsers(self, session):
        async def _test():
            refresher = SessionRefresher(
                session=session,
                config=RefreshConfig(
                    auto_refresh=True,
                    source_browser="firefox",
                ),
            )

            with patch(
                "tokenade.core.importer.browser_discovery.BrowserProfileDiscovery"
            ) as mock_discovery:
                mock_discovery.return_value.discover_all.return_value = {}
                await refresher._attempt_refresh()
        _run_async(_test())

    def test_attempt_refresh_success(self, session):
        async def _test():
            refresher = SessionRefresher(
                session=session,
                config=RefreshConfig(
                    auto_refresh=True,
                    source_browser="firefox",
                ),
            )

            mock_profile = MagicMock()
            mock_profile.browser = "firefox"
            mock_profile.name = "default"
            mock_profile.path = "/fake/profile"

            with patch(
                "tokenade.core.importer.browser_discovery.BrowserProfileDiscovery"
            ) as mock_discovery, patch(
                "tokenade.core.importer.cookie_extractor.CookieExtractor"
            ) as mock_extractor_cls, patch(
                "tokenade.core.importer.session_packager.SessionPackager"
            ) as mock_packager_cls:

                mock_discovery.return_value.discover_all.return_value = {
                    "firefox": [mock_profile]
                }
                mock_extractor = mock_extractor_cls.return_value
                mock_extractor.extract.return_value = [
                    {"name": "new_cookie", "value": "x", "domain": ".example.com"}
                ]

                mock_packager = mock_packager_cls.return_value
                mock_packager.package.return_value = {
                    "site_name": "test_site",
                    "cookies": [{"name": "new_cookie", "value": "x", "domain": ".example.com"}],
                }

                on_refresh = AsyncMock()
                refresher.on_refresh = on_refresh

                await refresher._attempt_refresh()

                on_refresh.assert_called_once()
                assert refresher.session["cookies"][0]["name"] == "new_cookie"
        _run_async(_test())

    def test_attempt_refresh_with_fallback(self, session):
        async def _test():
            refresher = SessionRefresher(
                session=session,
                config=RefreshConfig(
                    auto_refresh=True,
                    source_browser="firefox",
                    fallback_browsers=["chrome"],
                ),
            )

            mock_ff_profile = MagicMock()
            mock_ff_profile.browser = "firefox"
            mock_ff_profile.name = "default"
            mock_ff_profile.path = "/fake/ff"

            mock_chrome_profile = MagicMock()
            mock_chrome_profile.browser = "chrome"
            mock_chrome_profile.name = "Default"
            mock_chrome_profile.path = "/fake/chrome"

            with patch(
                "tokenade.core.importer.browser_discovery.BrowserProfileDiscovery"
            ) as mock_discovery, patch(
                "tokenade.core.importer.cookie_extractor.CookieExtractor"
            ) as mock_extractor_cls, patch(
                "tokenade.core.importer.session_packager.SessionPackager"
            ) as mock_packager_cls:

                mock_discovery.return_value.discover_all.return_value = {
                    "firefox": [mock_ff_profile],
                    "chrome": [mock_chrome_profile],
                }

                call_count = 0
                def extract_side_effect(**kwargs):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        raise Exception("Firefox locked")
                    return [{"name": "chrome_cookie", "value": "y", "domain": ".example.com"}]

                mock_extractor = mock_extractor_cls.return_value
                mock_extractor.extract.side_effect = extract_side_effect

                mock_packager = mock_packager_cls.return_value
                mock_packager.package.return_value = {
                    "site_name": "test_site",
                    "cookies": [{"name": "chrome_cookie", "value": "y", "domain": ".example.com"}],
                }

                await refresher._attempt_refresh()
                assert refresher.session["cookies"][0]["name"] == "chrome_cookie"
        _run_async(_test())

    def test_attempt_refresh_preserves_local_storage(self, session):
        async def _test():
            session["local_storage"] = {"key1": "value1"}
            refresher = SessionRefresher(
                session=session,
                config=RefreshConfig(
                    auto_refresh=True,
                    source_browser="firefox",
                ),
            )

            mock_profile = MagicMock()
            mock_profile.browser = "firefox"
            mock_profile.name = "default"
            mock_profile.path = "/fake/profile"

            with patch(
                "tokenade.core.importer.browser_discovery.BrowserProfileDiscovery"
            ) as mock_discovery, patch(
                "tokenade.core.importer.cookie_extractor.CookieExtractor"
            ) as mock_extractor_cls, patch(
                "tokenade.core.importer.session_packager.SessionPackager"
            ) as mock_packager_cls:

                mock_discovery.return_value.discover_all.return_value = {
                    "firefox": [mock_profile]
                }
                mock_extractor = mock_extractor_cls.return_value
                mock_extractor.extract.return_value = [
                    {"name": "new_cookie", "value": "x", "domain": ".example.com"}
                ]

                mock_packager = mock_packager_cls.return_value
                mock_packager.package.return_value = {
                    "site_name": "test_site",
                    "cookies": [{"name": "new_cookie", "value": "x", "domain": ".example.com"}],
                }

                await refresher._attempt_refresh()
                assert refresher.session.get("local_storage") == {"key1": "value1"}
        _run_async(_test())

    def test_attempt_refresh_filters_by_domains(self, session):
        async def _test():
            refresher = SessionRefresher(
                session=session,
                config=RefreshConfig(
                    auto_refresh=True,
                    source_browser="firefox",
                    domains="other.com",
                ),
            )

            mock_profile = MagicMock()
            mock_profile.browser = "firefox"
            mock_profile.name = "default"
            mock_profile.path = "/fake/profile"

            with patch(
                "tokenade.core.importer.browser_discovery.BrowserProfileDiscovery"
            ) as mock_discovery, patch(
                "tokenade.core.importer.cookie_extractor.CookieExtractor"
            ) as mock_extractor_cls:

                mock_discovery.return_value.discover_all.return_value = {
                    "firefox": [mock_profile]
                }
                mock_extractor = mock_extractor_cls.return_value
                mock_extractor.extract.return_value = [
                    {"name": "c1", "value": "x", "domain": ".example.com"},
                    {"name": "c2", "value": "y", "domain": ".other.com"},
                ]

                await refresher._attempt_refresh()
                assert refresher.session["cookies"][0]["name"] == "c2"
        _run_async(_test())

    def test_attempt_refresh_all_browsers_fail(self, session):
        async def _test():
            refresher = SessionRefresher(
                session=session,
                config=RefreshConfig(
                    auto_refresh=True,
                    source_browser="firefox",
                ),
            )

            queue = refresher.register_ws_client()

            mock_profile = MagicMock()
            mock_profile.browser = "firefox"
            mock_profile.name = "default"
            mock_profile.path = "/fake/profile"

            with patch(
                "tokenade.core.importer.browser_discovery.BrowserProfileDiscovery"
            ) as mock_discovery, patch(
                "tokenade.core.importer.cookie_extractor.CookieExtractor"
            ) as mock_extractor_cls:

                mock_discovery.return_value.discover_all.return_value = {
                    "firefox": [mock_profile]
                }
                mock_extractor = mock_extractor_cls.return_value
                mock_extractor.extract.side_effect = Exception("DB locked")

                await refresher._attempt_refresh()
                assert queue.qsize() == 1
                event = queue.get_nowait()
                assert event["type"] == "refresh_failed"
        _run_async(_test())

    def test_webhook_notify_on_refresh(self, session):
        async def _test():
            refresher = SessionRefresher(session=session)
            queue = refresher.register_ws_client()

            refresher.config.check_interval = 0.01
            refresher.config.auto_refresh = True
            refresher.config.source_browser = "firefox"

            mock_profile = MagicMock()
            mock_profile.browser = "firefox"
            mock_profile.name = "default"
            mock_profile.path = "/fake/profile"

            with patch(
                "tokenade.core.importer.browser_discovery.BrowserProfileDiscovery"
            ) as mock_discovery, patch(
                "tokenade.core.importer.cookie_extractor.CookieExtractor"
            ) as mock_extractor_cls, patch(
                "tokenade.core.importer.session_packager.SessionPackager"
            ) as mock_packager_cls:

                mock_discovery.return_value.discover_all.return_value = {
                    "firefox": [mock_profile]
                }
                mock_extractor = mock_extractor_cls.return_value
                mock_extractor.extract.return_value = [
                    {"name": "refreshed", "value": "r", "domain": ".example.com"}
                ]
                mock_packager = mock_packager_cls.return_value
                mock_packager.package.return_value = {
                    "site_name": "test_site",
                    "cookies": [{"name": "refreshed", "value": "r", "domain": ".example.com"}],
                }

                await refresher._attempt_refresh()
                assert queue.qsize() == 1
                event = queue.get_nowait()
                assert event["type"] == "session_refreshed"
                assert event["source_browser"] == "firefox"
        _run_async(_test())

    def test_expiry_thresholds(self):
        now = time.time()
        session = {
            "cookies": [
                {
                    "name": "c1",
                    "value": "v",
                    "domain": ".example.com",
                    "expires": int(now + 86400 * 3),
                },
            ],
        }
        config = RefreshConfig(
            expiry_warning_days=5,
            expiry_critical_days=1,
        )
        refresher = SessionRefresher(session=session, config=config)
        info = refresher.check_expiry()
        assert info.expiring_soon_count == 1
        assert info.critical_count == 0

    def test_session_cookies_excluded(self):
        session = {
            "cookies": [
                {"name": "c1", "value": "v", "domain": ".example.com", "expires": 0},
                {"name": "c2", "value": "v", "domain": ".example.com", "expires": -1},
            ],
        }
        refresher = SessionRefresher(session=session)
        info = refresher.check_expiry()
        assert info.expired_count == 0
        assert info.expiring_soon_count == 0
