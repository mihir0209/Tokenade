# Tokenade v3.0 — Browser Session Portability Tool

Extract browser sessions from one device, package them into portable `.tokenade` files, and browse as the donor on another device using a **CDP reverse proxy** with TLS fingerprint matching.

## Features

### Core

| Feature | Description |
|---------|-------------|
| **Session Export** | Extract cookies from Chrome, Firefox, Brave, Edge, Safari, Tor Browser |
| **Session Injection** | Inject sessions via CDP proxy or direct profile modification |
| **TLS Fingerprint Matching** | Bypass Cloudflare, DataDome with curl-cffi |
| **localStorage Support** | Extract/inject localStorage (Telegram, WhatsApp) |
| **Encryption** | AES-256-GCM encryption for session files |
| **Multi-Browser** | Cross-browser support (extract from Firefox, inject into Chrome) |

### Advanced

| Feature | Description |
|---------|-------------|
| **Session Auto-Refresh** | WebSocket notifications, multi-browser fallback, hot-reload |
| **Session Sharing** | Email, webhook (Slack/Discord), QR codes, HMAC-SHA256 signatures |
| **Multi-Session Management** | List, merge, rotate, stats across multiple sessions |
| **Advanced Validation** | Custom JS rules, screenshot comparison, API validation |
| **Browser Extension** | Chrome/Firefox extension for one-click export |
| **HTTP Forward Proxy** | `HTTP_PROXY` mode with TLS matching |
| **Multi-Site Bundler** | Serve multiple sessions with tabbed GUI |

### Enterprise

| Feature | Description |
|---------|-------------|
| **Audit Logging** | Structured JSONL logs for all session operations |
| **Role-Based Access Control** | Admin/editor/viewer roles with persistent storage |
| **LDAP/SSO Integration** | LDAP bind authentication with group membership checks |

### Performance

| Feature | Description |
|---------|-------------|
| **Connection Pooling** | Shared HTTP connections across multi-site proxy |
| **LRU Session Caching** | In-memory cache with configurable TTL |
| **Parallel Extraction** | Concurrent cookie extraction from multiple profiles |

### Browser Support

| Browser | Status | Notes |
|---------|--------|-------|
| Chrome | Full | SQLite extraction, profile discovery |
| Firefox | Full | SQLite extraction, profile discovery |
| Edge | Full | Chromium-based, same as Chrome |
| Brave | Full | Chromium-based, same as Chrome |
| Safari | Partial | Binary cookie parsing, macOS only |
| Tor Browser | Full | Firefox-based, cross-platform profile discovery |
| Mobile (Android) | Full | Via ADB — Chrome and Firefox on Android |

### Integration

| Feature | Description |
|---------|-------------|
| **GitHub Actions** | CI/CD with lint, test matrix (3.9–3.12), security scan, build |
| **Docker** | Multi-stage build, session management, batch containers |
| **Kubernetes** | Deployment, Service, ConfigMap, sidecar YAML generation |

## How It Works

### 1. Session Export

```
Your Browser (Firefox/Chrome/Safari/Tor)
        │
        ▼
┌─────────────────┐
│ tokenade export │
└─────────────────┘
        │
        ▼
┌─────────────────┐
│ Read SQLite DB  │──── Browser stores cookies in SQLite
└─────────────────┘
        │
        ▼
┌─────────────────┐
│ Decrypt Cookies │──── Platform-specific decryption
└─────────────────┘
        │
        ▼
┌─────────────────┐
│ Package .tokenade│──── JSON with cookies, fingerprint, TLS profile
└─────────────────┘
        │
        ▼
   session.tokenade
```

### 2. Session Injection (CDP Proxy)

```
.tokenade file
        │
        ▼
┌─────────────────┐
│ tokenade proxy  │
└─────────────────┘
        │
        ▼
┌─────────────────┐
│ Launch Chromium │──── Playwright browser
└─────────────────┘
        │
        ▼
┌─────────────────┐
│ Inject Cookies  │──── Add to browser context
└─────────────────┘
        │
        ▼
┌─────────────────┐
│ page.route()    │──── Intercept ALL browser requests
└─────────────────┘
        │
        ▼
┌─────────────────┐
│ curl-cffi       │──── Forward with donor TLS fingerprint
│ (TLS matched)   │
└─────────────────┘
        │
        ▼
   http://127.0.0.1:9222
   You are logged in as donor
```

