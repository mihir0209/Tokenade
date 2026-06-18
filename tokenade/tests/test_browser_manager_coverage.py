"""Comprehensive tests for browser.manager module - coverage boost."""

import pytest
from unittest.mock import patch, MagicMock

from tokenade.core.browser.manager import (
    BrowserConfig,
    BrowserManager,
    PlaywrightBrowserManager,
    BrowserFactory,
)


# ---------------------------------------------------------------------------
# BrowserConfig tests
# ---------------------------------------------------------------------------

class TestBrowserConfig:
    def test_defaults(self):
        cfg = BrowserConfig()
        assert cfg.browser_type == "chromium"
        assert cfg.headless is True
        assert cfg.user_data_dir is None
        assert cfg.executable_path is None
        assert cfg.channel is None
        assert cfg.viewport == {"width": 1920, "height": 1080}
        assert cfg.env is None
        assert cfg.proxy is None
        assert cfg.disable_blink_features is True
        assert cfg.no_sandbox is True
        assert cfg.disable_dev_shm_usage is True
        assert cfg.no_first_run is True
        assert cfg.no_default_browser_check is True
        assert cfg.fingerprint is None
        assert cfg.stealth_level == "maximum"

    def test_post_init_adds_default_args(self):
        cfg = BrowserConfig()
        assert "--no-sandbox" in cfg.args
        assert "--disable-dev-shm-usage" in cfg.args
        assert "--no-first-run" in cfg.args
        assert "--no-default-browser-check" in cfg.args
        assert "--disable-blink-features=AutomationControlled" in cfg.args

    def test_post_init_adds_enable_automation_to_ignore(self):
        cfg = BrowserConfig()
        assert "--enable-automation" in cfg.ignore_default_args

    def test_post_init_no_sandbox_false(self):
        cfg = BrowserConfig(no_sandbox=False)
        assert "--no-sandbox" not in cfg.args

    def test_post_init_disable_dev_shm_false(self):
        cfg = BrowserConfig(disable_dev_shm_usage=False)
        assert "--disable-dev-shm-usage" not in cfg.args

    def test_post_init_no_first_run_false(self):
        cfg = BrowserConfig(no_first_run=False)
        assert "--no-first-run" not in cfg.args

    def test_post_init_no_default_browser_check_false(self):
        cfg = BrowserConfig(no_default_browser_check=False)
        assert "--no-default-browser-check" not in cfg.args

    def test_post_init_disable_blink_false(self):
        cfg = BrowserConfig(disable_blink_features=False)
        assert "--disable-blink-features=AutomationControlled" not in cfg.args

    def test_post_init_user_args_preserved(self):
        cfg = BrowserConfig(args=["--no-sandbox", "--custom-flag"])
        assert "--custom-flag" in cfg.args
        assert cfg.args.count("--no-sandbox") == 1  # no duplicate

    def test_post_init_user_args_override_default(self):
        cfg = BrowserConfig(args=["--no-sandbox=my-profile"])
        # The existing set check uses split("=")[0], so user's --no-sandbox takes precedence
        no_sandbox_args = [a for a in cfg.args if a.startswith("--no-sandbox")]
        assert len(no_sandbox_args) == 1
        assert no_sandbox_args[0] == "--no-sandbox=my-profile"

    def test_post_init_enable_automation_not_duplicated(self):
        cfg = BrowserConfig(ignore_default_args=["--enable-automation"])
        assert cfg.ignore_default_args.count("--enable-automation") == 1

    def test_custom_viewport(self):
        cfg = BrowserConfig(viewport={"width": 1280, "height": 720})
        assert cfg.viewport == {"width": 1280, "height": 720}

    def test_proxy_config(self):
        cfg = BrowserConfig(proxy={"server": "http://proxy:8080"})
        assert cfg.proxy["server"] == "http://proxy:8080"

    def test_env_config(self):
        cfg = BrowserConfig(env={"DISPLAY": ":0"})
        assert cfg.env["DISPLAY"] == ":0"

    def test_executable_path(self):
        cfg = BrowserConfig(executable_path="/usr/bin/chromium")
        assert cfg.executable_path == "/usr/bin/chromium"

    def test_channel(self):
        cfg = BrowserConfig(channel="chrome")
        assert cfg.channel == "chrome"

    def test_fingerprint_and_stealth_level(self):
        fp = {"user_agent": "Test"}
        cfg = BrowserConfig(fingerprint=fp, stealth_level="basic")
        assert cfg.fingerprint == fp
        assert cfg.stealth_level == "basic"

    def test_post_init_merges_multiple_existing_args(self):
        cfg = BrowserConfig(args=["--no-sandbox", "--disable-dev-shm-usage", "--extra"])
        assert cfg.args.count("--no-sandbox") == 1
        assert cfg.args.count("--disable-dev-shm-usage") == 1
        assert "--extra" in cfg.args

    def test_post_init_no_enable_automation_in_ignore_when_already_present(self):
        cfg = BrowserConfig(ignore_default_args=["--enable-automation", "--other"])
        assert cfg.ignore_default_args.count("--enable-automation") == 1


