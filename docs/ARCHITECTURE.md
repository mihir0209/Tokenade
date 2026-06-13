# Tokenade Architecture

## Overview

Tokenade is a CLI-based browser session portability tool that extracts sessions from one browser, packages them into `.tokenade` files, and injects them into target browsers via a CDP reverse proxy with TLS fingerprint matching.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Tokenade CLI                             │
│  tokenade export │ tokenade proxy │ tokenade share │ ...       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Core Modules                             │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   Importer      │     Proxy       │         Crypto              │
│  - Extractor    │  - CDP Proxy    │    - Encryptor              │
│  - Packager     │  - Forward      │    - CookieCrypto           │
│  - Loader       │  - Multi-Site   │    - Credentials            │
│  - Refresher    │                 │                             │
│  - Sharer       │                 │                             │
│  - Manager      │                 │                             │
│  - Validator    │                 │                             │
└─────────────────┴─────────────────┴─────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      External Dependencies                      │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   Playwright    │    curl-cffi    │       aiohttp               │
│  (Chromium)     │  (TLS Match)    │    (HTTP Server)            │
└─────────────────┴─────────────────┴─────────────────────────────┘
```

## Core Components

### 1. Session Export (Importer)

The importer extracts browser sessions from SQLite cookie databases.

```
Browser Cookie DB (SQLite)
        │
        ▼
┌─────────────────┐
│ CookieExtractor │──── Decrypt (CookieCrypto)
└─────────────────┘
        │
        ▼
┌─────────────────┐
│ SessionPackager │──── Package into .tokenade format
└─────────────────┘
        │
        ▼
   .tokenade file
```

**Supported Browsers:**
- Chrome/Brave (Windows, Linux, macOS)
- Firefox (Linux, macOS)
- Edge (Windows, Linux)

### 2. Session Injection (Proxy)

The proxy injects sessions into a Playwright Chromium browser.

```
.tokenade file
        │
        ▼
┌─────────────────┐
│  CDPProxy       │──── Load session
└─────────────────┘
        │
        ▼
┌─────────────────┐
│  Playwright     │──── Launch Chromium
│  Browser        │──── Inject cookies
└─────────────────┘        │
        │                  ▼
        │         ┌─────────────────┐
        │         │  page.route()   │──── Intercept ALL requests
        │         └─────────────────┘        │
        │                                    ▼
        │                           ┌─────────────────┐
        │                           │   curl-cffi     │──── TLS fingerprint match
        │                           └─────────────────┘
        ▼
┌─────────────────┐
│  aiohttp        │──── Serve GUI
│  Server         │──── Reverse proxy
└─────────────────┘
```

### 3. TLS Fingerprint Matching

curl-cffi impersonates browser TLS fingerprints to bypass anti-bot systems.

```
Browser Request
        │
        ▼
┌─────────────────┐
│  page.route()   │──── Intercept
└─────────────────┘
        │
        ▼
┌─────────────────┐
│  curl-cffi      │──── Forward with donor TLS fingerprint
│  impersonate    │
└─────────────────┘
        │
        ▼
   Target Server
   (sees donor fingerprint)
```

**Supported Impersonations:**
- Chrome 99-120
- Firefox (falls back to Chrome)
- Edge

### 4. Session Auto-Refresh

Monitors cookie expiry during proxy operation.

```
┌─────────────────┐
│ SessionRefresher│──── Check every 5 minutes
└─────────────────┘
        │
        ├── Expired cookies? → Log warning
        ├── Expiring soon? → Log info
        └── Auto-refresh enabled? → Re-export from source browser
                │
                ▼
        ┌─────────────────┐
        │ CookieExtractor │──── Extract fresh cookies
        └─────────────────┘
                │
                ▼
        ┌─────────────────┐
        │ Hot-reload      │──── Update proxy without restart
        └─────────────────┘
```

### 5. Session Sharing

Generate shareable encrypted links.

```
.tokenade file
        │
        ▼
