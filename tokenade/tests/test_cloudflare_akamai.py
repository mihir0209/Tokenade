"""Tests for Phase 47: Cloudflare & Akamai Bypass."""
import time
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from tokenade.core.browser.cloudflare import (
    CloudflareBypass,
    AkamaiBypass,
    ChallengeDetection,
    ClearanceResult,
    detect_challenge,
    extract_clearance,
    has_clearance,
    CLOUDFLARE_COOKIE_NAMES,
    AKAMAI_COOKIE_NAMES,
    CHALLENGE_INDICATORS,
)
from tokenade.core.browser.captcha import (
    CaptchaType,
    CaptchaChallenge,
    CaptchaSolution,
    CaptchaSolver,
    NullCaptchaSolver,
    CaptchaDetector,
    CaptchaManager,
)
from tokenade.core.proxy.residential import (
    ResidentialProxyConfig,
    ResidentialProxyPool,
    ProxyHealth,
    SessionAwareProxy,
    create_residential_proxy,
    DATACENTER_ASNS,
    GEO_TIMEZONE_MAP,
)


# ─── Cloudflare Bypass Tests ──────────────────────────────────

class TestCloudflareBypass:
    def test_detect_cloudflare_challenge(self):
        bypass = CloudflareBypass()
        content = '<html><title>Just a moment...</title><div class="cf-challenge"></div></html>'
        result = bypass.detect_challenge(content, "https://example.com")
        assert result.is_challenge is True
        assert result.provider == "cloudflare"
        assert len(result.indicators) > 0

    def test_detect_no_challenge(self):
        bypass = CloudflareBypass()
        content = '<html><title>Example Page</title><body>Hello</body></html>'
        result = bypass.detect_challenge(content)
        assert result.is_challenge is False
        assert result.provider is None

    def test_detect_turnstile(self):
        bypass = CloudflareBypass()
        content = '<div class="cf-turnstile" data-sitekey="0x4AAAA"></div>'
        result = bypass.detect_challenge(content)
        assert result.is_challenge is True
        assert result.challenge_type == "turnstile"

    def test_detect_akamai(self):
        bypass = CloudflareBypass()
        content = '<script>var _abck = "abc123";</script>'
        result = bypass.detect_challenge(content)
        assert result.is_challenge is True
        assert result.provider == "akamai"

    def test_extract_cf_clearance(self):
        bypass = CloudflareBypass()
        cookies = [
            {"name": "cf_clearance", "value": "abc123def"},
            {"name": "__cf_bm", "value": "xyz789"},
            {"name": "other_cookie", "value": "ignore"},
        ]
        result = bypass.extract_cookies_from_page(cookies)
        assert result.success is True
        assert "cf_clearance" in result.cookies
        assert "__cf_bm" in result.cookies
        assert result.provider == "cloudflare"

    def test_extract_akamai_cookies(self):
        bypass = CloudflareBypass()
        cookies = [
            {"name": "_abck", "value": "ak123"},
            {"name": "ak_bmsc", "value": "bm456"},
            {"name": "other", "value": "ignore"},
        ]
        result = bypass.extract_cookies_from_page(cookies)
        assert result.success is True
        assert "_abck" in result.cookies
        assert "ak_bmsc" in result.cookies
        assert result.provider == "akamai"

    def test_extract_no_cookies(self):
        bypass = CloudflareBypass()
        cookies = [{"name": "session_id", "value": "abc"}]
        result = bypass.extract_cookies_from_page(cookies)
        assert result.success is False
        assert "No Cloudflare" in result.error

    def test_has_clearance_true(self):
        bypass = CloudflareBypass()
        cookies = [{"name": "cf_clearance", "value": "abc"}]
        assert bypass.has_clearance(cookies) is True

    def test_has_clearance_false(self):
        bypass = CloudflareBypass()
        cookies = [{"name": "session_id", "value": "abc"}]
        assert bypass.has_clearance(cookies) is False

    def test_get_clearance_quick(self):
        bypass = CloudflareBypass()
        cookies = [{"name": "cf_clearance", "value": "abc123"}]
        result = bypass.get_clearance_from_cookies(cookies)
        assert "cf_clearance" in result
        assert result["cf_clearance"] == "abc123"

    def test_merge_clearance_into_session(self):
        bypass = CloudflareBypass()
        session = {"cookies": [{"name": "session_id", "value": "abc"}]}
        clearance = {"cf_clearance": "xyz789"}
        result = bypass.merge_clearance_into_session(session, clearance)
        assert len(result["cookies"]) == 2
        names = {c["name"] for c in result["cookies"]}
        assert "cf_clearance" in names
        assert "session_id" in names

    def test_merge_existing_cookie_updated(self):
        bypass = CloudflareBypass()
        session = {"cookies": [{"name": "cf_clearance", "value": "old"}]}
        clearance = {"cf_clearance": "new_value"}
        result = bypass.merge_clearance_into_session(session, clearance)
        assert len(result["cookies"]) == 1
        assert result["cookies"][0]["value"] == "new_value"


