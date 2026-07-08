"""P2 — contract tests for official plugins when the plugins repo is present.

Skips cleanly if TOKENADE_PLUGINS_DIR is unset and the sibling path is absent.
"""

import os
from pathlib import Path

import pytest

from tokenade.core.integration.plugin_testing import PluginTestRunner


def _plugins_dir() -> Path | None:
    env = os.environ.get("TOKENADE_PLUGINS_DIR")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    # Common local layout: ~/Projects/tokenade + ~/Projects/tokenade-plugins
    sibling = Path.home() / "Projects" / "tokenade-plugins" / "plugins"
    if sibling.is_dir():
        return sibling
    return None


@pytest.fixture(scope="module")
def plugins_dir():
    d = _plugins_dir()
    if d is None:
        pytest.skip("Official plugins repo not available")
    return d


def test_all_official_plugins_pass_contracts(plugins_dir):
    runner = PluginTestRunner(plugins_dir=plugins_dir)
    suites = runner.test_all()
    assert suites, "No plugins discovered"
    failures = []
    for suite in suites:
        if not suite.passed:
            bad = [f"{r.test_name}: {r.message}" for r in suite.results if not r.passed]
            failures.append(f"{suite.plugin_name}: {'; '.join(bad)}")
    assert not failures, "Contract failures:\n" + "\n".join(failures)


def test_no_vanity_metrics_in_manifests(plugins_dir):
    for path in plugins_dir.glob("*/plugin.json"):
        import json
        meta = json.loads(path.read_text())
        for key in ("downloads", "rating"):
            assert key not in meta, f"{path.parent.name} has vanity field {key}"
