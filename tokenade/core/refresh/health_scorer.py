"""
OWASP-based session health scoring.

Evaluates session security posture based on OWASP session management guidelines:
- Token entropy (128-bit minimum)
- Cookie age vs absolute timeout (4-8 hours)
- Idle timeout (2-30 min depending on app)
- Flag presence (HttpOnly, Secure, SameSite)
- Token rotation status
"""
import time
import math
from dataclasses import dataclass, field
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class HealthScoreBreakdown:
    """Detailed breakdown of health score calculation."""
    total_score: float = 0.0  # 0-100
    entropy_score: float = 0.0  # 0-25
    expiry_score: float = 0.0  # 0-25
    flags_score: float = 0.0  # 0-25
    freshness_score: float = 0.0  # 0-25
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


class SessionHealthScorer:
    """Score session health based on OWASP guidelines."""

    # OWASP recommended timeouts (seconds)
    ABSOLUTE_TIMEOUT = 8 * 3600  # 8 hours
    IDLE_TIMEOUT_STANDARD = 30 * 60  # 30 minutes
    IDLE_TIMEOUT_CRITICAL = 5 * 60  # 5 minutes for critical apps
    MIN_TOKEN_ENTROPY_BITS = 128  # 128-bit minimum

    # Known critical cookies per site (auth cookies that MUST be present)
    CRITICAL_COOKIES = {
        "google": ["SID", "HSID", "SSID", "APISID", "SAPISID", "__Secure-1PSID", "__Secure-3PSID"],
        "github": ["logged_in", "user_session", "_gh_sess"],
        "twitter": ["auth_token", "ct0"],
        "facebook": ["c_user", "xs", "datr"],
        "session_id": ["session_id", "sessionid", "sid", "connect.sid"],
    }

    def score(self, session: Dict) -> HealthScoreBreakdown:
        """Calculate comprehensive health score for a session.

        Args:
            session: .tokenade session dictionary

        Returns:
            HealthScoreBreakdown with detailed scoring
        """
        breakdown = HealthScoreBreakdown()
        cookies = session.get("cookies", [])

        if not cookies:
            breakdown.issues.append("No cookies in session")
            breakdown.total_score = 0.0
            return breakdown

        # Score each dimension
        breakdown.entropy_score = self._score_entropy(cookies)
        breakdown.expiry_score = self._score_expiry(cookies)
        breakdown.flags_score = self._score_flags(cookies)
        breakdown.freshness_score = self._score_freshness(session)

        # Check critical cookies
        self._check_critical_cookies(session, breakdown)

        # Check auth status
        self._check_auth_status(session, breakdown)

        # Calculate total
        breakdown.total_score = (
            breakdown.entropy_score
            + breakdown.expiry_score
            + breakdown.flags_score
            + breakdown.freshness_score
        )

        return breakdown

    def _score_entropy(self, cookies: List[Dict]) -> float:
        """Score token entropy (0-25).

        OWASP requires minimum 128-bit entropy for session tokens.
        We estimate entropy based on token value length and character diversity.
        """
        if not cookies:
            return 0.0

        scores = []
        for cookie in cookies:
            value = cookie.get("value", "")
            if not value:
                scores.append(0.0)
                continue

            # Estimate entropy: log2(charset_size) * length
            charset_size = self._estimate_charset_size(value)
            entropy_bits = math.log2(max(charset_size, 1)) * len(value)

            # Score: 25 if >= 128 bits, linear scale down
            score = min(25.0, (entropy_bits / self.MIN_TOKEN_ENTROPY_BITS) * 25.0)
            scores.append(score)

        return sum(scores) / len(scores) if scores else 0.0

    def _estimate_charset_size(self, value: str) -> int:
        """Estimate the character set size of a token value."""
        has_upper = any(c.isupper() for c in value)
        has_lower = any(c.islower() for c in value)
        has_digit = any(c.isdigit() for c in value)
        has_special = any(not c.isalnum() for c in value)

        size = 0
        if has_lower:
            size += 26
        if has_upper:
            size += 26
        if has_digit:
            size += 10
        if has_special:
            size += 32

        return max(size, 1)

    def _score_expiry(self, cookies: List[Dict]) -> float:
        """Score cookie expiry management (0-25).

        - All cookies valid: 25
        - Some expiring soon (within 1 hour): 15
        - Some expired: 10
        - All expired: 0
        """
        if not cookies:
            return 0.0

        now = time.time()
        total = 0
        valid = 0
        expiring_soon = 0
        expired = 0

        for cookie in cookies:
            expires = cookie.get("expires", 0)
            if not expires or int(expires) <= 0:
                # Session cookie - considered valid
                valid += 1
                total += 1
                continue

            expires_int = int(expires)
            # Convert ms to seconds if needed
            if expires_int > 1262304000000:
                expires_int = expires_int // 1000

            total += 1
            if expires_int < now:
                expired += 1
            elif expires_int < now + 3600:  # 1 hour
                expiring_soon += 1
            else:
                valid += 1

        if total == 0:
            return 0.0

        if expired == total:
            return 0.0
        elif expired > 0:
            return 10.0
        elif expiring_soon > 0:
            return 15.0
        else:
            return 25.0

    def _score_flags(self, cookies: List[Dict]) -> float:
        """Score security flags (0-25).

        OWASP requires: HttpOnly, Secure, SameSite=Lax or Strict
        """
        if not cookies:
            return 0.0

        total = 0
        score_sum = 0.0

        for cookie in cookies:
            cookie_score = 0.0

            # HttpOnly: +7 points
            if cookie.get("httpOnly", False):
                cookie_score += 7.0
            else:
                # Session cookies without httponly are a risk
                if cookie.get("expires", 0) and int(cookie.get("expires", 0)) > 0:
                    pass  # persistent cookies should have httponly
                else:
                    cookie_score += 3.0  # partial credit for session cookies

            # Secure: +7 points
            if cookie.get("secure", False):
                cookie_score += 7.0

            # SameSite: +5 points for Lax/Strict, +2 for None, 0 for missing
            same_site = cookie.get("sameSite", "").lower()
            if same_site in ("lax", "strict"):
                cookie_score += 5.0
            elif same_site == "none":
                cookie_score += 2.0

            # Domain scope: +3 points for specific domain (not broad)
            domain = cookie.get("domain", "")
            if domain and not domain.startswith("."):
                cookie_score += 3.0
            elif domain.startswith("."):
                cookie_score += 1.0

            # Max 22 per cookie (normalized to 25 max)
            score_sum += min(cookie_score, 22.0)
            total += 1

        if total == 0:
            return 0.0

        avg = score_sum / total
        return min(25.0, avg * (25.0 / 22.0))

    def _score_freshness(self, session: Dict) -> float:
        """Score session freshness (0-25).

        Based on when the session was created and how it compares to
        OWASP absolute timeout recommendations.
        """
        created_at = session.get("created_at", "")
        if not created_at:
            return 12.5  # Unknown age, neutral score

        try:
            from datetime import datetime, timezone

            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            age_seconds = (now - created).total_seconds()

            # Perfect score if < 1 hour old
            if age_seconds < 3600:
                return 25.0
            # Good if < 4 hours
            elif age_seconds < 4 * 3600:
                return 20.0
            # Acceptable if < 8 hours (OWASP absolute timeout)
            elif age_seconds < self.ABSOLUTE_TIMEOUT:
                return 15.0
            # Degrading after 8 hours
            elif age_seconds < 24 * 3600:
                return 10.0
            # Stale after 24 hours
            else:
                return 5.0
        except Exception:
            return 12.5  # Can't parse, neutral score

    def _check_critical_cookies(self, session: Dict, breakdown: HealthScoreBreakdown):
        """Check for missing critical cookies."""
        site_name = session.get("site_name", "").lower()
        cookies = session.get("cookies", [])

        if site_name not in self.CRITICAL_COOKIES:
            return

        required = set(self.CRITICAL_COOKIES[site_name])
        present = {c.get("name", "") for c in cookies}
        missing = required - present

        if missing:
            breakdown.issues.append(f"Missing critical cookies: {', '.join(sorted(missing)[:5])}")
            breakdown.recommendations.append("Re-login and re-export session")

    def _check_auth_status(self, session: Dict, breakdown: HealthScoreBreakdown):
        """Check authentication status."""
        auth_status = session.get("auth_status", "unknown")
        if auth_status != "logged_in":
            breakdown.issues.append(f"Auth status: {auth_status}")
            breakdown.recommendations.append("Re-login and re-export session")
