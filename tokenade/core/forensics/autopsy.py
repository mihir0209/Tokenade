"""
Session Forensics — root-cause analysis for dead/expired sessions.

Analyzes a .tokenade session file and determines WHY it died:
- Natural cookie expiry
- Server-side revocation
- Missing critical cookies
- Incomplete extraction
- Session age

Usage:
    autopsy = SessionAutopsy("dead_session.tokenade")
    report = autopsy.analyze()
    print(report.to_text())
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from tokenade.core.importer.cookie_extractor import SITE_DETECTION

logger = logging.getLogger(__name__)


@dataclass
class CookieEvidence:
    """Evidence about a single cookie's status."""
    name: str
    domain: str
    status: str  # "expired" | "expiring_soon" | "valid" | "session"
    expires_at: str  # ISO timestamp or "session"
    age_hours: float = 0.0
    is_critical: bool = False
    probable_cause: str = ""


@dataclass
class AutopsyReport:
    """Full forensic analysis of a session."""
    session_file: str
    cause_of_death: str = "unknown"
    confidence: str = "low"  # high | medium | low
    cookie_evidence: List[CookieEvidence] = field(default_factory=list)
    timeline: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    session_age_hours: float = 0.0
    cookie_count: int = 0
    expired_count: int = 0
    critical_present: int = 0
    critical_missing: int = 0
    site_name: str = "unknown"
    auth_status: str = "unknown"

    def to_text(self) -> str:
        """Render human-readable forensic report."""
        lines = [
            "=" * 60,
            "SESSION AUTOPSY REPORT",
            "=" * 60,
            f"File: {self.session_file}",
            f"Site: {self.site_name}",
            f"Auth Status: {self.auth_status}",
            f"Session Age: {self.session_age_hours:.1f} hours",
            "",
            f"PRIMARY CAUSE: {self.cause_of_death.upper()} "
            f"(confidence: {self.confidence})",
            "-" * 60,
        ]

        # Cause description
        cause_desc = _CAUSE_DESCRIPTIONS.get(
            self.cause_of_death, "Unknown cause."
        )
        lines.append(cause_desc)
        lines.append("")

        # Cookie summary
        lines.append(
            f"COOKIES: {self.cookie_count} total | "
            f"{self.expired_count} expired | "
            f"{self.critical_present} critical present | "
            f"{self.critical_missing} critical missing"
        )
        lines.append("")

        # Cookie evidence table
        if self.cookie_evidence:
            lines.append("COOKIE EVIDENCE:")
            for e in self.cookie_evidence:
                icon = {
                    "expired": "❌",
                    "expiring_soon": "⚠️",
                    "valid": "✅",
                    "session": "📌",
                }.get(e.status, "❓")
                crit = " CRITICAL" if e.is_critical else ""
                cause = f" — {e.probable_cause}" if e.probable_cause else ""
                lines.append(
                    f"  {icon} {e.name:<35} ({e.domain}){crit}{cause}"
                )
            lines.append("")

        # Timeline
        if self.timeline:
            lines.append("TIMELINE:")
            for i, event in enumerate(self.timeline, 1):
                lines.append(f"  {i}. {event}")
            lines.append("")

        # Recommendations
        if self.recommendations:
            lines.append("RECOMMENDATIONS:")
            for i, rec in enumerate(self.recommendations, 1):
                lines.append(f"  {i}. {rec}")

        lines.append("=" * 60)
        return "\n".join(lines)

    def to_json(self) -> str:
        """Render JSON forensic report."""
        data = {
            "session_file": self.session_file,
            "cause_of_death": self.cause_of_death,
            "confidence": self.confidence,
            "site_name": self.site_name,
            "auth_status": self.auth_status,
            "session_age_hours": self.session_age_hours,
            "cookie_count": self.cookie_count,
            "expired_count": self.expired_count,
            "critical_present": self.critical_present,
            "critical_missing": self.critical_missing,
            "timeline": self.timeline,
            "recommendations": self.recommendations,
            "cookies": [
                {
                    "name": e.name,
                    "domain": e.domain,
                    "status": e.status,
                    "expires_at": e.expires_at,
                    "age_hours": e.age_hours,
                    "is_critical": e.is_critical,
                    "cause": e.probable_cause,
                }
                for e in self.cookie_evidence
            ],
        }
        return json.dumps(data, indent=2)


