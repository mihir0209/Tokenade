# Phase 2: SessionRouter Core

**Date:** 2026-07-18  
**Status:** Complete  
**Parent plan:** `.agent/plans/2026-07-18-gateway-request-framework.md`

## Progress

- 2026-07-18: Started implementation.
- 2026-07-18: Confirmed existing `SessionRotator` remains tied to old refresh/proxy-style rotation and returns paths only; Phase 2 will add a new context-neutral `tokenade.core.gateway` router/store with sanitized records.
- 2026-07-18: Added `tokenade.core.gateway` package with `SessionStore`, `SessionRecord`, `RoutingConfig`, `SessionRouter`, and `RoutingDecision`.
- 2026-07-18: Implemented sanitized `.tokenade` loading, stable session IDs, `round-robin`, `random`, `health-weighted`, `sticky`, failover filtering, and `switch_interval_seconds >= 5` validation.
- 2026-07-18: Added focused tests in `tokenade/tests/test_gateway_session_router.py`.
- 2026-07-18: Verified focused router suite, Phase 1/Phase 2 regression slice, and flake8 target all pass.
- 2026-07-18: Witnessed real load/selection from `/tmp/real-sessions`: loaded 7 `.tokenade` files and selected `/tmp/real-sessions/github.tokenade` with sanitized decision output.

## Verification

```bash
python3 -m pytest tokenade/tests/test_gateway_session_router.py -q
python3 -m pytest tokenade/tests/test_gateway_session_router.py tokenade/tests/test_request_config.py tokenade/tests/test_plugin_run_cli.py tokenade/tests/test_session_rotator.py -q
python3 -m flake8 tokenade/core/gateway tokenade/tests/test_gateway_session_router.py --max-line-length=120 --ignore=E501,W503,W293,E203,F541,F841,E306,E402,E226,E128,E127,E731,F821,F401,F811,E401,E704
python3 - <<'PY'
import json
from tokenade.core.gateway import SessionRouter, SessionStore
store = SessionStore()
records = store.load_directory('/tmp/real-sessions')
router = SessionRouter.from_config(records, {'object': 'session', 'strategy': 'health-weighted', 'switch_interval_seconds': 5})
decision = router.select({'site': 'github'})
print(json.dumps({'loaded': len(records), 'decision': decision.to_dict()}, indent=2))
PY
```

Witness result:

```json
{
  "loaded": 7,
  "decision": {
    "session": {
      "path": "/tmp/real-sessions/github.tokenade",
      "site_name": "github",
      "auth_status": "logged_in",
      "cookie_count": 9,
      "health_score": 1.0,
      "healthy": true
    },
    "strategy": "health-weighted",
    "reason": "health-weighted"
  }
}
```

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
