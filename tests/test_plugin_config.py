"""Unit tests for plugin configuration system.

Tests PluginConfigSchema, PluginConfig validation (types, constraints,
env_var), PluginConfigManager (load/save/delete/validate/has_config),
and global config merging.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tokenade.plugin.api import PluginConfig, PluginConfigSchema
from tokenade.core.integration.plugin_config import PluginConfigManager


class TestPluginConfigSchema:
    """Tests for PluginConfigSchema dataclass."""

    def test_basic_schema(self):
        schema = PluginConfigSchema(
            name="timeout",
            type="int",
            default=30,
            description="Request timeout",
        )
        assert schema.name == "timeout"
        assert schema.type == "int"
        assert schema.default == 30

    def test_schema_with_constraints(self):
        schema = PluginConfigSchema(
            name="port",
            type="int",
            min=1,
            max=65535,
            required=True,
        )
        assert schema.min == 1
        assert schema.max == 65535
        assert schema.required is True

    def test_schema_with_pattern(self):
        schema = PluginConfigSchema(
            name="slug",
            type="string",
            pattern="^[a-z0-9-]+$",
        )
        assert schema.pattern == "^[a-z0-9-]+$"

    def test_schema_with_choices(self):
        schema = PluginConfigSchema(
            name="mode",
            type="string",
            choices=["fast", "slow"],
            default="fast",
        )
        assert schema.choices == ["fast", "slow"]

    def test_schema_with_env_var(self):
        schema = PluginConfigSchema(
            name="api_key",
            type="string",
            env_var="TOKENADE_API_KEY",
            required=True,
        )
        assert schema.env_var == "TOKENADE_API_KEY"


class TestPluginConfigValidation:
    """Tests for PluginConfig.validate()."""

    def test_valid_config(self):
        schema = {
            "name": {"type": "string", "required": True},
            "timeout": {"type": "int", "default": 30, "min": 1, "max": 300},
        }
        config = PluginConfig(schema=schema, values={"name": "test", "timeout": 60})
        errors = config.validate()
        assert errors == []

    def test_missing_required(self):
        schema = {
            "api_key": {"type": "string", "required": True},
        }
        config = PluginConfig(schema=schema, values={})
        errors = config.validate()
        assert len(errors) == 1
        assert "Missing required" in errors[0]

    def test_wrong_type(self):
        schema = {
            "timeout": {"type": "int", "default": 30},
        }
        config = PluginConfig(schema=schema, values={"timeout": "not an int"})
        errors = config.validate()
        assert len(errors) == 1
        assert "must be int" in errors[0]

    def test_bool_type(self):
        schema = {
            "enabled": {"type": "bool", "default": True},
        }
        config = PluginConfig(schema=schema, values={"enabled": "yes"})
        errors = config.validate()
        assert len(errors) == 1
        assert "must be bool" in errors[0]

    def test_float_type(self):
        schema = {
            "rate": {"type": "float", "default": 1.0},
        }
        config = PluginConfig(schema=schema, values={"rate": "high"})
        errors = config.validate()
        assert len(errors) == 1
        assert "must be float" in errors[0]

    def test_list_type(self):
        schema = {
            "domains": {"type": "list", "default": []},
        }
        config = PluginConfig(schema=schema, values={"domains": "not a list"})
        errors = config.validate()
        assert len(errors) == 1
        assert "must be list" in errors[0]

    def test_dict_type(self):
        schema = {
            "settings": {"type": "dict", "default": {}},
        }
        config = PluginConfig(schema=schema, values={"settings": "not a dict"})
        errors = config.validate()
        assert len(errors) == 1
        assert "must be dict" in errors[0]

    def test_min_constraint(self):
        schema = {
            "port": {"type": "int", "min": 1, "max": 65535},
        }
        config = PluginConfig(schema=schema, values={"port": 0})
        errors = config.validate()
        assert len(errors) == 1
        assert "below min" in errors[0]

    def test_max_constraint(self):
        schema = {
            "port": {"type": "int", "min": 1, "max": 65535},
        }
        config = PluginConfig(schema=schema, values={"port": 70000})
        errors = config.validate()
        assert len(errors) == 1
        assert "exceeds max" in errors[0]

    def test_pattern_constraint(self):
        schema = {
            "slug": {"type": "string", "pattern": "^[a-z0-9-]+$"},
        }
        config = PluginConfig(schema=schema, values={"slug": "Invalid Slug!"})
        errors = config.validate()
        assert len(errors) == 1
        assert "pattern" in errors[0]

    def test_pattern_constraint_valid(self):
        schema = {
            "slug": {"type": "string", "pattern": "^[a-z0-9-]+$"},
        }
        config = PluginConfig(schema=schema, values={"slug": "my-plugin"})
        errors = config.validate()
        assert errors == []

    def test_choices_constraint(self):
        schema = {
            "mode": {"type": "string", "choices": ["fast", "slow"]},
        }
        config = PluginConfig(schema=schema, values={"mode": "medium"})
        errors = config.validate()
        assert len(errors) == 1
        assert "not in choices" in errors[0]

    def test_choices_valid(self):
        schema = {
            "mode": {"type": "string", "choices": ["fast", "slow"]},
        }
        config = PluginConfig(schema=schema, values={"mode": "fast"})
        errors = config.validate()
        assert errors == []

    def test_default_fallback(self):
        schema = {
            "timeout": {"type": "int", "default": 30},
        }
        config = PluginConfig(schema=schema, values={})
        assert config.get("timeout") == 30

    def test_get_with_default(self):
        config = PluginConfig(schema={}, values={"name": "test"})
        assert config.get("name") == "test"
        assert config.get("missing", "default") == "default"

    def test_env_var_override(self):
        schema = {
            "api_key": {"type": "string", "env_var": "TEST_API_KEY"},
        }
        with patch.dict(os.environ, {"TEST_API_KEY": "env-value"}):
            config = PluginConfig(schema=schema, values={})
            assert config.get("api_key") == "env-value"

    def test_env_var_int_conversion(self):
        schema = {
            "timeout": {"type": "int", "env_var": "TEST_TIMEOUT", "default": 30},
        }
        with patch.dict(os.environ, {"TEST_TIMEOUT": "120"}):
            config = PluginConfig(schema=schema, values={})
            assert config.get("timeout") == 120

    def test_env_var_bool_conversion(self):
        schema = {
            "enabled": {"type": "bool", "env_var": "TEST_ENABLED", "default": False},
        }
        with patch.dict(os.environ, {"TEST_ENABLED": "true"}):
            config = PluginConfig(schema=schema, values={})
            assert config.get("enabled") is True

    def test_no_env_var_set_uses_default(self):
        schema = {
            "api_key": {"type": "string", "env_var": "NOT_SET_VAR", "default": "fallback"},
        }
        # Ensure env var is not set
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NOT_SET_VAR", None)
            config = PluginConfig(schema=schema, values={})
            assert config.get("api_key") == "fallback"

    def test_to_dict_and_from_dict(self):
        schema = {"timeout": {"type": "int", "default": 30}}
        values = {"timeout": 60}
        config = PluginConfig(schema=schema, values=values)

        d = config.to_dict()
        restored = PluginConfig.from_dict(d)
        assert restored.get("timeout") == 60


class TestPluginConfigManager:
    """Tests for PluginConfigManager."""

    def _setup_plugin(self, tmp_path, name, manifest=None, config=None):
        """Set up a plugin directory with manifest and optional config."""
        plugin_dir = tmp_path / name
        plugin_dir.mkdir()
        if manifest:
            (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
        if config:
            (plugin_dir / "config.json").write_text(json.dumps(config))
        return plugin_dir

    def test_has_config_true(self, tmp_path):
        self._setup_plugin(
            tmp_path, "test-plugin",
            manifest={"name": "test-plugin", "version": "1.0.0"},
            config={"timeout": 60},
        )
        mgr = PluginConfigManager(plugins_dir=tmp_path)
        assert mgr.has_config("test-plugin") is True

    def test_has_config_false(self, tmp_path):
        self._setup_plugin(
            tmp_path, "test-plugin",
            manifest={"name": "test-plugin", "version": "1.0.0"},
        )
        mgr = PluginConfigManager(plugins_dir=tmp_path)
        assert mgr.has_config("test-plugin") is False

    def test_load_config(self, tmp_path):
        self._setup_plugin(
            tmp_path, "test-plugin",
            manifest={"name": "test-plugin", "version": "1.0.0"},
            config={"timeout": 60, "retries": 3},
        )
        mgr = PluginConfigManager(plugins_dir=tmp_path)
        config = mgr.load_config("test-plugin")
        assert config["timeout"] == 60
        assert config["retries"] == 3

    def test_load_config_not_found(self, tmp_path):
        mgr = PluginConfigManager(plugins_dir=tmp_path)
        assert mgr.load_config("nonexistent") == {}

    def test_save_config(self, tmp_path):
        self._setup_plugin(
            tmp_path, "test-plugin",
            manifest={
                "name": "test-plugin", "version": "1.0.0",
                "config": {
                    "schema": {
                        "timeout": {"type": "int", "default": 30}
                    }
                }
            },
        )
        mgr = PluginConfigManager(plugins_dir=tmp_path)
        result = mgr.save_config("test-plugin", {"timeout": 120})
        assert result is True
        assert mgr.has_config("test-plugin") is True
        assert mgr.load_config("test-plugin")["timeout"] == 120

    def test_delete_config(self, tmp_path):
        self._setup_plugin(
            tmp_path, "test-plugin",
            manifest={"name": "test-plugin", "version": "1.0.0"},
            config={"timeout": 60},
        )
        mgr = PluginConfigManager(plugins_dir=tmp_path)
        assert mgr.delete_config("test-plugin") is True
        assert mgr.has_config("test-plugin") is False

    def test_delete_config_not_found(self, tmp_path):
        mgr = PluginConfigManager(plugins_dir=tmp_path)
        assert mgr.delete_config("nonexistent") is False

    def test_get_schema(self, tmp_path):
        manifest = {
            "name": "test-plugin", "version": "1.0.0",
            "config": {
                "schema": {
                    "api_key": {"type": "string", "required": True},
                    "timeout": {"type": "int", "default": 30},
                }
            }
        }
        self._setup_plugin(tmp_path, "test-plugin", manifest=manifest)
        mgr = PluginConfigManager(plugins_dir=tmp_path)
        schema = mgr.get_schema("test-plugin")
        assert "api_key" in schema
        assert "timeout" in schema

    def test_get_schema_no_schema(self, tmp_path):
        manifest = {"name": "test-plugin", "version": "1.0.0"}
        self._setup_plugin(tmp_path, "test-plugin", manifest=manifest)
        mgr = PluginConfigManager(plugins_dir=tmp_path)
        assert mgr.get_schema("test-plugin") == {}

    def test_get_defaults(self, tmp_path):
        manifest = {
            "name": "test-plugin", "version": "1.0.0",
            "config": {
                "schema": {
                    "timeout": {"type": "int", "default": 30},
                    "name": {"type": "string", "default": "test"},
                    "required_field": {"type": "string", "required": True},
                }
            }
        }
        self._setup_plugin(tmp_path, "test-plugin", manifest=manifest)
        mgr = PluginConfigManager(plugins_dir=tmp_path)
        defaults = mgr.get_defaults("test-plugin")
        assert defaults["timeout"] == 30
        assert defaults["name"] == "test"
        assert "required_field" not in defaults

    def test_validate_config_valid(self, tmp_path):
        manifest = {
            "name": "test-plugin", "version": "1.0.0",
            "config": {
                "schema": {
                    "timeout": {"type": "int", "min": 1, "max": 300},
                }
            }
        }
        self._setup_plugin(tmp_path, "test-plugin", manifest=manifest)
        mgr = PluginConfigManager(plugins_dir=tmp_path)
        errors = mgr.validate_config("test-plugin", {"timeout": 60})
        assert errors == []

    def test_validate_config_invalid(self, tmp_path):
        manifest = {
            "name": "test-plugin", "version": "1.0.0",
            "config": {
                "schema": {
                    "timeout": {"type": "int", "min": 1, "max": 300},
                }
            }
        }
        self._setup_plugin(tmp_path, "test-plugin", manifest=manifest)
        mgr = PluginConfigManager(plugins_dir=tmp_path)
        errors = mgr.validate_config("test-plugin", {"timeout": 999})
        assert len(errors) > 0

    def test_validate_config_no_schema(self, tmp_path):
        manifest = {"name": "test-plugin", "version": "1.0.0"}
        self._setup_plugin(tmp_path, "test-plugin", manifest=manifest)
        mgr = PluginConfigManager(plugins_dir=tmp_path)
        errors = mgr.validate_config("test-plugin", {"anything": "valid"})
        assert errors == []

    def test_get_full_config_merge(self, tmp_path):
        """Test that full config merges defaults + user config."""
        manifest = {
            "name": "test-plugin", "version": "1.0.0",
            "config": {
                "schema": {
                    "timeout": {"type": "int", "default": 30},
                    "name": {"type": "string", "default": "default-name"},
                    "retries": {"type": "int", "default": 3},
                }
            }
        }
        # User config overrides "timeout" only
        self._setup_plugin(
            tmp_path, "test-plugin",
            manifest=manifest,
            config={"timeout": 60},
        )
        mgr = PluginConfigManager(plugins_dir=tmp_path)
        full = mgr.get_full_config("test-plugin")
        assert full["timeout"] == 60  # user override
        assert full["name"] == "default-name"  # schema default
        assert full["retries"] == 3  # schema default

    def test_get_full_config_global_override(self, tmp_path):
        """Test that global config overrides defaults but not user config."""
        manifest = {
            "name": "test-plugin", "version": "1.0.0",
            "config": {
                "schema": {
                    "timeout": {"type": "int", "default": 30},
                    "name": {"type": "string", "default": "default"},
                }
            }
        }
        self._setup_plugin(
            tmp_path, "test-plugin",
            manifest=manifest,
            config={"timeout": 60},  # user override (highest priority)
        )

        # Set up global config
        global_config_path = tmp_path / "global_config.json"
        global_config_path.write_text(json.dumps({
            "plugins": {
                "test-plugin": {"timeout": 45, "name": "global-name"}
            }
        }))

        mgr = PluginConfigManager(
            plugins_dir=tmp_path,
            global_config_path=global_config_path,
        )
        full = mgr.get_full_config("test-plugin")
        assert full["timeout"] == 60  # user wins over global
        assert full["name"] == "global-name"  # global wins over default

    def test_set_global_plugin_config(self, tmp_path):
        global_config_path = tmp_path / "global_config.json"
        mgr = PluginConfigManager(
            plugins_dir=tmp_path,
            global_config_path=global_config_path,
        )
        result = mgr.set_global_plugin_config("my-plugin", {"timeout": 90})
        assert result is True

        # Verify it was saved
        with open(global_config_path) as f:
            data = json.load(f)
        assert data["plugins"]["my-plugin"]["timeout"] == 90
