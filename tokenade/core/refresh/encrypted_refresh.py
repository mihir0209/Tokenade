"""
Encrypted Session Refresh Pipeline.

Handles refresh of encrypted .tokenade files by:
1. Decrypting the session
2. Performing OAuth refresh or cookie re-export
3. Re-encrypting the result

This ensures encrypted sessions can be automatically refreshed
without manual decrypt/refresh/re-encrypt steps.

Usage:
    pipeline = EncryptedRefreshPipeline()
    result = pipeline.refresh(
        session_file="gmail.tokenade",
        password="my-password",
        source_browser="firefox",
    )
"""

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class EncryptedRefreshResult:
    """Result of encrypted session refresh."""
    success: bool
    session_file: str
    method: str  # "oauth" or "cookie"
    error: Optional[str] = None
    duration_ms: float = 0.0
    was_encrypted: bool = True
    tokens_refreshed: int = 0


class EncryptedRefreshPipeline:
    """
    Refresh encrypted .tokenade sessions automatically.

    Usage:
        pipeline = EncryptedRefreshPipeline()
        result = pipeline.refresh(
            session_file="gmail.tokenade",
            password="my-password",
            source_browser="firefox",
        )
    """

    def refresh(
        self,
        session_file: str,
        password: Optional[str] = None,
        key_file: Optional[str] = None,
        source_browser: str = "firefox",
        source_profile: Optional[str] = None,
        force: bool = False,
    ) -> EncryptedRefreshResult:
        """
        Refresh an encrypted session file.

        Args:
            session_file: Path to .tokenade file (may be encrypted)
            password: Decryption password
            key_file: Path to key file (alternative to password)
            source_browser: Source browser for cookie refresh
            source_profile: Source profile name
            force: Force refresh even if not expired

        Returns:
            EncryptedRefreshResult
        """
        start_time = time.time()
        path = Path(session_file)

        if not path.exists():
            return EncryptedRefreshResult(
                success=False,
                session_file=session_file,
                method="unknown",
                error=f"File not found: {session_file}",
                duration_ms=(time.time() - start_time) * 1000,
            )

        # Detect if encrypted
        is_encrypted = self._is_encrypted(path)

        if is_encrypted and not password and not key_file:
            return EncryptedRefreshResult(
                success=False,
                session_file=session_file,
                method="unknown",
                error="Session is encrypted. Provide --password or --key-file",
                was_encrypted=True,
                duration_ms=(time.time() - start_time) * 1000,
            )

        try:
            # Step 1: Decrypt if needed
            if is_encrypted:
                session = self._decrypt_session(path, password, key_file)
                if session is None:
                    return EncryptedRefreshResult(
                        success=False,
                        session_file=session_file,
                        method="unknown",
                        error="Decryption failed — wrong password or corrupted file",
                        was_encrypted=True,
                        duration_ms=(time.time() - start_time) * 1000,
                    )
            else:
                with open(path) as f:
                    session = json.load(f)

            # Step 2: Check if refresh is needed
            if not force and not self._needs_refresh(session):
                return EncryptedRefreshResult(
                    success=True,
                    session_file=session_file,
                    method="none",
                    error=None,
                    was_encrypted=is_encrypted,
                    duration_ms=(time.time() - start_time) * 1000,
                )

            # Step 3: Perform refresh
            has_oauth = session.get("oauth_config") is not None
            method = "oauth" if has_oauth else "cookie"

            if has_oauth:
                refreshed_session = self._refresh_oauth(session)
            else:
                refreshed_session = self._refresh_cookie(
                    session, source_browser, source_profile
                )

            if refreshed_session is None:
                return EncryptedRefreshResult(
                    success=False,
                    session_file=session_file,
                    method=method,
                    error="Refresh failed",
                    was_encrypted=is_encrypted,
                    duration_ms=(time.time() - start_time) * 1000,
                )

            # Step 4: Re-encrypt if was encrypted
            if is_encrypted:
                self._encrypt_session(refreshed_session, path, password, key_file)
            else:
                with open(path, "w") as f:
                    json.dump(refreshed_session, f, indent=2)

            logger.info(f"Session refreshed: {session_file} (method={method}, encrypted={is_encrypted})")

            return EncryptedRefreshResult(
                success=True,
                session_file=session_file,
                method=method,
                was_encrypted=is_encrypted,
                tokens_refreshed=1,
                duration_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Encrypted refresh failed: {e}")
            return EncryptedRefreshResult(
                success=False,
                session_file=session_file,
                method="unknown",
                error=str(e),
                was_encrypted=is_encrypted,
                duration_ms=(time.time() - start_time) * 1000,
            )

    def _is_encrypted(self, path: Path) -> bool:
        """Check if a file is encrypted."""
        try:
            with open(path) as f:
                data = json.load(f)
            return False  # Valid JSON = not encrypted
        except (json.JSONDecodeError, UnicodeDecodeError):
            return True  # Can't parse as JSON = likely encrypted

    def _decrypt_session(
        self, path: Path, password: Optional[str], key_file: Optional[str]
    ) -> Optional[Dict]:
        """Decrypt an encrypted session file."""
        try:
            from tokenade.core.security.aes_gcm import AESGCMEncryption

            encryption = AESGCMEncryption()

            if key_file:
                key = encryption.derive_key_from_file(key_file)
            elif password:
                key = encryption.derive_key(password)
            else:
                return None

            encrypted_data = path.read_bytes()
            decrypted_data = encryption.decrypt(encrypted_data, key)
            return json.loads(decrypted_data.decode("utf-8"))

        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return None

    def _encrypt_session(
        self,
        session: Dict,
        path: Path,
        password: Optional[str],
        key_file: Optional[str],
    ):
        """Encrypt and save a session."""
        from tokenade.core.security.aes_gcm import AESGCMEncryption

        encryption = AESGCMEncryption()

        if key_file:
            key = encryption.derive_key_from_file(key_file)
        elif password:
            key = encryption.derive_key(password)
        else:
            raise ValueError("No encryption key provided")

        session_json = json.dumps(session, indent=2).encode("utf-8")
        encrypted_data = encryption.encrypt(session_json, key)
        path.write_bytes(encrypted_data)

    def _needs_refresh(self, session: Dict) -> bool:
        """Check if session needs refresh."""
        import time

        # Check OAuth tokens
        tokens = session.get("tokens", [])
        for t in tokens:
            if t.get("type") == "access_token":
                expires_at = t.get("expires_at")
                if expires_at and time.time() >= expires_at:
                    return True

        # Check cookie expiry
        cookies = session.get("cookies", [])
        now = time.time()
        for cookie in cookies:
            expires = cookie.get("expires", 0)
            if expires and int(expires) > 0:
                expires_int = int(expires)
                if expires_int > 1262304000000:
                    expires_int = expires_int // 1000
                if expires_int < now:
                    return True

        return False

    def _refresh_oauth(self, session: Dict) -> Optional[Dict]:
        """Refresh using OAuth token refresh."""
        from tokenade.core.refresh.oauth_refresh import (
            SessionOAuthManager,
            OAuthConfig,
        )
        import tempfile
        import os

        # Create temp file to use SessionOAuthManager
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".tokenade", delete=False
        ) as tmp:
            json.dump(session, tmp)
            tmp_path = tmp.name

        try:
            manager = SessionOAuthManager(tmp_path)
            result = manager.refresh()

            if result.success:
                # Reload the updated session
                with open(tmp_path) as f:
                    return json.load(f)
            return None
        finally:
            os.unlink(tmp_path)

    def _refresh_cookie(
        self,
        session: Dict,
        source_browser: str,
        source_profile: Optional[str],
    ) -> Optional[Dict]:
        """Refresh using cookie re-export from source browser."""
        from tokenade.core.refresh.health_checker import SessionRefresher
        import tempfile
        import os

        # Create temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".tokenade", delete=False
        ) as tmp:
            json.dump(session, tmp)
            tmp_path = tmp.name

        try:
            refresher = SessionRefresher()
            result = refresher.refresh(
                session_file=tmp_path,
                source_browser=source_browser,
                source_profile=source_profile,
            )

            if result.success:
                with open(tmp_path) as f:
                    return json.load(f)
            return None
        finally:
            os.unlink(tmp_path)


def batch_encrypted_refresh(
    sessions_dir: str,
    password: Optional[str] = None,
    key_file: Optional[str] = None,
    source_browser: str = "firefox",
    force: bool = False,
) -> Dict[str, EncryptedRefreshResult]:
    """
    Batch refresh all .tokenade files in a directory.

    Handles both encrypted and unencrypted files.

    Args:
        sessions_dir: Directory containing .tokenade files
        password: Decryption password (for encrypted files)
        key_file: Key file path (alternative to password)
        source_browser: Source browser for cookie refresh
        force: Force refresh even if not expired

    Returns:
        Dict of filename -> EncryptedRefreshResult
    """
    pipeline = EncryptedRefreshPipeline()
    results = {}

    sessions_path = Path(sessions_dir)
    if not sessions_path.exists():
        logger.error(f"Directory not found: {sessions_dir}")
        return results

    for session_file in sorted(sessions_path.glob("*.tokenade")):
        result = pipeline.refresh(
            session_file=str(session_file),
            password=password,
            key_file=key_file,
            source_browser=source_browser,
            force=force,
        )
        results[session_file.name] = result

    return results
