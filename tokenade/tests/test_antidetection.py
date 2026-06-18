"""Tests for CDPCleaner and BehavioralInjector."""

import re

from tokenade.core.antidetection.cdp_cleaner import CDPCleaner
from tokenade.core.antidetection.behavioral import BehavioralInjector


class TestCDPCleaner:
    def test_stealth_scripts_is_list(self):
        scripts = CDPCleaner.get_stealth_scripts()
        assert isinstance(scripts, list)
        assert len(scripts) > 0

    def test_all_scripts_are_strings(self):
        for script in CDPCleaner.get_stealth_scripts():
            assert isinstance(script, str)
            assert len(script.strip()) > 0

    def test_scripts_are_valid_javascript(self):
        js_pattern = re.compile(r"[a-zA-Z_$][\w$]*\s*[\(\.\[=]|function\s|delete\s|if\s*\(")
        for script in CDPCleaner.get_stealth_scripts():
            stripped = script.strip()
            assert js_pattern.search(stripped), f"Script does not look like valid JS: {stripped[:80]}"

    def test_get_init_script(self):
        init = CDPCleaner.get_init_script()
        assert isinstance(init, str)
        assert len(init) > 0
        # Should contain all stealth scripts
        for script in CDPCleaner.get_stealth_scripts():
            assert script.strip() in init

    def test_init_script_contains_webdriver_removal(self):
        init = CDPCleaner.get_init_script()
        assert "webdriver" in init

    def test_init_script_contains_cdc_removal(self):
        init = CDPCleaner.get_init_script()
        assert "cdc_" in init

    def test_init_script_contains_plugins(self):
        init = CDPCleaner.get_init_script()
        assert "plugins" in init

    def test_init_script_contains_languages(self):
        init = CDPCleaner.get_init_script()
        assert "languages" in init

    def test_no_syntax_errors_basic_check(self):
        """Check that scripts don't have obvious unclosed braces."""
        for script in CDPCleaner.get_stealth_scripts():
            opens = script.count("{")
            closes = script.count("}")
            assert opens == closes, f"Unmatched braces in: {script.strip()[:80]}"


class TestBehavioralInjector:
    def test_mouse_path_returns_list(self):
        path = BehavioralInjector.generate_mouse_path((0, 0), (100, 100))
        assert isinstance(path, list)
        assert len(path) > 0

    def test_mouse_path_has_required_fields(self):
        path = BehavioralInjector.generate_mouse_path((0, 0), (50, 50))
        for point in path:
            assert "x" in point
            assert "y" in point
            assert "delay_ms" in point

    def test_mouse_path_starts_near_start(self):
        path = BehavioralInjector.generate_mouse_path((10, 20), (200, 200))
        assert abs(path[0]["x"] - 10) < 5
        assert abs(path[0]["y"] - 20) < 5

    def test_mouse_path_ends_near_end(self):
        path = BehavioralInjector.generate_mouse_path((0, 0), (200, 200))
        last = path[-1]
        assert abs(last["x"] - 200) < 5
        assert abs(last["y"] - 200) < 5

    def test_mouse_path_custom_steps(self):
        path = BehavioralInjector.generate_mouse_path((0, 0), (100, 100), steps=30)
        assert len(path) == 31  # steps + 1 points

    def test_mouse_path_delay_in_range(self):
        path = BehavioralInjector.generate_mouse_path((0, 0), (500, 500))
        for point in path:
            assert 1 <= point["delay_ms"] <= 30

    def test_mouse_path_long_distance(self):
        path = BehavioralInjector.generate_mouse_path((0, 0), (1000, 800))
        assert len(path) >= 10

    def test_scroll_pattern_returns_list(self):
        pattern = BehavioralInjector.generate_scroll_pattern(500)
        assert isinstance(pattern, list)
        assert len(pattern) > 0

    def test_scroll_pattern_has_required_fields(self):
        pattern = BehavioralInjector.generate_scroll_pattern(300)
        for item in pattern:
            assert "delta_y" in item
            assert "delay_ms" in item

    def test_scroll_pattern_total_distance(self):
        pattern = BehavioralInjector.generate_scroll_pattern(1000)
        total = sum(item["delta_y"] for item in pattern)
        assert total == 1000

    def test_scroll_pattern_positive_values(self):
        pattern = BehavioralInjector.generate_scroll_pattern(500)
        for item in pattern:
            assert item["delta_y"] > 0
            assert item["delay_ms"] > 0

    def test_scroll_pattern_zero_distance(self):
        pattern = BehavioralInjector.generate_scroll_pattern(0)
        assert pattern == []

    def test_scroll_pattern_short_distance(self):
        pattern = BehavioralInjector.generate_scroll_pattern(10)
        assert len(pattern) >= 1

    def test_click_timing_in_range(self):
        for _ in range(100):
            delay = BehavioralInjector.generate_click_timing()
            assert 50 <= delay <= 400

    def test_click_timing_distribution(self):
        delays = [BehavioralInjector.generate_click_timing() for _ in range(500)]
        mean = sum(delays) / len(delays)
        # Mean should be around 150ms (within 50ms tolerance for randomness)
        assert 100 < mean < 250

    def test_stealth_inject_script(self):
        script = BehavioralInjector.get_stealth_inject_script()
        assert isinstance(script, str)
        assert len(script.strip()) > 0
        assert "dispatchEvent" in script
        assert "MouseEvent" in script

    def test_stealth_script_balanced_braces(self):
        script = BehavioralInjector.get_stealth_inject_script()
        assert script.count("{") == script.count("}")
