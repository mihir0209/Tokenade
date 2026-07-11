"""
Tests for SessionRotator — health-weighted rotation, cooldown, metrics, strategies.
"""
import json
import time
import tempfile
import os
from pathlib import Path

import pytest

from tokenade.core.refresh.session_rotator import (
    SessionEntry,
    RotatorMetrics,
    SessionRotator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_file(tmp_dir, filename="test.tokenade", site_name="example.com"):
    session = {
        "cookies": [
            {"name": "sid", "domain": ".example.com", "expires": time.time() + 3600,
             "secure": True, "httpOnly": True, "sameSite": "Lax", "value": "abc"},
        ],
        "metadata": {"site_name": site_name},
    }
    path = Path(tmp_dir) / filename
    path.write_text(json.dumps(session))
    return str(path)


# ---------------------------------------------------------------------------
# Data class tests
# ---------------------------------------------------------------------------

class TestSessionEntry:
    def test_defaults(self):
        e = SessionEntry(path="/tmp/s.tokenade", session_id="s", site_name="x.com")
        assert e.health_score == 100.0
        assert e.selection_count == 0
        assert e.cooldown_until == 0.0
        assert e.is_healthy is True

    def test_with_values(self):
        e = SessionEntry(
            path="/tmp/s.tokenade", session_id="s", site_name="x.com",
            health_score=75.0, cookie_count=10, selection_count=5,
            success_count=4, failure_count=1, cooldown_until=1000.0,
        )
        assert e.health_score == 75.0
        assert e.failure_count == 1


class TestRotatorMetrics:
    def test_defaults(self):
        m = RotatorMetrics()
        assert m.total_selections == 0
        assert m.total_failures == 0
        assert m.average_health == 0.0


# ---------------------------------------------------------------------------
# SessionRotator tests
# ---------------------------------------------------------------------------

class TestSessionRotatorLoad:
    def test_load_sessions_from_dir(self, tmp_path):
        _make_session_file(str(tmp_path), "s1.tokenade", "site1.com")
        _make_session_file(str(tmp_path), "s2.tokenade", "site2.com")

        rotator = SessionRotator(sessions_dir=str(tmp_path))
        count = rotator.load_sessions()
        assert count == 2

    def test_load_sessions_from_paths(self, tmp_path):
        p1 = _make_session_file(str(tmp_path), "s1.tokenade")
        p2 = _make_session_file(str(tmp_path), "s2.tokenade")

        rotator = SessionRotator()
        count = rotator.load_sessions(session_paths=[p1, p2])
        assert count == 2

    def test_load_empty_dir(self, tmp_path):
        rotator = SessionRotator(sessions_dir=str(tmp_path))
        count = rotator.load_sessions()
        assert count == 0

    def test_load_no_sessions_dir(self):
        rotator = SessionRotator()
        count = rotator.load_sessions()
        assert count == 0

    def test_load_invalid_file(self, tmp_path):
        path = Path(tmp_path) / "bad.tokenade"
        path.write_text("not json")
        rotator = SessionRotator(sessions_dir=str(tmp_path))
        count = rotator.load_sessions()
        assert count == 0

    def test_load_nonexistent_file(self):
        rotator = SessionRotator()
        count = rotator.load_sessions(session_paths=["/nonexistent/file.tokenade"])
        assert count == 0

    def test_add_session(self, tmp_path):
        path = _make_session_file(str(tmp_path))
        rotator = SessionRotator()
        entry = rotator.add_session(path, health_score=85.0)
        assert entry is not None
        assert entry.health_score == 85.0
        assert "test" in rotator._entries

    def test_add_nonexistent_session(self):
        rotator = SessionRotator()
        entry = rotator.add_session("/nonexistent.tokenade")
        assert entry is None

    def test_remove_session(self, tmp_path):
        path = _make_session_file(str(tmp_path))
        rotator = SessionRotator()
        rotator.add_session(path)
        rotator.remove_session("test")
        assert "test" not in rotator._entries


class TestSessionRotatorStrategies:
    def test_health_weighted_selects_healthy(self, tmp_path):
        p1 = _make_session_file(str(tmp_path), "s1.tokenade", "site1.com")
        p2 = _make_session_file(str(tmp_path), "s2.tokenade", "site2.com")

        rotator = SessionRotator(strategy="health-weighted")
        rotator.load_sessions(session_paths=[p1, p2])
        rotator.update_health("s1", 100.0)
        rotator.update_health("s2", 10.0)

        # Run multiple times to verify weighting
        selections = set()
        for _ in range(50):
            path = rotator.next()
            selections.add(Path(path).name)

        # s1 (high health) should be selected more often
        assert "s1.tokenade" in selections

    def test_round_robin_cycles(self, tmp_path):
        p1 = _make_session_file(str(tmp_path), "s1.tokenade")
        p2 = _make_session_file(str(tmp_path), "s2.tokenade")

        rotator = SessionRotator(strategy="round-robin")
        rotator.load_sessions(session_paths=[p1, p2])

        results = []
        for _ in range(4):
            results.append(Path(rotator.next()).name)

        # Should alternate: s1, s2, s1, s2
        assert results[0] == results[2]
        assert results[1] == results[3]

    def test_random_selects(self, tmp_path):
        p1 = _make_session_file(str(tmp_path), "s1.tokenade")
        rotator = SessionRotator(strategy="random")
        rotator.load_sessions(session_paths=[p1])

        path = rotator.next()
        assert path is not None

    def test_lru_selects_least_recent(self, tmp_path):
        p1 = _make_session_file(str(tmp_path), "s1.tokenade")
        p2 = _make_session_file(str(tmp_path), "s2.tokenade")

        rotator = SessionRotator(strategy="least-recently-used")
        rotator.load_sessions(session_paths=[p1, p2])

        # Select first
        first = Path(rotator.next()).name
        # Select second (should be the other one)
        second = Path(rotator.next()).name
        assert first != second

    def test_single_session_returns_itself(self, tmp_path):
        p1 = _make_session_file(str(tmp_path))
        rotator = SessionRotator(strategy="health-weighted")
        rotator.load_sessions(session_paths=[p1])

        path = rotator.next()
        assert Path(path).name == "test.tokenade"

    def test_no_sessions_returns_none(self):
        rotator = SessionRotator()
        assert rotator.next() is None

    def test_invalid_strategy_fallback(self, tmp_path):
        p1 = _make_session_file(str(tmp_path))
        rotator = SessionRotator(strategy="nonexistent")
        rotator.load_sessions(session_paths=[p1])

        path = rotator.next()
        assert path is not None


class TestSessionRotatorCooldown:
    def test_cooldown_blocks_session(self, tmp_path):
        p1 = _make_session_file(str(tmp_path), "s1.tokenade")
        p2 = _make_session_file(str(tmp_path), "s2.tokenade")

        rotator = SessionRotator(strategy="round-robin")
        rotator.load_sessions(session_paths=[p1, p2])

        # Put s1 on cooldown
        rotator.set_cooldown("s1", seconds=60)

        # s2 should always be selected
        for _ in range(5):
            path = Path(rotator.next()).name
            assert path == "s2.tokenade"

    def test_cooldown_expires(self, tmp_path):
        p1 = _make_session_file(str(tmp_path), "s1.tokenade")
        rotator = SessionRotator(strategy="round-robin")
        rotator.load_sessions(session_paths=[p1])

        # Put on short cooldown
        rotator.set_cooldown("s1", seconds=0.01)
        time.sleep(0.02)

        path = rotator.next()
        assert path is not None

    def test_record_failure_applies_cooldown(self, tmp_path):
        p1 = _make_session_file(str(tmp_path), "s1.tokenade")
        p2 = _make_session_file(str(tmp_path), "s2.tokenade")

        rotator = SessionRotator(strategy="round-robin")
        rotator.load_sessions(session_paths=[p1, p2])

        rotator.record_failure("s1")
        entry = rotator._entries["s1"]
        assert entry.failure_count == 1
        assert entry.cooldown_until > time.time()

    def test_record_success(self, tmp_path):
        p1 = _make_session_file(str(tmp_path))
        rotator = SessionRotator()
        rotator.load_sessions(session_paths=[p1])

        rotator.record_success("test")
        assert rotator._entries["test"].success_count == 1


class TestSessionRotatorHealth:
    def test_update_health(self, tmp_path):
        p1 = _make_session_file(str(tmp_path))
        rotator = SessionRotator(min_health=20.0)
        rotator.load_sessions(session_paths=[p1])

        rotator.update_health("test", 50.0)
        assert rotator._entries["test"].health_score == 50.0
        assert rotator._entries["test"].is_healthy is True

    def test_low_health_marks_unhealthy(self, tmp_path):
        p1 = _make_session_file(str(tmp_path))
        rotator = SessionRotator(min_health=50.0)
        rotator.load_sessions(session_paths=[p1])

        rotator.update_health("test", 10.0)
        assert rotator._entries["test"].is_healthy is False

    def test_unhealthy_session_not_selected(self, tmp_path):
        p1 = _make_session_file(str(tmp_path), "s1.tokenade")
        p2 = _make_session_file(str(tmp_path), "s2.tokenade")

        rotator = SessionRotator(strategy="round-robin", min_health=50.0)
        rotator.load_sessions(session_paths=[p1, p2])

        rotator.update_health("s1", 10.0)  # unhealthy
        rotator.update_health("s2", 100.0)

        for _ in range(5):
            path = Path(rotator.next()).name
            assert path == "s2.tokenade"


class TestSessionRotatorMetrics:
    def test_get_status(self, tmp_path):
        p1 = _make_session_file(str(tmp_path))
        rotator = SessionRotator(strategy="health-weighted")
        rotator.load_sessions(session_paths=[p1])

        rotator.next()
        status = rotator.get_status()

        assert status["strategy"] == "health-weighted"
        assert status["total_sessions"] == 1
        assert status["available_sessions"] == 1
        assert status["metrics"]["total_selections"] == 1
        assert len(status["sessions"]) == 1

    def test_average_health(self, tmp_path):
        p1 = _make_session_file(str(tmp_path), "s1.tokenade")
        p2 = _make_session_file(str(tmp_path), "s2.tokenade")

        rotator = SessionRotator()
        rotator.load_sessions(session_paths=[p1, p2])
        rotator.update_health("s1", 100.0)
        rotator.update_health("s2", 60.0)

        assert rotator._average_health() == 80.0

    def test_average_health_empty(self):
        rotator = SessionRotator()
        assert rotator._average_health() == 0.0

    def test_selection_count_increments(self, tmp_path):
        p1 = _make_session_file(str(tmp_path))
        rotator = SessionRotator()
        rotator.load_sessions(session_paths=[p1])

        rotator.next()
        assert rotator._entries["test"].selection_count == 1
        rotator.next()
        assert rotator._entries["test"].selection_count == 2


class TestSessionRotatorState:
    def test_save_and_load_state(self, tmp_path):
        p1 = _make_session_file(str(tmp_path))
        state_file = str(tmp_path / "state.json")

        rotator = SessionRotator(strategy="round-robin")
        rotator.load_sessions(session_paths=[p1])
        rotator.next()
        rotator.next()
        rotator.save_state(state_file)

        # Load into new rotator
        rotator2 = SessionRotator(strategy="round-robin")
        rotator2.load_sessions(session_paths=[p1])
        rotator2.load_state(state_file)

        assert rotator2._round_robin_index == 2
        assert rotator2._entries["test"].selection_count == 2

    def test_load_state_nonexistent(self):
        rotator = SessionRotator()
        rotator.load_state("/nonexistent/state.json")  # should not raise


class TestSessionRotatorEdgeCases:
    def test_all_sessions_on_cooldown(self, tmp_path):
        p1 = _make_session_file(str(tmp_path))
        rotator = SessionRotator()
        rotator.load_sessions(session_paths=[p1])

        rotator.set_cooldown("test", seconds=9999)
        result = rotator.next()
        assert result is None

    def test_remove_nonexistent_session(self):
        rotator = SessionRotator()
        rotator.remove_session("missing")  # should not raise

    def test_update_health_nonexistent(self):
        rotator = SessionRotator()
        rotator.update_health("missing", 50.0)  # should not raise

    def test_record_failure_nonexistent(self):
        rotator = SessionRotator()
        rotator.record_failure("missing")  # should not raise

    def test_record_success_nonexistent(self):
        rotator = SessionRotator()
        rotator.record_success("missing")  # should not raise
