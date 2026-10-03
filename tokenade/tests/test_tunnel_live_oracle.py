"""Tests for the live-browser oracle (needs headless Chromium; skips without)."""
import pytest

from tokenade.core.tunnel.live_oracle import PROBE_JS, LiveBrowserOracle
from tokenade.core.tunnel.origin import OriginEndpoint

ALLOW = ["navigator.platform", "navigator.hardwareConcurrency",
         "Intl.timeZone", "fonts.list", "canvas.readback"]


def _needs_browser():
    oracle = LiveBrowserOracle(ALLOW)
    try:
        oracle.start()
    except Exception as exc:
        pytest.skip(f"no headless chromium: {exc}")
    return oracle


def test_live_answers_scalars():
    oracle = _needs_browser()
    try:
        value, error = oracle.answer("navigator.platform")
        assert error is None and isinstance(value, str) and value
        value, error = oracle.answer("navigator.hardwareConcurrency")
        assert error is None and isinstance(value, int) and value >= 1
        value, error = oracle.answer("Intl.timeZone")
        assert error is None and isinstance(value, str) and value
    finally:
        oracle.stop()


def test_live_fonts_list():
    oracle = _needs_browser()
    try:
        value, error = oracle.answer("fonts.list")
        assert error is None and isinstance(value, list)
    finally:
        oracle.stop()


def test_live_denies_render_tier():
    oracle = LiveBrowserOracle(ALLOW)
    # Even allowlisted, render reads have no probe: never remotely answerable.
    value, error = oracle.answer("canvas.readback")
    assert value is None and error == "unknown: canvas.readback"
    assert "canvas.readback" not in PROBE_JS
    assert "toDataURL" not in str(PROBE_JS) and "readPixels" not in str(PROBE_JS)
    # Non-allowlisted methods are denied outright.
    value, error = oracle.answer("document.cookie")
    assert value is None and error == "denied: document.cookie"


def test_live_cache_survives_stop():
    oracle = _needs_browser()
    try:
        value, error = oracle.answer("navigator.platform")
        assert error is None
    finally:
        oracle.stop()
    value2, error2 = oracle.answer("navigator.platform")
    assert error2 is None and value2 == value


async def test_origin_answer_prefers_live():
    endpoint = OriginEndpoint("ws://x", "r", consumer_tokens=set(),
                              snapshot_values={"navigator.platform": "SNAP"},
                              oracle_allowlist=ALLOW)

    class _FakeLive:
        def start(self):
            pass

        def answer(self, method):
            return ("LIVE-" + method, None) if method != "nope" else (None, "boom")

    endpoint._live = _FakeLive()
    value, error, source = await endpoint._answer_query("navigator.platform")
    assert (value, source) == ("LIVE-navigator.platform", "live")
    assert error is None


async def test_origin_answer_falls_back_to_snapshot():
    endpoint = OriginEndpoint("ws://x", "r", consumer_tokens=set(),
                              snapshot_values={"navigator.platform": "SNAP"},
                              oracle_allowlist=ALLOW)

    class _FailingLive:
        def start(self):
            pass

        def answer(self, method):
            return None, "eval failed: gone"

    endpoint._live = _FailingLive()
    value, error, source = await endpoint._answer_query("navigator.platform")
    assert (value, error, source) == ("SNAP", None, "snapshot-fallback")


async def test_origin_answer_denied_stays_denied():
    endpoint = OriginEndpoint("ws://x", "r", consumer_tokens=set(),
                              snapshot_values={}, oracle_allowlist=ALLOW)

    class _FakeLive:
        def start(self):
            pass

        def answer(self, method):
            return None, f"denied: {method}"

    endpoint._live = _FakeLive()
    value, error, source = await endpoint._answer_query("canvas.readback")
    assert value is None and source == "none" and error.startswith("denied:")
