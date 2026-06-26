"""Tests for Phase 49.1 — Browser Profile Management + Fingerprint Generation."""
import json
import time
from pathlib import Path

import pytest

from tokenade.core.browser.profiles import BrowserProfile, ProfileManager
from tokenade.core.browser.fingerprint import FingerprintGenerator, OS_PROFILES, BROWSER_VERSIONS


# ─── BrowserProfile Tests ────────────────────────────────────

class TestBrowserProfile:
    def test_default_values(self):
        p = BrowserProfile(name="test")
        assert p.name == "test"
        assert p.browser == "chromium"
        assert p.os == "windows"
        assert p.fingerprint == {}
        assert p.proxy is None
        assert p.cookies == []
        assert p.id  # auto-generated

    def test_save_and_load(self, tmp_path):
        p = BrowserProfile(name="my-profile", browser="firefox", os="macos")
        p.fingerprint = {"test": True}
        p.save(tmp_path)
        loaded = BrowserProfile.load("my-profile", tmp_path)
        assert loaded.name == "my-profile"
        assert loaded.browser == "firefox"
        assert loaded.os == "macos"
        assert loaded.fingerprint["test"] is True

    def test_load_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            BrowserProfile.load("nonexistent", tmp_path)


# ─── ProfileManager Tests ────────────────────────────────────

class TestProfileManager:
    def test_create_profile(self, tmp_path):
        manager = ProfileManager(tmp_path)
        profile = manager.create_profile("test-profile", browser="firefox", os_name="linux")
        assert profile.name == "test-profile"
        assert profile.browser == "firefox"
        assert profile.os == "linux"
        assert profile.fingerprint  # auto-generated
        assert (tmp_path / "test-profile" / "profile.json").exists()

    def test_create_duplicate(self, tmp_path):
        manager = ProfileManager(tmp_path)
        manager.create_profile("dup")
        with pytest.raises(ValueError, match="already exists"):
            manager.create_profile("dup")

    def test_list_profiles(self, tmp_path):
        manager = ProfileManager(tmp_path)
        manager.create_profile("p1", browser="chromium")
        manager.create_profile("p2", browser="firefox")
        manager.create_profile("p3", browser="chromium")
        all_profiles = manager.list_profiles()
        assert len(all_profiles) == 3
        chrome_only = manager.list_profiles(browser="chromium")
        assert len(chrome_only) == 2

    def test_list_profiles_by_tag(self, tmp_path):
        manager = ProfileManager(tmp_path)
        manager.create_profile("t1", tags=["work", "important"])
        manager.create_profile("t2", tags=["personal"])
        manager.create_profile("t3", tags=["work"])
        work = manager.list_profiles(tag="work")
        assert len(work) == 2

    def test_get_profile(self, tmp_path):
        manager = ProfileManager(tmp_path)
        manager.create_profile("exists")
        assert manager.get_profile("exists") is not None
        assert manager.get_profile("nope") is None

    def test_delete_profile(self, tmp_path):
        manager = ProfileManager(tmp_path)
        manager.create_profile("to-delete")
        assert manager.delete_profile("to-delete") is True
        assert manager.get_profile("to-delete") is None
        assert manager.delete_profile("nope") is False

    def test_update_profile(self, tmp_path):
        manager = ProfileManager(tmp_path)
        manager.create_profile("upd")
        updated = manager.update_profile("upd", notes="updated notes", tags=["new"])
        assert updated.notes == "updated notes"
        assert updated.tags == ["new"]
        assert manager.get_profile("upd").notes == "updated notes"

    def test_mark_used(self, tmp_path):
        manager = ProfileManager(tmp_path)
        manager.create_profile("used")
        assert manager.get_profile("used").last_used is None
        manager.mark_used("used")
        assert manager.get_profile("used").last_used is not None

    def test_export_and_import(self, tmp_path):
        manager = ProfileManager(tmp_path)
        manager.create_profile("export-me", notes="test export")
        zip_path = tmp_path / "export.zip"
        manager.export_profile("export-me", str(zip_path))
        assert zip_path.exists()

        manager2 = ProfileManager(tmp_path / "imported")
        imported = manager2.import_profile(str(zip_path), name="imported")
        assert imported.name == "imported"
        assert imported.notes == "test export"

    def test_import_nonexistent(self, tmp_path):
        manager = ProfileManager(tmp_path)
        with pytest.raises(FileNotFoundError):
            manager.import_profile("/nonexistent.zip")

    def test_recent_profiles(self, tmp_path):
        manager = ProfileManager(tmp_path)
        p1 = manager.create_profile("old")
        p2 = manager.create_profile("new")
        # Simulate usage times
        manager.update_profile("old", last_used=time.time() - 3600)
        manager.update_profile("new", last_used=time.time())
        recent = manager.get_recent_profiles(limit=1)
        assert len(recent) == 1
        assert recent[0].name == "new"

    def test_stats(self, tmp_path):
        manager = ProfileManager(tmp_path)
        manager.create_profile("s1", browser="chromium")
        manager.create_profile("s2", browser="firefox")
        stats = manager.get_stats()
        assert stats["total"] == 2
        assert stats["by_browser"]["chromium"] == 1
        assert stats["by_browser"]["firefox"] == 1


# ─── FingerprintGenerator Tests ──────────────────────────────

