"""
Session Analytics Engine.

Tracks session usage patterns, health trends, and generates insights.
Stores analytics data in a local JSON database for historical reporting.

Usage:
    # CLI
    tokenade analytics --report
    tokenade analytics --export-csv usage.csv

    # Python
    from tokenade.core.analytics.engine import AnalyticsEngine
    engine = AnalyticsEngine()
    engine.record_event("export", {"site": "twitter", "cookies": 113})
    report = engine.generate_report()
"""

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ANALYTICS_DIR = Path.home() / ".tokenade" / "analytics"
EVENTS_FILE = ANALYTICS_DIR / "events.jsonl"
REPORT_CACHE = ANALYTICS_DIR / "report_cache.json"


@dataclass
class AnalyticsEvent:
    """A single analytics event."""
    event_type: str
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)
    session_name: str = ""
    site: str = ""
    success: bool = True

    def to_dict(self) -> Dict:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "data": self.data,
            "session_name": self.session_name,
            "site": self.site,
            "success": self.success,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "AnalyticsEvent":
        return cls(
            event_type=d.get("event_type", "unknown"),
            timestamp=d.get("timestamp", 0),
            data=d.get("data", {}),
            session_name=d.get("session_name", ""),
            site=d.get("site", ""),
            success=d.get("success", True),
        )


@dataclass
class SiteStats:
    """Aggregated statistics for a site."""
    site: str
    total_events: int = 0
    exports: int = 0
    loads: int = 0
    shares: int = 0
    syncs: int = 0
    vault_stores: int = 0
    avg_health: float = 0.0
    last_activity: float = 0.0
    total_cookies: int = 0

    def to_dict(self) -> Dict:
        return {
            "site": self.site,
            "total_events": self.total_events,
            "exports": self.exports,
            "loads": self.loads,
            "shares": self.shares,
            "syncs": self.syncs,
            "vault_stores": self.vault_stores,
            "avg_health": self.avg_health,
            "last_activity": self.last_activity,
            "total_cookies": self.total_cookies,
        }


@dataclass
class AnalyticsReport:
    """Aggregated analytics report."""
    generated_at: float = field(default_factory=time.time)
    period_days: int = 30
    total_events: int = 0
    total_exports: int = 0
    total_loads: int = 0
    total_shares: int = 0
    total_syncs: int = 0
    total_vault_stores: int = 0
    success_rate: float = 0.0
    sites: List[SiteStats] = field(default_factory=list)
    daily_activity: Dict[str, int] = field(default_factory=dict)
    top_sites: List[Dict[str, Any]] = field(default_factory=list)
    health_trend: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "generated_at": self.generated_at,
            "period_days": self.period_days,
            "total_events": self.total_events,
            "total_exports": self.total_exports,
            "total_loads": self.total_loads,
            "total_shares": self.total_shares,
            "total_syncs": self.total_syncs,
            "total_vault_stores": self.total_vault_stores,
            "success_rate": self.success_rate,
            "sites": [s.to_dict() for s in self.sites],
            "daily_activity": self.daily_activity,
            "top_sites": self.top_sites,
            "health_trend": self.health_trend,
        }


