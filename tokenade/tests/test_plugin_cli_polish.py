"""Tests for plugin CLI polish: annotated deps tree, JSON mode, info surfacing.

Covers ``tokenade plugin info`` (API version, runnable methods, annotated
dependencies) and ``tokenade plugin deps`` (annotated tree + ``--json``).
"""

import json
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _fake_loaded(state="active"):
    loaded = MagicMock()
    loaded.state.value = state
    loaded.error = None
    loaded.config = {}
    return loaded


def _loader_with(manifests):
    loader = MagicMock()
    loader.discover.return_value = manifests
    loader.get_plugin.side_effect = lambda n: _fake_loaded()
    return loader


def _run_cmd_plugin(args, manifests, registry_details=None):
    with (
        patch("tokenade.core.integration.plugin_loader.PluginLoader") as MockLoader,
        patch("tokenade.core.integration.plugin_registry.PluginRegistry") as MockReg,
        patch("tokenade.core.integration.plugin_verifier.PluginVerifier") as MockVer,
    ):
        loader = _loader_with(manifests)
        MockLoader.return_value = loader
        reg = MagicMock()
        reg.get_plugin_details.return_value = registry_details
        MockReg.return_value = reg
        verifier = MagicMock()
        verifier._local_checksums = {}
        verifier.verify.return_value = SimpleNamespace(verified=True)
        MockVer.return_value = verifier

        from tokenade.cli import cmd_plugin

        out = StringIO()
        with patch("sys.stdout", out):
            cmd_plugin(args)
        return out.getvalue()


CHALLENGE_MANIFESTS = [
    {
        "name": "nowsecure-handler",
        "version": "1.0.0",
        "type": "handler",
        "author": "Tokenade Team",
        "description": "Site handler for nowsecure.nl",
        "dependencies": ["challenge-detectors", "twocaptcha-solver"],
        "api_version": "1.3.0",
        "entry_class": "NowSecureHandlerPlugin",
        "category": "site-handlers",
        "icon": "\U0001f6e1\ufe0f",
        "tags": ["site-handler", "challenge"],
        "run": {
            "enabled": True,
            "default_method": "process",
            "methods": {"process": {"arguments": {"target_url": {"type": "string"}}}},
        },
    },
    {"name": "challenge-detectors", "version": "1.0.0", "type": "challenge_detector"},
    {"name": "twocaptcha-solver", "version": "1.0.0", "type": "challenge_solver"},
]


def test_plugin_info_surfaces_challenge_fields():
    args = SimpleNamespace(plugin_command="info", name="nowsecure-handler", json=False)
    out = _run_cmd_plugin(args, CHALLENGE_MANIFESTS)

    assert "Plugin: nowsecure-handler" in out
    assert "API version: 1.3.0" in out
    assert "Entry class: NowSecureHandlerPlugin" in out
    assert "Category: site-handlers" in out
    assert "Icon: \U0001f6e1\ufe0f" in out
    assert "Tags: site-handler, challenge" in out
    assert "Runnable methods: process (default)" in out
    assert "Run: tokenade run nowsecure-handler --input request.json" in out
    assert (
        "Dependencies: challenge-detectors [OK], twocaptcha-solver [OK]" in out
    )


def test_plugin_info_missing_dependency_annotated():
    manifests = [
        {"name": "orphan", "version": "1.0.0", "type": "handler", "dependencies": ["ghost-dep"]}
    ]
    args = SimpleNamespace(plugin_command="info", name="orphan", json=False)
    out = _run_cmd_plugin(args, manifests)

    assert "Dependencies: ghost-dep [X] missing" in out


def test_plugin_info_legacy_api_version_and_no_run():
    manifests = [{"name": "legacy", "version": "1.0.0", "type": "handler"}]
    args = SimpleNamespace(plugin_command="info", name="legacy", json=False)
    out = _run_cmd_plugin(args, manifests)

    assert "API version: legacy (no api_version declared)" in out
    assert "Runnable methods" not in out


