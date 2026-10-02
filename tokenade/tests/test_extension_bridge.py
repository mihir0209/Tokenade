"""Tests for extension-bridge export (no browser needed; fake CDP)."""
import asyncio
import json
import unittest
from unittest.mock import patch

from tokenade.core.importer.extension_bridge import (
    ExtensionBridgeMissing,
    build_keys_expr,
    build_probe_expr,
    build_roundtrip_expr,
    convert_bridge_cookies,
    export_via_bridge_sync,
)


class TestBuilders(unittest.TestCase):
    def test_probe(self):
        self.assertIn("window.Tokenade", build_probe_expr())

    def test_roundtrip_balanced_and_filtered(self):
        expr = build_roundtrip_expr("ASK_X", "WANT_Y", "localStorage", ["a", "b"])
        self.assertIn("ASK_X", expr)
        self.assertIn("WANT_Y", expr)
        self.assertIn('"a"', expr)
        # Timeout fallback always present so a missing listener can't hang us.
        self.assertIn("setTimeout", expr)

    def test_keys_expr(self):
        expr = build_keys_expr("ASK_X", "WANT_Y", "localStorage")
        self.assertIn("Object.keys", expr)
        self.assertIn("TIMEOUT", expr)


class TestCookieConvert(unittest.TestCase):
    def test_fields(self):
        out = convert_bridge_cookies([{
            "name": "s", "value": "v", "domain": ".x.com", "path": "/",
            "secure": True, "httpOnly": True, "sameSite": "no_restriction",
            "expirationDate": 1790628122.779,
        }, {"name": "", "value": "skip"}])
        self.assertEqual(len(out), 1)
        c = out[0]
        self.assertEqual((c["name"], c["value"], c["domain"]), ("s", "v", ".x.com"))
        self.assertEqual(c["sameSite"], "None")
        self.assertEqual(c["expires"], 1790628122)
        self.assertTrue(c["secure"] and c["httpOnly"])

    def test_empty(self):
        self.assertEqual(convert_bridge_cookies([]), [])
        self.assertEqual(convert_bridge_cookies(None), [])


class _FakeWS:
    """Scripted CDP websocket: method -> handler(mid, params) -> result."""

    def __init__(self, handlers):
        self._handlers = handlers
        self.sent = []
        self.closed = False

    async def send(self, raw):
        self._sent_msg = json.loads(raw)
        self.sent.append(self._sent_msg)

    async def recv(self):
        msg = self._sent_msg
        mid, method = msg["id"], msg["method"]
        payload = self._handlers[method](mid, msg.get("params", {}))
        return json.dumps({"id": mid, "result": payload})

    async def close(self):
        self.closed = True


def _run_bridge(tabs, handlers, domains=("example.com",)):
    async def _connect(*a, **k):
        return _FakeWS(handlers)

    async def _go():
        from tokenade.core.importer import extension_bridge as eb
        with patch.object(eb.urllib.request, "urlopen") as mock_urlopen, \
             patch("websockets.connect", side_effect=_connect):
            responses = {"list": tabs}

            class _Resp:
                def __init__(self, payload):
                    self._payload = payload

                def read(self):
                    return json.dumps(self._payload).encode()

            def fake_urlopen(req, timeout=None):
                url = req.full_url if hasattr(req, "full_url") else req
                if url.endswith("/json/list"):
                    return _Resp(responses["list"])
                if "/json/new?" in url:
                    return _Resp({
                        "id": "t1",
                        "webSocketDebuggerUrl": "ws://127.0.0.1:1/devtools/page/t1",
                    })
                raise AssertionError("unexpected url " + url)

            mock_urlopen.side_effect = fake_urlopen
            return await eb._export_async(9999, list(domains))

    return asyncio.run(_go())


def _eval_result(value):
    return {"result": {"value": value}}


