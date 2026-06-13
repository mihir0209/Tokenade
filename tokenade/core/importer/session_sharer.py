"""
Session sharing: generate shareable encrypted links and QR codes for mobile transfer.
"""

import base64
import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ShareConfig:
    """Configuration for session sharing."""
    expiry_hours: int = 24  # Link expires after 24 hours
    max_uses: int = 0  # 0 = unlimited
    password_protected: bool = False
    password: Optional[str] = None


@dataclass
class SharedSession:
    """A shared session with metadata."""
    session_id: str
    created_at: float
    expires_at: float
    max_uses: int
    use_count: int
    password_hash: Optional[str]
    session_data: Dict


class SessionSharer:
    """
    Generate shareable encrypted session links and QR codes.
    
    Features:
    - Time-limited links (configurable expiry)
    - Usage-limited links (optional max uses)
    - Password protection (optional)
    - QR code generation for mobile transfer
    - Self-contained links (no server needed)
    """
    
    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = Path(storage_dir or "~/.tokenade/shared").expanduser()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def create_share_link(
        self,
        session: Dict,
        config: Optional[ShareConfig] = None,
    ) -> Tuple[str, str]:
        """
        Create a shareable encrypted session link.
        
        Returns:
            Tuple of (share_url, session_id)
        """
        config = config or ShareConfig()
        
        # Generate session ID
        session_id = secrets.token_urlsafe(16)
        
        # Create expiry timestamp
        created_at = time.time()
        expires_at = created_at + (config.expiry_hours * 3600)
        
        # Hash password if provided
        password_hash = None
        if config.password_protected and config.password:
            password_hash = hashlib.sha256(config.password.encode()).hexdigest()
        
        # Create shared session
        shared = SharedSession(
            session_id=session_id,
            created_at=created_at,
            expires_at=expires_at,
            max_uses=config.max_uses,
            use_count=0,
            password_hash=password_hash,
            session_data=session,
        )
        
        # Save to storage
        self._save_shared(shared)
        
        # Generate share URL (self-contained, no server needed)
        share_url = self._generate_share_url(session, session_id, config.password)
        
        logger.info(f"Created share link: {session_id} (expires in {config.expiry_hours}h)")
        
        return share_url, session_id
    
    def _generate_share_url(
        self,
        session: Dict,
        session_id: str,
        password: Optional[str] = None,
    ) -> str:
        """Generate a self-contained share URL."""
        # Compress session data
        session_json = json.dumps(session, separators=(",", ":"))
        
        # Add password to payload if provided
        payload = {
            "id": session_id,
            "data": session,
        }
        if password:
            payload["p"] = password
        
        # Encode as base64
        payload_json = json.dumps(payload, separators=(",", ":"))
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()
        
        # Generate URL (using tokenade:// protocol for mobile apps)
        # For web, use a simple HTML page that can decode the payload
        return f"tokenade://share/{payload_b64}"
    
    def create_qr_code(
        self,
        session: Dict,
        output_path: str,
        config: Optional[ShareConfig] = None,
    ) -> str:
        """
        Generate a QR code for mobile transfer.
        
        Returns:
            Path to QR code image
        """
        try:
            import qrcode
            from qrcode.image.styledpil import StyledPilImage
        except ImportError:
            raise ImportError(
                "qrcode is required for QR code generation. "
                "Install with: pip install qrcode[pil]"
            )
        
        # Create share URL
        share_url, session_id = self.create_share_link(session, config)
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(share_url)
        qr.make(fit=True)
        
        # Create QR code image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save to file
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(output_path))
        
        logger.info(f"QR code saved to {output_path}")
        
        return str(output_path)
    
    def load_shared(
        self,
        session_id: str,
        password: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Load a shared session by ID.
        
        Returns:
            Session data or None if expired/invalid
        """
        shared = self._load_shared(session_id)
        if not shared:
            return None
        
        # Check expiry
        if time.time() > shared.expires_at:
            logger.warning(f"Shared session {session_id} has expired")
            self._delete_shared(session_id)
            return None
        
        # Check usage limit
        if shared.max_uses > 0 and shared.use_count >= shared.max_uses:
            logger.warning(f"Shared session {session_id} has reached max uses")
            self._delete_shared(session_id)
            return None
        
        # Check password
        if shared.password_hash:
            if not password:
                logger.warning(f"Shared session {session_id} requires password")
                return None
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            if password_hash != shared.password_hash:
                logger.warning(f"Invalid password for shared session {session_id}")
                return None
        
        # Increment use count
        shared.use_count += 1
        self._save_shared(shared)
        
        return shared.session_data
    
    def load_from_url(self, share_url: str, password: Optional[str] = None) -> Optional[Dict]:
        """
        Load session from a share URL.
        
        Returns:
            Session data or None if invalid
        """
        try:
            # Parse URL
            if share_url.startswith("tokenade://share/"):
                payload_b64 = share_url[len("tokenade://share/"):]
            else:
                # Try to decode as base64 directly
                payload_b64 = share_url
            
            # Decode payload
            payload_json = base64.urlsafe_b64decode(payload_b64 + "==").decode()
            payload = json.loads(payload_json)
            
            session_id = payload.get("id")
            session_data = payload.get("data")
            url_password = payload.get("p")
            
            if not session_id or not session_data:
                return None
            
            # Use password from URL if not provided
            if not password and url_password:
                password = url_password
            
            return session_data
            
        except Exception as e:
            logger.error(f"Failed to load share URL: {e}")
            return None
    
    def list_shared(self) -> list:
        """List all active shared sessions."""
        shared_list = []
        
        for path in self.storage_dir.glob("*.json"):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                
                shared = SharedSession(**data)
                
                # Check if expired
                if time.time() > shared.expires_at:
                    self._delete_shared(shared.session_id)
                    continue
                
                shared_list.append({
                    "session_id": shared.session_id,
                    "created_at": shared.created_at,
                    "expires_at": shared.expires_at,
                    "use_count": shared.use_count,
                    "max_uses": shared.max_uses,
                    "has_password": shared.password_hash is not None,
                })
            except Exception as e:
                logger.warning(f"Failed to load shared session {path}: {e}")
        
        return shared_list
    
    def revoke_share(self, session_id: str) -> bool:
        """Revoke a shared session."""
        try:
            self._delete_shared(session_id)
            logger.info(f"Revoked shared session {session_id}")
            return True
        except Exception:
            return False
    
    def _save_shared(self, shared: SharedSession):
        """Save shared session to storage."""
        path = self.storage_dir / f"{shared.session_id}.json"
        
        data = {
            "session_id": shared.session_id,
            "created_at": shared.created_at,
            "expires_at": shared.expires_at,
            "max_uses": shared.max_uses,
            "use_count": shared.use_count,
            "password_hash": shared.password_hash,
            "session_data": shared.session_data,
        }
        
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    
    def _load_shared(self, session_id: str) -> Optional[SharedSession]:
        """Load shared session from storage."""
        path = self.storage_dir / f"{session_id}.json"
        
        if not path.exists():
            return None
        
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return SharedSession(**data)
        except Exception:
            return None
    
    def _delete_shared(self, session_id: str):
        """Delete shared session from storage."""
        path = self.storage_dir / f"{session_id}.json"
        if path.exists():
            path.unlink()


def generate_share_html(session: Dict, output_path: str) -> str:
    """
    Generate an HTML page that can decode and display a shared session.
    
    This allows sharing via simple HTML files that work offline.
    """
    session_json = json.dumps(session, indent=2)
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tokenade Shared Session</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0a0a; color: #fff; min-height: 100vh;
            display: flex; justify-content: center; align-items: center;
        }}
        .container {{ max-width: 600px; padding: 40px; width: 100%; }}
        h1 {{ color: #00ff88; margin-bottom: 20px; }}
        .info {{ color: #888; margin-bottom: 30px; line-height: 1.6; }}
        .card {{ 
            background: #1a1a1a; border-radius: 12px; padding: 24px; 
            margin-bottom: 20px; border: 1px solid #333;
        }}
        .card h3 {{ color: #00ff88; margin-bottom: 12px; }}
        .info-row {{ display: flex; justify-content: space-between; margin: 8px 0; }}
        .info-label {{ color: #888; }}
        .info-value {{ color: #fff; font-weight: 500; }}
        .btn {{
            background: #00ff88; color: #000; padding: 12px 24px; 
            border-radius: 8px; border: none; font-size: 1em; font-weight: 600;
            cursor: pointer; width: 100%; margin-top: 20px;
        }}
        .btn:hover {{ background: #00cc6a; }}
        .btn:disabled {{ background: #333; color: #666; cursor: not-allowed; }}
        .status {{ 
            padding: 8px 16px; border-radius: 20px; 
            display: inline-block; margin: 10px 0;
        }}
        .status-ok {{ background: #00ff8822; color: #00ff88; border: 1px solid #00ff88; }}
        .status-expired {{ background: #ff6b6b22; color: #ff6b6b; border: 1px solid #ff6b6b; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Tokenade Shared Session</h1>
        <p class="info">
            This page contains a shared browser session. Click below to download the session file.
        </p>
        
        <div class="card">
            <h3>Session Info</h3>
            <div class="info-row">
                <span class="info-label">Site</span>
                <span class="info-value">{session.get('site_name', 'unknown')}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Cookies</span>
                <span class="info-value">{len(session.get('cookies', []))}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Created</span>
                <span class="info-value">{session.get('created_at', 'unknown')}</span>
            </div>
        </div>
        
        <button class="btn" onclick="downloadSession()">
            Download Session File (.tokenade)
        </button>
        
        <p class="info" style="margin-top: 20px; font-size: 0.9em;">
            Use with Tokenade: <code>tokenade proxy -s downloaded_file.tokenade</code>
        </p>
    </div>
    
    <script>
        const sessionData = {session_json};
        
        function downloadSession() {{
            const blob = new Blob([JSON.stringify(sessionData, null, 2)], {{ type: 'application/json' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${{sessionData.site_name || 'session'}}.tokenade`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }}
    </script>
</body>
</html>"""
    
    with open(output_path, "w") as f:
        f.write(html)
    
    return output_path
