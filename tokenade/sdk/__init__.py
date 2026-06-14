"""
Tokenade Python SDK.

Programmatic interface for session management, extraction, and proxy.

Usage:
    from tokenade.sdk import TokenadeClient
    
    client = TokenadeClient()
    session = client.extract(browser="chrome", domains=["github.com"])
    client.proxy(session, port=9222)
"""
import json
import logging
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Result of a session extraction."""
    success: bool
    session_file: Optional[str] = None
    session_data: Optional[Dict] = None
    cookie_count: int = 0
    error: Optional[str] = None


class TokenadeClient:
    """Main SDK client for Tokenade operations."""
    
    def __init__(self, sessions_dir: Optional[str] = None):
        self.sessions_dir = Path(sessions_dir or "~/.tokenade/sessions").expanduser()
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
    
    def extract(self, browser: str = "chrome", domains: Optional[List[str]] = None,
                profile: Optional[str] = None, output: Optional[str] = None) -> ExtractionResult:
        """Extract cookies from a browser.
        
        Args:
            browser: Browser name (chrome, firefox, edge, brave)
            domains: Optional domain filter (e.g., ["github.com"])
            profile: Optional profile name
            output: Optional output file path
            
        Returns:
            ExtractionResult
        """
        from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery
        from tokenade.core.importer.cookie_extractor import CookieExtractor, SiteFilter
        from tokenade.core.importer.session_packager import SessionPackager
        from tokenade.core.importer.cookie_extractor import SITE_DETECTION
        
        try:
            discovery = BrowserProfileDiscovery()
            profiles = discovery.discover_all()
            
            browser_profiles = profiles.get(browser, [])
            if not browser_profiles:
                return ExtractionResult(
                    success=False,
                    error=f"No profiles found for {browser}"
                )
            
            target_profile = browser_profiles[0]
            if profile:
                for p in browser_profiles:
                    if p.name == profile:
                        target_profile = p
                        break
            
            site_filter = None
            if domains:
                site_names = []
                for domain in domains:
                    for site_name, rules in SITE_DETECTION.items():
                        for pattern in rules["domains"]:
                            clean = pattern.lstrip(".")
                            if domain == clean or domain.endswith("." + clean):
                                site_names.append(site_name)
                                break
                if site_names:
                    site_filter = SiteFilter(list(set(site_names)))
            
            extractor = CookieExtractor(str(target_profile.path), browser=browser)
            cookies = extractor.extract(site_filter=site_filter)
            
            if not cookies:
                return ExtractionResult(
                    success=False,
                    error="No cookies extracted"
                )
            
            packager = SessionPackager()
            session = packager.package(
                cookies=cookies,
                browser=browser,
                profile=target_profile.name,
            )
            
            if output:
                output_path = output
            else:
                site_name = session.get("site_name", "session")
                output_path = str(self.sessions_dir / f"{site_name}.tokenade")
            
            packager.save(session, output_path)
            
            return ExtractionResult(
                success=True,
                session_file=output_path,
                session_data=session,
                cookie_count=len(cookies),
            )
            
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return ExtractionResult(
                success=False,
                error=str(e)
            )
    
    def load(self, session_file: str) -> Optional[Dict]:
        """Load a session file.
        
        Args:
            session_file: Path to .tokenade file
            
        Returns:
            Session dictionary or None
        """
        from tokenade.core.importer.session_packager import SessionPackager
        
        try:
            packager = SessionPackager()
            return packager.load(session_file)
        except Exception as e:
            logger.error(f"Failed to load session: {e}")
            return None
    
    def health_check(self, session_file: str) -> Dict:
        """Check session health.
        
        Args:
            session_file: Path to .tokenade file
            
        Returns:
            Health check result
        """
        from tokenade.core.refresh.health_checker import SessionHealthChecker
        from tokenade.core.refresh.health_scorer import SessionHealthScorer
        
        try:
            checker = SessionHealthChecker()
            health = checker.check_session(session_file)
            
            scorer = SessionHealthScorer()
            with open(session_file) as f:
                session = json.load(f)
            score = scorer.score(session)
            
            return {
                "healthy": health.healthy,
                "health_score": health.health_score,
                "owasp_score": score.total_score,
                "issues": health.issues,
                "recommendations": health.recommendations,
            }
            
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
            }
    
    def share(self, session_file: str, password: Optional[str] = None,
              expiry_hours: int = 24) -> Optional[str]:
        """Create a shareable link.
        
        Args:
            session_file: Path to .tokenade file
            password: Optional password protection
            expiry_hours: Link expiry in hours
            
        Returns:
            Share URL or None
        """
        from tokenade.core.importer.session_sharer import SessionSharer, ShareConfig
        
        try:
            with open(session_file) as f:
                session = json.load(f)
            
            config = ShareConfig(
                expiry_hours=expiry_hours,
                password_protected=password is not None,
                password=password,
            )
            
            sharer = SessionSharer()
            share_url, _ = sharer.create_share_link(session, config)
            return share_url
        except Exception as e:
            logger.error(f"Share failed: {e}")
            return None
    
    def list_sessions(self) -> List[Dict]:
        """List all sessions in the sessions directory.
        
        Returns:
            List of session metadata
        """
        from tokenade.core.importer.session_manager import SessionManager
        
        manager = SessionManager(str(self.sessions_dir))
        sessions = manager.list_sessions()
        
        return [
            {
                "path": s.path,
                "site_name": s.site_name,
                "cookie_count": s.cookie_count,
                "created_at": s.created_at,
                "source_browser": s.source_browser,
            }
            for s in sessions
        ]
    
    def export_playwright(self, session_file: str, output: str) -> bool:
        """Export session to Playwright storageState format.
        
        Args:
            session_file: Path to .tokenade file
            output: Output file path
            
        Returns:
            Success boolean
        """
        from tokenade.core.importer.format_exporter import FormatExporter
        
        try:
            with open(session_file) as f:
                session = json.load(f)
            
            exporter = FormatExporter(session)
            storage_state = exporter.to_playwright_storagestate()
            
            with open(output, "w") as f:
                f.write(storage_state)
            
            return True
        except Exception as e:
            logger.error(f"Export failed: {e}")
            return False
