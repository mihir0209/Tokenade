import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts/release_all.py"


def load_release_module():
    spec = importlib.util.spec_from_file_location("release_all", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_refuses_dirty_worktree(monkeypatch, tmp_path):
    release = load_release_module()
    monkeypatch.setattr(release, "output", lambda *args, **kwargs: (
        "main" if args[:2] == ("git", "branch") else "dirty"
    ))
    with pytest.raises(SystemExit, match="not clean"):
        release.require_clean_pushed(tmp_path)


def test_release_refuses_unpushed_head(monkeypatch, tmp_path):
    release = load_release_module()
    responses = iter(["main", "", "codeberg/main", "head", "remote"])
    monkeypatch.setattr(release, "output", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(release, "run", lambda *args, **kwargs: None)
    with pytest.raises(SystemExit, match="codeberg/main"):
        release.require_clean_pushed(tmp_path)


def test_release_requires_unpublished_version(monkeypatch):
    release = load_release_module()

    class Response:
        pass

    monkeypatch.setattr(release.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    with pytest.raises(SystemExit, match="already exists"):
        release.ensure_unpublished("9.9.9")
