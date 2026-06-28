# Tokenade v6.0 — Browser Session Portability Tool

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
| **Session Refresh** | Auto-refresh expiring cookies with multi-browser fallback |
| **Health Scoring** | OWASP-based session health scoring and validation |
| **Site Configs** | Preset configs for GitHub, Discord, Reddit, Google, OpenAI |

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

### Browser Stealth

| Feature | Description |
|---------|-------------|
| **14 Patch Categories** | Webdriver, plugins, permissions, WebGL, canvas, audio, screen, automation |
| **Cloudflare Bypass** | Turnstile solver, cf_clearance extraction, multi-domain support |
| **Akamai Bypass** | Bot detection bypass, akamai cookies extraction |
| **CAPTCHA Detection** | Turnstile, hCaptcha, reCAPTCHA detection and status tracking |
| **Residential Proxy** | Session-affinity proxy with sticky sessions and rotation |
| **Stealth Testing** | 18-point automated detection test suite with scoring |
| **Battle Testing** | End-to-end validation against 5 real detection sites with composite scoring |
| **Detection Dashboard** | HTML/JSON reports with category breakdown |

### Competitor Parity

| Feature | Description |
|---------|-------------|
| **Profile Manager** | Create, list, delete, export/import browser profiles |
| **Fingerprint Generator** | OS/hardware-aware deterministic fingerprint generation |
| **Multi-Profile Sync** | Execute actions across multiple browser profiles simultaneously |
| **Competitor Import** | Import sessions from AdsPower, Multilogin, GoLogin |

### Plugin System

| Feature | Description |
|---------|-------------|
| **16+ Plugin Types** | Site handlers, export formats, validators, stealth, proxy, captcha |
| **Plugin Marketplace** | Search, categories, ratings, trending, compatibility checks |
| **Plugin Testing** | Automated test suite for plugin validation |
| **HTML Marketplace** | Static marketplace page with search and filters |
| **Official Plugins** | 10+ plugins (OAuth2, Discord, Reddit, WhatsApp, Telegram, etc.) |

### Enterprise

| Feature | Description |
|---------|-------------|
| **Audit Logging** | Structured JSONL logs for all session operations |
| **Role-Based Access Control** | Admin/editor/viewer roles with persistent storage |
| **LDAP/SSO Integration** | LDAP bind authentication with group membership checks |

### Browser Support

| Browser | Status | Notes |
|---------|--------|-------|
| Chrome | Full | SQLite extraction, profile discovery, binary patching |
| Firefox | Full | SQLite extraction, profile discovery |
| Edge | Full | Chromium-based, same as Chrome |
| Brave | Full | Chromium-based, same as Chrome |
| Safari | Partial | Binary cookie parsing, macOS only |
| Tor Browser | Full | Firefox-based, cross-platform profile discovery |
| Mobile (Android) | Full | Via ADB — Chrome and Firefox on Android |

### Integration

| Feature | Description |
|---------|-------------|
| **GitHub Actions** | CI/CD with lint, test matrix (3.10–3.12), security scan, build |
| **Kubernetes** | Deployment, Service, ConfigMap, sidecar YAML generation |

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
  --rotate              Enable session rotation
  --rotate-strategy     Rotation strategy (health-weighted, round-robin, random, lru)
  --rotate-interval     Rotation interval in seconds
```

### Stealth

```bash
tokenade stealth test                     # Run 18-point detection test suite
tokenade stealth battle                   # Battle test against 5 real detection sites
tokenade stealth report                   # Generate HTML/JSON detection report
tokenade stealth deps                     # Check stealth system dependencies
tokenade stealth deps-install             # Install missing dependencies
```

**Battle Test Options:**

```bash
tokenade stealth battle --browser chromium        # Test with Chromium (default)
tokenade stealth battle --browser firefox         # Test with Firefox
tokenade stealth battle --site bot_sannysoft      # Test specific site only
tokenade stealth battle --output report.json      # Save JSON report
tokenade stealth battle -s bot_sannysoft -s creepjs  # Multiple sites
```

**Detection Sites Tested:**

| Site | What It Detects | Weight |
|------|----------------|--------|
| bot.sannysoft.com | WebDriver, automation flags | 1.0 |
| creepjs | Browser fingerprint anomalies | 0.8 |
| pixelscan.net | Headless, automation vectors | 1.0 |
| browserleaks.com | JavaScript API leaks | 0.7 |
| iphey.com | Bot detection, behavioral analysis | 0.6 |

### Browser Launch

```bash
tokenade launch -s session.tokenade -u https://site.com [options]

Options:
  -s, --session FILE     Session file (required)
  -u, --url URL          Target URL
  -b, --browser NAME     Browser (chrome, firefox, brave, edge)
  --visible              Show browser window
  --headless             Run in headless mode
  --proxy URL            Upstream proxy
  --proxy-file FILE      Proxy list file
  --proxy-rotate         Rotate proxies
  --plugin NAME          Plugin to use
  --encrypt              Encrypt session at rest
