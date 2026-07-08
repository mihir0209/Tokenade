"""Tests for Phase 55 — Session CI Runner."""

import json
import os
from pathlib import Path

import pytest
import yaml

from tokenade.core.cicd.runner import (
    CIConfig,
    CIRunner,
    CIReport,
    SessionCIResult,
    SessionEntry,
    DEFAULT_TEMPLATE,
)


# ─── Helper ─────────────────────────────────────────────────

def _make_session(tmp_path, name="test", site="github", auth="logged_in",
                  cookie_count=5, expired=0):
    """Create a minimal .tokenade session file."""
    import time
    cookies = []
    now = int(time.time())
    for i in range(cookie_count):
        if i < expired:
            exp = now - 3600  # expired 1 hour ago
        else:
            exp = now + 86400 * 30  # expires in 30 days
        cookies.append({
            "name": f"cookie_{i}",
            "value": f"val_{i}",
            "domain": ".example.com",
            "path": "/",
            "expires": exp,
            "secure": True,
            "httpOnly": False,
        })

    from datetime import datetime, timezone
    session = {
        "version": "2.0",
        "site_name": site,
        "auth_status": auth,
        # Recent timestamp so max_age_hours (default 168) does not fail over time
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cookies": cookies,
    }
    path = tmp_path / f"{name}.tokenade"
    path.write_text(json.dumps(session))
    return str(path)


def _make_config(tmp_path, sessions, **kwargs):
    """Create a tokenade.yml config file."""
    config = {
        "version": "1.0",
        "sessions": sessions,
    }
    config.update(kwargs)
    path = tmp_path / "tokenade.yml"
    path.write_text(yaml.dump(config))
    return str(path)


# ─── SessionEntry Tests ────────────────────────────────────

class TestSessionEntry:
    def test_defaults(self):
        e = SessionEntry(name="test", file="test.tokenade")
        assert e.name == "test"
        assert e.health_threshold == 70.0
        assert e.max_expired_cookies == 5
        assert e.refresh is False
        assert e.refresh_browser == "chrome"

    def test_custom_values(self):
        e = SessionEntry(
            name="g", file="g.tokenade",
            domains=["google.com"],
            health_threshold=90,
            max_expired_cookies=2,
            refresh=True,
            refresh_browser="brave",
        )
        assert e.health_threshold == 90
        assert e.refresh is True
        assert e.refresh_browser == "brave"


# ─── CIConfig Tests ────────────────────────────────────────

class TestCIConfig:
    def test_from_file_basic(self, tmp_path):
        cfg_path = _make_config(tmp_path, [
            {"name": "gh", "file": "gh.tokenade"},
        ])
        config = CIConfig.from_file(cfg_path)
        assert config.version == "1.0"
        assert len(config.sessions) == 1
        assert config.sessions[0].name == "gh"

    def test_from_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            CIConfig.from_file("/nonexistent/tokenade.yml")

    def test_from_file_invalid_yaml(self, tmp_path):
        p = tmp_path / "bad.yml"
        p.write_text("not: [valid: yaml: {}")
        with pytest.raises(Exception):
            CIConfig.from_file(str(p))

    def test_from_file_missing_name(self, tmp_path):
        cfg_path = _make_config(tmp_path, [{"file": "x.tokenade"}])
        with pytest.raises(ValueError, match="name.*file"):
            CIConfig.from_file(cfg_path)

    def test_from_file_missing_sessions(self, tmp_path):
        p = tmp_path / "empty.yml"
        p.write_text(yaml.dump({"version": "1.0"}))
        config = CIConfig.from_file(str(p))
        errors = config.validate_config()
        assert any("No sessions" in e for e in errors)

    def test_from_file_all_fields(self, tmp_path):
        cfg_path = _make_config(tmp_path, [
            {
                "name": "gmail",
                "file": "gmail.tokenade",
                "domains": ["google.com"],
                "health_threshold": 80,
                "max_expired_cookies": 3,
                "refresh": True,
                "refresh_browser": "brave",
            },
        ], **{
            "validate": {"require_critical_cookies": False, "max_age_hours": 72},
            "on_failure": {"action": "error"},
            "output": {"format": "json", "path": "report.json"},
        })
        config = CIConfig.from_file(cfg_path)
        assert config.sessions[0].health_threshold == 80
        assert config.validate.max_age_hours == 72
        assert config.on_failure.action == "error"
        assert config.output.format == "json"

    def test_validate_config_valid(self, tmp_path):
        cfg_path = _make_config(tmp_path, [
            {"name": "gh", "file": "gh.tokenade"},
        ])
        config = CIConfig.from_file(cfg_path)
        assert config.validate_config() == []

    def test_validate_config_duplicate_names(self, tmp_path):
        cfg_path = _make_config(tmp_path, [
            {"name": "gh", "file": "a.tokenade"},
            {"name": "gh", "file": "b.tokenade"},
        ])
        config = CIConfig.from_file(cfg_path)
        errors = config.validate_config()
        assert any("Duplicate" in e for e in errors)

    def test_validate_config_bad_threshold(self, tmp_path):
        cfg_path = _make_config(tmp_path, [
            {"name": "x", "file": "x.tokenade", "health_threshold": 150},
        ])
        config = CIConfig.from_file(cfg_path)
        errors = config.validate_config()
        assert any("health_threshold" in e for e in errors)

    def test_validate_config_bad_failure_action(self, tmp_path):
        cfg_path = _make_config(tmp_path, [
            {"name": "x", "file": "x.tokenade"},
        ], **{"on_failure": {"action": "invalid"}})
        config = CIConfig.from_file(cfg_path)
        errors = config.validate_config()
        assert any("on_failure" in e for e in errors)

    def test_validate_config_bad_output_format(self, tmp_path):
        cfg_path = _make_config(tmp_path, [
            {"name": "x", "file": "x.tokenade"},
        ], **{"output": {"format": "xml"}})
        config = CIConfig.from_file(cfg_path)
        errors = config.validate_config()
        assert any("output.format" in e for e in errors)