_CAUSE_DESCRIPTIONS = {
    "natural_expiry": (
        "Cookies expired by timestamp. This is normal — sessions have "
        "a limited lifetime. Re-export from the source browser."
    ),
    "server_revocation": (
        "Cookies exist and are unexpired by timestamp, but the server "
        "likely revoked them. This happens when: user logged out from "
        "another device, password changed, suspicious activity detected, "
        "or account security event triggered."
    ),
    "missing_critical": (
        "Critical authentication cookies are missing from the session. "
        "This usually means the session was exported with incorrect "
        "domain filters, or the browser didn't have those cookies."
    ),
    "incomplete_extraction": (
        "Too few cookies were extracted. The session may have been "
        "exported while the browser was not logged in, or the domain "
        "filter was too narrow."
    ),
    "session_age": (
        "Session is too old. Even if cookies haven't expired by "
        "timestamp, servers often invalidate sessions after a fixed "
        "age regardless of cookie expiry."
    ),
    "mixed_signals": (
        "Multiple issues detected. The session has a combination of "
        "expired cookies, missing critical cookies, and/or auth "
        "status problems."
    ),
    "auth_status_reported": (
        "The session's own auth_status field indicates the session "
        "is not valid (e.g., 'session_expired', 'unknown')."
    ),
    "unknown": (
        "Could not determine the cause of death. The session may "
        "have been invalidated by a mechanism not visible in the "
        "cookie data (e.g., server-side token revocation, IP ban)."
    ),
}


