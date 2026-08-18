# Tokenade API Documentation

## Overview

Tokenade exposes two HTTP servers:

| Server | Default Port | Purpose |
|---|---|---|
| **REST API** | `9224` | Session management, monitoring, export/share, sync |
| **CDP Proxy** | `9222` | Playwright-based reverse proxy with TLS fingerprint matching |

Both servers run on `127.0.0.1` by default and can be configured to bind to other interfaces.

The REST API is built with **aiohttp** and provides JSON endpoints for session operations, health monitoring, and integration with external tools. The CDP Proxy serves a web GUI, proxies browser requests through curl-cffi with the donor's TLS profile, and exposes CDP-compatible endpoints for browser automation tools.

---

## Authentication

The REST API supports optional API key authentication. When configured, requests must include the key via one of:

```
Authorization: Bearer <api_key>
```

```
X-API-Key: <api_key>
```

If no API key is configured, all endpoints are open (default behavior).

Set the API key in `APIServerConfig`:

```python
from tokenade.core.api.server import APIServerConfig

config = APIServerConfig(api_key="your-secret-key")
```

The CDP Proxy does **not** require authentication — it is intended for local use only.

---

## REST API Endpoints

Base URL: `http://127.0.0.1:9224`

### Health Check

```
GET /api/health
```

Returns server health status and version info.