```

### Session Refresh

```bash
tokenade refresh-browser -s session.tokenade -b chrome --url https://github.com
tokenade accounts list                     # List all sessions
tokenade accounts status                   # Health status with color coding
tokenade accounts refresh --all            # Parallel refresh with unique CDP ports
```

### Sessions

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
tokenade health-report --sessions-dir ./sessions
tokenade validate-rules -s session.tokenade -r rules.json
tokenade diff file1.tokenade file2.tokenade
```

### Profile Management

```bash
tokenade profile create --name "Work" --browser chrome
tokenade profile list
tokenade profile get --name "Work"
tokenade profile delete --name "Work"
tokenade profile export --name "Work" -o work-profile.json
tokenade profile import --file work-profile.json
tokenade profile recent
tokenade profile stats
```

### Fingerprint

```bash
tokenade fingerprint --browser chrome --platform windows
tokenade fingerprint --seed my-seed --count 5
```

### Multi-Profile Sync

```bash
tokenade sync --action "navigate,url=https://example.com;click,button#submit"
```

### Plugins

```bash
tokenade plugin list                           # List installed plugins
tokenade plugin install <name>                 # Install from marketplace
tokenade plugin uninstall <name>               # Remove plugin
tokenade plugin info <name>                    # Plugin details
tokenade plugin enable <name>                  # Enable plugin
tokenade plugin disable <name>                 # Disable plugin
tokenade plugin update <name>                  # Update plugin
tokenade plugin reload                         # Reload all plugins
tokenade plugin search <query>                 # Search marketplace
tokenade plugin categories                     # List categories
tokenade plugin popular                        # Top by downloads
tokenade plugin recent                         # Recently added
tokenade plugin trending                       # Trending plugins
tokenade plugin rate <name> <1-5>              # Rate plugin
tokenade plugin verify <name>                  # Verify checksum
tokenade plugin outdated                       # Check for updates
tokenade plugin browse                         # Generate HTML marketplace
tokenade plugin test <name>                    # Run plugin test suite
```

### Server

```bash
tokenade serve --port 8080                     # Start REST API server
```

### Configuration

```bash
tokenade config show                          # View all config
tokenade config set default_browser brave
tokenade config set stealth_level maximum
tokenade config get default_browser
tokenade config path
```

### Daemon

```bash
tokenade daemon start                         # Start background daemon
tokenade daemon stop                          # Stop daemon
tokenade daemon status                        # Check daemon status
tokenade daemon add session.tokenade          # Add session to daemon
tokenade daemon remove session.tokenade       # Remove session
tokenade daemon list                          # List managed sessions
```

### Session Versioning

```bash
tokenade versions list session.tokenade       # List versions
tokenade versions create session.tokenade     # Create version
tokenade versions delete session.tokenade 2   # Delete version
tokenade rollback session.tokenade 2          # Rollback to version
tokenade session-diff session.tokenade 1 2    # Diff versions
```

### Logging

```bash
tokenade logs                                 # View recent logs
tokenade logs --follow                        # Tail logs
tokenade logs --search "error"                # Search logs
tokenade logs --json                          # JSON format
```

### Other Commands

```bash
tokenade batch-export                         # Batch export multiple sessions
tokenade batch-load                           # Batch load sessions
tokenade batch-refresh                        # Batch refresh with rate limiting
tokenade clone-profile                        # Clone browser profile
tokenade completion                           # Shell completion
tokenade container start/status/health        # Docker container management
tokenade deps                                 # System dependency check
tokenade inject-profile                       # Inject session into browser profile
tokenade k8s deploy/status/scale              # Kubernetes management
tokenade mobile-import                        # Import from Android/iOS
tokenade monitor start/stop/status/history    # Session monitoring
tokenade oauth-config                         # Configure OAuth
tokenade patch-chrome scan/patch/restore      # Chrome binary patching
tokenade refresh-oauth                        # Refresh OAuth tokens
tokenade setup                                # Initial setup
tokenade transfer                             # Transfer sessions
tokenade validate-session                     # CI/CD validation
```

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
| **Stealth & Anti-Detection** | ✅ 14 patches, Cloudflare/Akamai bypass | ❌ | ❌ |
| **Plugin System** | ✅ 16+ types, marketplace | ❌ | ❌ |
| **Competitor Import** | ✅ AdsPower/Multilogin/GoLogin | ❌ | ❌ |
| **Enterprise Features** | ✅ Audit, RBAC, LDAP | ❌ | ❌ |
| **Self-Hosted** | ✅ No third-party | N/A | ✅ |

## What's New in v6.0

- **Enhanced Browser Stealth** — 14 patch categories, 2026-grade anti-detection
- **Cloudflare & Akamai Bypass** — Turnstile solver, cf_clearance extraction, residential proxy support
- **CAPTCHA Detection** — Turnstile, hCaptcha, reCAPTCHA detection
- **Plugin Marketplace** — Search, categories, ratings, trending, HTML marketplace page
- **Profile Manager** — Create, list, export/import browser profiles
- **Fingerprint Generator** — OS/hardware-aware deterministic fingerprints
- **Multi-Profile Sync** — Execute actions across multiple browser profiles
- **Competitor Import** — Import sessions from AdsPower, Multilogin, GoLogin
- **Stealth Testing** — 18-point automated detection test suite with HTML/JSON reports
- **Python 3.10+ Required** — Dropped Python 3.9 support

