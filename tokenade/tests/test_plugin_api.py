"""Tests for Plugin API v1.0 — Phase 78."""

from tokenade.plugin.api import (
    API_VERSION,
    PluginResult,
    PluginMetadata,
    PluginConfig,
    PluginConfigSchema,
)
from tokenade.plugin.base import (
    PluginBase,
    SessionRefreshPlugin,
    SiteHandlerPlugin,
    ProxyProviderPlugin,
    NotificationPlugin,
)


# ─── API_VERSION Tests ─────────────────────────────────────

class TestAPIVersion:
    def test_api_version_is_string(self):
        assert isinstance(API_VERSION, str)

    def test_api_version_format(self):
        parts = API_VERSION.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_api_version_is_1_3_0(self):
        assert API_VERSION == "1.3.0"


# ─── PluginResult Tests ────────────────────────────────────

class TestPluginResult:
    def test_success_result(self):
        r = PluginResult(success=True, data={"session": {"cookies": []}})
        assert r.success is True
        assert r.data["session"]["cookies"] == []
        assert r.error is None
        assert r.warnings == []
        assert r.duration_ms == 0.0

    def test_failure_result(self):
        r = PluginResult(success=False, error="Token expired")
        assert r.success is False
        assert r.error == "Token expired"

    def test_result_with_warnings(self):
        r = PluginResult(success=True, warnings=["Some warning"])
        assert r.success is True
        assert len(r.warnings) == 1

    def test_result_to_dict(self):
        r = PluginResult(success=True, data={"key": "val"}, duration_ms=10.5)
        d = r.to_dict()
        assert d["success"] is True
        assert d["data"]["key"] == "val"
        assert d["duration_ms"] == 10.5
        assert d["error"] is None

    def test_result_defaults(self):
        r = PluginResult(success=True)
        assert r.data == {}
        assert r.error is None
        assert r.warnings == []
        assert r.duration_ms == 0.0


# ─── PluginMetadata Tests ──────────────────────────────────

class TestPluginMetadata:
    def test_metadata_creation(self):
        m = PluginMetadata(
            name="test",
            version="1.0.0",
            api_version="1.0.0",
            author="Test",
            description="Test plugin",
        )
        assert m.name == "test"
        assert m.category == ""
        assert m.tags == []
        assert m.icon == "📦"

    def test_metadata_with_tags(self):
        m = PluginMetadata(
            name="test",
            version="1.0.0",
            api_version="1.0.0",
            author="Test",
            description="Test",
            tags=["oauth", "google"],
            category="authentication",
        )
        assert len(m.tags) == 2
        assert m.category == "authentication"


# ─── PluginConfig Tests ────────────────────────────────────

class TestPluginConfig:
    def test_config_defaults(self):
        c = PluginConfig()
        assert c.get("key") is None
        assert c.get("key", "default") == "default"

    def test_config_get_set(self):
        c = PluginConfig()
        c.set("api_key", "xxx")
        assert c.get("api_key") == "xxx"

    def test_config_from_values(self):
        c = PluginConfig(values={"api_key": "xxx", "timeout": 30})
        assert c.get("api_key") == "xxx"
        assert c.get("timeout") == 30

    def test_config_validate_required(self):
        schema = {"api_key": {"type": "string", "required": True}}
        c = PluginConfig(schema=schema, values={})
        errors = c.validate()
        assert len(errors) == 1
        assert "Missing required config: api_key" in errors[0]

    def test_config_validate_passes(self):
        schema = {"api_key": {"type": "string", "required": True}}
        c = PluginConfig(schema=schema, values={"api_key": "xxx"})
        errors = c.validate()
        assert errors == []

    def test_config_validate_type_int(self):
        schema = {"timeout": {"type": "int", "required": True}}
        c = PluginConfig(schema=schema, values={"timeout": "not_int"})
        errors = c.validate()
        assert len(errors) == 1
        assert "must be int" in errors[0]

    def test_config_validate_type_bool(self):
        schema = {"enabled": {"type": "bool", "required": True}}
        c = PluginConfig(schema=schema, values={"enabled": "yes"})
        errors = c.validate()
        assert len(errors) == 1
        assert "must be bool" in errors[0]

    def test_config_to_dict(self):
        c = PluginConfig(schema={"key": {"type": "string"}}, values={"key": "val"})
        d = c.to_dict()
        assert d["schema"]["key"]["type"] == "string"
        assert d["values"]["key"] == "val"

    def test_config_from_dict(self):
        d = {"schema": {"key": {"type": "string"}}, "values": {"key": "val"}}
        c = PluginConfig.from_dict(d)
        assert c.get("key") == "val"


# ─── PluginBase Tests ──────────────────────────────────────

class TestPluginBase:
    def test_base_has_api_version(self):
        assert hasattr(PluginBase, "API_VERSION")
        assert PluginBase.API_VERSION == "1.3.0"

    def test_base_has_lifecycle(self):
        assert hasattr(PluginBase, "on_load")
        assert hasattr(PluginBase, "on_unload")
        assert hasattr(PluginBase, "on_configure")
        assert hasattr(PluginBase, "health_check")

    def test_base_get_info(self):
        class TestPlugin(PluginBase):
            name = "test"
            version = "1.0.0"
            description = "Test"
        p = TestPlugin()
        info = p.get_info()
        assert info["name"] == "test"
        assert info["api_version"] == "1.3.0"

    def test_base_get_metadata(self):
        class TestPlugin(PluginBase):
            name = "test"
            version = "1.0.0"
            description = "Test"
            author = "Tester"
        p = TestPlugin()
        meta = p.get_metadata()
        assert meta.name == "test"
        assert meta.api_version == "1.3.0"

    def test_base_health_check_default(self):
        class TestPlugin(PluginBase):
            name = "test"
        p = TestPlugin()
        assert p.health_check() is True


