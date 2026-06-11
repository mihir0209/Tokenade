"""
Session Refresh - Automatic session refresh and health monitoring.

Provides session health checking and automatic refresh capabilities.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

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
