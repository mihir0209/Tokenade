"""Tests for advanced validator."""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from tokenade.core.importer.advanced_validator import (
    AdvancedValidator,
    ValidationResult,
    ValidationRule,
    load_validation_rules,
    create_example_rules,
)


class TestValidationRule:
    def test_default_rule(self):
        rule = ValidationRule(name="test", type="js")
        assert rule.name == "test"
        assert rule.type == "js"
        assert rule.config == {}
        assert rule.timeout == 30

    def test_custom_rule(self):
        rule = ValidationRule(
            name="custom",
            type="api",
            config={"url": "https://api.example.com", "status": 200},
            timeout=60,
        )
        assert rule.name == "custom"
        assert rule.type == "api"
        assert rule.config["url"] == "https://api.example.com"
        assert rule.timeout == 60


class TestValidationResult:
    def test_result_passed(self):
        result = ValidationResult(
            rule_name="test",
            passed=True,
            message="All good",
            details={"key": "value"},
            duration_ms=100.5,
        )
        assert result.passed is True
        assert result.message == "All good"
        assert result.duration_ms == 100.5

    def test_result_failed(self):
        result = ValidationResult(
            rule_name="test",
            passed=False,
            message="Failed",
        )
        assert result.passed is False


class TestAdvancedValidator:
    @pytest.fixture
    def validator(self):
        return AdvancedValidator(proxy_port=9222)

    @pytest.fixture
    def session(self):
        return {
            "version": "2.0",
            "site_name": "test_site",
            "cookies": [
                {"name": "session", "value": "abc", "domain": ".example.com", "path": "/"},
                {"name": "lang", "value": "en", "domain": ".example.com", "path": "/",
                 "secure": True, "httpOnly": True},
            ],
        }

    def test_validate_cookie_exists(self, validator, session):
        rule = ValidationRule(
            name="check_session",
            type="cookie",
            config={"name": "session", "exists": True},
        )
        result = validator._validate_cookie(session, rule)
        assert result.passed is True
        assert "session" in result.message

    def test_validate_cookie_not_exists(self, validator, session):
        rule = ValidationRule(
            name="check_missing",
            type="cookie",
            config={"name": "nonexistent", "exists": True},
        )
        result = validator._validate_cookie(session, rule)
        assert result.passed is False

    def test_validate_cookie_should_not_exist(self, validator, session):
        rule = ValidationRule(
            name="check_not_exists",
            type="cookie",
            config={"name": "nonexistent", "exists": False},
        )
        result = validator._validate_cookie(session, rule)
        assert result.passed is True

    def test_validate_cookie_with_value(self, validator, session):
        rule = ValidationRule(
            name="check_value",
            type="cookie",
            config={"name": "session", "exists": True, "value": "abc"},
        )
        result = validator._validate_cookie(session, rule)
        assert result.passed is True

    def test_validate_cookie_wrong_value(self, validator, session):
        rule = ValidationRule(
            name="check_wrong_value",
            type="cookie",
            config={"name": "session", "exists": True, "value": "wrong"},
        )
        result = validator._validate_cookie(session, rule)
        assert result.passed is False

    def test_validate_cookie_no_name(self, validator, session):
        rule = ValidationRule(
            name="no_name",
            type="cookie",
            config={"exists": True},
        )
        result = validator._validate_cookie(session, rule)
        assert result.passed is False

    def test_prepare_cookies(self, validator, session):
        pw_cookies = validator._prepare_cookies(session["cookies"])
        assert len(pw_cookies) == 2
        assert pw_cookies[0]["name"] == "session"
        assert pw_cookies[0]["value"] == "abc"
        assert pw_cookies[1]["secure"] is True
        assert pw_cookies[1]["httpOnly"] is True

    def test_get_site_url(self, validator, session):
        url = validator._get_site_url(session)
        assert url.startswith("https://")
        assert "example.com" in url

    def test_get_cookie_header(self, validator, session):
        header = validator._get_cookie_header(session, "https://example.com/page")
        assert "session=abc" in header
        assert "lang=en" in header

    def test_get_cookie_header_no_match(self, validator, session):
        header = validator._get_cookie_header(session, "https://other.com/page")
        assert header == ""

    def test_create_example_rules(self):
        rules = create_example_rules()
        assert len(rules) == 4
        assert rules[0].type == "js"
        assert rules[1].type == "url"
        assert rules[2].type == "cookie"
        assert rules[3].type == "api"


class TestLoadValidationRules:
    def test_load_rules(self, tmp_path):
        rules_data = [
            {
                "name": "test_js",
                "type": "js",
                "config": {"script": "return true"},
                "timeout": 30,
            },
            {
                "name": "test_cookie",
                "type": "cookie",
                "config": {"name": "session", "exists": True},
            },
        ]
        rules_file = tmp_path / "rules.json"
        rules_file.write_text(json.dumps(rules_data))
        
        rules = load_validation_rules(str(rules_file))
        assert len(rules) == 2
        assert rules[0].name == "test_js"
        assert rules[1].type == "cookie"


class TestAdvancedValidatorAsync:
    @pytest.fixture
    def validator(self):
        return AdvancedValidator()

    @pytest.fixture
    def session(self):
        return {
            "cookies": [
                {"name": "session", "value": "abc", "domain": ".example.com", "path": "/"},
            ],
        }

    @pytest.mark.asyncio
    async def test_validate_rules_empty(self, validator, session):
        results = await validator.validate_rules(session, [])
        assert results == []

    @pytest.mark.asyncio
    async def test_validate_rules_cookie(self, validator, session):
        rule = ValidationRule(
            name="check_session",
            type="cookie",
            config={"name": "session", "exists": True},
        )
        results = await validator.validate_rules(session, [rule])
        assert len(results) == 1
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_validate_rules_unknown_type(self, validator, session):
        rule = ValidationRule(
            name="unknown",
            type="unknown_type",
        )
        results = await validator.validate_rules(session, [rule])
        assert len(results) == 1
        assert results[0].passed is False
        assert "Unknown rule type" in results[0].message

    @pytest.mark.asyncio
    async def test_validate_rules_exception_handling(self, validator, session):
        rule = ValidationRule(
            name="failing",
            type="cookie",
            config={"name": "session", "exists": True},
        )
        with patch.object(validator, '_validate_cookie', side_effect=Exception("test error")):
            results = await validator.validate_rules(session, [rule])
            assert len(results) == 1
            assert results[0].passed is False
            assert "failed" in results[0].message.lower()
