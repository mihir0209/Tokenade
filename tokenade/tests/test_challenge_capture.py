"""
Tests for SolvedSessionCapturer: persisting the artifacts of a successful
challenge solve (cf_clearance, tokens) into a portable .tokenade file, and
its wiring into PlaywrightBrowserManager.navigate.
"""

from tokenade.core.integration.challenge_capture import (
    SolvedSessionCapturer,
    default_session_dir,
)
from tokenade.core.browser.manager import BrowserFactory
from tokenade.plugin.api import PluginResult


class FakePage:
    def __init__(self, cookies=None, origin="https://nowsecure.nl/"):
        self._cookies = list(cookies or [])
        self.origin = origin
        self.eval_called = False

    def evaluate(self, js):
        self.eval_called = True
        return {
            "user_agent": "CloakBrowser/0.4.11",
            "platform": "Linux x86_64",
            "languages": ["en-US"],
            "hardware_concurrency": 8,
        }

    @property
    def context(self):
        return self

    def cookies(self, url):
        return self._cookies


SOLVED_COOKIES = [
    {"name": "cf_clearance", "value": "abc123", "domain": "nowsecure.nl",
     "path": "/", "secure": True, "httpOnly": True},
    {"name": "__cf_bm", "value": "bm-value", "domain": ".nowsecure.nl",
     "path": "/", "secure": True, "httpOnly": True},
]


def solved_result(token="tok_" + "x" * 150, solved=True, elapsed=3.04):
    return PluginResult(
        success=True,
        data={"solved": solved, "token": token, "method": "stealth",
              "provider": "cloudflare", "elapsed_s": elapsed},
    )


class TestSolvedSessionCapturer:
    def test_capture_writes_loadable_tokenade_file(self, tmp_path):
        page = FakePage(cookies=SOLVED_COOKIES)
        capturer = SolvedSessionCapturer(output_dir=str(tmp_path), encrypt=False)
        path = capturer.capture(page, "https://nowsecure.nl", solved_result())

        assert path is not None
        assert path.name == "nowsecure.nl.tokenade"
        assert path.exists()

        from tokenade.core.importer.session_packager import SessionPackager
        package = SessionPackager().load(str(path))
        assert package["version"].startswith("3.")
        assert package["site_name"] == "nowsecure.nl"
        assert package["metadata"]["extraction_method"] == "challenge_solve"
        assert package["metadata"]["target_origin"] == "nowsecure.nl"
        names = {c["name"] for c in package["cookies"]}
        assert "cf_clearance" in names and "__cf_bm" in names
        assert package["tokens"][0]["name"] == "cf-turnstile-response"
        assert package["tokens"][0]["value"].startswith("tok_")
        assert package["fingerprint"]["user_agent"] == "CloakBrowser/0.4.11"
        assert package["metadata"]["challenge_provider"] == "cloudflare"
        assert package["metadata"]["solve_elapsed_s"] == 3.04

    def test_capture_skips_tokens_when_none_issued(self, tmp_path):
        page = FakePage(cookies=SOLVED_COOKIES)
        capturer = SolvedSessionCapturer(output_dir=str(tmp_path), encrypt=False)
        result = solved_result(token="")
        path = capturer.capture(page, "https://nowsecure.nl", result)
        assert path is not None
        from tokenade.core.importer.session_packager import SessionPackager
        package = SessionPackager().load(str(path))
        assert package["tokens"] == []

    def test_capture_drops_non_clearance_cookies(self, tmp_path):
        mixed = SOLVED_COOKIES + [
            {"name": "sessionid", "value": "user-login-state", "domain": "nowsecure.nl",
             "path": "/", "secure": True, "httpOnly": True},
            {"name": "datadome", "value": "dd-clearance", "domain": ".nowsecure.nl",
             "path": "/", "secure": True},
        ]
        page = FakePage(cookies=mixed)
        capturer = SolvedSessionCapturer(output_dir=str(tmp_path), encrypt=False)
        path = capturer.capture(page, "https://nowsecure.nl", solved_result())
        assert path is not None
        from tokenade.core.importer.session_packager import SessionPackager
        package = SessionPackager().load(str(path))
        names = {c["name"] for c in package["cookies"]}
        assert "cf_clearance" in names and "datadome" in names
        assert "sessionid" not in names

    def test_capture_never_raises_on_page_failure(self, tmp_path):
        class BrokenPage:
            @property
            def context(self):
                return self

            def cookies(self, url):
                raise RuntimeError("context gone")

        capturer = SolvedSessionCapturer(output_dir=str(tmp_path), encrypt=False)
        path = capturer.capture(BrokenPage(), "https://nowsecure.nl", solved_result())
        assert path is None

    def test_origin_parsing(self):
        assert SolvedSessionCapturer._origin_of("https://nowsecure.nl/") == "nowsecure.nl"
        assert SolvedSessionCapturer._origin_of(
            "https://labs.google/foo?bar=1") == "labs.google"

    def test_default_session_dir(self):
        assert str(default_session_dir()).endswith(".tokenade/sessions")


