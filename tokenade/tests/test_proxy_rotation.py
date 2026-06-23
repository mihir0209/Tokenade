"""
Tests for proxy rotation (Phase 43).
"""

import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# ProxyEntry
# ---------------------------------------------------------------------------

class TestProxyEntry:
    """Test ProxyEntry data class."""

    def test_parse_url_http(self):
        from tokenade.core.proxy.rotation import ProxyEntry
        p = ProxyEntry(url="http://user:pass@gate.example.com:8080")
        assert p.host == "gate.example.com"
        assert p.port == 8080
        assert p.username == "user"
        assert p.password == "pass"
        assert p.protocol == "http"

    def test_parse_url_socks5(self):
        from tokenade.core.proxy.rotation import ProxyEntry
        p = ProxyEntry(url="socks5://host.example.com:1080")
        assert p.host == "host.example.com"
        assert p.port == 1080
        assert p.protocol == "socks5"
        assert p.username is None

    def test_host_port(self):
        from tokenade.core.proxy.rotation import ProxyEntry
        p = ProxyEntry(url="http://1.2.3.4:3128")
        assert p.host_port == "1.2.3.4:3128"

    def test_server_url(self):
        from tokenade.core.proxy.rotation import ProxyEntry
        p = ProxyEntry(url="socks5://user:pass@gate.com:1080")
        assert p.server_url == "socks5://user:pass@gate.com:1080"

    def test_record_success(self):
        from tokenade.core.proxy.rotation import ProxyEntry
        p = ProxyEntry(url="http://host:8080")
        assert p.healthy is True
        p.record_success(150.0)
        assert p.total_successes == 1
        assert p.avg_latency_ms == 150.0
        assert p.consecutive_failures == 0

    def test_record_failure_marks_unhealthy(self):
        from tokenade.core.proxy.rotation import ProxyEntry
        p = ProxyEntry(url="http://host:8080")
        for _ in range(3):
            p.record_failure()
        assert p.healthy is False
        assert p.consecutive_failures == 3

    def test_record_success_resets_failures(self):
        from tokenade.core.proxy.rotation import ProxyEntry
        p = ProxyEntry(url="http://host:8080")
        p.record_failure()
        p.record_failure()
        p.record_success(50.0)
        assert p.consecutive_failures == 0
        assert p.healthy is True

    def test_success_rate_empty(self):
        from tokenade.core.proxy.rotation import ProxyEntry
        p = ProxyEntry(url="http://host:8080")
        assert p.success_rate == 1.0

    def test_success_rate_mixed(self):
        from tokenade.core.proxy.rotation import ProxyEntry
        p = ProxyEntry(url="http://host:8080")
        for _ in range(7):
            p.record_success(10.0)
        for _ in range(3):
            p.record_failure()
        assert p.success_rate == pytest.approx(0.7)

    def test_to_dict(self):
        from tokenade.core.proxy.rotation import ProxyEntry
        p = ProxyEntry(url="http://host:8080", country="US", tag="test")
        d = p.to_dict()
        assert d["host"] == "host"
        assert d["port"] == 8080
        assert d["protocol"] == "http"
        assert d["country"] == "US"
        assert d["tag"] == "test"
        assert "healthy" in d
        assert "success_rate" in d

    def test_avg_latency_rolling(self):
        from tokenade.core.proxy.rotation import ProxyEntry
        p = ProxyEntry(url="http://host:8080")
        p.record_success(100.0)
        p.record_success(200.0)
        assert p.avg_latency_ms == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# ProxyPool
# ---------------------------------------------------------------------------

