"""
Tests for ChallengeDetectorPlugin base and concrete anti-bot detectors:
1. CloudflareChallengeDetector (Turnstile, 5-second shield, WAF blocks)
2. AkamaiChallengeDetector (Bot Manager, sensor scripts, Sec-CPT)
3. DataDomeChallengeDetector (Device checks, Captcha delivery)
"""

import pytest

from tokenade.core.integration.challenge_detectors import (
    AkamaiChallengeDetector,
    CloudflareChallengeDetector,
    DataDomeChallengeDetector,
)


class TestCloudflareDetector:
    """Tests for Cloudflare challenge detection."""

    def test_detect_turnstile_widget(self):
        detector = CloudflareChallengeDetector()
        mock_page = {
            "html": "<html><body><div class='cf-turnstile' data-sitekey='0x4AAAAAA'></div><iframe src='https://challenges.cloudflare.com/turnstile/v0/api.js'></iframe></body></html>",
            "title": "Login Page",
            "headers": {"server": "cloudflare"},
            "status_code": 200,
        }
        res = detector.detect_challenge(mock_page)
        assert res.success is True
        assert res.data["detected"] is True
        assert res.data["provider"] == "cloudflare"
        assert res.data["challenge_type"] == "turnstile"
        assert res.data["confidence"] >= 0.9

    def test_detect_managed_challenge_interstitial(self):
        detector = CloudflareChallengeDetector()
        mock_page = {
            "html": "<div id='cf-challenge-running'>Just a moment while we check your connection...</div>",
            "title": "Just a moment...",
            "headers": {"cf-mitigated": "challenge", "server": "cloudflare"},
            "status_code": 403,
        }
        res = detector.detect_challenge(mock_page)
        assert res.success is True
        assert res.data["detected"] is True
        assert res.data["challenge_type"] == "managed_challenge"

    def test_clean_page_no_challenge(self):
        detector = CloudflareChallengeDetector()
        mock_page = {
            "html": "<html><body>Welcome to normal website</body></html>",
            "title": "Home Dashboard",
            "headers": {"server": "nginx"},
            "status_code": 200,
        }
        res = detector.detect_challenge(mock_page)
        assert res.success is True
        assert res.data["detected"] is False


class TestAkamaiDetector:
    """Tests for Akamai Bot Manager detection."""

    def test_detect_akamai_sec_cpt(self):
        detector = AkamaiChallengeDetector()
        mock_page = {
            "html": "<html><head><title>Access Denied</title></head><body>sec-cpt challenge active</body></html>",
            "title": "Access Denied",
            "headers": {"server": "AkamaiGHost", "x-akamai-transformed": "9 100 0 pmb=mRUM,1"},
            "status_code": 403,
        }
        res = detector.detect_challenge(mock_page)
        assert res.success is True
        assert res.data["detected"] is True
        assert res.data["provider"] == "akamai"


class TestDataDomeDetector:
    """Tests for DataDome captcha detection."""

    def test_detect_datadome_captcha(self):
        detector = DataDomeChallengeDetector()
        mock_page = {
            "html": "<html><body><script src='https://geo.captcha-delivery.com/captcha/captcha.js'></script>Please enable JS</body></html>",
            "title": "Verification Required",
            "headers": {"x-datadome": "protected"},
            "status_code": 403,
        }
        res = detector.detect_challenge(mock_page)
        assert res.success is True
        assert res.data["detected"] is True
        assert res.data["provider"] == "datadome"
        assert res.data["challenge_type"] == "datadome_captcha"
