"""Tests for Phase 49.3-49.4 — Multi-Window Synchronizer + Competitor Import."""
import json
import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from tokenade.core.browser.synchronizer import (
    WindowSynchronizer,
    SyncAction,
    SyncResult,
    SyncSession,
)
from tokenade.core.importer.competitor_import import CompetitorImporter


# ─── WindowSynchronizer Tests ────────────────────────────────

class TestWindowSynchronizer:
    def test_parse_navigate(self):
        sync = WindowSynchronizer()
        actions = sync.parse_actions("navigate,https://example.com")
        assert len(actions) == 1
        assert actions[0].action_type == "navigate"
        assert actions[0].target == "https://example.com"

    def test_parse_click(self):
        sync = WindowSynchronizer()
        actions = sync.parse_actions("click,#submit-btn")
        assert len(actions) == 1
        assert actions[0].action_type == "click"
        assert actions[0].target == "#submit-btn"

    def test_parse_type(self):
        sync = WindowSynchronizer()
        actions = sync.parse_actions("type,#username=admin123")
        assert len(actions) == 1
        assert actions[0].action_type == "type"
        assert actions[0].target == "#username"
        assert actions[0].value == "admin123"

    def test_parse_wait(self):
        sync = WindowSynchronizer()
        actions = sync.parse_actions("wait,2")
        assert len(actions) == 1
        assert actions[0].action_type == "wait"
        assert actions[0].value == "2"

    def test_parse_multiple(self):
        sync = WindowSynchronizer()
        actions = sync.parse_actions(
            "navigate,https://example.com;wait,1;click,#btn"
        )
        assert len(actions) == 3
        assert actions[0].action_type == "navigate"
        assert actions[1].action_type == "wait"
        assert actions[2].action_type == "click"

    def test_parse_empty(self):
        sync = WindowSynchronizer()
        actions = sync.parse_actions("")
        assert len(actions) == 0

    def test_parse_complex(self):
        sync = WindowSynchronizer()
        actions = sync.parse_actions(
            "navigate,https://google.com;wait,2;type,#q=search term;click,input[name='btnK']"
        )
        assert len(actions) == 4
        assert actions[2].target == "#q"
        assert actions[2].value == "search term"

    def test_create_sync_session(self):
        sync = WindowSynchronizer()
        session = sync.create_sync_session(
            ["profile1", "profile2"],
            "navigate,https://example.com;wait,1"
        )
        assert len(session.profile_names) == 2
        assert len(session.actions) == 2
        assert session.results == []

    def test_sync_session_summary_no_results(self):
        session = SyncSession(
            profile_names=["p1"],
            actions=[SyncAction("navigate", "https://example.com")],
        )
        assert "0/0" in session.summary()

    def test_sync_session_summary_with_results(self):
        session = SyncSession(
            profile_names=["p1", "p2"],
            actions=[SyncAction("navigate", "https://example.com")],
            results=[
                SyncResult("p1", True, duration_ms=100),
                SyncResult("p2", False, error="timeout", duration_ms=200),
            ],
            started_at=1000,
            completed_at=1001,
        )
        assert session.success_count == 1
        assert session.failure_count == 1
        assert session.duration_ms == 1000.0

    def test_execute_sync_wait_sync(self):
        """Test sync action execution without async (unit test the session tracking)."""
        sync = WindowSynchronizer()
        session = SyncSession(
            profile_names=["p1", "p2"],
            actions=[
                SyncAction("navigate", "https://example.com"),
                SyncAction("wait", value="1"),
            ],
        )
        # Simulate results
        session.results.append(SyncResult("p1", True, duration_ms=50))
        session.results.append(SyncResult("p2", True, duration_ms=55))
        session.results.append(SyncResult("p1", True, duration_ms=10))
        session.results.append(SyncResult("p2", False, error="timeout", duration_ms=1000))
        session.started_at = 1000.0
        session.completed_at = 1001.0

        assert session.success_count == 3
        assert session.failure_count == 1
        assert session.duration_ms == 1000.0
        assert "3/4" in session.summary()

    def test_build_launch_args_headless(self):
        from tokenade.core.browser.profiles import BrowserProfile
        sync = WindowSynchronizer()
        profile = BrowserProfile(name="test", browser="chromium")
        args = sync._build_launch_args(profile, headless=True)
        assert "--headless=new" in args

    def test_build_launch_args_proxy(self):
        from tokenade.core.browser.profiles import BrowserProfile
        sync = WindowSynchronizer()
        profile = BrowserProfile(
            name="test",
            proxy={"url": "socks5://127.0.0.1:1080"},
        )
        args = sync._build_launch_args(profile, headless=False)
        assert any("--proxy-server=" in a for a in args)


# ─── CompetitorImporter Tests ────────────────────────────────

