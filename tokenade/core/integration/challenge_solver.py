"""
Challenge solving for anti-bot protections (Cloudflare Turnstile / Managed
Challenge, DataDome CAPTCHA, etc.).

Built-in solvers:
1. CloakBrowserAutoSolver — drives a stealth (CloakBrowser) page until the
   challenge clears itself (Turnstile widget issues a token, Managed Challenge
   drops a cf_clearance cookie). Cloudflare explicitly blocks plain headless
   and automation frameworks, so a source-patched stealth browser is required
   for the "load and wait" strategy to succeed.
2. ExternalSolverPlugin — base for commercial solving APIs. Reference
   implementations: TwoCaptchaSolverPlugin and CapSolverSolverPlugin
   (async task pattern: create task, poll, collect token).

Artifacts produced on success:
  - token: cf-turnstile-response value (Turnstile widgets)
  - clearance_cookies: e.g. cf_clearance / __cf_bm / datadome — IP- and
    User-Agent-bound; reuse them via SessionLoader with a matching context.
"""

import json
import logging
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from tokenade.plugin.api import PluginConfig, PluginResult
from tokenade.plugin.base import ChallengeSolverPlugin

logger = logging.getLogger(__name__)

TURNSTILE_TOKEN_JS = """
() => {
    const el = document.querySelector('[name="cf-turnstile-response"]');
    return el ? el.value : '';
}
"""

CHALLENGE_MARKERS_JS = """
() => {
    const t = (document.title || '').toLowerCase();
    const b = (document.body ? document.body.innerText : '').slice(0, 2000).toLowerCase();
    const html = (document.documentElement ? document.documentElement.innerHTML : '')
        .slice(0, 3000).toLowerCase();
    const marker = t.includes('just a moment') || t.includes('attention required')
        || b.includes('verify you are human') || b.includes('enabling javascript')
        || html.includes('cf-challenge-running') || html.includes('challenge-stage');
    return marker;
}
"""

TURNSTILE_CHECKBOX_JS = """
() => {
    const frames = [...document.querySelectorAll('iframe')];
    for (const f of frames) {
        if ((f.src || '').includes('challenges.cloudflare.com')) {
            try {
                const doc = f.contentDocument;
                if (!doc) return false;
                const box = doc.querySelector('#challenge-stage, #cf-challenge-running, input[type="checkbox"]');
                if (box) { box.click(); return true; }
            } catch (e) {}
        }
    }
    return false;
}
"""