# ─── CIRunner Tests ────────────────────────────────────────

class TestCIRunner:
    def test_run_healthy_session(self, tmp_path):
        session_path = _make_session(tmp_path, "gh", cookie_count=10, expired=0)
        cfg_path = _make_config(tmp_path, [
            {"name": "gh", "file": session_path, "health_threshold": 50},
        ])
        config = CIConfig.from_file(cfg_path)
        runner = CIRunner(config)
        report = runner.run()

        assert report.overall_status == "pass"
        assert report.passed == 1
        assert report.failed == 0
        assert report.session_results[0].status == "pass"
        assert report.session_results[0].cookie_count == 10

    def test_run_unhealthy_session(self, tmp_path):
        session_path = _make_session(tmp_path, "gh", cookie_count=5, expired=4)
        cfg_path = _make_config(tmp_path, [
            {"name": "gh", "file": session_path, "health_threshold": 80,
             "max_expired_cookies": 2},
        ])
        config = CIConfig.from_file(cfg_path)
        runner = CIRunner(config)
        report = runner.run()

        assert report.overall_status == "fail"
        assert report.failed == 1
        assert report.session_results[0].status == "fail"
        assert report.session_results[0].expired_count == 4

    def test_run_file_not_found(self, tmp_path):
        cfg_path = _make_config(tmp_path, [
            {"name": "missing", "file": "/nonexistent/x.tokenade"},
        ])
        config = CIConfig.from_file(cfg_path)
        runner = CIRunner(config)
        report = runner.run()

        assert report.overall_status == "fail"
        assert report.session_results[0].status == "error"
        assert "not found" in report.session_results[0].error

    def test_run_multiple_sessions(self, tmp_path):
        s1 = _make_session(tmp_path, "gh", cookie_count=10, expired=0)
        s2 = _make_session(tmp_path, "gmail", cookie_count=5, expired=3)
        cfg_path = _make_config(tmp_path, [
            {"name": "gh", "file": s1, "health_threshold": 50},
            {"name": "gmail", "file": s2, "health_threshold": 80,
             "max_expired_cookies": 1},
        ])
        config = CIConfig.from_file(cfg_path)
        runner = CIRunner(config)
        report = runner.run()

        assert len(report.session_results) == 2
        assert report.passed == 1
        assert report.failed == 1

    def test_run_with_auth_status(self, tmp_path):
        session_path = _make_session(tmp_path, "gh", auth="session_expired")
        cfg_path = _make_config(tmp_path, [
            {"name": "gh", "file": session_path},
        ])
        config = CIConfig.from_file(cfg_path)
        runner = CIRunner(config)
        report = runner.run()

        assert report.session_results[0].auth_status == "session_expired"

    def test_from_file(self, tmp_path):
        session_path = _make_session(tmp_path, "gh")
        cfg_path = _make_config(tmp_path, [
            {"name": "gh", "file": session_path},
        ])
        runner = CIRunner.from_file(cfg_path)
        report = runner.run()
        assert report.overall_status == "pass"


# ─── CIReport Tests ────────────────────────────────────────

