"""Privacy-safe, opt-in, local-only operation analytics."""

from __future__ import annotations

import csv, json, os, sqlite3, time, uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


class AnalyticsOperation(str, Enum):
    EXPORT = "export"
    LOAD = "load"
    REFRESH = "refresh"
    HEALTH_CHECK = "health_check"
    SHARE_CREATE = "share_create"
    SHARE_RETRIEVE = "share_retrieve"
    SYNC_PUSH = "sync_push"
    SYNC_PULL = "sync_pull"
    SYNC_TWO_WAY = "sync_two_way"
    VAULT_STORE = "vault_store"
    VAULT_RETRIEVE = "vault_retrieve"
    PROXY_START = "proxy_start"


class AnalyticsOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"


ALLOWED_DIMENSIONS = {
    "export": {
        "browser_family",
        "source_kind",
        "encrypted",
        "cookie_count_bucket",
        "storage_present",
    },
    "load": {"browser_family", "visible", "validation_requested", "storage_present"},
    "refresh": {"method"},
    "health_check": {"health_band"},
    "share_create": {"backend", "expiry_band"},
    "share_retrieve": {"backend"},
    "sync_push": {"file_count_bucket"},
    "sync_pull": {"file_count_bucket"},
    "vault_store": {"encrypted"},
    "sync_two_way": {"file_count_bucket"},
    "vault_retrieve": set(),
    "proxy_start": {"provider_kind"},
}


@dataclass(frozen=True)
class AnalyticsConfig:
    enabled: bool = False
    directory: Optional[str] = None
    retention_days: int = 30


