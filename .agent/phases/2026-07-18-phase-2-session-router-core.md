# Phase 2: SessionRouter Core

**Date:** 2026-07-18  
**Status:** Planned  
**Parent plan:** `.agent/plans/2026-07-18-gateway-request-framework.md`

## Goal

Build a context-neutral session routing engine that can select the active `.tokenade` session quickly and safely before browser/CDP integration.

## Scope

- Add session records for routing.
- Load sessions from a configured directory/pattern.
- Support route strategies.
- Enforce timing constraints.
- Produce routing decisions in under hundreds of milliseconds for practical session counts.

## Gateway Rotation Semantics

Rotation means:

```text
Change the active isolated session context for future work.
```

It does not mean:

```text
Mutate cookies/storage in an existing live page.
```

Existing tabs drain. New tabs/new navigations use the current active session.

## Routing Config

```json
{
  "routing": {
    "object": "session",
    "strategy": "health-weighted",
    "switch_interval_seconds": 30,
    "sticky_by": "site",
    "failover": true,
    "drain_existing_tabs": true
  }
}
```

## Core Rules

- `routing.object` must be `session` in this phase.
- `switch_interval_seconds` must be `>= 5` when present.
- Supported strategies:
  - `round-robin`
  - `random`
  - `health-weighted`
  - `sticky`
- `health-weighted` should prefer sessions with better health but not require browser runtime.
- Router should expose selected session metadata without leaking cookies or secrets.

## Candidate Files

- `tokenade/core/gateway/__init__.py`
- `tokenade/core/gateway/session_router.py`
- `tokenade/core/gateway/session_store.py`
- `tokenade/tests/test_gateway_session_router.py`

## Data Model Draft

Session record:

```python
{
    "id": "stable-session-id",
    "path": "...",
    "site_name": "github",
    "auth_status": "logged_in",
    "cookie_count": 9,
    "health_score": 1.0,
    "metadata": {...sanitized...},
}
```

Stable session ID preference:

- `metadata.session_id` if present.
- Otherwise deterministic hash of absolute path plus created_at/site, not cookie values.

## Tests

- Loads `.tokenade` files from directory.
- Builds sanitized session records.
- Round-robin selection is deterministic.
- Random selection returns a valid session.
- Sticky selection returns the same session for the same key.
- Health-weighted avoids clearly unhealthy sessions where alternatives exist.
- Enforces `switch_interval_seconds >= 5`.
- Selection benchmark stays under hundreds of ms with real-session-like fixtures.

## Witness

Use `/tmp/real-sessions`:

```bash
python3 -m pytest tokenade/tests/test_gateway_session_router.py -q
```

and a small script/CLI call in Phase 3 to show router can load and select among real sessions.

## Exit Criteria

- Router can load real `.tokenade` files.
- Router selects sessions with supported strategies.
- Routing decisions are sanitized and fast.
- No browser/CDP dependency exists in router core.
