"""Tests for gateway SessionStore and SessionRouter core."""

import json
import time
from pathlib import Path

import pytest

from tokenade.core.gateway.session_router import RoutingConfig, SessionRouter, SessionRoutingError
from tokenade.core.gateway.session_store import SessionRecord, SessionStore


def _write_session(tmp_path, name, site_name="github", auth_status="logged_in", expires_delta=172800, metadata=None):
    path = Path(tmp_path) / name
    path.write_text(json.dumps({
        "version": "1.0",
        "created_at": "2026-07-18T00:00:00",
        "site_name": site_name,
        "auth_status": auth_status,
        "cookies": [{
            "name": "sid",
            "value": "secret-cookie-value",
            "domain": f".{site_name}.com",
            "path": "/",
            "expires": time.time() + expires_delta,
        }],
        "metadata": metadata or {},
        "storage": {"local": {"https://example.com": {"token": "secret-storage-value"}}},
    }))
    return path


def _record(session_id, health_score=1.0, healthy=True, site_name="github"):
    return SessionRecord(
        id=session_id,
        path=f"/tmp/{session_id}.tokenade",
        site_name=site_name,
        auth_status="logged_in" if healthy else "unknown",
        cookie_count=1,
        health_score=health_score,
        healthy=healthy,
        metadata={"site_name": site_name},
    )


def test_loads_tokenade_files_from_directory(tmp_path):
    _write_session(tmp_path, "a.tokenade")
    _write_session(tmp_path, "b.tokenade")
    (tmp_path / "ignored.txt").write_text("{}")

    records = SessionStore().load_directory(tmp_path)

    assert len(records) == 2
    assert [Path(record.path).name for record in records] == ["a.tokenade", "b.tokenade"]


def test_builds_sanitized_session_records(tmp_path):
    path = _write_session(tmp_path, "session.tokenade", metadata={
        "session_id": "stable-id",
        "site_handler": {"plugin_name": "github-handler"},
        "source_network": {"raw_ip_stored": False, "ip": "203.0.113.9", "approx_country": "US"},
        "private_token": "must-not-leak",
    })

    record = SessionStore().load_file(path)
    serialized = record.to_dict()

    assert record.id == "stable-id"
    assert record.cookie_count == 1
    assert record.health_score == 1.0
    assert "cookies" not in serialized
    assert "storage" not in serialized
    assert "private_token" not in serialized["metadata"]
    assert "ip" not in serialized["metadata"]["source_network"]
    assert serialized["metadata"]["site_handler"] == {"plugin_name": "github-handler"}


def test_stable_id_falls_back_to_path_and_public_metadata(tmp_path):
    path = _write_session(tmp_path, "session.tokenade")
    first = SessionStore().load_file(path)
    second = SessionStore().load_file(path)

    assert first.id == second.id
    assert first.id != "session"


def test_round_robin_selection_is_deterministic():
    router = SessionRouter([_record("a"), _record("b")], RoutingConfig(strategy="round-robin"))

    assert [router.select().session.id for _ in range(4)] == ["a", "b", "a", "b"]


def test_random_selection_returns_valid_session():
    router = SessionRouter([_record("a"), _record("b")], RoutingConfig(strategy="random"))

    assert router.select().session.id in {"a", "b"}


def test_sticky_selection_returns_same_session_for_same_key():
    router = SessionRouter([_record("a"), _record("b")], RoutingConfig(strategy="sticky", sticky_by="site"))

    first = router.select({"site": "github"}).session.id
    second = router.select({"site": "github"}).session.id
    other = router.select({"site": "discord"}).session.id

    assert first == second
    assert other != first


def test_health_weighted_avoids_clearly_unhealthy_sessions():
    router = SessionRouter([
        _record("bad", health_score=0.0, healthy=False),
        _record("good", health_score=1.0, healthy=True),
    ], RoutingConfig(strategy="health-weighted"))

    assert {router.select().session.id for _ in range(20)} == {"good"}


def test_switch_interval_keeps_current_active_session():
    router = SessionRouter(
        [_record("a"), _record("b")],
        RoutingConfig(strategy="round-robin", switch_interval_seconds=5),
    )

    first = router.select(now=100.0)
    second = router.select(now=104.0)
    third = router.select(now=106.0)

    assert first.session.id == "a"
    assert second.session.id == "a"
    assert third.session.id == "b"


def test_manual_selection_can_ignore_switch_interval():
    router = SessionRouter(
        [_record("a"), _record("b")],
        RoutingConfig(strategy="round-robin", switch_interval_seconds=5),
    )

    first = router.select(now=100.0)
    second = router.select(now=101.0, ignore_switch_interval=True)

    assert first.session.id == "a"
    assert second.session.id == "b"


def test_enforces_minimum_switch_interval():
    with pytest.raises(SessionRoutingError, match="switch_interval_seconds must be >= 5"):
        RoutingConfig.from_dict({"object": "session", "strategy": "round-robin", "switch_interval_seconds": 4})


def test_routing_config_default_scope():
    config = RoutingConfig.from_dict({"default_scope": "future-only"})

    assert config.default_scope == "future-only"

    with pytest.raises(SessionRoutingError, match="routing.default_scope"):
        RoutingConfig.from_dict({"default_scope": "invalid"})


def test_rejects_non_session_routing_object():
    with pytest.raises(SessionRoutingError, match="routing.object must be session"):
        RoutingConfig.from_dict({"object": "proxy"})


def test_selection_benchmark_stays_under_hundreds_of_ms():
    records = [_record(str(index), health_score=1.0) for index in range(1000)]
    router = SessionRouter(records, RoutingConfig(strategy="round-robin"))

    started = time.perf_counter()
    for _ in range(1000):
        router.select()
    elapsed = time.perf_counter() - started

    assert elapsed < 0.2