class CloakBrowserAutoSolver(ChallengeSolverPlugin):
    """Native solver: waits for a challenge to clear in a stealth browser page.

    Works on any Playwright page object (duck-typed interface). The browser
    itself must be stealth enough for Cloudflare to accept it (CloakBrowser).
    """

    name = "stealth-auto-solver"
    version = "1.0.0"
    description = "Drives a stealth browser until the challenge auto-clears"
    author = "Tokenade"
    solver_type = "stealth"

    def __init__(self, wait_timeout_s: float = 30.0, poll_interval_s: float = 1.0,
                 reload_attempts: int = 2, min_wait_s: float = 0.0,
                 progress_cb=None):
        super().__init__()
        self.wait_timeout_s = wait_timeout_s
        self.poll_interval_s = poll_interval_s
        self.reload_attempts = reload_attempts
        self.min_wait_s = min_wait_s
        self.progress_cb = progress_cb

    def can_solve(self, challenge_type: str, provider: str = "") -> bool:
        return provider in ("", "cloudflare", "datadome") and challenge_type in (
            "turnstile", "managed_challenge", "datadome_captcha", "interstitial", "waf_block")

    def _extract_token(self, page: Any) -> str:
        try:
            token = page.evaluate(TURNSTILE_TOKEN_JS) or ""
            return token.strip()
        except Exception:
            return ""

    def _has_clearance_cookie(self, page: Any) -> List[Dict[str, Any]]:
        try:
            cookies = page.context.cookies()
        except Exception:
            return []
        names = {c["name"] for c in cookies}
        return [c for c in cookies if c["name"] in ("cf_clearance", "__cf_bm", "datadome")]

    def _challenge_still_present(self, page: Any) -> bool:
        try:
            return bool(page.evaluate(CHALLENGE_MARKERS_JS))
        except Exception:
            return True

    def _report(self, page: Any, start: float, token: str,
                clearance: List[Dict[str, Any]]) -> PluginResult:
        try:
            verified = bool(self.verify_solution(page))
        except Exception:
            verified = False
        return PluginResult(success=True, data={
            "solved": True, "method": "stealth", "token": token,
            "clearance_cookies": clearance,
            "elapsed_s": round(time.monotonic() - start, 2),
            "verified": verified,
        })

    def _poll_loop(self, page: Any, start: float, deadline: float):
        """Poll for token/clearance until deadline. Returns (token, cookies) or (None, [])."""
        while time.monotonic() < deadline:
            token = self._extract_token(page)
            clearance = self._has_clearance_cookie(page)
            if token or clearance:
                return token, clearance
            if self.progress_cb:
                self.progress_cb(round(time.monotonic() - start, 1))
            page.wait_for_timeout(int(self.poll_interval_s * 1000))
        return None, []

    def solve(self, page: Any, challenge_data: Dict[str, Any]) -> PluginResult:
        start = time.monotonic()
        token = self._extract_token(page)
        clearance = self._has_clearance_cookie(page)

        if self.min_wait_s > 0 and (token or clearance):
            # Already cleared (stealth browser passed during page load): hold a
            # verification window of min_wait_s, re-asserting the artifacts on
            # every poll so the demo shows the cleared state being verified,
            # not an instant no-op.
            deadline = start + self.min_wait_s
            while time.monotonic() < deadline:
                fresh_token = self._extract_token(page)
                fresh_clearance = self._has_clearance_cookie(page)
                if fresh_token:
                    token = fresh_token
                if fresh_clearance:
                    clearance = fresh_clearance
                if self.progress_cb:
                    self.progress_cb(round(time.monotonic() - start, 1))
                page.wait_for_timeout(int(self.poll_interval_s * 1000))
            return self._report(page, start, token, clearance)

        if token or clearance:
            return self._report(page, start, token, clearance)

        # 1. Click an interactive Turnstile checkbox if one is rendered.
        try:
            page.evaluate(TURNSTILE_CHECKBOX_JS)
        except Exception:
            pass

        # 2. Poll for auto-clear (token or clearance cookie).
        deadline = time.monotonic() + self.wait_timeout_s
        while time.monotonic() < deadline:
            token = self._extract_token(page)
            clearance = self._has_clearance_cookie(page)
            if token or clearance:
                return self._report(page, start, token, clearance)
            if self.progress_cb:
                self.progress_cb(round(time.monotonic() - start, 1))
            page.wait_for_timeout(int(self.poll_interval_s * 1000))

        # 3. Reload-and-wait (Managed Challenge often clears on 2nd load).
        for _ in range(self.reload_attempts):
            try:
                page.reload(wait_until="domcontentloaded")
            except Exception:
                time.sleep(self.poll_interval_s)
            deadline = time.monotonic() + self.wait_timeout_s
            while time.monotonic() < deadline:
                token = self._extract_token(page)
                clearance = self._has_clearance_cookie(page)
                if token or clearance:
                    return self._report(page, start, token, clearance)
                if self.progress_cb:
                    self.progress_cb(round(time.monotonic() - start, 1))
                page.wait_for_timeout(int(self.poll_interval_s * 1000))

        return PluginResult(success=False, data={
            "solved": False, "method": "stealth", "token": "", "clearance_cookies": [],
            "elapsed_s": round(time.monotonic() - start, 2),
        }, error=(
            "Challenge did not clear within timeout — IP/fingerprint flagged or "
            "interactive challenge requires external solver or residential proxy"
        ))