### 3. TLS Fingerprint Matching (Why It Works)

```
Without Tokenade:
Your Browser → Your TLS fingerprint → Blocked by Cloudflare

With Tokenade:
Your Browser → Tokenade Proxy → Donor's TLS fingerprint → Allowed

curl-cffi impersonates Chrome's TLS handshake (JA3 hash),
so servers see the donor's fingerprint, not yours.
```

## Why Tokenade?

| Feature | Tokenade | Browser Extensions | Simple CLI Tools |
|---------|----------|-------------------|------------------|
| **CLI Interface** | ✅ Scriptable, automatable | ❌ GUI-only | ✅ |
| **TLS Fingerprint Matching** | ✅ Bypasses Cloudflare/DataDome | ❌ | ❌ |
| **Site-Agnostic** | ✅ Works with any website | ❌ Often site-specific | ⚠️ Limited |
| **Multi-Browser** | ✅ Chrome/Firefox/Edge/Safari/Tor | ⚠️ Single browser | ❌ |
| **localStorage Support** | ✅ Critical for Telegram, WhatsApp | ❌ | ❌ |
| **Encrypted Session Files** | ✅ AES-256-GCM | ❌ | ⚠️ Varies |
| **Enterprise Features** | ✅ Audit, RBAC, LDAP | ❌ | ❌ |
| **Docker/K8s Ready** | ✅ Built-in integration | N/A | ❌ |
| **Self-Hosted** | ✅ No third-party | N/A | ✅ |

**Unique advantage**: Tokenade is the only CLI tool that matches TLS fingerprints for cross-browser session portability.

## Quick Start (3 commands)

### Step 1 — Export cookies from your browser

```bash
# See what browsers are installed
tokenade export --list-profiles

# Export ChatGPT session from Firefox
tokenade export --browser-name firefox --domains "chatgpt.com,openai.com" -o chatgpt.tokenade

# Export Gmail session from Chrome
tokenade export --browser-name chrome --domains "google.com,accounts.google.com" -o gmail.tokenade
```

### Step 2 — Start the proxy

```bash
# Start CDP proxy (default — recommended)
tokenade proxy -s chatgpt.tokenade

# Custom port, visible browser
tokenade proxy -s gmail.tokenade --port 8080 --visible
```

### Step 3 — Browse

Open `http://127.0.0.1:9222`, enter the target URL, and click Browse.

## Full CLI Reference

### Export

```bash
tokenade export [options]

Options:
  --browser-name {chrome,firefox,edge,brave}
  --browser-path PATH        Custom browser profile path
  --profile NAME             Profile name (e.g. "Default", "Profile 1")
  --domains DOMAINS          Comma-separated domains to filter
  --site-config FILE         JSON site config for domain filtering
  -o, --output FILE          Output file path
  --list-profiles            List discovered browser profiles
  --extract-local-storage    Also extract localStorage
  --local-storage-origin ORIGIN
```

### Proxy

```bash
tokenade proxy -s SESSION_FILE [options]

Options:
  -s, --session FILE    .tokenade session file (required)
  -p, --port PORT       Port (default: 9222)
  --host HOST           Bind address (default: 127.0.0.1)
  --visible             Show Chromium window
  --no-open-browser     Don't auto-open GUI
  --timeout SECONDS     Request timeout (default: 30)
  --all                 Multi-site mode (use -d for sessions directory)
  --mode {cdp,forward}  Proxy mode
  --legacy              Use legacy service-worker proxy
  --auto-refresh        Enable auto-refresh from source browser
  --source-browser NAME Browser to refresh from
```

### Multi-Session

```bash
tokenade sessions list -d ./sessions         # List sessions
tokenade sessions list --site google          # Filter by site
tokenade sessions merge s1.tokenade s2.tokenade -o merged.tokenade
tokenade sessions rotate s1.tokenade s2.tokenade
tokenade sessions stats *.tokenade
```

### Session Sharing

