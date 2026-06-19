"""
Tests for SessionAnalytics — event recording, reports, session analytics, cleanup.
"""
import json
import time
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tokenade.core.monitoring.analytics import SessionAnalytics, SessionEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_analytics(tmp_path):
    """Create a SessionAnalytics with a temp storage dir."""
    return SessionAnalytics(storage_dir=str(tmp_path / "analytics"))


# ---------------------------------------------------------------------------
# Data class tests
# ---------------------------------------------------------------------------

class TestSessionEvent:
    def test_creation(self):
        e = SessionEvent(
            timestamp=1000.0,
            session_id="s1",
            event_type="export",
            metadata={"browser": "firefox"},
        )
        assert e.session_id == "s1"
        assert e.event_type == "export"
        assert e.metadata == {"browser": "firefox"}

    def test_default_metadata(self):
        e = SessionEvent(timestamp=1000.0, session_id="s1", event_type="load")
        assert e.metadata == {}


# ---------------------------------------------------------------------------
# SessionAnalytics tests
# ---------------------------------------------------------------------------

class TestAnalyticsRecordEvent:
    def test_record_event(self, tmp_path):
        analytics = _make_analytics(tmp_path)
        analytics.record_event("s1", "export", {"browser": "firefox"})
        events = analytics.get_events()
        assert len(events) == 1
        assert events[0]["session_id"] == "s1"
        assert events[0]["event_type"] == "export"

    def test_record_multiple_events(self, tmp_path):
        analytics = _make_analytics(tmp_path)
        analytics.record_event("s1", "export")
        analytics.record_event("s1", "load")
        analytics.record_event("s2", "export")
        events = analytics.get_events()
        assert len(events) == 3

    def test_record_default_metadata(self, tmp_path):
        analytics = _make_analytics(tmp_path)
        analytics.record_event("s1", "health_check")
        events = analytics.get_events()
        assert events[0]["metadata"] == {}


class TestAnalyticsQueryEvents:
    def test_filter_by_session_id(self, tmp_path):
        analytics = _make_analytics(tmp_path)
        analytics.record_event("s1", "export")
        analytics.record_event("s2", "export")
        analytics.record_event("s1", "load")

        events = analytics.get_events(session_id="s1")
        assert len(events) == 2

    def test_filter_by_event_type(self, tmp_path):
        analytics = _make_analytics(tmp_path)
        analytics.record_event("s1", "export")
        analytics.record_event("s1", "load")
        analytics.record_event("s1", "export")

        events = analytics.get_events(event_type="load")
        assert len(events) == 1

    def test_filter_by_since(self, tmp_path):
        analytics = _make_analytics(tmp_path)
        now = time.time()
        analytics.record_event("s1", "export")
        time.sleep(0.01)
        cutoff = time.time()
        analytics.record_event("s1", "load")

        events = analytics.get_events(since=cutoff)
        assert len(events) == 1
        assert events[0]["event_type"] == "load"

    def test_limit(self, tmp_path):
        analytics = _make_analytics(tmp_path)
        for _ in range(10):
            analytics.record_event("s1", "export")
        events = analytics.get_events(limit=3)
        assert len(events) == 3


class TestAnalyticsUsageReport:
    def test_empty_report(self, tmp_path):
        analytics = _make_analytics(tmp_path)
        report = analytics.get_usage_report()
        assert report["total_events"] == 0
        assert report["total_sessions"] == 0

    def test_report_with_events(self, tmp_path):
        analytics = _make_analytics(tmp_path)
        analytics.record_event("s1", "export")
        analytics.record_event("s1", "load")
        analytics.record_event("s2", "export")

        report = analytics.get_usage_report()
        assert report["total_events"] == 3
        assert report["total_sessions"] == 2
        assert report["events_by_type"]["export"] == 2
        assert report["events_by_type"]["load"] == 1

    def test_report_top_sessions(self, tmp_path):
        analytics = _make_analytics(tmp_path)
        for _ in range(5):
            analytics.record_event("s1", "export")
        for _ in range(2):
            analytics.record_event("s2", "export")

        report = analytics.get_usage_report()
        assert report["top_sessions"][0]["session_id"] == "s1"
        assert report["top_sessions"][0]["event_count"] == 5

    def test_report_daily_activity(self, tmp_path):
        analytics = _make_analytics(tmp_path)
        analytics.record_event("s1", "export")

        report = analytics.get_usage_report()
        today = time.strftime("%Y-%m-%d")
        assert today in report["daily_activity"]

    def test_report_custom_period(self, tmp_path):
        analytics = _make_analytics(tmp_path)
        analytics.record_event("s1", "export")

        report = analytics.get_usage_report(days=1)
        assert report["period_days"] == 1


class TestAnalyticsSessionAnalytics:
    def test_no_data(self, tmp_path):
        analytics = _make_analytics(tmp_path)
        data = analytics.get_session_analytics("missing")
        assert data["total_events"] == 0

    def test_with_data(self, tmp_path):
        analytics = _make_analytics(tmp_path)
        analytics.record_event("s1", "export")
        analytics.record_event("s1", "load")
        analytics.record_event("s1", "refresh")

        data = analytics.get_session_analytics("s1")
        assert data["total_events"] == 3
        assert data["lifespan_hours"] >= 0
        assert data["events_by_type"]["export"] == 1


class TestAnalyticsCleanup:
    def test_cleanup_old_events(self, tmp_path):
        analytics = _make_analytics(tmp_path)
        analytics.record_event("s1", "export")

        # Events just recorded, should not be cleaned
        analytics.cleanup(max_age_days=1)
        events = analytics.get_events()
        assert len(events) == 1

    def test_cleanup_with_old_events(self, tmp_path):
        analytics = _make_analytics(tmp_path)
        # Manually write an old event
        old_event = {
            "timestamp": time.time() - (100 * 86400),  # 100 days ago
            "session_id": "s1",
            "event_type": "export",
            "metadata": {},
        }
        analytics._append_event(SessionEvent(**old_event))
        analytics.record_event("s1", "load")

        analytics.cleanup(max_age_days=90)
        events = analytics.get_events()
        assert len(events) == 1
        assert events[0]["event_type"] == "load"


class TestAnalyticsFilePersistence:
    def test_events_persist_across_instances(self, tmp_path):
        dir_path = str(tmp_path / "analytics")

        a1 = SessionAnalytics(storage_dir=dir_path)
        a1.record_event("s1", "export")

        a2 = SessionAnalytics(storage_dir=dir_path)
        events = a2.get_events()
        assert len(events) == 1

    def test_corrupted_events_file_handled(self, tmp_path):
        analytics = _make_analytics(tmp_path)
        events_file = analytics._events_file
        events_file.write_text("not json\nvalid json?\n")

        events = analytics.get_events()
        # Should handle gracefully (may be empty or partial)
        assert isinstance(events, list)
