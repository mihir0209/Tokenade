# Tokenade v6.4 — Browser Session Portability Tool

Extract browser sessions from one device, package them into portable `.tokenade` files, and browse as the donor on another device using a **CDP reverse proxy** with TLS fingerprint matching.

**5165+ tests** · **50 CLI commands** · **20 plugins** · **Grade A stealth**

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
| **CloakBrowser** | Stealth Chromium binary with 58 C++ source-level patches (default backend) |
| **14 JS Patch Fallback** | Webdriver, plugins, permissions, WebGL, canvas, audio (when CloakBrowser unavailable) |
| **Cloudflare Bypass** | Turnstile solver, cf_clearance extraction, multi-domain support |
| **Akamai Bypass** | Bot detection bypass, akamai cookies extraction |
| **CAPTCHA Detection** | Turnstile, hCaptcha, reCAPTCHA detection and status tracking |
| **Residential Proxy** | Session-affinity proxy with sticky sessions and rotation |
| **Stealth Testing** | 18-point automated detection test suite with scoring |
| **Battle Testing** | End-to-end validation against 5 real detection sites with composite scoring |
| **Detection Dashboard** | HTML/JSON reports with category breakdown |
| **Humanize** | Human-like mouse curves, keyboard timing, scroll patterns |

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
| **Plugin Marketplace** | TUI marketplace with search, categories, ratings, install/uninstall |
| **Global Ratings** | Sync ratings via GitHub Issues API (PAT required for writes) |
| **Plugin Testing** | Automated test suite for plugin validation |
| **HTML Marketplace** | Static marketplace page with search and filters |
| **14 Official Plugins** | OAuth2, Google/GitHub/Discord handlers, session-health, webhook-notify, etc. |

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

### Step 1 — Install

```bash
pip install tokenade
```

### Step 2 — Export cookies from your browser

```bash
# See what browsers are installed
tokenade export --list-profiles

# Export ChatGPT session from Firefox
tokenade export --browser-name firefox --domains "chatgpt.com,openai.com" -o chatgpt.tokenade

# Export Gmail session from Chrome
tokenade export --browser-name chrome --domains "google.com,accounts.google.com,mail.google.com" -o gmail.tokenade
```

### Step 3 — Launch with stealth (CloakBrowser)

```bash
# Launch stealth browser with session injected
tokenade launch -s gmail.tokenade -u https://mail.google.com

# With human-like behavior
tokenade launch -s gmail.tokenade -u https://mail.google.com --humanize

# Or use the proxy mode
tokenade proxy -s gmail.tokenade
```

## Full CLI Reference (58 Commands)

### Session Management
```bash
tokenade export         # Extract cookies from browser
tokenade load           # Load session into browser
tokenade sessions list  # List all sessions
tokenade sessions stats # Session statistics
tokenade session-diff   # Compare two sessions
tokenade validate       # Validate session integrity
tokenade validate-rules # Validate against custom rules
tokenade validate-session # Validate for CI/CD health gates
tokenade health         # Check session health
tokenade health-report  # Batch health report for CI/CD
tokenade diff           # Diff two sessions
tokenade merge          # Merge multiple sessions
tokenade rotate         # Rotate sessions
tokenade transfer       # Transfer session between browsers
tokenade extract        # Extract session (alias for export)
tokenade inject-profile # Inject session into browser profile
tokenade import         # Import from competitor format
tokenade versions       # Show session versions
tokenade rollback       # Rollback to previous version
```

### Stealth & Browser
```bash
tokenade stealth test   # 18-point detection test suite
tokenade stealth battle # Battle test against 5 detection sites
tokenade stealth report # Generate detection report
tokenade stealth deps   # Check stealth dependencies
tokenade launch         # Launch stealth browser with session
tokenade patch-chrome   # Binary patch Chrome for stealth
tokenade fingerprint    # Generate fingerprint
tokenade clone-profile  # Clone browser profile
```

### CloakBrowser
```bash
tokenade cloak info     # Show CloakBrowser status
tokenade cloak install  # Download CloakBrowser binary
tokenade cloak serve    # Start CDP server (cloakserve)
```

### Session Refresh
```bash
tokenade refresh        # Refresh session from source browser
tokenade refresh-browser # Refresh via undetectable browser
tokenade refresh-oauth  # Refresh OAuth2 tokens
tokenade encrypted-refresh # Refresh encrypted sessions
tokenade batch-refresh  # Refresh multiple sessions
tokenade oauth-config   # Configure OAuth settings
```

