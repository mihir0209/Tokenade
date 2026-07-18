# Phase 3: Hidden Gateway API Skeleton

**Date:** 2026-07-18  
**Status:** Complete  
**Parent plan:** `.agent/plans/2026-07-18-gateway-request-framework.md`

## Progress

- 2026-07-18: Started implementation.
- 2026-07-18: Confirmed Phase 3 should register `gateway` as hidden/callable, preserve top-level help surface, and use the Phase 2 `SessionRouter` without browser/CDP context switching.
- 2026-07-18: Added `tokenade.core.gateway.server` with `GatewayControlPlane`, `GatewayServerConfig`, and `create_gateway_control_plane()`.
- 2026-07-18: Wired hidden `tokenade gateway --request request.json` command without adding it to top-level help.
- 2026-07-18: Implemented `GET /status`, `GET /sessions`, `POST /route/next`, and `POST /route/select` contracts with sanitized responses only.
- 2026-07-18: Added focused CLI/server tests in `tokenade/tests/test_cli_gateway.py` and `tokenade/tests/test_gateway_server.py`; focused suite and lint pass.
- 2026-07-18: Verified broader CLI/request/router regression slice passes and witnessed hidden gateway over localhost using `/tmp/real-sessions`.

## Verification

```bash
python3 -m pytest tokenade/tests/test_cli_gateway.py tokenade/tests/test_gateway_server.py tokenade/tests/test_gateway_session_router.py -q
python3 -m pytest tokenade/tests/test_cli_gateway.py tokenade/tests/test_gateway_server.py tokenade/tests/test_gateway_session_router.py tokenade/tests/test_request_config.py tokenade/tests/test_plugin_run_cli.py tokenade/tests/test_cli.py -q
python3 -m flake8 tokenade/cli/__init__.py tokenade/core/gateway tokenade/tests/test_cli_gateway.py tokenade/tests/test_gateway_server.py tokenade/tests/test_gateway_session_router.py --max-line-length=120 --ignore=E501,W503,W293,E203,F541,F841,E306,E402,E226,E128,E127,E731,F821,F401,F811,E401,E704
```

Witness request file:

```json
{
  "version": "1",
  "operation": "gateway",
  "sessions": {
    "dir": "/tmp/real-sessions",
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
    "switch_interval_seconds": 5,
    "sticky_by": "site",
    "failover": true,
    "drain_existing_tabs": true
  },
  "plugins": []
}
```

Witness result:

```text
STATUS {"operation": "gateway", "routing": {"strategy": "health-weighted"}, "session_count": 7, "success": true}
SESSIONS {"contains_secret_fields": false, "count": 7, "success": true}
ROUTE_NEXT {"cookie_count": 9, "site_name": "github", "strategy": "health-weighted", "success": true}
```

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