def test_plugin_info_not_installed_surfaces_registry_run_methods():
    registry_details = {
        "name": "remote-plugin",
        "version": "2.0.0",
        "type": "challenge_solver",
        "api_version": "1.3.0",
        "category": "solvers",
        "dependencies": ["challenge-detectors"],
        "run": {
            "enabled": True,
            "default_method": "solve",
            "methods": {"solve": {"arguments": {}}},
        },
    }
    args = SimpleNamespace(plugin_command="info", name="remote-plugin", json=False)
    out = _run_cmd_plugin(args, [], registry_details=registry_details)

    assert "Plugin: remote-plugin (not installed)" in out
    assert "API version: 1.3.0" in out
    assert "Category: solvers" in out
    assert "Runnable methods: solve (default)" in out


def test_plugin_deps_annotated_tree_with_transitives():
    manifests = [
        {"name": "app", "version": "1.0.0", "type": "handler", "dependencies": ["mid"]},
        {"name": "mid", "version": "1.0.0", "type": "challenge_solver", "dependencies": ["base"]},
        {"name": "base", "version": "1.0.0", "type": "challenge_detector"},
    ]
    args = SimpleNamespace(plugin_command="deps", name="app", json=False)
    out = _run_cmd_plugin(args, manifests)

    assert "[PKG] Dependency tree for app" in out
    assert "mid v1.0.0 [OK]" in out
    assert "  base v1.0.0 [OK]" in out


def test_plugin_deps_annotated_missing_dependency():
    manifests = [
        {"name": "app", "version": "1.0.0", "type": "handler", "dependencies": ["ghost-dep"]}
    ]
    args = SimpleNamespace(plugin_command="deps", name="app", json=False)
    out = _run_cmd_plugin(args, manifests)

    assert "ghost-dep v? [X] missing" in out


def test_plugin_deps_json_cycle_safe_diamond():
    manifests = [
        {"name": "a", "dependencies": ["b", "c"]},
        {"name": "b", "dependencies": ["d"]},
        {"name": "c", "dependencies": ["d"]},
        {"name": "d"},
    ]
    args = SimpleNamespace(plugin_command="deps", name="a", json=True)
    out = _run_cmd_plugin(args, manifests)

    tree = json.loads(out)
    assert tree["name"] == "a"
    assert tree["installed"] is True
    names = json.dumps(tree)
    assert "cycle" in names
    assert '"cycle": true' in names
    # d is fully expanded once, then referenced as a cycle
    assert names.count('"name": "d"') == 2


def test_plugin_deps_not_found():
    manifests = [{"name": "app", "version": "1.0.0", "dependencies": []}]
    args = SimpleNamespace(plugin_command="deps", name="nope", json=False)
    out = _run_cmd_plugin(args, manifests)

    assert "[ERROR] Plugin not found: nope" in out


def test_plugin_info_json_installed():
    args = SimpleNamespace(plugin_command="info", name="nowsecure-handler", json=True)
    out = _run_cmd_plugin(args, CHALLENGE_MANIFESTS)

    payload = json.loads(out)
    assert payload["name"] == "nowsecure-handler"
    assert payload["installed"] is True
    assert payload["status"] == "enabled"
    assert payload["api_version"] == "1.3.0"
    assert payload["legacy_api"] is False
    assert payload["entry_class"] == "NowSecureHandlerPlugin"
    assert payload["category"] == "site-handlers"
    assert payload["tags"] == ["site-handler", "challenge"]
    assert payload["dependencies"] == [
        {"name": "challenge-detectors", "installed": True},
        {"name": "twocaptcha-solver", "installed": True},
    ]
    assert payload["run"] == {
        "enabled": True,
        "default_method": "process",
        "methods": ["process"],
    }
    assert payload["run_invocation"] == (
        "tokenade run nowsecure-handler --input request.json"
    )
    assert payload["runtime_dependencies"]["ready"] is True
    assert payload["integrity"] == "unregistered"