### Plugins
```bash
tokenade plugin list    # List installed plugins
tokenade plugin install # Install a plugin
tokenade plugin uninstall # Uninstall a plugin
tokenade plugin info    # Show plugin details
tokenade plugin search  # Search marketplace
tokenade plugin rate    # Rate a plugin (syncs to GitHub)
tokenade plugin ratings # View global ratings
tokenade plugin popular # Show popular plugins
tokenade plugin recent  # Show newest plugins
tokenade plugin categories # List categories
tokenade plugin verify  # Verify plugin integrity
tokenade plugin outdated # Show outdated plugins
tokenade plugin browse  # Generate HTML marketplace
tokenade plugin test    # Test a plugin
tokenade plugin enable  # Enable a plugin
tokenade plugin disable # Disable a plugin
tokenade plugin update  # Update plugins
tokenade plugin reload  # Reload a plugin
```

### Proxy & Network
```bash
tokenade proxy          # Start CDP reverse proxy
tokenade serve          # Serve session via HTTP
```

### Session Sharing
```bash
tokenade share          # Share session (URL, QR, email)
tokenade unshare        # Revoke shared session
tokenade sync           # Sync sessions across devices
```

### Encryption
```bash
tokenade encrypt        # Encrypt session file
tokenade decrypt        # Decrypt session file
tokenade rekey          # Re-encrypt with new key
```

### CI/CD & Fleet
```bash
tokenade ci run         # Run CI pipeline from tokenade.yml
tokenade ci init        # Create starter tokenade.yml
tokenade ci validate    # Validate tokenade.yml
tokenade ci lint        # Lint tokenade.yml
tokenade cicd           # Generate CI/CD workflow files
tokenade fleet status   # Show all containers/pods
tokenade fleet health   # Health check across fleet
tokenade fleet refresh  # Refresh all containers
tokenade fleet logs     # Get container logs
```

### Forensics
```bash
tokenade autopsy        # Analyze why a session died
```

### Container & Kubernetes
```bash
tokenade container start/stop/restart/status/logs/refresh/scale/cleanup/health/generate
tokenade k8s deploy/status/scale/logs/delete/pods
```

### TUI
```bash
tokenade tui            # Launch interactive terminal UI
```

### Other
```bash
tokenade setup          # Initial setup
tokenade config show/get/set # Manage configuration
tokenade monitor start/stop/status # Session monitoring
tokenade analytics report/cleanup # Session analytics
tokenade daemon start/stop/status # Background daemon
tokenade logs           # View logs
tokenade diff           # Diff sessions
tokenade deps check/install # System dependencies
tokenade batch-export   # Export multiple sessions
tokenade batch-load     # Load multiple sessions
tokenade completion     # Shell completion scripts
tokenade test           # Run built-in tests
tokenade mobile-import  # Import from mobile device
```
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

## What's New in v6.4

- **Plugin API v1.0** — All 20 plugins inherit from proper base classes (SessionRefreshPlugin, SiteHandlerPlugin, ProxyProviderPlugin, etc.)
- **API_VERSION checking** — Plugins declare API version, loader validates at load time
- **PluginResult** — Standard result type for all plugin methods
- **PluginConfig** — Config with JSON schema validation
- **Full Ecosystem Transfer** — .tokenade v3.0 format with per-origin localStorage + sessionStorage
- **CDP StorageExtractor** — Extract localStorage/sessionStorage via Chrome DevTools Protocol
- **Encryption at Export** — `--encrypt-password` flag encrypts .tokenade files at export time
- **Plugin-First Export** — Auto-discovers site handler plugins for extraction
- **ProxyProviderPlugin** — New base class for commercial proxy providers (AnyIP, BrightData, etc.)
- **NotificationPlugin** — New base class for notification providers (Slack, Discord, Email)
- **5165+ tests** — Comprehensive test coverage

## What's New in v6.3

- **Stealth modules consolidated** — `core/browser/stealth/` package (manager, launcher, cloak, backend)
- **CLI handlers split** — `cli/handlers/` with infrastructure, CI, misc modules
- **Test suite optimization** — pytest-xdist parallel execution (150s → 27s)

## What's New in v6.2

- **CloakBrowser Integration** — Stealth Chromium binary with 58 C++ patches as default backend
- **Session CI Runner** — `tokenade ci run` reads `tokenade.yml` for automated session validation
- **Fleet Management** — `tokenade fleet status|health|refresh|logs` across Docker/k8s containers
- **Session Forensics** — `tokenade autopsy -s session.tokenade` — root-cause analysis for dead sessions
- **Interactive TUI** — `tokenade tui` — marketplace browser, session manager, keyboard navigation

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
```

CloakBrowser (stealth Chromium with 58 C++ patches) is a core dependency. The binary (~200MB) auto-downloads on first use.

### Optional Dependencies

```bash
pip install tokenade[runtime]    # curl-cffi for TLS matching
pip install tokenade[enterprise] # ldap3 for LDAP/SSO
pip install tokenade[linux]      # secretstorage for Linux keyring
pip install 'tokenade[tui]'     # Interactive terminal UI (textual)
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
└── tests/                          # 5165+ tests
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
