"""Worker-context parity: detectors re-read identity inside Web Workers.

Proves which spoof layers hold in worker contexts:
  - Playwright context options (UA/timezone/locale) are engine-level: hold.
  - add_init_script overrides: must ALSO hold in workers, or detectors that
    re-probe in workers see through the spoof. This test fails loudly if
    they ever diverge.
Skips when headless Chromium is unavailable.
"""
import pytest


def _launch():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        pytest.skip(f"playwright unavailable: {exc}")
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
    except Exception as exc:
        pytest.skip(f"no headless chromium: {exc}")
    return pw, browser


WORKER_READ = """async () => {
    const code = `
        const out = {
            ua: navigator.userAgent,
            platform: navigator.platform,
            cores: navigator.hardwareConcurrency,
            tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
            langs: navigator.languages ? Array.from(navigator.languages) : [],
        };
        self.postMessage(out);
    `;
    const blob = new Blob([code], {type: 'application/javascript'});
    const worker = new Worker(URL.createObjectURL(blob));
    const result = await new Promise((resolve) => {
        worker.onmessage = (e) => resolve(e.data);
    });
    worker.terminate();
    return result;
}"""


def test_context_options_hold_in_workers():
    """Native (engine-level) tier holds in workers: UA/tz/locale agree."""
    pw, browser = _launch()
    try:
        context = browser.new_context(
            user_agent="TokenadeProbe/1.0",
            timezone_id="Asia/Kolkata",
            locale="en-IN",
        )
        page = context.new_page()
        main = page.evaluate(
            """() => ({
                tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
            })""")
        # Chromium reports the Asia/Calcutta alias for Asia/Kolkata: same zone.
        assert main["tz"] in ("Asia/Kolkata", "Asia/Calcutta"), main["tz"]
        worker = page.evaluate(WORKER_READ)
        assert worker["tz"] == main["tz"], f"worker tz diverged: {worker}"
        assert worker["ua"] == "TokenadeProbe/1.0"
        assert worker["langs"] and worker["langs"][0].startswith("en")
    finally:
        browser.close()
        pw.stop()


def test_init_script_navigator_spoof_visible_gap():
    """KNOWN LIMITATION (Phase 3 backlog): add_init_script overrides do NOT
    run inside `new Worker()` contexts — a detector re-reading navigator
    props in a worker sees the REAL values while the main thread is spoofed.

    This test pins the current behavior so the gap can't silently change shape:
    main thread spoofed (16) while the worker reports the host value.
    The durable fix is engine-level (CloakBrowser/Camoufox-model patches), not
    more JS. RuntimePlanBuilder's native tier (UA/tz/locale) is unaffected —
    see test_context_options_hold_in_workers.
    """
    pw, browser = _launch()
    try:
        context = browser.new_context()
        context.add_init_script(
            "Object.defineProperty(navigator, 'hardwareConcurrency', "
            "{get: () => 16});"
        )
        page = context.new_page()
        main = page.evaluate("() => navigator.hardwareConcurrency")
        assert main == 16
        worker = page.evaluate(WORKER_READ)
        assert worker["cores"] != 16, (
            "unexpected: init scripts now cover workers — "
            "promote this to a parity assertion and close the backlog item")
    finally:
        browser.close()
        pw.stop()


def test_unspoofed_worker_matches_main():
    """Baseline: with no spoofing, main and worker agree (sanity)."""
    pw, browser = _launch()
    try:
        page = browser.new_page()
        main = page.evaluate(
            "() => ({cores: navigator.hardwareConcurrency, "
            "platform: navigator.platform})")
        worker = page.evaluate(WORKER_READ)
        assert worker["cores"] == main["cores"]
        assert worker["platform"] == main["platform"]
    finally:
        browser.close()
        pw.stop()