class TestFingerprintGenerator:
    def test_generate_basic(self):
        gen = FingerprintGenerator(seed=42)
        fp = gen.generate(os_name="windows", browser="chromium")
        assert fp["navigator"]["platform"] == "Win32"
        assert fp["navigator"]["vendor"] == "Google Inc."
        assert fp["browser"] == "chromium"
        assert fp["os"] == "windows"
        assert fp["userAgent"].startswith("Mozilla/5.0")
        assert "Windows NT 10.0" in fp["userAgent"]

    def test_generate_macos(self):
        gen = FingerprintGenerator(seed=42)
        fp = gen.generate(os_name="macos", browser="safari")
        assert fp["navigator"]["platform"] == "MacIntel"
        assert fp["os"] == "macos"
        assert "Macintosh" in fp["userAgent"]

    def test_generate_linux(self):
        gen = FingerprintGenerator(seed=42)
        fp = gen.generate(os_name="linux", browser="firefox")
        assert fp["navigator"]["platform"] == "Linux x86_64"
        assert fp["os"] == "linux"
        assert "Linux" in fp["userAgent"]
        assert "Firefox" in fp["userAgent"]

    def test_consistent_with_seed(self):
        gen1 = FingerprintGenerator(seed=123)
        fp1 = gen1.generate()
        gen2 = FingerprintGenerator(seed=123)
        fp2 = gen2.generate()
        assert fp1["navigator"]["platform"] == fp2["navigator"]["platform"]
        assert fp1["navigator"]["hardwareConcurrency"] == fp2["navigator"]["hardwareConcurrency"]
        assert fp1["screen"]["width"] == fp2["screen"]["width"]
        assert fp1["webgl"]["renderer"] == fp2["webgl"]["renderer"]

    def test_different_seeds_different_results(self):
        gen1 = FingerprintGenerator(seed=1)
        fp1 = gen1.generate()
        gen2 = FingerprintGenerator(seed=9999)
        fp2 = gen2.generate()
        # At least one field should differ
        diffs = 0
        if fp1["navigator"]["hardwareConcurrency"] != fp2["navigator"]["hardwareConcurrency"]:
            diffs += 1
        if fp1["screen"]["width"] != fp2["screen"]["width"]:
            diffs += 1
        if fp1["webgl"]["renderer"] != fp2["webgl"]["renderer"]:
            diffs += 1
        assert diffs > 0

    def test_screen_resolution_realistic(self):
        gen = FingerprintGenerator(seed=42)
        fp = gen.generate()
        scr = fp["screen"]
        assert scr["width"] >= 1280
        assert scr["height"] >= 720
        assert scr["colorDepth"] == 24

    def test_hardware_realistic(self):
        gen = FingerprintGenerator(seed=42)
        fp = gen.generate()
        hw = fp["navigator"]
        assert hw["hardwareConcurrency"] in [4, 6, 8, 12, 16]
        assert hw["deviceMemory"] in [4, 8, 16, 32]

    def test_webgl_has_renderer(self):
        gen = FingerprintGenerator(seed=42)
        fp = gen.generate()
        gl = fp["webgl"]
        assert gl["vendor"]
        assert gl["renderer"]
        assert len(gl["extensions"]) > 0

    def test_fonts_populated(self):
        gen = FingerprintGenerator(seed=42)
        fp = gen.generate(os_name="windows")
        assert len(fp["fonts"]) >= 15
        assert "Arial" in fp["fonts"]

    def test_user_agent_format(self):
        gen = FingerprintGenerator(seed=42)
        fp = gen.generate(browser="chrome")
        ua = fp["userAgent"]
        assert "Chrome/" in ua
        assert "Safari/" in ua
        assert ua.startswith("Mozilla/5.0")

    def test_firefox_user_agent(self):
        gen = FingerprintGenerator(seed=42)
        fp = gen.generate(browser="firefox")
        ua = fp["userAgent"]
        assert "Firefox/" in ua
        assert "Gecko/" in ua

    def test_generate_for_session_consistent(self):
        gen = FingerprintGenerator()
        fp1 = gen.generate_for_session("session-abc")
        fp2 = gen.generate_for_session("session-abc")
        assert fp1["navigator"]["platform"] == fp2["navigator"]["platform"]
        assert fp1["screen"]["width"] == fp2["screen"]["width"]

    def test_generate_seed_deterministic(self):
        gen = FingerprintGenerator()
        s1 = gen.generate_seed("test-session")
        s2 = gen.generate_seed("test-session")
        assert s1 == s2

    def test_canvas_noise(self):
        gen = FingerprintGenerator(seed=42)
        fp = gen.generate()
        assert 0 <= fp["canvas"]["noise"] <= 0.001

    def test_audio_noise(self):
        gen = FingerprintGenerator(seed=42)
        fp = gen.generate()
        assert 0 <= fp["audio"]["noise"] <= 0.0001
        assert fp["audio"]["sampleRate"] == 44100

    def test_plugins_for_chromium(self):
        gen = FingerprintGenerator(seed=42)
        fp = gen.generate(browser="chromium")
        assert len(fp["plugins"]) > 0
        assert any("PDF" in p["name"] for p in fp["plugins"])

    def test_no_plugins_for_firefox(self):
        gen = FingerprintGenerator(seed=42)
        fp = gen.generate(browser="firefox")
        assert fp["plugins"] == []

    def test_os_profiles_covered(self):
        for os_name in ["windows", "macos", "linux"]:
            assert os_name in OS_PROFILES
            assert "platform" in OS_PROFILES[os_name]

    def test_browser_versions_covered(self):
        for browser in ["chromium", "chrome", "firefox", "brave", "safari"]:
            assert browser in BROWSER_VERSIONS
            assert len(BROWSER_VERSIONS[browser]) > 0
