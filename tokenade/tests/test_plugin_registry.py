"""Tests for plugin registry."""

import json
import time
import urllib.error
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from tokenade.core.integration.plugin_registry import Plugin, PluginRegistry


class TestPlugin:
    def test_dataclass(self):
        p = Plugin(name="test", version="1.0", description="desc", author="me",
                   url="http://x", type="handler", entry_point="h.py")
        assert p.name == "test"
        assert p.dependencies == []

    def test_post_init_with_deps(self):
        p = Plugin(name="test", version="1.0", description="", author="",
                   url="", type="handler", entry_point="h.py", dependencies=["a", "b"])
        assert p.dependencies == ["a", "b"]


class TestPluginRegistrySearch:
    def test_search_empty_registry(self, tmp_path):
        registry = PluginRegistry(plugins_dir=tmp_path)
        with patch.object(registry, "_fetch_registry", return_value=[]):
            results = registry.search()
            assert results == []

    def test_search_by_query(self, tmp_path):
        plugins = [
            {"name": "github-handler", "description": "GitHub integration", "type": "handler", "author": "alice"},
            {"name": "gmail-handler", "description": "Gmail integration", "type": "handler", "author": "bob"},
            {"name": "json-exporter", "description": "JSON export", "type": "export_format", "author": "alice"},
        ]
        registry = PluginRegistry(plugins_dir=tmp_path)
        with patch.object(registry, "_fetch_registry", return_value=plugins):
            results = registry.search(query="github")
            assert len(results) == 1
            assert results[0]["name"] == "github-handler"

    def test_search_by_type(self, tmp_path):
        plugins = [
            {"name": "handler1", "type": "handler"},
            {"name": "exporter1", "type": "export_format"},
            {"name": "handler2", "type": "handler"},
        ]
        registry = PluginRegistry(plugins_dir=tmp_path)
        with patch.object(registry, "_fetch_registry", return_value=plugins):
            results = registry.search(plugin_type="handler")
            assert len(results) == 2

    def test_search_by_author(self, tmp_path):
        plugins = [
            {"name": "a", "description": "", "author": "alice"},
            {"name": "b", "description": "", "author": "bob"},
        ]
        registry = PluginRegistry(plugins_dir=tmp_path)
        with patch.object(registry, "_fetch_registry", return_value=plugins):
            results = registry.search(query="alice")
            assert len(results) == 1


class TestPluginRegistryInstall:
    def test_install_not_found(self, tmp_path):
        registry = PluginRegistry(plugins_dir=tmp_path)
        with patch.object(registry, "_fetch_registry", return_value=[]):
            result = registry.install("nonexistent")
            assert result is False

    def test_install_already_installed(self, tmp_path):
        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({"name": "myplugin"}))

        registry = PluginRegistry(plugins_dir=tmp_path)
        with patch.object(registry, "_fetch_registry", return_value=[
            {"name": "myplugin", "version": "1.0"}
        ]):
            result = registry.install("myplugin")
            assert result is True

    def test_install_missing_dependency(self, tmp_path):
        registry = PluginRegistry(plugins_dir=tmp_path)
        with patch.object(registry, "_fetch_registry", return_value=[
            {"name": "dep-required", "dependencies": ["missing-dep"]}
        ]):
            result = registry.install("dep-required")
            assert result is False

    @patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen")
    def test_install_success(self, mock_urlopen, tmp_path):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"name": "test"}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        registry = PluginRegistry(plugins_dir=tmp_path)
        with patch.object(registry, "_fetch_registry", return_value=[
            {"name": "new-plugin", "files": ["handler.py"]}
        ]):
            result = registry.install("new-plugin")
            assert result is True
            assert (tmp_path / "new-plugin" / "plugin.json").exists()