class ExternalSolverPlugin(ChallengeSolverPlugin):
    """Base class for commercial challenge solving APIs (async task pattern).

    Subclasses implement create_task()/get_task_result() for the provider's
    HTTP contract. API keys come from PluginConfig (env_var supported) or the
    api_key constructor arg.
    """

    solver_type = "external"
    create_task_payload: str = ""

    def __init__(self, api_key: Optional[str] = None, poll_interval_s: float = 3.0,
                 max_wait_s: float = 120.0):
        super().__init__()
        self.api_key = api_key or self._resolve_api_key()
        self.poll_interval_s = poll_interval_s
        self.max_wait_s = max_wait_s

    def _resolve_api_key(self) -> str:
        if self._config is not None:
            try:
                value = self._config.get("api_key")
                if value:
                    return str(value)
            except Exception:
                pass
        return ""

    def _http_json(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())

    def solve(self, page_context: Any, challenge_data: Dict[str, Any]) -> PluginResult:
        if not self.api_key:
            return PluginResult(success=False, error=(
                f"{self.name}: no api_key configured (set env var or plugin config)"))
        start = time.monotonic()
        sitekey = self._extract_sitekey(page_context, challenge_data)
        page_url = self._extract_page_url(page_context, challenge_data)
        challenge_type = challenge_data.get("challenge_type", "turnstile")
        task_id = self.create_task(challenge_type, sitekey, page_url)
        if not task_id:
            return PluginResult(success=False, error=f"{self.name}: task creation failed")
        deadline = time.monotonic() + self.max_wait_s
        while time.monotonic() < deadline:
            result = self.get_task_result(task_id)
            if result.get("status") == "ready":
                token = result.get("token", "")
                return PluginResult(success=True, data={
                    "solved": True, "method": self.name, "token": token,
                    "clearance_cookies": result.get("cookies", []),
                    "elapsed_s": round(time.monotonic() - start, 2),
                })
            if result.get("status") == "failed":
                return PluginResult(success=False, error=result.get("error", "task failed"))
            time.sleep(self.poll_interval_s)
        return PluginResult(success=False, error=f"{self.name}: solve timed out")

    def _extract_sitekey(self, page_context: Any, challenge_data: Dict[str, Any]) -> str:
        details = challenge_data.get("details", {}) or {}
        if details.get("sitekey"):
            return str(details["sitekey"])
        try:
            if isinstance(page_context, dict):
                html = str(page_context.get("html", ""))
            else:
                html = page_context.content()
            return self._sitekey_from_html(html)
        except Exception:
            return ""

    @staticmethod
    def _sitekey_from_html(html: str) -> str:
        for marker in ('data-sitekey="', "data-sitekey='"):
            idx = html.find(marker)
            if idx >= 0:
                end = html.find('"', idx + len(marker))
                if end > idx:
                    return html[idx + len(marker):end]
        return ""

    def _extract_page_url(self, page_context: Any, challenge_data: Dict[str, Any]) -> str:
        if isinstance(page_context, dict):
            return str(page_context.get("url", ""))
        try:
            return page_context.url
        except Exception:
            return ""

    def can_solve(self, challenge_type: str, provider: str = "") -> bool:
        return challenge_type in ("turnstile", "managed_challenge", "recaptcha_v2", "hcaptcha")

    def create_task(self, challenge_type: str, sitekey: str, page_url: str) -> str:
        """Create a solve task on the provider. Return task id or ''."""
        raise NotImplementedError

    def get_task_result(self, task_id: str) -> Dict[str, Any]:
        """Poll task status: {"status": "processing"|"ready"|"failed", ...}."""
        raise NotImplementedError


