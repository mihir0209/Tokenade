"""Tests for plugin registry."""

import json
import time
import urllib.error
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

    def test_install_auto_installs_dependency(self, tmp_path):
        registry = PluginRegistry(plugins_dir=tmp_path)
        plugins = [
            {"name": "base-lib", "version": "1.0", "entry_point": "plugin.py", "dependencies": []},
            {"name": "app-plugin", "version": "1.0", "entry_point": "plugin.py", "dependencies": ["base-lib"]},
        ]
        call_count = [0]

        def mock_download(meta, reg=None):
            d = tmp_path / meta["name"]
            d.mkdir(exist_ok=True)
            (d / "plugin.json").write_text(json.dumps(meta))
            (d / "plugin.py").write_text("# plugin")
            call_count[0] += 1
            return True

        with patch.object(registry, "_fetch_registry", return_value=plugins), \
             patch.object(registry, "_download_plugin", side_effect=mock_download):
            result = registry.install("app-plugin")
            assert result is True
            assert call_count[0] == 2
            assert (tmp_path / "base-lib" / "plugin.json").exists()
            assert (tmp_path / "app-plugin" / "plugin.json").exists()

    def test_install_circular_dependency_detected(self, tmp_path):
        registry = PluginRegistry(plugins_dir=tmp_path)
        plugins = [
            {"name": "plugin-a", "dependencies": ["plugin-b"]},
            {"name": "plugin-b", "dependencies": ["plugin-a"]},
        ]
        with patch.object(registry, "_fetch_registry", return_value=plugins), \
             patch.object(registry, "_download_plugin", return_value=True):
            result = registry.install("plugin-a")
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
        registry = PluginRegistry(
            plugins_dir=tmp_path,
            registry_url="https://example.com/reg",
        )
        cache = registry._cache_file
        cache.write_text(json.dumps({
            "timestamp": time.time(),
            "plugins": [{"name": "cached"}],
        }))
        result = registry._fetch_registry()
        assert len(result) == 1
        assert result[0]["name"] == "cached"

    def test_fetch_stale_cache(self, tmp_path):
        registry = PluginRegistry(
            plugins_dir=tmp_path,
            registry_url="https://example.com/reg",
        )
        cache = registry._cache_file
        cache.write_text(json.dumps({
            "timestamp": time.time() - 7200,
            "plugins": [{"name": "stale"}],
        }))
        with patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen") as mock:
            mock.side_effect = urllib.error.URLError("network error")
            result = registry._fetch_registry()
            assert result == []

    def test_fetch_network_error(self, tmp_path):
        registry = PluginRegistry(
            plugins_dir=tmp_path,
            registry_url="https://example.com/reg",
        )
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
            result = registry.update()
            assert result["updated"] == []
            assert "myplugin" in result["skipped"]

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
                result = registry.update("myplugin")
                assert len(result["updated"]) == 1
                assert "myplugin" in result["updated"][0]

    def test_update_plugin_not_in_registry(self, tmp_path):
        d = tmp_path / "myplugin"
        d.mkdir()
        (d / "plugin.json").write_text(json.dumps({
            "name": "myplugin", "version": "1.0",
        }))
        registry = PluginRegistry(plugins_dir=tmp_path)
        with patch.object(registry, "_fetch_registry", return_value=[]):
            result = registry.update()
            assert result["updated"] == []
            assert "myplugin" in result["skipped"]


class TestPluginRegistryDownload:
    @patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen")
    def test_download_network_error(self, mock_urlopen, tmp_path):
        mock_urlopen.side_effect = urllib.error.URLError("fail")
        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry._download_plugin({"name": "bad", "files": ["a.py"]})
        assert result is False

    @patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen")
    def test_download_success(self, mock_urlopen, tmp_path):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"content"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry._download_plugin({"name": "myplug", "files": ["handler.py"]})
        assert result is True
        assert (tmp_path / "myplug" / "plugin.json").exists()
        assert (tmp_path / "myplug" / "handler.py").exists()

    @patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen")
    def test_download_includes_site_config_when_available(self, mock_urlopen, tmp_path):
        contents = {
            "plugin.json": b'{"name":"github-handler","type":"handler"}',
            "plugin.py": b"# plugin",
            "site_config.json": b'{"name":"github","domains":["github.com"]}',
        }

        def fake_urlopen(req, timeout=30):
            filename = req.full_url.rsplit("/", 1)[-1]
            mock_resp = MagicMock()
            mock_resp.read.return_value = contents[filename]
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        mock_urlopen.side_effect = fake_urlopen

        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry._download_plugin({"name": "github-handler"})

        assert result is True
        assert (tmp_path / "github-handler" / "plugin.json").exists()
        assert (tmp_path / "github-handler" / "plugin.py").exists()
        assert (tmp_path / "github-handler" / "site_config.json").exists()

    @patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen")
    def test_download_missing_site_config_does_not_fail_plugin_install(self, mock_urlopen, tmp_path):
        def fake_urlopen(req, timeout=30):
            filename = req.full_url.rsplit("/", 1)[-1]
            if filename == "site_config.json":
                raise urllib.error.URLError("not found")
            mock_resp = MagicMock()
            mock_resp.read.return_value = b"content"
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        mock_urlopen.side_effect = fake_urlopen

        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry._download_plugin({"name": "utility-plugin"})

        assert result is True
        assert (tmp_path / "utility-plugin" / "plugin.json").exists()
        assert (tmp_path / "utility-plugin" / "plugin.py").exists()
        assert not (tmp_path / "utility-plugin" / "site_config.json").exists()

    @patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen")
    def test_install_then_discover_resolves_site_config(self, mock_urlopen, tmp_path):
        """After install, discover_plugin_site_configs resolves the freshly installed site."""
        from tokenade.core.importer.site_configs import discover_plugin_site_configs, get_site_config

        contents = {
            "plugin.json": b'{"name":"acme-handler","type":"handler","entry_point":"plugin.py"}',
            "plugin.py": b"# plugin",
            "site_config.json": b'{"name":"acme","domains":["acme.com"],"critical_cookies":["sid"]}',
        }

        def fake_urlopen(req, timeout=30):
            filename = req.full_url.rsplit("/", 1)[-1]
            mock_resp = MagicMock()
            mock_resp.read.return_value = contents[filename]
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        mock_urlopen.side_effect = fake_urlopen

        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry._download_plugin({"name": "acme-handler"})
        assert result is True

        found = discover_plugin_site_configs(tmp_path)
        assert "acme" in found
        assert found["acme"]["critical_cookies"] == ["sid"]
        assert get_site_config("acme", plugins_dir=tmp_path)["domains"] == ["acme.com"]


