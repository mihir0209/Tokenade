"""Tests for gateway isolated runtime contexts."""

import json
import time
from pathlib import Path

from tokenade.core.gateway.runtime import BrowserManagerContextFactory, GatewayRuntime
from tokenade.core.gateway.session_store import SessionRecord, SessionStore


class FakePage:
    def __init__(self, context):
        self.context = context
        self.goto_calls = []
        self.evaluate_calls = []
        self.closed = False

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append({"url": url, "wait_until": wait_until, "timeout": timeout})
        if url == "https://abort.example":
            raise RuntimeError("navigation aborted")

    def evaluate(self, script, data):
        self.evaluate_calls.append({"script": script, "data": data})
        self.context.local_storage_updates.append(data)

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, session_id):
        self.session_id = session_id
        self.cookies = []
        self.pages = []
        self.local_storage_updates = []
        self.closed = False

    def add_cookies(self, cookies):
        self.cookies.extend(cookies)

    def new_page(self):
        page = FakePage(self)
        self.pages.append(page)
        return page

    def close(self):
        self.closed = True


class FakeContextFactory:
    def __init__(self):
        self.contexts = {}
        self.closed = False

    def create_context(self, session):
        context = FakeContext(session.id)
        self.contexts[session.id] = context
        return context

    def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self):
        self.contexts = []

    def new_context(self, viewport=None):
        context = FakeContext(f"context-{len(self.contexts) + 1}")
        context.viewport = viewport
        self.contexts.append(context)
        return context

    def close(self):
        pass


class FakeBrowserManager:
    def __init__(self):
        self.config = type("Config", (), {"viewport": {"width": 1024, "height": 768}})()
        self._browser = FakeBrowser()
        self._context = FakeContext("startup")
        self._page = object()
        self.launch_calls = 0

    def launch(self):
        self.launch_calls += 1
        return self._page

    def close(self):
        if self._browser:
            self._browser.close()


def _write_session(tmp_path, name, site_name, cookie_value, storage_value=None):
    storage = {}
    if storage_value is not None:
        storage = {"local": {f"https://{site_name}.com": {"token": storage_value}}}
    path = Path(tmp_path) / name
    path.write_text(json.dumps({
        "version": "1.0",
        "created_at": "2026-07-18T00:00:00",
        "site_name": site_name,
        "auth_status": "logged_in",
        "cookies": [{
            "name": "sid",
            "value": cookie_value,
            "domain": f".{site_name}.com",
            "path": "/",
            "expires": time.time() + 172800,
        }],
        "metadata": {"session_id": site_name},
        "storage": storage,
    }))
    return path


def _records(tmp_path):
    _write_session(tmp_path, "github.tokenade", "github", "github-cookie", "github-storage")
    _write_session(tmp_path, "discord.tokenade", "discord", "discord-cookie", "discord-storage")
    return SessionStore().load_directory(tmp_path)


def _cookie_only_records(tmp_path):
    _write_session(tmp_path, "github.tokenade", "github", "github-cookie")
    _write_session(tmp_path, "discord.tokenade", "discord", "discord-cookie")
    return SessionStore().load_directory(tmp_path)


def test_prewarm_creates_isolated_contexts_and_injects_session_state(tmp_path):
    records = _records(tmp_path)
    factory = FakeContextFactory()
    runtime = GatewayRuntime(factory)

    result = runtime.prewarm(records)

    assert result["success"] is True
    assert result["context_count"] == 2
    github = factory.contexts["github"]
    discord = factory.contexts["discord"]
    assert github is not discord
    assert github.cookies[0]["value"] == "github-cookie"
    assert discord.cookies[0]["value"] == "discord-cookie"
    assert github.local_storage_updates == [{"token": "github-storage"}]
    assert discord.local_storage_updates == [{"token": "discord-storage"}]


def test_default_context_factory_closes_startup_context_and_does_not_open_pages(monkeypatch, tmp_path):
    records = _cookie_only_records(tmp_path)
    manager = FakeBrowserManager()

    def create_browser_manager(**kwargs):
        return manager

    monkeypatch.setattr(
        "tokenade.core.browser.manager.BrowserFactory.create",
        create_browser_manager,
    )
    runtime = GatewayRuntime(BrowserManagerContextFactory(headless=False))

    result = runtime.prewarm(records)

    assert result["success"] is True
    assert manager.launch_calls == 1
    assert manager._context is None
    assert manager._page is None
    assert manager._browser.contexts[0].closed is False
    assert manager._browser.contexts[1].closed is False
    assert manager._browser.contexts[0].pages == []
    assert manager._browser.contexts[1].pages == []


def test_active_context_changes_on_rotation_without_mutating_old_context(tmp_path):
    records = {record.site_name: record for record in _records(tmp_path)}
    factory = FakeContextFactory()
    runtime = GatewayRuntime(factory)

    first = runtime.activate(records["discord"])
    old_context = first.context
    runtime.new_page()
    second = runtime.activate(records["github"])
    runtime.new_page()

    assert runtime.active_context_id == "github"
    assert second.context is factory.contexts["github"]
    assert old_context is factory.contexts["discord"]
    assert old_context.closed is False
    assert len(old_context.pages) == 2
    assert len(factory.contexts["github"].pages) == 2


def test_new_page_navigates_optional_url_in_active_context(tmp_path):
    records = {record.site_name: record for record in _records(tmp_path)}
    factory = FakeContextFactory()
    runtime = GatewayRuntime(factory)
    runtime.activate(records["github"])

    result = runtime.new_page(url="https://github.com")

    page = factory.contexts["github"].pages[-1]
    assert result["success"] is True
    assert page.goto_calls == [{"url": "https://github.com", "wait_until": "domcontentloaded", "timeout": 30000}]


def test_new_page_navigation_error_is_non_fatal(tmp_path):
    records = {record.site_name: record for record in _records(tmp_path)}
    runtime = GatewayRuntime(FakeContextFactory())
    runtime.activate(records["github"])

    result = runtime.new_page(url="https://abort.example")

    assert result["success"] is True
    assert "navigation aborted" in result["navigation_error"]


def test_drain_closes_inactive_contexts_only(tmp_path):
    records = _records(tmp_path)
    factory = FakeContextFactory()
    runtime = GatewayRuntime(factory)
    runtime.prewarm(records)
    active = next(record for record in records if record.site_name == "github")
    runtime.activate(active)

    result = runtime.drain_inactive()

    assert result["success"] is True
    assert factory.contexts["github"].closed is False
    assert factory.contexts["discord"].closed is True


def test_switch_with_prewarmed_contexts_is_under_hundreds_of_ms(tmp_path):
    records = _records(tmp_path)
    factory = FakeContextFactory()
    runtime = GatewayRuntime(factory)
    runtime.prewarm(records)

    started = time.perf_counter()
    for _ in range(1000):
        for record in records:
            runtime.activate(record)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.2


def test_contexts_are_sanitized(tmp_path):
    records = _records(tmp_path)
    runtime = GatewayRuntime(FakeContextFactory())
    runtime.prewarm(records)

    serialized = json.dumps(runtime.contexts())

    assert "github-cookie" not in serialized
    assert "discord-cookie" not in serialized
    assert "github-storage" not in serialized
    assert "discord-storage" not in serialized