class TestChallengeDetectionQuick:
    def test_detect_challenge_function(self):
        content = '<title>Just a moment...</title>'
        result = detect_challenge(content)
        assert result.is_challenge is True

    def test_extract_clearance_function(self):
        cookies = [{"name": "cf_clearance", "value": "abc"}]
        result = extract_clearance(cookies)
        assert "cf_clearance" in result

    def test_has_clearance_function(self):
        assert has_clearance([{"name": "cf_clearance", "value": "x"}]) is True
        assert has_clearance([{"name": "other", "value": "x"}]) is False


# ─── CAPTCHA Tests ────────────────────────────────────────────

class TestCaptchaDetector:
    def test_detect_recaptcha(self):
        detector = CaptchaDetector()
        html = '<div class="g-recaptcha" data-sitekey="6Le-wvkSAAAAAPBMRTnh0YBz0DlIu6Ydg_qGFJc"></div>'
        challenge = detector.detect(html, "https://example.com")
        assert challenge is not None
        assert challenge.captcha_type == CaptchaType.RECAPTCHA_V2
        assert challenge.site_key is not None

    def test_detect_hcaptcha(self):
        detector = CaptchaDetector()
        html = '<div class="h-captcha" data-sitekey="10000000-ffff-ffff-ffff-000000000001"></div>'
        challenge = detector.detect(html)
        assert challenge is not None
        assert challenge.captcha_type == CaptchaType.HCAPTCHA

    def test_detect_turnstile(self):
        detector = CaptchaDetector()
        html = '<div class="cf-turnstile" data-sitekey="0x4AAAA"></div>'
        challenge = detector.detect(html)
        assert challenge is not None
        assert challenge.captcha_type == CaptchaType.TURNSTILE

    def test_detect_no_captcha(self):
        detector = CaptchaDetector()
        html = '<html><body>Hello World</body></html>'
        challenge = detector.detect(html)
        assert challenge is None


class TestNullCaptchaSolver:
    def test_name(self):
        solver = NullCaptchaSolver()
        assert solver.name == "null"

    def test_supported_types(self):
        solver = NullCaptchaSolver()
        assert solver.supported_types == []

    def test_solve_fails(self):
        solver = NullCaptchaSolver()
        challenge = CaptchaChallenge(captcha_type=CaptchaType.RECAPTCHA_V2)
        solution = solver.solve(challenge)
        assert solution.success is False
        assert "No CAPTCHA solver" in solution.error

    def test_can_solve(self):
        solver = NullCaptchaSolver()
        assert solver.can_solve(CaptchaType.RECAPTCHA_V2) is False


class TestCaptchaManager:
    def test_default_solver(self):
        manager = CaptchaManager()
        assert isinstance(manager.solver, NullCaptchaSolver)

    def test_set_solver(self):
        manager = CaptchaManager()
        solver = NullCaptchaSolver()
        manager.set_solver(solver)
        assert manager.solver is solver

    def test_detect(self):
        manager = CaptchaManager()
        html = '<div class="g-recaptcha" data-sitekey="abc"></div>'
        challenge = manager.detect(html)
        assert challenge is not None
        assert challenge.captcha_type == CaptchaType.RECAPTCHA_V2

    def test_solve_fails_with_null(self):
        manager = CaptchaManager()
        challenge = CaptchaChallenge(captcha_type=CaptchaType.RECAPTCHA_V2)
        solution = manager.solve(challenge)
        assert solution.success is False

    def test_get_info(self):
        manager = CaptchaManager()
        info = manager.get_info()
        assert "solver" in info
        assert info["solver"]["name"] == "null"


# ─── Residential Proxy Tests ──────────────────────────────────

class TestResidentialProxyConfig:
    def test_create_config(self):
        config = ResidentialProxyConfig(
            host="proxy.example.com",
            port=8080,
            username="user",
            password="pass",
            country="US",
        )
        assert config.host == "proxy.example.com"
        assert config.port == 8080
        assert config.country == "US"
        assert config.is_residential is True

    def test_create_function(self):
        proxy = create_residential_proxy(
            host="1.2.3.4",
            port=3128,
            country="DE",
            username="u",
            password="p",
        )
        assert proxy.host == "1.2.3.4"
        assert proxy.port == 3128
        assert proxy.country == "DE"


