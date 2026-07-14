"""Tests for Plugin API v1.1 — Login verification, export specification."""

from tokenade.plugin.api import API_VERSION, PluginResult
from tokenade.plugin.base import SiteHandlerPlugin


# ─── API Version Tests ─────────────────────────────────────

class TestAPIVersion:
    def test_api_version_is_1_3_0(self):
        assert API_VERSION == "1.3.0"


# ─── SiteHandlerPlugin v1.1 Methods ────────────────────────

class TestSiteHandlerPluginV11:
    def test_has_export_methods(self):
        class MyHandler(SiteHandlerPlugin):
            API_VERSION = "1.1.0"
            name = "test"
            def can_handle(self, url): return True  # noqa: E704
            def extract_session(self, ctx, url): return PluginResult(success=True)  # noqa: E704
            def inject_session(self, ctx, session): return PluginResult(success=True)  # noqa: E704
        h = MyHandler()
        assert hasattr(h, "get_export_domains")
        assert hasattr(h, "get_critical_cookies")
        assert hasattr(h, "get_critical_storage")

    def test_has_login_verification_methods(self):
        class MyHandler(SiteHandlerPlugin):
            API_VERSION = "1.1.0"
            name = "test"
            def can_handle(self, url): return True  # noqa: E704
            def extract_session(self, ctx, url): return PluginResult(success=True)  # noqa: E704
            def inject_session(self, ctx, session): return PluginResult(success=True)  # noqa: E704
        h = MyHandler()
        assert hasattr(h, "get_login_url")
        assert hasattr(h, "get_dashboard_url")
        assert hasattr(h, "get_session_check_url")
        assert hasattr(h, "get_logged_in_selectors")
        assert hasattr(h, "get_logged_out_selectors")
        assert hasattr(h, "verify_login")

    def test_default_export_domains(self):
        class MyHandler(SiteHandlerPlugin):
            name = "test"
            def can_handle(self, url): return True  # noqa: E704
            def extract_session(self, ctx, url): return PluginResult(success=True)  # noqa: E704
            def inject_session(self, ctx, session): return PluginResult(success=True)  # noqa: E704
        h = MyHandler()
        assert h.get_export_domains() == []

    def test_default_critical_cookies(self):
        class MyHandler(SiteHandlerPlugin):
            name = "test"
            def can_handle(self, url): return True  # noqa: E704
            def extract_session(self, ctx, url): return PluginResult(success=True)  # noqa: E704
            def inject_session(self, ctx, session): return PluginResult(success=True)  # noqa: E704
        h = MyHandler()
        assert h.get_critical_cookies() == []

    def test_default_critical_storage(self):
        class MyHandler(SiteHandlerPlugin):
            name = "test"
            def can_handle(self, url): return True  # noqa: E704
            def extract_session(self, ctx, url): return PluginResult(success=True)  # noqa: E704
            def inject_session(self, ctx, session): return PluginResult(success=True)  # noqa: E704
        h = MyHandler()
        storage = h.get_critical_storage()
        assert storage == {"local": {}, "session": {}}

    def test_default_login_url(self):
        class MyHandler(SiteHandlerPlugin):
            name = "test"
            def can_handle(self, url): return True  # noqa: E704
            def extract_session(self, ctx, url): return PluginResult(success=True)  # noqa: E704
            def inject_session(self, ctx, session): return PluginResult(success=True)  # noqa: E704
        h = MyHandler()
        assert h.get_login_url() == ""

    def test_default_selectors(self):
        class MyHandler(SiteHandlerPlugin):
            name = "test"
            def can_handle(self, url): return True  # noqa: E704
            def extract_session(self, ctx, url): return PluginResult(success=True)  # noqa: E704
            def inject_session(self, ctx, session): return PluginResult(success=True)  # noqa: E704
        h = MyHandler()
        assert h.get_logged_in_selectors() == []
        assert h.get_logged_out_selectors() == []

    def test_verify_login_no_dashboard(self):
        class MyHandler(SiteHandlerPlugin):
            name = "test"
            def can_handle(self, url): return True  # noqa: E704
            def extract_session(self, ctx, url): return PluginResult(success=True)  # noqa: E704
            def inject_session(self, ctx, session): return PluginResult(success=True)  # noqa: E704
        h = MyHandler()
        result = h.verify_login(None)
        assert result.success is True
        assert result.data["logged_in"] is False
        assert result.data["method"] == "none"


# ─── Custom Handler Tests ──────────────────────────────────

