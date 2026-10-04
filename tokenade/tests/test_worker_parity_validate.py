"""Tests for validate_worker_parity (fake managers; no browser needed)."""
from tokenade.core.fingerprint.injector import validate_worker_parity


class _FakeManager:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.seen_scripts = []

    def evaluate(self, script):
        self.seen_scripts.append(script)
        if self._error is not None:
            raise self._error
        return self._result


def _reads(main, worker):
    return {"main": main, "worker": worker, "worker_error": None}


def test_match():
    reads = {"userAgent": "UA", "platform": "Win32"}
    out = validate_worker_parity(_FakeManager(_reads(reads, dict(reads))))
    assert out["status"] == "match"
    assert set(out["probes"]) == {"userAgent", "platform"}


def test_mismatch_lists_fields():
    out = validate_worker_parity(_FakeManager(_reads(
        {"cores": 16, "tz": "X"}, {"cores": 4, "tz": "X"})))
    assert out["status"] == "mismatch"
    assert out["mismatches"] == ["cores"]


def test_no_evaluate_is_unknown():
    assert validate_worker_parity(object())["status"] == "unknown"


def test_evaluate_error_is_unknown():
    out = validate_worker_parity(_FakeManager(error=RuntimeError("boom")))
    assert out["status"] == "unknown" and "boom" in out["reason"]


def test_garbage_result_is_unknown():
    assert validate_worker_parity(_FakeManager("nope"))["status"] == "unknown"
    assert validate_worker_parity(_FakeManager(None))["status"] == "unknown"


def test_worker_failed_is_unknown_with_main():
    out = validate_worker_parity(_FakeManager(
        {"main": {"a": 1}, "worker": None, "worker_error": "timeout"}))
    assert out["status"] == "unknown"
    assert out["main"] == {"a": 1}


def test_script_probes_workers():
    manager = _FakeManager(_reads({}, {}))
    validate_worker_parity(manager)
    script = manager.seen_scripts[0]
    assert "new Worker" in script and "postMessage" in script


def test_loader_reports_parity_key(tmp_path):
    """Loader always sets worker_parity (unknown on mock backends)."""
    import json as _json
    from unittest.mock import MagicMock, patch

    from tokenade.core.importer.session_loader import SessionLoader

    path = tmp_path / "w.tokenade"
    path.write_text(_json.dumps({
        "version": "3.1", "site_name": "github",
        "cookies": [{"name": "a", "value": "b", "domain": ".github.com"}],
    }))
    with patch("tokenade.core.importer.session_loader.BrowserFactory") as factory:
        factory.create.return_value = MagicMock()
        result = SessionLoader().load(str(path), validate=False)
    assert result["worker_parity"]["status"] == "unknown"
