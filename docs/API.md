# Tokenade API Reference

## Core Modules

### tokenade.core.proxy.cdp_proxy

The CDP proxy is the primary proxy implementation using Playwright Chromium.

```python
from tokenade.core.proxy.cdp_proxy import CDPProxy, CDPProxyConfig

# Create proxy from session file
config = CDPProxyConfig(port=9222, headless=True)
proxy = CDPProxy.from_session_file("session.tokenade", config)

# Start the proxy (blocking)
proxy.run()

# Or start async
import asyncio
asyncio.run(proxy.start())
```

#### CDPProxyConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| port | int | 9222 | Port to listen on |
| host | str | "127.0.0.1" | Host to bind to |
| headless | bool | True | Run browser in headless mode |
| verbose | bool | False | Enable verbose logging |
| timeout | int | 30 | Request timeout in seconds |
| use_fingerprint | bool | False | Enable TLS fingerprint matching |

#### CDPProxy Methods

- `start()` - Start the proxy server and Playwright browser
- `stop()` - Stop the proxy server and Playwright browser
- `run()` - Run the proxy server (blocking)

### tokenade.core.importer.session_refresher

Monitor session cookie expiry and trigger re-export when needed.

```python
from tokenade.core.importer.session_refresher import SessionRefresher, RefreshConfig

config = RefreshConfig(
    check_interval=300,  # Check every 5 minutes
    expiry_warning_days=7,
    expiry_critical_days=1,
    auto_refresh=False,
    source_browser="firefox",
)

refresher = SessionRefresher(session, config, on_refresh=callback)

# Check expiry status
status = refresher.check_expiry()
print(f"Expired: {status.expired_count}, Expiring soon: {status.expiring_soon_count}")

# Start monitoring (async)
await refresher.start()
await refresher.stop()
```

#### RefreshConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| check_interval | int | 300 | Check interval in seconds |
| expiry_warning_days | int | 7 | Warn if expiring within N days |
| expiry_critical_days | int | 1 | Critical if expiring within N days |
| auto_refresh | bool | False | Auto-refresh from source browser |
| source_browser | str | None | Source browser for auto-refresh |
| source_profile | str | None | Source profile for auto-refresh |
| domains | str | None | Comma-separated domains to filter |

#### CookieExpiryInfo

| Field | Type | Description |
|-------|------|-------------|
| total_cookies | int | Total number of cookies |
| expired_count | Number of expired cookies |
| expiring_soon_count | int | Cookies expiring within warning_days |
| critical_count | int | Cookies expiring within critical_days |
| next_expiry_epoch | float | Next expiry timestamp |
| next_expiry_human | str | Human-readable next expiry |

### tokenade.core.importer.session_sharer

Create shareable encrypted session links and QR codes.

```python
from tokenade.core.importer.session_sharer import SessionSharer, ShareConfig

sharer = SessionSharer(storage_dir="~/.tokenade/shared")

# Create share link
config = ShareConfig(
    expiry_hours=24,
    max_uses=0,  # Unlimited
    password_protected=False,
)
url, session_id = sharer.create_share_link(session, config)

# Load from URL
loaded = sharer.load_from_url(url)

# Create QR code
sharer.create_qr_code(session, "qr.png", config)

# List active shares
shares = sharer.list_shared()

# Revoke a share
sharer.revoke_share(session_id)
```

#### ShareConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| expiry_hours | int | 24 | Link expiry in hours |
| max_uses | int | 0 | Max uses (0 = unlimited) |
| password_protected | bool | False | Password protect the link |
| password | str | None | Password for protection |

### tokenade.core.importer.session_manager

Manage multiple session files.

```python
from tokenade.core.importer.session_manager import SessionManager

manager = SessionManager(sessions_dir="./sessions")

# List sessions
sessions = manager.list_sessions()
for s in sessions:
    print(f"{s.site_name}: {s.cookie_count} cookies")

# Filter sessions
filtered = manager.filter_sessions(sessions, site_name="google", browser="firefox")

# Merge sessions
manager.merge_sessions(
    ["session1.tokenade", "session2.tokenade"],
    "merged.tokenade",
    site_name="merged",
)

# Rotate between sessions
selected = manager.rotate_session(
    ["session1.tokenade", "session2.tokenade"],
    strategy="round-robin",
)

# Get statistics
stats = manager.get_session_stats(["session1.tokenade", "session2.tokenade"])
```

#### SessionInfo

| Field | Type | Description |
|-------|------|-------------|
| path | str | Path to session file |
| site_name | str | Site name |
| cookie_count | int | Number of cookies |
| has_local_storage | bool | Has localStorage data |
| created_at | str | Creation timestamp |
| source_browser | str | Source browser |
| file_size | int | File size in bytes |

### tokenade.core.importer.advanced_validator

Validate sessions with custom rules.

```python
from tokenade.core.importer.advanced_validator import (
    AdvancedValidator,
    ValidationRule,
    load_validation_rules,
)

validator = AdvancedValidator(proxy_port=9222)

# Load rules from file
rules = load_validation_rules("rules.json")

# Validate session
results = await validator.validate_rules(session, rules, site_url="https://example.com")

for result in results:
    status = "✓" if result.passed else "✗"
    print(f"{status} {result.rule_name}: {result.message}")
```

#### ValidationRule

| Field | Type | Description |
|-------|------|-------------|
| name | str | Rule name |
| type | str | Rule type: "js", "screenshot", "api", "cookie", "url", "element" |
| config | dict | Rule configuration |
| timeout | int | Timeout in seconds |

#### Rule Types

**JavaScript Validation**
```python
ValidationRule(
    name="logged_in",
    type="js",
    config={"script": "return document.querySelector('.user-menu') !== null"},
)
```

**Cookie Validation**
```python
ValidationRule(
    name="session_cookie",
    type="cookie",
    config={"name": "session", "exists": True, "value": "abc123"},
)
```

**API Validation**
```python
ValidationRule(
    name="api_check",
    type="api",
    config={
        "url": "https://api.example.com/me",
        "status": 200,
        "body": {"authenticated": True},
    },
)
```

**Screenshot Validation**
```python
ValidationRule(
    name="visual_check",
    type="screenshot",
    config={"baseline": "homepage", "update_baseline": False},
)
```

**URL Validation**
```python
ValidationRule(
    name="no_redirect",
    type="url",
    config={"redirect": False},
)
```

**Element Validation**
```python
ValidationRule(
    name="user_avatar",
    type="element",
    config={"selector": ".user-avatar", "exists": True},
)
```

## CLI Commands

### Export
```bash
tokenade export --browser-name firefox --domains "example.com" -o session.tokenade
```

### Proxy
```bash
tokenade proxy -s session.tokenade --port 9222 --auto-refresh --source-browser firefox
```

### Share
```bash
tokenade share -s session.tokenade --format qr --expiry 48 --password secret
```

### Sessions
```bash
tokenade sessions list -d ./sessions --site google
tokenade sessions merge *.tokenade -o merged.tokenade
tokenade sessions rotate session1.tokenade session2.tokenade
```

### Validate Rules
```bash
tokenade validate-rules -s session.tokenade -r rules.json
```

### Diff
```bash
tokenade diff session1.tokenade session2.tokenade -v
```
