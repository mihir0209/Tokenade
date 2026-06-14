# Manual Test Report — CLI, API, SDK

**Date:** 2026-06-14
**Version:** v3.4.0

## Test 1: CLI Version

### Command
```bash
python -m tokenade.cli --version
```

### Result
- **Status:** PASS
- **Output:** `3.4.0`

## Test 2: CLI Export Command

### Command
```bash
python -m tokenade.cli export --browser-name firefox --domains "github.com" -o test_sessions/github.tokenade
```

### Result
- **Status:** PASS
- **Output:** 9 GitHub cookies exported with auth detection

## Test 3: CLI Health Command

### Command
```bash
python -m tokenade.cli health -s test_sessions/google.tokenade
```

### Result
- **Status:** PASS
- **Output:** Health check with score, issues, recommendations

## Test 4: CLI List Profiles

### Command
```bash
python -m tokenade.cli export --list-profiles
```

### Result
- **Status:** PASS
- **Output:** Lists Firefox (1) and Brave (1) profiles

## Test 5: REST API Endpoints

### Command
```bash
python -c "
from tokenade.core.api.server import TokenadeAPIServer

server = TokenadeAPIServer()
endpoints = server.get_endpoints()
for ep in endpoints:
    print(f'{ep[\"method\"]:6} {ep[\"path\"]:35} {ep[\"description\"]}')
"
```

### Result
- **Status:** PASS
- **Output:**
  ```
  GET    /api/health                         Health check
  GET    /api/sessions                       List sessions
  GET    /api/sessions/{id}                  Get session
  DELETE /api/sessions/{id}                  Delete session
  GET    /api/proxy/status                   Proxy status
  POST   /api/export                         Export session
  POST   /api/share                          Create share link
  ```

## Test 6: API Authentication

### Command
```bash
python -c "
from tokenade.core.api.server import TokenadeAPIServer, APIServerConfig
from unittest.mock import MagicMock

config = APIServerConfig(api_key='secret-key')
server = TokenadeAPIServer(config)

# Valid key
req = MagicMock()
req.headers = {'Authorization': 'Bearer secret-key'}
print(f'Valid key: {server._check_auth(req)}')

# Invalid key
req.headers = {'Authorization': 'Bearer wrong'}
print(f'Invalid key: {server._check_auth(req)}')

# No key
req.headers = {}
print(f'No key: {server._check_auth(req)}')
"
```

### Result
- **Status:** PASS
- **Output:** `True, False, False` — correct authentication behavior

## Test 7: SDK Client Operations

### Command
```bash
python -c "
from tokenade.sdk import TokenadeClient

client = TokenadeClient(sessions_dir='test_sessions')
sessions = client.list_sessions()
print(f'Sessions: {len(sessions)}')
for s in sessions:
    print(f'  {s[\"site_name\"]}: {s[\"cookie_count\"]} cookies')

health = client.health_check('test_sessions/google.tokenade')
print(f'Health: {health[\"healthy\"]} (OWASP: {health[\"owasp_score\"]:.1f}/100)')

result = client.export_playwright('test_sessions/google.tokenade', 'test_sessions/sdk_output.json')
print(f'Playwright export: {result}')
"
```

### Result
- **Status:** PASS
- **Output:** All SDK operations work correctly

## Test 8: Webhook Payload Building

### Command
```bash
python -c "
from tokenade.core.integration.webhooks import WebhookIntegration, WebhookConfig

config = WebhookConfig(url='https://hooks.slack.com/test', type='slack')
integration = WebhookIntegration(config)

payload = integration._build_payload('export', {'site_name': 'google', 'cookie_count': 166})
print(f'Event: {payload[\"event_type\"]}')
print(f'Message: {payload[\"message\"]}')
print(f'Site: {payload[\"site_name\"]}')
"
```

### Result
- **Status:** PASS
- **Output:** Correctly formatted notification payload

## Test 9: Session Diff

### Command
```bash
python -c "
from tokenade.core.importer.session_comparator import SessionComparator
import json

with open('test_sessions/google.tokenade') as f:
    google = json.load(f)
with open('test_sessions/brave.tokenade') as f:
    brave = json.load(f)

comparator = SessionComparator()
diff = comparator.compare(google, brave)
print(f'Google: {google[\"metadata\"][\"cookie_count\"]} cookies')
print(f'Brave: {brave[\"metadata\"][\"cookie_count\"]} cookies')
print(f'Common: {len(diff.cookies_common)}')
print(f'Only-Google: {len(diff.cookies_only_in_a)}')
print(f'Only-Brave: {len(diff.cookies_only_in_b)}')
print(f'Modified: {len(diff.cookies_modified)}')
"
```

### Result
- **Status:** PASS
- **Output:** Correct diff between Google and Brave sessions
