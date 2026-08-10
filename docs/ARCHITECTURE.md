# Tokenade Architecture

## System Overview

Tokenade is a session proxy system that extracts browser cookies, packages them into portable `.tokenade` files, and replays them through a local proxy with TLS fingerprint matching. The browser renders pages natively while all requests go through `curl-cffi` with the donor's TLS profile.

```
┌──────────────────────────────────────────────────────────────────┐
│                        Tokenade System                           │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐   ┌──────────────┐   ┌───────────────────────┐ │
│  │   Extractor  │   │   Importer   │   │    Runtime Engine     │ │
│  │  (cookies    │──▶│  (packager,  │──▶│  (CookieJar,          │ │
│  │   from       │   │   validator,  │   │   FingerprintMatcher, │ │
│  │   browser)   │   │   site_conf)  │   │   TLSMatcher)         │ │
│  └─────────────┘   └──────────────┘   └───────────┬───────────┘ │
│                                                     │             │
│                          ┌──────────────────────────┘             │
│                          ▼                                        │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                     Proxy Layer                              │ │
│  │                                                              │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐ │ │
│  │  │  CDP Proxy   │  │Legacy Proxy  │  │  Forward Proxy    │ │ │
│  │  │ (Playwright   │  │ (aiohttp     │  │  (raw asyncio     │ │ │
│  │  │  + curl-cffi) │  │  + curl-cffi)│  │   CONNECT tunnel) │ │ │
│  │  └──────┬───────┘  └──────────────┘  └───────────────────┘ │ │
│  │         │                                                    │ │
│  │  ┌──────┴────────────────────────────────────────────────┐  │ │
│  │  │  Extension Bridge (WebSocket) │ Multi-Site Proxy      │  │ │
│  │  └───────────────────────────────────────────────────────┘  │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                          │                                        │
│  ┌───────────────────────┴─────────────────────────────────────┐ │
│  │  Supporting Modules                                         │ │
│  │  • Fingerprint (collectors, templates)                      │ │
│  │  • Crypto (AES-256-GCM, AES-128-CBC cookie decryption)     │ │
│  │  • Plugin System (registry, loader)                         │ │
│  │  • Session Sync (daemon, mtime-based detection)             │ │
│  │  • Monitoring (health scores, expiry tracking)              │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## Module Structure

```
tokenade/
├── core/
│   ├── proxy/                          # Proxy implementations
│   │   ├── cdp_proxy.py                # CDP proxy orchestrator (Playwright + curl-cffi)
│   │   ├── cdp_stealth.py              # Stealth scripts, URL safety, blocked networks
│   │   ├── cdp_injection.py            # CDP/WebSocket cookie + stealth injection
│   │   ├── cdp_gui.py                  # GUI HTML templates for CDP proxy
│   │   ├── cdp_routing.py              # Request routing via curl-cffi/aiohttp
│   │   ├── cdp_api.py                  # CDP passthrough + status/stats endpoints
│   │   ├── server.py                   # Legacy aiohttp-based proxy orchestrator
│   │   ├── server_utils.py             # URL rewriting, response filtering
│   │   ├── server_gui.py               # GUI HTML templates for legacy proxy
│   │   ├── server_routing.py           # Request forwarding for legacy proxy
│   │   ├── forward_proxy.py            # HTTP/HTTPS CONNECT tunnel forward proxy
│   │   ├── multi_site_proxy.py         # Multi-site proxy with SharedConnectionPool
│   │   └── extension_bridge.py         # WebSocket bridge for browser extension
│   │
│   ├── importer/                       # Session extraction and packaging
│   │   ├── cookie_extractor.py         # Browser cookie extraction
│   │   ├── session_packager.py         # .tokenade file format packaging
│   │   ├── session_loader.py           # Session file loading
│   │   ├── session_sync.py             # Daemon: mtime-based browser sync
│   │   ├── session_comparator.py       # Session diff/comparison
│   │   ├── session_sharer.py           # Session sharing utilities
│   │   ├── session_vault.py            # Encrypted session storage
│   │   ├── session_manager.py          # Session lifecycle management
│   │   ├── site_configs.py             # Plugin-backed site config resolution
│   │   ├── format_importer.py          # Import from other formats
│   │   ├── format_exporter.py          # Export to other formats
│   │   ├── validator.py                # Session validation
│   │   ├── advanced_validator.py       # Extended validation rules
│   │   ├── browser_discovery.py        # Auto-detect installed browsers
│   │   ├── chromium_forks.py           # Chromium fork support
│   │   ├── mobile_extractor.py         # Mobile browser extraction
│   │   ├── safari_extractor.py         # Safari extraction
│   │   ├── tor_extractor.py            # Tor Browser extraction
│   │   ├── adb_extractor.py            # Android ADB extraction
│   │   ├── local_storage_extractor.py  # localStorage extraction
│   │   └── db_utils.py                 # SQLite database utilities
│   │
│   ├── refresh/                        # Session rotation and health-weighted refresh
│   │   ├── rotator.py                  # SessionRotationMonitor (login event tracking)
│   │   ├── session_rotator.py          # Health-weighted SessionRotator class
│   │   └── session_refresher.py        # Auto-refresh from source browser
│   │
│   ├── fingerprint/                    # Browser fingerprint collection
│   │   ├── manager.py                  # FingerprintCollector orchestrator
│   │   ├── injector.py                 # Fingerprint injection into pages
│   │   ├── stealth.py                  # Anti-detection stealth techniques
│   │   ├── templates/                  # Fingerprint templates
│   │   └── collectors/                 # Individual fingerprint collectors
│   │       ├── base.py                 # Base collector class
│   │       ├── navigator.py            # Navigator API fingerprint
│   │       ├── webgl.py                # WebGL fingerprint
│   │       ├── canvas.py               # Canvas fingerprint
│   │       ├── audio.py                # AudioContext fingerprint
│   │       ├── screen.py               # Screen/display fingerprint
│   │       ├── fonts.py                # Installed fonts fingerprint
│   │       ├── plugins.py              # Browser plugins fingerprint
│   │       ├── battery.py              # Battery API fingerprint
│   │       └── webrtc.py               # WebRTC fingerprint
│   │
│   ├── crypto/                         # Cryptography modules
│   │   ├── encryptor.py                # AES-256-GCM file encryption (PBKDF2 600k)
│   │   ├── cookie_crypto.py            # Platform-specific cookie decryption
│   │   └── at_rest.py                  # At-rest encryption utilities
│   │
│   ├── browser/                        # Browser management
│   │   ├── cloak.py                    # CloakBrowser integration
│   │   ├── stealth.py                  # JS stealth patches (fallback)
│   │   ├── stealth/                    # Stealth subsystem
│   │   │   ├── backend.py              # Stealth backend abstraction
│   │   │   ├── cloak.py                # CloakBrowser stealth layer
│   │   │   ├── launcher.py             # Stealth browser launcher
│   │   │   └── manager.py              # Stealth manager
│   │   ├── session_state.py            # .tokenade ↔ storage_state conversion
│   │   ├── battle.py                   # Battle test suite
│   │   ├── undetectable.py             # System browser launcher
│   │   ├── cdp_connection.py           # CDP WebSocket connection
│   │   ├── fingerprint.py              # Browser fingerprint detection
│   │   ├── tls_fingerprint.py          # TLS fingerprint extraction
│   │   ├── patcher.py                  # Chrome binary patcher
│   │   ├── profiles.py                 # Browser profile discovery
│   │   ├── profile_cloner.py           # Profile cloning
│   │   ├── storage_extractor.py        # Storage extraction
│   │   ├── synchronizer.py             # Browser sync
│   │   ├── manager.py                  # Browser manager
│   │   ├── dashboard.py                # Dashboard
│   │   ├── captcha.py                  # Captcha handling
│   │   ├── cloudflare.py               # Cloudflare bypass
│   │   ├── dependencies.py             # Dependency checking
│   │   └── xvfb.py                     # Virtual display (Linux)
│   │
│   ├── runtime/                        # Runtime engine
│   │   ├── engine.py                   # CookieJar, FingerprintMatcher, RuntimeEngine
│   │   └── tls_matcher.py             # curl-cffi TLS impersonation
│   │
│   ├── integration/                    # External integrations
│   │   ├── plugin_registry.py          # GitHub-hosted plugin registry
│   │   ├── plugin_loader.py            # Plugin discovery and loading
│   │   ├── plugin_browser.py           # Plugin browser
│   │   ├── plugin_search.py            # Plugin search
│   │   ├── plugin_testing.py           # Plugin testing
│   │   ├── plugin_verifier.py          # Plugin verification
│   │   ├── rating_sync.py              # Rating sync
│   │   ├── fleet.py                    # Fleet management
│   │   ├── docker_manager.py           # Docker management
│   │   ├── kubernetes.py               # Kubernetes orchestration
│   │   └── container_orchestrator.py   # Container orchestration
│   │
│   ├── cicd/                           # CI/CD integration
│   │   ├── runner.py                   # CI runner
│   │   └── workflow_generator.py       # Workflow generation
│   │
│   ├── daemon/                         # Background daemon
│   │   └── session_daemon.py           # Session daemon
│   │
│   ├── forensics/                      # Session forensics
│   │   └── autopsy.py                  # Session autopsy
│   │
│   ├── monitoring/                     # Session health monitoring
│   │   └── session_monitor.py          # Real-time cookie health tracking
│   │
│   ├── security/                       # Security modules
│   │   ├── audit.py                    # Audit logging
│   │   └── credentials.py             # Credential management
│   │
│   ├── logging/                        # Structured logging
│   ├── storage/                        # Storage utilities
│   ├── injector/                       # Data injection
│   ├── batch/                          # Batch operations
│   ├── api/                            # API server
│   ├── utils/                          # Shared utilities
│   ├── config.py                       # Global configuration
│   └── errors.py                       # Error definitions
│
├── handlers/                           # Site-specific handlers
│   └── resolve.py                      # Handler resolution
│
└── tests/                              # Test suite
```

---

## Core Components

### CDP Proxy (Primary)

The CDP proxy is the main proxy implementation. It uses a real Chromium browser (via Playwright) to render pages, intercepting all requests through `page.route()` and forwarding them via `curl-cffi` with the donor's TLS fingerprint.

**Orchestrator pattern**: `cdp_proxy.py:107-477` acts as the central coordinator, delegating to specialized modules:

```
CDPProxy (orchestrator)
    ├── cdp_stealth.py     → Stealth script injection, URL safety checks
    ├── cdp_injection.py   → Cookie/stealth injection via CDP + Playwright
    ├── cdp_gui.py         → HTML templates for web GUI
    ├── cdp_routing.py     → Request forwarding (curl-cffi → aiohttp fallback)
    └── cdp_api.py         → CDP passthrough, status/stats endpoints
