"""
URL Shortener Integration for Session Sharing.

Provides secure session sharing via URL shorteners with:
- Password-protected encrypted sessions
- Multiple URL shortener backends
- Automatic cleanup of expired links
- Support for request.json in session files
"""

import base64
import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class URLShortenerConfig:
    """Configuration for URL shortener integration."""
    
    backend: str = "local"  # local, bitly, tinyurl, custom
    api_key: Optional[str] = None
    api_url: Optional[str] = None
    custom_domain: Optional[str] = None
    expiry_hours: int = 24
    require_password: bool = True
    password_min_length: int = 8
    max_uses: int = 0  # 0 = unlimited
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'URLShortenerConfig':
        return cls(
            backend=data.get("backend", "local"),
            api_key=data.get("api_key"),
            api_url=data.get("api_url"),
            custom_domain=data.get("custom_domain"),
            expiry_hours=data.get("expiry_hours", 24),
            require_password=data.get("require_password", True),
            password_min_length=data.get("password_min_length", 8),
            max_uses=data.get("max_uses", 0),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "api_url": self.api_url,
            "custom_domain": self.custom_domain,
            "expiry_hours": self.expiry_hours,
            "require_password": self.require_password,
            "password_min_length": self.password_min_length,
            "max_uses": self.max_uses,
        }


@dataclass
class ShortenedURL:
    """A shortened URL with metadata."""
    
    short_id: str
    original_url: str
    short_url: str
    created_at: float
    expires_at: float
    password_hash: Optional[str] = None
    max_uses: int = 0
    current_uses: int = 0
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
            "short_id": self.short_id,
            "original_url": self.original_url,
            "short_url": self.short_url,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "password_hash": self.password_hash,
            "max_uses": self.max_uses,
            "current_uses": self.current_uses,
            "revoked": self.revoked,
            "is_valid": self.is_valid,
        }


class URLShortenerBackend:
    """Base class for URL shortener backends."""
    
    def shorten(self, url: str) -> Optional[str]:
        """Shorten a URL. Returns shortened URL or None on failure."""
        raise NotImplementedError
    
    def expand(self, short_url: str) -> Optional[str]:
        """Expand a shortened URL. Returns original URL or None."""
        raise NotImplementedError
    
    def is_available(self) -> bool:
        """Check if this backend is available."""
        raise NotImplementedError


class LocalURLShortener(URLShortenerBackend):
    """Local URL shortener using tokenade:// protocol."""
    
    def __init__(self, base_url: str = "tokenade://share"):
        self.base_url = base_url
    
    def shorten(self, url: str) -> Optional[str]:
        """Create a local share URL."""
        short_id = secrets.token_urlsafe(16)
        return f"{self.base_url}/{short_id}"
    
    def expand(self, short_url: str) -> Optional[str]:
        """Extract share ID from local URL."""
        if short_url.startswith(self.base_url + "/"):
            return short_url[len(self.base_url) + 1:]
        return None
    
    def is_available(self) -> bool:
        return True


class BitlyURLShortener(URLShortenerBackend):
    """Bitly URL shortener backend."""
    
    def __init__(self, api_key: str, custom_domain: Optional[str] = None):
        self.api_key = api_key
        self.custom_domain = custom_domain or "bit.ly"
        self.api_url = "https://api-ssl.bitly.com/v4/shorten"
    
    def shorten(self, url: str) -> Optional[str]:
        """Shorten URL using Bitly API."""
        import urllib.request
        import urllib.error
        
        try:
            data = json.dumps({
                "long_url": url,
                "domain": self.custom_domain,
            }).encode()
            
            req = urllib.request.Request(
                self.api_url,
                data=data,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read())
                return result.get("link")
                
        except Exception as e:
            logger.error(f"Bitly shortening failed: {e}")
            return None
    
    def expand(self, short_url: str) -> Optional[str]:
        """Expand Bitly URL."""
        import urllib.request
        
        try:
            url = f"https://api-ssl.bitly.com/v4/expand?bitlink={short_url}"
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read())
                return result.get("long_url")
                
        except Exception as e:
            logger.error(f"Bitly expand failed: {e}")
            return None
    
    def is_available(self) -> bool:
        return bool(self.api_key)