class TestPluginRegistryExtra:
    def test_list_bad_json_manifest(self, tmp_path):
        d = tmp_path / "broken"
        d.mkdir()
        (d / "plugin.json").write_text("NOT JSON {{{")
        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry.list_installed()
        assert result == []

    def test_list_os_error_manifest(self, tmp_path):
        d = tmp_path / "unreadable"
        d.mkdir()
        (d / "plugin.json").write_bytes(b"\x00\x01\x02")
        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry.list_installed()
        assert result == []

    def test_fetch_corrupt_cache_falls_back(self, tmp_path):
        cache = tmp_path / ".registry_cache.json"
        cache.write_text("NOT JSON {{{")
        registry = PluginRegistry(plugins_dir=tmp_path)
        with patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen") as mock:
            mock.side_effect = urllib.error.URLError("down")
            result = registry._fetch_registry()
            assert result == []

    @patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen")
    def test_fetch_success_from_network(self, mock_urlopen, tmp_path):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps([
            {"name": "remote-plugin", "version": "1.0"}
        ]).encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry._fetch_registry()
        assert len(result) == 1
        assert result[0]["name"] == "remote-plugin"
        assert registry._cache_file.exists()

    @patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen")
    def test_fetch_wraps_dict_response(self, mock_urlopen, tmp_path):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"plugins": [{"name": "p1"}]}).encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry._fetch_registry()
        assert len(result) == 1

    @patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen")
    def test_fetch_timeout(self, mock_urlopen, tmp_path):
        mock_urlopen.side_effect = urllib.error.URLError("timed out")
        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry._fetch_registry()
        assert result == []

    @patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen")
    def test_fetch_os_error(self, mock_urlopen, tmp_path):
        mock_urlopen.side_effect = OSError("disk full")
        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry._fetch_registry()
        assert result == []

    @patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen")
    def test_fetch_json_decode_error(self, mock_urlopen, tmp_path):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry._fetch_registry()
        assert result == []

    def test_update_skips_non_matching_name(self, tmp_path):
        d = tmp_path / "myplugin"
        d.mkdir()
        (d / "plugin.json").write_text(json.dumps({
            "name": "myplugin", "version": "1.0",
        }))
        d2 = tmp_path / "other"
        d2.mkdir()
        (d2 / "plugin.json").write_text(json.dumps({
            "name": "other", "version": "1.0",
        }))
        registry = PluginRegistry(plugins_dir=tmp_path)
        with patch.object(registry, "_fetch_registry", return_value=[
            {"name": "myplugin", "version": "2.0", "files": []},
            {"name": "other", "version": "2.0", "files": []},
        ]):
            with patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen") as mock:
                mock_resp = MagicMock()
                mock_resp.read.return_value = b'{"name":"x"}'
                mock_resp.__enter__ = lambda s: s
                mock_resp.__exit__ = MagicMock(return_value=False)
                mock.return_value = mock_resp
                result = registry.update("myplugin")
                assert len(result["updated"]) == 1
                assert "myplugin" in result["updated"][0]

    @patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen")
    def test_download_network_error(self, mock_urlopen, tmp_path):
        mock_urlopen.side_effect = urllib.error.URLError("fail")
        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry._download_plugin({"name": "bad", "files": ["a.py"]})
        assert result is False

    @patch("tokenade.core.integration.plugin_registry.urllib.request.urlopen")
    def test_download_success(self, mock_urlopen, tmp_path):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"content"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        registry = PluginRegistry(plugins_dir=tmp_path)
        result = registry._download_plugin({"name": "myplug", "files": ["handler.py"]})
        assert result is True
        assert (tmp_path / "myplug" / "plugin.json").exists()
        assert (tmp_path / "myplug" / "handler.py").exists()