```

**Startup sequence** (`cdp_proxy.py:176-303`):

1. Launch Playwright Chromium with anti-detection args
2. Create browser context with donor viewport/UA
3. Create CDP session and inject stealth via `Page.addScriptToEvaluateOnNewDocument`
4. Inject stealth into all existing pages + add init script for new pages
5. Inject donor cookies via CDP `Network.setCookie` + Playwright `context.add_cookies`
6. Start raw CDP WebSocket monitor for new targets
7. Create aiohttp web app with route table
8. Wrap server with `_LenientServerFactory` (tolerates duplicate headers from stale service workers)
9. Start `SessionRefresher` for automatic cookie expiry monitoring

**Request interception flow** (`cdp_routing.py:29-134`):

```
Browser makes request
        │
        ▼
page.route("**/*") intercepts
        │
        ▼
handle_route() called
        │
        ├── Forward via curl-cffi (TLS matched)
        │   ├── FingerprintMatcher.get_headers() → browser-specific headers
        │   ├── CookieJar.get_for_request() → matching cookies
        │   └── curl_requests.request(impersonate="chrome120")
        │
        ├── On success: collect Set-Cookie headers → add to CookieJar
        │
        └── Fallback to aiohttp if curl-cffi fails
                │
                ▼
        Fulfill route with response body + headers