class AnalyticsEngine:
    """Session analytics engine with persistent storage."""

    def __init__(self, analytics_dir: Optional[Path] = None):
        self.analytics_dir = analytics_dir or ANALYTICS_DIR
        self.analytics_dir.mkdir(parents=True, exist_ok=True)
        self.events_file = self.analytics_dir / "events.jsonl"
        self.report_cache = self.analytics_dir / "report_cache.json"

    def record_event(
        self,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
        session_name: str = "",
        site: str = "",
        success: bool = True,
    ):
        """Record an analytics event."""
        event = AnalyticsEvent(
            event_type=event_type,
            data=data or {},
            session_name=session_name,
            site=site,
            success=success,
        )
        try:
            with open(self.events_file, "a") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except Exception as e:
            logger.debug(f"Failed to record analytics event: {e}")

    def _load_events(self, period_days: int = 30) -> List[AnalyticsEvent]:
        """Load events from the last N days."""
        events = []
        cutoff = time.time() - (period_days * 86400)
        try:
            if not self.events_file.exists():
                return []
            with open(self.events_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = AnalyticsEvent.from_dict(json.loads(line))
                        if event.timestamp >= cutoff:
                            events.append(event)
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception as e:
            logger.debug(f"Failed to load events: {e}")
        return events

    def generate_report(self, period_days: int = 30) -> AnalyticsReport:
        """Generate an analytics report for the given period."""
        events = self._load_events(period_days)
        report = AnalyticsReport(period_days=period_days, total_events=len(events))

        if not events:
            return report

        site_stats: Dict[str, SiteStats] = defaultdict(lambda: SiteStats(site=""))
        daily: Dict[str, int] = defaultdict(int)
        successes = 0
        health_samples: List[Dict[str, Any]] = []

        for event in events:
            day = datetime.fromtimestamp(
                event.timestamp, tz=timezone.utc
            ).strftime("%Y-%m-%d")
            daily[day] += 1

            if event.success:
                successes += 1

            site = event.site or "unknown"
            stats = site_stats[site]
            stats.site = site
            stats.total_events += 1
            stats.last_activity = max(stats.last_activity, event.timestamp)

            if event.event_type == "export":
                stats.exports += 1
                report.total_exports += 1
                cookies = event.data.get("cookies", 0)
                stats.total_cookies += cookies
            elif event.event_type == "load":
                stats.loads += 1
                report.total_loads += 1
            elif event.event_type == "share":
                stats.shares += 1
                report.total_shares += 1
            elif event.event_type == "sync":
                stats.syncs += 1
                report.total_syncs += 1
            elif event.event_type == "vault_store":
                stats.vault_stores += 1
                report.total_vault_stores += 1

            health = event.data.get("health")
            if health is not None:
                health_samples.append({"day": day, "site": site, "health": health})

        report.success_rate = (
            successes / len(events) if events else 0
        )
        report.sites = sorted(
            site_stats.values(), key=lambda s: s.total_events, reverse=True
        )
        report.daily_activity = dict(sorted(daily.items()))
        report.top_sites = [
            {"site": s.site, "events": s.total_events}
            for s in report.sites[:10]
        ]

        if health_samples:
            by_day: Dict[str, List[float]] = defaultdict(list)
            for h in health_samples:
                by_day[h["day"]].append(h["health"])
            report.health_trend = [
                {"day": d, "avg_health": sum(v) / len(v)}
                for d, v in sorted(by_day.items())
            ]

        return report

    def get_usage_summary(self) -> Dict[str, Any]:
        """Get a quick usage summary."""
        events = self._load_events(period_days=7)
        sites = set()
        for e in events:
            sites.add(e.site or "unknown")
        return {
            "events_last_7d": len(events),
            "active_sites": len(sites),
            "sites": sorted(sites),
        }

    def export_csv(self, output_path: str, period_days: int = 30):
        """Export events to CSV."""
        import csv
        events = self._load_events(period_days)
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "event_type", "timestamp", "session_name",
                    "site", "success", "data",
                ],
            )
            writer.writeheader()
            for event in events:
                row = event.to_dict()
                row["data"] = json.dumps(row["data"])
                writer.writerow(row)

    def cleanup(self, max_events: int = 10000):
        """Trim events file to max_events most recent entries."""
        events = self._load_events(period_days=3650)
        if len(events) <= max_events:
            return
        events = events[-max_events:]
        try:
            with open(self.events_file, "w") as f:
                for event in events:
                    f.write(json.dumps(event.to_dict()) + "\n")
        except Exception as e:
            logger.debug(f"Failed to cleanup events: {e}")
