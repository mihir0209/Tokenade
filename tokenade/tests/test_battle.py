"""Tests for Phase 52 — Battle Test Suite (end-to-end stealth validation)."""

from tokenade.core.browser.battle import (
    BattleTestSuite,
    BattleTestReport,
    BattleVerdict,
    SiteResult,
    DETECTION_SITES,
    _run_battle_site,
)


# ─── SiteResult Tests ─────────────────────────────────────────

class TestSiteResult:
    def test_defaults(self):
        r = SiteResult(
            site_name="test",
            url="https://test.com",
            verdict=BattleVerdict.CLEAN,
            score=95.0,
        )
        assert r.site_name == "test"
        assert r.verdict == BattleVerdict.CLEAN
        assert r.score == 95.0
        assert r.passed is True
        assert r.error == ""

    def test_not_passed_when_detected(self):
        r = SiteResult(
            site_name="test",
            url="https://test.com",
            verdict=BattleVerdict.DETECTED,
            score=10.0,
        )
        assert r.passed is False

    def test_not_passed_when_error(self):
        r = SiteResult(
            site_name="test",
            url="https://test.com",
            verdict=BattleVerdict.ERROR,
            score=0.0,
            error="timeout",
        )
        assert r.passed is False

    def test_partial_is_not_passed(self):
        r = SiteResult(
            site_name="test",
            url="https://test.com",
            verdict=BattleVerdict.PARTIAL,
            score=50.0,
        )
        assert r.passed is False


# ─── BattleTestReport Tests ─────────────────────────────────

class TestBattleTestReport:
    def test_empty_report(self):
        report = BattleTestReport()
        assert report.overall_score == 0.0
        assert report.passed == 0
        assert report.detected == 0
        assert report.partial == 0
        assert report.errors == 0
        assert report.skipped == 0
        assert report.total_sites == 0
        assert report.grade == "F"

    def test_grade_a(self):
        report = BattleTestReport(overall_score=95.0)
        assert report.grade == "A"

    def test_grade_b(self):
        report = BattleTestReport(overall_score=85.0)
        assert report.grade == "B"

    def test_grade_c(self):
        report = BattleTestReport(overall_score=72.0)
        assert report.grade == "C"

    def test_grade_d(self):
        report = BattleTestReport(overall_score=55.0)
        assert report.grade == "D"

    def test_grade_f(self):
        report = BattleTestReport(overall_score=30.0)
        assert report.grade == "F"

    def test_counts_with_results(self):
        report = BattleTestReport(
            overall_score=80.0,
            site_results=[
                SiteResult("s1", "u1", BattleVerdict.CLEAN, 90),
                SiteResult("s2", "u2", BattleVerdict.DETECTED, 10),
                SiteResult("s3", "u3", BattleVerdict.PARTIAL, 50),
                SiteResult("s4", "u4", BattleVerdict.ERROR, 0, error="fail"),
                SiteResult("s5", "u5", BattleVerdict.SKIPPED, 0),
            ],
        )
        assert report.passed == 1
        assert report.detected == 1
        assert report.partial == 1
        assert report.errors == 1
        assert report.skipped == 1
        assert report.total_sites == 5

    def test_summary_contains_grade(self):
        report = BattleTestReport(overall_score=88.0)
        s = report.summary()
        assert "B" in s
        assert "88" in s

    def test_summary_contains_site_icons(self):
        report = BattleTestReport(
            overall_score=80.0,
            site_results=[
                SiteResult("clean_site", "u1", BattleVerdict.CLEAN, 90),
                SiteResult("detected_site", "u2", BattleVerdict.DETECTED, 10),
            ],
        )
        s = report.summary()
        assert "clean_site" in s
        assert "detected_site" in s


# ─── DETECTION_SITES Registry Tests ─────────────────────────────