class LocalAnalytics:
    def __init__(self, config: Optional[AnalyticsConfig] = None, analytics_dir=None):
        config = config or AnalyticsConfig(
            directory=str(analytics_dir) if analytics_dir else None
        )
        root = (
            config.directory
            or os.environ.get("TOKENADE_ANALYTICS_DIR")
            or str(
                Path(os.environ.get("TOKENADE_DIR", "~/.tokenade")).expanduser()
                / "analytics"
            )
        )
        self.directory = Path(root).expanduser().resolve()
        self.config_path = self.directory / "config.json"
        self.db_path = self.directory / "analytics.sqlite3"
        self.legacy_path = self.directory / "events.jsonl"
        saved = self._saved_config()
        self.enabled = bool(saved.get("enabled", config.enabled))
        self.retention_days = int(saved.get("retention_days", config.retention_days))
        if self.retention_days < 1:
            raise ValueError("retention_days must be positive")
        if self.enabled or self.db_path.exists():
            self._init_db()

    def enable(self, retention_days=30):
        if retention_days < 1:
            raise ValueError("retention_days must be positive")
        self.enabled = True
        self.retention_days = retention_days
        self._save_config()
        self._init_db()

    def disable(self):
        self.enabled = False
        self._save_config()

    def record(self, operation, outcome, *, duration_ms=None, dimensions=None):
        if not self.enabled:
            return False
        try:
            op = AnalyticsOperation(operation).value
            result = AnalyticsOutcome(outcome).value
            dims = dimensions or {}
            if duration_ms is not None and (
                not isinstance(duration_ms, int) or duration_ms < 0
            ):
                raise ValueError("invalid duration")
            unknown = set(dims) - ALLOWED_DIMENSIONS[op]
            if unknown:
                raise ValueError(f"unsupported dimensions: {sorted(unknown)}")
            if any(not _valid_dimension(key, value) for key, value in dims.items()):
                raise ValueError("invalid dimension value")
            self._init_db()
            with sqlite3.connect(self.db_path) as db:
                db.execute(
                    "INSERT INTO events VALUES(?,?,?,?,?,?,?)",
                    (
                        uuid.uuid4().hex,
                        1,
                        int(time.time() * 1000),
                        op,
                        result,
                        duration_ms,
                        json.dumps(dims, sort_keys=True),
                    ),
                )
            self.cleanup()
            return True
        except Exception:
            return False

    def record_event(
        self, event_type, data=None, session_name="", site="", success=True
    ):
        """Compatibility adapter: ignores identifying legacy arguments."""
        try:
            op = AnalyticsOperation(event_type)
        except ValueError:
            return False
        return self.record(
            op,
            AnalyticsOutcome.SUCCESS if success else AnalyticsOutcome.FAILURE,
            dimensions={},
        )

    def status(self):
        count = 0
        oldest = newest = None
        if self.db_path.exists():
            with sqlite3.connect(self.db_path) as db:
                count, oldest, newest = db.execute(
                    "SELECT COUNT(*),MIN(occurred_at_ms),MAX(occurred_at_ms) FROM events"
                ).fetchone()
        return {
            "schema_version": 1,
            "enabled": self.enabled,
            "storage_path": str(self.db_path),
            "retention_days": self.retention_days,
            "event_count": count,
            "oldest_at": _iso(oldest),
            "newest_at": _iso(newest),
            "file_size_bytes": self.db_path.stat().st_size
            if self.db_path.exists()
            else 0,
            "corrupt_event_count": 0,
            "legacy_file": str(self.legacy_path) if self.legacy_path.exists() else None,
        }

    def report(self, days=30):
        if days < 1:
            raise ValueError("days must be positive")
        since = int((time.time() - days * 86400) * 1000)
        rows = []
        if self.db_path.exists():
            with sqlite3.connect(self.db_path) as db:
                rows = db.execute(
                    "SELECT occurred_at_ms,operation,outcome,duration_ms FROM events WHERE occurred_at_ms>=? ORDER BY occurred_at_ms",
                    (since,),
                ).fetchall()
        by = {}
        daily = {}
        outcomes = {"success": 0, "failure": 0, "cancelled": 0}
        for ts, op, outcome, duration in rows:
            outcomes[outcome] += 1
            bucket = by.setdefault(
                op,
                {
                    "total": 0,
                    "success": 0,
                    "failure": 0,
                    "cancelled": 0,
                    "durations": [],
                },
            )
            bucket["total"] += 1
            bucket[outcome] += 1
            if duration is not None:
                bucket["durations"].append(duration)
            day = datetime.fromtimestamp(ts / 1000, timezone.utc).date().isoformat()
            daily[day] = daily.get(day, 0) + 1
        for bucket in by.values():
            ds = sorted(bucket.pop("durations"))
            bucket["p50_ms"] = ds[len(ds) // 2] if ds else None
            bucket["p95_ms"] = ds[min(len(ds) - 1, int(len(ds) * 0.95))] if ds else None
        completed = outcomes["success"] + outcomes["failure"]
        outcomes["success_rate"] = (
            outcomes["success"] / completed if completed else None
        )
        return {
            "schema_version": 1,
            "period_days": days,
            "total_operations": len(rows),
            "outcomes": outcomes,
            "by_operation": by,
            "daily_operations": daily,
        }

    def generate_report(self, days=30):
        return self.report(days)

    def inspect(self, days=7, limit=100):
        if days < 1 or limit < 1:
            raise ValueError("days and limit must be positive")
        if not self.db_path.exists():
            return []
        since = int((time.time() - days * 86400) * 1000)
        with sqlite3.connect(self.db_path) as db:
            rows = db.execute(
                "SELECT occurred_at_ms,operation,outcome,duration_ms,dimensions_json FROM events WHERE occurred_at_ms>=? ORDER BY occurred_at_ms DESC LIMIT ?",
                (since, limit),
            ).fetchall()
        return [
            {
                "occurred_at": _iso(ts),
                "operation": op,
                "outcome": outcome,
                "duration_ms": duration,
                "dimensions": json.loads(dims),
            }
            for ts, op, outcome, duration, dims in rows
        ]

    def export_csv(self, output, days=30, raw=False):
        output = Path(output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        rows = (
            self.inspect(days, 100000)
            if raw
            else [
                {"operation": op, **values}
                for op, values in self.report(days)["by_operation"].items()
            ]
        )
        fields = sorted({key for row in rows for key in row}) if rows else ["operation"]
        with open(output, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        if os.name != "nt":
            os.chmod(output, 0o600)
        return output

    def cleanup(self, older_than_days=None, max_events=None):
        if not self.db_path.exists():
            return 0
        days = older_than_days or self.retention_days
        if days < 1:
            raise ValueError("days must be positive")
        with sqlite3.connect(self.db_path) as db:
            before = db.total_changes
            db.execute(
                "DELETE FROM events WHERE occurred_at_ms<?",
                (int((time.time() - days * 86400) * 1000),),
            )
            removed = db.total_changes - before
            db.commit()
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return removed

    def delete_all(self):
        count = self.status()["event_count"]
        for suffix in ("", "-wal", "-shm"):
            Path(str(self.db_path) + suffix).unlink(missing_ok=True)
        return count

    def _init_db(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            os.chmod(self.directory, 0o700)
        with sqlite3.connect(self.db_path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA busy_timeout=5000")
            db.execute(
                "CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY,schema_version INTEGER NOT NULL,occurred_at_ms INTEGER NOT NULL,operation TEXT NOT NULL,outcome TEXT NOT NULL,duration_ms INTEGER,dimensions_json TEXT NOT NULL)"
            )
        if os.name != "nt":
            os.chmod(self.db_path, 0o600)

    def _saved_config(self):
        try:
            return (
                json.loads(self.config_path.read_text())
                if self.config_path.exists()
                else {}
            )
        except Exception:
            return {}

    def _save_config(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp = self.config_path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "enabled": self.enabled,
                    "retention_days": self.retention_days,
                },
                indent=2,
            )
        )
        os.chmod(temp, 0o600)
        os.replace(temp, self.config_path)


AnalyticsEngine = LocalAnalytics


def record_local(operation, outcome, *, duration_ms=None, dimensions=None):
    """Best-effort canonical instrumentation; never affects the operation."""
    try:
        return LocalAnalytics().record(
            operation, outcome, duration_ms=duration_ms, dimensions=dimensions
        )
    except Exception:
        return False


def _iso(ts):
    return (
        datetime.fromtimestamp(ts / 1000, timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
        if ts
        else None
    )


DIMENSION_VALUES = {
    "browser_family": {"firefox", "chromium", "safari", "other"},
    "source_kind": {"profile", "cdp", "plugin"},
    "cookie_count_bucket": {"0", "1-10", "11-50", "51-200", "200+"},
    "method": {"browser", "oauth", "plugin"},
    "health_band": {"healthy", "warning", "expired", "empty"},
    "backend": {"local", "remote"},
    "expiry_band": {"<=1h", "<=24h", "<=7d", ">7d"},
    "file_count_bucket": {"0", "1-10", "11+"},
    "provider_kind": {"direct", "configured", "plugin"},
}


def _valid_dimension(key, value):
    if key in {"encrypted", "storage_present", "visible", "validation_requested"}:
        return isinstance(value, bool)
    if not isinstance(value, str) or len(value) > 32:
        return False
    return value in DIMENSION_VALUES.get(key, set())