# ---------------------------------------------------------------------------
# BrowserManager abstract base class tests
# ---------------------------------------------------------------------------

class TestBrowserManagerABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BrowserManager(BrowserConfig())

    def test_is_active_false_initially(self):
        class DummyManager(BrowserManager):
            def launch(self):
                return None

            def close(self):
                pass

            def get_cookies(self, urls=None):
                return []

            def add_cookies(self, cookies):
                pass

            def navigate(self, url, wait_until="networkidle", timeout=30000):
                return None

            def evaluate(self, expression):
                return None

        mgr = DummyManager(BrowserConfig())
        assert mgr.is_active is False

    def test_is_active_true_when_context_set(self):
        class DummyManager(BrowserManager):
            def launch(self):
                return None

            def close(self):
                pass

            def get_cookies(self, urls=None):
                return []

            def add_cookies(self, cookies):
                pass

            def navigate(self, url, wait_until="networkidle", timeout=30000):
                return None

            def evaluate(self, expression):
                return None

        mgr = DummyManager(BrowserConfig())
        mgr._context = "something"
        assert mgr.is_active is True


# ---------------------------------------------------------------------------
# PlaywrightBrowserManager tests
# ---------------------------------------------------------------------------

class TestPlaywrightBrowserManager:
    def _make_manager(self, **kwargs):
        cfg = BrowserConfig(**kwargs)
        return PlaywrightBrowserManager(cfg)

    @patch("tokenade.core.browser.manager.PlaywrightBrowserManager.close")
    def test_launch_success(self, mock_close):
        mgr = self._make_manager(headless=True)
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page

        with patch("playwright.sync_api.sync_playwright") as mock_sp:
            mock_sp.return_value.start.return_value = mock_pw
            mock_pw.chromium.launch.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context

            page = mgr.launch()
            assert page == mock_page
            assert mgr._playwright == mock_pw
            assert mgr._browser == mock_browser
            assert mgr._context == mock_context

    @patch("tokenade.core.browser.manager.PlaywrightBrowserManager.close")
    def test_launch_with_executable_path(self, mock_close):
        mgr = self._make_manager(executable_path="/usr/bin/chrome")
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page

        with patch("playwright.sync_api.sync_playwright") as mock_sp:
            mock_sp.return_value.start.return_value = mock_pw
            mock_pw.chromium.launch.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context

            mgr.launch()
            launch_opts = mock_pw.chromium.launch.call_args[1]
            assert launch_opts["executable_path"] == "/usr/bin/chrome"

    @patch("tokenade.core.browser.manager.PlaywrightBrowserManager.close")
    def test_launch_with_channel(self, mock_close):
        mgr = self._make_manager(channel="chrome")
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page

        with patch("playwright.sync_api.sync_playwright") as mock_sp:
            mock_sp.return_value.start.return_value = mock_pw
            mock_pw.chromium.launch.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context

            mgr.launch()
            launch_opts = mock_pw.chromium.launch.call_args[1]
            assert launch_opts["channel"] == "chrome"

    @patch("tokenade.core.browser.manager.PlaywrightBrowserManager.close")
    def test_launch_with_proxy(self, mock_close):
        proxy = {"server": "http://proxy:8080"}
        mgr = self._make_manager(proxy=proxy)
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page

        with patch("playwright.sync_api.sync_playwright") as mock_sp:
            mock_sp.return_value.start.return_value = mock_pw
            mock_pw.chromium.launch.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context

            mgr.launch()
            launch_opts = mock_pw.chromium.launch.call_args[1]
            assert launch_opts["proxy"] == proxy

    @patch("tokenade.core.browser.manager.PlaywrightBrowserManager.close")
    def test_launch_persistent_context(self, mock_close):
        mgr = self._make_manager(user_data_dir="/tmp/profile")
        mock_pw = MagicMock()
        MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_context.pages = [mock_page]

        with patch("playwright.sync_api.sync_playwright") as mock_sp:
            mock_sp.return_value.start.return_value = mock_pw
            mock_pw.chromium.launch_persistent_context.return_value = mock_context

            page = mgr.launch()
            mock_pw.chromium.launch_persistent_context.assert_called_once()
            assert page == mock_page

    @patch("tokenade.core.browser.manager.PlaywrightBrowserManager.close")
    def test_launch_persistent_context_no_pages(self, mock_close):
        mgr = self._make_manager(user_data_dir="/tmp/profile")
        mock_pw = MagicMock()
        mock_context = MagicMock()
        mock_context.pages = []
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page

        with patch("playwright.sync_api.sync_playwright") as mock_sp:
            mock_sp.return_value.start.return_value = mock_pw
            mock_pw.chromium.launch_persistent_context.return_value = mock_context

            page = mgr.launch()
            mock_context.new_page.assert_called_once()
            assert page == mock_page

    @patch("tokenade.core.browser.manager.PlaywrightBrowserManager.close")
    def test_launch_with_env(self, mock_close):
        mgr = self._make_manager(env={"DISPLAY": ":0"})
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page

        with patch("playwright.sync_api.sync_playwright") as mock_sp:
            mock_sp.return_value.start.return_value = mock_pw
            mock_pw.chromium.launch.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context

            mgr.launch()
            ctx_opts = mock_browser.new_context.call_args[1]
            assert ctx_opts["env"] == {"DISPLAY": ":0"}

    @patch("tokenade.core.browser.manager.PlaywrightBrowserManager.close")
    def test_launch_with_fingerprint_dict(self, mock_close):
        fp = {
            "user_agent": "Test/1.0",
            "platform": "Linux",
            "language": "en-US",
            "languages": ["en-US"],
            "hardware_concurrency": 4,
            "device_memory": 8.0,
            "max_touch_points": 0,
            "screen_width": 1920,
            "screen_height": 1080,
            "device_pixel_ratio": 1.0,
            "color_depth": 24,
            "webgl_vendor": "Intel",
            "webgl_renderer": "HD",
        }
        mgr = self._make_manager(fingerprint=fp)
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page

        with patch("playwright.sync_api.sync_playwright") as mock_sp:
            with patch("tokenade.core.fingerprint.injector.inject_stealth_script") as mock_inject:
                mock_sp.return_value.start.return_value = mock_pw
                mock_pw.chromium.launch.return_value = mock_browser
                mock_browser.new_context.return_value = mock_context

                mgr.launch()
                mock_inject.assert_called_once()

    @patch("tokenade.core.browser.manager.PlaywrightBrowserManager.close")
    def test_launch_fingerprint_injection_failure_non_fatal(self, mock_close):
        fp = {
            "user_agent": "Test/1.0",
            "platform": "Linux",
            "language": "en-US",
            "languages": ["en-US"],
            "hardware_concurrency": 4,
            "device_memory": 8.0,
            "max_touch_points": 0,
            "screen_width": 1920,
            "screen_height": 1080,
            "device_pixel_ratio": 1.0,
            "color_depth": 24,
            "webgl_vendor": "Intel",
            "webgl_renderer": "HD",
        }
        mgr = self._make_manager(fingerprint=fp)
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page

        with patch("playwright.sync_api.sync_playwright") as mock_sp:
            with patch("tokenade.core.fingerprint.injector.inject_stealth_script", side_effect=Exception("inject fail")):
                mock_sp.return_value.start.return_value = mock_pw
                mock_pw.chromium.launch.return_value = mock_browser
                mock_browser.new_context.return_value = mock_context

                page = mgr.launch()
                assert page == mock_page  # launch still succeeds

    @patch("tokenade.core.browser.manager.PlaywrightBrowserManager.close")
    def test_launch_fingerprint_as_browser_fingerprint_object(self, mock_close):
        from tokenade.core.fingerprint.manager import BrowserFingerprint
        fp = BrowserFingerprint(user_agent="Obj/1.0", platform="Win")
        mgr = self._make_manager(fingerprint=fp)
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page

        with patch("playwright.sync_api.sync_playwright") as mock_sp:
            with patch("tokenade.core.fingerprint.injector.inject_stealth_script") as mock_inject:
                mock_sp.return_value.start.return_value = mock_pw
                mock_pw.chromium.launch.return_value = mock_browser
                mock_browser.new_context.return_value = mock_context

                mgr.launch()
                call_args = mock_inject.call_args
                assert call_args[0][1] == fp

    def test_launch_error_generic(self):
        mgr = self._make_manager()
        with patch("playwright.sync_api.sync_playwright") as mock_sp:
            mock_pw = mock_sp.return_value.start.return_value
            mock_pw.chromium.launch.side_effect = Exception("generic error")
            with pytest.raises(Exception):
                mgr.launch()

    def test_launch_error_timeout_hint(self):
        mgr = self._make_manager()
        mock_pw = MagicMock()
        mock_pw.chromium.launch.side_effect = Exception("Timeout error occurred")

        with patch("playwright.sync_api.sync_playwright") as mock_sp:
            mock_sp.return_value.start.return_value = mock_pw
            with pytest.raises(Exception):
                mgr.launch()

    def test_launch_error_port_in_use(self):
        mgr = self._make_manager()
        mock_pw = MagicMock()
        mock_pw.chromium.launch.side_effect = Exception("address already connected")

        with patch("playwright.sync_api.sync_playwright") as mock_sp:
            mock_sp.return_value.start.return_value = mock_pw
            with pytest.raises(Exception):
                mgr.launch()

    def test_launch_error_permission_denied(self):
        mgr = self._make_manager()
        mock_pw = MagicMock()
        mock_pw.chromium.launch.side_effect = Exception("Permission denied")

        with patch("playwright.sync_api.sync_playwright") as mock_sp:
            mock_sp.return_value.start.return_value = mock_pw
            with pytest.raises(Exception):
                mgr.launch()

    def test_launch_error_playwright_not_installed(self):
        mgr = self._make_manager()
        mock_pw = MagicMock()
        mock_pw.chromium.launch.side_effect = Exception("playwright is not installed")

        with patch("playwright.sync_api.sync_playwright") as mock_sp:
            mock_sp.return_value.start.return_value = mock_pw
            with pytest.raises(Exception):
                mgr.launch()

    def test_launch_error_not_found(self):
        mgr = self._make_manager()
        mock_pw = MagicMock()
        mock_pw.chromium.launch.side_effect = Exception("executable path not found")

        with patch("playwright.sync_api.sync_playwright") as mock_sp:
            mock_sp.return_value.start.return_value = mock_pw
            with pytest.raises(Exception):
                mgr.launch()

    def test_close_all_resources(self):
        mgr = self._make_manager()
        ctx = MagicMock()
        browser = MagicMock()
        pw = MagicMock()
        mgr._context = ctx
        mgr._browser = browser
        mgr._playwright = pw

        mgr.close()
        ctx.close.assert_called_once()
        browser.close.assert_called_once()
        pw.stop.assert_called_once()
        assert mgr._context is None
        assert mgr._browser is None
        assert mgr._playwright is None

    def test_close_with_exception(self):
        mgr = self._make_manager()
        ctx = MagicMock()
        ctx.close.side_effect = Exception("close failed")
        browser = MagicMock()
        pw = MagicMock()
        mgr._context = ctx
        mgr._browser = browser
        mgr._playwright = pw

        mgr.close()  # should not raise
        # context.close() raised, so _context remains set; browser and playwright not touched
        assert mgr._context is ctx
        assert mgr._browser is browser
        assert mgr._playwright is pw

    def test_close_no_resources(self):
        mgr = self._make_manager()
        mgr.close()  # should not raise

    def test_get_cookies(self):
        mgr = self._make_manager()
        mgr._context = MagicMock()
        mgr._context.cookies.return_value = [{"name": "test", "value": "val"}]

        cookies = mgr.get_cookies(["https://example.com"])
        assert len(cookies) == 1
        mgr._context.cookies.assert_called_once_with(["https://example.com"])

    def test_get_cookies_no_context_raises(self):
        mgr = self._make_manager()
        with pytest.raises(RuntimeError, match="not launched"):
            mgr.get_cookies()

    def test_add_cookies(self):
        mgr = self._make_manager()
        mgr._context = MagicMock()
        cookies = [{"name": "test", "value": "val"}]

        mgr.add_cookies(cookies)
        mgr._context.add_cookies.assert_called_once_with(cookies)

    def test_add_cookies_no_context_raises(self):
        mgr = self._make_manager()
        with pytest.raises(RuntimeError, match="not launched"):
            mgr.add_cookies([{"name": "x"}])

    def test_navigate(self):
        mgr = self._make_manager()
        mgr._page = MagicMock()
        mgr._page.goto.return_value = "response"

        resp = mgr.navigate("https://example.com")
        assert resp == "response"
        mgr._page.goto.assert_called_once_with(
            "https://example.com", wait_until="networkidle", timeout=30000
        )

    def test_navigate_custom_params(self):
        mgr = self._make_manager()
        mgr._page = MagicMock()

        mgr.navigate("https://example.com", wait_until="load", timeout=60000)
        mgr._page.goto.assert_called_once_with(
            "https://example.com", wait_until="load", timeout=60000
        )

    def test_navigate_no_page_raises(self):
        mgr = self._make_manager()
        with pytest.raises(RuntimeError, match="not launched"):
            mgr.navigate("https://example.com")

    def test_evaluate(self):
        mgr = self._make_manager()
        mgr._page = MagicMock()
        mgr._page.evaluate.return_value = 42

        result = mgr.evaluate("() => 42")
        assert result == 42
        mgr._page.evaluate.assert_called_once_with("() => 42")

    def test_evaluate_no_page_raises(self):
        mgr = self._make_manager()
        with pytest.raises(RuntimeError, match="not launched"):
            mgr.evaluate("() => 1")

    def test_evaluate_with_arg(self):
        mgr = self._make_manager()
        mgr._page = MagicMock()
        mgr._page.evaluate.return_value = "result"

        result = mgr.evaluate_with_arg("(x) => x + 1", 5)
        assert result == "result"
        mgr._page.evaluate.assert_called_once_with("(x) => x + 1", 5)

    def test_evaluate_with_arg_no_page_raises(self):
        mgr = self._make_manager()
        with pytest.raises(RuntimeError, match="not launched"):
            mgr.evaluate_with_arg("(x) => x", 1)

    def test_query_selector(self):
        mgr = self._make_manager()
        mgr._page = MagicMock()
        mgr._page.query_selector.return_value = "element"

        el = mgr.query_selector("#my-id")
        assert el == "element"
        mgr._page.query_selector.assert_called_once_with("#my-id")

    def test_query_selector_with_timeout(self):
        mgr = self._make_manager()
        mgr._page = MagicMock()
        mgr._page.wait_for_selector.return_value = "element"

        el = mgr.query_selector("#my-id", timeout=5000)
        assert el == "element"
        mgr._page.wait_for_selector.assert_called_once_with("#my-id", timeout=5000)

    def test_query_selector_no_page_raises(self):
        mgr = self._make_manager()
        with pytest.raises(RuntimeError, match="not launched"):
            mgr.query_selector("#id")

    def test_click(self):
        mgr = self._make_manager()
        mgr._page = MagicMock()
        mock_element = MagicMock()
        mgr._page.wait_for_selector.return_value = mock_element

        result = mgr.click("#btn")
        assert result == mock_element
        mock_element.click.assert_called_once()

    def test_click_no_element(self):
        mgr = self._make_manager()
        mgr._page = MagicMock()
        mgr._page.wait_for_selector.return_value = None

        result = mgr.click("#btn")
        assert result is None

    def test_click_no_page_raises(self):
        mgr = self._make_manager()
        with pytest.raises(RuntimeError, match="not launched"):
            mgr.click("#btn")

    def test_fill(self):
        mgr = self._make_manager()
        mgr._page = MagicMock()
        mock_element = MagicMock()
        mgr._page.wait_for_selector.return_value = mock_element

        result = mgr.fill("#input", "hello")
        assert result == mock_element
        mock_element.fill.assert_called_once_with("hello")

    def test_fill_no_element(self):
        mgr = self._make_manager()
        mgr._page = MagicMock()
        mgr._page.wait_for_selector.return_value = None

        result = mgr.fill("#input", "hello")
        assert result is None

    def test_fill_no_page_raises(self):
        mgr = self._make_manager()
        with pytest.raises(RuntimeError, match="not launched"):
            mgr.fill("#input", "val")