class TestResidentialProxyPool:
    def test_empty_pool(self):
        pool = ResidentialProxyPool()
        assert pool.get_next() is None
        assert pool.get_stats()["total"] == 0

    def test_add_and_get(self):
        pool = ResidentialProxyPool()
        proxy = ResidentialProxyConfig(host="1.1.1.1", port=8080)
        pool.add_proxy(proxy)
        assert pool.get_next() is not None
        assert pool.get_stats()["total"] == 1

    def test_round_robin(self):
        pool = ResidentialProxyPool()
        pool.add_proxy(ResidentialProxyConfig(host="1.1.1.1", port=8080))
        pool.add_proxy(ResidentialProxyConfig(host="2.2.2.2", port=8080))
        p1 = pool.get_next()
        p2 = pool.get_next()
        assert p1.host != p2.host

    def test_get_by_country(self):
        pool = ResidentialProxyPool()
        pool.add_proxy(ResidentialProxyConfig(host="1.1.1.1", port=8080, country="US"))
        pool.add_proxy(ResidentialProxyConfig(host="2.2.2.2", port=8080, country="DE"))
        proxy = pool.get_by_country("US")
        assert proxy is not None
        assert proxy.country == "US"

    def test_get_best_for_session(self):
        pool = ResidentialProxyPool()
        pool.add_proxy(ResidentialProxyConfig(host="1.1.1.1", port=8080, country="US"))
        pool.add_proxy(ResidentialProxyConfig(host="2.2.2.2", port=8080, country="DE"))
        session = {"timezone": "America/New_York"}
        proxy = pool.get_best_for_session(session)
        assert proxy is not None
        assert proxy.country == "US"

    def test_mark_success_failure(self):
        pool = ResidentialProxyPool()
        proxy = ResidentialProxyConfig(host="1.1.1.1", port=8080)
        pool.add_proxy(proxy)
        pool.mark_success("1.1.1.1", 8080, 0.5)
        pool.mark_failure("1.1.1.1", 8080, "timeout")
        stats = pool.get_stats()
        assert stats["total"] == 1

    def test_mark_failure_unhealthy(self):
        pool = ResidentialProxyPool()
        proxy = ResidentialProxyConfig(host="1.1.1.1", port=8080)
        pool.add_proxy(proxy)
        for _ in range(3):
            pool.mark_failure("1.1.1.1", 8080, "error")
        assert pool.get_next() is None

    def test_remove_proxy(self):
        pool = ResidentialProxyPool()
        pool.add_proxy(ResidentialProxyConfig(host="1.1.1.1", port=8080))
        assert pool.remove_proxy("1.1.1.1", 8080) is True
        assert pool.get_stats()["total"] == 0

    def test_get_proxy_url(self):
        pool = ResidentialProxyPool()
        proxy = ResidentialProxyConfig(
            host="1.1.1.1", port=8080,
            username="user", password="pass",
        )
        url = pool.get_proxy_url(proxy)
        assert "user:pass@1.1.1.1:8080" in url

    def test_load_from_file(self, tmp_path):
        proxy_file = tmp_path / "proxies.txt"
        proxy_file.write_text("http://user:pass@1.1.1.1:8080\nhttp://2.2.2.2:3128\n")
        pool = ResidentialProxyPool()
        pool.load_from_file(str(proxy_file))
        assert pool.get_stats()["total"] == 2

    def test_load_from_config(self):
        pool = ResidentialProxyPool()
        config = {
            "proxies": [
                {"host": "1.1.1.1", "port": 8080, "country": "US"},
                {"host": "2.2.2.2", "port": 3128, "country": "DE"},
            ]
        }
        pool.load_from_config(config)
        assert pool.get_stats()["total"] == 2


class TestSessionAwareProxy:
    def test_select_for_session(self):
        pool = ResidentialProxyPool()
        pool.add_proxy(ResidentialProxyConfig(host="1.1.1.1", port=8080, country="US"))
        aware = SessionAwareProxy(pool)
        session = {"timezone": "America/New_York"}
        proxy = aware.select_for_session(session)
        assert proxy is not None

    def test_apply_to_session(self):
        pool = ResidentialProxyPool()
        proxy = ResidentialProxyConfig(host="1.1.1.1", port=8080, country="US")
        pool.add_proxy(proxy)
        aware = SessionAwareProxy(pool)
        session = {}
        result = aware.apply_to_session(session, proxy)
        assert "upstream_proxy" in result
        assert result["proxy_country"] == "US"

    def test_apply_to_launch_config(self):
        pool = ResidentialProxyPool()
        proxy = ResidentialProxyConfig(host="1.1.1.1", port=8080)
        pool.add_proxy(proxy)
        aware = SessionAwareProxy(pool)
        config = MagicMock()
        result = aware.apply_to_launch_config(config, proxy)
        assert result.upstream_proxy is not None