class TestCustomSiteHandler:
    def _make_handler(self):
        class GoogleHandler(SiteHandlerPlugin):
            API_VERSION = "1.1.0"
            name = "google-handler"
            def can_handle(self, url):
                return "google.com" in url
            def extract_session(self, ctx, url):
                return PluginResult(success=True, data={"cookies": []})
            def inject_session(self, ctx, session):
                return PluginResult(success=True)
            def get_export_domains(self):
                return ["google.com", "accounts.google.com", "mail.google.com"]
            def get_critical_cookies(self):
                return ["SID", "HSID", "__Secure-1PSID"]
            def get_critical_storage(self):
                return {"local": {"https://mail.google.com": ["inbox_count"]}, "session": {}}
            def get_login_url(self):
                return "https://accounts.google.com/signin"
            def get_dashboard_url(self):
                return "https://mail.google.com"
            def get_session_check_url(self):
                return "https://labs.google/fx/api/auth/session"
            def get_logged_in_selectors(self):
                return ["img.gbii", "[data-email]"]
            def get_logged_out_selectors(self):
                return ["a[href*='accounts.google.com/SignIn']"]
        return GoogleHandler()

    def test_can_handle(self):
        h = self._make_handler()
        assert h.can_handle("https://mail.google.com") is True
        assert h.can_handle("https://github.com") is False

    def test_export_domains(self):
        h = self._make_handler()
        domains = h.get_export_domains()
        assert "google.com" in domains
        assert "mail.google.com" in domains
        assert len(domains) == 3

    def test_critical_cookies(self):
        h = self._make_handler()
        cookies = h.get_critical_cookies()
        assert "SID" in cookies
        assert "__Secure-1PSID" in cookies
        assert len(cookies) == 3

    def test_critical_storage(self):
        h = self._make_handler()
        storage = h.get_critical_storage()
        assert "https://mail.google.com" in storage["local"]
        assert "inbox_count" in storage["local"]["https://mail.google.com"]

    def test_login_url(self):
        h = self._make_handler()
        assert "accounts.google.com" in h.get_login_url()

    def test_dashboard_url(self):
        h = self._make_handler()
        assert "mail.google.com" in h.get_dashboard_url()

    def test_session_check_url(self):
        h = self._make_handler()
        assert "labs.google" in h.get_session_check_url()

    def test_logged_in_selectors(self):
        h = self._make_handler()
        selectors = h.get_logged_in_selectors()
        assert len(selectors) == 2
        assert "img.gbii" in selectors

    def test_extract_returns_plugin_result(self):
        h = self._make_handler()
        result = h.extract_session(None, "https://mail.google.com")
        assert isinstance(result, PluginResult)
        assert result.success is True

    def test_inject_returns_plugin_result(self):
        h = self._make_handler()
        result = h.inject_session(None, {"cookies": []})
        assert isinstance(result, PluginResult)
        assert result.success is True


# ─── GitHub Handler Tests ──────────────────────────────────

class TestGitHubHandlerV2:
    def _make_handler(self):
        class GitHubHandler(SiteHandlerPlugin):
            API_VERSION = "1.1.0"
            name = "github-handler"
            def can_handle(self, url):
                return "github.com" in url
            def extract_session(self, ctx, url):
                return PluginResult(success=True, data={"cookies": []})
            def inject_session(self, ctx, session):
                return PluginResult(success=True)
            def get_export_domains(self):
                return ["github.com", ".github.com", "gist.github.com"]
            def get_critical_cookies(self):
                return ["user_session", "__Host-user_session_same_site", "logged_in"]
            def get_login_url(self):
                return "https://github.com/login"
            def get_dashboard_url(self):
                return "https://github.com"
            def get_logged_in_selectors(self):
                return ["img.avatar", "[data-testid='header-avatar']"]
            def get_logged_out_selectors(self):
                return ["a[href='/login']"]
        return GitHubHandler()

    def test_export_domains(self):
        h = self._make_handler()
        assert "github.com" in h.get_export_domains()
        assert "gist.github.com" in h.get_export_domains()

    def test_critical_cookies(self):
        h = self._make_handler()
        assert "user_session" in h.get_critical_cookies()
        assert "logged_in" in h.get_critical_cookies()

    def test_login_url(self):
        h = self._make_handler()
        assert "github.com/login" in h.get_login_url()

    def test_selectors(self):
        h = self._make_handler()
        assert "img.avatar" in h.get_logged_in_selectors()
        assert "a[href='/login']" in h.get_logged_out_selectors()


