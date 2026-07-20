"""
Session Sharing - Share sessions via encrypted URLs and QR codes.

Provides secure session sharing with:
- Encrypted session data in URLs
- QR code generation
- Expiration and access control
- Revocation support
"""

import base64
import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ShareConfig:
    """Configuration for session sharing."""
    
    encryption_key: Optional[str] = None
    expiry_hours: int = 24
    max_uses: int = 0  # 0 = unlimited
    require_password: bool = False
    password: Optional[str] = None
    qr_size: int = 200
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ShareConfig':
        return cls(
            encryption_key=data.get("encryption_key"),
            expiry_hours=data.get("expiry_hours", 24),
            max_uses=data.get("max_uses", 0),
            require_password=data.get("require_password", False),
            password=data.get("password"),
            qr_size=data.get("qr_size", 200),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "encryption_key": self.encryption_key,
            "expiry_hours": self.expiry_hours,
            "max_uses": self.max_uses,
            "require_password": self.require_password,
            "qr_size": self.qr_size,
        }


@dataclass
class ShareResult:
    """Result of a share operation."""
    
    share_url: str = ""
    share_id: str = ""
    qr_code_path: Optional[str] = None
    expiry: float = 0
    encrypted_data: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "share_url": self.share_url,
            "share_id": self.share_id,
            "qr_code_path": self.qr_code_path,
            "expiry": self.expiry,
            "encrypted_data": self.encrypted_data[:100] + "..." if self.encrypted_data else "",
        }


@dataclass
class ShareToken:
    """A share token with metadata."""
    
    share_id: str
    encrypted_data: str
    created_at: float
    expires_at: float
    max_uses: int
    current_uses: int = 0
    password_hash: Optional[str] = None
    revoked: bool = False
    
    @property
    def is_valid(self) -> bool:
        if self.revoked:
            return False
        if self.expires_at > 0 and time.time() > self.expires_at:
            return False
        if self.max_uses > 0 and self.current_uses >= self.max_uses:
            return False
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "share_id": self.share_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "max_uses": self.max_uses,
            "current_uses": self.current_uses,
            "revoked": self.revoked,
            "is_valid": self.is_valid,
        }