class TwoCaptchaSolverPlugin(ExternalSolverPlugin):
    """2captcha solver (TurnstileTaskProxyless flow)."""

    name = "2captcha-solver"
    version = "1.0.0"
    description = "Solves Turnstile / reCAPTCHA via 2captcha API"
    author = "Tokenade"
    solver_type = "external"
    API_URL = "https://2captcha.com"

    def __init__(self, api_key: Optional[str] = None, **kw):
        super().__init__(api_key, **kw)

    def create_task(self, challenge_type: str, sitekey: str, page_url: str) -> str:
        payload = {
            "key": self.api_key,
            "method": "turnstile",
            "sitekey": sitekey,
            "pageurl": page_url,
            "action": "verify",
            "json": 1,
        }
        data = self._http_json(f"{self.API_URL}/in.php", payload)
        if str(data.get("status")) == "1":
            return str(data.get("request", ""))
        logger.warning("2captcha create failed: %s", data)
        return ""

    def get_task_result(self, task_id: str) -> Dict[str, Any]:
        url = (f"{self.API_URL}/res.php?key={self.api_key}&action=get&id={task_id}&json=1")
        data = self._http_json(url, {})
        if str(data.get("status")) == "1":
            return {"status": "ready", "token": str(data.get("request", ""))}
        if "CAPCHA_NOT_READY" in str(data.get("request", "")).upper():
            return {"status": "processing"}
        return {"status": "failed", "error": str(data.get("request", ""))}


class CapSolverSolverPlugin(ExternalSolverPlugin):
    """CapSolver solver (AntiTurnstileTaskProxyLess flow)."""

    name = "capsolver-solver"
    version = "1.0.0"
    description = "Solves Turnstile / DataDome via CapSolver API"
    author = "Tokenade"
    solver_type = "external"
    API_URL = "https://api.capsolver.com"

    def __init__(self, api_key: Optional[str] = None, **kw):
        super().__init__(api_key, **kw)

    def create_task(self, challenge_type: str, sitekey: str, page_url: str) -> str:
        payload = {
            "clientKey": self.api_key,
            "task": {
                "type": "AntiTurnstileTaskProxyLess",
                "websiteURL": page_url,
                "websiteKey": sitekey,
                "metadata": {"type": "turnstile"},
            },
        }
        data = self._http_json(f"{self.API_URL}/createTask", payload)
        if data.get("taskId"):
            return str(data["taskId"])
        logger.warning("capsolver create failed: %s", data)
        return ""

    def get_task_result(self, task_id: str) -> Dict[str, Any]:
        payload = {"clientKey": self.api_key, "taskId": task_id}
        data = self._http_json(f"{self.API_URL}/getTaskResult", payload)
        status = data.get("status")
        if status == "ready":
            return {"status": "ready", "token": str(data["solution"].get("token", ""))}
        if status == "processing":
            return {"status": "processing"}
        return {"status": "failed", "error": str(data.get("errorDescription", "unknown"))}


class ChallengeSolver:
    """Orchestrates challenge solving: auto (stealth) first, external fallback.

    Usage:
        solver = ChallengeSolver(auto_solver=CloakBrowserAutoSolver(),
                                 external=[TwoCaptchaSolverPlugin()])
        result = solver.solve(page, challenge_data)
    """

    def __init__(self, auto_solver: Optional[ChallengeSolverPlugin] = None,
                 external: Optional[List[ChallengeSolverPlugin]] = None,
                 verify: bool = True):
        self.auto_solver = auto_solver
        self.external = external or []
        self.verify = verify

    def solve(self, page: Any, challenge_data: Dict[str, Any]) -> PluginResult:
        challenge_type = challenge_data.get("challenge_type", "")
        provider = challenge_data.get("provider", "")
        attempts = []

        solvers: List[ChallengeSolverPlugin] = []
        if self.auto_solver is not None:
            solvers.append(self.auto_solver)
        solvers.extend(self.external)

        for solver in solvers:
            if not solver.can_solve(challenge_type, provider):
                continue
            result = solver.solve(page, challenge_data)
            attempts.append({"solver": solver.name, "success": result.success,
                             "error": result.error})
            if result.success and result.data.get("solved"):
                if self.verify and page is not None:
                    try:
                        result.data["verified"] = solver.verify_solution(page)
                    except Exception:
                        result.data["verified"] = False
                result.data["attempts"] = attempts
                return result

        return PluginResult(success=False, data={"solved": False, "attempts": attempts},
                            error="All solvers failed or no solver supports this challenge")
