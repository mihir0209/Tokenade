"""
Example: Custom Session Health Validation Plugin

This plugin demonstrates how to create custom validation rules
for session health checks.

Use cases:
- Custom scoring based on cookie freshness
- Domain-specific validation (e.g., check for critical cookies)
- Integration with external health check services

To use this plugin:
1. Copy the my_health_check/ directory to ~/.tokenade/plugins/
2. Run: tokenade plugin list
3. Run: tokenade health --session google.tokenade
"""

import time
import logging
from typing import Dict, List

from tokenade.plugin import SessionValidatorPlugin

logger = logging.getLogger(__name__)


class HealthCheckPlugin(SessionValidatorPlugin):
    """Custom session health validation with domain-specific rules.

    This example shows:
    - How to validate session health with custom scoring
    - How to check for critical cookies
    - How to detect stale sessions
    """

    name = "my-health-check"
    version = "1.0.0"
    description = "Example: Custom session health validation"
    author = "Tokenade Examples"

    # Critical cookies per site (example)
    CRITICAL_COOKIES = {
        "google": ["SID", "HSID", "SSID", "NID"],
        "github": ["logged_in", "user_session"],
        "twitter": ["auth_token", "ct0"],
    }

    def validate(self, session: dict) -> dict:
        """Validate session health with custom rules.

        Returns:
            Dict with valid (bool), score (float 0-100), issues (list)
        """
        issues = []
        score = 100.0

        cookies = session.get("cookies", [])
        site_name = session.get("site_name", "unknown")
        metadata = session.get("metadata", {})

        # Rule 1: Check cookie count
        if len(cookies) == 0:
            issues.append("No cookies in session")
            score -= 50
        elif len(cookies) < 3:
            issues.append(f"Only {len(cookies)} cookies (expected more)")
            score -= 20

        # Rule 2: Check for critical cookies
        critical = self.CRITICAL_COOKIES.get(site_name, [])
        if critical:
            cookie_names = {c.get("name", "") for c in cookies}
            missing = [name for name in critical if name not in cookie_names]
            if missing:
                issues.append(f"Missing critical cookies: {', '.join(missing)}")
                score -= 10 * len(missing)

        # Rule 3: Check cookie freshness
        now = time.time()
        stale_count = 0
        for cookie in cookies:
            expires = cookie.get("expires", 0)
            if expires and expires > 0 and expires < now:
                stale_count += 1
        if stale_count > 0:
            issues.append(f"{stale_count} expired cookie(s)")
            score -= 5 * stale_count

        # Rule 4: Check metadata
        if not metadata.get("last_refreshed"):
            issues.append("No refresh timestamp in metadata")
            score -= 10

        # Rule 5: Check auth status
        auth_status = metadata.get("auth_status", "")
        if auth_status and auth_status != "logged_in":
            issues.append(f"Auth status: {auth_status}")
            score -= 15

        # Clamp score
        score = max(0.0, min(100.0, score))

        return {
            "valid": score >= 50.0,
            "score": score,
            "issues": issues,
        }
