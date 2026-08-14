"""Shared pytest fixtures for the tests/ suite."""

from unittest.mock import MagicMock

import pytest

from tokenade.core.integration.plugin_loader import PluginState


@pytest.fixture
def inactive_plugin_loader():
    """A (loaded, loader) pair where the plugin is loaded but not ACTIVE.

    Used by CR-05 regression tests for direct consumers that must reject
    non-active plugins (artifacts/manager, browser_ops).
    """
    fake_loaded = MagicMock()
    fake_loaded.is_active = False
    fake_loaded.state = PluginState.LOADED

    fake_loader = MagicMock()
    fake_loader.get_manifest.return_value = {
        "version": "1.0.0",
        "dependencies": [],
    }
    fake_loader.is_disabled.return_value = False
    fake_loader.load_by_name.return_value = fake_loaded

    return fake_loaded, fake_loader
