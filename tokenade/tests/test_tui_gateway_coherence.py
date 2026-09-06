"""Gateway TUI coherence: Active vs Dropdown Selected, guards, cleanup.

Covers the `.agent/gateway/tui-ux.md` slice without running Textual:
action labels name their target, Open requires an active Session, Lease and
Release fall back to the active Session, and Force Cleanup sends `force`.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from tokenade.tui.views.gateway import (
    GATEWAY_ACTIONS,
    GATEWAY_ADVANCED_ACTIONS,
    GATEWAY_SCOPE_HELP,
)


def _button_event(button_id):
    return SimpleNamespace(button=SimpleNamespace(id=button_id))


def _gateway_app(monkeypatch, selector_value="", active_session=None):
    from tokenade.tui.app import TokenadeTUI

    app = TokenadeTUI()
    widget = MagicMock()
    widget.value = selector_value
    app.query_one = MagicMock(return_value=widget)
    app._gateway_run_http = MagicMock()
    app.notify = MagicMock()
    app._gateway_status_data = (
        {"active_session": active_session} if active_session else {}
    )
    return app


class TestGatewayActionLabels:
    def test_actions_name_active_vs_dropdown_targets(self):
        labels = {button_id: label for label, button_id, _ in GATEWAY_ACTIONS}
        assert labels["gateway-route-select"] == "Select Dropdown Session"
        assert labels["gateway-open-tab"] == "Open Active Session"
        assert labels["gateway-next-tab"] == "Route Next and Open"
        assert labels["gateway-select-tab"] == "Select Dropdown and Open"
        assert labels["gateway-lease"] == "Lease Active or Selected"
        assert labels["gateway-release"] == "Release Active Lease"
        assert labels["gateway-drain"] == "Cleanup Inactive Contexts"

    def test_force_cleanup_is_separate_advanced_action(self):
        assert ("Force Cleanup", "gateway-drain-force", "error") in GATEWAY_ADVANCED_ACTIONS
        assert "gateway-drain-force" not in {
            button_id for _, button_id, _ in GATEWAY_ACTIONS
        }

    def test_scope_help_states_visible_browser_effect(self):
        assert "no visible navigation" in GATEWAY_SCOPE_HELP
        assert "active Session only" in GATEWAY_SCOPE_HELP
        assert "visibly open" in GATEWAY_SCOPE_HELP


class TestGatewayButtonGuards:
    def test_open_without_active_session_warns_and_skips_http(self):
        app = _gateway_app(MagicMock(), selector_value="/tmp/a.tokenade")
        app.handle_button(_button_event("gateway-open-tab"))

        app.notify.assert_called_once()
        assert "active" in str(app.notify.call_args).lower()
        app._gateway_run_http.assert_not_called()

    def test_open_with_active_session_posts_tabs_new(self):
        app = _gateway_app(
            MagicMock(),
            selector_value="",
            active_session={"path": "/tmp/a.tokenade", "id": "abc"},
        )
        app._gateway_open_payload = MagicMock(
            return_value={"window_policy": "reuse-active-window"}
        )
        app.handle_button(_button_event("gateway-open-tab"))

        app._gateway_run_http.assert_called_once_with(
            "open active session",
            "POST",
            "/tabs/new",
            {"window_policy": "reuse-active-window"},
        )

    def test_lease_without_dropdown_leases_active_session(self):
        app = _gateway_app(
            MagicMock(),
            selector_value="",
            active_session={"path": "/tmp/a.tokenade", "id": "abc"},
        )
        app.handle_button(_button_event("gateway-lease"))

        app._gateway_run_http.assert_called_once_with(
            "lease active",
            "POST",
            "/contexts/lease",
            {"ttl_seconds": 900, "leased_by": "tui"},
        )

    def test_lease_with_dropdown_leases_selected_session(self):
        app = _gateway_app(MagicMock(), selector_value="/tmp/b.tokenade")
        app.handle_button(_button_event("gateway-lease"))

        app._gateway_run_http.assert_called_once_with(
            "lease selected",
            "POST",
            "/contexts/lease",
            {
                "path": "/tmp/b.tokenade",
                "ttl_seconds": 900,
                "leased_by": "tui",
            },
        )

    def test_release_without_any_session_warns_and_skips_http(self):
        app = _gateway_app(MagicMock(), selector_value="")
        app.handle_button(_button_event("gateway-release"))

        app.notify.assert_called_once()
        app._gateway_run_http.assert_not_called()

    def test_release_with_active_only_releases_active_lease(self):
        app = _gateway_app(
            MagicMock(),
            selector_value="",
            active_session={"path": "/tmp/a.tokenade", "id": "abc"},
        )
        app.handle_button(_button_event("gateway-release"))

        app._gateway_run_http.assert_called_once_with(
            "release active lease", "POST", "/contexts/release", {}
        )

    def test_cleanup_and_force_cleanup_payloads(self):
        app = _gateway_app(MagicMock(), selector_value="")
        app.handle_button(_button_event("gateway-drain"))
        app.handle_button(_button_event("gateway-drain-force"))

        assert app._gateway_run_http.call_count == 2
        app._gateway_run_http.assert_any_call(
            "cleanup inactive contexts", "POST", "/contexts/drain", {}
        )
        app._gateway_run_http.assert_any_call(
            "force cleanup inactive contexts",
            "POST",
            "/contexts/drain",
            {"force": True},
        )


class TestPlaywrightBrowserTypeMapping:
    """`browser_type="playwright"` (as sent by the gateway runtime factory)
    must resolve to the Playwright chromium backend, not AttributeError."""

    def test_playwright_type_launches_chromium(self):
        from unittest.mock import MagicMock, patch

        from tokenade.core.browser.manager import (
            BrowserConfig,
            PlaywrightBrowserManager,
        )

        config = BrowserConfig(browser_type="playwright", headless=True)
        manager = PlaywrightBrowserManager(config)

        mock_playwright = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        with patch("playwright.sync_api.sync_playwright") as mock_sp:
            mock_sp.return_value.start.return_value = mock_playwright
            mock_playwright.chromium.launch.return_value = mock_browser
            page = manager.launch()

        assert page is mock_page
        mock_playwright.chromium.launch.assert_called_once()
