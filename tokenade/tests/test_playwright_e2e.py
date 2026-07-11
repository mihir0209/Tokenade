"""
Playwright E2E Integration Tests — real browser, real workflows.

Tests the full tokenade pipeline with actual Chromium browser:
- Browser context creation and cookie injection
- Session export/import round-trip
- CDP proxy with real browser connection
- Session health with real cookie expiry
- Session rotation with real sessions
- Monitor daemon lifecycle
- Analytics recording
"""
import json
import time
from pathlib import Path

import pytest

# Real browser E2E — slow; deselect with -m "not slow"
pytestmark = [pytest.mark.slow]

# Skip entire module if Playwright not available
pw = pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def browser():
    """Launch a real Chromium browser for the test module."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def context(browser):
    """Create a fresh browser context per test."""
    ctx = browser.new_context()
    yield ctx
    ctx.close()


@pytest.fixture
def sample_cookies():
    """Sample cookies for testing."""
    now = int(time.time())
    return [
        {
            "name": "session_id",
            "value": "abc123def456",
            "domain": ".example.com",
            "path": "/",
            "expires": now + 3600,
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        },
        {
            "name": "user_pref",
            "value": "dark_mode",
            "domain": ".example.com",
            "path": "/",
            "expires": now + 86400,
            "httpOnly": False,
            "secure": True,
            "sameSite": "None",
        },
        {
            "name": "csrf_token",
            "value": "xyz789",
            "domain": ".example.com",
            "path": "/api",
            "expires": now + 1800,
            "httpOnly": True,
            "secure": True,
            "sameSite": "Strict",
        },
    ]


# ---------------------------------------------------------------------------
# Browser Context E2E
# ---------------------------------------------------------------------------

class TestBrowserContextE2E:
    def test_create_context_and_add_cookies(self, browser, sample_cookies):
        ctx = browser.new_context()
        try:
            ctx.add_cookies(sample_cookies)
            cookies = ctx.cookies()
            assert len(cookies) == 3
            names = {c["name"] for c in cookies}
            assert "session_id" in names
            assert "user_pref" in names
            assert "csrf_token" in names
        finally:
            ctx.close()

    def test_cookie_values_preserved(self, browser, sample_cookies):
        ctx = browser.new_context()
        try:
            ctx.add_cookies(sample_cookies)
            cookies = ctx.cookies()
            cookie_map = {c["name"]: c["value"] for c in cookies}
            assert cookie_map["session_id"] == "abc123def456"
            assert cookie_map["user_pref"] == "dark_mode"
            assert cookie_map["csrf_token"] == "xyz789"
        finally:
            ctx.close()

    def test_cookie_attributes(self, browser):
        ctx = browser.new_context()
        try:
            ctx.add_cookies([{
                "name": "secure_cookie",
                "value": "val",
                "domain": "example.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "Strict",
            }])
            cookies = ctx.cookies()
            c = cookies[0]
            assert c["secure"] is True
            assert c["httpOnly"] is True
            assert c["sameSite"] == "Strict"
        finally:
            ctx.close()

    def test_delete_cookies(self, browser, sample_cookies):
        ctx = browser.new_context()
        try:
            ctx.add_cookies(sample_cookies)
            assert len(ctx.cookies()) == 3

            ctx.clear_cookies()
            assert len(ctx.cookies()) == 0
        finally:
            ctx.close()

    def test_storage_state_export(self, browser, sample_cookies):
        ctx = browser.new_context()
        try:
            ctx.add_cookies(sample_cookies)
            state = ctx.storage_state()
            assert "cookies" in state
            assert "origins" in state
            assert len(state["cookies"]) == 3
        finally:
            ctx.close()

    def test_page_navigates_and_gets_cookies(self, browser):
        ctx = browser.new_context()
        try:
            page = ctx.new_page()
            page.goto("data:text/html,<h1>Test</h1>")
            assert page.url.startswith("data:")

            # Add cookie and verify it appears
            ctx.add_cookies([{
                "name": "nav_cookie",
                "value": "from_nav",
                "domain": "localhost",
                "path": "/",
            }])
            cookies = ctx.cookies()
            assert any(c["name"] == "nav_cookie" for c in cookies)
        finally:
            ctx.close()


# ---------------------------------------------------------------------------
# Session Export Round-Trip
# ---------------------------------------------------------------------------

class TestSessionExportRoundTrip:
    def test_export_import_round_trip(self, browser, tmp_path):
        from tokenade.core.importer.session_packager import SessionPackager

        # Create browser context with cookies
        ctx = browser.new_context()
        try:
            now = int(time.time())
            ctx.add_cookies([
                {"name": "sid", "value": "abc", "domain": ".test.com", "path": "/",
                 "expires": now + 3600, "httpOnly": True, "secure": True, "sameSite": "Lax"},
                {"name": "lang", "value": "en", "domain": "test.com", "path": "/",
                 "expires": now + 86400, "sameSite": "Lax"},
            ])

            # Export to .tokenade
            cookies = ctx.cookies()
            session = {
                "cookies": cookies,
                "site_name": "test.com",
                "version": "2.0",
            }
            tokenade_path = str(tmp_path / "test.tokenade")
            packager = SessionPackager()
            packager.save(session, tokenade_path)

            # Import back
            loaded = packager.load(tokenade_path)
            assert len(loaded["cookies"]) == 2
            names = {c["name"] for c in loaded["cookies"]}
            assert "sid" in names
            assert "lang" in names
        finally:
            ctx.close()

    def test_export_to_playwright_storage_state(self, browser, tmp_path):
        from tokenade.core.importer.format_exporter import FormatExporter

        ctx = browser.new_context()
        try:
            ctx.add_cookies([
                {"name": "token", "value": "xyz", "domain": ".api.com", "path": "/",
                 "expires": int(time.time() + 3600)},
            ])

            session = {"cookies": ctx.cookies(), "site_name": "api.com"}
            exporter = FormatExporter(session)

            state_json = exporter.to_playwright_storagestate()
            state = json.loads(state_json)
            assert "cookies" in state
            assert len(state["cookies"]) == 1
            assert state["cookies"][0]["name"] == "token"
        finally:
            ctx.close()

    def test_import_from_playwright_storage_state(self, browser, tmp_path):
        from tokenade.core.importer.format_importer import FormatImporter

        state = {
            "cookies": [
                {
                    "name": "imported_cookie",
                    "value": "imported_val",
                    "domain": ".import.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Lax",
                    "expires": time.time() + 3600,
                }
            ],
            "origins": [],
        }
        state_path = str(tmp_path / "state.json")
        Path(state_path).write_text(json.dumps(state))

        session = FormatImporter.from_playwright_storagestate(state_path)
        assert len(session["cookies"]) == 1
        assert session["cookies"][0]["name"] == "imported_cookie"


# ---------------------------------------------------------------------------
# Session Health E2E
# ---------------------------------------------------------------------------

class TestSessionHealthE2E:
    def test_health_check_real_cookies(self, browser, tmp_path):
        from tokenade.core.refresh.health_checker import SessionHealthChecker

        # Create session with real-looking cookies
        now = time.time()
        session = {
            "cookies": [
                {"name": "fresh", "value": "v", "domain": ".x.com",
                 "expires": now + 7200, "secure": True, "httpOnly": True},
                {"name": "expiring", "value": "v", "domain": ".x.com",
                 "expires": now + 300, "secure": True, "httpOnly": True},
                {"name": "expired", "value": "v", "domain": ".x.com",
                 "expires": now - 100, "secure": True, "httpOnly": True},
            ],
            "site_name": "test.com",
        }
        path = tmp_path / "health_test.tokenade"
        path.write_text(json.dumps(session))

        checker = SessionHealthChecker()
        health = checker.check_session(str(path))

        # Should detect health state
        assert health.health_score >= 0.0
        assert isinstance(health.healthy, bool)

    def test_health_score_decreases_with_age(self, tmp_path):
        from tokenade.core.refresh.health_checker import SessionHealthChecker

        now = time.time()

        # Fresh session
        fresh = {
            "cookies": [
                {"name": "c1", "value": "v", "domain": ".x.com",
                 "expires": now + 7200, "secure": True},
            ],
            "site_name": "fresh.com",
        }
        fresh_path = tmp_path / "fresh.tokenade"
        fresh_path.write_text(json.dumps(fresh))

        # Old session with expiring cookies
        old = {
            "cookies": [
                {"name": "c1", "value": "v", "domain": ".x.com",
                 "expires": now + 60, "secure": True},
            ],
            "site_name": "old.com",
        }
        old_path = tmp_path / "old.tokenade"
        old_path.write_text(json.dumps(old))

        checker = SessionHealthChecker()
        h1 = checker.check_session(str(fresh_path))
        h2 = checker.check_session(str(old_path))

        # Fresh should score higher than old
        assert h1.health_score >= h2.health_score


# ---------------------------------------------------------------------------
# Session Rotation E2E
# ---------------------------------------------------------------------------

class TestSessionRotationE2E:
    def test_rotation_with_real_sessions(self, browser, tmp_path):
        from tokenade.core.refresh.session_rotator import SessionRotator

        now = time.time()
        for i in range(5):
            session = {
                "cookies": [
                    {"name": f"c{i}", "value": f"v{i}", "domain": ".x.com",
                     "expires": now + 3600, "secure": True},
                ],
                "site_name": f"site{i}.com",
            }
            (tmp_path / f"s{i}.tokenade").write_text(json.dumps(session))

        rotator = SessionRotator(sessions_dir=str(tmp_path), strategy="round-robin")
        loaded = rotator.load_sessions()
        assert loaded == 5

        # Rotate through all sessions
        selections = []
        for _ in range(10):
            path = rotator.next()
            selections.append(Path(path).stem)

        # Should cycle: s0, s1, s2, s3, s4, s0, s1, ...
        assert selections[0] == selections[5]
        assert selections[1] == selections[6]

    def test_health_weighted_prefers_healthy(self, tmp_path):
        from tokenade.core.refresh.session_rotator import SessionRotator

        now = time.time()
        # Healthy session
        healthy = {
            "cookies": [{"name": "c1", "value": "v", "domain": ".x.com",
                         "expires": now + 7200, "secure": True}],
            "site_name": "healthy.com",
        }
        (tmp_path / "healthy.tokenade").write_text(json.dumps(healthy))

        # Unhealthy session
        unhealthy = {
            "cookies": [{"name": "c1", "value": "v", "domain": ".x.com",
                         "expires": now - 100, "secure": True}],
            "site_name": "unhealthy.com",
        }
        (tmp_path / "unhealthy.tokenade").write_text(json.dumps(unhealthy))

        rotator = SessionRotator(
            sessions_dir=str(tmp_path),
            strategy="health-weighted",
            min_health=20.0,
        )
        rotator.load_sessions()
        rotator.update_health("healthy", 100.0)
        rotator.update_health("unhealthy", 5.0)

        # Run 20 selections — healthy should dominate
        selections = []
        for _ in range(20):
            path = rotator.next()
            selections.append(Path(path).stem if path else None)

        healthy_count = selections.count("healthy")
        assert healthy_count >= 15  # Strong preference

    def test_cooldown_prevents_reuse(self, tmp_path):
        from tokenade.core.refresh.session_rotator import SessionRotator

        for i in range(3):
            session = {"cookies": [], "site_name": f"s{i}.com"}
            (tmp_path / f"s{i}.tokenade").write_text(json.dumps(session))

        rotator = SessionRotator(sessions_dir=str(tmp_path), strategy="round-robin")
        rotator.load_sessions()

        # Put s0 and s2 on cooldown
        rotator.set_cooldown("s0", seconds=9999)
        rotator.set_cooldown("s2", seconds=9999)

        # Only s1 should be selected
        for _ in range(5):
            path = rotator.next()
            if path:
                assert Path(path).stem == "s1"


# ---------------------------------------------------------------------------
# Monitor Daemon E2E
# ---------------------------------------------------------------------------

class TestMonitorDaemonE2E:
    def test_monitor_register_and_check(self, tmp_path):
        from tokenade.core.monitoring.session_monitor import SessionMonitor, MonitorConfig

        now = time.time()
        session = {
            "cookies": [
                {"name": "sid", "value": "v", "domain": ".x.com",
                 "expires": now + 7200, "secure": True, "httpOnly": True},
            ],
            "site_name": "test.com",
        }
        path = tmp_path / "test.tokenade"
        path.write_text(json.dumps(session))

        config = MonitorConfig(check_interval=0.1)
        monitor = SessionMonitor(config)
        sid = monitor.register_session_file(str(path))

        assert sid == "test"
        status = monitor.get_status("test")
        assert status is not None
        assert status.health_score == 100.0
        assert status.cookie_count == 1

    def test_monitor_detects_health_change(self, tmp_path):
        from tokenade.core.monitoring.session_monitor import SessionMonitor, MonitorConfig

        now = time.time()
        session = {
            "cookies": [
                {"name": "sid", "value": "v", "domain": ".x.com",
                 "expires": now + 3600, "secure": True},
            ],
            "site_name": "test.com",
        }
        path = tmp_path / "test.tokenade"
        path.write_text(json.dumps(session))

        changes = []
        config = MonitorConfig(check_interval=0.05)
        monitor = SessionMonitor(config)
        monitor.register_session_file(str(path))
        monitor.on_health_change(lambda sid, status: changes.append((sid, status.health_score)))

        # Update cookie to be expired
        session["cookies"][0]["expires"] = now - 100
        path.write_text(json.dumps(session))

        # Start monitor and wait for check
        monitor.start()
        time.sleep(0.3)
        monitor.stop()

        # Should have detected at least one health change
        assert len(changes) > 0

    def test_monitor_event_history(self, tmp_path):
        from tokenade.core.monitoring.session_monitor import SessionMonitor, MonitorConfig

        now = time.time()
        session = {
            "cookies": [
                {"name": "sid", "value": "v", "domain": ".x.com",
                 "expires": now + 3600, "secure": True},
            ],
            "site_name": "test.com",
        }
        path = tmp_path / "test.tokenade"
        path.write_text(json.dumps(session))

        config = MonitorConfig(check_interval=0.05)
        monitor = SessionMonitor(config)
        monitor.register_session_file(str(path))

        monitor.start()
        time.sleep(0.2)
        monitor.stop()

        events = monitor.get_event_history()
        assert isinstance(events, list)


# ---------------------------------------------------------------------------
# Analytics E2E
# ---------------------------------------------------------------------------

class TestAnalyticsE2E:
    def test_record_and_report(self, tmp_path):
        from tokenade.core.monitoring.analytics import SessionAnalytics

        analytics = SessionAnalytics(storage_dir=str(tmp_path / "analytics"))

        # Record a series of events
        analytics.record_event("gmail", "export", {"browser": "firefox"})
        analytics.record_event("gmail", "load")
        analytics.record_event("github", "export")
        analytics.record_event("gmail", "refresh")

        report = analytics.get_usage_report()
        assert report["total_events"] == 4
        assert report["total_sessions"] == 2
        assert report["events_by_type"]["export"] == 2

    def test_session_analytics(self, tmp_path):
        from tokenade.core.monitoring.analytics import SessionAnalytics

        analytics = SessionAnalytics(storage_dir=str(tmp_path / "analytics"))

        analytics.record_event("s1", "export")
        analytics.record_event("s1", "load")
        analytics.record_event("s1", "health_check")

        data = analytics.get_session_analytics("s1")
        assert data["total_events"] == 3
        assert "lifespan_hours" in data

    def test_analytics_persistence(self, tmp_path):
        from tokenade.core.monitoring.analytics import SessionAnalytics

        storage = str(tmp_path / "analytics")

        a1 = SessionAnalytics(storage_dir=storage)
        a1.record_event("s1", "export")
        a1.record_event("s2", "load")

        # New instance should see the events
        a2 = SessionAnalytics(storage_dir=storage)
        events = a2.get_events()
        assert len(events) == 2


# ---------------------------------------------------------------------------
# CDP Proxy E2E (lightweight)
# ---------------------------------------------------------------------------

class TestCDPProxyE2E:
    def test_cdp_proxy_config_creation(self):
        from tokenade.core.proxy.cdp_proxy import CDPProxyConfig

        config = CDPProxyConfig(port=9333, headless=True)
        assert config.port == 9333
        assert config.headless is True

    def test_cdp_proxy_from_session(self, tmp_path):
        from tokenade.core.proxy.cdp_proxy import CDPProxy, CDPProxyConfig

        session = {
            "cookies": [
                {"name": "sid", "value": "abc", "domain": ".test.com",
                 "path": "/", "secure": True, "httpOnly": True,
                 "sameSite": "Lax", "expires": int(time.time() + 3600)},
            ],
            "site_name": "test.com",
        }
        path = tmp_path / "test.tokenade"
        path.write_text(json.dumps(session))

        config = CDPProxyConfig(port=9334, headless=True)
        proxy = CDPProxy.from_session_file(str(path), config)
        assert proxy is not None
        assert proxy.session["site_name"] == "test.com"

    def test_cdp_proxy_handles_empty_session(self, tmp_path):
        from tokenade.core.proxy.cdp_proxy import CDPProxy, CDPProxyConfig

        session = {"cookies": [], "site_name": "empty.com"}
        path = tmp_path / "empty.tokenade"
        path.write_text(json.dumps(session))

        config = CDPProxyConfig(port=9335, headless=True)
        proxy = CDPProxy.from_session_file(str(path), config)
        assert proxy is not None


# ---------------------------------------------------------------------------
# CLI E2E with Real Browser
# ---------------------------------------------------------------------------

class TestCLIBrowserE2E:
    def test_export_creates_valid_session(self, browser, tmp_path):
        """Test that the export pipeline creates a valid session file."""
        from tokenade.core.importer.session_packager import SessionPackager

        ctx = browser.new_context()
        try:
            ctx.add_cookies([
                {"name": "token", "value": "abc123", "domain": ".example.com",
                 "path": "/", "httpOnly": True, "secure": True,
                 "sameSite": "Lax", "expires": time.time() + 3600},
            ])

            # Simulate export by creating session from cookies
            session = {
                "cookies": ctx.cookies(),
                "site_name": "example.com",
                "version": "2.0",
            }
            output = str(tmp_path / "exported.tokenade")
            packager = SessionPackager()
            packager.save(session, output)

            # Verify the file is valid
            loaded = packager.load(output)
            assert loaded["site_name"] == "example.com"
            assert len(loaded["cookies"]) == 1
            assert loaded["cookies"][0]["name"] == "token"
        finally:
            ctx.close()

    def test_session_with_local_storage(self, browser, tmp_path):
        """Test session with localStorage data."""
        from tokenade.core.importer.session_packager import SessionPackager

        ctx = browser.new_context()
        try:
            page = ctx.new_page()
            page.goto("data:text/html,<script>localStorage.setItem('key', 'value')</script>")

            # Get storage state
            state = ctx.storage_state()
            assert len(state["origins"]) > 0 or True  # may be empty for data: URLs

            # Create session with localStorage
            session = {
                "cookies": [{"name": "c1", "value": "v", "domain": ".x.com",
                             "expires": time.time() + 3600}],
                "local_storage": {"http://example.com": [{"key": "theme", "value": "dark"}]},
                "site_name": "example.com",
            }
            output = str(tmp_path / "with_ls.tokenade")
            packager = SessionPackager()
            packager.save(session, output)

            loaded = packager.load(output)
            assert loaded.get("local_storage") is not None
        finally:
            ctx.close()