```

**Key design insight** (`cdp_proxy.py:1-14`): The browser makes the requests, not the proxy. The proxy just ensures each request goes through `curl-cffi` with the donor's TLS fingerprint and cookies. This means:
- No URL rewriting needed
- No service worker required
- Browser renders everything natively
- CSP/security policies work normally

### Legacy Proxy (Deprecated)

The legacy proxy (`server.py:43-384`) uses aiohttp for all HTTP handling. It works by:

1. Using a service worker to intercept browser requests
2. Rewriting URLs to route through `/proxy/` prefix
3. Forwarding requests via `forward_request()` with curl-cffi/aiohttp
4. Rewriting response HTML/JS/CSS to maintain proxy routing

**Orchestrator pattern**:
```
TokenadeProxy (orchestrator)
    ├── server_utils.py     → URL rewriting, header filtering, content rewriting
    ├── server_gui.py       → HTML templates
    └── server_routing.py   → forward_request() with redirect following
```

**Content rewriting** (`server_utils.py:115-253`): The legacy proxy must rewrite:
- HTML: `<base href="/proxy/">`, service worker injection, URL rewriting in `href`/`src`
- JavaScript: `import`/`fetch` URL rewriting to `/proxy/` paths
- CSS: `url()` rewriting to `/proxy/` paths

This is the key limitation compared to the CDP proxy — content rewriting is fragile and breaks on complex sites.

### Forward Proxy

`forward_proxy.py:248-318` implements a raw asyncio-based HTTP/HTTPS forward proxy for use as `HTTP_PROXY`.

**Architecture**:
```
ForwardProxy
    └── _ForwardProxyProtocol (asyncio.Protocol)
            │
            ├── HTTP requests → aiohttp with donor cookies
            │
            └── HTTPS CONNECT → bidirectional stream piping
                    │
                    ├── client_reader → target_writer (upload)
                    └── target_reader → client_transport (download)
