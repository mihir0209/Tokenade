"""
Tests for ChallengeGuard: the detect -> solve loop that auto-mitigates
anti-bot challenges during browser navigation, and its wiring into
PlaywrightBrowserManager.navigate.
"""

import time

import pytest

from tokenade.core.browser.challenge_guard import (
    ChallengeError,
    ChallengeGuard,
    detect_on_page,
)
from tokenade.core.browser.manager import BrowserFactory, BrowserManager
from tokenade.plugin.api import PluginResult

CHALLENGE_HTML = (
    "<html><title>Just a moment...</title>"
    "<body><div class='cf-challenge'>Verify you are human</div></body></html>"
)


class FakePage:
    """Duck-typed Playwright page with a switchable html body."""

    def __init__(self, html="", url="https://example.com/"):
        self._html = html
        self._url = url
        self.goto_calls = []
        self.reload_calls = 0

    def content(self):
        return self._html

    def title(self):
        if "<title>" in self._html:
            start = self._html.index("<title>") + 7
            end = self._html.index("</title>")
            return self._html[start:end]
        return ""

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append(url)
        return {"ok": True}

    def url(self):
        return self._url

    @property
    def context(self):
        return self

    def cookies(self):
        return []


class FakeSolver:
    """Solver stub: solves N times then reports failure, or always succeeds."""

    def __init__(self, solve_ok=True, solved=True):
        self.solve_ok = solve_ok
        self.solved = solved
        self.calls = []

    def solve(self, page, detection):
        self.calls.append(detection)
        if self.solve_ok:
            return PluginResult(success=True,
                                data={"solved": self.solved, "method": "stealth"})
        return PluginResult(success=False, error="simulated solve failure")


class TestDetectOnPage:
    def test_detects_cloudflare_challenge_html(self):
        page = FakePage(html=CHALLENGE_HTML)
        result = detect_on_page(page)
        assert result["detected"] is True
        assert result["provider"] == "cloudflare"
        assert "all" in result

    def test_clean_page_not_detected(self):
        page = FakePage(html="<html><title>Home</title><body>Hello</body></html>")
        result = detect_on_page(page)
        assert result["detected"] is False
        assert result["challenge_type"] == "none"

    def test_tolerates_broken_page(self):
        class BrokenPage:
            def content(self):
                raise RuntimeError("navigated away")

            def title(self):
                raise RuntimeError("navigated away")

            @property
            def context(self):
                raise RuntimeError("navigated away")

        result = detect_on_page(BrokenPage())
        assert result["detected"] is False


class TestChallengeGuard:
    def test_navigate_solves_challenge_and_returns_response(self):
        page = FakePage(html=CHALLENGE_HTML)
        solver = FakeSolver()
        solved_urls = []
        guard = ChallengeGuard(page, solver=solver, settle_s=0,
                               on_solve=lambda u, d, r: solved_urls.append(u))
        response = guard.navigate("https://example.com/protected")
        assert response == {"ok": True}
        assert page.goto_calls == ["https://example.com/protected"]
        assert solver.calls and solver.calls[0]["detected"] is True
        assert solved_urls == ["https://example.com/protected"]

    def test_navigate_retries_until_challenge_clears(self):
        page = FakePage(html=CHALLENGE_HTML)

        class FlipPage(FakePage):
            def __init__(self):
                super().__init__(html=CHALLENGE_HTML)
                self._cleared_on = 2

            def goto(self, url, wait_until=None, timeout=None):
                super().goto(url, wait_until=wait_until, timeout=timeout)
                if len(self.goto_calls) >= self._cleared_on:
                    self._html = "<html><title>Home</title></html>"

        flip = FlipPage()
        solver = FakeSolver(solve_ok=False)
        guard = ChallengeGuard(flip, solver=solver, settle_s=0, max_attempts=3)
        guard.navigate("https://example.com/protected")
        assert len(flip.goto_calls) == 2  # initial + one retry

    def test_navigate_raises_when_challenge_sticks(self):
        page = FakePage(html=CHALLENGE_HTML)
        solver = FakeSolver(solve_ok=False)
        guard = ChallengeGuard(page, solver=solver, settle_s=0,
                               max_attempts=2, raise_on_failure=True)
        with pytest.raises(ChallengeError):
            guard.navigate("https://example.com/protected")
        assert len(page.goto_calls) == 3  # initial + one retry per failed solve

    def test_navigate_disabled_behaves_like_goto(self):
        page = FakePage(html=CHALLENGE_HTML)
        solver = FakeSolver()
        guard = ChallengeGuard(page, solver=solver, enabled=False)
        guard.navigate("https://example.com/protected")
        assert solver.calls == []

    def test_try_mitigate_returns_none_on_clean_page(self):
        page = FakePage(html="<html><title>Home</title></html>")
        solver = FakeSolver()
        guard = ChallengeGuard(page, solver=solver, settle_s=0)
        assert guard.try_mitigate() is None
        assert solver.calls == []

    def test_try_mitigate_solves_challenged_page(self):
        page = FakePage(html=CHALLENGE_HTML)
        solver = FakeSolver()
        guard = ChallengeGuard(page, solver=solver, settle_s=0)
        result = guard.try_mitigate("https://example.com/protected")
        assert result is not None
        assert result.success is True
        assert result.data["solved"] is True
        assert result.data["provider"] == "cloudflare"
        assert result.data["challenge_type"]


