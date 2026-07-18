"""Fast session selection for Tokenade gateway operations."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from tokenade.core.gateway.session_store import SessionRecord


class SessionRoutingError(ValueError):
    """Raised when routing cannot be configured or completed."""


@dataclass(frozen=True)
class RoutingConfig:
    """Validated routing settings for session rotation."""

    object: str = "session"
    strategy: str = "health-weighted"
    switch_interval_seconds: Optional[float] = None
    sticky_by: str = "site"
    failover: bool = True
    drain_existing_tabs: bool = True

    STRATEGIES = ("round-robin", "random", "health-weighted", "sticky")

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "RoutingConfig":
        raw = data or {}
        if not isinstance(raw, dict):
            raise SessionRoutingError("routing must be an object")

        route_object = raw.get("object", "session")
        if route_object != "session":
            raise SessionRoutingError("routing.object must be session")

        strategy = raw.get("strategy", "health-weighted")
        if strategy not in cls.STRATEGIES:
            raise SessionRoutingError(f"unsupported routing.strategy: {strategy}")

        interval = raw.get("switch_interval_seconds")
        if interval is not None:
            if not isinstance(interval, (int, float)) or isinstance(interval, bool):
                raise SessionRoutingError("routing.switch_interval_seconds must be a number")
            if interval < 5:
                raise SessionRoutingError("routing.switch_interval_seconds must be >= 5")

        sticky_by = raw.get("sticky_by", "site")
        if not isinstance(sticky_by, str) or not sticky_by.strip():
            raise SessionRoutingError("routing.sticky_by must be a string")

        failover = raw.get("failover", True)
        if not isinstance(failover, bool):
            raise SessionRoutingError("routing.failover must be a boolean")

        drain_existing_tabs = raw.get("drain_existing_tabs", True)
        if not isinstance(drain_existing_tabs, bool):
            raise SessionRoutingError("routing.drain_existing_tabs must be a boolean")

        return cls(
            object=route_object,
            strategy=strategy,
            switch_interval_seconds=float(interval) if interval is not None else None,
            sticky_by=sticky_by.strip(),
            failover=failover,
            drain_existing_tabs=drain_existing_tabs,
        )


@dataclass(frozen=True)
class RoutingDecision:
    """A sanitized routing decision for future gateway work."""

    session: SessionRecord
    strategy: str
    reason: str
    selected_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session": self.session.to_dict(),
            "strategy": self.strategy,
            "reason": self.reason,
            "selected_at": self.selected_at,
        }


class SessionRouter:
    """Select active session contexts without browser/CDP dependencies."""

    def __init__(self, sessions: List[SessionRecord], config: Optional[RoutingConfig] = None):
        self.sessions = list(sessions)
        self.config = config or RoutingConfig()
        self._round_robin_index = 0
        self._active: Optional[RoutingDecision] = None
        self._sticky: Dict[str, SessionRecord] = {}

    @classmethod
    def from_config(cls, sessions: List[SessionRecord], routing: Optional[Dict[str, Any]] = None) -> "SessionRouter":
        return cls(sessions, RoutingConfig.from_dict(routing))

    def select(self, context: Optional[Dict[str, Any]] = None, now: Optional[float] = None) -> RoutingDecision:
        """Return the active session routing decision."""
        selected_at = time.time() if now is None else now
        available = self._available_sessions()
        if not available:
            raise SessionRoutingError("no routable sessions available")

        if self._active and self._within_switch_interval(selected_at):
            return RoutingDecision(
                session=self._active.session,
                strategy=self.config.strategy,
                reason="within switch interval",
                selected_at=selected_at,
            )

        if self.config.strategy == "round-robin":
            session = self._select_round_robin(available)
            reason = "round-robin"
        elif self.config.strategy == "random":
            session = random.choice(available)
            reason = "random"
        elif self.config.strategy == "sticky":
            session, reason = self._select_sticky(available, context or {})
        else:
            session, reason = self._select_health_weighted(available)

        decision = RoutingDecision(
            session=session,
            strategy=self.config.strategy,
            reason=reason,
            selected_at=selected_at,
        )
        self._active = decision
        return decision

    def _available_sessions(self) -> List[SessionRecord]:
        if self.config.failover:
            healthy = [session for session in self.sessions if session.healthy and session.health_score > 0]
            if healthy:
                return healthy
        return list(self.sessions)

    def _within_switch_interval(self, now: float) -> bool:
        interval = self.config.switch_interval_seconds
        return bool(interval is not None and self._active and now - self._active.selected_at < interval)

    def _select_round_robin(self, available: List[SessionRecord]) -> SessionRecord:
        session = available[self._round_robin_index % len(available)]
        self._round_robin_index += 1
        return session

    def _select_sticky(self, available: List[SessionRecord], context: Dict[str, Any]) -> tuple[SessionRecord, str]:
        sticky_key = self._sticky_key(context)
        if sticky_key and sticky_key in self._sticky and self._sticky[sticky_key] in available:
            return self._sticky[sticky_key], f"sticky:{sticky_key}"

        session = self._select_round_robin(available)
        if sticky_key:
            self._sticky[sticky_key] = session
            return session, f"sticky:{sticky_key}"
        return session, "sticky:no-key"

    def _select_health_weighted(self, available: List[SessionRecord]) -> tuple[SessionRecord, str]:
        positive = [session for session in available if session.health_score > 0]
        candidates = positive or available
        if len(candidates) == 1:
            return candidates[0], "health-weighted:single-candidate"

        total = sum(session.health_score for session in candidates)
        if total <= 0:
            return random.choice(candidates), "health-weighted:all-zero-random"

        threshold = random.uniform(0, total)
        cumulative = 0.0
        for session in candidates:
            cumulative += session.health_score
            if cumulative >= threshold:
                return session, "health-weighted"
        return candidates[-1], "health-weighted"

    def _sticky_key(self, context: Dict[str, Any]) -> Optional[str]:
        value = context.get(self.config.sticky_by)
        if value is None and self.config.sticky_by == "site":
            value = context.get("site_name")
        if value is None:
            value = context.get("sticky_key")
        return str(value) if value is not None else None
