"""Shared test fixtures for Tokenade."""
import json
import sys
import tempfile
import types
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock

import pytest

import time as _real_time


class _NoSleepTimeModule(types.ModuleType):
    """Wrapper around the real time module with a no-op sleep."""

    def __init__(self):
        super().__init__("time")
        self._real = _real_time

    def __getattr__(self, name):
        if name == "sleep":
            return lambda *a, **kw: None
        return getattr(self._real, name)


_NO_SLEEP_TIME = _NoSleepTimeModule()


@pytest.fixture(autouse=True)
def _ensure_handlers_registered():
    """Ensure legacy handlers are registered in HandlerRegistry.

    Some tests clear HandlerRegistry._handlers, so we re-register before each test.
    Concrete handlers were removed in core cleanup — base classes remain.
    """
    from tokenade.handlers.base import HandlerRegistry

    # Re-register any handlers that other tests may have cleared
    # (Concrete handlers removed; this fixture ensures registry is non-empty for
    # tests that depend on it)
    pass


_MODULES_WITH_SLEEP = [
    "tokenade.core.importer.validator",
    "tokenade.core.importer.session_loader",
    "tokenade.core.browser.stealth.cloak",
    "tokenade.core.browser.xvfb",
    "tokenade.core.browser.stealth.launcher",
    "tokenade.core.daemon.session_daemon",
    "tokenade.core.monitoring.session_monitor",
    "tokenade.core.refresh.batch_refresh",
    "tokenade.core.proxy.cdp_proxy",
    "tokenade.core.proxy.server",
    "tokenade.core.proxy.extension_bridge",
    "tokenade.core.proxy.multi_site_proxy",
    "tokenade.core.runtime.engine",
]


@pytest.fixture(autouse=True)
def _fast_sleep():
    """Replace the time module reference in slow production modules so sleep() is a no-op.

    This only affects the time reference *inside* each module, not the global
    time module, so tests that call time.sleep() directly still actually sleep.
    """
    saved = {}
    for mod_name in _MODULES_WITH_SLEEP:
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, "time"):
            saved[mod_name] = mod.time
            mod.time = _NO_SLEEP_TIME

    yield

    for mod_name, original in saved.items():
        mod = sys.modules.get(mod_name)
        if mod is not None:
            mod.time = original


@pytest.fixture
def sample_session() -> Dict:
    """Sample .tokenade session data."""
    return {
        "version": "2.0",
        "created_at": "2026-01-01T00:00:00Z",
        "source_device": {
            "browser": "firefox",
            "profile": "default",
            "platform": "Linux",
            "hostname": "test-pc",
        },
        "site_name": "example",
        "auth_status": "logged_in",
        "cookies": [
            {
                "name": "session_id",
                "value": "abc123",
                "domain": ".example.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "Lax",
                "expires": 1800000000,
            },
            {
                "name": "csrf_token",
                "value": "xyz789",
                "domain": ".example.com",
                "path": "/",
                "secure": True,
                "httpOnly": False,
                "sameSite": "Strict",
                "expires": 1800000000,
            },
        ],
        "fingerprint": {
            "user_agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
            "platform": "Linux",
            "language": "en-US",
        },
        "tls_profile": {
            "browser": "chrome",
            "version": "120",
            "impersonate": "chrome120",
            "http_version": "2",
        },
        "metadata": {
            "cookie_count": 2,
            "critical_cookie_count": 1,
        },
    }


@pytest.fixture
def sample_cookies() -> List[Dict]:
    """Sample cookie list."""
    return [
        {
            "name": "sid",
            "value": "abc123",
            "domain": ".google.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "Lax",
            "expires": 1800000000,
        },
        {
            "name": "nid",
            "value": "xyz789",
            "domain": ".google.com",
            "path": "/",
            "secure": True,
            "httpOnly": False,
            "sameSite": "None",
            "expires": 1800000000,
        },
    ]


@pytest.fixture
def tmp_session_file(tmp_path, sample_session) -> Path:
    """Create a temporary .tokenade session file."""
    session_file = tmp_path / "test_session.tokenade"
    with open(session_file, "w") as f:
        json.dump(sample_session, f, indent=2)
    return session_file


@pytest.fixture
def mock_browser():
    """Mock Playwright browser for testing."""
    browser = MagicMock()
    context = MagicMock()
    page = MagicMock()
    browser.new_context.return_value = context
    context.new_page.return_value = page
    page.goto = MagicMock()
    page.wait_for_load_state = MagicMock()
    return browser


@pytest.fixture
def mock_subprocess(monkeypatch):
    """Mock subprocess calls for docker/kubectl."""
    mock_run = MagicMock()
    mock_run.returncode = 0
    mock_run.stdout = ""
    mock_run.stderr = ""

    def fake_run(args, **kwargs):
        return mock_run

    monkeypatch.setattr("subprocess.run", fake_run)
    return mock_run
