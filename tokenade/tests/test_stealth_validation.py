"""Tests for Phase 50 — Stealth Testing & Validation framework."""
import json
from pathlib import Path

from tokenade.core.browser.stealth_validation import (
    StealthTestSuite,
    StealthTestReport,
    DetectionTestResult,
    Verdict,
    JS_CHECKS,
    run_stealth_tests,
)
from tokenade.core.browser.dashboard import (
    generate_html_report,
    generate_json_report,
    _categorize_results,
)


# ─── DetectionTestResult Tests ─────────────────────────────────────────

class TestDetectionTestResult:
    def test_defaults(self):
        r = DetectionTestResult(name="test", verdict=Verdict.PASS, score=100)
        assert r.name == "test"
        assert r.verdict == Verdict.PASS
        assert r.score == 100
        assert r.message == ""
        assert r.details == {}
        assert r.duration_ms == 0.0


# ─── StealthTestReport Tests ─────────────────────────────────

class TestStealthTestReport:
    def test_empty_report(self):
        report = StealthTestReport()
        assert report.overall_score == 0.0
        assert report.passed == 0
        assert report.failed == 0
        assert report.warned == 0

    def test_summary_with_results(self):
        report = StealthTestReport(
            overall_score=85.0,
            results=[
                DetectionTestResult("t1", Verdict.PASS, 100),
                DetectionTestResult("t2", Verdict.FAIL, 0, "failed"),
                DetectionTestResult("t3", Verdict.WARN, 50),
            ],
        )
        assert report.passed == 1
        assert report.failed == 1
        assert report.warned == 1
        s = report.summary()
        assert "85" in s
        assert "1 passed" in s
        assert "1 failed" in s

    def test_grades(self):
        for score, grade in [(95, "A"), (85, "B"), (75, "C"), (65, "D"), (50, "F")]:
            report = StealthTestReport(overall_score=score)
            assert report._grade() == grade


# ─── JS_CHECKS Tests ──────────────────────────────────────────

class TestJSChecks:
    def test_all_checks_have_required_fields(self):
        for check_id, check in JS_CHECKS.items():
            assert "name" in check, f"{check_id} missing name"
            assert "weight" in check, f"{check_id} missing weight"
            assert "test_js" in check, f"{check_id} missing test_js"
            assert check["weight"] > 0, f"{check_id} has zero weight"

    def test_webdriver_check_exists(self):
        assert "webdriver_undefined" in JS_CHECKS
        assert "navigator.webdriver" in JS_CHECKS["webdriver_undefined"]["name"]

    def test_no_cdc_check_exists(self):
        assert "no_cdc_artifacts" in JS_CHECKS

    def test_total_weight_reasonable(self):
        total = sum(c["weight"] for c in JS_CHECKS.values())
        assert total >= 30  # At least 30 weight points


# ─── StealthTestSuite Tests ──────────────────────────────────

class TestStealthTestSuite:
    def test_initialization(self):
        suite = StealthTestSuite(browser="chromium", headless=True)
        assert suite.browser == "chromium"
        assert suite.headless is True

    def test_stealth_script_loaded(self):
        suite = StealthTestSuite()
        script = suite._get_stealth_script()
        assert len(script) > 100
        assert "navigator" in script

    def test_calculate_score_perfect(self):
        suite = StealthTestSuite()
        results = [
            DetectionTestResult(f"check_{i}", Verdict.PASS, c["weight"] * 10)
            for i, c in enumerate(JS_CHECKS.values())
        ]
        score = suite._calculate_score(results)
        assert score >= 95  # Should be near 100

    def test_calculate_score_zero(self):
        suite = StealthTestSuite()
        results = [
            DetectionTestResult(f"check_{i}", Verdict.FAIL, 0)
            for i in range(len(JS_CHECKS))
        ]
        score = suite._calculate_score(results)
        assert score == 0.0

    def test_calculate_score_empty(self):
        suite = StealthTestSuite()
        score = suite._calculate_score([])
        assert score == 0.0


# ─── Dashboard Tests ──────────────────────────────────────────

class TestDashboard:
    def test_generate_html_report(self, tmp_path):
        report = StealthTestReport(
            overall_score=85.0,
            browser="chromium",
            results=[
                DetectionTestResult("navigator.webdriver = undefined", Verdict.PASS, 50),
                DetectionTestResult("window.chrome exists", Verdict.PASS, 40),
                DetectionTestResult("No automation artifacts", Verdict.FAIL, 0, "detected cdc_"),
            ],
        )
        output = tmp_path / "report.html"
        path = generate_html_report(report, str(output))
        assert Path(path).exists()
        content = Path(path).read_text()
        assert "Tokenade Stealth Report" in content
        assert "85" in content
        assert "B" in content
        assert "chromium" in content

    def test_generate_json_report(self, tmp_path):
        report = StealthTestReport(
            overall_score=90.0,
            browser="firefox",
            results=[
                DetectionTestResult("test1", Verdict.PASS, 100),
                DetectionTestResult("test2", Verdict.FAIL, 0),
            ],
        )
        output = tmp_path / "report.json"
        path = generate_json_report(report, str(output))
        assert Path(path).exists()
        data = json.loads(Path(path).read_text())
        assert data["overall_score"] == 90.0
        assert data["grade"] == "A"
        assert data["browser"] == "firefox"
        assert len(data["results"]) == 2

    def test_categorize_results(self):
        results = [
            DetectionTestResult("navigator.webdriver = undefined", Verdict.PASS, 50),
            DetectionTestResult("WebGL vendor is set", Verdict.PASS, 30),
            DetectionTestResult("No automation artifacts", Verdict.FAIL, 0),
            DetectionTestResult("No headless detection", Verdict.PASS, 40),
            DetectionTestResult("Site: https://example.com", Verdict.PASS, 10),
        ]
        cats = _categorize_results(results)
        assert "JavaScript Properties" in cats
        assert "Canvas & WebGL" in cats
        assert "Automation Artifacts" in cats
        assert "Site Tests" in cats
        assert len(cats["JavaScript Properties"]) == 1

    def test_categorize_empty(self):
        cats = _categorize_results([])
        assert cats == {}

    def test_html_report_has_all_sections(self, tmp_path):
        report = StealthTestReport(
            overall_score=75.0,
            results=[
                DetectionTestResult("test1", Verdict.PASS, 50),
                DetectionTestResult("test2", Verdict.WARN, 25),
            ],
        )
        path = generate_html_report(report, str(tmp_path / "r.html"))
        content = Path(path).read_text()
        assert "<!DOCTYPE html>" in content
        assert "score-circle" in content
        assert "JavaScript Properties" in content


# ─── run_stealth_tests wrapper ────────────────────────────────

class TestRunStealthTests:
    def test_import(self):
        assert callable(run_stealth_tests)


# ─── Verdict Enum ─────────────────────────────────────────────

class TestVerdict:
    def test_values(self):
        assert Verdict.PASS.value == "pass"
        assert Verdict.FAIL.value == "fail"
        assert Verdict.WARN.value == "warn"
        assert Verdict.SKIP.value == "skip"