class TestBridgeExport(unittest.TestCase):
    def _handlers(self, storage, cookies):
        def _eval(mid, params):
            expr = params.get("expression", "")
            if "typeof window.Tokenade" in expr:
                return _eval_result("object")
            if "TOKENADE_LOCALSTORAGE_RESULT" in expr:
                if "Object.keys" in expr:
                    return _eval_result(json.dumps(list(storage.keys())))
                return _eval_result(json.dumps(storage))
            if "TOKENADE_SESSIONSTORAGE_RESULT" in expr:
                return _eval_result(json.dumps([]))
            if "TOKENADE_COOKIES_RESULT" in expr:
                return _eval_result(json.dumps(cookies))
            return _eval_result("")
        return {"Runtime.evaluate": _eval}

    def test_full_flow(self):
        storage = {"token": "T" * 10, "a": "1"}
        cookies = [{"name": "s", "value": "v", "domain": ".example.com",
                    "path": "/", "secure": True, "httpOnly": False,
                    "sameSite": "no_restriction"}]
        tabs = [{"id": "t1", "type": "page", "url": "https://example.com/",
                 "webSocketDebuggerUrl": "ws://x"}]
        out = _run_bridge(tabs, self._handlers(storage, cookies))
        self.assertEqual(out["local_storage"], storage)
        self.assertEqual(out["session_storage"], {})
        self.assertEqual(len(out["cookies"]), 1)
        self.assertEqual(out["cookies"][0]["name"], "s")

    def test_missing_bridge(self):
        def _eval(mid, params):
            return _eval_result("undefined")

        tabs = [{"id": "t1", "type": "page", "url": "https://example.com/",
                 "webSocketDebuggerUrl": "ws://x"}]
        with self.assertRaises(ExtensionBridgeMissing) as cm:
            _run_bridge(tabs, {"Runtime.evaluate": _eval})
        self.assertIn("Load unpacked", str(cm.exception))

    def test_no_domains(self):
        with self.assertRaises(ValueError):
            export_via_bridge_sync(9999, [])

    def test_multi_domain_per_origin_storage(self):
        per_origin = {
            "https://a.com": {"k1": "v1"},
            "https://b.com": {"k2": "v2"},
        }

        def _handlers_for(domain):
            def _eval(mid, params):
                expr = params.get("expression", "")
                if "typeof window.Tokenade" in expr:
                    return _eval_result("object")
                if "TOKENADE_LOCALSTORAGE_RESULT" in expr:
                    if "Object.keys" in expr:
                        want = [k for o, m in per_origin.items()
                                if domain in o for k in m]
                        return _eval_result(json.dumps(want))
                    store = next((m for o, m in per_origin.items() if domain in o), {})
                    return _eval_result(json.dumps(store))
                if "TOKENADE_COOKIES_RESULT" in expr:
                    return _eval_result(json.dumps(
                        [{"name": "c", "value": "v", "domain": "." + domain}]))
                return _eval_result("")
            return {"Runtime.evaluate": _eval}

        seen = {}

        async def _connect(*a, **k):
            raise AssertionError("patched per-domain below")

        import asyncio as _asyncio

        async def _go(domains):
            from tokenade.core.importer import extension_bridge as eb
            current = [None]

            async def fake_connect(url, **kw):
                return _FakeWS(_handlers_for(current[0]))

            def fake_tab(port, domain, timeout=10):
                current[0] = domain
                return {"id": "t-" + domain,
                        "webSocketDebuggerUrl": "ws://x/" + domain}

            with patch.object(eb, "_tab_for_domain", side_effect=fake_tab), \
                 patch("websockets.connect", side_effect=fake_connect):
                return await eb._export_async(9999, domains)

        out = asyncio.run(_go(["a.com", "b.com"]))
        self.assertEqual(out["storage"]["local"]["https://a.com"], {"k1": "v1"})
        self.assertEqual(out["storage"]["local"]["https://b.com"], {"k2": "v2"})
        self.assertEqual(len(out["cookies"]), 2)

    def test_generated_js_parses(self):
        """All builder expressions must be syntactically valid JS.

        A single unbalanced brace once shipped hollow jars; node (when
        present) is the oracle. Skipped where node is unavailable.
        """
        import shutil
        import subprocess

        if shutil.which("node") is None:
            self.skipTest("node not available")
        from tokenade.core.importer.extension_bridge import (
            build_keys_expr,
            build_roundtrip_expr,
        )
        src = "\n".join([
            build_keys_expr("A", "B", "localStorage"),
            build_roundtrip_expr("A", "B", "localStorage"),
            build_roundtrip_expr("A", "B", "localStorage", ["x"]),
        ]) + "\n"
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(src)
            path = f.name
        try:
            proc = subprocess.run(["node", "--check", path],
                                  capture_output=True, text=True, timeout=60)
        finally:
            import os
            os.unlink(path)
        self.assertEqual(proc.returncode, 0, proc.stderr[:500])


class TestMergeLiveStorage(unittest.TestCase):
    def test_live_wins_and_file_fills_gaps(self):
        from tokenade.cli.session_export import _merge_live_storage

        local, session, storage = {"a": "live"}, {}, {"local": {}, "session": {}}
        live_local = {"a": "live", "b": "live-b"}
        live_storage = {"local": {"https://x.com": {"k": "v"}}, "session": {}}
        _merge_live_storage(local, session, storage, live_local, {}, live_storage)
        self.assertEqual(local, {"a": "live", "b": "live-b"})
        self.assertEqual(storage["local"], {"https://x.com": {"k": "v"}})

    def test_empty_live_is_noop(self):
        from tokenade.cli.session_export import _merge_live_storage

        local, session, storage = {"a": "1"}, {"s": "2"}, {"local": {"o": {"k": "v"}}, "session": {}}
        _merge_live_storage(local, session, storage, {}, {}, {"local": {}, "session": {}})
        self.assertEqual((local, session), ({"a": "1"}, {"s": "2"}))
        self.assertEqual(storage["local"], {"o": {"k": "v"}})


if __name__ == "__main__":
    unittest.main()
