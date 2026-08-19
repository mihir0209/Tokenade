"""Tests for dependency-aware plugin loading in PluginLoader."""

import json
import logging

import pytest

from tokenade.core.integration.plugin_loader import PluginLoader


def _write_plugin(root, name, plugin_type="handler", dependencies=None, entry_class="DepPlugin"):
    plugin_dir = root / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps(
            {
                "name": name,
                "version": "1.0",
                "type": plugin_type,
                "entry_point": "plugin.py",
                "entry_class": entry_class,
                "dependencies": dependencies or [],
            }
        )
    )
    (plugin_dir / "plugin.py").write_text(
        "class DepPlugin:\n"
        "    def __init__(self): self.loaded = True\n"
        "    def can_handle(self, url): return True\n"
        "    def extract_session(self, ctx, url): return None\n"
        "    def inject_session(self, ctx, session): return None\n"
    )


@pytest.fixture
def loader(tmp_path):
    return PluginLoader(plugins_dir=tmp_path)


def test_load_by_name_loads_dependencies_first(tmp_path):
    _write_plugin(tmp_path, "core-detector", plugin_type="challenge_detector")
    _write_plugin(tmp_path, "solver", plugin_type="challenge_solver")
    _write_plugin(tmp_path, "site", dependencies=["core-detector", "solver"])

    loader = PluginLoader(plugins_dir=tmp_path)
    result = loader.load_by_name("site")

    assert result is not None
    assert result.name == "site"
    names = list(loader._loaded)
    assert names.index("core-detector") < names.index("site")
    assert names.index("solver") < names.index("site")
    assert loader.get_challenge_detector("core-detector") is not None
    assert loader.get_challenge_solver("solver") is not None


def test_load_by_name_transitive_dependencies(tmp_path):
    _write_plugin(tmp_path, "base-lib", plugin_type="challenge_detector")
    _write_plugin(tmp_path, "mid-lib", dependencies=["base-lib"], plugin_type="challenge_solver")
    _write_plugin(tmp_path, "app", dependencies=["mid-lib"])

    loader = PluginLoader(plugins_dir=tmp_path)
    result = loader.load_by_name("app")

    assert result is not None
    names = list(loader._loaded)
    assert names == ["base-lib", "mid-lib", "app"]


def test_load_by_name_circular_dependency_does_not_hang(tmp_path, caplog):
    _write_plugin(tmp_path, "plugin-a", dependencies=["plugin-b"])
    _write_plugin(tmp_path, "plugin-b", dependencies=["plugin-a"])

    loader = PluginLoader(plugins_dir=tmp_path)
    with caplog.at_level(logging.ERROR, logger="tokenade.core.integration.plugin_loader"):
        result = loader.load_by_name("plugin-a")

    assert result is not None
    assert "Circular plugin dependency" in caplog.text
    assert set(loader._loaded) == {"plugin-a", "plugin-b"}


def test_load_by_name_missing_dependency_still_loads_plugin(tmp_path, caplog):
    _write_plugin(tmp_path, "orphan", dependencies=["ghost-dep"])

    loader = PluginLoader(plugins_dir=tmp_path)
    with caplog.at_level(logging.ERROR, logger="tokenade.core.integration.plugin_loader"):
        result = loader.load_by_name("orphan")

    assert result is not None
    assert "Plugin not installed: ghost-dep" in caplog.text


def test_load_all_loads_in_dependency_order(tmp_path):
    _write_plugin(tmp_path, "aaa-site", dependencies=["bbb-solver"], plugin_type="handler")
    _write_plugin(tmp_path, "bbb-solver", dependencies=["ccc-detector"], plugin_type="challenge_solver")
    _write_plugin(tmp_path, "ccc-detector", plugin_type="challenge_detector")

    loader = PluginLoader(plugins_dir=tmp_path)
    count = loader.load_all()

    assert count == 3
    names = list(loader._loaded)
    assert names.index("ccc-detector") < names.index("bbb-solver") < names.index("aaa-site")


def test_load_all_missing_dependency_warns_and_loads_rest(tmp_path, caplog):
    _write_plugin(tmp_path, "needy", dependencies=["not-installed"])
    _write_plugin(tmp_path, "plain")

    loader = PluginLoader(plugins_dir=tmp_path)
    with caplog.at_level(logging.WARNING, logger="tokenade.core.integration.plugin_loader"):
        count = loader.load_all()

    assert count == 2
    assert "depends on missing plugin: not-installed" in caplog.text


def test_load_all_circular_dependency_does_not_hang(tmp_path, caplog):
    _write_plugin(tmp_path, "plugin-a", dependencies=["plugin-b"])
    _write_plugin(tmp_path, "plugin-b", dependencies=["plugin-a"])

    loader = PluginLoader(plugins_dir=tmp_path)
    with caplog.at_level(logging.ERROR, logger="tokenade.core.integration.plugin_loader"):
        count = loader.load_all()

    assert count == 2
    assert "Circular plugin dependency" in caplog.text
