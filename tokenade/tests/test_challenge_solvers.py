"""
Tests for challenge solvers: CloakBrowserAutoSolver (stealth auto-solve),
ExternalSolverPlugin API flow (2captcha / CapSolver), and the ChallengeSolver
orchestrator.
"""

from tokenade.core.integration.challenge_solver import (
    CapSolverSolverPlugin,
    ChallengeSolver,
    CloakBrowserAutoSolver,
    TwoCaptchaSolverPlugin,
)
from tokenade.plugin import ChallengeSolverPlugin
from tokenade.plugin.api import PluginResult


class FakeCtx:
    def __init__(self, page):
        self.page = page

    def cookies(self):
        if self.page._cleared():
            return [{"name": n} for n in self.page.cookie_names]
        return []


class FakePage:
    """Duck-typed Playwright page for solver tests.

    Artifacts (token / cookies) appear once polls >= clear_at_poll, or
    immediately when clear_at_poll is None and an artifact is set.
    """

    def __init__(self, token="", cookie_names=None, clear_at_poll=None,
                 reload_clears=False):
        self.token = token
        self.cookie_names = list(cookie_names or [])
        self.clear_at_poll = clear_at_poll
        self.reload_clears = reload_clears
        self.polls = 0
        self.reloads = 0
        self.clicked_checkbox = False

    def _cleared(self):
        return self.clear_at_poll is None or self.polls >= self.clear_at_poll

    def evaluate(self, js, *args):
        if "cf-turnstile-response" in js:
            return self.token if self._cleared() else ""
        if "challenges.cloudflare.com" in js:
            self.clicked_checkbox = True
            return True
        return False

    def wait_for_timeout(self, ms):
        self.polls += 1

    def reload(self, **kw):
        self.reloads += 1
        if self.reload_clears:
            self.clear_at_poll = 0

    @property
    def context(self):
        return FakeCtx(self)


class TestCloakBrowserAutoSolver:
    def test_solves_when_token_appears(self):
        page = FakePage(token="tok_" + "x" * 200, clear_at_poll=3)
        solver = CloakBrowserAutoSolver(wait_timeout_s=5, poll_interval_s=0.01)
        res = solver.solve(page, {"provider": "cloudflare", "challenge_type": "turnstile"})
        assert res.success is True
        assert res.data["solved"] is True
        assert res.data["token"].startswith("tok_")
        assert res.data["method"] == "stealth"
        assert res.data["elapsed_s"] >= 0

    def test_solves_when_clearance_cookie_drops(self):
        page = FakePage(cookie_names=["__cf_bm"], clear_at_poll=2)
        solver = CloakBrowserAutoSolver(wait_timeout_s=5, poll_interval_s=0.01)
        res = solver.solve(page, {"provider": "cloudflare", "challenge_type": "managed_challenge"})
        assert res.success is True
        assert any(c["name"] == "__cf_bm" for c in res.data["clearance_cookies"])

    def test_solves_after_reload(self):
        page = FakePage(token="cleared-after-reload-token-abcdefghijklmnopqrstuvwxyz0123456789",
                        clear_at_poll=10**9, reload_clears=True)
        solver = CloakBrowserAutoSolver(wait_timeout_s=0.3, poll_interval_s=0.01,
                                        reload_attempts=1)
        res = solver.solve(page, {"provider": "cloudflare", "challenge_type": "managed_challenge"})
        assert res.success is True
        assert page.reloads == 1
        assert res.data["token"].startswith("cleared-after-reload")

    def test_clicks_interactive_checkbox(self):
        page = FakePage(token="tok_" + "x" * 200, clear_at_poll=1)
        solver = CloakBrowserAutoSolver(wait_timeout_s=1, poll_interval_s=0.01)
        solver.solve(page, {"provider": "cloudflare", "challenge_type": "turnstile"})
        assert page.clicked_checkbox is True

    def test_fails_when_challenge_persists(self):
        page = FakePage(clear_at_poll=10**9)
        solver = CloakBrowserAutoSolver(wait_timeout_s=0.3, poll_interval_s=0.01,
                                        reload_attempts=1)
        res = solver.solve(page, {"provider": "cloudflare", "challenge_type": "turnstile"})
        assert res.success is False
        assert res.data["solved"] is False
        assert "did not clear" in (res.error or "")

    def test_can_solve_matching_types(self):
        solver = CloakBrowserAutoSolver()
        assert solver.can_solve("turnstile", "cloudflare") is True
        assert solver.can_solve("managed_challenge", "cloudflare") is True
        assert solver.can_solve("datadome_captcha", "datadome") is True
        assert solver.can_solve("akamai_interstitial", "akamai") is False

    def test_min_wait_holds_verification_window(self):
        page = FakePage(token="tok_" + "x" * 200)
        progress = []
        solver = CloakBrowserAutoSolver(wait_timeout_s=5, poll_interval_s=0.05,
                                        min_wait_s=0.4,
                                        progress_cb=lambda s: progress.append(s))
        res = solver.solve(page, {"provider": "cloudflare", "challenge_type": "turnstile"})
        assert res.success is True
        assert res.data["elapsed_s"] >= 0.4
        assert len(progress) >= 3
        assert res.data["verified"] is True

    def test_min_wait_does_not_delay_unsolved_challenge(self):
        page = FakePage(clear_at_poll=10**9)
        solver = CloakBrowserAutoSolver(wait_timeout_s=0.2, poll_interval_s=0.01,
                                        min_wait_s=0.5, reload_attempts=0)
        res = solver.solve(page, {"provider": "cloudflare", "challenge_type": "turnstile"})
        assert res.success is False
        assert res.data["elapsed_s"] < 1.0