# ---------------------------------------------------------------------------
# BrowserFactory tests
# ---------------------------------------------------------------------------

class TestBrowserFactory:
    def test_create_default(self):
        mgr = BrowserFactory.create()
        assert isinstance(mgr, PlaywrightBrowserManager)
        assert mgr.config.browser_type == "chromium"

    def test_create_with_kwargs(self):
        mgr = BrowserFactory.create(headless=False, browser_type="firefox")
        assert mgr.config.headless is False
        assert mgr.config.browser_type == "firefox"

    def test_create_unknown_backend(self):
        with pytest.raises(ValueError, match="Unknown browser backend"):
            BrowserFactory.create(backend="selenium")

    def test_register_custom_backend(self):
        class CustomManager(BrowserManager):
            def launch(self):
                return None

            def close(self):
                pass

            def get_cookies(self, urls=None):
                return []

            def add_cookies(self, cookies):
                pass

            def navigate(self, url, wait_until="networkidle", timeout=30000):
                return None

            def evaluate(self, expression):
                return None

        BrowserFactory.register("custom", CustomManager)
        mgr = BrowserFactory.create(backend="custom")
        assert isinstance(mgr, CustomManager)
        # cleanup
        del BrowserFactory._registry["custom"]

    def test_detect_chrome_path_linux(self):
        with patch("platform.system", return_value="Linux"):
            with patch("os.path.exists", return_value=True):
                path = BrowserFactory.detect_chrome_path()
                assert path == "/usr/bin/google-chrome"

    def test_detect_chrome_path_linux_stable(self):
        with patch("platform.system", return_value="Linux"):
            def exists_side_effect(p):
                return p == "/usr/bin/google-chrome-stable"
            with patch("os.path.exists", side_effect=exists_side_effect):
                path = BrowserFactory.detect_chrome_path()
                assert path == "/usr/bin/google-chrome-stable"

    def test_detect_chrome_path_linux_chromium(self):
        with patch("platform.system", return_value="Linux"):
            def exists_side_effect(p):
                return p == "/usr/bin/chromium"
            with patch("os.path.exists", side_effect=exists_side_effect):
                path = BrowserFactory.detect_chrome_path()
                assert path == "/usr/bin/chromium"

    def test_detect_chrome_path_linux_chromium_browser(self):
        with patch("platform.system", return_value="Linux"):
            def exists_side_effect(p):
                return p == "/usr/bin/chromium-browser"
            with patch("os.path.exists", side_effect=exists_side_effect):
                path = BrowserFactory.detect_chrome_path()
                assert path == "/usr/bin/chromium-browser"

    def test_detect_chrome_path_windows(self):
        with patch("platform.system", return_value="Windows"):
            with patch("os.path.exists", return_value=True):
                path = BrowserFactory.detect_chrome_path()
                assert "chrome.exe" in path

    def test_detect_chrome_path_windows_x86(self):
        with patch("platform.system", return_value="Windows"):
            def exists_side_effect(p):
                return "x86" in p
            with patch("os.path.exists", side_effect=exists_side_effect):
                path = BrowserFactory.detect_chrome_path()
                assert "x86" in path

    def test_detect_chrome_path_mac(self):
        with patch("platform.system", return_value="Darwin"):
            with patch("os.path.exists", return_value=True):
                path = BrowserFactory.detect_chrome_path()
                assert "Google Chrome.app" in path

    def test_detect_chrome_path_mac_chromium(self):
        with patch("platform.system", return_value="Darwin"):
            def exists_side_effect(p):
                return "Chromium.app" in p
            with patch("os.path.exists", side_effect=exists_side_effect):
                path = BrowserFactory.detect_chrome_path()
                assert "Chromium.app" in path

    def test_detect_chrome_path_not_found(self):
        with patch("platform.system", return_value="Linux"):
            with patch("os.path.exists", return_value=False):
                path = BrowserFactory.detect_chrome_path()
                assert path is None

    def test_detect_chrome_path_unknown_os(self):
        with patch("platform.system", return_value="FreeBSD"):
            with patch("os.path.exists", return_value=False):
                path = BrowserFactory.detect_chrome_path()
                assert path is None

    def test_registry_contains_playwright(self):
        assert "playwright" in BrowserFactory._registry
        assert BrowserFactory._registry["playwright"] is PlaywrightBrowserManager
