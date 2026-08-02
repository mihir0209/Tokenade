# Tokenade Gateway

Multi-session **control plane** for listing sanitized session metadata, selecting active sessions by strategy, and optionally preparing isolated browser contexts/tabs when runtime is enabled.

## Maturity (read this first)

| Layer | Status |
|-------|--------|
| CLI `tokenade gateway --request …` | **Present** — validates request JSON, starts HTTP server |
| Session store + routing strategies | **Unit-tested** (round-robin, select by id/site, sanitized list) |
| HTTP API (`/status`, `/sessions`, `/route/*`) | **Implemented**; keep binding on `127.0.0.1` unless you design otherwise |
| Browser runtime (CloakBrowser / CDP contexts, `/tabs/new`) | **Witnessed locally** with 5 generated `.tokenade` sessions and CloakBrowser headless |
| Auto-rotate timers, webhooks, rate limits | **Implemented in code**; not a production SLA |

This is **not** a drop-in replacement for a full fleet product. Use it when you want a local router over many `.tokenade` files; verify endpoints against your sessions before automation depends on them.

## Quick start

```bash
cat > gateway.request.json << 'EOF'
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
    "strategy": "round-robin",
    "default_scope": "activate-context"
  },
  "plugins": []
}
EOF

tokenade gateway --request gateway.request.json
```

Smoke-check:

```bash
curl -s http://127.0.0.1:9222/status | python3 -m json.tool
curl -s http://127.0.0.1:9222/sessions | python3 -m json.tool
curl -s -X POST http://127.0.0.1:9222/route/next | python3 -m json.tool
```

Invalid request files exit **2** with a JSON error envelope (`operation: gateway`).

## API endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Gateway state and session count |
| `/sessions` | GET | Sanitized session records (**no** cookie/storage secrets) |
| `/route/next` | POST | Select the active session by strategy, then apply route scope |
| `/route/select` | POST | Set active session by selector, then apply route scope |
| `/contexts` | GET | Browser context state (when runtime enabled) |
| `/contexts/lease` | POST | Keep a runtime context protected from cleanup for a TTL |
| `/contexts/release` | POST | Release a context lease by `lease_id`, `context_id`, or session selector |
| `/contexts/drain` | POST | Cleanup inactive runtime contexts; leased contexts are preserved unless `force` is true |
| `/tabs/new` | POST | Open the active session using the configured window policy |

## Gateway mental model

Gateway separates selection, preparation, opening, and cleanup:

- **Route** chooses which Session should be active.
- **Prepare Context** (`activate-context`) creates or reuses the isolated browser context for that Session, but does not open a visible page.
- **Select Only** (`future-only`) changes the active Session without touching the browser runtime.
- **Open Target** (`open-target`) routes and opens the target URL in one request.
- **Open** (`/tabs/new`) opens the active Session's target URL. The default window policy is `reuse-active-window` to avoid tab spam.
- **Lease** protects a runtime context from cleanup for a TTL.
- **Cleanup** (`/contexts/drain`) closes inactive, unleased contexts to recover resources. Pass `force: true` only when protected contexts should also close.

Route scope can be set per request with `scope`, or globally with `routing.default_scope`:

| Scope | Meaning |
|-------|---------|
| `activate-context` | Prepare Context: select the Session and prepare its browser context. This is the default. |
| `future-only` | Select Only: select the Session without browser runtime activity. |
| `open-target` | Open Target: select the Session and open the target URL immediately. |

## Routing strategies

| Strategy | Behavior |
|----------|----------|
| `round-robin` | Cycle through sessions in order |
| `random` | Random session selection |
| `health-weighted` | Prefer sessions with better health scores |
| `sticky` | Stick to same session by key (e.g. site) |

## Request shape

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
    "backend": "cdp",
    "runtime": {
      "enabled": true,
      "backend": "cloakbrowser",
      "headless": true,
      "url": "https://example.com/",
      "window_policy": "reuse-active-window"
    },
    "state_file": "~/.tokenade/gateway_state.json",
    "webhooks": {
      "on_rotate": "https://example.com/webhook/rotate",
      "on_select": "https://example.com/webhook/select",
      "on_unhealthy": "https://example.com/webhook/unhealthy",
      "secret": "hmac-secret-key"
    },
    "rate_limit": {
      "requests_per_minute": 60,
      "burst": 10
    }
  },
  "routing": {
    "object": "session",
    "strategy": "health-weighted",
    "switch_interval_seconds": 300,
    "health_check_interval_seconds": 30,
    "unhealthy_threshold": 3,
    "default_scope": "activate-context",
    "sticky_by": "site",
    "failover": true,
    "drain_existing_tabs": true
  },
  "plugins": []
}
```

## Privacy

Gateway list/status responses expose **metadata only**:

- Site name, cookie **count**, health score, auth status flags

**Never** intended in those responses:

- Cookie values, tokens, localStorage/sessionStorage, proxy credentials

Always verify with your own `curl` that secrets do not leak before exposing the port.

## Programmatic use

```python
from tokenade.core.request_config import parse_request_config
from tokenade.core.gateway import create_gateway_control_plane

request = parse_request_config({
    "version": "1",
    "operation": "gateway",
    "sessions": {"dir": "./sessions", "pattern": "*.tokenade"},
    "gateway": {"host": "127.0.0.1", "port": 0, "backend": "cdp"},
    "routing": {"object": "session", "strategy": "round-robin"},
    "plugins": [],
})
plane = create_gateway_control_plane(request)
print(plane.status())
print(plane.route_next())
# plane.serve_forever()  # blocking HTTP server
```

For a **single-session** authenticated reverse proxy from Python (scraping use case), prefer:

```python
from tokenade.sdk import TokenadeClient
with TokenadeClient().start_proxy("site.tokenade", port=9222) as proxy:
    ...
```

Gateway is for **multi-session routing**; `SessionProxy` is for **one jar → one local proxy**.

## Related tests

```bash
pytest tokenade/tests/test_cli_gateway.py \
       tokenade/tests/test_gateway_server.py \
       tokenade/tests/test_gateway_session_router.py \
       tokenade/tests/test_gateway_runtime.py -q
```

## Future / hardening

- Real-site runtime witnesses with non-fixture sessions
- Production guidance for webhooks + auth on the control port
- Clearer split between control-plane-only vs full browser mesh

## Witness Log

### 2026-07-27

- Started a temporary local account server and minted 5 independent accounts.
- Generated Playwright `storageState` JSON directly for each account (no browser launch required for export generation).
- Converted each storage state into v3 `.tokenade` sessions through `FormatImporter`.
- Ran Gateway with `runtime.enabled=true`, `backend=cloakbrowser`, and `headless=true`.
- Verified `/contexts/prewarm` created 5 isolated CloakBrowser contexts.
- Verified `/tabs/new` navigated the selected account context to the local app with no navigation error.
- Fixed Playwright storage origin preservation so `http://127.0.0.1:<port>` remains exact during localStorage injection.

See also [`USE-CASES.md`](../USE-CASES.md) §14 and the main [`README.md`](../README.md).