class SessionAutopsy:
    """Performs root-cause analysis on a dead/expired session."""

    def __init__(self, session_file: str):
        self.session_file = session_file
        self._session = None
        self._cookies = []
        self._now = time.time()

    def analyze(self) -> AutopsyReport:
        """Run full forensic analysis."""
        report = AutopsyReport(session_file=self.session_file)

        # Load session
        try:
            with open(self.session_file) as f:
                self._session = json.load(f)
        except FileNotFoundError:
            report.cause_of_death = "unknown"
            report.confidence = "high"
            report.recommendations = [f"File not found: {self.session_file}"]
            return report
        except json.JSONDecodeError:
            report.cause_of_death = "unknown"
            report.confidence = "high"
            report.recommendations = ["Invalid JSON in session file"]
            return report

        self._cookies = self._session.get("cookies", [])
        report.site_name = self._session.get("site_name", "unknown")
        report.auth_status = self._session.get("auth_status", "unknown")
        report.cookie_count = len(self._cookies)

        # Determine critical cookies for this site
        critical_names = set()
        site = report.site_name
        if site in SITE_DETECTION:
            critical_names = set(SITE_DETECTION[site]["critical_cookies"])

        # Analyze each cookie
        cookie_names = set()
        for c in self._cookies:
            evidence = self._analyze_cookie(c, critical_names)
            report.cookie_evidence.append(evidence)
            cookie_names.add(evidence.name)
            if evidence.status == "expired":
                report.expired_count += 1
            if evidence.is_critical:
                report.critical_present += 1

        # Check for missing critical cookies
        missing_critical = critical_names - cookie_names
        report.critical_missing = len(missing_critical)

        # Session age
        created = self._session.get("created_at", "")
        if created:
            try:
                created_dt = datetime.fromisoformat(
                    created.replace("Z", "+00:00")
                )
                report.session_age_hours = (
                    datetime.now(timezone.utc) - created_dt
                ).total_seconds() / 3600
            except Exception:
                pass

        # Build timeline
        report.timeline = self._build_timeline(report)

        # Determine cause of death
        report.cause_of_death, report.confidence = self._determine_cause(
            report, missing_critical
        )

        # Generate recommendations
        report.recommendations = self._generate_recommendations(report)

        return report

    def _analyze_cookie(
        self, cookie: Dict, critical_names: set
    ) -> CookieEvidence:
        """Analyze a single cookie."""
        name = cookie.get("name", "unknown")
        domain = cookie.get("domain", "unknown")
        expires = cookie.get("expires", 0)
        is_critical = name in critical_names

        # Determine expiry
        if not expires or int(expires) == 0:
            return CookieEvidence(
                name=name,
                domain=domain,
                status="session",
                expires_at="session",
                is_critical=is_critical,
            )

        expires_int = int(expires)
        if expires_int > 1262304000000:
            expires_int = expires_int // 1000

        # Convert to ISO
        try:
            expires_dt = datetime.fromtimestamp(expires_int, tz=timezone.utc)
            expires_iso = expires_dt.isoformat()
        except Exception:
            expires_iso = str(expires_int)

        # Calculate age
        age_hours = (self._now - expires_int) / 3600 if expires_int < self._now else 0

        # Status
        if expires_int < self._now:
            status = "expired"
            cause = f"expired {abs(age_hours):.1f}h ago"
        elif expires_int < self._now + 86400:
            status = "expiring_soon"
            cause = f"expires in {(expires_int - self._now) / 3600:.1f}h"
        else:
            status = "valid"
            cause = ""

        return CookieEvidence(
            name=name,
            domain=domain,
            status=status,
            expires_at=expires_iso,
            age_hours=abs(age_hours),
            is_critical=is_critical,
            probable_cause=cause,
        )

    def _build_timeline(self, report: AutopsyReport) -> List[str]:
        """Build an ordered timeline of events."""
        events = []

        # Session creation
        created = self._session.get("created_at", "")
        if created:
            events.append(f"Session created: {created}")

        # Cookie expiry events (sorted by time)
        expired_cookies = [
            e for e in report.cookie_evidence if e.status == "expired"
        ]
        expired_cookies.sort(key=lambda e: e.expires_at)

        for e in expired_cookies[:5]:  # Show top 5
            crit = " (CRITICAL)" if e.is_critical else ""
            events.append(
                f"Cookie expired: {e.name}{crit} at {e.expires_at}"
            )

        if len(expired_cookies) > 5:
            events.append(
                f"... and {len(expired_cookies) - 5} more expired cookies"
            )

        # Autopsy time
        events.append(
            f"Autopsy performed: "
            f"{datetime.now(timezone.utc).isoformat()}"
        )

        return events

    def _determine_cause(
        self, report: AutopsyReport, missing_critical: set
    ) -> Tuple[str, str]:
        """Determine primary cause of death and confidence."""
        issues = []

        # Check auth_status
        if report.auth_status in ("session_expired", "expired", "invalid"):
            issues.append("auth_status_bad")

        # Check expired cookies
        if report.expired_count > 0:
            expired_ratio = report.expired_count / max(report.cookie_count, 1)
            if expired_ratio > 0.5:
                issues.append("mostly_expired")
            else:
                issues.append("some_expired")

        # Check missing critical
        if missing_critical:
            issues.append("missing_critical")

        # Check session age
        if report.session_age_hours > 168:  # 7 days
            issues.append("old_session")

        # Determine cause
        if not issues:
            return "unknown", "low"

        if len(issues) >= 3:
            return "mixed_signals", "high"

        if "auth_status_bad" in issues and report.expired_count == 0:
            return "server_revocation", "high"

        if "mostly_expired" in issues:
            return "natural_expiry", "high"

        if "missing_critical" in issues and report.expired_count == 0:
            return "missing_critical", "high"

        if "old_session" in issues:
            return "session_age", "medium"

        if "some_expired" in issues:
            return "natural_expiry", "medium"

        if "auth_status_bad" in issues:
            return "auth_status_reported", "medium"

        return "unknown", "low"

    def _generate_recommendations(self, report: AutopsyReport) -> List[str]:
        """Generate actionable recommendations."""
        recs = []

        if report.cause_of_death == "natural_expiry":
            recs.append("Re-export session from the source browser")
            recs.append("Consider enabling auto-refresh with: tokenade ci run")

        elif report.cause_of_death == "server_revocation":
            recs.append("Re-login to the site in the browser and re-export")
            recs.append(
                "Check account security activity for suspicious logins"
            )
            recs.append("Consider enabling 2FA if not already enabled")

        elif report.cause_of_death == "missing_critical":
            site = report.site_name
            if site in SITE_DETECTION:
                domains = SITE_DETECTION[site]["domains"]
                domain_str = ",".join(domains[:3])
                recs.append(
                    f"Re-export with correct domains: "
                    f"tokenade export --domains '{domain_str}'"
                )
            else:
                recs.append("Re-export with the correct --domains filter")

        elif report.cause_of_death == "session_age":
            recs.append("Session is too old — re-export from the browser")
            recs.append("Consider shorter refresh intervals in tokenade.yml")

        elif report.cause_of_death == "mixed_signals":
            recs.append("Multiple issues found — re-login and re-export")
            recs.append("Run: tokenade health -s <session> for details")

        elif report.cause_of_death == "auth_status_reported":
            recs.append("The session reports itself as invalid")
            recs.append("Re-export from the source browser")

        else:
            recs.append("Re-export session from the browser")
            recs.append(
                "If issue persists, check if the site uses "
                "server-side session invalidation"
            )

        return recs