class TestExternalSolvers:
    def test_requires_api_key(self):
        solver = TwoCaptchaSolverPlugin(api_key="")
        res = solver.solve(None, {"challenge_type": "turnstile"})
        assert res.success is False
        assert "api_key" in (res.error or "")

    def test_2captcha_full_flow(self, monkeypatch):
        solver = TwoCaptchaSolverPlugin(api_key="key123", poll_interval_s=0.01,
                                        max_wait_s=5)
        calls = {"n": 0}

        def fake_http(url, payload):
            if "in.php" in url:
                return {"status": 1, "request": "task_42"}
            calls["n"] += 1
            if calls["n"] <= 1:
                return {"status": 0, "request": "CAPCHA_NOT_READY"}
            return {"status": 1, "request": "TOKEN_" + "y" * 150}

        monkeypatch.setattr(solver, "_http_json", fake_http)
        res = solver.solve(None, {"challenge_type": "turnstile",
                                  "details": {"sitekey": "0x4AAAAAA"}})
        assert res.success is True
        assert res.data["token"].startswith("TOKEN_")
        assert res.data["method"] == "2captcha-solver"

    def test_capsolver_full_flow(self, monkeypatch):
        solver = CapSolverSolverPlugin(api_key="ck_123", poll_interval_s=0.01,
                                       max_wait_s=5)
        calls = {"n": 0}

        def fake_http(url, payload):
            if "createTask" in url:
                return {"taskId": "tid_9"}
            calls["n"] += 1
            if calls["n"] <= 1:
                return {"status": "processing"}
            return {"status": "ready", "solution": {"token": "CAP_" + "z" * 150}}

        monkeypatch.setattr(solver, "_http_json", fake_http)
        res = solver.solve(None, {"challenge_type": "turnstile",
                                  "details": {"sitekey": "0x4AAAAAA"}})
        assert res.success is True
        assert res.data["token"].startswith("CAP_")

    def test_sitekey_extraction_from_html(self):
        html = '<div class="cf-turnstile" data-sitekey="0x4AAAAAAAGhYbwMOGHiaL4f"></div>'
        assert TwoCaptchaSolverPlugin._sitekey_from_html(html) == "0x4AAAAAAAGhYbwMOGHiaL4f"

    def test_verify_solution_token(self):
        page = FakePage(token="tok_" + "x" * 200)
        solver = TwoCaptchaSolverPlugin(api_key="k")
        assert solver.verify_solution(page) is True

    def test_verify_solution_cookie(self):
        page = FakePage(cookie_names=["cf_clearance"])
        solver = TwoCaptchaSolverPlugin(api_key="k")
        assert solver.verify_solution(page) is True


class TestChallengeSolverOrchestrator:
    def test_auto_fails_then_external_solves(self, monkeypatch):
        class FailingAuto(ChallengeSolverPlugin):
            name = "failing-auto"

            def can_solve(self, challenge_type, provider=""):
                return True

            def solve(self, page, challenge_data):
                return PluginResult(success=False, data={"solved": False},
                                    error="auto failed")

        class WinningExternal(ChallengeSolverPlugin):
            name = "winning-external"

            def can_solve(self, challenge_type, provider=""):
                return True

            def solve(self, page, challenge_data):
                return PluginResult(success=True, data={
                    "solved": True, "token": "WIN_123", "method": "winning-external"})

            def verify_solution(self, page):
                return True

        page = FakePage(token="WIN_123")
        solver = ChallengeSolver(auto_solver=FailingAuto(), external=[WinningExternal()],
                                 verify=True)
        res = solver.solve(page, {"challenge_type": "turnstile", "provider": "cloudflare"})
        assert res.success is True
        assert res.data["token"] == "WIN_123"
        assert res.data["attempts"][0]["solver"] == "failing-auto"
        assert res.data["verified"] is True

    def test_no_solver_supports_challenge(self):
        class Picky(ChallengeSolverPlugin):
            name = "picky"

            def can_solve(self, challenge_type, provider=""):
                return False

            def solve(self, page, challenge_data):
                raise AssertionError("should not be called")

        solver = ChallengeSolver(auto_solver=Picky(), external=[])
        res = solver.solve(None, {"challenge_type": "akamai_interstitial",
                                  "provider": "akamai"})
        assert res.success is False
        assert "no solver" in (res.error or "").lower()