## Installation

```bash
pip install tokenade
playwright install chromium --with-deps
```

### Optional Dependencies

```bash
pip install tokenade[runtime]    # curl-cffi for TLS matching
pip install tokenade[enterprise] # ldap3 for LDAP/SSO
pip install tokenade[linux]      # secretstorage for Linux keyring
```

### Development

```bash
git clone https://github.com/mihir0209/tokenade.git
cd tokenade
pip install -e ".[dev]"
playwright install chromium --with-deps
```

## .tokenade File Format

```json
{
  "version": "2.0",
  "created_at": "2026-06-27T12:00:00Z",
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
    "version": "131",
    "impersonate": "chrome131",
    "http_version": "2"
  },
  "metadata": {
    "cookie_count": 50,
    "critical_cookie_count": 30
  }
}
```

## Architecture

```
tokenade/
├── core/
│   ├── browser/
│   │   ├── stealth.py              # 14-patch stealth injection
│   │   ├── stealth_test.py         # 18-point detection test suite
│   │   ├── dashboard.py            # HTML/JSON detection reports
│   │   ├── cloudflare.py           # Cloudflare & Akamai bypass
│   │   ├── captcha.py              # CAPTCHA detection
│   │   ├── tls_fingerprint.py      # curl-cffi TLS matching
│   │   ├── undetectable.py         # System browser launcher
│   │   ├── cdp_connection.py       # CDP WebSocket connection
│   │   ├── patcher.py              # Chrome binary patcher
│   │   ├── profiles.py             # Browser profile manager
│   │   ├── fingerprint.py          # Fingerprint generator
│   │   ├── synchronizer.py         # Multi-profile sync
│   │   └── dependencies.py         # System dependency checker
│   ├── proxy/
│   │   ├── cdp_proxy.py            # CDP proxy (recommended)
│   │   ├── forward_proxy.py        # HTTP forward proxy
│   │   ├── multi_site_proxy.py     # Multi-site bundler
│   │   ├── rotation.py             # Proxy rotation
│   │   └── residential.py          # Residential proxy pool
│   ├── importer/
│   │   ├── browser_discovery.py    # Find browser profiles
│   │   ├── cookie_extractor.py     # Extract cookies from SQLite
│   │   ├── session_packager.py     # Package into .tokenade
│   │   ├── session_loader.py       # Load .tokenade into browser
│   │   ├── session_refresher.py    # Auto-refresh sessions
│   │   ├── session_sharer.py       # Email, webhook, QR codes
│   │   ├── session_manager.py      # Multi-session management
│   │   ├── competitor_import.py    # AdsPower/Multilogin/GoLogin import
│   │   └── mobile_import.py        # Android/iOS import
│   ├── integration/
│   │   ├── plugin_loader.py        # Plugin auto-discovery
│   │   ├── plugin_registry.py      # Plugin marketplace registry
│   │   ├── plugin_search.py        # TF-IDF search index
│   │   ├── plugin_browser.py       # HTML marketplace generator
│   │   ├── plugin_verifier.py      # SHA256 verification
│   │   ├── plugin_testing.py       # Plugin test runner
│   │   └── container_orchestrator.py
│   ├── crypto/
│   │   ├── encryptor.py            # AES-256-GCM encryption
│   │   └── at_rest.py              # Transparent encryption at rest
│   ├── security/
│   │   ├── credentials.py          # Credential management
│   │   └── audit.py                # Audit logging, RBAC, LDAP
│   ├── api/
│   │   └── server.py               # REST API server
│   ├── daemon/
│   │   └── session_daemon.py       # Background refresh daemon
│   ├── logging/
│   │   └── structured.py           # JSON structured logging
│   ├── config.py                   # Config file support
│   └── utils/
│       └── performance.py          # LRU cache, connection pooling
├── cli/                            # 47 CLI commands
├── plugin/
│   └── base.py                     # Plugin base classes
├── handlers/                       # Site-specific handlers
├── extension/                      # Browser extension
└── tests/                          # 5035+ tests
```

## Security

- Session files contain raw cookies — treat like passwords
- Use `tokenade encrypt` to encrypt at rest
- The proxy runs on `127.0.0.1` only (not accessible from network)
- Cookies are injected into an isolated Playwright browser context
- SSRF protection blocks private/loopback/link-local IPs
- HMAC-SHA256 signatures on shared sessions
- Audit logging tracks all session operations
- Stealth patches hide automation artifacts from detection
- Residential proxy support for anonymous session refresh

## Documentation

- [Use Cases & Competitor Comparison](USE-CASES.md)
- [Site Configurations](docs/SITE_CONFIGS.md)
- [Troubleshooting Guide](docs/TROUBLESHOOTING.md)
- [Tutorials](docs/)
- [API Reference](docs/API.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Security](docs/SECURITY.md)
- [Competitor Comparison](docs/competitor-comparison.md)
- [Contributing](docs/CONTRIBUTING.md)

## License

MIT License