# ─── SessionRefreshPlugin Tests ────────────────────────────

class TestSessionRefreshPlugin:
    def test_subclass_check(self):
        class MyPlugin(SessionRefreshPlugin):
            API_VERSION = "1.0.0"
            name = "test"
            def can_refresh(self, session):
                return True
            def refresh(self, session, credentials):
                return PluginResult(success=True)
        p = MyPlugin()
        assert isinstance(p, PluginBase)
        assert isinstance(p, SessionRefreshPlugin)
        assert p.API_VERSION in ("1.0.0", "1.1.0")

    def test_get_credentials_args_default(self):
        class MyPlugin(SessionRefreshPlugin):
            name = "test"
            def can_refresh(self, session):
                return True
            def refresh(self, session, credentials):
                return PluginResult(success=True)
        p = MyPlugin()
        assert p.get_credentials_args() == []


# ─── SiteHandlerPlugin Tests ───────────────────────────────

class TestSiteHandlerPlugin:
    def test_subclass_check(self):
        class MyHandler(SiteHandlerPlugin):
            API_VERSION = "1.0.0"
            name = "test"
            def can_handle(self, url):
                return True
            def extract_session(self, ctx, url):
                return PluginResult(success=True)
            def inject_session(self, ctx, session):
                return PluginResult(success=True)
        h = MyHandler()
        assert isinstance(h, SiteHandlerPlugin)

    def test_validate_default(self):
        class MyHandler(SiteHandlerPlugin):
            name = "test"
            def can_handle(self, url):
                return True
            def extract_session(self, ctx, url):
                return PluginResult(success=True)
            def inject_session(self, ctx, session):
                return PluginResult(success=True)
            def validate(self, session):
                return PluginResult(success=True, data={"valid": True, "score": 100.0})
        h = MyHandler()
        result = h.validate({"cookies": []})
        assert result.success is True
        assert result.data["valid"] is True


# ─── ProxyProviderPlugin Tests ─────────────────────────────

class TestProxyProviderPlugin:
    def test_subclass_check(self):
        class MyProxy(ProxyProviderPlugin):
            API_VERSION = "1.0.0"
            name = "test-proxy"
            def get_proxy(self, options=None):
                return PluginResult(success=True, data={"host": "proxy.test.io", "port": 1080})
            def rotate(self, session_id=None):
                return PluginResult(success=True, data={"host": "proxy2.test.io", "port": 1080})
        p = MyProxy()
        assert isinstance(p, ProxyProviderPlugin)
        assert p.supports_sticky is False
        assert p.countries == []

    def test_get_provider_info(self):
        class MyProxy(ProxyProviderPlugin):
            name = "test-proxy"
            website = "https://test.io"
            supports_sticky = True
            countries = ["US", "UK"]
            def get_proxy(self, options=None):
                return PluginResult(success=True)
            def rotate(self, session_id=None):
                return PluginResult(success=True)
        p = MyProxy()
        info = p.get_provider_info()
        assert info["provider"] == "test-proxy"
        assert info["supports_sticky"] is True
        assert "US" in info["countries"]

    def test_check_health_default(self):
        class MyProxy(ProxyProviderPlugin):
            name = "test-proxy"
            def get_proxy(self, options=None):
                return PluginResult(success=True)
            def rotate(self, session_id=None):
                return PluginResult(success=True)
        p = MyProxy()
        result = p.check_health({"host": "proxy.test.io"})
        assert result.success is True


# ─── NotificationPlugin Tests ──────────────────────────────

class TestNotificationPlugin:
    def test_subclass_check(self):
        class MyNotify(NotificationPlugin):
            API_VERSION = "1.0.0"
            name = "test-notify"
            def send(self, event, data):
                return PluginResult(success=True)
            def get_supported_events(self):
                return ["session_expired", "refresh_failed"]
        n = MyNotify()
        assert isinstance(n, NotificationPlugin)
        assert len(n.get_supported_events()) == 2


# ─── Plugin Loader Integration Tests ───────────────────────

class TestPluginLoaderAPI:
    def test_api_version_import(self):
        from tokenade.plugin import API_VERSION
        assert API_VERSION == "1.3.0"

    def test_plugin_result_import(self):
        from tokenade.plugin import PluginResult
        r = PluginResult(success=True)
        assert r.success is True

    def test_plugin_config_import(self):
        from tokenade.plugin import PluginConfig
        c = PluginConfig()
        assert c.get("key") is None

    def test_all_base_classes_importable(self):
        from tokenade.plugin import (
            PluginBase, SessionRefreshPlugin, SiteHandlerPlugin,
            ExportFormatPlugin, SessionValidatorPlugin,
            ProxyProviderPlugin, NotificationPlugin,
            StealthPlugin, CaptchaPlugin,
        )
        assert PluginBase is not None
        assert SessionRefreshPlugin is not None
        assert SiteHandlerPlugin is not None
        assert ProxyProviderPlugin is not None
        assert NotificationPlugin is not None
