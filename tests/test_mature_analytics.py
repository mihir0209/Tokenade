import os
import sqlite3
import time

from tokenade.core.analytics import (
    AnalyticsConfig,
    AnalyticsOperation,
    AnalyticsOutcome,
    LocalAnalytics,
)


def engine(tmp_path, enabled=False):
    return LocalAnalytics(
        AnalyticsConfig(
            enabled=enabled, directory=str(tmp_path / "analytics"), retention_days=30
        )
    )


def test_disabled_analytics_writes_nothing(tmp_path):
    analytics = engine(tmp_path)
    assert analytics.record("export", "success") is False
    assert not (tmp_path / "analytics/analytics.sqlite3").exists()


def test_enable_records_closed_schema_and_secure_permissions(tmp_path):
    analytics = engine(tmp_path)
    analytics.enable(30)
    assert analytics.record(
        "export",
        "success",
        duration_ms=20,
        dimensions={
            "browser_family": "firefox",
            "source_kind": "profile",
            "encrypted": True,
            "cookie_count_bucket": "1-10",
            "storage_present": False,
        },
    )
    status = analytics.status()
    assert status["event_count"] == 1
    if os.name != "nt":
        assert (tmp_path / "analytics").stat().st_mode & 0o777 == 0o700
        assert (
            tmp_path / "analytics/analytics.sqlite3"
        ).stat().st_mode & 0o777 == 0o600


def test_sensitive_unknown_dimensions_are_rejected(tmp_path):
    analytics = engine(tmp_path, enabled=True)
    assert (
        analytics.record("export", "success", dimensions={"domain": "secret.example"})
        is False
    )
    assert analytics.status()["event_count"] == 0


def test_identifying_values_inside_allowed_dimensions_are_rejected(tmp_path):
    analytics = engine(tmp_path, enabled=True)
    assert (
        analytics.record(
            "export",
            "success",
            dimensions={
                "browser_family": "secret.example/token=abc",
                "source_kind": "profile",
                "encrypted": True,
                "cookie_count_bucket": "1-10",
                "storage_present": False,
            },
        )
        is False
    )
    assert analytics.status()["event_count"] == 0


def test_report_uses_outcomes_and_utc_days(tmp_path):
    analytics = engine(tmp_path, enabled=True)
    analytics.record(
        "load",
        "success",
        duration_ms=10,
        dimensions={
            "browser_family": "chromium",
            "visible": True,
            "validation_requested": False,
            "storage_present": False,
        },
    )
    analytics.record(
        "load",
        "failure",
        duration_ms=30,
        dimensions={
            "browser_family": "chromium",
            "visible": True,
            "validation_requested": False,
            "storage_present": False,
        },
    )
    analytics.record(
        "load",
        "cancelled",
        dimensions={
            "browser_family": "chromium",
            "visible": True,
            "validation_requested": False,
            "storage_present": False,
        },
    )
    report = analytics.report(1)
    assert report["total_operations"] == 3
    assert report["outcomes"]["success_rate"] == 0.5
    assert report["by_operation"]["load"]["p50_ms"] == 30


def test_cleanup_returns_removed_count(tmp_path):
    analytics = engine(tmp_path, enabled=True)
    analytics.record("vault_retrieve", "success")
    with sqlite3.connect(analytics.db_path) as db:
        db.execute(
            "UPDATE events SET occurred_at_ms=?",
            (int((time.time() - 60 * 86400) * 1000),),
        )
    assert analytics.cleanup(older_than_days=30) == 1
    assert analytics.status()["event_count"] == 0


def test_legacy_jsonl_is_reported_not_imported(tmp_path):
    root = tmp_path / "analytics"
    root.mkdir()
    (root / "events.jsonl").write_text('{"metadata":{"token":"secret"}}\n')
    analytics = engine(tmp_path)
    status = analytics.status()
    assert status["legacy_file"].endswith("events.jsonl")
    assert status["event_count"] == 0


def test_aggregate_csv_excludes_event_ids_and_timestamps(tmp_path):
    analytics = engine(tmp_path, enabled=True)
    analytics.record("vault_retrieve", "success")
    output = analytics.export_csv(tmp_path / "report.csv", days=1)
    text = output.read_text()
    assert "operation" in text
    assert "event_id" not in text
    assert "occurred_at" not in text


def test_delete_all_removes_database(tmp_path):
    analytics = engine(tmp_path, enabled=True)
    analytics.record("vault_retrieve", "success")
    assert analytics.delete_all() == 1
    assert not analytics.db_path.exists()


def test_legacy_identifying_writer_fails_closed(tmp_path):
    from tokenade.core.monitoring.analytics import SessionAnalytics

    try:
        SessionAnalytics(storage_dir=str(tmp_path)).record_event(
            "session-id", "export", {"token": "secret"}
        )
    except RuntimeError as exc:
        assert "disabled" in str(exc)
    else:
        raise AssertionError("legacy writer accepted identifying analytics")