class TestManagerCaptureWiring:
    def _manager_with_stub_capture(self, monkeypatch, solve_result=None):
        import tokenade.core.browser.challenge_guard as guard_mod
        import tokenade.core.integration.challenge_capture as capture_mod

        class StubGuard:
            def __init__(self, page):
                pass

            def try_mitigate(self, url, settle_s=None):
                return solve_result

        class StubCapturer:
            captured = None

            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def capture(self, page, url, result):
                type(self).captured = (page, url, result)
                return "nowsecure.nl.tokenade"

        monkeypatch.setattr(guard_mod, "ChallengeGuard", StubGuard)
        monkeypatch.setattr(capture_mod, "SolvedSessionCapturer", StubCapturer)

        class FakePageMgr:
            def goto(self, url, wait_until=None, timeout=None):
                return "response"

        mgr = BrowserFactory.create(browser_type="cloakbrowser")
        mgr._uses_cloak = True
        mgr._page = FakePageMgr()
        return mgr, capture_mod

    def test_capture_runs_after_solved_challenge(self, monkeypatch):
        mgr, capture_mod = self._manager_with_stub_capture(
            monkeypatch, solve_result=solved_result())
        mgr.config.capture_solved_sessions = True
        mgr.navigate("https://nowsecure.nl", timeout=15000)
        page, url, result = capture_mod.SolvedSessionCapturer.captured
        assert url == "https://nowsecure.nl"
        assert result.data["solved"] is True

    def test_capture_skipped_when_unsolved(self, monkeypatch):
        mgr, capture_mod = self._manager_with_stub_capture(
            monkeypatch, solve_result=solved_result(solved=False))
        mgr.config.capture_solved_sessions = True
        mgr.navigate("https://nowsecure.nl", timeout=15000)
        assert capture_mod.SolvedSessionCapturer.captured is None

    def test_capture_skipped_when_disabled(self, monkeypatch):
        mgr, capture_mod = self._manager_with_stub_capture(
            monkeypatch, solve_result=solved_result())
        mgr.config.capture_solved_sessions = False
        mgr.navigate("https://nowsecure.nl", timeout=15000)
        assert capture_mod.SolvedSessionCapturer.captured is None

    def test_capture_runs_when_cloak_load_drops_clearance(self, monkeypatch):
        import tokenade.core.browser.challenge_guard as guard_mod
        import tokenade.core.integration.challenge_capture as capture_mod

        class CleanGuard:
            def __init__(self, page):
                pass

            def try_mitigate(self, url, settle_s=None):
                return None

        class StubCapturer:
            captured = None

            def __init__(self, **kwargs):
                pass

            def capture(self, page, url, result):
                type(self).captured = (url, result)
                return "nowsecure.nl.tokenade"

        class StatefulContext:
            cleared = False

            def cookies(self, url):
                if self.cleared:
                    return [{"name": "cf_clearance", "value": "fresh"}]
                return []

        context = StatefulContext()

        class FakePageMgr:
            def goto(self, url, wait_until=None, timeout=None):
                context.cleared = True
                return "response"

        monkeypatch.setattr(guard_mod, "ChallengeGuard", CleanGuard)
        monkeypatch.setattr(capture_mod, "SolvedSessionCapturer", StubCapturer)
        mgr = BrowserFactory.create(browser_type="cloakbrowser",
                                    capture_solved_sessions=True)
        mgr._uses_cloak = True
        mgr._context = context
        mgr._page = FakePageMgr()

        mgr.navigate("https://nowsecure.nl")
        url, result = StubCapturer.captured
        assert url == "https://nowsecure.nl"
        assert result.data["method"] == "cloakbrowser_load"
        assert result.data["provider"] == "cloudflare"
