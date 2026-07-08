# Tokenade v6.4 — Browser Session Portability Tool

Extract browser sessions from one device, package them into portable `.tokenade` files, and browse as the donor on another device using a **CDP reverse proxy** with TLS fingerprint matching.

**Product focus:** session portability + TLS-matched replay — not a Multilogin replacement.

**~5250 automated tests** · **large CLI surface** · **22 official plugins (unverified)** · **stealth: measured, not “Grade A”**

> **Honesty policy:** This README separates **battle-tested** behavior from **code that exists but is not production-proven**. Overclaims were removed 2026-07-09. Deferred goals live in [`.agent/plans/2026-07-09-p0-honesty-deferred-claims.md`](.agent/plans/2026-07-09-p0-honesty-deferred-claims.md).

## What actually works (battle-tested)

Evidence: `.agent/working.md`, `.agent/testing-reports/2026-07-06-e2e-headless-test.md`, manual multi-device notes.

| Capability | Status | Notes |
|------------|--------|-------|
| Cookie export (Chrome/Firefox/Brave/Edge) | **Works** | SQLite extraction, domain filters |
| CDP proxy + session inject (Gmail, ChatGPT) | **Works** | Confirmed logged-in in real runs |
| localStorage transfer (Telegram Web) | **Works** | E2E headless 2026-07-06 |
| Google persistent cookies → CloakBrowser | **Works** | 171 cookies, login selectors matched |
| AES-256-GCM session file encryption | **Works** | Core `TokenadeEncryptor`, PBKDF2 600k |
| Session health scoring (cookie heuristics) | **Works** | Heuristic score — not a live auth proof |
| Forward proxy CONNECT | **Works** | Battle-tested 2026-06-17 |
| Multi-site proxy (2 sessions) | **Works** | Battle-tested 2026-06-17 |
| CloakBrowser as default stealth backend | **Works** | Prefer over pure JS patches |
| GitHub/Discord/Reddit from **session-only** Firefox cookies | **Often fails** | Auth cookies not always persisted to disk |
| Google Chrome→Chrome / multi-device | **Often fails** | DBSC + risk signals; see working notes |
| Cloudflare Turnstile / hard bot labs | **Often fails** | Battle suite ~Grade C (~78/100), not A |
| Enterprise LDAP / fleet / K8s generators | **Code present** | Not battle-tested as a product |
| Official plugin marketplace “ratings/downloads” | **Removed** | Were never real telemetry |

## Features

### Core (primary product)

| Feature | Description | Confidence |
|---------|-------------|------------|
| **Session Export** | Extract cookies from Chrome, Firefox, Brave, Edge; Safari/Tor/mobile available | High for desktop Chromium/Firefox |
| **Session Injection** | CDP proxy or direct profile modification | High for persistent-cookie sites |
| **TLS Fingerprint Matching** | `curl-cffi` impersonation on proxied requests | High when `tokenade[runtime]` installed |
| **localStorage Support** | Extract/inject localStorage (critical for Telegram) | High for Telegram; mixed for Discord |
| **Encryption** | AES-256-GCM via **core** encryptor only | High |
| **Session Refresh** | Cookie re-warm via headless browser; OAuth path exists | Medium (site-dependent) |
| **Health Scoring** | Heuristic cookie/auth scoring | Medium (not live site proof) |
| **Site Configs / plugins** | Domain + critical-cookie presets | Medium (configs/lists, not deep site engines) |

### Stealth (honest)

| Feature | Description | Confidence |
|---------|-------------|------------|
| **CloakBrowser** | Stealth Chromium backend (default when available) | High as launcher |
| **JS patch fallback** | Webdriver/plugins/WebGL/canvas/etc. when CloakBrowser unavailable | Best-effort |
| **Battle testing** | Multi-site detection suite with scores | Use scores; do not assume “undetectable” |
| **CAPTCHA / CF / Akamai helpers** | Detection + partial automation | Partial — not a guaranteed bypass product |
| **Humanize** | Mouse/keyboard timing helpers | Best-effort |

### Also present (code exists — not the sales pitch)

| Area | What exists | Caveat |
|------|-------------|--------|
| Advanced refresh/share/merge/rotate | CLI + modules | Prefer core loop first |
| Browser extension | MV3 export helper | Manual install; not a full product surface |
| Plugin marketplace | Install/search/TUI; 22 official plugins | Plugins **unverified**; many thin or core-overlapping |
| Profile / fingerprint / competitor import | Modules + CLI | Competitor parity is incomplete vs AdsPower/Multilogin |
| Enterprise (audit, RBAC, LDAP) | Modules + optional deps | Not production-hardened for multi-tenant ops |
| Fleet / K8s YAML / CI generators | CLI scaffolding | Generators ≠ managed platform |
| GitHub Actions CI for this repo | Present | Matrix lint/test |

### Browser support

| Browser | Status | Notes |
|---------|--------|-------|
| Chrome | Strong | SQLite extraction, profile discovery; binary patch experimental |
| Firefox | Strong | SQLite + LevelDB localStorage paths used in E2E |
| Edge / Brave | Strong | Chromium-based |
| Safari | Partial | macOS cookie parsing |
| Tor Browser | Available | Firefox-based profile discovery |
| Mobile (Android) | Available | Via ADB — less battle coverage than desktop |

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

| Feature | Tokenade (honest) | Browser Extensions | Simple cookie dump tools |
|---------|-------------------|--------------------|--------------------------|
| **CLI + portable `.tokenade` files** | Yes | Usually no | Partial |
| **TLS-matched CDP proxy** | Yes (needs `curl-cffi`) | No | No |
| **Multi-browser extract** | Yes (desktop strong) | Limited | Varies |
| **localStorage packaging** | Yes (Telegram proven) | Varies | Rare |
| **Encrypted session files** | Yes (core AES-GCM) | Rare | Rare |
| **Undetectable vs all bot labs** | **No — do not claim this** | No | No |
| **Full Multilogin replacement** | **No** | No | No |
| **Self-hosted** | Yes | N/A | Yes |

## What's New in v6.4

- **Plugin API v1.0/v1.1** — Base classes + PluginResult/PluginConfig
- **Full ecosystem transfer format** — `.tokenade` v3 storage.local / storage.session per origin
- **Encryption at export** — `--encrypt-password` uses core encryptor
- **Plugin-first export** — site handlers can drive domains/critical cookies
- **Honesty pass (2026-07-09)** — removed Grade A / fake plugin stats; single crypto path for session-encrypt plugin

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
pip install tokenade[enterprise] # ldap3 for LDAP/SSO (experimental)
pip install tokenade[linux]      # secretstorage for Linux keyring
pip install 'tokenade[tui]'     # Interactive terminal UI (textual)
# tokenade[runtime] still installs curl-cffi (now also a core dependency)
```

**Note:** `curl-cffi` is a **core** dependency (P1). TLS-matched proxy fails closed if it is missing (broken install), instead of silently degrading.

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
└── tests/                          # large automated suite (~5250 tests; not a quality grade)
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
