"""Tests for Phase 50.3 — Fingerprint consistency tests."""
import hashlib
import json

import pytest

from tokenade.core.browser.fingerprint import FingerprintGenerator
from tokenade.core.browser.stealth import StealthManager


class TestFingerprintConsistency:
    """Verify fingerprints are consistent and realistic."""

    def test_canvas_noise_deterministic(self):
        """Same seed should produce same canvas noise."""
        gen1 = FingerprintGenerator(seed=42)
        fp1 = gen1.generate()
        gen2 = FingerprintGenerator(seed=42)
        fp2 = gen2.generate()
        assert fp1["canvas"]["noise"] == fp2["canvas"]["noise"]

    def test_canvas_noise_range(self):
        """Canvas noise should be small and positive."""
        gen = FingerprintGenerator(seed=42)
        for _ in range(100):
            fp = gen.generate()
            assert 0 <= fp["canvas"]["noise"] <= 0.001

    def test_webgl_consistent_per_seed(self):
        """Same seed = same WebGL vendor/renderer."""
        gen1 = FingerprintGenerator(seed=123)
        fp1 = gen1.generate()
        gen2 = FingerprintGenerator(seed=123)
        fp2 = gen2.generate()
        assert fp1["webgl"]["vendor"] == fp2["webgl"]["vendor"]
        assert fp1["webgl"]["renderer"] == fp2["webgl"]["renderer"]
        assert fp1["webgl"]["extensions"] == fp2["webgl"]["extensions"]

    def test_audio_noise_consistent(self):
        """Same seed = same audio noise."""
        gen1 = FingerprintGenerator(seed=99)
        fp1 = gen1.generate()
        gen2 = FingerprintGenerator(seed=99)
        fp2 = gen2.generate()
        assert fp1["audio"]["noise"] == fp2["audio"]["noise"]

    def test_navigator_consistent(self):
        """Same seed = same navigator properties."""
        gen1 = FingerprintGenerator(seed=77)
        fp1 = gen1.generate()
        gen2 = FingerprintGenerator(seed=77)
        fp2 = gen2.generate()
        assert fp1["navigator"]["platform"] == fp2["navigator"]["platform"]
        assert fp1["navigator"]["hardwareConcurrency"] == fp2["navigator"]["hardwareConcurrency"]
        assert fp1["navigator"]["deviceMemory"] == fp2["navigator"]["deviceMemory"]

    def test_screen_consistent(self):
        """Same seed = same screen resolution."""
        gen1 = FingerprintGenerator(seed=55)
        fp1 = gen1.generate()
        gen2 = FingerprintGenerator(seed=55)
        fp2 = gen2.generate()
        assert fp1["screen"]["width"] == fp2["screen"]["width"]
        assert fp1["screen"]["height"] == fp2["screen"]["height"]

    def test_fonts_consistent(self):
        """Same seed = same font list."""
        gen1 = FingerprintGenerator(seed=33)
        fp1 = gen1.generate()
        gen2 = FingerprintGenerator(seed=33)
        fp2 = gen2.generate()
        assert fp1["fonts"] == fp2["fonts"]

    def test_plugins_consistent(self):
        """Same seed = same plugin list."""
        gen1 = FingerprintGenerator(seed=11)
        fp1 = gen1.generate(browser="chromium")
        gen2 = FingerprintGenerator(seed=11)
        fp2 = gen2.generate(browser="chromium")
        assert fp1["plugins"] == fp2["plugins"]

    def test_different_seeds_different(self):
        """Different seeds should produce different fingerprints."""
        gen1 = FingerprintGenerator(seed=1)
        fp1 = gen1.generate()
        gen2 = FingerprintGenerator(seed=99999)
        fp2 = gen2.generate()
        # At least some fields should differ
        diffs = 0
        if fp1["navigator"]["hardwareConcurrency"] != fp2["navigator"]["hardwareConcurrency"]:
            diffs += 1
        if fp1["screen"]["width"] != fp2["screen"]["width"]:
            diffs += 1
        if fp1["webgl"]["renderer"] != fp2["webgl"]["renderer"]:
            diffs += 1
        if fp1["fonts"] != fp2["fonts"]:
            diffs += 1
        assert diffs >= 2

    def test_generate_for_session_consistent(self):
        """Same session ID = same fingerprint."""
        gen = FingerprintGenerator()
        fp1 = gen.generate_for_session("session-abc-123")
        fp2 = gen.generate_for_session("session-abc-123")
        assert fp1["navigator"]["platform"] == fp2["navigator"]["platform"]
        assert fp1["screen"]["width"] == fp2["screen"]["width"]
        assert fp1["webgl"]["renderer"] == fp2["webgl"]["renderer"]

    def test_user_agent_matches_os(self):
        """User agent should match the OS."""
        gen = FingerprintGenerator(seed=42)
        fp = gen.generate(os_name="windows", browser="chrome")
        assert "Windows" in fp["userAgent"]

        fp_mac = gen.generate(os_name="macos", browser="chrome")
        assert "Macintosh" in fp_mac["userAgent"]

        fp_linux = gen.generate(os_name="linux", browser="chrome")
        assert "Linux" in fp_linux["userAgent"]

    def test_user_agent_matches_browser(self):
        """User agent should match the browser."""
        gen = FingerprintGenerator(seed=42)
        fp_chrome = gen.generate(browser="chrome")
        assert "Chrome/" in fp_chrome["userAgent"]

        fp_ff = gen.generate(browser="firefox")
        assert "Firefox/" in fp_ff["userAgent"]

    def test_screen_resolution_reasonable(self):
        """Screen resolution should be realistic."""
        gen = FingerprintGenerator(seed=42)
        for _ in range(20):
            fp = gen.generate()
            assert 1280 <= fp["screen"]["width"] <= 3840
            assert 720 <= fp["screen"]["height"] <= 2160

    def test_hardware_concurrency_reasonable(self):
        """hardwareConcurrency should be realistic."""
        gen = FingerprintGenerator(seed=42)
        for _ in range(20):
            fp = gen.generate()
            assert 2 <= fp["navigator"]["hardwareConcurrency"] <= 64

    def test_device_memory_reasonable(self):
        """deviceMemory should be realistic."""
        gen = FingerprintGenerator(seed=42)
        for _ in range(20):
            fp = gen.generate()
            assert fp["navigator"]["deviceMemory"] in [4, 8, 16, 32]

    def test_stealth_script_injection_consistency(self):
        """StealthManager script should be consistent."""
        mgr1 = StealthManager()
        s1 = mgr1.get_comprehensive_script()
        mgr2 = StealthManager()
        s2 = mgr2.get_comprehensive_script()
        assert s1 == s2
        assert len(s1) > 1000

    def test_fingerprint_hash_stable(self):
        """Same fingerprint should produce same hash."""
        gen = FingerprintGenerator(seed=42)
        fp = gen.generate()
        fp_str = json.dumps(fp, sort_keys=True)
        h1 = hashlib.sha256(fp_str.encode()).hexdigest()
        h2 = hashlib.sha256(fp_str.encode()).hexdigest()
        assert h1 == h2

    def test_browser_versions_valid(self):
        """Browser version strings should be valid."""
        gen = FingerprintGenerator(seed=42)
        for browser in ["chromium", "chrome", "firefox", "brave", "safari"]:
            fp = gen.generate(browser=browser)
            version = fp["browserVersion"]
            assert "." in version
            parts = version.split(".")
            assert len(parts) >= 2
            assert all(p.isdigit() for p in parts[:2])

    def test_timezone_matches_os(self):
        """Timezone should match the OS."""
        gen = FingerprintGenerator(seed=42)
        fp = gen.generate(os_name="windows")
        assert fp["timezone"] == "America/New_York"

        fp_mac = gen.generate(os_name="macos")
        assert fp_mac["timezone"] == "America/Los_Angeles"

    def test_fingerprint_per_session_unique(self):
        """Different session IDs should produce different fingerprints."""
        gen = FingerprintGenerator()
        fp1 = gen.generate_for_session("session-1")
        fp2 = gen.generate_for_session("session-2")
        diffs = 0
        if fp1["navigator"]["hardwareConcurrency"] != fp2["navigator"]["hardwareConcurrency"]:
            diffs += 1
        if fp1["screen"]["width"] != fp2["screen"]["width"]:
            diffs += 1
        if fp1["fonts"] != fp2["fonts"]:
            diffs += 1
        assert diffs >= 1