```bash
tokenade share -s session.tokenade                    # Create URL
tokenade share -s session.tokenade --format qr -o qr.png
tokenade share -s session.tokenade --password x --expiry 48
tokenade share -s session.tokenade --webhook https://hooks.slack.com/...
tokenade unshare --list
tokenade unshare <session-id>
```

### Encrypt / Decrypt

```bash
tokenade encrypt -s session.tokenade -o encrypted.tokenade
tokenade decrypt -s encrypted.tokenade -o session.tokenade
tokenade rekey -s encrypted.tokenade
```

### Health & Validation

```bash
tokenade health -s session.tokenade
tokenade validate-rules -s session.tokenade -r rules.json
tokenade diff file1.tokenade file2.tokenade
```

### Inject Profile

```bash
tokenade inject-profile -s session.tokenade --browser firefox --profile "default"
tokenade inject-profile -s session.tokenade --browser firefox --profile "default" --dry-run
```

## Docker

```bash
# Build
docker build -t tokenade .

# Run proxy in container
docker run --rm -p 9222:9222 \
  -v ./sessions:/app/sessions:ro \
  --cap-add=SYS_ADMIN \
  tokenade proxy --host 0.0.0.0 -s /app/sessions/session.tokenade

# Docker Compose
docker compose up tokenade
```

### Docker Session Management

```python
from tokenade.core.integration import DockerSessionManager

manager = DockerSessionManager()
manager.create_session_container("session.tokenade", "my-proxy", port=9222)
print(manager.get_status())
```

## Kubernetes

### Sidecar Mode

```python
from tokenade.core.integration import KubernetesManager, KubernetesConfig

k8s = KubernetesManager(KubernetesConfig(namespace="production"))
print(k8s.generate_sidecar_yaml("my-app:latest", "tokenade-sessions"))
```

### Generate Manifests

```python
# Full deployment
print(k8s.generate_deployment_yaml(session_configmap="tokenade-sessions"))

# Service
print(k8s.generate_service_yaml())

# ConfigMap from session files
print(k8s.generate_configmap_yaml({
    "session.tokenade": open("session.tokenade").read()
}))
```

## Enterprise

### Audit Logging

```python
from tokenade.core.security.audit import AuditLogger

logger = AuditLogger()
logger.log_event("session_export", session_id="abc", site_name="google")
logger.log_event("session_share", session_id="abc", method="email")
print(logger.get_summary())
```

### Role-Based Access Control

```python
from tokenade.core.security.audit import RoleManager

rbac = RoleManager()
rbac.assign_role("user@example.com", "editor")
rbac.check_permission("user@example.com", "view_share")  # True
rbac.check_permission("user@example.com", "revoke_share")  # False
```

### LDAP Authentication

```python
from tokenade.core.security.audit import LDAPAuthenticator, LDAPConfig

config = LDAPConfig(
    server="ldap.example.com",
    port=636,
    use_ssl=True,
    bind_dn="cn=admin,dc=example,dc=com",
    bind_password="...",
    user_search_base="ou=users,dc=example,dc=com",
    user_search_filter="(uid={username})",
)
auth = LDAPAuthenticator(config)
auth.authenticate("alice", "password123")
```

## Architecture