┌─────────────────┐
│  SessionSharer  │──── Create share link
└─────────────────┘
        │
        ├── URL: tokenade://share/{base64_payload}
        ├── HTML: Self-contained download page
        └── QR: Mobile-friendly QR code
```

### 6. Multi-Session Management

Manage multiple session files.

```
┌─────────────────┐
│ SessionManager  │
└─────────────────┘
        │
        ├── list: Find all .tokenade files
        ├── merge: Combine multiple sessions
        ├── rotate: Round-robin or random selection
        └── stats: Aggregate statistics
```

## Data Flow

### Export Flow

```
1. Browser Discovery → Find installed browsers
2. Cookie Extraction → Read SQLite database
3. Decryption → Decrypt cookies (platform-specific)
4. Filtering → Filter by domain/site
5. Packaging → Create .tokenade JSON
6. Optional Encryption → AES-256-GCM encryption
```

### Proxy Flow

```
1. Load Session → Parse .tokenade file
2. Launch Browser → Start Playwright Chromium
3. Inject Cookies → Add to browser context
4. Start Server → aiohttp on port 9222
5. Navigate → User enters URL
6. Intercept → page.route() catches request
7. Forward → curl-cffi with TLS fingerprint
8. Render → Browser displays page
```

## Security Architecture

### Cookie Encryption

```
Plaintext Cookie
        │
        ▼
┌─────────────────┐
│  AES-256-GCM    │──── Encrypt with key
│  (v2 format)    │
└─────────────────┘
        │
        ▼
Encrypted .tokenade file
```

### SSRF Protection

```
Incoming URL
        │
        ▼
┌─────────────────┐
│ _is_safe_url()  │──── Check against blocklist
└─────────────────┘
        │
        ├── Private IPs (10.x, 172.16.x, 192.168.x)
        ├── Loopback (127.x, ::1)
        ├── Link-local (169.254.x)
        └── Metadata endpoints
                │
                ▼
        Block if unsafe
```

### Credential Management

```
┌─────────────────┐
│ CredentialManager│
└─────────────────┘
        │
        ├── Try keyring (OS keychain)
        ├── Fallback to encrypted file
        └── Interactive prompt (getpass)
```

## File Format

### .tokenade Format (v2)

```json
{
  "version": "2.0",
  "created_at": "2025-01-01T00:00:00Z",
  "site_name": "example",
  "auth_status": "logged_in",
  "source_device": {
    "browser": "firefox",
    "profile": "default",
    "platform": "Linux",
    "hostname": "my-pc"
  },
  "cookies": [
    {
      "name": "session",
      "value": "abc123",
      "domain": ".example.com",
      "path": "/",
      "secure": true,
      "httpOnly": true,
      "sameSite": "Lax",
      "expires": 1781000000
    }
  ],
  "local_storage": {
    "key": "value"
  },
  "fingerprint": {
    "user_agent": "Mozilla/5.0 ...",
    "platform": "Linux",
    "language": "en-US"
  },
  "tls_profile": {
    "browser": "chrome",
    "version": "120",
    "impersonate": "chrome120"
  }
}
```

## Testing Architecture

```
tests/
├── unit/                    # Unit tests for individual modules
│   ├── test_session_packager.py
│   ├── test_session_refresher.py
│   ├── test_session_sharer.py
│   ├── test_session_manager.py
│   └── test_advanced_validator.py
├── integration/             # Integration tests
│   ├── test_proxy.py
│   └── test_cli.py
└── portability.py           # Cross-browser portability tests
```

**Test Coverage:** 465 tests passing

## Performance Considerations

### Connection Pooling

```python
connector = aiohttp.TCPConnector(
    ssl=False,
    limit=100,          # Total connections
    limit_per_host=30,  # Per-host connections
    enable_cleanup_closed=True
)
```

### Page Lifecycle

- TTL: 1 hour per page
- Max pages: 20
- Auto-cleanup of expired pages

### Cookie Deduplication

When merging sessions, cookies are deduplicated by (name, domain, path) with later sessions overriding earlier ones.
