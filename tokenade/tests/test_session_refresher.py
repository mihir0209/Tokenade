"""Tests for session auto-refresher with WebSocket notifications and multi-browser fallback."""

import asyncio
import time
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from tokenade.core.importer.session_refresher import (
    SessionRefresher,
    RefreshConfig,
    CookieExpiryInfo,
)


def _run_async(coro):
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class TestRefreshConfig(unittest.TestCase):
    def test_default_config(self):
        config = RefreshConfig()
        self.assertEqual(config.check_interval, 300)
        self.assertEqual(config.expiry_warning_days, 7)
        self.assertEqual(config.expiry_critical_days, 1)
        self.assertFalse(config.auto_refresh)
        self.assertIsNone(config.source_browser)
        self.assertIsNone(config.source_profile)
        self.assertIsNone(config.domains)
        self.assertEqual(config.fallback_browsers, [])
        self.assertIsNone(config.notify_ws)

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
        self.assertEqual(config.check_interval, 60)
        self.assertEqual(config.source_browser, "firefox")
        self.assertEqual(config.fallback_browsers, ["chrome", "edge"])


class TestCookieExpiryInfo(unittest.TestCase):
    def test_dataclass_fields(self):
        info = CookieExpiryInfo(
            total_cookies=50,
            expired_count=5,
            expiring_soon_count=10,
            critical_count=2,
            next_expiry_epoch=time.time() + 3600,
            next_expiry_human="1 hours",
        )
        self.assertEqual(info.total_cookies, 50)
        self.assertEqual(info.expired_count, 5)
        self.assertEqual(info.next_expiry_human, "1 hours")


