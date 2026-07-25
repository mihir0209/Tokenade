# Tokenade Gateway

Multi-session **control plane** for listing sanitized session metadata and selecting an active session by strategy. Optional browser runtime hooks attach contexts/tabs when configured.

## Maturity (read this first)

| Layer | Status |
|-------|--------|
| CLI `tokenade gateway --request …` | **Present** — validates request JSON, starts HTTP server |
| Session store + routing strategies | **Unit-tested** (round-robin, select by id/site, sanitized list) |
| HTTP API (`/status`, `/sessions`, `/route/*`) | **Implemented**; keep binding on `127.0.0.1` unless you design otherwise |
| Browser runtime (CloakBrowser / CDP contexts, `/tabs/new`) | **Code present** — needs your own witness run with real jars |
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
    "strategy": "round-robin"
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
| `/route/next` | POST | Select next session by strategy |
| `/route/select` | POST | Set active session by selector |
| `/contexts` | GET | Browser context state (when runtime enabled) |
| `/contexts/prewarm` | POST | Prewarm contexts for sessions |
| `/contexts/drain` | POST | Close inactive contexts |
| `/tabs/new` | POST | Open new tab on active context (runtime) |

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
      "headless": true
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

- Stronger live runtime witnesses with CloakBrowser
- Production guidance for webhooks + auth on the control port
- Clearer split between control-plane-only vs full browser mesh

See also [`USE-CASES.md`](../USE-CASES.md) §14 and the main [`README.md`](../README.md).