class TinyURLShortener(URLShortenerBackend):
    """TinyURL URL shortener backend."""
    
    def __init__(self, custom_domain: Optional[str] = None):
        self.custom_domain = custom_domain
        self.api_url = "https://tinyurl.com/api-create.php"
    
    def shorten(self, url: str) -> Optional[str]:
        """Shorten URL using TinyURL API."""
        import urllib.request
        import urllib.parse
        
        try:
            params = urllib.parse.urlencode({"url": url})
            if self.custom_domain:
                params += f"&domain={self.custom_domain}"
            
            api_url = f"{self.api_url}?{params}"
            
            with urllib.request.urlopen(api_url) as response:
                return response.read().decode()
                
        except Exception as e:
            logger.error(f"TinyURL shortening failed: {e}")
            return None
    
    def expand(self, short_url: str) -> Optional[str]:
        """Expand TinyURL (follow redirects)."""
        import urllib.request
        
        try:
            req = urllib.request.Request(
                short_url,
                method="HEAD",
            )
            req.add_header("User-Agent", "Tokenade/1.0")
            
            with urllib.request.urlopen(req) as response:
                return response.url
                
        except Exception as e:
            logger.error(f"TinyURL expand failed: {e}")
            return None
    
    def is_available(self) -> bool:
        return True