```

**CONNECT tunneling** (`forward_proxy.py:64-156`): Uses `asyncio.open_connection()` for raw TCP, then pipes data bidirectionally using `asyncio.StreamReader`. The protocol upgrade from raw transport to stream reader enables transparent tunneling.

### Multi-Site Proxy

`multi_site_proxy.py:92-257` runs multiple CDPProxy instances from one command with a shared connection pool.

```
MultiSiteProxy
    ├── SharedConnectionPool (max 200 connections, 50 per host)
    ├── CDPProxy[0] → port 9223 (site A)
    ├── CDPProxy[1] → port 9224 (site B)
    ├── ...
    └── Master GUI → base_port (tabbed iframe interface)
```

The `SharedConnectionPool` (`multi_site_proxy.py:29-89`) creates a single `aiohttp.ClientSession` shared across all proxy instances, reducing file descriptor usage and enabling TCP connection reuse.

### Extension Bridge

`extension_bridge.py:25-132` provides WebSocket communication between a browser extension and the proxy.

```
Browser Extension ←──WebSocket──→ ExtensionBridge ←──Callback──→ CDPProxy
                              │
                              ├── cookie_update → CookieJar.add_cookies()
                              ├── heartbeat
                              ├── session_request
                              └── session_response
```

---

## Data Flow

### CDP Proxy Request Lifecycle

```
┌─────────┐     ┌──────────┐     ┌───────────┐     ┌──────────┐
│ Browser  │────▶│ Playwright│────▶│  curl-cffi │────▶│  Target  │
│  (user)  │     │  route() │     │ (TLS match)│     │  Server  │
└─────────┘     └──────────┘     └───────────┘     └──────────┘
     │                │                │                  │
     │  1. Navigate   │                │                  │
     │───────────────▶│                │                  │
     │                │ 2. Intercept   │                  │
     │                │  ALL requests  │                  │
     │                │                │                  │
     │                │ 3. Build       │                  │
     │                │    headers     │                  │
     │                │    + cookies   │                  │
     │                │                │                  │
     │                │ 4. Forward ────│──▶ 5. Execute   │
     │                │    via curl-cffi   request        │
     │                │                │                  │
     │                │                │◀── 6. Response ──│
     │                │ 7. Collect     │                  │
     │                │    Set-Cookie  │                  │
     │                │    → CookieJar │                  │
     │                │                │                  │
     │◀── 8. Render ──│ 9. Fulfill    │                  │
     │    natively    │    route()     │                  │