class TestProxyPool:
    """Test ProxyPool management."""

    def test_empty_pool(self):
        from tokenade.core.proxy.rotation import ProxyPool
        pool = ProxyPool()
        assert pool.size == 0
        assert pool.healthy_count == 0
        assert pool.get_all() == []

    def test_add_proxy(self):
        from tokenade.core.proxy.rotation import ProxyPool, ProxyEntry
        pool = ProxyPool()
        pool.add(ProxyEntry(url="http://h1:80"))
        pool.add(ProxyEntry(url="http://h2:80"))
        assert pool.size == 2

    def test_remove_proxy(self):
        from tokenade.core.proxy.rotation import ProxyPool, ProxyEntry
        pool = ProxyPool()
        pool.add(ProxyEntry(url="http://h1:80"))
        pool.add(ProxyEntry(url="http://h2:80"))
        pool.remove("h1:80")
        assert pool.size == 1
        assert pool.get_all()[0].host == "h2"

    def test_get_healthy(self):
        from tokenade.core.proxy.rotation import ProxyPool, ProxyEntry
        p1 = ProxyEntry(url="http://h1:80")
        p2 = ProxyEntry(url="http://h2:80")
        pool = ProxyPool(proxies=[p1, p2])
        p2.record_failure()
        p2.record_failure()
        p2.record_failure()
        healthy = pool.get_healthy()
        assert len(healthy) == 1
        assert healthy[0].host == "h1"

    def test_get_by_index(self):
        from tokenade.core.proxy.rotation import ProxyPool, ProxyEntry
        pool = ProxyPool(proxies=[
            ProxyEntry(url="http://h1:80"),
            ProxyEntry(url="http://h2:80"),
        ])
        assert pool.get_by_index(0).host == "h1"
        assert pool.get_by_index(1).host == "h2"
        assert pool.get_by_index(99) is None

    def test_mark_checked(self):
        from tokenade.core.proxy.rotation import ProxyPool, ProxyEntry
        pool = ProxyPool(proxies=[ProxyEntry(url="http://h1:80")])
        pool.mark_checked("h1:80", True, 50.0)
        assert pool.get_all()[0].total_successes == 1
        assert pool.get_all()[0].avg_latency_ms == 50.0

    def test_from_urls(self):
        from tokenade.core.proxy.rotation import ProxyPool
        pool = ProxyPool.from_urls([
            "http://h1:80",
            "socks5://h2:1080",
            "",
            "# comment",
            "http://h3:3128",
        ])
        assert pool.size == 3

    def test_from_file(self, tmp_path):
        from tokenade.core.proxy.rotation import ProxyPool
        proxy_file = tmp_path / "proxies.txt"
        proxy_file.write_text(
            "# comment\n"
            "http://h1:80\n"
            "socks5://h2:1080\n"
            "h3:3128:user:pass\n"
            "\n"
            "h4:8080\n"
        )
        pool = ProxyPool.from_file(str(proxy_file))
        assert pool.size == 4

    def test_from_file_not_found(self):
        from tokenade.core.proxy.rotation import ProxyPool
        with pytest.raises(FileNotFoundError):
            ProxyPool.from_file("/nonexistent/proxies.txt")

    def test_from_file_colon_separated_with_auth(self, tmp_path):
        from tokenade.core.proxy.rotation import ProxyPool
        proxy_file = tmp_path / "proxies.txt"
        proxy_file.write_text("host1:3128:user1:pass1\n")
        pool = ProxyPool.from_file(str(proxy_file))
        assert pool.size == 1
        p = pool.get_all()[0]
        assert p.host == "host1"
        assert p.port == 3128
        assert p.username == "user1"
        assert p.password == "pass1"

    def test_to_dict(self):
        from tokenade.core.proxy.rotation import ProxyPool, ProxyEntry
        pool = ProxyPool(proxies=[ProxyEntry(url="http://h1:80")])
        d = pool.to_dict()
        assert d["size"] == 1
        assert d["healthy"] == 1
        assert len(d["proxies"]) == 1

    def test_thread_safety(self):
        import threading
        from tokenade.core.proxy.rotation import ProxyPool, ProxyEntry
        pool = ProxyPool()

        def add_proxies():
            for i in range(50):
                pool.add(ProxyEntry(url=f"http://h{i}:80"))

        threads = [threading.Thread(target=add_proxies) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert pool.size == 200


# ---------------------------------------------------------------------------
# ProxyRotator
# ---------------------------------------------------------------------------

class TestProxyRotator:
    """Test ProxyRotator with various strategies."""

    def _make_pool(self, n=5):
        from tokenade.core.proxy.rotation import ProxyPool, ProxyEntry
        proxies = [ProxyEntry(url=f"http://h{i}:80") for i in range(n)]
        return ProxyPool(proxies=proxies)

    def test_round_robin(self):
        from tokenade.core.proxy.rotation import ProxyRotator, RotationStrategy
        pool = self._make_pool(3)
        rotator = ProxyRotator(pool, strategy=RotationStrategy.ROUND_ROBIN)
        results = [rotator.next().host for _ in range(6)]
        assert results == ["h0", "h1", "h2", "h0", "h1", "h2"]

    def test_random(self):
        from tokenade.core.proxy.rotation import ProxyRotator, RotationStrategy
        pool = self._make_pool(5)
        rotator = ProxyRotator(pool, strategy=RotationStrategy.RANDOM)
        results = {rotator.next().host for _ in range(50)}
        # Should see at least 2 different proxies in 50 random picks
        assert len(results) >= 2

    def test_sticky(self):
        from tokenade.core.proxy.rotation import ProxyRotator, RotationStrategy
        pool = self._make_pool(5)
        rotator = ProxyRotator(pool, strategy=RotationStrategy.STICKY)
        # Same session_id → same proxy every time
        r1 = rotator.next(session_id="session-abc")
        r2 = rotator.next(session_id="session-abc")
        r3 = rotator.next(session_id="session-abc")
        assert r1.host == r2.host == r3.host
        # Different session_id → may be different
        r4 = rotator.next(session_id="session-xyz")
        # Not guaranteed to be different, but the mapping is deterministic
        assert r4.host in [f"h{i}" for i in range(5)]

    def test_health_weighted(self):
        from tokenade.core.proxy.rotation import ProxyRotator, RotationStrategy, ProxyPool, ProxyEntry
        # Make h0 very healthy, h1 very unhealthy
        p0 = ProxyEntry(url="http://h0:80")
        p1 = ProxyEntry(url="http://h1:80")
        for _ in range(20):
            p0.record_success(10.0)
        for _ in range(20):
            p1.record_failure()
        pool = ProxyPool(proxies=[p0, p1])
        rotator = ProxyRotator(pool, strategy=RotationStrategy.HEALTH_WEIGHTED)
        results = [rotator.next().host for _ in range(100)]
        # h0 should be chosen much more often
        assert results.count("h0") > results.count("h1")

    def test_empty_pool(self):
        from tokenade.core.proxy.rotation import ProxyRotator, ProxyPool, RotationStrategy
        pool = ProxyPool()
        rotator = ProxyRotator(pool, strategy=RotationStrategy.ROUND_ROBIN)
        assert rotator.next() is None

    def test_all_unhealthy_fallback(self):
        from tokenade.core.proxy.rotation import ProxyRotator, ProxyPool, ProxyEntry, RotationStrategy
        p1 = ProxyEntry(url="http://h1:80")
        p2 = ProxyEntry(url="http://h2:80")
        for _ in range(3):
            p1.record_failure()
            p2.record_failure()
        pool = ProxyPool(proxies=[p1, p2])
        rotator = ProxyRotator(pool, strategy=RotationStrategy.ROUND_ROBIN)
        # Should fall back to unhealthy proxies
        proxy = rotator.next()
        assert proxy is not None

    def test_record_success_and_failure(self):
        from tokenade.core.proxy.rotation import ProxyRotator, ProxyPool, ProxyEntry, RotationStrategy
        p = ProxyEntry(url="http://h1:80")
        pool = ProxyPool(proxies=[p])
        rotator = ProxyRotator(pool, strategy=RotationStrategy.ROUND_ROBIN)
        proxy = rotator.next()
        rotator.record_success(proxy, 100.0)
        assert pool.get_all()[0].total_successes == 1
        rotator.record_failure(proxy)
        assert pool.get_all()[0].total_failures == 1


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    """Test proxy health checking."""

    def test_health_check_unreachable(self):
        from tokenade.core.proxy.rotation import ProxyRotator, ProxyEntry
        p = ProxyEntry(url="http://192.0.2.1:19999")  # TEST-NET, unreachable
        healthy, latency = ProxyRotator.health_check(p, timeout=1.0)
        assert healthy is False
        assert latency >= 0

    def test_check_health_batch(self):
        from tokenade.core.proxy.rotation import ProxyRotator, ProxyPool, ProxyEntry, RotationStrategy
        p1 = ProxyEntry(url="http://192.0.2.1:19999")
        p2 = ProxyEntry(url="http://192.0.2.2:19999")
        pool = ProxyPool(proxies=[p1, p2])
        rotator = ProxyRotator(pool, strategy=RotationStrategy.ROUND_ROBIN)
        results = rotator.check_health(timeout=0.5)
        assert len(results) == 2
        assert all(not v for v in results.values())


# ---------------------------------------------------------------------------
# BrowserLaunchConfig with proxy
# ---------------------------------------------------------------------------

class TestBrowserLaunchConfigProxy:
    """Test BrowserLaunchConfig includes upstream_proxy."""

    def test_default_no_proxy(self):
        from tokenade.core.browser.undetectable import BrowserLaunchConfig
        config = BrowserLaunchConfig()
        assert config.upstream_proxy is None

    def test_set_proxy(self):
        from tokenade.core.browser.undetectable import BrowserLaunchConfig
        config = BrowserLaunchConfig(upstream_proxy="socks5://user:pass@host:1080")
        assert config.upstream_proxy == "socks5://user:pass@host:1080"

    def test_build_args_with_proxy(self):
        from tokenade.core.browser.undetectable import SystemBrowserLauncher
        launcher = SystemBrowserLauncher()
        args = launcher._build_args(
            browser="chrome",
            browser_path="/usr/bin/google-chrome",
            visible=True,
            port=9222,
            profile_dir="/tmp/profile",
            user_data_dir=None,
            window_size=(1920, 1080),
            extra_args=[],
            upstream_proxy="socks5://user:pass@host:1080",
        )
        assert "--proxy-server=socks5://user:pass@host:1080" in args
        assert "--proxy-bypass-list=localhost,127.0.0.1,<-loopback>" in args

    def test_build_args_no_proxy(self):
        from tokenade.core.browser.undetectable import SystemBrowserLauncher
        launcher = SystemBrowserLauncher()
        args = launcher._build_args(
            browser="chrome",
            browser_path="/usr/bin/google-chrome",
            visible=True,
            port=9222,
            profile_dir="/tmp/profile",
            user_data_dir=None,
            window_size=(1920, 1080),
            extra_args=[],
        )
        assert not any("--proxy-server" in a for a in args)

    def test_build_args_firefox_with_proxy(self):
        from tokenade.core.browser.undetectable import SystemBrowserLauncher
        launcher = SystemBrowserLauncher()
        args = launcher._build_args(
            browser="firefox",
            browser_path="/usr/bin/firefox",
            visible=True,
            port=9222,
            profile_dir="/tmp/profile",
            user_data_dir=None,
            window_size=(1920, 1080),
            extra_args=[],
            upstream_proxy="http://host:3128",
        )
        assert "--proxy-server=http://host:3128" in args


# ---------------------------------------------------------------------------
# Config proxy options
# ---------------------------------------------------------------------------

class TestConfigProxyOptions:
    """Test proxy-related config options."""

    def test_default_config_has_proxy_options(self):
        from tokenade.core.config import DEFAULTS
        assert "upstream_proxy" in DEFAULTS
        assert "upstream_proxy_file" in DEFAULTS
        assert "upstream_proxy_rotate" in DEFAULTS
        assert "upstream_proxy_strategy" in DEFAULTS
        assert DEFAULTS["upstream_proxy"] is None
        assert DEFAULTS["upstream_proxy_rotate"] is False
        assert DEFAULTS["upstream_proxy_strategy"] == "health-weighted"

    def test_config_get_proxy(self, tmp_path):
        from tokenade.core.config import TokenadeConfig
        config_file = tmp_path / "config.json"
        config_file.write_text('{"upstream_proxy": "socks5://h:1080"}')
        config = TokenadeConfig(str(config_file))
        assert config.get("upstream_proxy") == "socks5://h:1080"

    def test_config_defaults_fallback(self):
        from tokenade.core.config import TokenadeConfig
        config = TokenadeConfig("/nonexistent/config.json")
        assert config.get("upstream_proxy") is None
        assert config.get("upstream_proxy_strategy") == "health-weighted"


# ---------------------------------------------------------------------------
# CLI parser proxy flags
# ---------------------------------------------------------------------------

class TestCLIParserProxyFlags:
    """Test CLI parser accepts proxy flags."""

    def test_launch_proxy_flags(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args([
            "launch", "-s", "test.tokenade",
            "--proxy", "socks5://h:1080",
            "--proxy-strategy", "round-robin",
        ])
        assert args.proxy == "socks5://h:1080"
        assert args.proxy_strategy == "round-robin"
        assert args.proxy_file is None
        assert args.proxy_rotate is False

    def test_launch_proxy_file_flags(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args([
            "launch", "-s", "test.tokenade",
            "--proxy-file", "proxies.txt",
            "--proxy-rotate",
        ])
        assert args.proxy_file == "proxies.txt"
        assert args.proxy_rotate is True

    def test_refresh_browser_proxy_flags(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args([
            "refresh-browser", "-s", "test.tokenade",
            "--proxy", "http://h:3128",
        ])
        assert args.proxy == "http://h:3128"

    def test_accounts_refresh_proxy_flags(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args([
            "accounts", "refresh",
            "--proxy-file", "proxies.txt",
            "--proxy-rotate",
            "--proxy-strategy", "random",
        ])
        assert args.proxy_file == "proxies.txt"
        assert args.proxy_rotate is True
        assert args.proxy_strategy == "random"


# ---------------------------------------------------------------------------
# _resolve_upstream_proxy
# ---------------------------------------------------------------------------

class TestResolveUpstreamProxy:
    """Test _resolve_upstream_proxy helper."""

    def test_resolve_single_proxy(self):
        from tokenade.cli.management import _resolve_upstream_proxy
        from argparse import Namespace
        args = Namespace(proxy="socks5://h:1080", proxy_file=None, proxy_strategy="health-weighted")
        assert _resolve_upstream_proxy(args) == "socks5://h:1080"

    def test_resolve_from_file(self, tmp_path):
        from tokenade.cli.management import _resolve_upstream_proxy
        from argparse import Namespace
        proxy_file = tmp_path / "proxies.txt"
        proxy_file.write_text("http://h1:80\nhttp://h2:80\n")
        args = Namespace(proxy=None, proxy_file=str(proxy_file), proxy_strategy="round-robin")
        result = _resolve_upstream_proxy(args)
        assert result in ["http://h1:80", "http://h2:80"]

    def test_resolve_nothing(self):
        from tokenade.cli.management import _resolve_upstream_proxy
        from argparse import Namespace
        args = Namespace(proxy=None, proxy_file=None, proxy_strategy="health-weighted")
        result = _resolve_upstream_proxy(args)
        # Should return None (no proxy configured)
        assert result is None

    def test_resolve_file_not_found(self):
        from tokenade.cli.management import _resolve_upstream_proxy
        from argparse import Namespace
        args = Namespace(proxy=None, proxy_file="/nonexistent/proxies.txt", proxy_strategy="health-weighted")
        result = _resolve_upstream_proxy(args)
        assert result is None

    def test_single_proxy_takes_priority_over_file(self, tmp_path):
        from tokenade.cli.management import _resolve_upstream_proxy
        from argparse import Namespace
        proxy_file = tmp_path / "proxies.txt"
        proxy_file.write_text("http://h1:80\n")
        args = Namespace(proxy="socks5://priority:1080", proxy_file=str(proxy_file), proxy_strategy="round-robin")
        assert _resolve_upstream_proxy(args) == "socks5://priority:1080"


# ---------------------------------------------------------------------------
# Integration: rotation with pool from file
# ---------------------------------------------------------------------------

class TestRotationIntegration:
    """Integration tests for proxy rotation."""

    def test_rotation_cycle(self, tmp_path):
        from tokenade.core.proxy.rotation import ProxyPool, ProxyRotator, RotationStrategy
        proxy_file = tmp_path / "proxies.txt"
        proxy_file.write_text("http://h1:80\nhttp://h2:80\nhttp://h3:80\n")
        pool = ProxyPool.from_file(str(proxy_file))
        assert pool.size == 3

        rotator = ProxyRotator(pool, strategy=RotationStrategy.ROUND_ROBIN)
        seen = [rotator.next().host for _ in range(9)]
        assert seen == ["h1", "h2", "h3", "h1", "h2", "h3", "h1", "h2", "h3"]

    def test_health_check_updates_pool(self, tmp_path):
        from tokenade.core.proxy.rotation import ProxyPool, ProxyRotator, ProxyEntry, RotationStrategy
        p1 = ProxyEntry(url="http://h1:80")
        pool = ProxyPool(proxies=[p1])
        rotator = ProxyRotator(pool, strategy=RotationStrategy.ROUND_ROBIN)

        # Simulate failures
        for _ in range(5):
            rotator.record_failure(p1)

        assert pool.get_all()[0].healthy is False
        assert pool.get_all()[0].consecutive_failures == 5

        # Simulate recovery
        rotator.record_success(p1, 50.0)
        assert pool.get_all()[0].healthy is True
        assert pool.get_all()[0].consecutive_failures == 0

    def test_to_dict_reflects_state(self, tmp_path):
        from tokenade.core.proxy.rotation import ProxyPool, ProxyEntry
        p = ProxyEntry(url="http://h1:80")
        p.record_success(100.0)
        p.record_success(200.0)
        pool = ProxyPool(proxies=[p])
        d = pool.to_dict()
        assert d["proxies"][0]["total_successes"] == 2
        assert d["proxies"][0]["avg_latency_ms"] == 150.0
