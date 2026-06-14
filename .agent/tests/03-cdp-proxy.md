# Manual Test Report — CDP Proxy

**Date:** 2026-06-14
**Version:** v3.4.0

## Test 1: Proxy Startup with Session

### Command
```bash
timeout 10 python -m tokenade.cli proxy -s test_sessions/google.tokenade --port 9222 --no-open-browser
```

### Result
- **Status:** PASS
- **Output:**
  ```
  Session loaded: test_sessions/google.tokenade (167 cookies)
  Injected 158 cookies into browser
  Session auto-refresh monitor started
  CDP Proxy started on 127.0.0.1:9222
  ```
- **Notes:**
  - 167 cookies in session, 158 injected (some may be expired/invalid for injection)
  - Auto-refresh monitor started successfully
  - Proxy bound to 127.0.0.1:9222
  - Timeout after 10 seconds (expected for test)

## Test 2: Proxy Startup with GitHub Session

### Command
```bash
timeout 10 python -m tokenade.cli proxy -s test_sessions/github.tokenade --port 9223 --no-open-browser
```

### Result
- **Status:** PASS
- **Output:**
  ```
  Session loaded: test_sessions/github.tokenade (9 cookies)
  Injected 9 cookies into browser
  CDP Proxy started on 127.0.0.1:9223
  ```
- **Notes:** All 9 GitHub cookies injected successfully

## Test 3: Extension Bridge Initialization

### Command
```bash
python -c "
from tokenade.core.proxy.extension_bridge import ExtensionBridge

bridge = ExtensionBridge(port=9223)
status = bridge.get_status()
print(f'Host: {status[\"host\"]}')
print(f'Port: {status[\"port\"]}')
print(f'Running: {status[\"running\"]}')
print(f'Clients: {status[\"connected_clients\"]}')
"
```

### Result
- **Status:** PASS
- **Output:** Bridge initializes correctly with default settings
