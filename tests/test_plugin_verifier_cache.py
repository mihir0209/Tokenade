from tokenade.core.integration.plugin_verifier import PluginVerifier


def test_checksum_registration_ignores_generated_bytecode(tmp_path):
    plugin = tmp_path / "demo"
    cache = plugin / "__pycache__"
    cache.mkdir(parents=True)
    (plugin / "plugin.py").write_text("value = 1")
    (cache / "plugin.pyc").write_bytes(b"generated")

    verifier = PluginVerifier(plugins_dir=tmp_path)
    checksums = verifier.compute_plugin_checksums("demo")

    assert list(checksums) == ["plugin.py"]