**Response** `200 OK`:

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "sessions_dir": "/home/user/.tokenade/sessions"
}
```

**Example:**

```bash
curl http://127.0.0.1:9224/api/health
```

---

### Sessions

#### List Sessions

```
GET /api/sessions
```

Returns all imported sessions in the sessions directory.

**Response** `200 OK`:

```json
{
  "sessions": [
    {
      "path": "/home/user/.tokenade/sessions/discord_abc123.tokenade",
      "site_name": "discord",
      "cookie_count": 24,
      "created_at": "2026-01-15T10:30:00Z",
      "source_browser": "chrome",
      "file_size": 12480
    }
  ],
  "total": 1
}
```

**Example:**

```bash
curl http://127.0.0.1:9224/api/sessions
```

---

#### Get Session

```
GET /api/sessions/{id}
```

Returns full session details including all cookies and metadata.

**Path Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `id` | string | Session file ID (partial match supported) |

**Response** `200 OK`:

```json
{
  "id": "abc123",
  "file": "/home/user/.tokenade/sessions/discord_abc123.tokenade",
  "session": {
    "version": "2.0",
    "site_name": "discord",
    "auth_status": "logged_in",
    "cookies": [
      {
        "name": "__dcfduid",
        "value": "...",
        "domain": ".discord.com",
        "path": "/",
        "secure": true,
        "httpOnly": true,
        "sameSite": "None",
        "expires": 1735689600
      }
    ],
    "tokens": [],
    "local_storage": {},
    "fingerprint": {
      "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ..."
    },
    "tls_profile": {
      "browser": "chrome",
      "version": "120",
      "impersonate": "chrome120"
    }
  }
}
```

**Response** `404 Not Found`:

```json
{
  "error": "Session not found"
}
```

**Example:**

```bash
curl http://127.0.0.1:9224/api/sessions/abc123
```

---

#### Delete Session

```
DELETE /api/sessions/{id}
```

Deletes a session file from disk.

**Path Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `id` | string | Session file ID (partial match supported) |

**Response** `200 OK`:

```json
{
  "deleted": true
}
```

**Response** `404 Not Found`:

```json
{
  "error": "Session not found"
}
```

**Example:**

```bash
curl -X DELETE http://127.0.0.1:9224/api/sessions/abc123
```

---

### Proxy Status

```
GET /api/proxy/status
```

Returns current proxy status. This endpoint always returns the proxy as not running — it is informational only. Use `tokenade proxy` to start the actual proxy.

**Response** `200 OK`:

```json
{
  "proxy_running": false,
  "message": "Use 'tokenade proxy' to start the proxy"
}
```

---

### Monitoring

#### Monitor Status

```
GET /api/monitor/status
```

Returns aggregate monitoring status across all tracked sessions. Returns `monitoring: false` if the monitor has not been started.

**Response** `200 OK` (monitor running):

```json
{
  "monitoring": true,
  "sessions_monitored": 3,
  "average_health_score": 0.85,
  "sessions": [
    {
      "session_id": "abc123",
      "site_name": "discord",
      "health_score": 0.92,
      "cookie_count": 24,
      "healthy_cookies": 20,
      "warning_cookies": 3,
      "expired_cookies": 1
    }
  ]
}
```

**Response** `200 OK` (monitor not started):

```json
{
  "monitoring": false,
  "message": "Monitor not started"
}
```

**Example:**

```bash
curl http://127.0.0.1:9224/api/monitor/status
```

---

#### Session Health Details

```
GET /api/monitor/sessions/{id}
```

Returns detailed health information for a single monitored session.

**Response** `200 OK`:

```json
{
  "session_id": "abc123",
  "site_name": "discord",
  "health_score": 0.92,
  "cookie_count": 24,
  "healthy_cookies": 20,
  "warning_cookies": 3,
  "expired_cookies": 1,
  "last_check": 1735689600.0,
  "last_refresh": 1735686000.0,
  "refresh_count": 2,
  "issues": ["1 cookie expired"],
  "recommendations": ["Re-export session from source browser"],
  "cookies": [
    {
      "name": "__dcfduid",
      "domain": ".discord.com",
      "health": "healthy",
      "remaining_seconds": 31536000,
      "secure": true,
      "http_only": true,
      "same_site": "None"
    },
    {
      "name": "session_id",
      "domain": ".discord.com",
      "health": "warning",
      "remaining_seconds": 1800,
      "secure": true,
      "http_only": true,
      "same_site": "Lax"
    }
  ]
}
```

**Response** `404 Not Found`:

```json
{
  "error": "Session not monitored"
}
```

---

#### Cookie Expiry Timeline

```
GET /api/monitor/sessions/{id}/cookies
```

Returns cookies sorted by remaining TTL (ascending) for expiry timeline visualization.

**Response** `200 OK`:

```json
{
  "session_id": "abc123",
  "now": 1735689600.0,
  "cookies": [
    {
      "name": "session_id",
      "domain": ".discord.com",
      "expires_at": 1735691400.0,
      "remaining_seconds": 1800,
      "health": "warning"
    },
    {
      "name": "__dcfduid",
      "domain": ".discord.com",
      "expires_at": 1736985600.0,
      "remaining_seconds": 31536000,
      "health": "healthy"
    }
  ]
}
```

---

### Export Session

```
POST /api/export
```

Export cookies from a source browser into a `.tokenade` session file.

**Request Body:**

```json
{
  "browser": "chrome",
  "domains": ["discord.com", "google.com"],
  "output": "/tmp/discord.tokenade"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `browser` | string | No | Source browser name (default: `"chrome"`) |
| `domains` | string[] | No | Filter cookies by domain |
| `output` | string | No | Output file path |

**Response** `200 OK`:

```json
{
  "success": true,
  "output": "Exported 24 cookies from Chrome"
}
```

**Response** `500 Internal Server Error`:

```json
{
  "error": "No Chrome profile found"
}
```

**Example:**

```bash
curl -X POST http://127.0.0.1:9224/api/export \
  -H "Content-Type: application/json" \
  -d '{"browser": "chrome", "domains": ["discord.com"]}'
```

---

### Share Session

```
POST /api/share
```

Create an encrypted, shareable link for a session file.

**Request Body:**

```json
{
  "session_file": "/home/user/.tokenade/sessions/discord_abc123.tokenade",
  "password": "optional-password",
  "expiry_hours": 24
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `session_file` | string | Yes | Path to the `.tokenade` file |
| `password` | string | No | Encryption password |
| `expiry_hours` | number | No | Link expiry in hours (default: 24) |

**Response** `200 OK`:

```json
{
  "success": true,
  "output": "Share link: https://share.tokenade.com/abc123"
}
```

---

### Sync

#### List Sync Targets

```
GET /api/sync
```

Returns configured session sync targets and their status.

**Response** `200 OK`:

```json
{
  "targets": [
    {
      "name": "local-sync",
      "source_dir": "/home/user/.tokenade/sessions",
      "active": true,
      "last_sync": 1735689600.0
    }
  ]
}
```

---

#### Trigger Sync

```
POST /api/sync/run
```

Run a one-time synchronization of all configured sync targets.

**Response** `200 OK`:

```json
{
  "results": [
    {
      "target": "local-sync",
      "synced": 5,
      "errors": []
    }
  ]
}
```

---

## Dashboard API Endpoints

Base URL: `http://127.0.0.1:8080`

The Dashboard provides a web UI for session monitoring with authentication and HTTPS support.

### List Sessions

```
GET /api/sessions
```

Returns all sessions.

**Response** `200 OK`:

```json
[
  {
    "name": "twitter-fresh",
    "path": "/path/to/twitter.tokenade",
    "size": 29191,
    "modified": 1784671233.761121,
    "status": "healthy"
  }
]
```

### Health Status

```
GET /api/health
```

Returns health status.

**Response** `200 OK`:

```json
{
  "status": "healthy",
  "healthy": 5,
  "total": 5,
  "timestamp": 1784671651.0
}
```

### Statistics

```
GET /api/stats
```

Returns session statistics.

**Response** `200 OK`:

```json
{
  "total": 5,
  "healthy": 4,
  "expired": 1,
  "unknown": 0
}
```

### Authentication

```
POST /api/auth/login
```

Authenticate user.

**Request**:
```json
{
  "username": "admin",
  "password": "secret"
}
```

**Response** `200 OK`:
```json
{
  "success": true,
  "token": "session-token"
}
```

```
POST /api/auth/logout
```

Logout user.

---

## Vault API Endpoints

Base URL: `http://127.0.0.1:9224`

The Vault provides encrypted storage for sessions with key rotation.

### Store Session

```
POST /api/vault/store
```

Store a session in the vault.

**Request**:
```json
{
  "session_file": "/path/to/session.tokenade",
  "name": "twitter-fresh"
}
```

**Response** `200 OK`:
```json
{
  "success": true,
  "name": "twitter-fresh"
}
```

### Retrieve Session

```
POST /api/vault/retrieve
```

Retrieve a session from the vault.

**Request**:
```json
{
  "name": "twitter-fresh",
  "output_path": "/path/to/output.tokenade"
}
```

**Response** `200 OK`:
```json
{
  "success": true,
  "output_path": "/path/to/output.tokenade"
}
```

### List Stored Sessions

```
GET /api/vault/list
```

Returns list of stored sessions.

**Response** `200 OK`:
```json
{
  "sessions": [
    {"name": "twitter-fresh", "stored_at": "2026-07-22T10:30:00Z"},
    {"name": "github-session", "stored_at": "2026-07-21T15:45:00Z"}
  ]
}
```

### Delete Session

```
POST /api/vault/delete
```

Delete a session from the vault.

**Request**:
```json
{
  "name": "twitter-fresh"
}
```

### Rotate Key

```
POST /api/vault/rotate-key
```

Rotate the encryption key.

**Response** `200 OK`:
```json
{
  "success": true,
  "rotated_at": "2026-07-22T10:30:00Z"
}
```

---

## Sync-Remote API Endpoints

Base URL: `http://127.0.0.1:9224`

The Sync-Remote feature syncs sessions to/from a remote machine via SSH/SCP.

### Sync Status

```
GET /api/sync/status
```

Returns sync status.

**Response** `200 OK`:
```json
{
  "remote_host": "user@remote",
  "remote_path": "~/.tokenade/sessions",
  "local_path": "~/.tokenade/sessions",
  "last_sync": "2026-07-22T10:30:00Z",
  "status": "synced"
}
```

### Trigger Push

```
POST /api/sync/push
```

Push sessions to remote.

**Request**:
```json
{
  "remote_host": "user@remote",
  "remote_path": "~/.tokenade/sessions",
  "conflict": "remote-wins"
}
```

**Response** `200 OK`:
```json
{
  "success": true,
  "pushed": 5,
  "skipped": 0,
  "conflicts": 0
}
```

### Trigger Pull

```
POST /api/sync/pull
```

Pull sessions from remote.

### Bidirectional Sync

```
POST /api/sync/bidirectional
```

Perform bidirectional sync.

---

## Share-URL API Endpoints

Base URL: `http://127.0.0.1:9224`

The Share-URL feature creates password-protected share links for sessions.

### Create Share

```
POST /api/share-url/create
```

Create a password-protected share link.

**Request**:
```json
{
  "session_file": "/path/to/session.tokenade",
  "password": "MySecurePassword123!",
  "expiry_hours": 24,
  "max_uses": 5
}
```

**Response** `200 OK`:
```json
{
  "success": true,
  "share_id": "abc123",
  "short_url": "tokenade://share/abc123",
  "expires_at": "2026-07-23T10:30:00Z"
}
```

### Retrieve Session

```
POST /api/share-url/retrieve
```

Retrieve a shared session.

**Request**:
```json
{
  "share_id": "abc123",
  "password": "MySecurePassword123!",
  "output_path": "/path/to/output.tokenade"
}
```

**Response** `200 OK`:
```json
{
  "success": true,
  "output_path": "/path/to/output.tokenade"
}
```

### List Shares

```
GET /api/share-url/list
```

Returns list of active shares.

**Response** `200 OK`:
```json
{
  "shares": [
    {
      "share_id": "abc123",
      "short_url": "tokenade://share/abc123",
      "created_at": "2026-07-22T10:30:00Z",
      "expires_at": "2026-07-23T10:30:00Z",
      "uses": 2,
      "max_uses": 5,
      "is_valid": true
    }
  ]
}
```

### Revoke Share

```
POST /api/share-url/revoke
```

Revoke a share.

**Request**:
```json
{
  "share_id": "abc123"
}
```

### Cleanup Expired

```
POST /api/share-url/cleanup
```

Cleanup expired shares.

**Response** `200 OK`:
```json
{
  "success": true,
  "cleaned": 3
}
```

---

## Enterprise API Endpoints

Base URL: `http://127.0.0.1:9224`

Enterprise features include RBAC and encrypted audit logging.

### Audit Log Query

```
GET /api/audit/query
```

Query audit logs.

**Query Parameters**:
- `user_id`: Filter by user ID
- `action`: Filter by action
- `resource`: Filter by resource type
- `start_time`: Start timestamp
- `end_time`: End timestamp

**Response** `200 OK`:
```json
{
  "entries": [
    {
      "timestamp": "2026-07-22T10:30:00Z",
      "user_id": "alice",
      "action": "export",
      "resource": "session",
      "resource_id": "twitter-fresh",
      "details": {"browser": "firefox", "cookies": 113},
      "success": true
    }
  ],
  "total": 1
}
```

### RBAC Role Management

```
GET /api/rbac/roles
```

List roles.

```
POST /api/rbac/roles
```

Create a role.

**Request**:
```json
{
  "name": "admin",
  "permissions": ["read", "write", "delete", "manage_users"]
}
```

```
POST /api/rbac/roles/assign
```

Assign a role to a user.

**Request**:
```json
{
  "user_id": "alice",
  "role": "admin"
}
```

---

## CDP Proxy Endpoints

Base URL: `http://127.0.0.1:9222`

The CDP Proxy uses a Playwright-based Chromium browser to render pages. All requests are intercepted via `page.route()` and forwarded through curl-cffi with the donor's TLS fingerprint and cookies.

### CDP Version Info

```
GET /json/version
```

Returns Chrome DevTools Protocol version information, proxied from the underlying Chromium instance.

**Response** `200 OK`:

```json
{
  "Browser": "Chromium/120.0.0.0",
  "Protocol-Version": "1.3",
  "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) ...",
  "V8-Version": "12.0.267.8",
  "WebKit-Version": "537.36",
  "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/browser/..."
}
```

**Example:**

```bash
curl http://127.0.0.1:9222/json/version
```

---

### List Browser Targets

```
GET /json/list
```

Returns all open browser targets (tabs, iframes, service workers).

**Response** `200 OK`:

```json
[
  {
    "id": "PAGE_ID",
    "type": "page",
    "title": "Discord",
    "url": "https://discord.com/channels/@me",
    "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/page/..."
  }
]
```

---

### Stealth Script

```
GET /stealth.js
```

Returns a comprehensive JavaScript stealth script that patches browser APIs to avoid bot detection. Served as `application/javascript`.

The script includes:

- WebDriver detection bypass
- `navigator.plugins` and `navigator.languages` spoofing
- WebGL vendor/renderer override
- Canvas fingerprint noise
- AudioContext fingerprint noise
- Chrome runtime spoofing
- Permissions API patching
- Network information spoofing
- Screen resolution consistency checks

**Example:**

```bash
curl http://127.0.0.1:9222/stealth.js
```

---

### Proxy Status

```
GET /status
```

Returns CDP proxy runtime status.

**Response** `200 OK`:

```json
{
  "status": "running",
  "site": "discord",
  "cookies": 24,
  "tls_profile": {
    "browser": "chrome",
    "version": "120",
    "impersonate": "chrome120"
  },
  "uptime": 3600.5
}
```

**Example:**

```bash
curl http://127.0.0.1:9222/status
```

---

### Proxy Statistics

```
GET /stats
```

Returns request statistics for the current proxy session.

**Response** `200 OK`:

```json
{
  "requests": 142,
  "bytes_sent": 524288,
  "bytes_received": 1048576,
  "errors": 3,
  "start_time": 1735686000.0
}
```

---

### Session Status

```
GET /session/status
```

Returns the session refresh monitor status, including cookie expiry information.

**Response** `200 OK`:

```json
{
  "total_cookies": 24,
  "healthy": 20,
  "expiring_soon": 3,
  "expired": 1,
  "next_expiry_human": "2 hours 30 minutes",
  "refresh_enabled": true,
  "last_refresh": 1735686000.0
}
```

**Response** `503 Service Unavailable`:

```json
{
  "error": "Refresh monitor not active"
}
```

---

### Force Session Refresh

```
POST /session/refresh
```

Trigger an immediate session refresh from the source browser. Re-extracts cookies and hot-reloads them into the running proxy without downtime.

**Response** `200 OK`:

```json
{
  "status": "refreshed",
  "cookies": 24
}
```

**Response** `503 Service Unavailable`:

```json
{
  "error": "Refresh monitor not active"
}
```

**Response** `500 Internal Server Error`:

```json
{
  "error": "Refresh failed"
}
```

**Example:**

```bash
curl -X POST http://127.0.0.1:9222/session/refresh
```

---

## Session Format (`.tokenade`)

Sessions are stored as JSON files in `~/.tokenade/sessions/`. The package structure:

```json
{
  "version": "2.0",
  "created_at": "2026-01-15T10:30:00Z",
  "source_device": {
    "browser": "chrome",
    "profile": "Default",
    "platform": "Linux",
    "hostname": "anonymous"
  },
  "site_name": "discord",
  "auth_status": "logged_in",
  "cookies": [
    {
      "name": "__dcfduid",
      "value": "...",
      "domain": ".discord.com",
      "path": "/",
      "secure": true,
      "httpOnly": true,
      "sameSite": "None",
      "expires": 1735689600,
      "storeId": "0"
    }
  ],
  "tokens": [],
  "storage": {
    "local": {
      "https://example.com": { "theme": "dark" }
    },
    "session": {
      "https://example.com": { "tab_id": "active" }
    },
    "indexeddb": {
      "https://example.com": {
        "app_db": {
          "version": 1,
          "stores": {
            "auth": { "token": "jwt_sample" }
          }
        }
      }
    }
  },
  "local_storage": {
    "key": "value"
  },
  "fingerprint": {
    "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "viewport": { "width": 1920, "height": 1080 },
    "platform": "Linux"
  },
  "tls_profile": {
    "browser": "chrome",
    "version": "120",
    "impersonate": "chrome120",
    "http_version": "2"
  },
  "metadata": {
    "extraction_method": "sqlite_direct",
    "cookie_count": 24,
    "critical_cookie_count": 5,
    "local_storage_count": 12
  }
}
```

### Field Reference

| Field | Type | Description |
|---|---|---|
| `version` | string | Package format version |
| `created_at` | string | ISO 8601 creation timestamp |
| `source_device.browser` | string | Source browser name |
| `source_device.profile` | string | Source browser profile |
| `source_device.platform` | string | OS platform |
| `source_device.hostname` | string | Source hostname (anonymized) |
| `site_name` | string | Detected site name or `"unknown"` |
| `auth_status` | string | `logged_in`, `logged_out`, `session_expired`, `unknown` |
| `cookies` | array | Browser cookie objects |
| `tokens` | array | OAuth/session tokens |
| `storage` | object | Per-origin storage map (`local`, `session`, `indexeddb`) |
| `local_storage` | object | Key-value localStorage data |
| `fingerprint` | object | Browser fingerprint (viewport, user agent, etc.) |
| `tls_profile` | object | TLS impersonation target for curl-cffi |
| `metadata` | object | Extraction metadata and counts |

---

## Error Responses

All error responses follow a consistent format:

```json
{
  "error": "Human-readable error message"
}
```

### Common Status Codes

| Status | Meaning |
|---|---|
| `200` | Success |
| `400` | Bad request / invalid input |
| `401` | Unauthorized (invalid or missing API key) |
| `404` | Resource not found |
| `500` | Internal server error |
| `502` | Upstream error (CDP proxy cannot reach Chromium) |
| `503` | Service unavailable (e.g., monitor not started) |

---

## CORS

The REST API includes CORS headers on all responses:

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Headers: Authorization, Content-Type, X-API-Key
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
```

Preflight `OPTIONS` requests return `204 No Content`.