class TestCIReport:
    def test_empty_report(self):
        report = CIReport()
        assert report.exit_code == 0
        assert report.passed == 0
        assert report.failed == 0

    def test_pass_status(self):
        report = CIReport(
            overall_status="pass",
            session_results=[
                SessionCIResult(name="x", file="x", status="pass"),
            ],
        )
        assert report.exit_code == 0
        assert report.passed == 1

    def test_fail_status(self):
        report = CIReport(
            overall_status="fail",
            session_results=[
                SessionCIResult(name="x", file="x", status="fail"),
            ],
        )
        assert report.exit_code == 1
        assert report.failed == 1

    def test_to_text(self):
        report = CIReport(
            overall_status="pass",
            session_results=[
                SessionCIResult(
                    name="gh", file="gh.tokenade",
                    status="pass", health_score=95.0,
                    cookie_count=10, expired_count=0,
                ),
            ],
        )
        text = report.to_text()
        assert "TOKENADE CI REPORT" in text
        assert "PASS" in text
        assert "gh" in text

    def test_to_json(self):
        report = CIReport(
            overall_status="fail",
            session_results=[
                SessionCIResult(
                    name="gh", file="gh.tokenade",
                    status="fail", health_score=30.0,
                    cookie_count=5, expired_count=4,
                    issues=["Health 30% < threshold 80%"],
                ),
            ],
        )
        j = json.loads(report.to_json())
        assert j["overall_status"] == "fail"
        assert j["sessions"][0]["name"] == "gh"
        assert j["sessions"][0]["expired_count"] == 4

    def test_to_junit(self):
        report = CIReport(
            overall_status="fail",
            session_results=[
                SessionCIResult(
                    name="gh", file="gh.tokenade",
                    status="fail", issues=["expired"],
                ),
                SessionCIResult(
                    name="ok", file="ok.tokenade",
                    status="pass",
                ),
            ],
        )
        xml = report.to_junit()
        assert '<?xml' in xml
        assert 'tests="2"' in xml
        assert 'failures="1"' in xml
        assert 'name="gh"' in xml
        assert 'name="ok"' in xml

    def test_to_junit_error(self):
        report = CIReport(
            overall_status="fail",
            session_results=[
                SessionCIResult(
                    name="x", file="x.tokenade",
                    status="error", error="not found",
                ),
            ],
        )
        xml = report.to_junit()
        assert "<error" in xml

    def test_warned_count(self):
        report = CIReport(
            session_results=[
                SessionCIResult(name="a", file="a", status="warn"),
                SessionCIResult(name="b", file="b", status="pass"),
            ],
        )
        assert report.warned == 1

    def test_skipped_count(self):
        report = CIReport(
            session_results=[
                SessionCIResult(name="a", file="a", status="skip"),
            ],
        )
        assert report.skipped == 1


# ─── DEFAULT_TEMPLATE Tests ────────────────────────────────

class TestDefaultTemplate:
    def test_template_is_valid_yaml(self):
        data = yaml.safe_load(DEFAULT_TEMPLATE)
        assert "sessions" in data
        assert "version" in data

    def test_template_has_sessions(self):
        data = yaml.safe_load(DEFAULT_TEMPLATE)
        assert len(data["sessions"]) >= 1

    def test_template_has_validate(self):
        data = yaml.safe_load(DEFAULT_TEMPLATE)
        assert "validate" in data

    def test_template_has_output(self):
        data = yaml.safe_load(DEFAULT_TEMPLATE)
        assert "output" in data


# ─── CLI Parser Tests ──────────────────────────────────────

class TestCLIParser:
    def test_ci_run_parser(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["ci", "run"])
        assert a.ci_action == "run"
        assert a.config == "tokenade.yml"

    def test_ci_run_custom_config(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["ci", "run", "--config", "my.yml"])
        assert a.config == "my.yml"

    def test_ci_run_format_override(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["ci", "run", "--format", "json"])
        assert a.format == "json"

    def test_ci_init_parser(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["ci", "init"])
        assert a.ci_action == "init"

    def test_ci_validate_parser(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["ci", "validate"])
        assert a.ci_action == "validate"

    def test_ci_lint_parser(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["ci", "lint"])
        assert a.ci_action == "lint"

    def test_ci_help(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        with pytest.raises(SystemExit):
            p.parse_args(["ci", "--help"])


# ─── Integration: Full Pipeline ────────────────────────────

class TestIntegration:
    def test_full_pipeline(self, tmp_path):
        """Test a full CI pipeline with mixed results."""
        s1 = _make_session(tmp_path, "gh", cookie_count=10, expired=0)
        s2 = _make_session(tmp_path, "gmail", cookie_count=8, expired=6)
        s3 = tmp_path / "missing.tokenade"
        cfg_path = _make_config(tmp_path, [
            {"name": "gh", "file": s1, "health_threshold": 50},
            {"name": "gmail", "file": s2, "health_threshold": 80,
             "max_expired_cookies": 2},
            {"name": "missing", "file": str(s3)},
        ], **{
            "on_failure": {"action": "warn"},
            "output": {"format": "json"},
        })
        config = CIConfig.from_file(cfg_path)
        runner = CIRunner(config)
        report = runner.run()

        assert len(report.session_results) == 3
        assert report.passed == 1
        assert report.failed == 1
        assert report.errors == 1
        assert report.overall_status == "fail"
        assert report.duration_ms > 0

        # JSON output should be valid
        j = json.loads(report.to_json())
        assert len(j["sessions"]) == 3

    def test_pipeline_with_warn(self, tmp_path):
        """Session with issues but above threshold = warn."""
        session_path = _make_session(tmp_path, "x", cookie_count=5, expired=1)
        cfg_path = _make_config(tmp_path, [
            {"name": "x", "file": session_path, "health_threshold": 50,
             "max_expired_cookies": 5},
        ])
        config = CIConfig.from_file(cfg_path)
        runner = CIRunner(config)
        report = runner.run()

        # Has 1 expired cookie (issue) but below threshold
        # So it should be warn or pass depending on logic
        assert report.session_results[0].status in ("pass", "warn")
