# Tokenade v2.0 — Browser Session Portability Tool

Extract browser sessions from one device, package them into portable `.tokenade` files, and browse as the donor on another device using a **CDP reverse proxy** with TLS fingerprint matching.

## How It Works

```
Source Browser (Firefox/Chrome/Brave)
        │
        ▼
  tokenade export ──→ Extracts cookies ──→ .tokenade file
                                                   │
                                                   ▼
                                          tokenade proxy
                                                   │
                                    Launches Playwright Chromium
                                    Injects donor cookies
                                    page.route() intercepts ALL requests
                                    Forwards via curl-cffi (TLS matched)
                                                   │
                                                   ▼
                                        http://127.0.0.1:9222
                                        Open in any browser
                                        You are logged in as the donor
```

## Quick Start (3 commands)

### Step 1 — Export cookies from your browser

```bash
# See what browsers are installed
tokenade export --list-profiles

# Export ChatGPT session from Firefox default profile
tokenade export --browser-name firefox --domains "chatgpt.com,openai.com,cdn.openai.com" -o chatgpt.tokenade

# Export Gmail session from Firefox default profile
tokenade export --browser-name firefox --domains "google.com,accounts.google.com,mail.google.com" -o gmail.tokenade

# Export from Chrome instead
tokenade export --browser-name chrome --domains "google.com,accounts.google.com" -o gmail.tokenade

# Export from a specific profile
tokenade export --browser-name firefox --profile "2P8fh3oV.Profile 3" --domains "github.com" -o github.tokenade
```

### Step 2 — Start the proxy

```bash
# Start CDP proxy (default — recommended)
tokenade proxy -s chatgpt.tokenade

# Start on a custom port
tokenade proxy -s chatgpt.tokenade --port 8080

# Show the browser window (non-headless)
tokenade proxy -s chatgpt.tokenade --visible

# Use legacy service-worker proxy (not recommended)
tokenade proxy -s chatgpt.tokenade --legacy
```

### Step 3 — Browse

Open `http://127.0.0.1:9222` in your browser, enter the target URL, and click Browse.

## Full CLI Reference

### Export

```bash
tokenade export [options]

Options:
  --browser-name {chrome,firefox,edge,brave}
                        Browser to extract from
  --browser-path PATH   Custom path to browser profile directory
  --profile NAME        Profile name within browser (e.g. "Default", "Profile 1")
  --domains DOMAINS     Comma-separated domains to filter
                        (e.g. "google.com,accounts.google.com,mail.google.com")
  --site-config FILE    JSON site config file for domain filtering
  --output, -o FILE     Output file path (any extension, default: {site}_session.tokenade)
  --list-profiles       List all discovered browser profiles and exit
  --extract-local-storage   Also extract localStorage data
  --local-storage-origin ORIGIN   Origin to extract localStorage from
```

**Examples:**

```bash
# List profiles
tokenade export --list-profiles

# Export all cookies (no filtering)
tokenade export --browser-name firefox -o all_cookies.tokenade

# Export only google.com cookies
tokenade export --browser-name firefox --domains "google.com,accounts.google.com" -o gmail.tokenade

# Export from Chrome's default profile
tokenade export --browser-name chrome --domains "github.com" -o github.tokenade

# Export with fingerprint collection
tokenade export --browser-name firefox --domains "chatgpt.com" --collect-fingerprint -o chatgpt.tokenade
```

### Proxy

```bash
tokenade proxy -s SESSION_FILE [options]

Options:
  -s, --session FILE    Path to .tokenade session file (required)
  -p, --port PORT       Port to listen on (default: 9222)
  --host HOST           Host to bind to (default: 127.0.0.1)
  --visible             Show the Chromium browser window
  --no-open-browser     Don't auto-open the GUI in your browser
  --timeout SECONDS     Request timeout (default: 30)
  --legacy              Use legacy service-worker proxy instead of CDP
```

**Examples:**

```bash
# Basic usage
tokenade proxy -s chatgpt.tokenade

# Custom port, visible browser
tokenade proxy -s gmail.tokenade --port 8080 --visible

# Headless (default), custom timeout
tokenade proxy -s session.tokenade --timeout 60
```

### Inject Profile

```bash
# Inject cookies directly into a browser profile (bypasses proxy)
tokenade inject-profile -s session.tokenade --browser firefox --profile "nj40lj6y.default"

# Dry run (show what would be injected)
tokenade inject-profile -s session.tokenade --browser firefox --profile "nj40lj6y.default" --dry-run
```

### Encrypt / Decrypt

```bash
# Encrypt a session file
tokenade encrypt -s session.tokenade -o session.encrypted.tokenade

# Decrypt
tokenade decrypt -s session.encrypted.tokenade -o session.tokenade

# Change encryption password
tokenade rekey -s session.encrypted.tokenade
```

### Health Check

```bash
# Check if session cookies are still valid
tokenade health -s session.tokenade
```

## Architecture

```
tokenade/
├── core/
│   ├── proxy/
│   │   ├── cdp_proxy.py          # CDP proxy (recommended)
│   │   └── server.py             # Legacy SW proxy
│   ├── runtime/
│   │   ├── tls_matcher.py        # curl-cffi TLS fingerprint matching
│   │   └── engine.py             # CookieJar, FingerprintMatcher
│   ├── importer/
│   │   ├── browser_discovery.py  # Find browser profiles
│   │   ├── cookie_extractor.py   # Extract cookies from SQLite
│   │   ├── session_packager.py   # Package into .tokenade format
│   │   └── session_loader.py     # Load .tokenade into browser
│   ├── injector/
│   │   └── profile_manager.py    # Direct profile cookie injection
│   ├── crypto/
│   │   └── encryptor.py          # AES-256-GCM encryption
│   └── batch/
│       └── operations.py         # Batch export/load
├── cli.py                        # CLI entry point
├── handlers/                     # Site-specific handlers
│   ├── base.py                   # SiteHandler ABC and registry
│   └── google.py                 # Google handler
└── tests/                        # 361 tests
```

### CDP Proxy Architecture

The CDP proxy uses Playwright to launch a real Chromium browser. Every request the browser makes is intercepted via `page.route("**/*")` and forwarded through `curl-cffi` with the donor's TLS fingerprint. This means:

- **No URL rewriting** — the browser handles all URLs natively
- **No service worker injection** — not needed
- **No `<base>` tag injection** — not needed
- **Perfect rendering** — React, Next.js, SPAs all work
- **Sub-resources work** — fonts, analytics, API calls, CDN assets
- **TLS fingerprint matches** — curl-cffi impersonates Chrome's JA3 hash

## .tokenade File Format

```json
{
  "version": "2.0",
  "created_at": "2026-06-11T12:00:00Z",
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

## Security

- Session files contain raw cookies — treat like passwords
- Use `tokenade encrypt` to encrypt at rest
- The proxy runs on `127.0.0.1` only (not accessible from network)
- Cookies are injected into an isolated Playwright browser context

## Installation

```bash
git clone https://github.com/mihir0209/tokenade.git
cd tokenade
pip install -r requirements.txt
playwright install chromium
pip install -e .
```

## Development

```bash
pip install -e ".[dev]"
pytest                    # Run 361 tests
pytest -x -q             # Quick mode
```

## License

MIT License