class TestSessionRefresher(unittest.TestCase):
    def setUp(self):
        now = time.time()
        self.session = {
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
        self.refresher = SessionRefresher(session=self.session)

    def test_check_expiry(self):
        info = self.refresher.check_expiry()
        self.assertEqual(info.total_cookies, 5)
        self.assertEqual(info.expired_count, 1)
        self.assertEqual(info.expiring_soon_count, 1)
        self.assertEqual(info.critical_count, 1)
        self.assertIsNotNone(info.next_expiry_human)

    def test_check_expiry_empty_session(self):
        refresher = SessionRefresher(session={"cookies": []})
        info = refresher.check_expiry()
        self.assertEqual(info.total_cookies, 0)
        self.assertEqual(info.expired_count, 0)
        self.assertIsNone(info.next_expiry_epoch)

    def test_check_expiry_no_cookies_key(self):
        refresher = SessionRefresher(session={})
        info = refresher.check_expiry()
        self.assertEqual(info.total_cookies, 0)

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
        self.assertEqual(info.total_cookies, 1)
        self.assertEqual(info.expired_count, 0)

    def test_get_status(self):
        status = self.refresher.get_status()
        self.assertIn("total_cookies", status)
        self.assertIn("expired_count", status)
        self.assertIn("auto_refresh_enabled", status)
        self.assertIn("source_browser", status)
        self.assertIn("fallback_browsers", status)
        self.assertIn("last_check", status)

    def test_update_session(self):
        new_session = {**self.session, "cookies": []}
        self.refresher.update_session(new_session)
        self.assertEqual(self.refresher.session, new_session)
        self.assertIsNone(self.refresher._last_status)

    def test_register_unregister_ws_client(self):
        queue = self.refresher.register_ws_client()
        self.assertIsNotNone(queue)
        self.assertEqual(len(self.refresher._ws_clients), 1)

        self.refresher.unregister_ws_client(queue)
        self.assertEqual(len(self.refresher._ws_clients), 0)

    def test_unregister_nonexistent_client(self):
        queue = asyncio.Queue()
        self.refresher.unregister_ws_client(queue)
        self.assertEqual(len(self.refresher._ws_clients), 0)

    def test_notify_ws_clients(self):
        async def _test():
            queue = self.refresher.register_ws_client()
            event = {"type": "test_event", "data": "test"}
            await self.refresher._notify_ws_clients(event)
            self.assertEqual(queue.qsize(), 1)
            received = queue.get_nowait()
            self.assertEqual(received, event)
        _run_async(_test())

    def test_notify_ws_clients_queue_full(self):
        async def _test():
            queue = self.refresher.register_ws_client()
            for _ in range(100):
                try:
                    queue.put_nowait({"filler": True})
                except asyncio.QueueFull:
                    break
            event = {"type": "test"}
            await self.refresher._notify_ws_clients(event)
        _run_async(_test())

    def test_start_stop(self):
        async def _test():
            await self.refresher.start()
            self.assertTrue(self.refresher._running)
            self.assertIsNotNone(self.refresher._task)
            await self.refresher.stop()
            self.assertFalse(self.refresher._running)
        _run_async(_test())

    def test_start_idempotent(self):
        async def _test():
            await self.refresher.start()
            task1 = self.refresher._task
            await self.refresher.start()
            self.assertIs(self.refresher._task, task1)
            await self.refresher.stop()
        _run_async(_test())

    def test_monitor_loop_logs_expired(self):
        async def _test():
            import logging
            self.refresher.config.check_interval = 0.01
            with patch.object(logging.Logger, 'warning') as mock_warn:
                await self.refresher.start()
                await asyncio.sleep(0.1)
                await self.refresher.stop()
        _run_async(_test())

    def test_attempt_refresh_no_config(self):
        async def _test():
            refresher = SessionRefresher(
                session=self.session,
                config=RefreshConfig(auto_refresh=True),
            )
            await refresher._attempt_refresh()
        _run_async(_test())

    def test_attempt_refresh_no_fallback_browsers(self):
        async def _test():
            refresher = SessionRefresher(
                session=self.session,
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

    def test_attempt_refresh_success(self):
        async def _test():
            refresher = SessionRefresher(
                session=self.session,
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
                self.assertEqual(refresher.session["cookies"][0]["name"], "new_cookie")
        _run_async(_test())

    def test_attempt_refresh_with_fallback(self):
        async def _test():
            refresher = SessionRefresher(
                session=self.session,
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
                self.assertEqual(refresher.session["cookies"][0]["name"], "chrome_cookie")
        _run_async(_test())

    def test_attempt_refresh_preserves_local_storage(self):
        async def _test():
            self.session["local_storage"] = {"key1": "value1"}
            refresher = SessionRefresher(
                session=self.session,
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
                self.assertEqual(self.session.get("local_storage"), {"key1": "value1"})
        _run_async(_test())

    def test_attempt_refresh_filters_by_domains(self):
        async def _test():
            refresher = SessionRefresher(
                session=self.session,
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
                self.assertEqual(refresher.session["cookies"][0]["name"], "c2")
        _run_async(_test())

    def test_attempt_refresh_all_browsers_fail(self):
        async def _test():
            refresher = SessionRefresher(
                session=self.session,
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
                self.assertEqual(queue.qsize(), 1)
                event = queue.get_nowait()
                self.assertEqual(event["type"], "refresh_failed")
        _run_async(_test())

    def test_webhook_notify_on_refresh(self):
        async def _test():
            refresher = SessionRefresher(session=self.session)
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
                self.assertEqual(queue.qsize(), 1)
                event = queue.get_nowait()
                self.assertEqual(event["type"], "session_refreshed")
                self.assertEqual(event["source_browser"], "firefox")
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
        self.assertEqual(info.expiring_soon_count, 1)
        self.assertEqual(info.critical_count, 0)

    def test_session_cookies_excluded(self):
        session = {
            "cookies": [
                {"name": "c1", "value": "v", "domain": ".example.com", "expires": 0},
                {"name": "c2", "value": "v", "domain": ".example.com", "expires": -1},
            ],
        }
        refresher = SessionRefresher(session=session)
        info = refresher.check_expiry()
        self.assertEqual(info.expired_count, 0)
        self.assertEqual(info.expiring_soon_count, 0)


if __name__ == "__main__":
    unittest.main()
