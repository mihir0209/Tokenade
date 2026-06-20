"""Tests for session validator."""
import json
import time
import pytest
from pathlib import Path

from tokenade.core.refresh.session_validator import (
    SessionValidator,
    ValidationResult,
    ValidationRule,
    create_ci_validation_rules,
)


class TestValidationRule:
    def test_rule_creation(self):
        rule = ValidationRule(
            name="test",
            check="min_health",
            value=0.8,
            description="Test rule",
        )
        assert rule.name == "test"
        assert rule.check == "min_health"
        assert rule.value == 0.8


class TestSessionValidator:
    def test_validate_valid_session(self, tmp_path):
        session_file = tmp_path / "valid.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [
                {"name": "session", "value": "abc", "domain": ".google.com", "expires": time.time() + 86400},
            ],
            "tokens": [],
            "metadata": {},
        }
        session_file.write_text(json.dumps(session_data))

        validator = SessionValidator()
        result = validator.validate(str(session_file))

        assert result.valid
        assert result.rules_passed == result.rules_total

    def test_validate_no_cookies(self, tmp_path):
        session_file = tmp_path / "empty.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "google",
            "auth_status": "logged_out",
            "cookies": [],
            "tokens": [],
            "metadata": {},
        }
        session_file.write_text(json.dumps(session_data))

        validator = SessionValidator()
        result = validator.validate(str(session_file))

        assert not result.valid
        assert len(result.errors) > 0

    def test_validate_expired_cookies(self, tmp_path):
        session_file = tmp_path / "expired.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [
                {"name": "session", "value": "abc", "domain": ".google.com", "expires": time.time() - 100},
            ],
            "tokens": [],
            "metadata": {},
        }
        session_file.write_text(json.dumps(session_data))

        validator = SessionValidator()
        rules = [ValidationRule("no_expired", "max_expired", 0)]
        result = validator.validate(str(session_file), rules)

        assert not result.valid

    def test_validate_file_not_found(self):
        validator = SessionValidator()
        result = validator.validate("/nonexistent/file.tokenade")

        assert not result.valid
        assert "File not found" in result.errors[0]

    def test_validate_require_oauth(self, tmp_path):
        session_file = tmp_path / "no_oauth.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [{"name": "c", "value": "v"}],
            "tokens": [],
            "oauth_config": None,
            "metadata": {},
        }
        session_file.write_text(json.dumps(session_data))

        validator = SessionValidator()
        rules = [ValidationRule("require_oauth", "require_oauth")]
        result = validator.validate(str(session_file), rules)

        assert not result.valid

    def test_validate_with_oauth(self, tmp_path):
        session_file = tmp_path / "with_oauth.tokenade"
        session_data = {
            "version": "2.0",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [{"name": "c", "value": "v"}],
            "tokens": [],
            "oauth_config": {"token_endpoint": "https://example.com/token", "client_id": "test"},
            "metadata": {},
        }
        session_file.write_text(json.dumps(session_data))

        validator = SessionValidator()
        rules = [ValidationRule("require_oauth", "require_oauth")]
        result = validator.validate(str(session_file), rules)

        assert result.valid

    def test_validate_directory(self, tmp_path):
        for name in ["a.tokenade", "b.tokenade", "c.txt"]:
            session_data = {
                "version": "2.0",
                "site_name": "test",
                "auth_status": "logged_in",
                "cookies": [{"name": "c", "value": "v"}],
                "metadata": {},
            }
            (tmp_path / name).write_text(json.dumps(session_data))

        validator = SessionValidator()
        results = validator.validate_directory(str(tmp_path))

        assert len(results) == 2

    def test_ci_report(self):
        results = [
            ValidationResult(
                valid=True,
                session_file="a.tokenade",
                rules_passed=3,
                rules_total=3,
            ),
            ValidationResult(
                valid=False,
                session_file="b.tokenade",
                rules_passed=1,
                rules_total=3,
                errors=["Rule failed"],
            ),
        ]

        validator = SessionValidator()
        report = validator.ci_report(results)

        assert "1/2 passed" in report
        assert "PASS" in report
        assert "FAIL" in report

    def test_validate_max_age(self, tmp_path):
        session_file = tmp_path / "old.tokenade"
        session_data = {
            "version": "2.0",
            "created_at": "2020-01-01T00:00:00Z",
            "site_name": "google",
            "auth_status": "logged_in",
            "cookies": [{"name": "c", "value": "v"}],
            "metadata": {},
        }
        session_file.write_text(json.dumps(session_data))

        validator = SessionValidator()
        rules = [ValidationRule("max_age", "max_age_hours", 24)]
        result = validator.validate(str(session_file), rules)

        assert not result.valid


class TestCreateCIValidationRules:
    def test_default_rules(self):
        rules = create_ci_validation_rules()
        assert len(rules) == 3

    def test_with_oauth(self):
        rules = create_ci_validation_rules(require_oauth=True)
        assert len(rules) == 4
        assert any(r.check == "require_oauth" for r in rules)

    def test_with_max_age(self):
        rules = create_ci_validation_rules(max_age_hours=12)
        assert len(rules) == 4
        assert any(r.check == "max_age_hours" for r in rules)