```

**Step-by-step**:

1. User enters URL in GUI or navigates in browser
2. `page.route("**/*")` intercepts the request (`cdp_routing.py:29`)
3. `FingerprintMatcher.get_headers()` generates browser-specific headers (`engine.py:182-250`)
4. `CookieJar.get_for_request()` selects matching cookies (`engine.py:344-382`)
5. `curl_requests.request(impersonate=...)` sends with TLS fingerprint (`cdp_routing.py:169-178`)
6. Target server responds
7. `Set-Cookie` headers parsed and added to `CookieJar` (`cdp_routing.py:83-99`)
8. Browser renders the response natively via `route.fulfill()` (`cdp_routing.py:122-126`)

### Legacy Proxy Request Lifecycle

```
┌─────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ Browser  │────▶│ Service  │────▶│ aiohttp  │────▶│  Target  │
│  (user)  │     │ Worker   │     │ server   │     │  Server  │
└─────────┘     └──────────┘     └──────────┘     └──────────┘
     │                │                │                  │
     │  1. Fetch      │ 2. Redirect    │                  │
     │    request     │ to /proxy/     │                  │
     │                │                │                  │
     │                │ 3. _handle_    │                  │
     │                │    proxy()     │                  │
     │                │                │                  │
     │                │ 4. build_      │                  │
     │                │    target_url()│                  │
     │                │                │                  │
     │                │ 5. forward_    │                  │
     │                │    request() ──│──▶ 6. Execute   │
     │                │                │                  │
     │                │                │◀── 7. Response ──│
     │                │ 8. rewrite_    │                  │
     │                │    html/css/js │                  │
     │◀── 9. Serve ───│ 9. filter_    │                  │
     │    rewritten   │    headers     │                  │
```

---

## Session Format

### TokenadeSession v2.0

The `.tokenade` file is a JSON document with the following structure:

```json
{
  "version": "2.0",
  "created_at": "2024-01-15T10:30:00Z",
  "source_device": {
    "browser": "firefox",
    "profile": "default",
    "platform": "Linux",
    "hostname": "anonymous"
  },
  "site_name": "github",
  "auth_status": "logged_in",
  "cookies": [
    {
      "name": "user_session",
      "value": "encrypted_value",
      "domain": "github.com",
      "path": "/",
      "secure": true,
      "httpOnly": true,
      "sameSite": "Lax",
      "expires": 1705312200
    }
  ],
  "tokens": [],
  "local_storage": {
    "key": "value"
  },
  "fingerprint": {
    "user_agent": "Mozilla/5.0 ...",
    "platform": "Win32",
    "language": "en-US",
    "screen_width": 1920,
    "screen_height": 1080
  },
  "tls_profile": {
    "browser": "chrome",
    "version": "120",
    "impersonate": "chrome120",
    "http_version": "2"
  },
  "metadata": {
    "extraction_method": "sqlite_direct",
    "cookie_count": 15,
    "critical_cookie_count": 3,
    "local_storage_count": 5
  }
}
```

**Required fields** (`session_packager.py:298-323`): `version`, `created_at`, `site_name`, `auth_status`, `cookies`

### Cookie Encryption

Cookie decryption is platform-specific (`cookie_crypto.py:100-527`):

| Platform | Algorithm | Key Source | File |
|----------|-----------|------------|------|
| Windows | AES-256-GCM | DPAPI → `Local State` → `os_crypt.encrypted_key` | `WindowsCookieCrypto` |
| Linux | AES-128-CBC | PBKDF2(`sha1`, `"peanuts"`, `"saltysalt"`, 1 iteration) | `LinuxCookieCrypto` |
| macOS | AES-256-GCM | Keychain → `"Chrome Safe Storage"` | `MacCookieCrypto` |

**Windows decryption flow** (`cookie_crypto.py:168-195`):
1. Read `Local State` → base64 decode `os_crypt.encrypted_key`
2. Strip DPAPI prefix (5 bytes) → `CryptUnprotectData()` → AES-256 key
3. Cookie: `v10`/`v11` prefix (3 bytes) + nonce (12 bytes) + ciphertext + GCM tag (16 bytes)
4. AES-256-GCM decrypt → skip first 32 bytes metadata → UTF-8 plaintext

**Linux decryption flow** (`cookie_crypto.py:302-343`):
1. Get key: `secretstorage` → `"Chrome Safe Storage"` or fallback `"peanuts"`
2. Derive: `PBKDF2-HMAC-SHA1(key, "saltysalt", 1 iteration, dklen=16)`
3. Cookie: `v10` prefix (3 bytes) + IV (16 bytes, all `0x20` spaces) + ciphertext
4. AES-128-CBC decrypt → PKCS7 unpad → UTF-8 plaintext

### File Encryption

`.tokenade.encrypted` files use AES-256-GCM (`encryptor.py:40-177`):

```
┌─────────────────────────────────────────────────────┐
│  TOKENADE_ENCRYPTED (18 bytes)                      │
│  Version (4 bytes, big-endian uint32)               │
│  Salt (16 bytes)                                    │
│  Nonce (12 bytes)                                   │
│  Encrypted Data + GCM Auth Tag (16 bytes)           │
└─────────────────────────────────────────────────────┘
```

- Key derivation: PBKDF2-HMAC-SHA256, 600,000 iterations
- Authenticated encryption: AES-256-GCM (GCM tag provides integrity, no separate HMAC)

---

## Security Architecture

### SSRF Protection

`cdp_stealth.py:11-41` blocks requests to internal/private networks:

```python
BLOCKED_NETWORKS = [
    "10.0.0.0/8",      # Private Class A
    "172.16.0.0/12",    # Private Class B
    "192.168.0.0/16",   # Private Class C
    "169.254.0.0/16",   # Link-local
    "127.0.0.0/8",      # Loopback
    "::1/128",          # IPv6 loopback
    "fc00::/7",         # IPv6 ULA
]

