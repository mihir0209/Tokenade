"""
Batch Health Reporting API.

Provides consolidated health reports for CI/CD pipelines, batch operations,
and webhook notifications. Combines SessionHealthChecker, SessionHealthScorer,
and SessionValidator into a unified reporting interface.

Usage:
    # CLI
    tokenade health-report --sessions-dir sessions/
    tokenade health-report --session gmail.tokenade --json
    tokenade health-report --sessions-dir sessions/ --webhook https://hooks.slack.com/...

    # Python
    from tokenade.core.refresh.health_reporter import HealthReporter
    reporter = HealthReporter()
    report = reporter.generate_report(sessions_dir="sessions/")
    print(report.to_json())
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)


@dataclass
class SessionReport:
    """Health report for a single session."""
    session_file: str
    site_name: str
    healthy: bool
    health_score: float  # 0-1 (simple) from SessionHealthChecker
    owasp_score: float  # 0-100 from SessionHealthScorer
    cookie_count: int
    expired_cookies: int
    expiring_soon: int
    valid_cookies: int
    auth_status: str
    expires_in: Optional[int] = None  # seconds
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    last_checked: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "session_file": self.session_file,
            "site_name": self.site_name,
            "healthy": self.healthy,
            "health_score": self.health_score,
            "owasp_score": self.owasp_score,
            "cookie_count": self.cookie_count,
            "expired_cookies": self.expired_cookies,
            "expiring_soon": self.expiring_soon,
            "valid_cookies": self.valid_cookies,
            "auth_status": self.auth_status,
            "expires_in": self.expires_in,
            "issues": self.issues,
            "recommendations": self.recommendations,
            "last_checked": self.last_checked,
        }


@dataclass
class HealthReport:
    """Consolidated health report for multiple sessions."""
    sessions: List[SessionReport] = field(default_factory=list)
    total_sessions: int = 0
    healthy_sessions: int = 0
    unhealthy_sessions: int = 0
    overall_health_score: float = 0.0  # 0-1 average
    overall_owasp_score: float = 0.0  # 0-100 average
    total_cookies: int = 0
    total_expired: int = 0
    generated_at: Optional[str] = None
    exit_code: int = 0  # 0=healthy, 1=unhealthy, 2=mixed

    def to_dict(self) -> Dict:
        return {
            "total_sessions": self.total_sessions,
            "healthy_sessions": self.healthy_sessions,
            "unhealthy_sessions": self.unhealthy_sessions,
            "overall_health_score": round(self.overall_health_score, 3),
            "overall_owasp_score": round(self.overall_owasp_score, 1),
            "total_cookies": self.total_cookies,
            "total_expired": self.total_expired,
            "exit_code": self.exit_code,
            "generated_at": self.generated_at,
            "sessions": [s.to_dict() for s in self.sessions],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def summary(self) -> str:
        """Human-readable summary."""
        lines = []
        lines.append("=" * 70)
        lines.append("TOKENADE HEALTH REPORT")
        lines.append("=" * 70)
        lines.append(f"Generated: {self.generated_at}")
        lines.append(f"Sessions: {self.total_sessions} total, {self.healthy_sessions} healthy, {self.unhealthy_sessions} unhealthy")
        lines.append(f"Cookies: {self.total_cookies} total, {self.total_expired} expired")
        lines.append(f"Health Score: {self.overall_health_score:.1%}")
        lines.append(f"OWASP Score: {self.overall_owasp_score:.1f}/100")

        if self.exit_code == 0:
            lines.append(f"Status: ALL HEALTHY")
        elif self.exit_code == 1:
            lines.append(f"Status: UNHEALTHY SESSIONS DETECTED")
        else:
            lines.append(f"Status: MIXED (some healthy, some unhealthy)")

        lines.append("")
        lines.append("-" * 70)

        for s in self.sessions:
            icon = "✅" if s.healthy else "❌"
            lines.append(f"  {icon} {s.site_name:<20} {s.cookie_count:>4} cookies  health={s.health_score:.0%}  owasp={s.owasp_score:.0f}/100")
            if s.expired_cookies > 0:
                lines.append(f"     ⚠️  {s.expired_cookies} expired, {s.expiring_soon} expiring soon")
            if s.auth_status and s.auth_status != "logged_in":
                lines.append(f"     ⚠️  Auth: {s.auth_status}")
            for issue in s.issues[:3]:
                lines.append(f"     • {issue}")

        lines.append("=" * 70)

        if self.exit_code == 0:
            lines.append("✅ All sessions healthy — safe to proceed")
        elif self.exit_code == 1:
            lines.append("❌ Unhealthy sessions detected — review before deploying")
        else:
            lines.append("⚠️  Mixed results — some sessions need attention")

        return "\n".join(lines)


class HealthReporter:
    """
    Batch health reporter for CI/CD and operational use.

    Usage:
        reporter = HealthReporter()

        # Report on a directory
        report = reporter.generate_report(sessions_dir="sessions/")

        # Report on specific files
        report = reporter.generate_report(session_files=["a.tokenade", "b.tokenade"])

        # Send to webhook
        reporter.send_webhook(report, "https://hooks.slack.com/...")
    """

    def __init__(self, min_health: float = 0.5, max_expired: int = 0):
        """
        Initialize the health reporter.

        Args:
            min_health: Minimum health score threshold (0.0-1.0)
            max_expired: Maximum allowed expired cookies per session
        """
        self.min_health = min_health
        self.max_expired = max_expired

    def generate_report(
        self,
        sessions_dir: Optional[str] = None,
        session_files: Optional[List[str]] = None,
    ) -> HealthReport:
        """
        Generate a consolidated health report.

        Args:
            sessions_dir: Directory containing .tokenade files
            session_files: Specific session files to check

        Returns:
            HealthReport with all session details
        """
        from tokenade.core.refresh.health_checker import SessionHealthChecker
        from tokenade.core.refresh.health_scorer import SessionHealthScorer

        checker = SessionHealthChecker()
        scorer = SessionHealthScorer()

        # Discover session files
        files = []
        if session_files:
            files = session_files
        elif sessions_dir:
            sessions_path = Path(sessions_dir)
            if sessions_path.exists():
                files = sorted([str(f) for f in sessions_path.glob("*.tokenade")])
                files += sorted([str(f) for f in sessions_path.glob("*.session")])

        report = HealthReport(
            total_sessions=len(files),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        for session_file in files:
            session_report = self._check_single_session(
                session_file, checker, scorer
            )
            report.sessions.append(session_report)

            report.total_cookies += session_report.cookie_count
            report.total_expired += session_report.expired_cookies

            if session_report.healthy:
                report.healthy_sessions += 1
            else:
                report.unhealthy_sessions += 1

        # Calculate overall scores
        if report.sessions:
            report.overall_health_score = (
                sum(s.health_score for s in report.sessions) / len(report.sessions)
            )
            report.overall_owasp_score = (
                sum(s.owasp_score for s in report.sessions) / len(report.sessions)
            )

        # Determine exit code
        if report.unhealthy_sessions == 0:
            report.exit_code = 0  # all healthy
        elif report.healthy_sessions == 0:
            report.exit_code = 1  # all unhealthy
        else:
            report.exit_code = 2  # mixed

        return report

    def _check_single_session(
        self,
        session_file: str,
        checker,
        scorer,
    ) -> SessionReport:
        """Check a single session and return a SessionReport."""
        try:
            with open(session_file) as f:
                session = json.load(f)
        except Exception as e:
            return SessionReport(
                session_file=session_file,
                site_name="unknown",
                healthy=False,
                health_score=0.0,
                owasp_score=0.0,
                cookie_count=0,
                expired_cookies=0,
                expiring_soon=0,
                valid_cookies=0,
                auth_status="error",
                issues=[f"Failed to read session: {e}"],
                last_checked=datetime.now(timezone.utc).isoformat(),
            )

        cookies = session.get("cookies", [])
        site_name = session.get("site_name", "unknown")
        auth_status = session.get("auth_status", "unknown")

        # Simple health check
        health = checker.check_session(session_file)

        # OWASP scoring
        owasp = scorer.score(session)

        # Count cookie states
        now = time.time()
        expired = 0
        expiring_soon = 0
        valid = 0
        for c in cookies:
            expires = c.get("expires", 0)
            if not expires or int(expires) <= 0:
                valid += 1
            else:
                exp = int(expires)
                if exp > 1262304000000:
                    exp = exp // 1000
                if exp < now:
                    expired += 1
                elif exp < now + 86400:
                    expiring_soon += 1
                else:
                    valid += 1

        # Combine issues from both checkers
        all_issues = list(health.issues)
        all_recommendations = list(health.recommendations)

        # Add OWASP-specific issues
        for issue in owasp.issues:
            if issue not in all_issues:
                all_issues.append(issue)
        for rec in owasp.recommendations:
            if rec not in all_recommendations:
                all_recommendations.append(rec)

        # Apply thresholds
        is_healthy = (
            health.health_score >= self.min_health
            and expired <= self.max_expired
        )

        return SessionReport(
            session_file=session_file,
            site_name=site_name,
            healthy=is_healthy,
            health_score=health.health_score,
            owasp_score=owasp.total_score,
            cookie_count=len(cookies),
            expired_cookies=expired,
            expiring_soon=expiring_soon,
            valid_cookies=valid,
            auth_status=auth_status,
            expires_in=health.expires_in,
            issues=all_issues,
            recommendations=all_recommendations,
            last_checked=datetime.now(timezone.utc).isoformat(),
        )

    def send_webhook(self, report: HealthReport, webhook_url: str) -> bool:
        """
        Send health report to a webhook (Slack, Discord, custom).

        Args:
            report: HealthReport to send
            webhook_url: Webhook URL

        Returns:
            True if sent successfully
        """
        if not webhook_url:
            logger.warning("No webhook URL provided")
            return False

        try:
            # Build payload (Slack-compatible format)
            status_emoji = "✅" if report.exit_code == 0 else "❌" if report.exit_code == 1 else "⚠️"
            text = (
                f"{status_emoji} *Tokenade Health Report*\n"
                f"Sessions: {report.healthy_sessions}/{report.total_sessions} healthy\n"
                f"Health: {report.overall_health_score:.0%} | OWASP: {report.overall_owasp_score:.0f}/100\n"
                f"Cookies: {report.total_cookies} total, {report.total_expired} expired\n"
                f"Status: {'ALL HEALTHY' if report.exit_code == 0 else 'UNHEALTHY' if report.exit_code == 1 else 'MIXED'}"
            )

            payload = json.dumps({"text": text}).encode("utf-8")

            req = Request(
                webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urlopen(req, timeout=10) as resp:
                status = resp.status
                logger.info(f"Webhook sent: {status}")
                return 200 <= status < 300

        except URLError as e:
            logger.error(f"Webhook failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return False