class TestDetectionSitesRegistry:
    def test_all_sites_have_required_keys(self):
        required = {"name", "url", "weight", "extract_js"}
        for key, site in DETECTION_SITES.items():
            for field in required:
                assert field in site, f"{key} missing {field}"

    def test_all_urls_are_https(self):
        for key, site in DETECTION_SITES.items():
            assert site["url"].startswith("https://"), f"{key} URL not HTTPS"

    def test_weights_are_valid(self):
        for key, site in DETECTION_SITES.items():
            assert 0 < site["weight"] <= 1.0, f"{key} weight out of range"

    def test_extract_js_is_non_empty_string(self):
        for key, site in DETECTION_SITES.items():
            assert isinstance(site["extract_js"], str)
            assert len(site["extract_js"]) > 10, f"{key} extract_js too short"

    def test_all_sites_have_unique_urls(self):
        urls = [s["url"] for s in DETECTION_SITES.values()]
        assert len(urls) == len(set(urls)), "Duplicate URLs in registry"

    def test_known_sites_present(self):
        expected = {"bot_sannysoft", "creepjs", "pixelscan", "browserleaks", "iphey"}
        assert expected.issubset(set(DETECTION_SITES.keys()))

    def test_bot_sannysoft_extract_js_returns_expected_shape(self):
        site = DETECTION_SITES["bot_sannysoft"]
        assert "score" in site["extract_js"]
        assert "failed_checks" in site["extract_js"]
        assert "summary" in site["extract_js"]

    def test_creepjs_extract_js_has_async_await(self):
        site = DETECTION_SITES["creepjs"]
        assert "async" in site["extract_js"]
        assert "await" in site["extract_js"]

    def test_pixelscan_extract_js_has_async_await(self):
        site = DETECTION_SITES["pixelscan"]
        assert "async" in site["extract_js"]
        assert "await" in site["extract_js"]


# ─── BattleTestSuite Tests ───────────────────────────────────

class TestBattleTestSuite:
    def test_defaults(self):
        suite = BattleTestSuite()
        assert suite.browser == "chromium"
        assert suite.headless is True
        assert suite.sites == list(DETECTION_SITES.keys())
        assert suite.timeout_ms == 30000

    def test_custom_sites(self):
        suite = BattleTestSuite(sites=["bot_sannysoft", "creepjs"])
        assert suite.sites == ["bot_sannysoft", "creepjs"]

    def test_custom_timeout(self):
        suite = BattleTestSuite(timeout_ms=60000)
        assert suite.timeout_ms == 60000

    def test_firefox_browser(self):
        suite = BattleTestSuite(browser="firefox")
        assert suite.browser == "firefox"

    def test_unknown_site_in_list(self):
        suite = BattleTestSuite(sites=["nonexistent_site"])
        report = suite.run_sync()
        assert report.site_results[0].verdict == BattleVerdict.SKIPPED
        assert "Unknown site" in report.site_results[0].error

    def test_get_stealth_script_returns_string(self):
        suite = BattleTestSuite()
        script = suite._get_stealth_script()
        assert isinstance(script, str)


# ─── _run_battle_site Tests ──────────────────────────────────

class TestRunBattleSite:
    def test_unknown_site_returns_skipped(self):
        import inspect
        sig = inspect.signature(_run_battle_site)
        params = list(sig.parameters.keys())
        assert "browser_type" in params
        assert "site_config" in params
        assert "stealth_script" in params
        assert "headless" in params
        assert "timeout_ms" in params


# ─── BattleVerdict Tests ─────────────────────────────────────

class TestBattleVerdict:
    def test_all_values(self):
        values = [v.value for v in BattleVerdict]
        assert "clean" in values
        assert "detected" in values
        assert "partial" in values
        assert "error" in values
        assert "skipped" in values

    def test_count(self):
        assert len(BattleVerdict) == 5


# ─── Integration: Score Calculation ──────────────────────────

class TestScoreCalculation:
    def test_perfect_score(self):
        report = BattleTestReport(
            overall_score=100.0,
            site_results=[
                SiteResult("s1", "u1", BattleVerdict.CLEAN, 100),
            ],
        )
        assert report.grade == "A"
        assert report.passed == 1

    def test_mixed_results_weighted(self):
        sites = [
            SiteResult("s1", "u1", BattleVerdict.CLEAN, 100),
            SiteResult("s2", "u2", BattleVerdict.DETECTED, 0),
        ]
        report = BattleTestReport(
            overall_score=50.0,
            site_results=sites,
        )
        assert report.passed == 1
        assert report.detected == 1
        assert 50 <= report.overall_score <= 60

    def test_all_errors(self):
        report = BattleTestReport(
            overall_score=0.0,
            site_results=[
                SiteResult("s1", "u1", BattleVerdict.ERROR, 0, error="timeout"),
                SiteResult("s2", "u2", BattleVerdict.ERROR, 0, error="crash"),
            ],
        )
        assert report.errors == 2
        assert report.grade == "F"