def test_plugin_info_json_missing_dependency_and_tampered():
    manifests = [
        {"name": "orphan", "version": "1.0.0", "type": "handler", "dependencies": ["ghost-dep"]}
    ]
    args = SimpleNamespace(plugin_command="info", name="orphan", json=True)
    out = _run_cmd_plugin(args, manifests)

    payload = json.loads(out)
    assert payload["dependencies"] == [{"name": "ghost-dep", "installed": False}]
    assert payload["legacy_api"] is True
    assert "run" not in payload
    assert "run_invocation" not in payload


def test_plugin_info_json_not_installed():
    registry_details = {
        "name": "remote-plugin",
        "version": "2.0.0",
        "type": "challenge_solver",
        "api_version": "1.3.0",
        "category": "solvers",
        "dependencies": ["challenge-detectors"],
        "run": {
            "enabled": True,
            "default_method": "solve",
            "methods": {"solve": {"arguments": {}}},
        },
    }
    args = SimpleNamespace(plugin_command="info", name="remote-plugin", json=True)
    out = _run_cmd_plugin(args, [], registry_details=registry_details)

    payload = json.loads(out)
    assert payload["installed"] is False
    assert payload["available"] is True
    assert payload["dependencies"] == ["challenge-detectors"]
    assert payload["run"] == {
        "enabled": True,
        "default_method": "solve",
        "methods": ["solve"],
    }
    assert payload["install"] == "tokenade plugin install remote-plugin"


def test_plugin_info_json_unknown():
    args = SimpleNamespace(plugin_command="info", name="nope", json=True)
    out = _run_cmd_plugin(args, [])

    payload = json.loads(out)
    assert payload == {"name": "nope", "installed": False, "available": False}


def test_plugin_check_deps_json_named_ok():
    manifests = [
        {"name": "app", "version": "1.0.0", "type": "handler", "dependencies": ["mid"]},
        {"name": "mid", "version": "1.0.0", "type": "challenge_solver"},
    ]
    args = SimpleNamespace(plugin_command="check-deps", name="app", json=True)
    out = _run_cmd_plugin(args, manifests)

    payload = json.loads(out)
    assert payload == {"plugin": "app", "found": True, "missing": [], "runtime_issues": []}


def test_plugin_check_deps_json_named_missing():
    manifests = [
        {"name": "app", "version": "1.0.0", "type": "handler", "dependencies": ["ghost-dep"]}
    ]
    args = SimpleNamespace(plugin_command="check-deps", name="app", json=True)
    out = _run_cmd_plugin(args, manifests)

    payload = json.loads(out)
    assert payload["missing"] == ["ghost-dep"]
    assert payload["found"] is True


def test_plugin_check_deps_json_all():
    manifests = [
        {"name": "app", "version": "1.0.0", "type": "handler", "dependencies": ["mid"]},
        {"name": "mid", "version": "1.0.0", "type": "challenge_solver"},
        {"name": "orphan", "version": "1.0.0", "type": "handler", "dependencies": ["ghost-dep"]},
    ]
    args = SimpleNamespace(plugin_command="check-deps", name=None, json=True)
    out = _run_cmd_plugin(args, manifests)

    payload = json.loads(out)
    assert payload["missing"] == ["ghost-dep"]
    assert payload["circular"] == []
    assert payload["depth"] == []
    assert "runtime_issues" in payload


def test_plugin_check_deps_json_unknown():
    manifests = [{"name": "app", "version": "1.0.0", "dependencies": []}]
    args = SimpleNamespace(plugin_command="check-deps", name="nope", json=True)
    out = _run_cmd_plugin(args, manifests)

    payload = json.loads(out)
    assert payload == {"plugin": "nope", "found": False}
