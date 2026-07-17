# Phase 3: Hidden Gateway API Skeleton

**Date:** 2026-07-18  
**Status:** Planned  
**Parent plan:** `.agent/plans/2026-07-18-gateway-request-framework.md`

## Goal

Introduce a hidden `gateway --request request.json` command with a lightweight API control plane backed by the request framework and SessionRouter.

## Scope

- Add hidden CLI command:
  ```bash
  tokenade gateway --request request.json
  ```
- Validate request JSON.
- Validate required plugins.
- Load sessions.
- Build SessionRouter.
- Start API endpoints:
  - `GET /status`
  - `GET /sessions`
  - `POST /route/next`
  - `POST /route/select`
- No CDP/browser context switching in this phase.

## Why Hidden

`gateway` should not be visible in top-level help until it can serve/route sessions end-to-end with browser/CDP witness tests. This phase creates the control plane contract first.

## Request Shape

```json
{
  "version": "1",
  "operation": "gateway",
  "sessions": {
    "dir": "./sessions",
    "pattern": "*.tokenade"
  },
  "gateway": {
    "host": "127.0.0.1",
    "port": 9222,
    "backend": "cdp"
  },
  "routing": {
    "object": "session",
    "strategy": "health-weighted",
    "switch_interval_seconds": 30,
    "sticky_by": "site",
    "failover": true,
    "drain_existing_tabs": true
  },
  "plugins": []
}
```

## Endpoint Contracts

### `GET /status`

Returns:

```json
{
  "success": true,
  "operation": "gateway",
  "active_session": null,
  "session_count": 7,
  "routing": {
    "strategy": "health-weighted"
  },
  "plugins": []
}
```

### `GET /sessions`

Returns sanitized session records only. No cookies, tokens, localStorage, proxy credentials, or secrets.

### `POST /route/next`

Selects next session according to routing strategy and returns sanitized metadata.

### `POST /route/select`

Accepts a session ID/path/site selector and sets active session if valid.

## Candidate Files

- `tokenade/cli/__init__.py`
- `tokenade/cli/gateway.py`
- `tokenade/core/gateway/server.py`
- `tokenade/core/gateway/session_router.py`
- `tokenade/tests/test_cli_gateway.py`
- `tokenade/tests/test_gateway_server.py`

## Tests

- `gateway` is registered but hidden from top-level help.
- `gateway --help` works.
- Valid request starts API in test mode or through app factory.
- `/status` returns request/gateway state.
- `/sessions` returns sanitized sessions.
- `/route/next` changes active session according to strategy.
- `/route/select` validates selectors and rejects invalid ones.
- Missing required plugin fails before server starts.
- Switch interval floor is enforced.

## Witness

Use `/tmp/real-sessions` with a generated request file:

```bash
tokenade gateway --request /tmp/tokenade-gateway.request.json
```

Then query:

```bash
curl http://127.0.0.1:9222/status
curl http://127.0.0.1:9222/sessions
curl -X POST http://127.0.0.1:9222/route/next
```

## Exit Criteria

- Hidden gateway command validates request and serves control endpoints.
- Endpoint responses are sanitized.
- Real sessions can be loaded and routed.
- No user-visible top-level promotion yet.