class SessionURLShortener:
    """
    URL shortener for session sharing with password protection.
    
    Features:
    - Password-protected encrypted sessions
    - Multiple URL shortener backends
    - Automatic cleanup of expired links
    - Support for request.json in session files
    """
    
    def __init__(self, config: Optional[URLShortenerConfig] = None):
        self.config = config or URLShortenerConfig()
        self._backend = self._get_backend()
        self._urls: Dict[str, ShortenedURL] = {}
        self._url_store = Path("~/.tokenade/shortened_urls.json").expanduser()
        self._load_urls()
    
    def create_share(
        self,
        session_file: str,
        password: str,
        expiry_hours: Optional[int] = None,
        max_uses: Optional[int] = None,
        include_request_json: bool = False,
    ) -> Dict[str, Any]:
        """
        Create a password-protected share link for a session.
        
        Args:
            session_file: Path to session file
            password: Password for decryption (required)
            expiry_hours: Optional override for expiry
            max_uses: Optional override for max uses
            include_request_json: Include request.json in session
            
        Returns:
            Dictionary with share URL and metadata
        """
        session_path = Path(session_file)
        if not session_path.exists():
            raise FileNotFoundError(f"Session file not found: {session_file}")
        
        if len(password) < self.config.password_min_length:
            raise ValueError(
                f"Password must be at least {self.config.password_min_length} characters"
            )
        
        with open(session_path, "rb") as f:
            session_data = f.read()
        
        session_json = self._parse_session(session_data)
        
        if include_request_json:
            request_json = self._load_request_json(session_path.parent)
            if request_json:
                session_json["_request_config"] = request_json
        
        encrypted = self._encrypt_with_password(
            json.dumps(session_json).encode(),
            password,
        )
        
        short_id = secrets.token_urlsafe(16)
        expiry = expiry_hours or self.config.expiry_hours
        expires_at = time.time() + (expiry * 3600) if expiry > 0 else 0
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        original_url = f"tokenade://share/{short_id}?data={encrypted}"
        short_url = self._backend.shorten(original_url)
        
        if not short_url:
            short_url = original_url
        
        url_entry = ShortenedURL(
            short_id=short_id,
            original_url=original_url,
            short_url=short_url,
            created_at=time.time(),
            expires_at=expires_at,
            password_hash=password_hash,
            max_uses=max_uses or self.config.max_uses,
        )
        
        self._urls[short_id] = url_entry
        self._save_urls()
        
        return {
            "success": True,
            "short_url": short_url,
            "short_id": short_id,
            "expires_at": expires_at,
            "requires_password": True,
            "message": "Share link created. Receiver must enter password to decrypt.",
        }
    
    def retrieve_session(
        self,
        short_url: str,
        password: str,
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve session from a shortened URL with password.
        
        Args:
            short_url: The shortened URL or share ID
            password: Password for decryption
            output_path: Optional path to save session
            
        Returns:
            Dictionary with session data or error
        """
        short_id = self._extract_short_id(short_url)
        
        if not short_id:
            return {"success": False, "error": "Invalid share URL"}
        
        url_entry = self._urls.get(short_id)
        if not url_entry:
            return {"success": False, "error": "Share not found"}
        
        if not url_entry.is_valid:
            return {"success": False, "error": "Share expired or revoked"}
        
        if not url_entry.password_hash:
            return {"success": False, "error": "Share has no password protection"}
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if password_hash != url_entry.password_hash:
            return {"success": False, "error": "Invalid password"}
        
        try:
            encrypted_data = self._extract_encrypted_data(url_entry.original_url)
            if not encrypted_data:
                return {"success": False, "error": "No encrypted data in share"}
            
            decrypted = self._decrypt_with_password(encrypted_data, password)
            session_json = json.loads(decrypted)
            
            url_entry.current_uses += 1
            self._save_urls()
            
            if output_path:
                output = Path(output_path)
                output.write_text(json.dumps(session_json, indent=2))
            
            return {
                "success": True,
                "session": session_json,
                "output_path": output_path,
                "remaining_uses": (
                    url_entry.max_uses - url_entry.current_uses
                    if url_entry.max_uses > 0
                    else None
                ),
            }
            
        except Exception as e:
            return {"success": False, "error": f"Decryption failed: {e}"}
    
    def revoke(self, short_id: str) -> bool:
        """Revoke a share link."""
        url_entry = self._urls.get(short_id)
        if not url_entry:
            return False
        
        url_entry.revoked = True
        self._save_urls()
        return True
    
    def list_shares(self) -> List[Dict[str, Any]]:
        """List all active shares."""
        return [
            url_entry.to_dict()
            for url_entry in self._urls.values()
            if url_entry.is_valid
        ]
    
    def cleanup_expired(self) -> int:
        """Remove expired shares. Returns count removed."""
        expired = [
            sid for sid, url_entry in self._urls.items()
            if not url_entry.is_valid
        ]
        
        for sid in expired:
            del self._urls[sid]
        
        if expired:
            self._save_urls()
        
        return len(expired)
    
    def _get_backend(self) -> URLShortenerBackend:
        """Get the URL shortener backend."""
        if self.config.backend == "bitly" and self.config.api_key:
            return BitlyURLShortener(
                self.config.api_key,
                self.config.custom_domain,
            )
        elif self.config.backend == "tinyurl":
            return TinyURLShortener(self.config.custom_domain)
        else:
            return LocalURLShortener()
    
    def _extract_short_id(self, url_or_id: str) -> Optional[str]:
        """Extract short ID from URL or return as-is if it's an ID."""
        # Handle tokenade://share/ID format
        if "://share/" in url_or_id:
            parts = url_or_id.split("://share/")
            if len(parts) > 1:
                return parts[1].split("?")[0]
        # Handle /share/ID format
        if "/share/" in url_or_id:
            parts = url_or_id.split("/share/")
            if len(parts) > 1:
                return parts[1].split("?")[0]
        return url_or_id
    
    def _extract_encrypted_data(self, original_url: str) -> Optional[str]:
        """Extract encrypted data from original URL."""
        if "data=" in original_url:
            parts = original_url.split("data=")
            if len(parts) > 1:
                return parts[1].split("&")[0]
        return None
    
    def _parse_session(self, data: bytes) -> Dict[str, Any]:
        """Parse session data."""
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return {"raw_data": base64.b64encode(data).decode()}
    
    def _load_request_json(self, session_dir: Path) -> Optional[Dict[str, Any]]:
        """Load request.json if it exists in session directory."""
        request_file = session_dir / "request.json"
        if request_file.exists():
            try:
                with open(request_file) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load request.json: {e}")
        return None
    
    def _encrypt_with_password(self, data: bytes, password: str) -> str:
        """Encrypt data with password using PBKDF2 + Fernet."""
        try:
            from cryptography.fernet import Fernet
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            
            salt = secrets.token_bytes(16)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=480000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
            
            fernet = Fernet(key)
            encrypted = fernet.encrypt(data)
            
            result = base64.urlsafe_b64encode(salt + encrypted).decode()
            return result
            
        except ImportError:
            logger.warning("cryptography not installed, using basic encoding")
            return base64.urlsafe_b64encode(data).decode()
    
    def _decrypt_with_password(self, encrypted: str, password: str) -> bytes:
        """Decrypt data with password using PBKDF2 + Fernet."""
        try:
            from cryptography.fernet import Fernet
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            
            raw = base64.urlsafe_b64decode(encrypted)
            salt = raw[:16]
            encrypted_data = raw[16:]
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=480000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
            
            fernet = Fernet(key)
            decrypted = fernet.decrypt(encrypted_data)
            return decrypted
            
        except ImportError:
            logger.warning("cryptography not installed, using basic decoding")
            return base64.urlsafe_b64decode(encrypted)
    
    def _load_urls(self) -> None:
        """Load URLs from storage."""
        if self._url_store.exists():
            try:
                with open(self._url_store) as f:
                    data = json.load(f)
                
                for url_data in data:
                    # Remove is_valid if present (it's a computed property)
                    url_data.pop("is_valid", None)
                    url_entry = ShortenedURL(**url_data)
                    self._urls[url_entry.short_id] = url_entry
                    
            except Exception as e:
                logger.warning(f"Failed to load shortened URLs: {e}")
    
    def _save_urls(self) -> None:
        """Save URLs to storage."""
        try:
            self._url_store.parent.mkdir(parents=True, exist_ok=True)
            
            data = [url_entry.to_dict() for url_entry in self._urls.values()]
            
            with open(self._url_store, "w") as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.warning(f"Failed to save shortened URLs: {e}")
