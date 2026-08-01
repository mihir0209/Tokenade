"""
Session Refresh - Automatic session refresh and health monitoring.

Provides session health checking and automatic refresh capabilities.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionHealth:
    """Session health status."""
    healthy: bool
    expires_in: Optional[int] = None  # seconds
    health_score: float = 0.0  # 0.0 to 1.0
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    last_checked: Optional[str] = None
    server_valid: Optional[bool] = None  # None = not probed, True = valid, False = invalidated


@dataclass
class RefreshResult:
    """Result of session refresh operation."""
    success: bool
    session_file: str
    cookies_refreshed: int
    cookies_total: int
    error: Optional[str] = None


class SessionHealthChecker:
    """
    Checks session health and expiry.

    Usage:
        checker = SessionHealthChecker()
        health = checker.check_session("chatgpt.session")
        if not health.healthy:
            print(f"Session issues: {health.issues}")
    """

    def check_session(self, session_file: str) -> SessionHealth:
        """
        Check session health.

        Args:
            session_file: Path to session file

        Returns:
            SessionHealth with details
        """
        try:
            with open(session_file) as f:
                session = json.load(f)

            issues = []
            recommendations = []

            # Check basic structure
            if 'cookies' not in session:
                issues.append("No cookies in session")
                return SessionHealth(
                    healthy=False,
                    health_score=0.0,
                    issues=issues,
                    recommendations=["Export session with cookies"],
                    last_checked=datetime.now().isoformat()
                )

            cookies = session.get('cookies', [])
            if not cookies:
                issues.append("Empty cookie list")
                return SessionHealth(
                    healthy=False,
                    health_score=0.0,
                    issues=issues,
                    recommendations=["Re-export session from browser"],
                    last_checked=datetime.now().isoformat()
                )

            # Check cookie expiry
            now = time.time()
            expired_cookies = []
            expiring_soon = []
            valid_cookies = []

            for cookie in cookies:
                expires = cookie.get('expires', 0)
                if expires and int(expires) > 0:
                    expires_int = int(expires)
                    # Convert milliseconds to seconds if needed
                    if expires_int > 1262304000000:
                        expires_int = expires_int // 1000

                    if expires_int < now:
                        expired_cookies.append(cookie.get('name', 'unknown'))
                    elif expires_int < now + 86400:  # 24 hours
                        expiring_soon.append(cookie.get('name', 'unknown'))
                    else:
                        valid_cookies.append(cookie.get('name', 'unknown'))
                else:
                    # Session cookie (no expiry)
                    valid_cookies.append(cookie.get('name', 'unknown'))

            if expired_cookies:
                issues.append(f"{len(expired_cookies)} expired cookies")
                recommendations.append("Re-export session from browser")

            if expiring_soon:
                issues.append(f"{len(expiring_soon)} cookies expiring soon")
                recommendations.append("Consider refreshing session")

            # Calculate health score
            total = len(cookies)
            if total == 0:
                health_score = 0.0
            else:
                health_score = len(valid_cookies) / total

            # Check auth status
            auth_status = session.get('auth_status', 'unknown')
            if auth_status != 'logged_in':
                issues.append(f"Auth status: {auth_status}")
                recommendations.append("Re-login and re-export session")

            # Calculate expiry
            expires_in = None
            if expiring_soon:
                # Find soonest expiry
                soonest = float('inf')
                for cookie in cookies:
                    expires = cookie.get('expires', 0)
                    if expires and int(expires) > 0:
                        expires_int = int(expires)
                        if expires_int > 1262304000000:
                            expires_int = expires_int // 1000
                        if expires_int < soonest and expires_int > now:
                            soonest = expires_int
                if soonest < float('inf'):
                    expires_in = int(soonest - now)

            healthy = len(issues) == 0 or (len(issues) == 1 and 'expiring soon' in issues[0])

            return SessionHealth(
                healthy=healthy,
                expires_in=expires_in,
                health_score=health_score,
                issues=issues,
                recommendations=recommendations,
                last_checked=datetime.now().isoformat()
            )

        except Exception as e:
            logger.error(f"Failed to check session health: {e}")
            return SessionHealth(
                healthy=False,
                health_score=0.0,
                issues=[f"Failed to read session: {e}"],
                recommendations=["Check session file format"],
                last_checked=datetime.now().isoformat()
            )

    def check_multiple(self, session_files: List[str]) -> Dict[str, SessionHealth]:
        """
        Check health of multiple sessions.

        Args:
            session_files: List of session file paths

        Returns:
            Dictionary of session file to health status
        """
        results = {}
        for session_file in session_files:
            results[session_file] = self.check_session(session_file)
        return results


class SessionRefresher:
    """
    Refreshes sessions from source browser.

    Usage:
        refresher = SessionRefresher()
        result = refresher.refresh(
            session_file="chatgpt.session",
            source_browser="firefox"
        )
    """

    def refresh(
        self,
        session_file: str,
        source_browser: str,
        source_browser_path: Optional[str] = None,
        source_profile: Optional[str] = None,
        site_config: Optional[Dict] = None
    ) -> RefreshResult:
        """
        Refresh session from source browser.

        Args:
            session_file: Path to session file to refresh
            source_browser: Source browser name
            source_browser_path: Custom browser profile path
            source_profile: Source profile name
            site_config: Site configuration for filtering

        Returns:
            RefreshResult
        """
        from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery
        from tokenade.core.importer.cookie_extractor import CookieExtractor
        from tokenade.core.importer.session_packager import SessionPackager

        try:
            # Load existing session
            with open(session_file) as f:
                old_session = json.load(f)

            # Discover source browser profile
            browser_path = source_browser_path
            if not browser_path:
                discovery = BrowserProfileDiscovery()
                profiles = discovery.discover_all()
                all_profiles = []
                for browser_profiles in profiles.values():
                    all_profiles.extend(browser_profiles)

                matching = [p for p in all_profiles if p.browser == source_browser]
                if source_profile:
                    matching = [p for p in matching if p.name == source_profile]

                if matching:
                    browser_path = str(matching[0].path)
                else:
                    return RefreshResult(
                        success=False,
                        session_file=session_file,
                        cookies_refreshed=0,
                        cookies_total=0,
                        error=f"No profile found for {source_browser}"
                    )

            # Extract fresh cookies
            extractor = CookieExtractor(browser_path, browser=source_browser)
            all_cookies = extractor.extract(site_filter=None)

            # Filter by domains from old session or site config
            domains = set()
            for cookie in old_session.get('cookies', []):
                domains.add(cookie.get('domain', ''))

            if site_config and 'domains' in site_config:
                domains.update(site_config['domains'])

            # Filter cookies
            fresh_cookies = []
            for cookie in all_cookies:
                domain = cookie.get('domain', '')
                for d in domains:
                    if d.startswith('.'):
                        if domain.endswith(d) or domain == d[1:]:
                            fresh_cookies.append(cookie)
                            break
                    else:
                        if domain == d or domain.endswith('.' + d):
                            fresh_cookies.append(cookie)
                            break

            if not fresh_cookies:
                return RefreshResult(
                    success=False,
                    session_file=session_file,
                    cookies_refreshed=0,
                    cookies_total=len(all_cookies),
                    error="No matching cookies found"
                )

            # Package new session
            packager = SessionPackager()
            new_session = packager.package(
                cookies=fresh_cookies,
                browser=source_browser,
                profile=source_profile or old_session.get('metadata', {}).get('profile', 'unknown'),
                local_storage=old_session.get('local_storage')
            )

            # Preserve original metadata
            new_session['metadata']['refreshed_from'] = session_file
            new_session['metadata']['refreshed_at'] = datetime.now().isoformat()
            new_session['metadata']['original_exported_at'] = old_session.get('metadata', {}).get('exported_at')

            # Save
            packager.save(new_session, session_file)

            return RefreshResult(
                success=True,
                session_file=session_file,
                cookies_refreshed=len(fresh_cookies),
                cookies_total=len(all_cookies)
            )

        except Exception as e:
            logger.error(f"Session refresh failed: {e}")
            return RefreshResult(
                success=False,
                session_file=session_file,
                cookies_refreshed=0,
                cookies_total=0,
                error=str(e)
            )


def generate_health_report(health: SessionHealth) -> str:
    """
    Generate human-readable health report.

    Args:
        health: SessionHealth object

    Returns:
        Formatted report string
    """
    lines = []

    status = "✅ HEALTHY" if health.healthy else "❌ UNHEALTHY"
    lines.append(f"Status: {status}")
    lines.append(f"Health Score: {health.health_score:.1%}")

    if health.expires_in is not None:
        hours = health.expires_in // 3600
        minutes = (health.expires_in % 3600) // 60
        lines.append(f"Expires In: {hours}h {minutes}m")

    if health.issues:
        lines.append("\nIssues:")
        for issue in health.issues:
            lines.append(f"  • {issue}")

    if health.recommendations:
        lines.append("\nRecommendations:")
        for rec in health.recommendations:
            lines.append(f"  • {rec}")

    lines.append(f"\nLast Checked: {health.last_checked}")

    return "\n".join(lines)


class SessionProbe:
    """Server-side session invalidation probe using a lightweight HTTP request.

    Sends the session's cookies to a configured ``session_check_url`` or
    ``api_probe_url`` and inspects the HTTP status code:
    - 200/2xx/304 → valid
    - 401/403 → invalidated
    - Other → unknown (treated as inconclusive, not a failure)

    The probe is pure HTTP (no browser). It reads the site_config from the
    installed plugin system to find the probe URL.
    """

    @staticmethod
    def probe(session_path: str, *, timeout: float = 8.0) -> Optional[bool]:
        """Probe whether cookies in a session file are still server-valid.

        Args:
            session_path: Path to the .tokenade session file.
            timeout: HTTP request timeout in seconds.

        Returns:
            True if server confirms valid, False if invalidated, None if inconclusive.
        """
        import urllib.request
        import urllib.error

        try:
            with open(session_path, encoding="utf-8") as f:
                session = json.load(f)
        except Exception:
            return None

        cookies = session.get("cookies", [])
        if not isinstance(cookies, list) or not cookies:
            return None

        probe_url = _resolve_probe_url(session)
        if not probe_url:
            return None

        cookie_header = _build_cookie_header(cookies, probe_url)
        if not cookie_header:
            return None

        request = urllib.request.Request(
            probe_url,
            headers={"Cookie": cookie_header, "User-Agent": "tokenade-probe/1.0"},
            method="GET",
        )

        # Avoid following redirects — a 302 to /login is the auth-failed signal.
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def http_error_301(self, req, fp, code, msg, headers):
                return fp
            def http_error_302(self, req, fp, code, msg, headers):
                return fp
            def http_error_303(self, req, fp, code, msg, headers):
                return fp
            def http_error_307(self, req, fp, code, msg, headers):
                return fp
            def http_error_308(self, req, fp, code, msg, headers):
                return fp

        opener = urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open(request, timeout=timeout) as resp:
                status = resp.status
            # 2xx → valid; 3xx usually means redirect to login for auth-gated pages.
            if 200 <= status < 300:
                return True
            if 300 <= status < 400:
                return False
            return None
        except urllib.error.HTTPError as e:
            status = e.code
            if status in (401, 403, 302, 301, 303, 307, 308):
                return False
            return None
        except Exception:
            return None


def _resolve_probe_url(session: dict) -> Optional[str]:
    """Find a probe URL from the installed site config or session metadata."""
    try:
        from tokenade.core.importer.site_configs import get_site_config
    except Exception:
        return None

    site_name = session.get("site_name", "unknown") or "unknown"
    try:
        config = get_site_config(site_name)
    except Exception:
        config = {}

    # Server-side probes require an endpoint with machine-readable auth semantics
    # (2xx when logged in, 3xx/401/403 when logged out). Generic browser
    # validate_url pages can return bot-protection 403 or anonymous 200, causing
    # false invalidation signals.
    probe_url = config.get("session_check_url") or config.get("api_probe_url")
    if isinstance(probe_url, str) and probe_url.strip():
        return probe_url.strip()

    browser_metadata = (session.get("metadata") or {}).get("site_handler") or {}
    if isinstance(browser_metadata, dict):
        probe_url = browser_metadata.get("session_check_url") or browser_metadata.get("api_probe_url")
        if isinstance(probe_url, str) and probe_url.strip():
            return probe_url.strip()

    return None


def _build_cookie_header(cookies: list, probe_url: str) -> str:
    """Build a Cookie header only from cookies relevant to the probe URL."""
    from urllib.parse import urlparse

    try:
        hostname = urlparse(probe_url).hostname or ""
    except Exception:
        hostname = ""

    parts = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = cookie.get("name")
        value = cookie.get("value")
        if not name or value is None:
            continue
        domain = cookie.get("domain", "")
        if domain:
            clean_domain = domain.lstrip(".").lower()
            if hostname and hostname != clean_domain and not hostname.endswith("." + clean_domain):
                continue
        parts.append(f"{name}={value}")
    return "; ".join(parts)


def _infer_probe_url_from_cookies(cookies: list) -> Optional[str]:
    """Infer a probe URL from cookie domains when no site config URL is available.

    Picks the most common domain among cookies, preferring dot-prefixed domains
    (which are shared across subdomains).
    """
    from collections import Counter

    domains = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        domain = cookie.get("domain", "")
        if not isinstance(domain, str) or not domain.strip():
            continue
        clean = domain.lstrip(".").strip().lower()
        if clean:
            domains.append(clean)

    if not domains:
        return None

    # Pick most common domain
    most_common = Counter(domains).most_common(1)
    if most_common:
        domain = most_common[0][0]
        return f"https://{domain}/"
    return None