# ─── Discord Handler Tests ─────────────────────────────────

class TestDiscordHandlerV2:
    def _make_handler(self):
        class DiscordHandler(SiteHandlerPlugin):
            API_VERSION = "1.1.0"
            name = "discord-handler"
            def can_handle(self, url):
                return "discord.com" in url
            def extract_session(self, ctx, url):
                return PluginResult(success=True, data={"cookies": []})
            def inject_session(self, ctx, session):
                return PluginResult(success=True)
            def get_export_domains(self):
                return ["discord.com", ".discord.com", "discordapp.com"]
            def get_critical_storage(self):
                return {"local": {"https://discord.com": ["token"]}, "session": {}}
            def get_login_url(self):
                return "https://discord.com/login"
            def get_dashboard_url(self):
                return "https://discord.com/channels/@me"
            def get_logged_in_selectors(self):
                return ["[data-list-item-id='guildsnav']"]
            def get_logged_out_selectors(self):
                return ["button[type='submit']"]
        return DiscordHandler()

    def test_export_domains(self):
        h = self._make_handler()
        assert "discord.com" in h.get_export_domains()

    def test_critical_storage(self):
        h = self._make_handler()
        storage = h.get_critical_storage()
        assert "https://discord.com" in storage["local"]
        assert "token" in storage["local"]["https://discord.com"]

    def test_login_url(self):
        h = self._make_handler()
        assert "discord.com/login" in h.get_login_url()


# ─── Telegram Handler Tests ────────────────────────────────

class TestTelegramHandler:
    def _make_handler(self):
        class TelegramHandler(SiteHandlerPlugin):
            API_VERSION = "1.1.0"
            name = "telegram-handler"
            def can_handle(self, url):
                return "telegram.org" in url
            def extract_session(self, ctx, url):
                return PluginResult(success=True, data={"cookies": [], "storage": {"local": {"https://web.telegram.org": {"tg_user": "test"}}}})
            def inject_session(self, ctx, session):
                return PluginResult(success=True)
            def get_export_domains(self):
                return ["web.telegram.org"]
            def get_critical_storage(self):
                return {"local": {"https://web.telegram.org": ["tg_user", "tg_session"]}, "session": {}}
            def get_login_url(self):
                return "https://web.telegram.org/"
            def get_logged_in_selectors(self):
                return [".chat-list"]
            def get_logged_out_selectors(self):
                return [".auth-form"]
        return TelegramHandler()

    def test_export_domains(self):
        h = self._make_handler()
        assert "web.telegram.org" in h.get_export_domains()

    def test_critical_storage(self):
        h = self._make_handler()
        storage = h.get_critical_storage()
        assert "tg_user" in storage["local"]["https://web.telegram.org"]
        assert "tg_session" in storage["local"]["https://web.telegram.org"]

    def test_extract_includes_storage(self):
        h = self._make_handler()
        result = h.extract_session(None, "https://web.telegram.org")
        assert result.success is True
        assert "tg_user" in result.data["storage"]["local"]["https://web.telegram.org"]


# ─── Reddit Handler Tests ──────────────────────────────────

class TestRedditHandler:
    def _make_handler(self):
        class RedditHandler(SiteHandlerPlugin):
            API_VERSION = "1.1.0"
            name = "reddit-handler"
            def can_handle(self, url):
                return "reddit.com" in url
            def extract_session(self, ctx, url):
                return PluginResult(success=True, data={"cookies": []})
            def inject_session(self, ctx, session):
                return PluginResult(success=True)
            def get_export_domains(self):
                return ["reddit.com", ".reddit.com", "old.reddit.com"]
            def get_critical_cookies(self):
                return ["reddit_session", "token", "session"]
            def get_login_url(self):
                return "https://www.reddit.com/login/"
            def get_dashboard_url(self):
                return "https://www.reddit.com"
            def get_logged_in_selectors(self):
                return ["#header-account-action-button"]
            def get_logged_out_selectors(self):
                return ["a[href='/login']"]
        return RedditHandler()

    def test_export_domains(self):
        h = self._make_handler()
        assert "reddit.com" in h.get_export_domains()
        assert "old.reddit.com" in h.get_export_domains()

    def test_critical_cookies(self):
        h = self._make_handler()
        assert "reddit_session" in h.get_critical_cookies()
        assert "token" in h.get_critical_cookies()
