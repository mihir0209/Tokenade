"""Tests for session loader."""

import asyncio
import json
from unittest.mock import patch

from tokenade.core.importer.session_loader import (
    SessionLoader,
    storage_shortfall_message,
)


class TestSessionLoader:
    def test_creation(self):
        loader = SessionLoader()
        assert loader is not None

    def test_load_valid_file(self, tmp_path):
        session = {
            "version": "2.0",
            "site_name": "test",
            "auth_status": "logged_in",
            "cookies": [
                {"name": "session", "value": "abc", "domain": ".example.com", "path": "/"},
            ],
        }
        f = tmp_path / "test.tokenade"
        f.write_text(json.dumps(session))

        loader = SessionLoader()
        # load() returns a result dict, doesn't raise
        result = loader.load(str(f), validate=False)
        assert isinstance(result, dict)

    def test_load_nonexistent_file(self):
        loader = SessionLoader()
        result = loader.load("/nonexistent/file.tokenade", validate=False)
        assert result.get("success") is False

    def test_load_invalid_json(self, tmp_path):
        f = tmp_path / "bad.tokenade"
        f.write_text("not json {{{")

        loader = SessionLoader()
        result = loader.load(str(f), validate=False)
        assert result.get("success") is False

    def test_load_empty_file(self, tmp_path):
        f = tmp_path / "empty.tokenade"
        f.write_text("")

        loader = SessionLoader()
        result = loader.load(str(f), validate=False)
        assert result.get("success") is False

    def test_close(self):
        loader = SessionLoader()
        loader.close()  # Should not raise


class TestStorageShortfallMessage:
    def test_none_when_nothing_expected(self):
        assert storage_shortfall_message({}) is None
        assert storage_shortfall_message({"local_storage_total": 0}) is None

    def test_none_when_fully_injected_playwright_shape(self):
        assert storage_shortfall_message({
            "local_storage_total": 3,
            "local_storage_injected": 3,
            "session_storage_total": 0,
            "session_storage_injected": 0,
        }) is None

    def test_warns_on_partial_playwright_inject(self):
        msg = storage_shortfall_message({
            "local_storage_total": 93,
            "local_storage_injected": 0,
            "session_storage_total": 0,
            "session_storage_injected": 0,
        })
        assert msg and "localStorage 0/93" in msg and "extension" in msg

    def test_warns_on_cdp_failed_flag_without_counts(self):
        # inject_into_cdp_tab shape: totals + failed flags, no injected counts.
        assert storage_shortfall_message({
            "local_storage_total": 5,
            "session_storage_total": 0,
            "storage_failed_local": False,
            "storage_failed_session": False,
        }) is None
        msg = storage_shortfall_message({
            "local_storage_total": 5,
            "session_storage_total": 0,
            "storage_failed_local": True,
            "storage_failed_session": False,
        })
        assert msg and "localStorage" in msg

    def test_session_storage_gap(self):
        msg = storage_shortfall_message({
            "local_storage_total": 0,
            "session_storage_total": 2,
            "session_storage_injected": 1,
        })
        assert msg and "sessionStorage 1/2" in msg


class _FakeTabWS:
    """Minimal websockets stand-in answering CDP calls by method."""

    def __init__(self, evaluate_responder):
        self._sent = []
        self._respond = evaluate_responder
        self.closed = False

    async def send(self, raw):
        self._sent.append(json.loads(raw))

    async def recv(self):
        msg = self._sent[-1]
        mid, method = msg["id"], msg["method"]
        payload = self._respond(method, msg)
        return json.dumps({"id": mid, "result": payload})

    async def close(self):
        self.closed = True


def _run_cdp_inject(evaluate_payload, local_data=None, session_data=None):
    async def _go():
        async def _connect(*a, **k):
            return ws

        def _respond(method, msg):
            if method == "Runtime.evaluate":
                return evaluate_payload
            if method == "Network.setCookies":
                return {}
            return {}

        ws = _FakeTabWS(_respond)
        with patch("websockets.connect", side_effect=_connect):
            return await SessionLoader().inject_into_cdp_tab(
                "ws://127.0.0.1:1/devtools/page/x",
                [{"name": "a", "value": "b", "domain": "example.com"}],
                local_data=local_data if local_data is not None else {"k": "v"},
                session_data=session_data or {},
                url="https://example.com",
            )

    return asyncio.run(_go())


class TestInjectIntoCdpTabStorageFlags:
    def test_storage_write_error_flagged(self):
        res = _run_cdp_inject(
            {"result": {"type": "object", "subtype": "error",
                        "className": "DOMException"}}
        )
        assert res["storage_failed_local"] is True
        assert res["storage_failed_session"] is False
        assert res["local_storage_total"] == 1
        assert res["injected_cookies"] == 1

    def test_storage_write_success_not_flagged(self):
        res = _run_cdp_inject({"result": {"type": "undefined"}})
        assert res["storage_failed_local"] is False
        assert res["storage_failed_session"] is False