# Also blocked hostnames:
# "localhost", "0.0.0.0", "[::]", "metadata.google.internal"
```

`is_safe_url()` is called before every request in both proxy modes (`cdp_routing.py:278`, `cdp_gui.py:240`).

### XSS Prevention

All user-provided data is escaped with `html_mod.escape()` before embedding in HTML:
- `cdp_gui.py:24-29` — site name, browser, platform
- `cdp_routing.py:345-351` — page URLs injected into HTML

### Header Security

`cdp_routing.py:20-26` strips security-sensitive response headers:

```python
SKIP_HEADERS = {
    "content-security-policy",  # Allows proxied content to load
    "x-frame-options",          # Allows iframe embedding
    "strict-transport-security",# Prevents HSTS interference
    "content-encoding",         # Avoids double-decompression
    "transfer-encoding",        # Chunked transfer handled by proxy
}
```

### Race Condition Fixes

`cdp_proxy.py:26-71` handles duplicate headers from stale service workers:
- `_strip_duplicate_headers()` — removes duplicate HTTP headers from raw request data
- `_LenientProtocol` — wraps aiohttp's protocol to tolerate malformed requests
- `_LenientServerFactory` — protocol factory that applies the lenient wrapper

### SSL Verification

`engine.py:488` — SSL verification is configurable via `RuntimeConfig.verify_ssl`:
- Default: `True` (verify SSL certificates)
- Can be disabled for development/testing

---

## Plugin System

### Registry

`plugin_registry.py:41-250` — GitHub-hosted plugin registry:

- Registry URL: `https://tokenade-plugins.pages.dev`
- Local cache: `~/.tokenade/plugins/.registry_cache.json` (1-hour TTL)
- Plugin metadata: name, version, description, author, type, entry_point

**Plugin types**:
- `handler` — Site-specific request/response handling
- `export_format` — Custom export formats
- `validator` — Custom validation rules

### Local Plugins

`plugin_loader.py:33-286` — Plugin discovery and loading:

```
~/.tokenade/plugins/
├── plugin-name/
│   ├── plugin.json          # Manifest (name, version, entry_point)
│   └── main.py              # Plugin code
```

**Loading flow**:
1. `discover()` — scan `~/.tokenade/plugins/` for `plugin.json` manifests
2. `load_all()` — load each plugin via `importlib.util.spec_from_file_location()`
3. `load_plugin()` — instantiate the entry class
4. Plugins register handlers via `register_handler()`, `register_exporter()`, `register_validator()`

---

## Session Sync

`session_sync.py:50-301` — Daemon for automatic session export:

### Daemon Architecture

```
SessionSyncDaemon
    ├── SyncTarget[]          # Sites to monitor
    │   ├── name              # "gmail"
    │   ├── domains           # ["google.com", "mail.google.com"]
    │   ├── browser           # "firefox"
    │   └── output_dir        # "~/.tokenade/synced"
    │
    └── SyncStatus[]          # Per-target status
        ├── last_sync         # ISO timestamp
        ├── last_db_mtime     # File modification time
        └── sync_count        # Number of syncs performed
```

### Change Detection

Uses `os.stat().st_mtime` for lightweight detection:
1. Record initial mtime of browser cookie database
2. On each interval (default 60s), check mtime
3. If mtime changed → re-extract cookies → re-package → save `.tokenade` file
4. No need to read the database unless mtime changes

