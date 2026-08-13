"""Tests for plugin loader."""

import json

from tokenade.core.integration.plugin_loader import LoadedPlugin, PluginLoader, PluginState


class TestLoadedPlugin:
    def test_dataclass(self):
        p = LoadedPlugin(name="test", version="1.0", description="desc", plugin_type="handler",
                         module=None, entry_class=None, instance=None)
        assert p.name == "test"
        assert p.instance is None


class TestPluginLoaderDiscovery:
    def test_discover_empty_dir(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        plugins = loader.discover()
        assert plugins == []

    def test_discover_nonexistent_dir(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path / "nonexistent")
        plugins = loader.discover()
        assert plugins == []

    def test_discover_with_valid_plugin(self, tmp_path):
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        manifest = plugin_dir / "plugin.json"
        manifest.write_text(json.dumps({
            "name": "my-plugin",
            "version": "1.0.0",
            "type": "handler",
            "entry_point": "handler.py",
        }))

        loader = PluginLoader(plugins_dir=tmp_path)
        plugins = loader.discover()
        assert len(plugins) == 1
        assert plugins[0]["name"] == "my-plugin"
        assert "_path" in plugins[0]

    def test_discover_skips_hidden_dirs(self, tmp_path):
        hidden = tmp_path / ".hidden-plugin"
        hidden.mkdir()
        (hidden / "plugin.json").write_text('{"name": "hidden"}')

        loader = PluginLoader(plugins_dir=tmp_path)
        plugins = loader.discover()
        assert plugins == []

    def test_discover_skips_files(self, tmp_path):
        (tmp_path / "not-a-dir.json").write_text('{"name": "bad"}')

        loader = PluginLoader(plugins_dir=tmp_path)
        plugins = loader.discover()
        assert plugins == []

    def test_discover_skips_dirs_without_manifest(self, tmp_path):
        (tmp_path / "no-manifest").mkdir()

        loader = PluginLoader(plugins_dir=tmp_path)
        plugins = loader.discover()
        assert plugins == []

    def test_discover_handles_invalid_json(self, tmp_path):
        plugin_dir = tmp_path / "bad-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text("not json {{{")

        loader = PluginLoader(plugins_dir=tmp_path)
        plugins = loader.discover()
        assert plugins == []


class TestPluginLoaderLoadPlugin:
    def test_load_already_loaded(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        loader._loaded["test"] = LoadedPlugin(
            name="test", version="1.0", description="", plugin_type="handler",
            module=None, entry_class=None, instance="cached"
        )
        result = loader.load_plugin({"name": "test"})
        assert result.instance == "cached"

    def test_load_no_entry_point(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.load_plugin({"name": "test", "_path": str(tmp_path)})
        assert result is None

    def test_load_missing_entry_file(self, tmp_path):
        plugin_dir = tmp_path / "test"
        plugin_dir.mkdir()
        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.load_plugin({
            "name": "test",
            "entry_point": "handler.py",
            "_path": str(plugin_dir),
        })
        assert result is None

    def test_load_with_real_plugin(self, tmp_path):
        plugin_dir = tmp_path / "myhandler"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "myhandler",
            "version": "2.0",
            "type": "handler",
            "site_name": "example.com",
            "entry_point": "handler.py",
            "entry_class": "MyHandler",
        }))
        (plugin_dir / "handler.py").write_text(
            "class MyHandler:\n    def check_auth(self, cookies):\n        return True\n"
        )

        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.load_plugin({
            "name": "myhandler",
            "version": "2.0",
            "type": "handler",
            "site_name": "example.com",
            "entry_point": "handler.py",
            "entry_class": "MyHandler",
            "_path": str(plugin_dir),
        })
        assert result is not None
        assert result.name == "myhandler"
        assert result.version == "2.0"
        assert result.instance.check_auth([]) is True
        assert loader.get_handler("example.com") is result.instance

    def test_load_export_format_plugin(self, tmp_path):
        plugin_dir = tmp_path / "exporter"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "exporter",
            "version": "1.0",
            "type": "export_format",
            "format_name": "myformat",
            "entry_point": "exporter.py",
            "entry_class": "MyExporter",
        }))
        (plugin_dir / "exporter.py").write_text(
            "class MyExporter:\n    def export(self, session):\n        return 'exported'\n"
        )

        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.load_plugin({
            "name": "exporter", "version": "1.0", "type": "export_format",
            "format_name": "myformat", "entry_point": "exporter.py",
            "entry_class": "MyExporter", "_path": str(plugin_dir),
        })
        assert result is not None
        assert loader.get_exporter("myformat") is result.instance

    def test_load_validator_plugin(self, tmp_path):
        plugin_dir = tmp_path / "validator"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "validator",
            "version": "1.0",
            "type": "validator",
            "rule_name": "my-rule",
            "entry_point": "validator.py",
            "entry_class": "MyValidator",
        }))
        (plugin_dir / "validator.py").write_text(
            "class MyValidator:\n    def validate(self, session):\n        return True\n"
        )

        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.load_plugin({
            "name": "validator", "version": "1.0", "type": "validator",
            "rule_name": "my-rule", "entry_point": "validator.py",
            "entry_class": "MyValidator", "_path": str(plugin_dir),
        })
        assert result is not None
        assert loader.get_validator("my-rule") is result.instance

    def test_unconfigured_optional_plugin_does_not_run_on_configure_or_warn(
        self, tmp_path, caplog
    ):
        plugin_dir = tmp_path / "webhook-notify"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps(
                {
                    "name": "webhook-notify",
                    "version": "1.0",
                    "type": "notification",
                    "entry_point": "plugin.py",
                    "entry_class": "WebhookPlugin",
                    "config": {
                        "schema": {
                            "webhook_url": {"type": "string", "required": True}
                        }
                    },
                }
            )
        )
        (plugin_dir / "plugin.py").write_text(
            "class WebhookPlugin:\n"
            "    def __init__(self): self.configured = False\n"
            "    def on_configure(self, config): self.configured = True\n"
        )

        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.load_by_name("webhook-notify")

        assert result is not None
        assert result.instance.configured is False
        assert result.state == PluginState.LOADED
        assert result.instance not in loader._notifications.values()
        assert "config validation errors" not in caplog.text

    def test_load_no_entry_class(self, tmp_path):
        plugin_dir = tmp_path / "noclass"
        plugin_dir.mkdir()
        (plugin_dir / "noclass.py").write_text("x = 1\n")

        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.load_plugin({
            "name": "noclass", "entry_point": "noclass.py", "_path": str(plugin_dir),
        })
        assert result is None


