"""
Multi-session management: list, merge, rotate sessions.
"""

import json
import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    """Metadata about a session file."""
    path: str
    site_name: str
    cookie_count: int
    has_local_storage: bool
    created_at: Optional[str]
    source_browser: Optional[str]
    file_size: int


class SessionManager:
    """
    Manage multiple session files.
    
    Features:
    - List all sessions in a directory
    - Merge multiple sessions into one
    - Rotate between sessions (round-robin or random)
    - Filter sessions by site, browser, etc.
    """
    
    def __init__(self, sessions_dir: Optional[str] = None):
        self.sessions_dir = Path(sessions_dir or ".").expanduser()
    
    def list_sessions(
        self,
        pattern: str = "*.tokenade",
        recursive: bool = False,
    ) -> List[SessionInfo]:
        """
        List all session files in the directory.
        
        Args:
            pattern: Glob pattern to match
            recursive: Search subdirectories
            
        Returns:
            List of SessionInfo objects
        """
        sessions = []
        
        glob_func = self.sessions_dir.rglob if recursive else self.sessions_dir.glob
        
        for path in glob_func(pattern):
            try:
                info = self._get_session_info(path)
                if info:
                    sessions.append(info)
            except Exception as e:
                logger.warning(f"Failed to read {path}: {e}")
        
        return sorted(sessions, key=lambda s: s.site_name)
    
    def _get_session_info(self, path: Path) -> Optional[SessionInfo]:
        """Get metadata about a session file."""
        try:
            with open(path, "r") as f:
                data = json.load(f)
            
            return SessionInfo(
                path=str(path),
                site_name=data.get("site_name", "unknown"),
                cookie_count=len(data.get("cookies", [])),
                has_local_storage=bool(data.get("local_storage")),
                created_at=data.get("created_at"),
                source_browser=(data.get("source_device") or {}).get("browser"),
                file_size=path.stat().st_size,
            )
        except Exception:
            return None
    
    def merge_sessions(
        self,
        session_files: List[str],
        output_path: str,
        site_name: Optional[str] = None,
    ) -> str:
        """
        Merge multiple sessions into one.
        
        Combines cookies from all sessions, with later sessions overriding
        earlier ones for duplicate cookie names.
        
        Args:
            session_files: List of session file paths
            output_path: Output file path
            site_name: Optional site name for the merged session
            
        Returns:
            Path to merged session file
        """
        from tokenade.core.importer.session_packager import SessionPackager
        
        packager = SessionPackager()
        all_cookies = []
        all_local_storage = {}
        merged_metadata = {}
        
        for session_file in session_files:
            try:
                session = packager.load(session_file)
                cookies = session.get("cookies", [])
                local_storage = session.get("local_storage", {})
                
                # Merge cookies (later sessions override earlier)
                all_cookies.extend(cookies)
                
                # Merge localStorage (later sessions override earlier)
                all_local_storage.update(local_storage)
                
                # Use metadata from last session
                merged_metadata = session
                
                logger.info(f"Loaded {len(cookies)} cookies from {session_file}")
                
            except Exception as e:
                logger.warning(f"Failed to load {session_file}: {e}")
        
        if not all_cookies:
            raise ValueError("No cookies found in any session files")
        
        # Deduplicate cookies (keep last occurrence)
        seen = {}
        for cookie in all_cookies:
            key = (cookie.get("name"), cookie.get("domain"), cookie.get("path"))
            seen[key] = cookie
        deduped_cookies = list(seen.values())
        
        # Create merged session
        merged = {
            "version": "2.0",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "site_name": site_name or merged_metadata.get("site_name", "merged"),
            "source_device": merged_metadata.get("source_device", {}),
            "cookies": deduped_cookies,
            "fingerprint": merged_metadata.get("fingerprint"),
            "tls_profile": merged_metadata.get("tls_profile"),
            "local_storage": all_local_storage if all_local_storage else None,
            "metadata": {
                "merged_from": session_files,
                "cookie_count": len(deduped_cookies),
                "original_count": len(all_cookies),
            }
        }
        
        # Save merged session
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output, "w") as f:
            json.dump(merged, f, indent=2)
        
        logger.info(f"Merged {len(session_files)} sessions into {output_path}")
        logger.info(f"  Total cookies: {len(all_cookies)} -> {len(deduped_cookies)} (deduped)")
        
        return str(output)
    
    def rotate_session(
        self,
        session_files: List[str],
        strategy: str = "round-robin",
        state_file: Optional[str] = None,
    ) -> str:
        """
        Select next session file using rotation strategy.
        
        Args:
            session_files: List of session file paths
            strategy: 'round-robin' or 'random'
            state_file: File to persist rotation state
            
        Returns:
            Selected session file path
        """
        if not session_files:
            raise ValueError("No session files provided")
        
        if len(session_files) == 1:
            return session_files[0]
        
        if strategy == "random":
            return random.choice(session_files)
        
        # Round-robin
        state_path = Path(state_file or ".tokenade_rotation_state")
        
        # Load current index
        current_index = 0
        if state_path.exists():
            try:
                with open(state_path, "r") as f:
                    state = json.load(f)
                current_index = state.get("index", 0)
            except Exception:
                pass
        
        # Get next session
        selected = session_files[current_index % len(session_files)]
        
        # Update state
        next_index = (current_index + 1) % len(session_files)
        try:
            with open(state_path, "w") as f:
                json.dump({"index": next_index, "last_selected": selected}, f)
        except Exception as e:
            logger.warning(f"Failed to save rotation state: {e}")
        
        return selected
    
    def filter_sessions(
        self,
        sessions: List[SessionInfo],
        site_name: Optional[str] = None,
        browser: Optional[str] = None,
        min_cookies: Optional[int] = None,
        max_cookies: Optional[int] = None,
        has_local_storage: Optional[bool] = None,
    ) -> List[SessionInfo]:
        """
        Filter sessions by criteria.
        
        Args:
            sessions: List of SessionInfo to filter
            site_name: Filter by site name (substring match)
            browser: Filter by source browser
            min_cookies: Minimum cookie count
            max_cookies: Maximum cookie count
            has_local_storage: Filter by localStorage presence
            
        Returns:
            Filtered list of SessionInfo
        """
        filtered = []
        
        for session in sessions:
            if site_name and site_name.lower() not in session.site_name.lower():
                continue
            if browser and session.source_browser != browser:
                continue
            if min_cookies and session.cookie_count < min_cookies:
                continue
            if max_cookies and session.cookie_count > max_cookies:
                continue
            if has_local_storage is not None and session.has_local_storage != has_local_storage:
                continue
            
            filtered.append(session)
        
        return filtered
    
    def get_session_stats(self, session_files: List[str]) -> Dict:
        """
        Get aggregate statistics for multiple sessions.
        
        Returns:
            Dictionary with stats
        """
        total_cookies = 0
        total_size = 0
        sites = set()
        browsers = set()
        
        for session_file in session_files:
            info = self._get_session_info(Path(session_file))
            if info:
                total_cookies += info.cookie_count
                total_size += info.file_size
                sites.add(info.site_name)
                if info.source_browser:
                    browsers.add(info.source_browser)
        
        return {
            "session_count": len(session_files),
            "total_cookies": total_cookies,
            "total_size_bytes": total_size,
            "unique_sites": list(sites),
            "unique_browsers": list(browsers),
        }
