"""
Session CI Runner — execute session validation pipelines locally.

Reads a `tokenade.yml` config and runs health checks, validation,
and optional refresh on session files. Designed for both local dev
and CI/CD pipelines (GitHub Actions, GitLab CI, etc.).

Usage:
    runner = CIRunner.from_file("tokenade.yml")
    report = runner.run()
    sys.exit(report.exit_code)
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class SessionEntry:
    """A single session to validate in CI."""
    name: str
    file: str
    domains: List[str] = field(default_factory=list)
    health_threshold: float = 70.0
    max_expired_cookies: int = 5
    refresh: bool = False
    refresh_browser: str = "chrome"
    refresh_profile: Optional[str] = None


@dataclass
class ValidateConfig:
    """Global validation settings."""
    require_critical_cookies: bool = True
    max_age_hours: int = 168


@dataclass
class FailureConfig:
    """What to do on failure."""
    action: str = "warn"  # warn | error | webhook
    webhook: Optional[str] = None


@dataclass
class OutputConfig:
    """Report output settings."""
    format: str = "text"  # text | json | junit
    path: Optional[str] = None


@dataclass
class CIConfig:
    """Full CI configuration parsed from tokenade.yml."""
    version: str = "1.0"
    sessions: List[SessionEntry] = field(default_factory=list)
    validate: ValidateConfig = field(default_factory=ValidateConfig)
    on_failure: FailureConfig = field(default_factory=FailureConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    @classmethod
    def from_file(cls, path: str = "tokenade.yml") -> "CIConfig":
        """Load and parse tokenade.yml."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config not found: {path}")

        with open(p) as f:
            raw = yaml.safe_load(f)

        if not isinstance(raw, dict):
            raise ValueError(f"Invalid config format: {path}")

        config = cls()
        config.version = str(raw.get("version", "1.0"))

        # Parse sessions
        for s in raw.get("sessions", []):
            if not isinstance(s, dict):
                raise ValueError(f"Invalid session entry: {s}")
            if "name" not in s or "file" not in s:
                raise ValueError(f"Session must have 'name' and 'file': {s}")
            config.sessions.append(SessionEntry(
                name=s["name"],
                file=s["file"],
                domains=s.get("domains", []),
                health_threshold=float(s.get("health_threshold", 70)),
                max_expired_cookies=int(s.get("max_expired_cookies", 5)),
                refresh=bool(s.get("refresh", False)),
                refresh_browser=s.get("refresh_browser", "chrome"),
                refresh_profile=s.get("refresh_profile"),
            ))

        # Parse validate section
        v = raw.get("validate", {})
        if isinstance(v, dict):
            config.validate = ValidateConfig(
                require_critical_cookies=bool(
                    v.get("require_critical_cookies", True)
                ),
                max_age_hours=int(v.get("max_age_hours", 168)),
            )

        # Parse on_failure section
        f = raw.get("on_failure", {})
        if isinstance(f, dict):
            config.on_failure = FailureConfig(
                action=f.get("action", "warn"),
                webhook=f.get("webhook"),
            )

        # Parse output section
        o = raw.get("output", {})
        if isinstance(o, dict):
            config.output = OutputConfig(
                format=o.get("format", "text"),
                path=o.get("path"),
            )

        return config

    def validate_config(self) -> List[str]:
        """Validate config and return list of errors."""
        errors = []
        if not self.sessions:
            errors.append("No sessions defined")

        seen_names = set()
        for s in self.sessions:
            if not s.name:
                errors.append("Session entry missing 'name'")
            if s.name in seen_names:
                errors.append(f"Duplicate session name: {s.name}")
            seen_names.add(s.name)
            if not s.file:
                errors.append(f"Session '{s.name}' missing 'file'")
            if s.health_threshold < 0 or s.health_threshold > 100:
                errors.append(
                    f"Session '{s.name}': health_threshold must be 0-100"
                )
            if s.max_expired_cookies < 0:
                errors.append(
                    f"Session '{s.name}': max_expired_cookies must be >= 0"
                )
            if s.refresh and not s.refresh_browser:
                errors.append(
                    f"Session '{s.name}': refresh=true but no refresh_browser"
                )

        if self.on_failure.action not in ("warn", "error", "webhook"):
            errors.append(
                f"on_failure.action must be warn|error|webhook, "
                f"got: {self.on_failure.action}"
            )

        if self.output.format not in ("text", "json", "junit"):
            errors.append(
                f"output.format must be text|json|junit, "
                f"got: {self.output.format}"
            )

        return errors


@dataclass
class SessionCIResult:
    """Result of CI check for a single session."""
    name: str
    file: str
    status: str = "pass"  # pass | fail | warn | skip | error
    health_score: float = 0.0
    cookie_count: int = 0
    expired_count: int = 0
    critical_count: int = 0
    auth_status: str = "unknown"
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    refresh_attempted: bool = False
    refresh_success: bool = False
    duration_ms: float = 0.0
    error: str = ""