### Multi-Browser Support

```python
daemon.add_target(SyncTarget(
    name="gmail",
    domains=["google.com", "accounts.google.com"],
    browser="firefox",              # Primary
    browser_profile="default",
))
```

---

## Monitoring

`session_monitor.py:17-286` — Real-time session health tracking:

### Health Scores

```
CookieStatus:
    healthy  → expires > warning_threshold
    warning  → expires < warning_threshold (7 days default)
    expired  → expires < now

SessionStatus:
    health_score = healthy_cookies / total_cookies (0.0 - 1.0)
```

### Session Refresher

`session_refresher.py` (`core/refresh/session_refresher.py:49-354`) — Automatic cookie expiry handling:

```
SessionRefresher
    ├── RefreshConfig
    │   ├── check_interval      # 300 seconds (5 min)
    │   ├── expiry_warning_days # 7 days
    │   ├── expiry_critical_days# 1 day
    │   ├── auto_refresh        # bool
    │   └── fallback_browsers   # ["firefox", "chrome", ...]
    │
    └── CookieExpiryInfo
        ├── total_cookies
        ├── expired_count
        ├── expiring_soon_count
        ├── critical_count
        └── next_expiry_human
```

**Refresh flow**:
1. Periodic check of cookie expiry via `CookieJar.get_expired_cookies()`
2. Log warnings for expiring cookies
3. If `auto_refresh=True` and source browser available → re-extract cookies
4. Hot-reload via `_on_session_refresh()` callback → re-inject into browser context
5. WebSocket notification to connected clients

---

## Performance

### curl-cffi TLS Fingerprinting

`cdp_routing.py:137-199` — All requests go through `curl-cffi` with TLS impersonation:

```python
response = await asyncio.to_thread(
    curl_requests.request,
    method=method,
    url=url,
    headers=donor_headers,
    impersonate="chrome120",    # Matches Chrome 120 TLS fingerprint
    timeout=proxy.config.timeout,
)
```

- `asyncio.to_thread()` runs blocking curl-cffi calls in a thread pool
- Fallback to aiohttp if curl-cffi fails

### Streaming Responses

- Forward proxy: bidirectional stream piping (`forward_proxy.py:114-147`)
- CDP proxy: `route.fulfill(body=response.body)` streams response data
- Legacy proxy: `web.Response(body=response.body)` streams via aiohttp

### Connection Pooling

**Per-proxy** (`cdp_routing.py:216-228`):
```python
connector = aiohttp.TCPConnector(
    ssl=None,
    limit=100,          # Total connections
    limit_per_host=30,  # Per-host connections
)
```

**Multi-site shared pool** (`multi_site_proxy.py:29-89`):
```python
SharedConnectionPool(
    max_connections=200,
    max_per_host=50,
    timeout=30,
)
```

### Fingerprint Header Ordering

`engine.py:155-180` — Headers are ordered browser-specifically for HTTP/2 fingerprinting:

```python
CHROME_HEADERS = [
    ":authority", ":method", ":path", ":scheme",
    "accept", "accept-encoding", "accept-language",
    "cache-control", "cookie", "sec-ch-ua", ...
]
```

This ordering is critical for HTTP/2 SETTINGS frame fingerprinting (JA3/H2).

### CookieJar Efficiency

`engine.py:291-440` — Domain-keyed cookie storage:
- `cookies: Dict[str, List[Dict]]` — O(1) domain lookup
- `get_for_request()` — domain + path matching with expiry checking
- `prune_expired()` — batch removal of expired cookies

---

## Site Configs (plugin-owned)

`site_configs.py` resolves site metadata from **handler plugins only**:

```
~/.tokenade/plugins/<name>-handler/
├── plugin.json
├── plugin.py
└── site_config.json   # domains, critical_cookies, URLs
```

- `get_site_config("google")` → loads that plugin’s `site_config.json`
- `SiteHandlerPlugin` base class loads the same file for export/verify defaults
- No built-in Python catalog; no repo-root `site_configs/` directory

Each `site_config.json` typically defines:
- `domains` — Cookie domains to match during extraction
- `critical_cookies` — Cookies required for session validity
- `dashboard_url` / `validate_url` — Logged-in / health URLs
- `login_indicator_css` / selectors — Logged-out UI markers
- `wait_seconds` — Time to wait for page load during validation
