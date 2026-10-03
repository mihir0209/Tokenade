"""Loader wiring: extra_args merge + init_scripts registration (mocked browser)."""
import json
from unittest.mock import MagicMock, patch

from tokenade.core.importer.session_loader import SessionLoader


def _jar_file(tmp_path, package):
    path = tmp_path / "s.tokenade"
    path.write_text(json.dumps(package))
    return str(path)


def _pkg():
    return {
        "version": "3.1", "site_name": "github",
        "cookies": [{"name": "a", "value": "b", "domain": ".github.com"}],
    }


def test_load_applies_extra_args_and_init_scripts(tmp_path):
    path = _jar_file(tmp_path, _pkg())
    mock_bm = MagicMock()
    captured = {}
    real_create = None

    def fake_create(**kwargs):
        captured.update(kwargs)
        return mock_bm

    with patch("tokenade.core.importer.session_loader.BrowserFactory") as factory:
        factory.create.side_effect = fake_create
        result = SessionLoader().load(
            path, validate=False,
            extra_args=["--force-webrtc-ip-handling-policy=disable_non_proxied_udp"],
            init_scripts=["window.__x = 1;"],
        )
    assert result["success"] is True
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in captured["args"]
    scripts = [call[0][0] for call in mock_bm.add_init_script.call_args_list]
    assert any("__x" in s for s in scripts)


def test_load_without_runtime_args_unchanged(tmp_path):
    path = _jar_file(tmp_path, _pkg())
    mock_bm = MagicMock()
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return mock_bm

    with patch("tokenade.core.importer.session_loader.BrowserFactory") as factory:
        factory.create.side_effect = fake_create
        SessionLoader().load(path, validate=False)
    assert captured.get("args", []) == [] or "webrtc" not in " ".join(captured.get("args", []))
    mock_bm.add_init_script.assert_not_called()