class TestManagerAutoWire:
    def test_navigate_runs_guard_when_cloak_active(self, monkeypatch):
        mgr = BrowserFactory.create(browser_type="cloakbrowser")
        mgr._uses_cloak = True
        called = []
        results = []

        class StubGuard:
            def __init__(self, page):
                self.page = page

            def try_mitigate(self, url, settle_s=None):
                called.append((url, settle_s))
                return PluginResult(success=True,
                                    data={"solved": True, "method": "stealth"})

        import tokenade.core.browser.challenge_guard as guard_mod
        monkeypatch.setattr(guard_mod, "ChallengeGuard", StubGuard)

        class FakePageMgr:
            def goto(self, url, wait_until=None, timeout=None):
                return "response"

        mgr._page = FakePageMgr()
        response = mgr.navigate("https://nowsecure.nl", timeout=15000)
        assert response == "response"
        assert called == [("https://nowsecure.nl", 1.0)]

    def test_navigate_skips_guard_without_cloak(self, monkeypatch):
        mgr = BrowserFactory.create(browser_type="cloakbrowser")
        mgr._uses_cloak = False
        called = []

        class StubGuard:
            def __init__(self, page):
                pass

            def try_mitigate(self, url, settle_s=None):
                called.append(url)
                return None

        import tokenade.core.browser.challenge_guard as guard_mod
        monkeypatch.setattr(guard_mod, "ChallengeGuard", StubGuard)

        class FakePageMgr:
            def goto(self, url, wait_until=None, timeout=None):
                return "response"

        mgr._page = FakePageMgr()
        assert mgr.navigate("https://nowsecure.nl") == "response"
        assert called == []

    def test_navigate_auto_solve_disabled_skips_guard(self, monkeypatch):
        mgr = BrowserFactory.create(browser_type="cloakbrowser",
                                    auto_solve_challenges=False)
        mgr._uses_cloak = True
        called = []

        class StubGuard:
            def __init__(self, page):
                pass

            def try_mitigate(self, url, settle_s=None):
                called.append(url)
                return None

        import tokenade.core.browser.challenge_guard as guard_mod
        monkeypatch.setattr(guard_mod, "ChallengeGuard", StubGuard)

        class FakePageMgr:
            def goto(self, url, wait_until=None, timeout=None):
                return "response"

        mgr._page = FakePageMgr()
        assert mgr.navigate("https://nowsecure.nl") == "response"
        assert called == []

    def test_navigate_tolerates_guard_failure(self, monkeypatch):
        mgr = BrowserFactory.create(browser_type="cloakbrowser")
        mgr._uses_cloak = True

        class BrokenGuard:
            def __init__(self, page):
                raise RuntimeError("guard exploded")

        import tokenade.core.browser.challenge_guard as guard_mod
        monkeypatch.setattr(guard_mod, "ChallengeGuard", BrokenGuard)

        class FakePageMgr:
            def goto(self, url, wait_until=None, timeout=None):
                return "response"

        mgr._page = FakePageMgr()
        assert mgr.navigate("https://nowsecure.nl") == "response"
