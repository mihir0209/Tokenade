"""Tests for egress_provider + fingerprint_oracle plugin seams."""
import json

from tokenade.core.integration.plugin_loader import PluginLoader
from tokenade.plugin.api import PluginResult
from tokenade.plugin.base import (
    PLUGIN_TYPE_BASE_CLASSES,
    PLUGIN_TYPE_REQUIRED_METHODS,
    EgressProviderPlugin,
    FingerprintOraclePlugin,
)


def _write_plugin(root, name, plugin_type, entry_class, body):
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
                "dependencies": [],
            }
        )
    )
    (plugin_dir / "plugin.py").write_text(body)


EGRESS_BODY = (
    "from tokenade.plugin.base import EgressProviderPlugin\n"
    "from tokenade.plugin.api import PluginResult\n"
    "class WirePlugin(EgressProviderPlugin):\n"
    "    name = 'wire'\n"
    "    version = '1.0'\n"
    "    description = 'd'\n"
    "    transport = 'wireguard'\n"
    "    def open_circuit(self, descriptor, auth):\n"
    "        return PluginResult(success=True, data={'local_proxy': {'server': 'http://127.0.0.1:1'}})\n"
)

ORACLE_BODY = (
    "from tokenade.plugin.base import FingerprintOraclePlugin\n"
    "from tokenade.plugin.api import PluginResult\n"
    "class SnapPlugin(FingerprintOraclePlugin):\n"
    "    name = 'snap'\n"
    "    version = '1.0'\n"
    "    description = 'd'\n"
    "    def answer(self, query):\n"
    "        return PluginResult(success=True, data={'value': 'Win32'})\n"
)


def test_registry_entries():
    assert PLUGIN_TYPE_BASE_CLASSES["egress_provider"] == (EgressProviderPlugin,)
    assert PLUGIN_TYPE_BASE_CLASSES["fingerprint_oracle"] == (FingerprintOraclePlugin,)
    assert PLUGIN_TYPE_REQUIRED_METHODS["egress_provider"] == ["open_circuit"]
    assert PLUGIN_TYPE_REQUIRED_METHODS["fingerprint_oracle"] == ["answer"]


def test_loader_registers_new_types(tmp_path):
    _write_plugin(tmp_path, "wire", "egress_provider", "WirePlugin", EGRESS_BODY)
    _write_plugin(tmp_path, "snap", "fingerprint_oracle", "SnapPlugin", ORACLE_BODY)
    loader = PluginLoader(plugins_dir=tmp_path)
    assert loader.load_by_name("wire") is not None
    assert loader.load_by_name("snap") is not None
    provider = loader.get_egress_provider("wire")
    assert provider is not None
    result = provider.open_circuit({}, {})
    assert isinstance(result, PluginResult) and result.success
    oracle = loader.get_fingerprint_oracle("snap")
    assert oracle is not None
    assert oracle.answer({"method": "navigator.platform"}).data["value"] == "Win32"
    assert "wire" in loader.list_egress_providers()
    assert "snap" in loader.list_fingerprint_oracles()


def test_loader_unload_new_types(tmp_path):
    _write_plugin(tmp_path, "wire", "egress_provider", "WirePlugin", EGRESS_BODY)
    loader = PluginLoader(plugins_dir=tmp_path)
    loader.load_by_name("wire")
    assert loader.unload("wire") is True
    assert loader.get_egress_provider("wire") is None
