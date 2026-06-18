"""Tests for plugin loader - coverage boost."""

import json

from tokenade.core.integration.plugin_loader import PluginLoader, LoadedPlugin, DEFAULT_PLUGINS_DIR


class TestPluginLoaderDisabled:
    def test_load_all_skips_disabled(self, tmp_path):
        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "myplugin", "version": "1.0", "type": "handler",
            "site_name": "test.com", "entry_point": "handler.py", "entry_class": "H",
        }))
        (plugin_dir / "handler.py").write_text("class H:\n    pass\n")

        disabled_file = tmp_path / ".disabled"
        disabled_file.write_text("myplugin\n")

        loader = PluginLoader(plugins_dir=tmp_path)
        count = loader.load_all()
        assert count == 0

    def test_load_all_with_load_error(self, tmp_path):
        plugin_dir = tmp_path / "error_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "error_plugin", "version": "1.0", "type": "handler",
            "entry_point": "bad.py",
        }))
        (plugin_dir / "bad.py").write_text("raise ImportError('fail')")

        loader = PluginLoader(plugins_dir=tmp_path)
        count = loader.load_all()
        assert count == 0

    def test_load_plugin_import_error(self, tmp_path):
        plugin_dir = tmp_path / "bad_import"
        plugin_dir.mkdir()
        (plugin_dir / "bad.py").write_text("raise ImportError('broken')")

        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.load_plugin({
            "name": "bad_import", "entry_point": "bad.py", "_path": str(plugin_dir),
        })
        assert result is None

    def test_load_plugin_instantiation_error(self, tmp_path):
        plugin_dir = tmp_path / "bad_init"
        plugin_dir.mkdir()
        (plugin_dir / "bad_init.py").write_text("class H:\n    def __init__(self):\n        raise RuntimeError('init fail')")

        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.load_plugin({
            "name": "bad_init", "entry_point": "bad_init.py", "entry_class": "H",
            "_path": str(plugin_dir),
        })
        assert result is None

    def test_load_plugin_auto_discover_handler(self, tmp_path):
        plugin_dir = tmp_path / "auto_handler"
        plugin_dir.mkdir()
        (plugin_dir / "handler.py").write_text("class SiteHandler:\n    pass\n")

        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.load_plugin({
            "name": "auto_handler", "type": "handler",
            "entry_point": "handler.py", "_path": str(plugin_dir),
        })
        assert result is not None
        assert result.entry_class.__name__ == "SiteHandler"

    def test_load_plugin_auto_discover_export_format(self, tmp_path):
        plugin_dir = tmp_path / "auto_export"
        plugin_dir.mkdir()
        (plugin_dir / "exporter.py").write_text("class ExportFormat:\n    pass\n")

        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.load_plugin({
            "name": "auto_export", "type": "export_format",
            "entry_point": "exporter.py", "_path": str(plugin_dir),
        })
        assert result is not None

    def test_load_plugin_auto_discover_validator(self, tmp_path):
        plugin_dir = tmp_path / "auto_valid"
        plugin_dir.mkdir()
        (plugin_dir / "validator.py").write_text("class SessionValidator:\n    pass\n")

        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.load_plugin({
            "name": "auto_valid", "type": "validator",
            "entry_point": "validator.py", "_path": str(plugin_dir),
        })
        assert result is not None

    def test_load_plugin_auto_discover_unknown_type(self, tmp_path):
        plugin_dir = tmp_path / "auto_unknown"
        plugin_dir.mkdir()
        (plugin_dir / "unknown.py").write_text("class Something:\n    pass\n")

        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.load_plugin({
            "name": "auto_unknown", "type": "unknown_type",
            "entry_point": "unknown.py", "_path": str(plugin_dir),
        })
        assert result is None

    def test_unload_export_format(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        instance = type("E", (), {})()
        loader._loaded["test"] = LoadedPlugin(
            name="test", version="1.0", description="", plugin_type="export_format",
            module=None, entry_class=None, instance=instance,
        )
        loader._exporters["myformat"] = instance
        assert loader.unload("test") is True
        assert "myformat" not in loader._exporters

    def test_unload_validator(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        instance = type("V", (), {})()
        loader._loaded["test"] = LoadedPlugin(
            name="test", version="1.0", description="", plugin_type="validator",
            module=None, entry_class=None, instance=instance,
        )
        loader._validators["my-rule"] = instance
        assert loader.unload("test") is True
        assert "my-rule" not in loader._validators

    def test_disable_plugin(self, tmp_path):
        plugin_dir = tmp_path / "disabler"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "disabler", "version": "1.0", "type": "handler",
            "site_name": "d.com", "entry_point": "h.py", "entry_class": "H",
        }))
        (plugin_dir / "h.py").write_text("class H:\n    pass\n")

        loader = PluginLoader(plugins_dir=tmp_path)
        loader.load_plugin({
            "name": "disabler", "version": "1.0", "type": "handler",
            "site_name": "d.com", "entry_point": "h.py", "entry_class": "H",
            "_path": str(plugin_dir),
        })
        result = loader.disable("disabler")
        assert result is True
        assert "disabler" in loader._disabled

    def test_disable_nonexistent_plugin(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.disable("nonexistent")
        assert result is False

    def test_enable_plugin(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        loader._disabled.add("myplugin")
        result = loader.enable("myplugin")
        assert result is True
        assert "myplugin" not in loader._disabled

    def test_enable_already_enabled(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.enable("already_enabled")
        assert result is True

    def test_enable_updates_loaded_plugin(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        loader._disabled.add("myplugin")
        loader._loaded["myplugin"] = LoadedPlugin(
            name="myplugin", version="1.0", description="", plugin_type="handler",
            module=None, entry_class=None, enabled=False,
        )
        loader.enable("myplugin")
        assert loader._loaded["myplugin"].enabled is True

    def test_save_disabled_list(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        loader._disabled = {"b_plugin", "a_plugin"}
        loader._save_disabled_list()
        disabled_file = tmp_path / ".disabled"
        content = disabled_file.read_text()
        lines = content.strip().split("\n")
        assert lines == ["a_plugin", "b_plugin"]

    def test_load_disabled_list_exception(self, tmp_path):
        disabled_file = tmp_path / ".disabled"
        disabled_file.write_text("bad\n")
        loader = PluginLoader(plugins_dir=tmp_path)
        assert loader._disabled == {"bad"}

    def test_load_disabled_list_file_not_exists(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        assert loader._disabled == set()

    def test_discover_names(self, tmp_path):
        plugin_dir = tmp_path / "p1"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({"name": "p1"}))

        loader = PluginLoader(plugins_dir=tmp_path)
        names = loader.discover_names()
        assert "p1" in names

    def test_discover_names_empty(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        names = loader.discover_names()
        assert names == set()

    def test_reload_nonexistent(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.reload("nonexistent")
        assert result is None

    def test_load_plugin_default_plugins_dir(self):
        loader = PluginLoader()
        assert loader.plugins_dir == DEFAULT_PLUGINS_DIR

    def test_loaded_plugin_dataclass(self):
        p = LoadedPlugin(
            name="test", version="2.0", description="desc",
            plugin_type="handler", module="mod", entry_class="cls",
            instance="inst", enabled=True,
        )
        assert p.name == "test"
        assert p.instance == "inst"
        assert p.enabled is True

    def test_loaded_plugin_defaults(self):
        p = LoadedPlugin(
            name="test", version="1.0", description="",
            plugin_type="handler", module=None, entry_class=None,
        )
        assert p.instance is None
        assert p.enabled is True