@dataclass
class CIReport:
    """Aggregated CI report for all sessions."""
    overall_status: str = "pass"  # pass | fail
    session_results: List[SessionCIResult] = field(default_factory=list)
    config_path: str = ""
    duration_ms: float = 0.0

    @property
    def exit_code(self) -> int:
        return 0 if self.overall_status == "pass" else 1

    @property
    def passed(self) -> int:
        return sum(1 for r in self.session_results if r.status == "pass")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.session_results if r.status == "fail")

    @property
    def warned(self) -> int:
        return sum(1 for r in self.session_results if r.status == "warn")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.session_results if r.status == "skip")

    @property
    def errors(self) -> int:
        return sum(1 for r in self.session_results if r.status == "error")

    def to_text(self) -> str:
        """Render human-readable text report."""
        lines = [
            "=" * 60,
            "TOKENADE CI REPORT",
            "=" * 60,
            f"Config: {self.config_path}",
            f"Status: {'PASS' if self.overall_status == 'pass' else 'FAIL'}",
            f"Sessions: {self.passed} passed, {self.failed} failed, "
            f"{self.warned} warned, {self.skipped} skipped, "
            f"{self.errors} errors",
            f"Duration: {self.duration_ms / 1000:.1f}s",
            "-" * 60,
        ]

        for r in self.session_results:
            icon = {
                "pass": "✅", "fail": "❌", "warn": "⚠️",
                "skip": "⏭️", "error": "💥",
            }.get(r.status, "?")
            lines.append(
                f"  {icon} {r.name}: {r.status.upper()} "
                f"(health={r.health_score:.0f}%, "
                f"cookies={r.cookie_count}, "
                f"expired={r.expired_count})"
            )
            for issue in r.issues:
                lines.append(f"      - {issue}")
            if r.error:
                lines.append(f"      ERROR: {r.error}")
            if r.refresh_attempted:
                tag = "OK" if r.refresh_success else "FAILED"
                lines.append(f"      Refresh: {tag}")

        lines.append("=" * 60)
        return "\n".join(lines)

    def to_json(self) -> str:
        """Render JSON report."""
        data = {
            "overall_status": self.overall_status,
            "exit_code": self.exit_code,
            "passed": self.passed,
            "failed": self.failed,
            "warned": self.warned,
            "skipped": self.skipped,
            "errors_count": self.errors,
            "duration_ms": self.duration_ms,
            "config_path": self.config_path,
            "sessions": [],
        }
        for r in self.session_results:
            data["sessions"].append({
                "name": r.name,
                "file": r.file,
                "status": r.status,
                "health_score": r.health_score,
                "cookie_count": r.cookie_count,
                "expired_count": r.expired_count,
                "critical_count": r.critical_count,
                "auth_status": r.auth_status,
                "issues": r.issues,
                "warnings": r.warnings,
                "refresh_attempted": r.refresh_attempted,
                "refresh_success": r.refresh_success,
                "duration_ms": r.duration_ms,
                "error": r.error,
            })
        return json.dumps(data, indent=2)

    def to_junit(self) -> str:
        """Render JUnit XML report."""
        total = len(self.session_results)
        failures = self.failed + self.errors
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<testsuites tests="{total}" failures="{failures}">',
            f'  <testsuite name="tokenade-ci" tests="{total}" '
            f'failures="{failures}">',
        ]
        for r in self.session_results:
            lines.append(
                f'    <testcase name="{r.name}" '
                f'classname="tokenade.ci" '
                f'time="{r.duration_ms / 1000:.3f}">'
            )
            if r.status == "fail":
                msg = "; ".join(r.issues) if r.issues else r.error
                lines.append(
                    f'      <failure message="{_xml_escape(msg)}">'
                    f'{_xml_escape(r.file)}</failure>'
                )
            elif r.status == "error":
                lines.append(
                    f'      <error message="{_xml_escape(r.error)}">'
                    f'{_xml_escape(r.file)}</error>'
                )
            lines.append('    </testcase>')
        lines.append('  </testsuite>')
        lines.append('</testsuites>')
        return "\n".join(lines)


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


DEFAULT_TEMPLATE = """\
# tokenade.yml — Session CI configuration
# See: tokenade ci --help
version: "1.0"

sessions:
  - name: gmail
    file: ./sessions/gmail.tokenade
    domains: ["google.com", "accounts.google.com", "mail.google.com"]
    health_threshold: 70
    max_expired_cookies: 5
    refresh: false

  # - name: github
  #   file: ./sessions/github.tokenade
  #   domains: ["github.com"]
  #   health_threshold: 80
  #   refresh: false

validate:
  require_critical_cookies: true
  max_age_hours: 168

on_failure:
  action: warn   # warn | error | webhook
  # webhook: ${SESSION_WEBHOOK_URL}

output:
  format: text   # text | json | junit
  # path: ./tokenade-ci-report.json
"""


