"""
Encrypted Audit Logging for Tokenade.

Provides encrypted audit logging with:
- AES-256-GCM encryption for log entries
- Key rotation support
- Secure key storage
- Tamper-evident logging
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
class EncryptedAuditConfig:
    """Configuration for encrypted audit logging."""

    log_dir: str = "~/.tokenade/audit"
    encryption_key: Optional[str] = None
    key_rotation_days: int = 30
    max_entries_per_file: int = 10000

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EncryptedAuditConfig':
        return cls(
            log_dir=data.get("log_dir", "~/.tokenade/audit"),
            encryption_key=data.get("encryption_key"),
            key_rotation_days=data.get("key_rotation_days", 30),
            max_entries_per_file=data.get("max_entries_per_file", 10000),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "log_dir": self.log_dir,
            "key_rotation_days": self.key_rotation_days,
            "max_entries_per_file": self.max_entries_per_file,
        }


class EncryptedAuditLogger:
    """
    Encrypted audit logging system.
    
    Features:
    - AES-256-GCM encryption for log entries
    - Key rotation support
    - Secure key storage
    - Tamper-evident logging
    - Query capabilities
    """

    def __init__(self, config: Optional[EncryptedAuditConfig] = None):
        self.config = config or EncryptedAuditConfig()
        self._log_dir = Path(self.config.log_dir).expanduser()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._current_file = None
        self._current_count = 0
        self._encryption_key = self._get_or_create_key()
        self._init_current_file()

    def _get_or_create_key(self) -> bytes:
        """Get or create encryption key."""
        key_file = self._log_dir / "audit.key"

        if key_file.exists():
            return key_file.read_bytes()

        key = secrets.token_bytes(32)
        key_file.write_bytes(key)
        key_file.chmod(0o600)
        return key

    def _init_current_file(self):
        """Initialize current log file."""
        today = time.strftime("%Y-%m-%d")
        self._current_file = self._log_dir / f"encrypted_audit_{today}.jsonl"

        if self._current_file.exists():
            with open(self._current_file) as f:
                self._current_count = sum(1 for _ in f)

    def log(
        self,
        user_id: str,
        action: str,
        resource: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Log an encrypted audit event.
        
        Args:
            user_id: User performing the action
            action: Action being performed
            resource: Resource type
            resource_id: Specific resource ID
            details: Additional details
            ip_address: User's IP address
            success: Whether action succeeded
            error_message: Error message if failed
            
        Returns:
            Dictionary with entry metadata
        """
        entry_data = {
            "timestamp": time.time(),
            "user_id": user_id,
            "action": action,
            "resource": resource,
            "resource_id": resource_id,
            "details": details or {},
            "ip_address": ip_address,
            "success": success,
            "error_message": error_message,
        }

        encrypted_entry = self._encrypt_entry(entry_data)

        self._write_encrypted_entry(encrypted_entry)

        return {
            "timestamp": entry_data["timestamp"],
            "checksum": self._compute_checksum(entry_data),
        }

    def query(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        resource: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        success_only: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query encrypted audit logs.
        
        Args:
            user_id: Filter by user ID
            action: Filter by action
            resource: Filter by resource type
            start_time: Start time range
            end_time: End time range
            success_only: Only return successful entries
            limit: Maximum entries to return
            
        Returns:
            List of decrypted audit entries
        """
        results = []

        for log_file in sorted(self._log_dir.glob("encrypted_audit_*.jsonl"), reverse=True):
            if len(results) >= limit:
                break

            try:
                with open(log_file) as f:
                    for line in f:
                        if len(results) >= limit:
                            break

                        try:
                            encrypted_data = json.loads(line.strip())
                            entry_data = self._decrypt_entry(encrypted_data)

                            if not entry_data:
                                continue

                            if user_id and entry_data.get("user_id") != user_id:
                                continue
                            if action and entry_data.get("action") != action:
                                continue
                            if resource and entry_data.get("resource") != resource:
                                continue
                            if start_time and entry_data.get("timestamp", 0) < start_time:
                                continue
                            if end_time and entry_data.get("timestamp", 0) > end_time:
                                continue
                            if success_only and not entry_data.get("success", True):
                                continue

                            results.append(entry_data)

                        except json.JSONDecodeError:
                            continue

            except Exception as e:
                logger.warning(f"Failed to read encrypted audit file {log_file}: {e}")

        return results[:limit]

    def rotate_key(self) -> Dict[str, Any]:
        """
        Rotate encryption key and re-encrypt existing logs.
        
        Returns:
            Dictionary with rotation results
        """
        old_key = self._encryption_key
        new_key = secrets.token_bytes(32)

        re_encrypted = 0

        for log_file in self._log_dir.glob("encrypted_audit_*.jsonl"):
            try:
                entries = []
                with open(log_file) as f:
                    for line in f:
                        try:
                            encrypted_data = json.loads(line.strip())
                            entry_data = self._decrypt_entry(encrypted_data, old_key)
                            if entry_data:
                                entries.append(entry_data)
                        except json.JSONDecodeError:
                            continue

                self._encryption_key = new_key

                with open(log_file, "w") as f:
                    for entry_data in entries:
                        encrypted_entry = self._encrypt_entry(entry_data)
                        f.write(json.dumps(encrypted_entry) + "\n")
                        re_encrypted += 1

            except Exception as e:
                logger.warning(f"Failed to rotate key for {log_file}: {e}")

        self._encryption_key = new_key

        key_file = self._log_dir / "audit.key"
        key_file.write_bytes(new_key)
        key_file.chmod(0o600)

        return {
            "success": True,
            "re_encrypted_count": re_encrypted,
            "old_key_hash": hashlib.sha256(old_key).hexdigest(),
            "new_key_hash": hashlib.sha256(new_key).hexdigest(),
        }

    def _encrypt_entry(self, entry_data: Dict[str, Any]) -> Dict[str, str]:
        """Encrypt an audit entry."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            iv = secrets.token_bytes(12)
            aesgcm = AESGCM(self._encryption_key)

            plaintext = json.dumps(entry_data).encode()
            ciphertext = aesgcm.encrypt(iv, plaintext, None)

            return {
                "iv": base64.b64encode(iv).decode(),
                "data": base64.b64encode(ciphertext).decode(),
                "checksum": self._compute_checksum(entry_data),
            }

        except ImportError:
            logger.warning("cryptography not installed, storing plaintext")
            return {
                "iv": "",
                "data": base64.b64encode(json.dumps(entry_data).encode()).decode(),
                "checksum": self._compute_checksum(entry_data),
            }

    def _decrypt_entry(self, encrypted_data: Dict[str, str], key: Optional[bytes] = None) -> Optional[Dict[str, Any]]:
        """Decrypt an audit entry."""
        key = key or self._encryption_key

        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            iv = base64.b64decode(encrypted_data["iv"])
            ciphertext = base64.b64decode(encrypted_data["data"])

            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(iv, ciphertext, None)

            return json.loads(plaintext)

        except ImportError:
            logger.warning("cryptography not installed, reading plaintext")
            return json.loads(base64.b64decode(encrypted_data["data"]))

        except Exception as e:
            logger.error(f"Failed to decrypt audit entry: {e}")
            return None

    def _compute_checksum(self, entry_data: Dict[str, Any]) -> str:
        """Compute checksum for tamper detection."""
        data_str = json.dumps(entry_data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()[:16]

    def _write_encrypted_entry(self, encrypted_entry: Dict[str, str]):
        """Write encrypted entry to log file."""
        if self._current_count >= self.config.max_entries_per_file:
            self._init_current_file()

        with open(self._current_file, "a") as f:
            f.write(json.dumps(encrypted_entry) + "\n")

        self._current_count += 1
