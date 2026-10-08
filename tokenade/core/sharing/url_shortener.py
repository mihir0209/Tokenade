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

    def __init__(
        self,
        config: Optional[URLShortenerConfig] = None,
        *,
        supabase_config: Any = None,
    ):
        self.config = config or URLShortenerConfig()
        self._backend = self._get_backend()
        self._urls: Dict[str, ShortenedURL] = {}
        self._url_store = Path("~/.tokenade/shortened_urls.json").expanduser()
        self._supabase_config = supabase_config
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

        # Preserve original basename for receiver default output path
        file_name = session_path.name
        if not file_name.endswith(".tokenade"):
            file_name = f"{session_path.stem}.tokenade"
        meta = session_json.get("metadata")
        if not isinstance(meta, dict):
            meta = {}
            session_json["metadata"] = meta
        meta["file_name"] = file_name

        if include_request_json:
            request_json = self._load_request_json(session_path.parent)
            if request_json:
                session_json["_request_config"] = request_json

        from tokenade.core.sharing.supabase_store import (
            MAX_CIPHERTEXT_CHARS,
            MAX_EMBEDDED_URL_CHARS,
            SupabaseShareStore,
            SupabaseConfig,
        )

        # Shrink full-profile dumps so remote share stays under RPC limit
        session_json, prune_note = self._fit_session_for_remote_share(session_json)

        encrypted = self._encrypt_with_password(
            json.dumps(session_json, separators=(",", ":")).encode(),
            password,
        )
        ct_len = len(encrypted)

        short_id = secrets.token_urlsafe(16)
        expiry = expiry_hours or self.config.expiry_hours
        expires_at = time.time() + (expiry * 3600) if expiry > 0 else 0

        password_hash = hashlib.sha256(password.encode()).hexdigest()

        # Embed payload only when small enough for local store / paste
        can_embed = ct_len <= MAX_EMBEDDED_URL_CHARS
        original_url = (
            f"tokenade://share/{short_id}?data={encrypted}"
            if can_embed
            else f"tokenade://share/{short_id}"
        )
        local_ref = f"tokenade://share/{short_id}"

        remote = None
        remote_error = ""
        remote_source = ""
        remote_code = ""
        try:
            sb_cfg = getattr(self, "_supabase_config", None) or SupabaseConfig.from_env()
            store = SupabaseShareStore(sb_cfg)
            if store.available:
                if ct_len > MAX_CIPHERTEXT_CHARS:
                    remote_error = (
                        f"ciphertext too large ({ct_len} chars; max {MAX_CIPHERTEXT_CHARS}). "
                        "Export a site-scoped session or transfer the .tokenade file directly."
                    )
                    remote_code = "payload_too_large"
                else:
                    remote = store.put_share(
                        short_id,
                        encrypted,
                        expires_at=expires_at,
                        max_uses=max_uses or self.config.max_uses,
                    )
                    remote_source = store.config.source
                    if remote and remote.get("success"):
                        logger.info(
                            "Uploaded share %s to Supabase (%s)", short_id, remote_source
                        )
                    else:
                        remote_error = str((remote or {}).get("error") or remote)
                        remote_code = str((remote or {}).get("code") or "")
                        remote = None
        except Exception as e:
            remote_error = str(e)
            logger.warning("Supabase upload failed: %s", e)

        short_url = None
        try:
            if remote and remote.get("success"):
                short_url = local_ref
            elif self._backend.__class__.__name__ == "LocalURLShortener":
                short_url = local_ref
            elif can_embed:
                short_url = self._backend.shorten(original_url)
        except Exception as e:
            logger.debug("shorten failed: %s", e)
            short_url = None

        if not short_url:
            short_url = local_ref

        # Never persist multi-MB ?data= blobs into shortened_urls.json
        store_original = original_url if can_embed else local_ref
        url_entry = ShortenedURL(
            short_id=short_id,
            original_url=store_original,
            short_url=short_url,
            created_at=time.time(),
            expires_at=expires_at,
            password_hash=password_hash,
            max_uses=max_uses or self.config.max_uses,
        )

        self._urls[short_id] = url_entry
        self._save_urls()

        transport = "supabase" if remote and remote.get("success") else "embedded"
        if transport == "embedded" and not can_embed:
            # Large payload, remote failed — share id alone cannot retrieve
            transport = "local-ref-only"

        msg = (
            f"Share created via {transport}"
            + (f" ({remote_source})" if remote_source and transport == "supabase" else "")
            + ". Password is never uploaded. "
            "Receiver: python3 -m tokenade share-url retrieve <short_id|full_url> "
            f"--password '...' -o {file_name}"
        )
        if prune_note:
            msg += f" [{prune_note}]"
        if remote_error and transport != "supabase":
            msg += f" (remote unavailable: {remote_error[:160]})"
        if transport == "local-ref-only":
            msg += (
                " WARNING: payload too large for remote and embedded URL; "
                "copy the .tokenade file instead or re-export with domain filter."
            )
            return {
                "success": False,
                "error": remote_error or "payload too large for share",
                "code": remote_code or "payload_too_large",
                "short_id": short_id,
                "short_url": short_url,
                "ciphertext_chars": ct_len,
                "max_chars": MAX_CIPHERTEXT_CHARS,
                "file_name": file_name,
                "message": msg,
            }

        return {
            "success": True,
            "short_url": short_url,
            "short_id": short_id,
            "original_url": original_url if can_embed else local_ref,
            "full_url": original_url if can_embed else local_ref,
            "expires_at": expires_at,
            "requires_password": True,
            "transport": transport,
            "remote": bool(remote and remote.get("success")),
            "remote_source": remote_source or None,
            "file_name": file_name,
            "ciphertext_chars": ct_len,
            "pruned": bool(prune_note),
            "message": msg,
        }

    @staticmethod
    def session_file_name(session_json: Any) -> str:
        """Basename from share metadata, or received.tokenade fallback."""
        if not isinstance(session_json, dict):
            return "received.tokenade"
        meta = session_json.get("metadata") if isinstance(session_json.get("metadata"), dict) else {}
        name = meta.get("file_name") or session_json.get("file_name") or ""
        name = Path(str(name)).name.strip() if name else ""
        if not name:
            return "received.tokenade"
        if not name.endswith(".tokenade"):
            name = f"{Path(name).stem}.tokenade"
        # Stay within basename only (no path traversal)
        return Path(name).name

    @staticmethod
    def resolve_output_path(
        session_json: Any,
        output_path: Optional[str] = None,
        *,
        default_dir: Optional[str] = None,
    ) -> str:
        """Pick write path: explicit -o, else metadata file_name under default_dir."""
        if output_path and str(output_path).strip():
            path = Path(str(output_path).strip()).expanduser()
            if path.parent and str(path.parent) not in (".", ""):
                path.parent.mkdir(parents=True, exist_ok=True)
            return str(path)

        base_dir = Path(default_dir).expanduser() if default_dir else Path.cwd()
        base_dir.mkdir(parents=True, exist_ok=True)
        name = SessionURLShortener.session_file_name(session_json)
        candidate = base_dir / name
        if not candidate.exists():
            return str(candidate)
        stem = candidate.stem
        suffix = candidate.suffix or ".tokenade"
        for i in range(2, 1000):
            alt = base_dir / f"{stem}-{i}{suffix}"
            if not alt.exists():
                return str(alt)
        return str(base_dir / f"{stem}-{int(time.time())}{suffix}")

    def _write_retrieved(
        self,
        session_json: dict,
        output_path: Optional[str],
        *,
        default_dir: Optional[str] = None,
    ) -> str:
        path = self.resolve_output_path(
            session_json, output_path, default_dir=default_dir
        )
        Path(path).write_text(json.dumps(session_json, indent=2), encoding="utf-8")
        return path

    def retrieve_session(
        self,
        short_url: str,
        password: str,
        output_path: Optional[str] = None,
        *,
        default_dir: Optional[str] = None,
        write_file: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve session from a shortened URL with password.

        KISS peer path: if the URL embeds ``?data=`` ciphertext, decrypt it
        directly — no local share store required. Otherwise resolve short_id
        against the local shortened_urls.json store (same machine / synced).

        Writes a file when ``output_path`` or ``default_dir`` is set (or
        ``write_file=True``). Without ``output_path``, uses
        ``metadata.file_name`` under ``default_dir`` (or cwd), with
        ``name-2.tokenade`` style de-dupe on collision.
        """
        raw = (short_url or "").strip()
        if not raw:
            return {"success": False, "error": "Invalid share URL"}

        do_write = (
            write_file
            if write_file is not None
            else bool(output_path or default_dir)
        )

        def _finish(session_json, *, remaining=None, source="embedded", **extra):
            out = None
            if do_write:
                out = self._write_retrieved(
                    session_json, output_path, default_dir=default_dir
                )
            result = {
                "success": True,
                "session": session_json,
                "output_path": out,
                "file_name": self.session_file_name(session_json),
                "remaining_uses": remaining,
                "source": source,
            }
            result.update(extra)
            return result

        # 1) Self-contained full URL — payload travels with the link
        embedded = self._extract_encrypted_data(raw)
        if embedded:
            try:
                decrypted = self._decrypt_with_password(embedded, password)
                session_json = json.loads(decrypted)
                # Best-effort use accounting if this id is in local store
                short_id = self._extract_short_id(raw)
                url_entry = self._urls.get(short_id) if short_id else None
                remaining = None
                if url_entry and url_entry.is_valid:
                    url_entry.current_uses += 1
                    self._save_urls()
                    if url_entry.max_uses > 0:
                        remaining = url_entry.max_uses - url_entry.current_uses
                return _finish(session_json, remaining=remaining, source="embedded")
            except Exception as e:
                return {"success": False, "error": f"Decryption failed: {e}"}

        # 2) Short id — try local store, then Supabase remote
        short_id = self._extract_short_id(raw)
        if not short_id:
            return {"success": False, "error": "Invalid share URL"}

        url_entry = self._urls.get(short_id)
        if url_entry:
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
                remaining = (
                    url_entry.max_uses - url_entry.current_uses
                    if url_entry.max_uses > 0
                    else None
                )
                return _finish(session_json, remaining=remaining, source="store")
            except Exception as e:
                return {"success": False, "error": f"Decryption failed: {e}"}

        # 3) Supabase remote (password never stored — only ciphertext)
        #    RPC consumes one use server-side on successful fetch.
        try:
            from tokenade.core.sharing.supabase_store import (
                SupabaseShareStore,
                SupabaseConfig,
            )
            sb_cfg = getattr(self, "_supabase_config", None) or SupabaseConfig.from_env()
            store = SupabaseShareStore(sb_cfg)
            if store.available:
                row = store.get_share(short_id)
                if row:
                    err = row.get("error")
                    if err == "revoked" or row.get("revoked"):
                        return {"success": False, "error": "Share revoked"}
                    if err == "expired":
                        return {"success": False, "error": "Share expired"}
                    if err == "max_uses":
                        return {"success": False, "error": "Share max uses reached"}
                    if err:
                        return {"success": False, "error": f"Share unavailable ({err})"}
                    ciphertext = row.get("ciphertext") or ""
                    if not ciphertext:
                        return {"success": False, "error": "Empty remote ciphertext"}
                    try:
                        decrypted = self._decrypt_with_password(ciphertext, password)
                        session_json = json.loads(decrypted)
                    except Exception as e:
                        return {"success": False, "error": f"Decryption failed: {e}"}
                    remaining = row.get("remaining_uses")
                    if remaining is None:
                        max_uses = int(row.get("max_uses") or 0)
                        cur = int(row.get("current_uses") or 0)
                        remaining = (max_uses - cur) if max_uses > 0 else None
                    return _finish(
                        session_json,
                        remaining=remaining,
                        source="supabase",
                        remote_source=store.config.source,
                    )
        except Exception as e:
            logger.debug("Supabase retrieve failed: %s", e)

        return {
            "success": False,
            "error": (
                "Share not found (local or remote). "
                "Paste the full URL (with ?data=) or use the public/default "
                "Supabase project (or your private TOKENADE_SUPABASE_* override)."
            ),
        }

    def revoke(self, short_id: str) -> bool:
        """Revoke a local share link entry (remote revoke is separate)."""
        sid = (short_id or "").strip()
        if "share/" in sid:
            sid = sid.rstrip("/").split("share/")[-1].split("?")[0].strip()
        if not sid:
            return False
        url_entry = self._urls.get(sid)
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

    # Strip embedded ?data= payloads larger than this from local store
    MAX_STORED_ORIGINAL_URL = 50_000

    @classmethod
    def _strip_embedded_data(cls, url: str) -> str:
        """Drop ?data=... payload from tokenade:// share URLs (keep short ref)."""
        if not url or "?data=" not in url:
            return url
        base, _, _rest = url.partition("?data=")
        return base or url

    def prune_oversized_embeds(self, *, max_url_chars: Optional[int] = None) -> Dict[str, int]:
        """Strip huge embedded payloads from local shortened_urls.json.

        Full-profile shares used to write multi‑MB ``?data=`` blobs into the
        local store. Keep short_id refs; remote retrieve still works if uploaded.
        """
        limit = int(max_url_chars or self.MAX_STORED_ORIGINAL_URL)
        stripped = 0
        removed = 0
        changed = False
        for sid, entry in list(self._urls.items()):
            orig = entry.original_url or ""
            if len(orig) <= limit:
                continue
            if "?data=" in orig:
                entry.original_url = self._strip_embedded_data(orig)
                # Prefer compact short_url too
                if entry.short_url and "?data=" in entry.short_url:
                    entry.short_url = self._strip_embedded_data(entry.short_url)
                if not entry.short_url or len(entry.short_url) > limit:
                    entry.short_url = f"tokenade://share/{sid}"
                stripped += 1
                changed = True
            elif len(orig) > limit * 2:
                # Unusable giant non-embed entry — drop
                del self._urls[sid]
                removed += 1
                changed = True
        if changed:
            self._save_urls()
        return {"stripped": stripped, "removed": removed, "remaining": len(self._urls)}

    def cleanup_local_store(self) -> Dict[str, int]:
        """Expired + oversized embed prune. Safe default for ``share-url cleanup``."""
        expired = self.cleanup_expired()
        pruned = self.prune_oversized_embeds()
        return {
            "expired": expired,
            "stripped": pruned.get("stripped", 0),
            "removed": pruned.get("removed", 0),
            "remaining": pruned.get("remaining", len(self._urls)),
        }

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

    @staticmethod
    def _origin_matches_needles(origin: str, needles: List[str]) -> bool:
        o = (origin or "").lower()
        return any(n in o for n in needles)

    @classmethod
    def _site_storage_needles(cls, session: Dict[str, Any]) -> List[str]:
        """Domain fragments used to keep only relevant storage origins."""
        site = str(session.get("site_name") or session.get("site") or "").lower()
        needles: List[str] = []
        if site and site not in ("unknown", "session-backup", "backup"):
            needles.append(site)
            if "." not in site:
                needles.append(f"{site}.com")
        # Cookie domains always count
        for c in session.get("cookies") or []:
            if not isinstance(c, dict):
                continue
            d = str(c.get("domain") or "").lower().lstrip(".")
            if d and d not in needles:
                needles.append(d)
                # bare registrable-ish token
                parts = d.split(".")
                if len(parts) >= 2 and parts[-2] not in needles:
                    needles.append(parts[-2])
        # Common aliases
        if any(n in ("google", "gmail", "youtube") or "google" in n for n in needles):
            for extra in (
                "google.",
                "gmail.",
                "youtube.",
                "gstatic.",
                "googleapis.",
                "accounts.google",
                "mail.google",
            ):
                if extra not in needles:
                    needles.append(extra)
        return [n for n in needles if n]

    @classmethod
    def _filter_storage_dict(
        cls, storage: Any, needles: List[str]
    ) -> tuple[Any, int, int]:
        """Return (filtered_storage, kept_origins, dropped_origins)."""
        if not isinstance(storage, dict) or not needles:
            return storage, 0, 0
        kept_o = dropped_o = 0

        def _filter_map(m: Any) -> Dict[str, Any]:
            nonlocal kept_o, dropped_o
            if not isinstance(m, dict):
                return m
            out: Dict[str, Any] = {}
            for origin, val in m.items():
                if cls._origin_matches_needles(str(origin), needles):
                    out[str(origin)] = val
                    kept_o += 1
                else:
                    dropped_o += 1
            return out

        # v3 shape: {local: {origin: {...}}, session: {...}}
        if "local" in storage or "session" in storage:
            filtered = dict(storage)
            if "local" in storage:
                filtered["local"] = _filter_map(storage.get("local"))
            if "session" in storage:
                filtered["session"] = _filter_map(storage.get("session"))
            return filtered, kept_o, dropped_o
        # flat origin map
        return _filter_map(storage), kept_o, dropped_o

    @classmethod
    def _estimate_ciphertext_chars(cls, session: Dict[str, Any]) -> int:
        """Rough upper bound: json size * 4/3 (b64) + fernet overhead."""
        try:
            n = len(json.dumps(session, separators=(",", ":")))
        except Exception:
            n = 0
        return int(n * 1.4) + 256

    @classmethod
    def _fit_session_for_remote_share(
        cls, session: Dict[str, Any]
    ) -> tuple[Dict[str, Any], str]:
        """Prune bulk storage so encrypted payload can fit Supabase max.

        Full-profile dumps (1000+ origins) exceed the 2MB ciphertext cap.
        Keeps cookies/tokens and site-relevant storage when possible.
        """
        from tokenade.core.sharing.supabase_store import MAX_CIPHERTEXT_CHARS

        if not isinstance(session, dict):
            return session, ""

        notes: List[str] = []
        data = session
        est = cls._estimate_ciphertext_chars(data)
        if est <= MAX_CIPHERTEXT_CHARS:
            return data, ""

        # 1) Filter storage to site/cookie-related origins
        needles = cls._site_storage_needles(data)
        if needles and isinstance(data.get("storage"), dict):
            data = dict(data)
            filtered, kept, dropped = cls._filter_storage_dict(
                data.get("storage"), needles
            )
            data["storage"] = filtered
            meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
            meta = dict(meta)
            meta["share_storage_filtered"] = True
            meta["share_storage_kept_origins"] = kept
            meta["share_storage_dropped_origins"] = dropped
            data["metadata"] = meta
            notes.append(f"storage filtered to site origins (kept {kept}, dropped {dropped})")
            est = cls._estimate_ciphertext_chars(data)
            if est <= MAX_CIPHERTEXT_CHARS:
                return data, "; ".join(notes)

        # 2) Drop all web storage — cookies + tokens usually enough for login
        if isinstance(data.get("storage"), dict) and data.get("storage"):
            data = dict(data)
            data["storage"] = {"local": {}, "session": {}}
            meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
            meta = dict(meta)
            meta["share_storage_stripped"] = True
            data["metadata"] = meta
            notes.append("storage stripped (cookies/tokens only)")
            est = cls._estimate_ciphertext_chars(data)
            if est <= MAX_CIPHERTEXT_CHARS:
                return data, "; ".join(notes)

        # 3) Drop fingerprint / tls bulk if still huge
        for bulky in ("fingerprint", "tls_profile", "source_device", "oauth_config"):
            if bulky in data and data[bulky]:
                data = dict(data)
                data.pop(bulky, None)
                notes.append(f"dropped {bulky}")
        est = cls._estimate_ciphertext_chars(data)
        if est > MAX_CIPHERTEXT_CHARS:
            notes.append(
                f"still ~{est} chars estimated (max {MAX_CIPHERTEXT_CHARS}); remote may fail"
            )
        return data, "; ".join(notes)

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
                # Auto-heal multi‑MB stores from old full-embed shares
                try:
                    size = self._url_store.stat().st_size
                except OSError:
                    size = 0
                with open(self._url_store) as f:
                    data = json.load(f)

                for url_data in data:
                    # Remove is_valid if present (it's a computed property)
                    url_data.pop("is_valid", None)
                    # Strip giant embeds on load so memory stays small
                    orig = url_data.get("original_url") or ""
                    if isinstance(orig, str) and len(orig) > self.MAX_STORED_ORIGINAL_URL:
                        url_data["original_url"] = self._strip_embedded_data(orig)
                    short = url_data.get("short_url") or ""
                    if isinstance(short, str) and len(short) > self.MAX_STORED_ORIGINAL_URL:
                        sid = url_data.get("short_id") or ""
                        url_data["short_url"] = (
                            self._strip_embedded_data(short)
                            if "?data=" in short
                            else (f"tokenade://share/{sid}" if sid else short[:200])
                        )
                    try:
                        url_entry = ShortenedURL(**url_data)
                    except TypeError:
                        # tolerate extra keys from older formats
                        known = {
                            k: url_data[k]
                            for k in (
                                "short_id",
                                "original_url",
                                "short_url",
                                "created_at",
                                "expires_at",
                                "password_hash",
                                "max_uses",
                                "current_uses",
                                "revoked",
                            )
                            if k in url_data
                        }
                        url_entry = ShortenedURL(**known)
                    self._urls[url_entry.short_id] = url_entry

                if size > 1_000_000:
                    # Rewrite compact file after load
                    try:
                        self._save_urls()
                        logger.info(
                            "Compacted oversized shortened_urls.json (%s bytes → rewritten)",
                            size,
                        )
                    except Exception:
                        pass

            except Exception as e:
                logger.warning(f"Failed to load shortened URLs: {e}")

    def _save_urls(self) -> None:
        """Save URLs to storage."""
        try:
            self._url_store.parent.mkdir(parents=True, exist_ok=True)

            data = []
            for url_entry in self._urls.values():
                row = url_entry.to_dict()
                # Never rewrite multi‑MB embeds
                orig = row.get("original_url") or ""
                if isinstance(orig, str) and len(orig) > self.MAX_STORED_ORIGINAL_URL:
                    row["original_url"] = self._strip_embedded_data(orig)
                short = row.get("short_url") or ""
                if isinstance(short, str) and len(short) > self.MAX_STORED_ORIGINAL_URL:
                    row["short_url"] = self._strip_embedded_data(short) or (
                        f"tokenade://share/{row.get('short_id')}"
                    )
                data.append(row)

            with open(self._url_store, "w") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.warning(f"Failed to save shortened URLs: {e}")