class TestPluginLoaderUnload:
    def test_unload_existing(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        instance = type("H", (), {})()
        loader._loaded["test"] = LoadedPlugin(
            name="test", version="1.0", description="", plugin_type="handler",
            module=None, entry_class=None, instance=instance
        )
        loader._handlers["site"] = instance

        assert loader.unload("test") is True
        assert "test" not in loader._loaded
        assert "site" not in loader._handlers

    def test_unload_nonexistent(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        assert loader.unload("nonexistent") is False


class TestPluginLoaderGetters:
    def test_get_handler_missing(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        assert loader.get_handler("missing") is None

    def test_get_exporter_missing(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        assert loader.get_exporter("missing") is None

    def test_get_validator_missing(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        assert loader.get_validator("missing") is None

    def test_list_handlers(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        loader._handlers["a"] = "handler_a"
        result = loader.list_handlers()
        assert result == {"a": "handler_a"}
        assert result is not loader._handlers

    def test_list_exporters(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        loader._exporters[""] = "exporter_f"
        result = loader.list_exporters()
        assert result == {"": "exporter_f"}

    def test_list_validators(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        loader._validators["r"] = "validator_r"
        result = loader.list_validators()
        assert result == {"r": "validator_r"}

    def test_list_all(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        p = LoadedPlugin(name="x", version="1.0", description="", plugin_type="handler",
                         module=None, entry_class=None)
        loader._loaded["x"] = p
        assert loader.list_all() == [p]


class TestPluginLoaderReload:
    def test_reload_nonexistent_manifest(self, tmp_path):
        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.reload("nonexistent")
        assert result is None

    def test_reload_with_real_plugin(self, tmp_path):
        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "myplugin", "version": "1.0", "type": "handler",
            "site_name": "test.com", "entry_point": "handler.py", "entry_class": "H",
        }))
        (plugin_dir / "handler.py").write_text("class H:\n    pass\n")

        loader = PluginLoader(plugins_dir=tmp_path)
        result = loader.reload("myplugin")
        assert result is not None
        assert result.name == "myplugin"


class TestPluginLoaderLoadAll:
    def test_load_all(self, tmp_path):
        plugin_dir = tmp_path / "p1"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "p1", "version": "1.0", "type": "handler",
            "site_name": "s1.com", "entry_point": "h.py", "entry_class": "H",
        }))
        (plugin_dir / "h.py").write_text("class H:\n    pass\n")

        loader = PluginLoader(plugins_dir=tmp_path)
        count = loader.load_all()
        assert count == 1

    def test_load_all_with_error(self, tmp_path):
        plugin_dir = tmp_path / "bad"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "bad", "version": "1.0", "entry_point": "missing.py",
        }))

        loader = PluginLoader(plugins_dir=tmp_path)
        count = loader.load_all()
        assert count == 0