```
tokenade/
├── core/
│   ├── proxy/
│   │   ├── cdp_proxy.py          # CDP proxy (recommended)
│   │   ├── server.py             # Legacy SW proxy
│   │   ├── forward_proxy.py      # HTTP forward proxy
│   │   └── multi_site_proxy.py   # Multi-site bundler + connection pooling
│   ├── runtime/
│   │   ├── tls_matcher.py        # curl-cffi TLS fingerprint matching
│   │   └── engine.py             # CookieJar, FingerprintMatcher
│   ├── importer/
│   │   ├── browser_discovery.py  # Find browser profiles
│   │   ├── cookie_extractor.py   # Extract cookies from SQLite
│   │   ├── local_storage_extractor.py
│   │   ├── session_packager.py   # Package into .tokenade (with LRU cache)
│   │   ├── session_loader.py     # Load .tokenade into browser
│   │   ├── session_refresher.py  # Auto-refresh with WebSocket notifications
│   │   ├── session_sharer.py     # Email, webhook, HMAC signatures
│   │   ├── session_manager.py    # Multi-session management
│   │   ├── session_comparator.py # Session diff tool
│   │   ├── advanced_validator.py # Custom validation rules
│   │   ├── safari_extractor.py   # Safari binary cookie parser
│   │   ├── tor_extractor.py      # Tor Browser extraction
│   │   ├── adb_extractor.py      # Android ADB extraction
│   │   └── db_utils.py           # Shared SQLite utilities
│   ├── security/
│   │   ├── credentials.py        # Credential management
│   │   └── audit.py              # Audit logging, RBAC, LDAP
│   ├── integration/
│   │   ├── docker_manager.py     # Docker session management
│   │   └── kubernetes.py         # K8s deployment + sidecar
│   ├── crypto/
│   │   ├── encryptor.py          # AES-256-GCM encryption
│   │   └── cookie_crypto.py      # Browser cookie decryption
│   ├── injector/
│   │   └── profile_manager.py    # Direct profile injection
│   ├── batch/
│   │   └── operations.py         # Batch export/load
│   └── utils/
│       └── performance.py        # LRU cache, connection pooling, parallel extraction
├── cli.py                        # CLI entry point (21 commands)
├── handlers/                     # Site-specific handlers
├── extension/                    # Browser extension
└── tests/                        # 1045 tests
```

## .tokenade File Format

```json
{
  "version": "2.0",
  "created_at": "2026-06-14T12:00:00Z",
  "source_device": {
    "browser": "firefox",
    "profile": "default",
    "platform": "Linux",
    "hostname": "my-pc"
  },
  "site_name": "google",
  "auth_status": "logged_in",
  "cookies": [
    {
      "name": "SID",
      "value": "abc123",
      "domain": ".google.com",
      "path": "/",
      "secure": true,
      "httpOnly": true,
      "sameSite": "Lax",
      "expires": 1781000000
    }
  ],
  "fingerprint": {
    "user_agent": "Mozilla/5.0 ...",
    "platform": "Linux",
    "language": "en-US"
  },
  "tls_profile": {
    "browser": "chrome",
    "version": "120",
    "impersonate": "chrome120",
    "http_version": "2"
  },
  "metadata": {
    "cookie_count": 50,
    "critical_cookie_count": 30
  }
}
```

## Installation

```bash
git clone https://github.com/mihir0209/tokenade.git
cd tokenade
pip install -e ".[dev]"
playwright install chromium --with-deps
```

### Optional Dependencies

```bash
pip install -e ".[runtime]"    # curl-cffi for TLS matching
pip install -e ".[enterprise]" # ldap3 for LDAP/SSO
pip install -e ".[linux]"      # secretstorage for Linux keyring
```

## Development

```bash
make install-dev     # Install with dev deps + Playwright
make test            # Run all 1045 tests
make test-quick      # Skip slow/network tests
make lint            # Flake8 linting
make format          # Black formatting
make typecheck       # Mypy type checking
make clean           # Remove build artifacts
make build           # Build distribution packages
```

### Docker Development

```bash
make docker-build    # Build Docker image
make docker-run      # Run interactively
make docker-proxy SESSION=session.tokenade  # Run proxy
make docker-cleanup  # Remove all containers
```

## Documentation

- [Use Cases & Competitor Comparison](USE-CASES.md) - All use cases, competitor analysis, feature matrix
- [API Reference](docs/API.md) - Complete API documentation
- [Architecture](docs/ARCHITECTURE.md) - System design and data flow
- [Security](docs/SECURITY.md) - Security considerations
- [Competitor Comparison](docs/competitor-comparison.md) - Market analysis
- [Contributing](docs/CONTRIBUTING.md) - How to contribute

## Security

- Session files contain raw cookies — treat like passwords
- Use `tokenade encrypt` to encrypt at rest
- The proxy runs on `127.0.0.1` only (not accessible from network)
- Cookies are injected into an isolated Playwright browser context
- SSRF protection blocks private/loopback/link-local IPs
- HMAC-SHA256 signatures on shared sessions
- Audit logging tracks all session operations

## License

MIT License
