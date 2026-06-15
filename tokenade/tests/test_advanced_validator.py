"""Tests for advanced_validator module."""

import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from tokenade.core.importer.advanced_validator import (
    ValidationResult, ValidationRule, AdvancedValidator,
    load_validation_rules, create_example_rules,
)


class TestValidationResult:
    def test_creation(self):
        r = ValidationResult(rule_name="test", passed=True, message="ok")
        assert r.rule_name == "test"
        assert r.passed is True
        assert r.message == "ok"
        assert r.details is None
        assert r.duration_ms is None

    def test_with_details(self):
        r = ValidationResult(rule_name="test", passed=False, message="fail",
                             details={"key": "val"}, duration_ms=12.5)
        assert r.details == {"key": "val"}
        assert r.duration_ms == 12.5


class TestValidationRule:
    def test_creation(self):
        rule = ValidationRule(name="my_rule", type="js", config={"script": "return true"})
        assert rule.name == "my_rule"
        assert rule.type == "js"
        assert rule.timeout == 30

    def test_defaults(self):
        rule = ValidationRule(name="r", type="cookie")
        assert rule.config == {}
        assert rule.timeout == 30


class TestLoadValidationRules:
    def test_load_valid(self, tmp_path):
        rules_file = tmp_path / "rules.json"
        rules_file.write_text(json.dumps([
            {"name": "check1", "type": "js", "config": {"script": "return true"}},
            {"name": "check2", "type": "cookie", "config": {"name": "SID"}},
        ]))
        rules = load_validation_rules(str(rules_file))
        assert len(rules) == 2
        assert rules[0].name == "check1"
        assert rules[1].type == "cookie"

    def test_load_defaults(self, tmp_path):
        rules_file = tmp_path / "rules.json"
        rules_file.write_text(json.dumps([{"name": "minimal"}]))
        rules = load_validation_rules(str(rules_file))
        assert rules[0].type == "js"
        assert rules[0].timeout == 30


class TestCreateExampleRules:
    def test_creates_rules(self):
        rules = create_example_rules()
        assert len(rules) == 4
        types = {r.type for r in rules}
        assert "js" in types
        assert "url" in types
        assert "cookie" in types
        assert "api" in types


