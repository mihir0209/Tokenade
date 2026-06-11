"""
Direct Profile Injection - Cookie injection into browser profiles.

Allows injecting cookies directly into browser profile databases
without launching the browser, enabling session transfer to running browsers.
"""

import logging
import os
import shutil
import sqlite3
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class InjectionResult:
    """Result of cookie injection."""
    success: bool
    cookies_injected: int
    cookies_total: int
    profile_path: str
    backup_path: Optional[str] = None
    error: Optional[str] = None


class ProfileManager:
    """
    Manages browser profile cookie injection.
    
    Injects cookies directly into browser profile databases,
    allowing session transfer to running browsers.
    
    Usage:
        manager = ProfileManager()
        result = manager.inject_cookies(
            profile_path="/path/to/cookies.sqlite",
            cookies=cookies_list,
            browser="brave"
        )
    """
    
    # Chrome epoch offset (microseconds from 1601-01-01 to 1970-01-01)
    CHROME_EPOCH_OFFSET = 11644473600
    
    def inject_cookies(
        self,
        profile_path: str,
        cookies: List[Dict],
        browser: str = "chrome",
        backup: bool = True,
        verify: bool = True
    ) -> InjectionResult:
        """
        Inject cookies into browser profile.
        
        Args:
            profile_path: Path to browser profile directory or cookies database
            cookies: List of cookie dictionaries
            browser: Browser name (chrome, brave, edge, firefox, opera, vivaldi)
            backup: Create backup before modification
            verify: Verify injection succeeded
            
        Returns:
            InjectionResult with details
        """
        try:
            # Resolve profile path
            db_path = self._resolve_database_path(profile_path, browser)
            if not db_path:
                return InjectionResult(
                    success=False,
                    cookies_injected=0,
                    cookies_total=len(cookies),
                    profile_path=profile_path,
                    error="Could not locate cookies database"
                )
            
            # Create backup
            backup_path = None
            if backup:
                backup_path = self._create_backup(db_path)
            
            # Work on copy
            temp_fd, temp_db = tempfile.mkstemp(suffix='.db')
            os.close(temp_fd)
            shutil.copy2(db_path, temp_db)
            
            # Copy WAL and SHM files
            for suffix in ['-wal', '-shm']:
                src = db_path + suffix
                if os.path.exists(src):
                    shutil.copy2(src, temp_db + suffix)
            
            # Inject cookies
            injected = self._inject_into_database(temp_db, cookies, browser)
            
            # Copy back
            shutil.copy2(temp_db, db_path)
            for suffix in ['-wal', '-shm']:
                src = temp_db + suffix
                if os.path.exists(src):
                    shutil.copy2(src, db_path + suffix)
            
            # Cleanup temp file
            os.unlink(temp_db)
            
            # Verify if requested
            if verify:
                actual_count = self._count_cookies(db_path, browser)
                if actual_count < len(cookies):
                    logger.warning(f"Verification: expected {len(cookies)} cookies, found {actual_count}")
            
            return InjectionResult(
                success=True,
                cookies_injected=injected,
                cookies_total=len(cookies),
                profile_path=profile_path,
                backup_path=backup_path
            )
            
        except Exception as e:
            logger.error(f"Cookie injection failed: {e}")
            return InjectionResult(
                success=False,
                cookies_injected=0,
                cookies_total=len(cookies),
                profile_path=profile_path,
                error=str(e)
            )
    
    def _resolve_database_path(self, profile_path: str, browser: str) -> Optional[str]:
        """Resolve the actual cookies database path."""
        path = Path(profile_path)
        
        # If it's a file, use directly
        if path.is_file():
            return str(path)
        
        # If it's a directory, look for cookies database
        if path.is_dir():
            if browser.lower() in ["chrome", "brave", "edge", "opera", "vivaldi"]:
                # Chromium-based browsers
                cookies_db = path / "Default" / "Cookies"
                if cookies_db.exists():
                    return str(cookies_db)
            elif browser.lower() == "firefox":
                # Firefox
                cookies_db = path / "cookies.sqlite"
                if cookies_db.exists():
                    return str(cookies_db)
        
        return None
    
    def _create_backup(self, db_path: str) -> str:
        """Create timestamped backup of database."""
        timestamp = int(time.time())
        backup_path = f"{db_path}.backup.{timestamp}"
        shutil.copy2(db_path, backup_path)
        
        # Also backup WAL and SHM
        for suffix in ['-wal', '-shm']:
            src = db_path + suffix
            if os.path.exists(src):
                shutil.copy2(src, backup_path + suffix)
        
        logger.info(f"Backup created: {backup_path}")
        return backup_path
    
    def _inject_into_database(self, db_path: str, cookies: List[Dict], browser: str) -> int:
        """Inject cookies into database."""
        if browser.lower() in ["chrome", "brave", "edge", "opera", "vivaldi"]:
            return self._inject_chromium(db_path, cookies)
        elif browser.lower() == "firefox":
            return self._inject_firefox(db_path, cookies)
        else:
            raise ValueError(f"Unsupported browser: {browser}")
    
    def _inject_chromium(self, db_path: str, cookies: List[Dict]) -> int:
        """Inject cookies into Chromium-based browser database."""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        now_chrome = int((time.time() + self.CHROME_EPOCH_OFFSET) * 1000000)
        
        injected = 0
        for cookie in cookies:
            try:
                host = cookie.get('domain', '')
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                path = cookie.get('path', '/')
                secure = 1 if cookie.get('secure') else 0
                httponly = 1 if cookie.get('httpOnly') else 0
                
                # Map sameSite
                samesite_map = {'None': 0, 'Lax': 1, 'Strict': 2}
                samesite = samesite_map.get(cookie.get('sameSite', 'Lax'), 1)
                source_scheme = 2 if secure else 1
                source_port = 443 if secure else 80
                
                # Handle expiry
                expires = cookie.get('expires', 0)
                if expires and int(expires) > 0:
                    expires_int = int(expires)
                    # Convert milliseconds to seconds if needed
                    if expires_int > 1262304000000:
                        expires_int = expires_int // 1000
                    expires_utc = int((expires_int + self.CHROME_EPOCH_OFFSET) * 1000000)
                    has_expires = 1
                    is_persistent = 1
                else:
                    expires_utc = 0
                    has_expires = 0
                    is_persistent = 0
                
                # Insert cookie
                cursor.execute('''
                    INSERT OR REPLACE INTO cookies 
                    (creation_utc, host_key, top_frame_site_key, name, value, encrypted_value,
                     path, expires_utc, is_secure, is_httponly, last_access_utc, has_expires,
                     is_persistent, priority, samesite, source_scheme, source_port,
                     last_update_utc, source_type, has_cross_site_ancestor)
                    VALUES (?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, 0, 0)
                ''', (now_chrome, host, name, value, b'', path, expires_utc, secure, httponly,
                      now_chrome, has_expires, is_persistent, samesite, source_scheme, source_port,
                      now_chrome))
                injected += 1
            except Exception as e:
                logger.warning(f"Failed to inject cookie {name}: {e}")
        
        conn.commit()
        conn.close()
        
        return injected
    
    def _inject_firefox(self, db_path: str, cookies: List[Dict]) -> int:
        """Inject cookies into Firefox database."""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        now = int(time.time() * 1000000)  # microseconds
        
        injected = 0
        for cookie in cookies:
            try:
                host = cookie.get('domain', '')
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                path = cookie.get('path', '/')
                secure = 1 if cookie.get('secure') else 0
                httponly = 1 if cookie.get('httpOnly') else 0
                
                # Handle expiry
                expires = cookie.get('expires', 0)
                if expires and int(expires) > 0:
                    expires_int = int(expires)
                    # Convert to microseconds
                    if expires_int < 1262304000000:
                        expires_int = expires_int * 1000000
                    else:
                        expires_int = expires_int * 1000
                else:
                    expires_int = 0
                
                # Map sameSite
                samesite_map = {'None': 0, 'Lax': 1, 'Strict': 2}
                samesite = samesite_map.get(cookie.get('sameSite', 'Lax'), -1)
                
                # Insert cookie
                cursor.execute('''
                    INSERT OR REPLACE INTO moz_cookies 
                    (baseDomain, name, value, host, path, expiry, lastAccessed, 
                     creationTime, isSecure, isHttpOnly, sameSite, schemeMap)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ''', (host.lstrip('.'), name, value, host, path, expires_int, now,
                      now, secure, httponly, samesite))
                injected += 1
            except Exception as e:
                logger.warning(f"Failed to inject cookie {name}: {e}")
        
        conn.commit()
        conn.close()
        
        return injected
    
    def _count_cookies(self, db_path: str, browser: str) -> int:
        """Count cookies in database."""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            if browser.lower() in ["chrome", "brave", "edge", "opera", "vivaldi"]:
                cursor.execute("SELECT COUNT(*) FROM cookies")
            elif browser.lower() == "firefox":
                cursor.execute("SELECT COUNT(*) FROM moz_cookies")
            else:
                return 0
            
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except Exception:
            return 0
    
    def restore_profile(self, backup_path: str) -> bool:
        """
        Restore profile from backup.
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            True if successful
        """
        try:
            # Find the original database path
            if '.backup.' in backup_path:
                original = backup_path.split('.backup.')[0]
            else:
                original = backup_path
            
            # Restore main file
            shutil.copy2(backup_path, original)
            
            # Restore WAL and SHM
            for suffix in ['-wal', '-shm']:
                src = backup_path + suffix
                if os.path.exists(src):
                    shutil.copy2(src, original + suffix)
            
            logger.info(f"Profile restored from: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore profile: {e}")
            return False


def inject_session_to_profile(
    session_file: str,
    profile_path: str,
    browser: str = "chrome",
    backup: bool = True
) -> InjectionResult:
    """
    Convenience function to inject session file into browser profile.
    
    Args:
        session_file: Path to .tokenade session file
        profile_path: Path to browser profile
        browser: Browser name
        backup: Create backup before modification
        
    Returns:
        InjectionResult
    """
    import json
    
    with open(session_file) as f:
        session = json.load(f)
    
    cookies = session.get('cookies', [])
    
    manager = ProfileManager()
    return manager.inject_cookies(
        profile_path=profile_path,
        cookies=cookies,
        browser=browser,
        backup=backup
    )