class TestCompetitorImporter:
    def test_import_adspower_single(self, tmp_path):
        data = {
            "name": "test-profile",
            "profile_id": "abc123",
            "browser_type": "chrome",
            "system": "Windows 10",
            "resolution": "1920x1080",
            "language": "en-US",
            "cpu": 8,
            "memory": 16,
            "webgl_vendor": "Google Inc. (NVIDIA)",
            "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060)",
            "proxy_config": {
                "proxy_type": "socks5",
                "proxy_host": "127.0.0.1",
                "proxy_port": 1080,
                "proxy_user": "user",
                "proxy_password": "pass",
            },
            "cookies": [{"name": "token", "value": "abc"}],
            "remark": "test profile",
            "group_name": "work",
        }
        f = tmp_path / "adspower.json"
        f.write_text(json.dumps(data))

        importer = CompetitorImporter()
        profiles = importer.import_file(str(f))
        assert len(profiles) == 1
        p = profiles[0]
        assert p["name"] == "test-profile"
        assert p["source"] == "adspower"
        assert p["browser"] == "chromium"
        assert p["os"] == "windows"
        assert p["fingerprint"]["navigator"]["hardwareConcurrency"] == 8
        assert p["proxy"]["type"] == "socks5"
        assert len(p["cookies"]) == 1

    def test_import_adspower_list(self, tmp_path):
        data = [
            {"name": "p1", "profile_id": "1", "browser_type": "chrome", "system": "Windows"},
            {"name": "p2", "profile_id": "2", "browser_type": "firefox", "system": "Mac OS X"},
        ]
        f = tmp_path / "adspower_list.json"
        f.write_text(json.dumps(data))

        importer = CompetitorImporter()
        profiles = importer.import_file(str(f))
        assert len(profiles) == 2
        assert profiles[0]["browser"] == "chromium"
        assert profiles[1]["browser"] == "firefox"
        assert profiles[1]["os"] == "macos"

    def test_import_multilogin(self, tmp_path):
        data = {
            "profiles": [
                {
                    "name": "ml-profile",
                    "browser_type": "mixin",
                    "os": "macOS",
                    "language": "en-US",
                    "navigator": {"hardwareConcurrency": 8, "deviceMemory": 16},
                    "screen": {"width": 2560, "height": 1440},
                    "webgl": {"vendor": "Apple", "renderer": "Apple GPU"},
                    "proxy": {"type": "http", "host": "proxy.example.com", "port": 8080},
                    "cookies": [],
                }
            ]
        }
        f = tmp_path / "multilogin.json"
        f.write_text(json.dumps(data))

        importer = CompetitorImporter()
        profiles = importer.import_file(str(f))
        assert len(profiles) == 1
        p = profiles[0]
        assert p["name"] == "ml-profile"
        assert p["source"] == "multilogin"
        assert p["browser"] == "chromium"
        assert p["os"] == "macos"
        assert p["fingerprint"]["screen"]["width"] == 2560

    def test_import_gologin(self, tmp_path):
        data = {
            "profiles": [
                {
                    "name": "gl-profile",
                    "os": "windows",
                    "navigator": {"platform": "Win32", "language": "de-DE"},
                    "screen": {"width": 1920, "height": 1080},
                    "webgl": {"vendor": "Google Inc.", "renderer": "ANGLE (Intel)"},
                    "proxy": {"type": "socks5", "host": "1.2.3.4", "port": 9050},
                }
            ]
        }
        f = tmp_path / "gologin.json"
        f.write_text(json.dumps(data))

        importer = CompetitorImporter()
        profiles = importer.import_file(str(f))
        assert len(profiles) == 1
        p = profiles[0]
        assert p["name"] == "gl-profile"
        assert p["source"] == "gologin"
        assert p["proxy"]["host"] == "1.2.3.4"

    def test_auto_detect_adspower(self, tmp_path):
        data = {"name": "p", "profile_id": "abc", "browser_type": "chrome"}
        f = tmp_path / "export.json"
        f.write_text(json.dumps(data))

        importer = CompetitorImporter()
        profiles = importer.import_file(str(f))
        assert profiles[0]["source"] == "adspower"

    def test_auto_detect_multilogin(self, tmp_path):
        data = {"profiles": [{"name": "p", "browser_type": "chrome"}]}
        f = tmp_path / "export.json"
        f.write_text(json.dumps(data))

        importer = CompetitorImporter()
        profiles = importer.import_file(str(f))
        assert profiles[0]["source"] == "multilogin"

    def test_file_not_found(self):
        importer = CompetitorImporter()
        with pytest.raises(FileNotFoundError):
            importer.import_file("/nonexistent.json")

    def test_unsupported_source(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text("{}")
        importer = CompetitorImporter()
        with pytest.raises(ValueError, match="Unsupported source"):
            importer.import_file(str(f), source="unknown_tool")

    def test_no_proxy(self, tmp_path):
        data = {"name": "no-proxy", "profile_id": "np1", "browser_type": "chrome"}
        f = tmp_path / "np.json"
        f.write_text(json.dumps(data))

        importer = CompetitorImporter()
        profiles = importer.import_file(str(f))
        assert profiles[0]["proxy"] is None

    def test_empty_cookies(self, tmp_path):
        data = {"name": "no-cookies", "profile_id": "nc1", "browser_type": "chrome"}
        f = tmp_path / "nc.json"
        f.write_text(json.dumps(data))

        importer = CompetitorImporter()
        profiles = importer.import_file(str(f))
        assert profiles[0]["cookies"] == []