class TestPluginRegistryUninstall:
    def test_uninstall_not_installed(self, tmp_path):
        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry.uninstall("nonexistent")
        assert result is False

    def test_uninstall_success(self, tmp_path):
        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "myplugin", "version": "1.0",
        }))

        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry.uninstall("myplugin")
        assert result is True
        assert not plugin_dir.exists()

    def test_uninstall_dependency_blocked(self, tmp_path):
        # Plugin A depends on B
        a_dir = tmp_path / "pluginA"
        a_dir.mkdir()
        (a_dir / "plugin.json").write_text(json.dumps({
            "name": "pluginA", "dependencies": ["pluginB"],
        }))
        b_dir = tmp_path / "pluginB"
        b_dir.mkdir()
        (b_dir / "plugin.json").write_text(json.dumps({
            "name": "pluginB",
        }))

        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry.uninstall("pluginB")
        assert result is False
        assert b_dir.exists()


class TestPluginRegistryListInstalled:
    def test_list_empty(self, tmp_path):
        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry.list_installed()
        assert result == []

    def test_list_with_plugins(self, tmp_path):
        for name in ["alpha", "beta"]:
            d = tmp_path / name
            d.mkdir()
            (d / "plugin.json").write_text(json.dumps({
                "name": name, "version": "1.0", "type": "handler",
                "entry_point": "h.py",
            }))

        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry.list_installed()
        assert len(result) == 2
        assert all(isinstance(p, Plugin) for p in result)
        assert result[0].name == "alpha"

    def test_list_skips_hidden_dirs(self, tmp_path):
        d = tmp_path / ".hidden"
        d.mkdir()
        (d / "plugin.json").write_text(json.dumps({"name": "hidden"}))

        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry.list_installed()
        assert result == []

    def test_list_skips_dirs_without_manifest(self, tmp_path):
        (tmp_path / "no-manifest").mkdir()

        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry.list_installed()
        assert result == []


class TestPluginRegistryFetchRegistry:
    def test_fetch_from_cache(self, tmp_path):
        cache = tmp_path / ".registry_cache.json"
        cache.write_text(json.dumps({
            "timestamp": time.time(),
            "plugins": [{"name": "cached"}],
        }))

        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry._fetch_registry()
        assert len(result) == 1
        assert result[0]["name"] == "cached"

    def test_fetch_stale_cache(self, tmp_path):
        cache = tmp_path / ".registry_cache.json"
        cache.write_text(json.dumps({
            "timestamp": time.time() - 7200,
            "plugins": [{"name": "stale"}],
        }))

        registry = PluginRegistry(plugins_dir=tmp_path)
        with patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen") as mock:
            mock.side_effect = urllib.error.URLError("network error")
            result = registry._fetch_registry()
            assert result == []

    def test_fetch_network_error(self, tmp_path):
        registry = PluginRegistry(plugins_dir=tmp_path)
        with patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen") as mock:
            mock.side_effect = urllib.error.URLError("network error")
            result = registry._fetch_registry()
            assert result == []


class TestPluginRegistryUpdate:
    def test_update_all_no_updates(self, tmp_path):
        d = tmp_path / "myplugin"
        d.mkdir()
        (d / "plugin.json").write_text(json.dumps({
            "name": "myplugin", "version": "1.0",
        }))

        registry = PluginRegistry(plugins_dir=tmp_path)
        with patch.object(registry, "_fetch_registry", return_value=[
            {"name": "myplugin", "version": "1.0"},
        ]):
            count = registry.update()
            assert count == 0

    def test_update_specific_plugin(self, tmp_path):
        d = tmp_path / "myplugin"
        d.mkdir()
        (d / "plugin.json").write_text(json.dumps({
            "name": "myplugin", "version": "1.0",
        }))

        registry = PluginRegistry(plugins_dir=tmp_path)
        with patch.object(registry, "_fetch_registry", return_value=[
            {"name": "myplugin", "version": "2.0", "files": []},
        ]):
            with patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen") as mock:
                mock_response = MagicMock()
                mock_response.read.return_value = b'{"name": "myplugin", "version": "2.0"}'
                mock_response.__enter__ = lambda s: s
                mock_response.__exit__ = MagicMock(return_value=False)
                mock.return_value = mock_response
                count = registry.update("myplugin")
                assert count == 1
