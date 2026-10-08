"""
Audit Logging for Tokenade.

Provides comprehensive audit logging with:
- Action tracking
- User attribution
- Timestamp precision
- Log rotation
- Query capabilities
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AuditEntry:
    """An audit log entry."""

    timestamp: float
    user_id: str
    action: str
    resource: str
    resource_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    ip_address: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "user_id": self.user_id,
            "action": self.action,
            "resource": self.resource,
            "resource_id": self.resource_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "success": self.success,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AuditEntry':
        return cls(
            timestamp=data.get("timestamp", 0),
            user_id=data.get("user_id", ""),
            action=data.get("action", ""),
            resource=data.get("resource", ""),
            resource_id=data.get("resource_id"),
            details=data.get("details", {}),
            ip_address=data.get("ip_address"),
            success=data.get("success", True),
            error_message=data.get("error_message"),
        )


class AuditLogger:
    """
    Comprehensive audit logging system.
    
    Features:
    - Action tracking with user attribution
    - Structured logging format
    - Log rotation by date
    - Query and search capabilities
    - Export to various formats
    """

    def __init__(self, log_dir: Optional[str] = None, max_entries_per_file: int = 10000):
        self._log_dir = Path(log_dir or "~/.tokenade/audit").expanduser()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._max_entries = max_entries_per_file
        self._current_file = None
        self._current_count = 0
        self._init_current_file()

    def _init_current_file(self):
        """Initialize current log file."""
        today = time.strftime("%Y-%m-%d")
        self._current_file = self._log_dir / f"audit_{today}.jsonl"

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
    ) -> AuditEntry:
        """
        Log an audit event.
        
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
            Created AuditEntry
        """
        entry = AuditEntry(
            timestamp=time.time(),
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            details=details or {},
            ip_address=ip_address,
            success=success,
            error_message=error_message,
        )

        self._write_entry(entry)
        return entry

    def query(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        resource: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        success_only: bool = False,
        limit: int = 100,
    ) -> List[AuditEntry]:
        """
        Query audit logs.
        
        Args:
            user_id: Filter by user ID
            action: Filter by action
            resource: Filter by resource type
            start_time: Start time range
            end_time: End time range
            success_only: Only return successful entries
            limit: Maximum entries to return
            
        Returns:
            List of matching AuditEntry objects
        """
        results = []

        for log_file in sorted(self._log_dir.glob("audit_*.jsonl"), reverse=True):
            if len(results) >= limit:
                break

            try:
                with open(log_file) as f:
                    for line in f:
                        if len(results) >= limit:
                            break

                        try:
                            data = json.loads(line.strip())
                            entry = AuditEntry.from_dict(data)

                            if user_id and entry.user_id != user_id:
                                continue
                            if action and entry.action != action:
                                continue
                            if resource and entry.resource != resource:
                                continue
                            if start_time and entry.timestamp < start_time:
                                continue
                            if end_time and entry.timestamp > end_time:
                                continue
                            if success_only and not entry.success:
                                continue

                            results.append(entry)

                        except json.JSONDecodeError:
                            continue

            except Exception as e:
                logger.warning(f"Failed to read audit file {log_file}: {e}")

        return results[:limit]

    def get_user_activity(
        self,
        user_id: str,
        days: int = 7,
    ) -> List[AuditEntry]:
        """Get recent activity for a user."""
        start_time = time.time() - (days * 86400)
        return self.query(user_id=user_id, start_time=start_time)

    def get_resource_history(
        self,
        resource: str,
        resource_id: str,
    ) -> List[AuditEntry]:
        """Get history for a specific resource."""
        return self.query(resource=resource, resource_id=resource_id)

    def get_statistics(
        self,
        days: int = 7,
    ) -> Dict[str, Any]:
        """Get audit statistics."""
        start_time = time.time() - (days * 86400)
        entries = self.query(start_time=start_time, limit=10000)

        user_counts = {}
        action_counts = {}
        resource_counts = {}
        success_count = 0
        failure_count = 0

        for entry in entries:
            user_counts[entry.user_id] = user_counts.get(entry.user_id, 0) + 1
            action_counts[entry.action] = action_counts.get(entry.action, 0) + 1
            resource_counts[entry.resource] = resource_counts.get(entry.resource, 0) + 1

            if entry.success:
                success_count += 1
            else:
                failure_count += 1

        return {
            "total_entries": len(entries),
            "period_days": days,
            "top_users": sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:10],
            "top_actions": sorted(action_counts.items(), key=lambda x: x[1], reverse=True)[:10],
            "top_resources": sorted(resource_counts.items(), key=lambda x: x[1], reverse=True)[:10],
            "success_rate": success_count / len(entries) if entries else 0,
            "success_count": success_count,
            "failure_count": failure_count,
        }

    def export(
        self,
        output_path: str,
        format: str = "json",
        **query_kwargs,
    ) -> bool:
        """
        Export audit logs.
        
        Args:
            output_path: Output file path
            format: Export format (json, csv)
            **query_kwargs: Query parameters
            
        Returns:
            True if successful
        """
        entries = self.query(**query_kwargs)

        try:
            if format == "json":
                data = [entry.to_dict() for entry in entries]
                with open(output_path, "w") as f:
                    json.dump(data, f, indent=2)

            elif format == "csv":
                import csv

                with open(output_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        "timestamp", "user_id", "action", "resource",
                        "resource_id", "success", "error_message"
                    ])

                    for entry in entries:
                        writer.writerow([
                            entry.timestamp, entry.user_id, entry.action,
                            entry.resource, entry.resource_id, entry.success,
                            entry.error_message,
                        ])

            return True

        except Exception as e:
            logger.error(f"Failed to export audit logs: {e}")
            return False

    def cleanup(self, days: int = 90) -> int:
        """
        Remove old audit logs.
        
        Args:
            days: Keep logs newer than this many days
            
        Returns:
            Number of files removed
        """
        cutoff = time.time() - (days * 86400)
        removed = 0

        for log_file in self._log_dir.glob("audit_*.jsonl"):
            try:
                date_str = log_file.stem.replace("audit_", "")
                file_date = time.mktime(time.strptime(date_str, "%Y-%m-%d"))

                if file_date < cutoff:
                    log_file.unlink()
                    removed += 1

            except Exception as e:
                logger.warning(f"Failed to check/delete {log_file}: {e}")

        return removed

    def _write_entry(self, entry: AuditEntry) -> None:
        """Write an entry to the current log file."""
        today = time.strftime("%Y-%m-%d")
        expected_file = self._log_dir / f"audit_{today}.jsonl"

        if self._current_file != expected_file or self._current_count >= self._max_entries:
            self._current_file = expected_file
            self._current_count = 0

        try:
            with open(self._current_file, "a") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")

            self._current_count += 1

        except Exception as e:
            logger.error(f"Failed to write audit entry: {e}")
