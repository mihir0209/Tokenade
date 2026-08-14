import base64
import hashlib
import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

from tokenade.core.artifacts import (
    AccessMode,
    ArtifactError,
    ProfileArtifactManager,
    SessionPolicyError,
)
from tokenade.plugin import PluginResult


def make_payload(mode="exclusive_move"):
    archive = b"safe archive bytes"
    return {
        "format": "test-profile-v1",
        "access_mode": mode,
        "archive_base64": base64.b64encode(archive).decode(),
        "archive_sha256": hashlib.sha256(archive).hexdigest(),
        "files": {"logical/file": hashlib.sha256(b"value").hexdigest()},
        "file_count": 1,
        "uncompressed_size": 5,
    }


def make_session(mode="exclusive_move"):
    artifact = ProfileArtifactManager.package_plugin_payload(
        "test-handler", "2.0.0", make_payload(mode),
        tokenade_requirement=">=1.1.92",
    )
    return {
        "version": "3.0",
        "created_at": "2026-08-10T00:00:00Z",
        "site_name": "test",
        "auth_status": "logged_in",
        "cookies": [{"name": "secret", "value": "hidden", "domain": "test.invalid"}],
        "tokens": [{"type": "secret", "value": "hidden"}],
        "storage": {"local": {"https://test.invalid": {"secret-key": "hidden"}}, "session": {}},
        "profile_artifacts": [artifact],
        "metadata": {},
    }


def test_inspection_is_secret_safe():
    inspection = ProfileArtifactManager.inspect(make_session()).as_dict()
    serialized = json.dumps(inspection)
    assert inspection["access_mode"] == "exclusive_move"
    assert inspection["cookie_count"] == 1
    assert inspection["profile_artifacts"]["owners"] == ["test-handler"]
    assert "hidden" not in serialized
    assert "secret-key" not in serialized
    assert "logical/file" not in serialized
    assert "sha256" not in serialized


def test_exclusive_move_is_passive_for_inspection_but_active_use_requires_ack():
    session = make_session()
    assert ProfileArtifactManager.preflight(session, purpose="inspect").access_mode == AccessMode.EXCLUSIVE_MOVE
    with pytest.raises(SessionPolicyError, match="exclusive move"):
        ProfileArtifactManager.preflight(session, purpose="launch")
    assert ProfileArtifactManager.preflight(
        session, purpose="launch", acknowledge_exclusive_move=True
    ).access_mode == AccessMode.EXCLUSIVE_MOVE


def test_profile_artifacts_are_rejected_by_gateway_and_proxy():
    session = make_session("clone")
    with pytest.raises(SessionPolicyError, match="does not support"):
        ProfileArtifactManager.preflight(session, purpose="gateway")
    with pytest.raises(SessionPolicyError, match="does not support"):
        ProfileArtifactManager.preflight(session, purpose="proxy")


def test_legacy_plugin_data_fails_closed_for_active_use():
    session = {"plugin_data": {"legacy": {"archive_base64": "abc"}}}
    with pytest.raises(SessionPolicyError, match="Legacy or mixed"):
        ProfileArtifactManager.preflight(session, purpose="launch")


def test_restore_stages_then_swaps_profile(tmp_path):
    session = make_session("clone")
    target = tmp_path / "profile"
    target.mkdir()
    (target / "old.txt").write_text("old")

    class Handler:
        def restore_profile_data(self, package, profile_path, browser):
            staged = Path(profile_path)
            assert staged != target
            assert (staged / "old.txt").read_text() == "old"
            (staged / "new.txt").write_text("new")
            return PluginResult(success=True, data={})

    loaded = type("Loaded", (), {"instance": Handler()})()
    with patch.object(ProfileArtifactManager, "_load_compatible_handler", return_value=loaded.instance):
        result = ProfileArtifactManager.restore(session, str(target), "brave")

    assert result["restored"] == 1
    assert (target / "old.txt").read_text() == "old"
    assert (target / "new.txt").read_text() == "new"


def test_invalid_artifact_checksum_is_rejected():
    session = make_session()
    session["profile_artifacts"][0]["content"]["sha256"] = "0" * 64
    with pytest.raises(ArtifactError, match="checksum"):
        ProfileArtifactManager.inspect(session)


