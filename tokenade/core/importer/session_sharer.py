"""
Session sharing: generate shareable encrypted links, QR codes, email/webhook delivery.

Features:
- Time-limited encrypted share links
- Usage-limited links (optional max uses)
- Password protection (optional)
- QR code generation for mobile transfer
- Email delivery (SMTP integration)
- Webhook delivery (POST to any URL)
- Session versioning (track changes over time)
- Self-contained HTML pages for offline sharing
"""

import base64
import hashlib
import json
import logging
import secrets
import smtplib
import time
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class ShareConfig:
    """Configuration for session sharing."""
    expiry_hours: int = 24  # Link expires after 24 hours
    max_uses: int = 0  # 0 = unlimited
    password_protected: bool = False
    password: Optional[str] = None
    # Email delivery
    email_recipients: List[str] = field(default_factory=list)
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    # Webhook delivery
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None  # HMAC secret for signing


@dataclass
class SessionVersion:
    """A version of a shared session."""
    version_id: str
    created_at: float
    cookies_count: int
    changes: str  # Description of what changed
    session_data: Dict


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
    - Email delivery (SMTP integration)
    - Webhook delivery (POST to any URL)
    - Session versioning (track changes over time)
    - Self-contained links (no server needed)
    """

    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = Path(storage_dir or "~/.tokenade/shared").expanduser()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.versions_dir = self.storage_dir / "versions"
        self.versions_dir.mkdir(parents=True, exist_ok=True)

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
        """Generate an encrypted share URL.

        If a password is provided, the payload is encrypted with a
        password-derived key (PBKDF2 + AES-256-GCM).  Without a password
        the data is encrypted with a random key that is embedded in the
        URL (obfuscation only — anyone with the URL can decrypt).
        """
        payload_json = json.dumps(session, separators=(",", ":")).encode()

        # Random salt and IV for AES-GCM
        salt = secrets.token_bytes(16)
        iv = secrets.token_bytes(12)

        if password:
            # Derive key from password (PBKDF2-HMAC-SHA256, 200k iterations)
            key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200000)
        else:
            # Random key (embedded later so the URL is self-contained)
            key = secrets.token_bytes(32)

        # AES-256-GCM encryption
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(iv, payload_json, None)  # includes tag

        # Build binary payload: salt(16) + iv(12) + key(32, only if no password) + ciphertext
        parts = [salt, iv]
        if not password:
            parts.append(key)
        parts.append(ciphertext)
        raw = b"".join(parts)

        payload_b64 = base64.urlsafe_b64encode(raw).decode().rstrip("=")
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
        Load session from an encrypted share URL.

        Returns:
            Session data or None if invalid / wrong password
        """
        try:
            # Parse URL
            if share_url.startswith("tokenade://share/"):
                payload_b64 = share_url[len("tokenade://share/"):]
            else:
                payload_b64 = share_url

            # Restore base64 padding
            payload_b64 += "=" * (4 - len(payload_b64) % 4) if len(payload_b64) % 4 else ""

            raw = base64.urlsafe_b64decode(payload_b64)

            # Binary layout: salt(16) + iv(12) + [key(32)] + ciphertext
            salt = raw[:16]
            iv = raw[16:28]

            if password:
                # Derive key from password
                key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200000)
                ciphertext = raw[28:]
            else:
                # Key is embedded in the payload
                key = raw[28:60]
                ciphertext = raw[60:]

            # AES-256-GCM decryption
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            aesgcm = AESGCM(key)
            payload_json = aesgcm.decrypt(iv, ciphertext, None)
            payload = json.loads(payload_json)

            return payload

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

    def send_email(
        self,
        session: Dict,
        config: ShareConfig,
        subject: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Send session share link via email.

        Returns:
            Tuple of (success, message)
        """
        if not config.smtp_host:
            return False, "SMTP host not configured"
        if not config.email_recipients:
            return False, "No email recipients"

        # Create share link
        share_url, session_id = self.create_share_link(session, config)

        site_name = session.get("site_name", "Unknown")
        subject = subject or f"Tokenade Session Share: {site_name}"

        # Build email body
        body = f"""Tokenade Shared Session

Site: {site_name}
Cookies: {len(session.get('cookies', []))}
Expires: {config.expiry_hours} hours from now
{'Password protected: Yes' if config.password_protected else ''}

To import this session:
1. Install Tokenade: pip install tokenade
2. Run: tokenade import {share_url}

Or open this link directly in your browser to download the session file.

---
Generated by Tokenade v2.5.0
"""

        try:
            msg = MIMEMultipart()
            msg["From"] = config.smtp_from or config.smtp_user
            msg["To"] = ", ".join(config.email_recipients)
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
                server.starttls()
                if config.smtp_user and config.smtp_password:
                    server.login(config.smtp_user, config.smtp_password)
                server.sendmail(
                    config.smtp_from or config.smtp_user,
                    config.email_recipients,
                    msg.as_string(),
                )

            logger.info(f"Email sent to {len(config.email_recipients)} recipients")
            return True, f"Email sent to {len(config.email_recipients)} recipients"

        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False, str(e)

    def send_webhook(
        self,
        session: Dict,
        config: ShareConfig,
    ) -> Tuple[bool, str]:
        """
        Send session data to a webhook URL via HTTP POST.

        Returns:
            Tuple of (success, message)
        """
        import hmac
        import urllib.request
        import urllib.error

        if not config.webhook_url:
            return False, "Webhook URL not configured"

        # Validate URL
        parsed = urlparse(config.webhook_url)
        if parsed.scheme not in ("http", "https"):
            return False, "Invalid webhook URL scheme"

        # Create share link
        share_url, session_id = self.create_share_link(session, config)

        # Build payload
        payload = {
            "event": "session_shared",
            "session_id": session_id,
            "share_url": share_url,
            "site_name": session.get("site_name", "unknown"),
            "cookies_count": len(session.get("cookies", [])),
            "expires_in_hours": config.expiry_hours,
            "password_protected": config.password_protected,
            "timestamp": time.time(),
        }

        # Sign payload if secret is provided
        headers = {"Content-Type": "application/json"}
        if config.webhook_secret:
            signature = hmac.HMAC(
                config.webhook_secret.encode(),
                json.dumps(payload, separators=(",", ":")).encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Tokenade-Signature"] = f"sha256={signature}"

        try:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            req = urllib.request.Request(
                config.webhook_url,
                data=data,
                headers=headers,
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                status_code = resp.getcode()
                response_text = resp.read().decode("utf-8", errors="replace")

            if 200 <= status_code < 300:
                logger.info(f"Webhook delivered to {config.webhook_url}")
                return True, f"Webhook delivered (HTTP {status_code})"
            else:
                return False, f"Webhook failed (HTTP {status_code}): {response_text}"

        except urllib.error.HTTPError as e:
            logger.error(f"Webhook delivery failed: HTTP {e.code}")
            return False, f"Webhook failed (HTTP {e.code}): {e.read().decode('utf-8', errors='replace')}"
        except Exception as e:
            logger.error(f"Webhook delivery failed: {e}")
            return False, str(e)

    def create_version(
        self,
        session: Dict,
        changes: str = "Initial version",
    ) -> str:
        """
        Create a new version of a session.

        Returns:
            Version ID
        """
        site_name = session.get("site_name", "unknown")
        version_id = f"{site_name}_{int(time.time())}_{secrets.token_hex(4)}"

        version = SessionVersion(
            version_id=version_id,
            created_at=time.time(),
            cookies_count=len(session.get("cookies", [])),
            changes=changes,
            session_data=session,
        )

        # Save version
        version_path = self.versions_dir / f"{version_id}.json"
        with open(version_path, "w") as f:
            json.dump({
                "version_id": version.version_id,
                "created_at": version.created_at,
                "cookies_count": version.cookies_count,
                "changes": version.changes,
                "session_data": version.session_data,
            }, f, indent=2)

        logger.info(f"Created session version: {version_id}")
        return version_id

    def list_versions(self, site_name: Optional[str] = None) -> List[Dict]:
        """List all session versions, optionally filtered by site name."""
        versions = []

        for path in self.versions_dir.glob("*.json"):
            try:
                with open(path, "r") as f:
                    data = json.load(f)

                if site_name and not data.get("version_id", "").startswith(site_name):
                    continue

                versions.append({
                    "version_id": data["version_id"],
                    "created_at": data["created_at"],
                    "cookies_count": data["cookies_count"],
                    "changes": data["changes"],
                })
            except Exception as e:
                logger.warning(f"Failed to load version {path}: {e}")

        return sorted(versions, key=lambda v: v["created_at"], reverse=True)

    def load_version(self, version_id: str) -> Optional[Dict]:
        """Load a specific session version."""
        version_path = self.versions_dir / f"{version_id}.json"

        if not version_path.exists():
            return None

        try:
            with open(version_path, "r") as f:
                data = json.load(f)
            return data.get("session_data")
        except Exception:
            return None

    def rollback_version(self, version_id: str) -> Optional[Dict]:
        """
        Rollback to a previous session version.

        Returns:
            The session data from the specified version, or None
        """
        session_data = self.load_version(version_id)
        if session_data:
            logger.info(f"Rolled back to version: {version_id}")
        return session_data

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