class CIRunner:
    """Executes a CI pipeline defined by CIConfig."""

    def __init__(self, config: CIConfig, base_dir: str = "."):
        self.config = config
        self.base_dir = base_dir

    @classmethod
    def from_file(
        cls, path: str = "tokenade.yml", base_dir: str = "."
    ) -> "CIRunner":
        """Create runner from config file."""
        config = CIConfig.from_file(path)
        return cls(config, base_dir)

    def run(self) -> CIReport:
        """Execute the CI pipeline."""
        # perf_counter (not wall-clock time): highest resolution and
        # immune to clock adjustments; wall time can read 0.0 elapsed
        # on coarse-timer platforms (Windows).
        start = time.perf_counter()
        report = CIReport(config_path=self.base_dir)
        report.session_results = []

        for entry in self.config.sessions:
            result = self._run_session(entry)
            report.session_results.append(result)

        # Determine overall status
        has_fail = any(
            r.status in ("fail", "error") for r in report.session_results
        )
        has_warn = any(
            r.status == "warn" for r in report.session_results
        )

        if has_fail:
            report.overall_status = "fail"
        elif has_warn and self.config.on_failure.action == "error":
            report.overall_status = "fail"
        else:
            report.overall_status = "pass"

        report.duration_ms = (time.perf_counter() - start) * 1000
        return report

    def _run_session(self, entry: SessionEntry) -> SessionCIResult:
        """Run CI checks on a single session."""
        start = time.perf_counter()
        result = SessionCIResult(name=entry.name, file=entry.file)

        # Resolve file path
        session_path = os.path.join(self.base_dir, entry.file)
        if not os.path.exists(session_path):
            session_path = entry.file

        if not os.path.exists(session_path):
            result.status = "error"
            result.error = f"File not found: {entry.file}"
            result.duration_ms = (time.perf_counter() - start) * 1000
            return result

        # Health check
        try:
            from tokenade.core.refresh.health_checker import (
                SessionHealthChecker,
            )
            checker = SessionHealthChecker()
            health = checker.check_session(session_path)

            result.health_score = health.health_score * 100
            result.issues = list(health.issues)
        except Exception as e:
            result.status = "error"
            result.error = f"Health check failed: {e}"
            result.duration_ms = (time.perf_counter() - start) * 1000
            return result

        # Load session for details
        try:
            with open(session_path) as f:
                session = json.load(f)
            cookies = session.get("cookies", [])
            result.cookie_count = len(cookies)
            result.auth_status = session.get("auth_status", "unknown")

            # Count expired
            now = time.time()
            for c in cookies:
                exp = c.get("expires", 0)
                if exp and int(exp) > 0:
                    exp_int = int(exp)
                    if exp_int > 1262304000000:
                        exp_int = exp_int // 1000
                    if exp_int < now:
                        result.expired_count += 1

            # Count critical cookies
            from tokenade.core.importer.cookie_extractor import (
                SITE_DETECTION,
            )
            site_name = session.get("site_name", "")
            if site_name and site_name in SITE_DETECTION:
                crit_names = SITE_DETECTION[site_name].get(
                    "critical_cookies", []
                )
                cookie_names = {c.get("name", "") for c in cookies}
                result.critical_count = sum(
                    1 for cn in crit_names if cn in cookie_names
                )
        except Exception:
            pass

        # Apply thresholds
        if result.health_score < entry.health_threshold:
            result.status = "fail"
            result.issues.append(
                f"Health {result.health_score:.0f}% < "
                f"threshold {entry.health_threshold:.0f}%"
            )

        if result.expired_count > entry.max_expired_cookies:
            if result.status != "fail":
                result.status = "fail"
            result.issues.append(
                f"Expired cookies {result.expired_count} > "
                f"max {entry.max_expired_cookies}"
            )

        # Check max age
        try:
            created = session.get("created_at", "")
            if created:
                from datetime import datetime
                created_dt = datetime.fromisoformat(
                    created.replace("Z", "+00:00")
                )
                age_hours = (
                    datetime.now(created_dt.tzinfo) - created_dt
                ).total_seconds() / 3600
                if age_hours > self.config.validate.max_age_hours:
                    if result.status != "fail":
                        result.status = "fail"
                    result.issues.append(
                        f"Session age {age_hours:.0f}h > "
                        f"max {self.config.validate.max_age_hours}h"
                    )
        except Exception:
            pass

        # Attempt refresh if requested and unhealthy
        if entry.refresh and result.status == "fail":
            result.refresh_attempted = True
            try:
                from tokenade.core.refresh.health_checker import (
                    SessionRefresher,
                )
                refresher = SessionRefresher()
                refresh_result = refresher.refresh(
                    session_file=session_path,
                    source_browser=entry.refresh_browser,
                    source_profile=entry.refresh_profile,
                )
                result.refresh_success = refresh_result.success
                if refresh_result.success:
                    result.issues.append(
                        f"Refreshed: {refresh_result.cookies_refreshed} cookies"
                    )
            except Exception as e:
                result.refresh_success = False
                result.issues.append(f"Refresh failed: {e}")

        # If no fail, mark pass or warn
        if result.status not in ("fail", "error"):
            if result.issues:
                result.status = "warn"
                result.warnings = list(result.issues)
            else:
                result.status = "pass"

        result.duration_ms = (time.perf_counter() - start) * 1000
        return result