def test_restore_rolls_back_when_final_swap_fails(tmp_path):
    session = make_session("clone")
    target = tmp_path / "profile"
    target.mkdir()
    (target / "old.txt").write_text("old")

    class Handler:
        def restore_profile_data(self, package, profile_path, browser):
            (Path(profile_path) / "new.txt").write_text("new")
            return PluginResult(success=True, data={})

    real_replace = __import__("os").replace
    calls = 0

    def fail_second_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated swap failure")
        return real_replace(source, destination)

    with patch.object(ProfileArtifactManager, "_load_compatible_handler", return_value=Handler()), \
         patch("tokenade.core.artifacts.manager.os.replace", side_effect=fail_second_replace):
        with pytest.raises(OSError, match="simulated"):
            ProfileArtifactManager.restore(session, str(target), "brave")

    assert (target / "old.txt").read_text() == "old"
    assert not (target / "new.txt").exists()


def test_dead_restore_lock_is_reclaimed(tmp_path):
    target = tmp_path / "profile"
    lock = tmp_path / ".profile.tokenade-lock"
    lock.write_text("999999999")
    with ProfileArtifactManager._target_lock(target):
        assert lock.exists()
    assert not lock.exists()


def test_single_use_claim_is_consumed(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    session = make_session("single_use")
    target = tmp_path / "profile"

    class Handler:
        def restore_profile_data(self, package, profile_path, browser):
            return PluginResult(success=True, data={})

    with patch.object(ProfileArtifactManager, "_load_compatible_handler", return_value=Handler()):
        ProfileArtifactManager.restore(session, str(target), "brave", allow_single_use=True)
        with pytest.raises(SessionPolicyError, match="consumed"):
            ProfileArtifactManager.restore(session, str(target), "brave", allow_single_use=True)


def test_inspect_cli_json_does_not_print_secrets(tmp_path, capsys):
    from tokenade.cli.handlers.session_ops import cmd_inspect
    session_path = tmp_path / "session.tokenade"
    session_path.write_text(json.dumps(make_session()))
    cmd_inspect(Namespace(session=str(session_path), decrypt_password=None, json=True))
    output = capsys.readouterr().out
    assert '"access_mode": "exclusive_move"' in output
    assert "hidden" not in output
    assert "secret-key" not in output


def test_artifact_envelope_contains_payload_once():
    session = make_session()
    serialized = json.dumps(session)
    encoded = make_payload()["archive_base64"]
    assert serialized.count(encoded) == 1
    assert "plugin_data" not in session
    assert session["profile_artifacts"][0]["access"]["mode"] == "exclusive_move"


def test_web_storage_supersession_is_declarative():
    assert ProfileArtifactManager.web_storage_is_superseded(make_session()) is True
    session = make_session()
    session["profile_artifacts"][0]["supersedes"] = []
    assert ProfileArtifactManager.web_storage_is_superseded(session) is False


def test_load_compatible_handler_rejects_inactive_plugin():
    """CR-05: _load_compatible_handler rejects loaded-but-not-active plugins."""
    from unittest.mock import MagicMock

    from tokenade.core.integration.plugin_loader import PluginState

    fake_loaded = MagicMock()
    fake_loaded.is_active = False
    fake_loaded.state = PluginState.LOADED

    fake_loader = MagicMock()
    fake_loader.get_manifest.return_value = {
        "version": "1.0.0",
        "dependencies": [],
    }
    fake_loader.is_disabled.return_value = False
    fake_loader.load_by_name.return_value = fake_loaded

    artifact = {
        "owner": {"plugin": "test-plugin"},
        "requirements": {
            "plugins": [{"name": "test-plugin", "version": ">=1.0.0"}]
        },
    }

    with patch(
        "tokenade.core.integration.plugin_loader.PluginLoader",
        return_value=fake_loader,
    ), patch(
        "tokenade.core.integration.plugin_dependencies.check_runtime_dependencies"
    ) as mock_rt:
        mock_rt.return_value = MagicMock(ready=True)
        with pytest.raises(ArtifactError, match="not active"):
            ProfileArtifactManager._load_compatible_handler(artifact)