class TestAdvancedValidator:
    def test_init(self):
        v = AdvancedValidator(proxy_port=8080)
        assert v.proxy_port == 8080
        assert v._baseline_dir.exists()

    def test_prepare_cookies(self):
        v = AdvancedValidator()
        cookies = [
            {"name": "SID", "value": "abc", "domain": ".google.com", "path": "/",
             "secure": True, "httpOnly": True, "sameSite": "lax", "expires": 1700000000},
            {"name": "NID", "value": "def", "domain": ".google.com", "sameSite": "invalid"},
        ]
        pw = v._prepare_cookies(cookies)
        assert len(pw) == 2
        assert pw[0]["sameSite"] == "Lax"
        assert pw[0]["secure"] is True
        assert pw[0]["httpOnly"] is True
        assert pw[1]["sameSite"] == "Lax"  # invalid falls back to Lax

    def test_prepare_cookies_ms_expiry(self):
        v = AdvancedValidator()
        cookies = [{"name": "X", "value": "1", "domain": ".test.com", "expires": 1700000000000}]
        pw = v._prepare_cookies(cookies)
        assert pw[0]["expires"] == 1700000000000 / 1000

    def test_get_site_url_with_cookies(self):
        v = AdvancedValidator()
        session = {"cookies": [{"domain": ".example.com"}, {"domain": "api.example.com"}]}
        url = v._get_site_url(session)
        assert url == "https://example.com"

    def test_get_site_url_no_cookies(self):
        v = AdvancedValidator()
        session = {"site_name": "google"}
        url = v._get_site_url(session)
        assert url == "https://www.google.com"

    def test_get_cookie_header(self):
        v = AdvancedValidator()
        session = {"cookies": [
            {"name": "SID", "value": "abc", "domain": ".google.com"},
            {"name": "X", "value": "1", "domain": ".other.com"},
        ]}
        header = v._get_cookie_header(session, "https://mail.google.com")
        assert "SID=abc" in header
        assert "X=1" not in header

    def test_validate_cookie_found(self):
        v = AdvancedValidator()
        session = {"cookies": [{"name": "SID", "value": "abc", "domain": ".google.com"}]}
        rule = ValidationRule(name="check_sid", type="cookie", config={"name": "SID"})
        result = v._validate_cookie(session, rule)
        assert result.passed is True

    def test_validate_cookie_not_found(self):
        v = AdvancedValidator()
        session = {"cookies": []}
        rule = ValidationRule(name="check_sid", type="cookie", config={"name": "SID"})
        result = v._validate_cookie(session, rule)
        assert result.passed is False
        assert "not found" in result.message

    def test_validate_cookie_wrong_value(self):
        v = AdvancedValidator()
        session = {"cookies": [{"name": "SID", "value": "abc", "domain": ".google.com"}]}
        rule = ValidationRule(name="check_val", type="cookie",
                              config={"name": "SID", "value": "wrong"})
        result = v._validate_cookie(session, rule)
        assert result.passed is False
        assert "wrong value" in result.message

    def test_validate_cookie_should_not_exist(self):
        v = AdvancedValidator()
        session = {"cookies": []}
        rule = ValidationRule(name="no_cookie", type="cookie",
                              config={"name": "SID", "exists": False})
        result = v._validate_cookie(session, rule)
        assert result.passed is True

    def test_validate_cookie_should_not_exist_but_found(self):
        v = AdvancedValidator()
        session = {"cookies": [{"name": "SID", "value": "abc", "domain": ".google.com"}]}
        rule = ValidationRule(name="no_cookie", type="cookie",
                              config={"name": "SID", "exists": False})
        result = v._validate_cookie(session, rule)
        assert result.passed is False

    def test_validate_cookie_no_name(self):
        v = AdvancedValidator()
        rule = ValidationRule(name="no_name", type="cookie", config={})
        result = v._validate_cookie({}, rule)
        assert result.passed is False
        assert "no cookie name" in result.message.lower()

    def test_validate_cookie_domain_filter(self):
        v = AdvancedValidator()
        session = {"cookies": [
            {"name": "SID", "value": "abc", "domain": ".google.com"},
            {"name": "SID", "value": "xyz", "domain": ".other.com"},
        ]}
        rule = ValidationRule(name="check", type="cookie",
                              config={"name": "SID", "domain": ".other.com"})
        result = v._validate_cookie(session, rule)
        assert result.passed is True
        assert result.details["value"] == "xyz"

    @pytest.mark.asyncio
    async def test_validate_rules_exception(self):
        v = AdvancedValidator()
        bad_rule = ValidationRule(name="bad", type="unknown_type")
        results = await v.validate_rules({}, [bad_rule])
        assert len(results) == 1
        assert results[0].passed is False

    @pytest.mark.asyncio
    async def test_validate_unknown_type(self):
        v = AdvancedValidator()
        rule = ValidationRule(name="mystery", type="nonexistent")
        results = await v.validate_rules({}, [rule])
        assert results[0].passed is False
        assert "unknown" in results[0].message.lower()

    @pytest.mark.asyncio
    async def test_validate_api_no_url(self):
        v = AdvancedValidator()
        rule = ValidationRule(name="api", type="api", config={})
        results = await v.validate_rules({}, [rule])
        assert results[0].passed is False
        assert "no api url" in results[0].message.lower()

    @pytest.mark.asyncio
    async def test_validate_url_no_url(self):
        v = AdvancedValidator()
        rule = ValidationRule(name="url", type="url", config={})
        results = await v.validate_rules({}, [rule])
        assert results[0].passed is False
        assert "no url" in results[0].message.lower()
