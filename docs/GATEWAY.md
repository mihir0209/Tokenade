# Tokenade Gateway

Multi-session control plane for session routing and isolation.

## Quick Start

```bash
# 1. Create a request.json
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
    "backend": "cloakbrowser"
  },
  "routing": {
    "object": "session",
    "strategy": "round-robin"
  },
  "plugins": []
}
EOF

# 2. Start the gateway
tokenade gateway --request gateway.request.json
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Gateway state and session count |
| `/sessions` | GET | Sanitized session records (no cookies) |
| `/route/next` | POST | Select next session by strategy |
| `/route/select` | POST | Set active session by selector |
| `/contexts` | GET | Browser context state |
| `/contexts/prewarm` | POST | Prewarm contexts for sessions |
| `/contexts/drain` | POST | Close inactive contexts |
| `/tabs/new` | POST | Open new tab on active context |

## Routing Strategies

| Strategy | Behavior |
|----------|----------|
| `round-robin` | Cycle through sessions in order |
| `random` | Random session selection |
| `health-weighted` | Prefer sessions with better health scores |
| `sticky` | Stick to same session by key (e.g., site) |

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
    "backend": "cloakbrowser",
    "runtime": {
      "enabled": true,
      "backend": "cloakbrowser",
      "headless": true
    }
  },
  "routing": {
    "object": "session",
    "strategy": "health-weighted",
    "switch_interval_seconds": 300,
    "sticky_by": "site",
    "failover": true,
    "drain_existing_tabs": true
  },
  "plugins": []
}
```

## Privacy

Gateway outputs session metadata only:
- Site name
- Cookie count
- Health score
- Authentication status

**Never outputs:**
- Cookie values
- Tokens
- localStorage/sessionStorage
- Proxy credentials

## Use Cases

### Load Balancing

Route requests across multiple sessions:

```bash
curl -X POST http://127.0.0.1:9222/route/next
```

### Session Isolation

Each session gets its own browser context. Rotation changes the active context for future work. Existing tabs drain.

### API Automation

Use gateway as a session-aware reverse proxy backend:

```python
import requests

# Get next session
resp = requests.post("http://127.0.0.1:9222/route/next")
session = resp.json()["decision"]["session"]

# Open a new tab with that session
resp = requests.post("http://127.0.0.1:9222/tabs/new", json={
    "url": "https://example.com"
})
tab = resp.json()
```

## Future Features (Planned)

- Auto-rotation on timer
- Health monitoring with auto-failover
- Session persistence across restarts
- Webhook notifications
- Rate limiting

See `.agent/plans/gateway-maturity.md` for details.
