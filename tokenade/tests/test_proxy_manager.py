"""Tests for Phase 82 — Proxy Architecture."""

from tokenade.core.proxy.manager import ProxyConfig, ProxyManager
from tokenade.plugin.base import ProxyProviderPlugin, PluginResult


# ─── ProxyConfig Tests ─────────────────────────────────────

class TestProxyConfig:
    def test_basic_creation(self):
        proxy = ProxyConfig(host="proxy.example.com", port=8080)
        assert proxy.host == "proxy.example.com"
        assert proxy.port == 8080
        assert proxy.protocol == "http"
        assert proxy.username is None
        assert proxy.password is None

    def test_server_url_no_auth(self):
        proxy = ProxyConfig(host="proxy.example.com", port=8080)
        assert proxy.server_url == "http://proxy.example.com:8080"

    def test_server_url_with_auth(self):
        proxy = ProxyConfig(
            host="proxy.example.com", port=8080,
            username="user", password="pass"
        )
        assert proxy.server_url == "http://user:pass@proxy.example.com:8080"

    def test_server_url_socks5(self):
        proxy = ProxyConfig(host="proxy.example.com", port=1080, protocol="socks5")
        assert proxy.server_url == "socks5://proxy.example.com:1080"

    def test_is_authenticated_true(self):
        proxy = ProxyConfig(host="p", port=80, username="u", password="p")
        assert proxy.is_authenticated is True

    def test_is_authenticated_false(self):
        proxy = ProxyConfig(host="p", port=80)
        assert proxy.is_authenticated is False

    def test_from_url_http(self):
        proxy = ProxyConfig.from_url("http://proxy.example.com:8080")
        assert proxy is not None
        assert proxy.host == "proxy.example.com"
        assert proxy.port == 8080
        assert proxy.protocol == "http"

    def test_from_url_with_auth(self):
        proxy = ProxyConfig.from_url("http://user:pass@proxy.example.com:8080")
        assert proxy is not None
        assert proxy.username == "user"
        assert proxy.password == "pass"

    def test_from_url_socks5(self):
        proxy = ProxyConfig.from_url("socks5://proxy.example.com:1080")
        assert proxy is not None
        assert proxy.protocol == "socks5"
        assert proxy.port == 1080

    def test_from_url_no_port(self):
        proxy = ProxyConfig.from_url("http://proxy.example.com")
        assert proxy is not None
        assert proxy.port == 8080  # default

    def test_from_url_none(self):
        assert ProxyConfig.from_url(None) is None

    def test_from_url_empty(self):
        assert ProxyConfig.from_url("") is None

    def test_to_dict(self):
        proxy = ProxyConfig(host="p", port=80, username="u", password="secret")
        d = proxy.to_dict()
        assert d["host"] == "p"
        assert d["password"] == "***"  # masked
        assert d["username"] == "u"

    def test_session_id(self):
        proxy = ProxyConfig(host="p", port=80, session_id="gmail")
        assert proxy.session_id == "gmail"


# ─── ProxyManager Tests ────────────────────────────────────