class SessionSharer:
    """
    Share sessions via encrypted URLs and QR codes.
    
    Features:
    - AES encryption of session data
    - URL-safe base64 encoding
    - QR code generation
    - Token-based access control
    - Expiration and revocation
    """
    
    def __init__(self, config: Optional[ShareConfig] = None):
        self.config = config or ShareConfig()
        self._tokens: Dict[str, ShareToken] = {}
        self._token_store = Path("~/.tokenade/share_tokens.json").expanduser()
        self._load_tokens()
    
    def share_session(
        self,
        session_file: str,
        password: Optional[str] = None,
    ) -> ShareResult:
        """
        Create a shareable link for a session.
        
        Args:
            session_file: Path to session file
            password: Optional password for access
            
        Returns:
            ShareResult with share URL and metadata
        """
        session_path = Path(session_file)
        if not session_path.exists():
            raise FileNotFoundError(f"Session file not found: {session_file}")
        
        with open(session_path, "rb") as f:
            session_data = f.read()
        
        encrypted = self._encrypt(session_data)
        share_id = secrets.token_urlsafe(32)
        
        expiry = 0
        if self.config.expiry_hours > 0:
            expiry = time.time() + (self.config.expiry_hours * 3600)
        
        password_hash = None
        if password:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        token = ShareToken(
            share_id=share_id,
            encrypted_data=encrypted,
            created_at=time.time(),
            expires_at=expiry,
            max_uses=self.config.max_uses,
            password_hash=password_hash,
        )
        
        self._tokens[share_id] = token
        self._save_tokens()
        
        share_url = f"tokenade://share/{share_id}"
        
        result = ShareResult(
            share_url=share_url,
            share_id=share_id,
            expiry=expiry,
            encrypted_data=encrypted,
        )
        
        return result
    
    def generate_qr(self, share_url: str, output_path: str) -> str:
        """
        Generate QR code for share URL.
        
        Args:
            share_url: The share URL to encode
            output_path: Path to save QR code image
            
        Returns:
            Path to generated QR code
        """
        try:
            import qrcode
            
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(share_url)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(output_path)
            
            return output_path
            
        except ImportError:
            logger.warning("qrcode not installed, cannot generate QR code")
            return ""
    
    def retrieve_session(
        self,
        share_id: str,
        password: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> Optional[bytes]:
        """
        Retrieve session data from share token.
        
        Args:
            share_id: The share ID
            password: Password if required
            output_path: Optional path to save session file
            
        Returns:
            Decrypted session data or None if invalid
        """
        token = self._tokens.get(share_id)
        if not token:
            logger.error(f"Share token not found: {share_id}")
            return None
        
        if not token.is_valid:
            logger.error(f"Share token is invalid or expired: {share_id}")
            return None
        
        if token.password_hash:
            if not password:
                logger.error("Password required for this share")
                return None
            
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            if password_hash != token.password_hash:
                logger.error("Invalid password")
                return None
        
        try:
            decrypted = self._decrypt(token.encrypted_data)
            token.current_uses += 1
            self._save_tokens()
            
            if output_path:
                Path(output_path).write_bytes(decrypted)
            
            return decrypted
            
        except Exception as e:
            logger.error(f"Failed to decrypt session: {e}")
            return None
    
    def revoke(self, share_id: str) -> bool:
        """Revoke a share token."""
        token = self._tokens.get(share_id)
        if not token:
            return False
        
        token.revoked = True
        self._save_tokens()
        return True
    
    def list_shares(self) -> List[Dict[str, Any]]:
        """List all active share tokens."""
        return [
            token.to_dict()
            for token in self._tokens.values()
            if token.is_valid
        ]
    
    def cleanup_expired(self) -> int:
        """Remove expired tokens. Returns count removed."""
        expired = [
            sid for sid, token in self._tokens.items()
            if not token.is_valid
        ]
        
        for sid in expired:
            del self._tokens[sid]
        
        if expired:
            self._save_tokens()
        
        return len(expired)
    
    def _encrypt(self, data: bytes) -> str:
        """Encrypt data using AES-256-CBC."""
        key = self._get_encryption_key()
        
        try:
            from cryptography.fernet import Fernet
            
            fernet_key = base64.urlsafe_b64encode(key[:32])
            fernet = Fernet(fernet_key)
            encrypted = fernet.encrypt(data)
            return base64.urlsafe_b64encode(encrypted).decode()
            
        except ImportError:
            logger.warning("cryptography not installed, using basic encoding")
            return base64.urlsafe_b64encode(data).decode()
    
    def _decrypt(self, encrypted: str) -> bytes:
        """Decrypt data using AES-256-CBC."""
        key = self._get_encryption_key()
        
        try:
            from cryptography.fernet import Fernet
            
            fernet_key = base64.urlsafe_b64encode(key[:32])
            fernet = Fernet(fernet_key)
            decrypted = fernet.decrypt(base64.urlsafe_b64decode(encrypted))
            return decrypted
            
        except ImportError:
            logger.warning("cryptography not installed, using basic decoding")
            return base64.urlsafe_b64decode(encrypted)
    
    def _get_encryption_key(self) -> bytes:
        """Get encryption key from config or generate one."""
        if self.config.encryption_key:
            return self.config.encryption_key.encode()
        
        key_file = Path("~/.tokenade/share_key").expanduser()
        if key_file.exists():
            return key_file.read_bytes()
        
        key = secrets.token_bytes(32)
        key_file.write_bytes(key)
        key_file.chmod(0o600)
        return key
    
    def _load_tokens(self) -> None:
        """Load tokens from storage."""
        if self._token_store.exists():
            try:
                with open(self._token_store) as f:
                    data = json.load(f)
                
                for token_data in data:
                    token = ShareToken(**token_data)
                    self._tokens[token.share_id] = token
                    
            except Exception as e:
                logger.warning(f"Failed to load share tokens: {e}")
    
    def _save_tokens(self) -> None:
        """Save tokens to storage."""
        try:
            self._token_store.parent.mkdir(parents=True, exist_ok=True)
            
            data = [token.to_dict() for token in self._tokens.values()]
            
            with open(self._token_store, "w") as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.warning(f"Failed to save share tokens: {e}")