class TestProxyManager:
    def test_init(self):
        mgr = ProxyManager()
        assert mgr.has_plugin is False

    def test_init_with_cli_proxy(self):
        mgr = ProxyManager(cli_proxy="http://proxy:8080")
        proxy = mgr.get_proxy()
        assert proxy is not None
        assert proxy.host == "proxy"

    def test_init_with_config_proxy(self):
        mgr = ProxyManager(config_proxy="http://config-proxy:8080")
        proxy = mgr.get_proxy()
        assert proxy is not None
        assert proxy.host == "config-proxy"

    def test_cli_proxy_priority_over_config(self):
        mgr = ProxyManager(
            cli_proxy="http://cli-proxy:8080",
            config_proxy="http://config-proxy:8080"
        )
        proxy = mgr.get_proxy()
        assert proxy.host == "cli-proxy"

    def test_no_proxy_returns_none(self):
        mgr = ProxyManager()
        proxy = mgr.get_proxy()
        assert proxy is None

    def test_sticky_proxy_with_session_id(self):
        mgr = ProxyManager(cli_proxy="http://proxy:8080")
        proxy = mgr.get_proxy(session_id="gmail.tokenade", mode="sticky")
        assert proxy is not None
        assert proxy.session_id == "gmail.tokenade"

    def test_rotating_proxy_no_session(self):
        mgr = ProxyManager(cli_proxy="http://proxy:8080")
        proxy = mgr.get_proxy(mode="rotating")
        assert proxy is not None
        assert proxy.session_id is None

    def test_sticky_returns_same_proxy(self):
        mgr = ProxyManager(cli_proxy="http://proxy:8080")
        p1 = mgr.get_proxy(session_id="gmail", mode="sticky")
        p2 = mgr.get_proxy(session_id="gmail", mode="sticky")
        assert p1.host == p2.host

    def test_register_plugin(self):
        mgr = ProxyManager()
        mock_plugin = type("MockPlugin", (), {"name": "test"})()
        mgr.register_plugin(mock_plugin)
        assert mgr.has_plugin is True

    def test_plugin_proxy_priority(self):
        class MockPlugin(ProxyProviderPlugin):
            API_VERSION = "1.0.0"
            name = "mock"
            def get_proxy(self, options=None):
                return PluginResult(success=True, data={"host": "plugin-proxy", "port": 1080})
            def get_sticky_proxy(self, session_id=None):
                return PluginResult(success=True, data={"host": "sticky-proxy", "port": 1080})
            def get_rotating_proxy(self):
                return PluginResult(success=True, data={"host": "rotating-proxy", "port": 1080})
            def rotate(self, session_id=None):
                return PluginResult(success=True, data={"host": "rotated-proxy", "port": 1080})

        mgr = ProxyManager(cli_proxy="http://cli-proxy:8080")
        plugin = MockPlugin()
        mgr.register_plugin(plugin)

        # Plugin should take priority
        proxy = mgr.get_proxy(session_id="gmail", mode="sticky")
        assert proxy.host == "sticky-proxy"

        proxy = mgr.get_proxy(mode="rotating")
        assert proxy.host == "rotating-proxy"

    def test_plugin_fallback_to_cli(self):
        class FailPlugin(ProxyProviderPlugin):
            API_VERSION = "1.0.0"
            name = "fail"
            def get_proxy(self, options=None):
                return PluginResult(success=False, error="no proxy")
            def get_sticky_proxy(self, session_id=None):
                return PluginResult(success=False, error="no proxy")
            def get_rotating_proxy(self):
                return PluginResult(success=False, error="no proxy")
            def rotate(self, session_id=None):
                return PluginResult(success=False, error="no proxy")

        mgr = ProxyManager(cli_proxy="http://fallback:8080")
        plugin = FailPlugin()
        mgr.register_plugin(plugin)

        # Should fallback to CLI proxy
        proxy = mgr.get_proxy()
        assert proxy.host == "fallback"

    def test_rotate_with_plugin(self):
        class MockPlugin(ProxyProviderPlugin):
            API_VERSION = "1.0.0"
            name = "mock"
            def get_proxy(self, options=None):
                return PluginResult(success=True, data={"host": "p", "port": 80})
            def rotate(self, session_id=None):
                return PluginResult(success=True, data={"host": "rotated", "port": 80})

        mgr = ProxyManager()
        plugin = MockPlugin()
        mgr.register_plugin(plugin)
        proxy = mgr.rotate(session_id="gmail")
        assert proxy.host == "rotated"

    def test_check_health_no_plugin(self):
        mgr = ProxyManager()
        proxy = ProxyConfig(host="p", port=80)
        assert mgr.check_health(proxy) is True  # default healthy


# ─── CLI Parser Tests ──────────────────────────────────────

class TestProxyCLIParsers:
    def test_launch_proxy_flag(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["launch", "-s", "test.tokenade", "--proxy", "http://proxy:8080"])
        assert a.proxy == "http://proxy:8080"

    def test_launch_geoip_flag(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["launch", "-s", "test.tokenade", "--geoip"])
        assert a.geoip is True
