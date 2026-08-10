# Tokenade Tutorials

Comprehensive, step-by-step tutorials covering every feature of Tokenade.

**Table of Contents**

1. [Tutorial 1: Getting Started](#tutorial-1-getting-started)
2. [Tutorial 2: CDP Proxy](#tutorial-2-cdp-proxy)
3. [Tutorial 3: Multi-Site Proxy](#tutorial-3-multi-site-proxy)
4. [Tutorial 4: Session Sync](#tutorial-4-session-sync)
5. [Tutorial 5: Dashboard](#tutorial-5-dashboard)
6. [Tutorial 6: Plugin Development](#tutorial-6-plugin-development)
7. [Tutorial 7: TLS Fingerprinting](#tutorial-7-tls-fingerprinting)
8. [Tutorial 8: Browser Extension](#tutorial-8-browser-extension)
9. [Tutorial 9: Forward Proxy](#tutorial-9-forward-proxy)
10. [Tutorial 10: Session Sharing](#tutorial-10-session-sharing)

---

## Tutorial 1: Getting Started

**Prerequisites**

- Python 3.10+
- A browser with active sessions (Firefox, Chrome, Brave, or Edge)
- Git (for cloning)

### Step 1: Install Tokenade

```bash
git clone https://codeberg.org/mihir0209/tokenade.git
cd tokenade
pip install -e ".[dev]"
playwright install chromium --with-deps
```

`curl-cffi` is a core dependency (TLS fingerprint matching is built-in).

### Step 2: Discover Browser Profiles

List all browser profiles Tokenade can find:

```bash
tokenade export --list-profiles
```

Expected output:

```
📦 Discovered Browser Profiles:

  firefox:
    • default — /home/user/.mozilla/firefox/xxxx.default
    • dev-edition — /home/user/.mozilla/firefox/xxxx.dev-edition

  chrome:
    • Default — /home/user/.config/google-chrome/Default
    • Profile 1 — /home/user/.config/google-chrome/Profile 1
```

### Step 3: Export Your First Session

Export a ChatGPT session from Firefox:

```bash
tokenade export \
  --browser-name firefox \
  --domains "chatgpt.com,openai.com" \
  -o chatgpt.tokenade
```

Expected output:

```
📂 Extracting cookies from firefox...
   Browser path: /home/user/.mozilla/firefox/xxxx.default
   Domains: chatgpt.com, openai.com
   ✅ Extracted 24 cookies

📦 Session packaged:
   Site: chatgpt
   Cookies: 24
   TLS Profile: chrome120
   Fingerprint: collected
   Output: chatgpt.tokenade
```

### Step 4: Check Session Health

```bash
tokenade health -s chatgpt.tokenade
```

Expected output:

```
🩺 Session Health: chatgpt.tokenade

   Overall: 92% (Healthy)
   Total cookies: 24
   ├── Healthy: 20
   ├── Expiring soon: 3
   └── Expired: 1

   Critical cookies: 8/8 present
   Next expiry: 6h 23m
```

### Step 5: Start the Proxy

```bash
tokenade proxy -s chatgpt.tokenade
```

Expected output:

```
============================================================
Tokenade CDP Proxy Server
============================================================
Site: chatgpt
Cookies: 24
TLS Profile: chrome120
Browser: Chromium (Playwright)
Headless: True
Default URL: https://chatgpt.com

GUI: http://127.0.0.1:9222
============================================================
```

### Step 6: Browse

Open `http://127.0.0.1:9222` in your browser, enter a URL (e.g., `https://chatgpt.com`), and click Browse. You are now browsing as the donor user.

### Step 7: View Your Sessions

List all exported session files:

```bash
tokenade sessions list -d .
```

Expected output:

```
📦 Sessions in ./

  Site          Cookies  Browser  Health  File
  ────────────  ───────  ───────  ──────  ──────────────────
  chatgpt       24       firefox  92%     chatgpt.tokenade
```

### Common Issues

| Issue | Solution |
|-------|----------|
| `No browser profiles found` | Run your browser at least once so it creates a profile directory |
| `Session file not found` | Check the file path and ensure the export succeeded |
| `Port 9222 already in use` | Use `--port 9223` or kill the existing process: `lsof -ti:9222 \| xargs kill` |

---

## Tutorial 2: CDP Proxy

The CDP (Chrome DevTools Protocol) proxy is Tokenade's recommended mode. It launches a real Chromium browser, intercepts all requests via `page.route()`, and forwards them through curl-cffi with the donor's TLS fingerprint.

**Prerequisites**

- Tokenade installed with Playwright (`playwright install chromium`)
- A `.tokenade` session file

### Basic Usage

```bash
tokenade proxy -s my_session.tokenade
```

Open `http://127.0.0.1:9222` and enter the target URL.

### Stealth Mode

The CDP proxy applies comprehensive stealth scripts automatically:

- `navigator.webdriver` removed
- Chrome DevTools Protocol detection bypassed
- Automation indicators stripped
- Plugin/webgl metadata patched
- Network-level automation blocked (`BLOCKED_NETWORKS`)

No configuration needed — stealth is applied by default.

### Visible Browser Mode

Launch with a visible Chromium window for debugging:

```bash
tokenade proxy -s my_session.tokenade --visible
```

### Auto-Navigate to Site

Skip the GUI and navigate directly to the target site:

```bash
tokenade proxy -s my_session.tokenade --auto-navigate
```

Or specify a custom URL:

```bash
tokenade proxy -s my_session.tokenade --target-url "https://chatgpt.com"
```

### TLS Fingerprint Matching

Enable curl-cffi TLS fingerprint matching (results vary by site; not guaranteed):

```bash
tokenade proxy -s my_session.tokenade --fingerprint
```

Impersonate a specific browser version:

```bash
tokenade proxy -s my_session.tokenade --fingerprint --impersonate chrome120
```

### Playwright Connection

The proxy exposes a CDP endpoint on `port + 1` (default `9223`) for external Playwright connections:

```python
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9223")
    context = browser.contexts[0]
    page = await context.new_page()
    await page.goto("https://example.com")
```

### Request Timeout

Adjust the request timeout (default: 30 seconds):

```bash
tokenade proxy -s my_session.tokenade --timeout 60
```

### Auto-Refresh from Source Browser

Automatically refresh cookies from the source browser when they expire:

```bash
tokenade proxy -s my_session.tokenade \
  --auto-refresh \
  --source-browser firefox \
  --source-profile default
```

### Custom Port

```bash
tokenade proxy -s my_session.tokenade --port 8080
```

Bind to all interfaces (for Docker):

```bash
tokenade proxy -s my_session.tokenade --host 0.0.0.0 --port 9222
```

### Python API

Use the CDP proxy programmatically:

```python
import asyncio
from tokenade.core.proxy.cdp_proxy import CDPProxy, CDPProxyConfig

async def main():
    config = CDPProxyConfig(
        port=9222,
        host="127.0.0.1",
        headless=True,
        timeout=30,
    )
    proxy = CDPProxy.from_session_file("my_session.tokenade", config)
    await proxy.start()

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await proxy.stop()

asyncio.run(main())
```

### Common Issues

| Issue | Solution |
|-------|----------|
| `Chromium browser not found` | Run `playwright install chromium` |
| `Chromium launch timed out` | Try `--visible` mode or check system resources |
| `CDP injection failed` | Restart the proxy; the browser context may be stale |
| `cf_clearance` blocked | Use `--fingerprint` to enable TLS matching |

---

## Tutorial 3: Multi-Site Proxy

Serve multiple `.tokenade` sessions from one command with a tabbed GUI.

**Prerequisites**

- Multiple `.tokenade` session files
- Tokenade installed with Playwright

### Serve All Sessions in a Directory

```bash
tokenade proxy --all --sessions-dir ./sessions/
```

This loads every `.tokenade` file in `./sessions/` and serves each on its own port.

### Serve Specific Sessions

```bash
tokenade proxy --all \
  -s session1.tokenade \
  -s session2.tokenade \
  -s session3.tokenade
```

### Master GUI

The multi-site proxy runs a master GUI on the base port (default `9222`):

```
============================================================
Tokenade Multi-Site Proxy
============================================================
Master GUI: http://127.0.0.1:9222
Sessions: 3

  - gmail: 42 cookies -> port 9223
  - github: 18 cookies -> port 9224
  - chatgpt: 24 cookies -> port 9225

============================================================
```

Open `http://127.0.0.1:9222` to see tabs for each session. Click a tab to switch between sites.

### SharedConnectionPool

All proxy instances share a single `aiohttp.ClientSession` via `SharedConnectionPool`:

- **Max connections**: 200 (across all sites)
- **Max per host**: 50
- **Connection reuse**: TCP connections are reused across sites

This reduces file descriptor usage and improves performance when serving many sites.

### Custom Base Port

```bash
tokenade proxy --all --sessions-dir ./sessions/ --port 8000
```

Sessions are served on `8001`, `8002`, `8003`, etc.

### API Endpoint

The master GUI exposes a JSON API:

```bash
curl http://127.0.0.1:9222/api/sessions
```

Returns:

```json
[
  {
    "index": 0,
    "site_name": "gmail",
    "port": 9223,
    "cookies": 42,
    "auth_status": "logged_in"
  },
  {
    "index": 1,
    "site_name": "github",
    "port": 9224,
    "cookies": 18,
    "auth_status": "logged_in"
  }
]
```

### Common Issues

| Issue | Solution |
|-------|----------|
| `No session files found` | Ensure `.tokenade` files exist in the directory |
| Too many file descriptors | Increase ulimit: `ulimit -n 4096` |
| Browser crashes | Reduce sessions or increase system memory |

---

## Tutorial 4: Session Sync

The session sync daemon monitors browser cookie databases and auto-exports sessions when cookies change.

**Prerequisites**

- A running browser with active sessions
- Tokenade installed

### Add a Sync Target

Monitor Gmail cookies from Firefox:

```bash
tokenade sync add \
  --name gmail \
  --domains "google.com,accounts.google.com,mail.google.com" \
  --browser firefox
```

Monitor GitHub cookies from Chrome:

```bash
tokenade sync add \
  --name github \
  --domains "github.com,api.github.com" \
  --browser chrome \
  --profile "Default"
```

### List Sync Targets

```bash
tokenade sync list
```

Expected output:

```
🔄 Sync Targets:

  Name      Browser   Domains                              Output Dir
  ────────  ────────  ────────────────────────────────────  ──────────────────
  gmail     firefox   google.com,accounts.google.com,...   ~/.tokenade/synced
  github    chrome    github.com,api.github.com            ~/.tokenade/synced
```

### Run One-Time Sync

Check all targets once and export if changed:

```bash
tokenade sync once
```

### Start the Sync Daemon

Run the daemon in the background, checking every 60 seconds:

```bash
tokenade sync start --interval 60
```

The daemon uses file mtime (`os.stat`) to detect cookie database changes without reading the database on every check.

### Domain Filtering

Cookies are filtered to only include the specified domains:

```bash
tokenade sync add \
  --name social \
  --domains "twitter.com,x.com,facebook.com,instagram.com" \
  --browser firefox
```

Only cookies matching these domains are exported.

### Custom Output Directory

Export to a network share or specific path:

```bash
tokenade sync add \
  --name work-sessions \
  --domains "slack.com,notion.so" \
  --browser chrome \
  --output-dir /mnt/nas/tokenade-sessions
```

### Custom Output Filename

```bash
tokenade sync add \
  --name my-gmail \
  --domains "google.com" \
  --browser firefox \
  --output-dir ~/.tokenade/synced \
  --output-file gmail_auto.tokenade
```

### Stop the Daemon

```bash
# Find the daemon process
ps aux | grep "tokenade sync"

# Kill it
kill <PID>
```

### Config Persistence

Sync targets are saved to `~/.tokenade/sync/sync_config.json`:

```bash
# View config location
ls ~/.tokenade/sync/sync_config.json
```

Targets survive daemon restarts. Add targets, then start the daemon — it loads saved targets automatically.

### Python API

```python
from tokenade.core.importer.session_sync import SessionSyncDaemon, SyncTarget

daemon = SessionSyncDaemon()

daemon.add_target(SyncTarget(
    name="gmail",
    domains=["google.com", "accounts.google.com"],
    browser="firefox",
    output_dir="~/.tokenade/synced",
))

daemon.add_target(SyncTarget(
    name="github",
    domains=["github.com"],
    browser="chrome",
    output_dir="~/.tokenade/synced",
))

# Register callback
def on_sync(target_name, cookie_count):
    print(f"Synced {target_name}: {cookie_count} cookies")

daemon.on_sync(on_sync)

# Run once
daemon.check_once()

# Or run as daemon (blocking)
daemon.start(interval=60)
```

### Common Issues

| Issue | Solution |
|-------|----------|
| `No profile found` | Run the target browser at least once |
| `Extraction failed` | Quit browser (SQLite lock), use extension, CDP, or `tokenade convert` |
| Cookies not updating | Check that the browser is writing to the expected profile |

---

## Tutorial 5: Dashboard

The Tokenade dashboard provides a web-based UI for monitoring sessions, sync targets, and proxy status.

**Prerequisites**

- Tokenade running with at least one session loaded
- A web browser

### Open the Dashboard

Start the proxy with any session:

```bash
tokenade proxy -s my_session.tokenade
```

Open `http://127.0.0.1:9222` in your browser.

### Dashboard Layout

The dashboard has four tabs:

- **Sessions** — View all exported sessions with health scores
- **Sync** — Monitor sync targets and their status
- **Timeline** — Event history with timestamps
- **Diff** — Compare two sessions side by side

### Real-Time Updates

The dashboard auto-refreshes every 15 seconds and connects via WebSocket for real-time events:

- Session updates appear instantly
- Sync completions are logged
- Health changes trigger alerts

### Session Health View

Each session shows:

- **Health Score** — 0-100% based on cookie freshness
- **Cookie Count** — Total cookies in the session
- **Domains** — Domains included in the session
- **Last Modified** — Time since last export

Click **Details** on any session to see:

- Individual cookie health (healthy / warning / expired)
- Remaining time until expiry
- Issues detected (missing cookies, expired auth)

### Session Diff

Compare two sessions to see added, removed, and unchanged cookies:

1. Click the **Diff** tab
2. Select session A from the dropdown
3. Select session B from the dropdown
4. Click **Compare**

The diff shows:

- `+` Green rows: cookies present in B but not in A (added)
- `-` Red rows: cookies present in A but not in B (removed)
- Unchanged cookies are grayed out

### Quick Actions

- **Refresh All** — Reload all session data
- **Export Sessions** — Download all sessions as JSON
- **Run Sync** — Trigger an immediate sync for all targets
- **Compare Sessions** — Open the diff view

### Timeline

The timeline logs events with timestamps:

- Session exports
- Sync completions
- Errors and warnings

Filter by event type using the dropdown: All Events, Exports, Syncs, Errors.

Events are stored in `localStorage` (up to 200 events) and persist across page reloads.

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+R` | Refresh all data |
| `Escape` | Close detail/diff overlays |

### Common Issues

| Issue | Solution |
|-------|----------|
| `Cannot connect to Tokenade API` | Ensure the proxy is running |
| Dashboard shows no sessions | Run `tokenade export` to create session files |
| WebSocket disconnected | Check if the proxy is still running |

---

## Tutorial 6: Plugin Development

Extend Tokenade with custom handlers, export formats, and validators.

**Prerequisites**

- Tokenade installed
- Basic Python knowledge

### Plugin Types

| Type | Purpose |
|------|---------|
| `handler` | Custom cookie extraction and auth detection per site |
| `export_format` | Custom output formats for session export |
| `validator` | Custom health check rules |

### Plugin Location

Plugins are stored in `~/.tokenade/plugins/`. Each plugin is a directory with:

```
~/.tokenade/plugins/my-plugin/
├── plugin.json      # Manifest
├── handler.py       # Entry point (or exporter.py / validator.py)
└── ...
```

### Create a Site Handler Plugin

**Step 1: Create the directory**

```bash
mkdir -p ~/.tokenade/plugins/my-site-handler
```

**Step 2: Create `plugin.json`**

```json
{
  "name": "my-site-handler",
  "version": "1.0.0",
  "description": "Custom handler for my-site.com",
  "author": "Your Name",
  "type": "handler",
  "site_name": "my-site.com",
  "entry_point": "handler.py",
  "entry_class": "MySiteHandler"
}
```

**Step 3: Create `handler.py`**

```python
class MySiteHandler:
    """Custom handler for my-site.com."""

    def check_auth(self, cookies: list) -> bool:
        """Check if user is authenticated."""
        cookie_names = {c["name"] for c in cookies}
        return "session_id" in cookie_names and "user_token" in cookie_names

    def extract_tokens(self, cookies: list) -> list:
        """Extract auth tokens from cookies."""
        auth_cookies = ["session_id", "user_token", "csrf_token"]
        return [c for c in cookies if c["name"] in auth_cookies]

    def get_auth_status(self, cookies: list) -> str:
        """Get authentication status."""
        if self.check_auth(cookies):
            return "logged_in"
        return "logged_out"

    def get_critical_cookies(self) -> list:
        """List cookies required for authentication."""
        return ["session_id", "user_token"]
```

**Step 4: Test the plugin**

```bash
tokenade plugin list
tokenade plugin info my-site-handler
```

### Create an Export Format Plugin

**Step 1: Create the directory**

```bash
mkdir -p ~/.tokenade/plugins/my-exporter
```

**Step 2: Create `plugin.json`**

```json
{
  "name": "my-exporter",
  "version": "1.0.0",
  "description": "Custom export format",
  "author": "Your Name",
  "type": "export_format",
  "format_name": "my-format",
  "entry_point": "exporter.py",
  "entry_class": "MyExporter"
}
```

**Step 3: Create `exporter.py`**

```python
class MyExporter:
    """Custom export format."""

    def export(self, session: dict) -> str:
        """Export session to custom format."""
        cookies = session.get("cookies", [])
        lines = []
        for cookie in cookies:
            lines.append(f"{cookie['name']}={cookie['value']}")
        return "\n".join(lines)

    def get_content_type(self) -> str:
        """Return MIME type for this format."""
        return "text/plain"

    def get_file_extension(self) -> str:
        """Return file extension for this format."""
        return ".txt"
```

### Create a Validator Plugin

**Step 1: Create the directory**

```bash
mkdir -p ~/.tokenade/plugins/my-validator
```

**Step 2: Create `plugin.json`**

```json
{
  "name": "my-validator",
  "version": "1.0.0",
  "description": "Custom validation rules",
  "author": "Your Name",
  "type": "validator",
  "rule_name": "check-secure-cookies",
  "entry_point": "validator.py",
  "entry_class": "SecureCookieValidator"
}
```

**Step 3: Create `validator.py`**

```python
class SecureCookieValidator:
    """Validate that all cookies have Secure flag."""

    def validate(self, session: dict) -> dict:
        """Validate session and return results."""
        cookies = session.get("cookies", [])
        issues = []
        recommendations = []

        for cookie in cookies:
            if not cookie.get("secure"):
                issues.append(f"Cookie '{cookie['name']}' missing Secure flag")
            if not cookie.get("httpOnly"):
                recommendations.append(
                    f"Cookie '{cookie['name']}' could benefit from HttpOnly"
                )

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "recommendations": recommendations,
            "score": max(0, 100 - len(issues) * 10),
        }
```

### Plugin Management Commands

```bash
# List installed plugins
tokenade plugin list

# List available plugins from registry
tokenade plugin list --available

# Install from registry
tokenade plugin install example-plugin

# Uninstall
tokenade plugin uninstall example-plugin

# Show plugin details
tokenade plugin info my-site-handler
```

### Publishing Plugins

1. Create a GitHub repo with your plugin
2. Add a `plugin.json` manifest with correct metadata
3. Submit to the Tokenade plugin registry via PR
4. Users can then install with `tokenade plugin install your-plugin`

### Best Practices

- Keep plugins focused — one site or one format per plugin
- Handle missing cookies gracefully
- Add error handling for edge cases
- Document your plugin's purpose and usage
- Test with `tokenade health` after creating a handler

---

## Tutorial 7: TLS Fingerprinting

TLS fingerprinting matches the donor browser's TLS handshake (JA3 hash) so anti-bot systems see the original fingerprint instead of yours.

**Prerequisites**

- Tokenade installed (`pip install tokenade` — curl-cffi is a core dependency)
- A `.tokenade` session file with a `tls_profile`

### When to Use

| Scenario | Use TLS Fingerprinting? |
|----------|------------------------|
| Site behind Cloudflare | Yes |
| Site uses DataDome | Yes |
| No anti-bot protection | Not needed |
| cf_clearance cookie present | May break it — test carefully |

### Enable TLS Matching

```bash
tokenade proxy -s my_session.tokenade --fingerprint
```

### Impersonate a Specific Browser

Use the `--impersonate` flag to choose which browser TLS fingerprint to mimic:

```bash
# Chrome 120
tokenade proxy -s my_session.tokenade --fingerprint --impersonate chrome120

# Chrome 131
tokenade proxy -s my_session.tokenade --fingerprint --impersonate chrome131

# Firefox 128
tokenade proxy -s my_session.tokenade --fingerprint --impersonate firefox128

# Safari 17.0
tokenade proxy -s my_session.tokenade --fingerprint --impersonate safari17_0
```

### Available Impersonation Targets

| Target | Browser | Version |
|--------|---------|---------|
| `chrome120` | Chrome | 120 |
| `chrome124` | Chrome | 124 |
| `chrome131` | Chrome | 131 |
| `firefox128` | Firefox | 128 |
| `safari17_0` | Safari | 17.0 |
| `safari17_2_ios` | Safari iOS | 17.2 |

### Check Session TLS Profile

View the TLS profile in a session file:

```bash
tokenade health -s my_session.tokenade
```

The TLS profile is extracted from the source browser during export. If missing, the proxy defaults to Chrome 120.

### How It Works

```
Your Browser → Tokenade Proxy → curl-cffi (TLS matched) → Server

curl-cffi sends the TLS ClientHello with the same JA3 hash
as the donor browser, making the connection appear to come
from the original browser.
```

### Combining with Auto-Navigate

```bash
tokenade proxy -s my_session.tokenade \
  --fingerprint \
  --impersonate chrome131 \
  --auto-navigate \
  --target-url "https://example.com"
```

### Python API

```python
from tokenade.core.proxy.cdp_proxy import CDPProxy, CDPProxyConfig

config = CDPProxyConfig(
    port=9222,
    headless=True,
    use_fingerprint=True,
)
proxy = CDPProxy.from_session_file("my_session.tokenade", config)
proxy._auto_refresh_config["impersonate"] = "chrome131"

import asyncio
asyncio.run(proxy.start())
```

### Common Issues

| Issue | Solution |
|-------|----------|
| `curl-cffi not installed` | Reinstall: `pip install tokenade` (it is a core dependency) |
| `cf_clearance` blocked | Try without `--fingerprint` or use a different impersonation target |
| TLS mismatch errors | Ensure the session has a valid `tls_profile` |

---

## Tutorial 8: Browser Extension

The Tokenade browser extension provides one-click session export and proxy status monitoring.

**Prerequisites**

- Chrome or Firefox browser
- Tokenade installed

### Install the Extension

#### Chrome

1. Open `chrome://extensions/`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select the `extension/` directory

#### Firefox

1. Open `about:debugging#/runtime/this-firefox`
2. Click **Load Temporary Add-on**
3. Select `extension/manifest.json`

### Proxy Status Indicator

The extension shows a status indicator in the toolbar:

- **Green dot** — Proxy is running and connected
- **Red dot** — Proxy is not running
- **Yellow dot** — Proxy is starting or reconnecting

Click the extension icon to see:

- Current proxy port
- Number of cookies loaded
- Session health status
- Quick link to the dashboard

### Export History

The extension maintains an export history:

1. Click the extension icon
2. View recent exports with timestamps
3. Click any export to re-load it into the proxy
4. Clear history with the trash icon

### One-Click Export

1. Navigate to any supported site (GitHub, Discord, etc.)
2. Click the Tokenade extension icon
3. Click **Export Session**
4. The extension extracts cookies and creates a `.tokenade` file
5. The file is saved to your Downloads folder (or configured path)

### Extension Bridge

When the proxy is running, the extension connects via WebSocket on port `9224`:

```
Extension ←→ ws://127.0.0.1:9224 ←→ CDP Proxy
```

This enables:

- Real-time cookie updates from the extension
- Proxy status monitoring
- Session refresh notifications

### Configure Export Path

In the extension settings:

1. Click the extension icon
2. Click the gear icon
3. Set **Export Directory** (default: `~/Downloads`)
4. Set **Auto-export** toggle

### Common Issues

| Issue | Solution |
|-------|----------|
| Extension not connecting | Ensure the proxy is running on `127.0.0.1` |
| WebSocket error | Check port `9224` is not blocked |
| Export fails | Quit browser for CLI SQLite export; or use extension / `convert` |

---

## Tutorial 9: Forward Proxy

Use Tokenade as an HTTP forward proxy. All browser traffic goes through the proxy with donor cookies injected.

**Prerequisites**

- Tokenade installed
- A `.tokenade` session file

### Start Forward Proxy Mode

```bash
tokenade proxy -s my_session.tokenade --mode forward
```

Expected output:

```
🔒 Forward proxy ready on 127.0.0.1:9223
   Configure browser: HTTP_PROXY=http://127.0.0.1:9223
   Or: export http_proxy=http://127.0.0.1:9223
```

### Configure Your Browser

#### Firefox

1. Open **Settings** → **Network Settings**
2. Select **Manual proxy configuration**
3. HTTP Proxy: `127.0.0.1`, Port: `9223`
4. Enable **Also use this proxy for HTTPS**

#### Chrome

```bash
# Launch Chrome with proxy
google-chrome --proxy-server=http://127.0.0.1:9223
```

#### System-Wide (Linux)

```bash
export http_proxy=http://127.0.0.1:9223
export https_proxy=http://127.0.0.1:9223

# Or for a single command
curl -x http://127.0.0.1:9223 https://example.com
```

#### System-Wide (macOS)

```bash
export http_proxy=http://127.0.0.1:9223
export https_proxy=http://127.0.0.1:9223
```

### HTTP Tunneling (CONNECT)

The forward proxy supports HTTPS via CONNECT tunneling:

```
Client → CONNECT example.com:443 → Forward Proxy → Target Server
```

The proxy establishes a TCP tunnel and pipes data bidirectionally.

### Cookie Injection

For HTTP requests (not CONNECT tunnels), the proxy injects donor cookies:

```
GET /page HTTP/1.1
Host: example.com
Cookie: session=abc123; token=xyz789  ← Injected by proxy
```

### Custom Port

```bash
tokenade proxy -s my_session.tokenade --mode forward --port 8888
```

### Check Proxy Statistics

```python
# The proxy tracks stats in memory
# Restart the proxy to reset stats
```

### Python API

```python
import asyncio
from tokenade.core.proxy.forward_proxy import ForwardProxy

async def main():
    session = ...  # Load your session
    proxy = ForwardProxy(session, port=9223, host="127.0.0.1")
    await proxy.start()

asyncio.run(main())
```

### Common Issues

| Issue | Solution |
|-------|----------|
| `Connection refused` | Ensure the proxy is running on the correct port |
| HTTPS sites not loading | Verify CONNECT tunneling is enabled in your browser |
| Cookies not injected | Check that the session has cookies for the target domain |
| `502 Bad Gateway` | The target server may be unreachable; check DNS |

---

## Tutorial 10: Session Sharing

Share sessions securely with password protection, expiry, and revocation.

**Prerequisites**

- Tokenade installed
- A `.tokenade` session file

### Create a Share Link

```bash
tokenade share -s my_session.tokenade
```

Expected output:

```
🔗 Share link created:
   Session: my_session
   Link: https://tokenade.app/share/abc123def456
   Expires: 24 hours
   Uses: unlimited
```

### Password Protection

Add a password to the share link:

```bash
tokenade share -s my_session.tokenade --password my-secret-password
```

The recipient must enter the password to download the session.

### Set Expiry

Limit the link lifetime:

```bash
# Expires in 48 hours
tokenade share -s my_session.tokenade --expiry 48

# Expires in 1 hour
tokenade share -s my_session.tokenade --expiry 1
```

### Limit Uses

Restrict the number of downloads:

```bash
# Maximum 5 downloads
tokenade share -s my_session.tokenade --max-uses 5
```

### Generate QR Code

Create a QR code for mobile sharing:

```bash
tokenade share -s my_session.tokenade --format qr -o qr.png
```

Scan the QR code with a mobile device to download the session.

### Generate HTML Page

Create a standalone HTML page for sharing:

```bash
tokenade share -s my_session.tokenade --format html -o share.html
```

Open `share.html` in any browser to download the session.

### Share via Webhook (Slack/Discord)

Send the session to a Slack or Discord webhook:

```bash
tokenade share -s my_session.tokenade \
  --webhook https://hooks.slack.com/services/T00/B00/xxxx
```

### Revoke a Share

List all active shares:

```bash
tokenade unshare --list
```

Expected output:

```
🔗 Active Shares:

  ID            Site       Expires      Uses    Password
  ────────────  ─────────  ───────────  ──────  ────────
  abc123def456  gmail      2026-06-18   3/10    yes
  xyz789ghi012  github     2026-06-19   1/0     no
```

Revoke a specific share:

```bash
tokenade unshare abc123def456
```

### HMAC-SHA256 Signatures

Share links include HMAC-SHA256 signatures to prevent tampering:

- The signature is generated from the session data + a secret key
- Recipients can verify the session hasn't been modified
- Revoked sessions are checked against a revocation list

### Security Considerations

- Session files contain raw cookies — treat them like passwords
- Always use `--password` for sensitive sessions
- Set short `--expiry` times for temporary shares
- Use `--max-uses` to limit exposure
- Revoke shares immediately after use with `tokenade unshare`

### Common Issues

| Issue | Solution |
|-------|----------|
| `Session file not found` | Verify the file path is correct |
| Link expired | Create a new share link |
| QR code not generating | Install QR dependencies: `pip install qrcode[pil]` |
| Webhook failed | Check the webhook URL is valid and the service is reachable |

---

## Additional Resources

- [Quick Start Guide](TUTORIAL_GETTING_STARTED.md) — 3-step quick start
- [Plugin Development](TUTORIAL_PLUGIN_DEV.md) — Detailed plugin guide
- [Enterprise Deployment](TUTORIAL_ENTERPRISE.md) — Audit, RBAC, LDAP
- [API Reference](API.md) — REST API and Python SDK
- [Architecture](ARCHITECTURE.md) — System design and data flow
- [Troubleshooting](TROUBLESHOOTING.md) — Common issues and fixes
- [Site Configurations](SITE_CONFIGS.md) — Preset configs for popular sites
- [Security](SECURITY.md) — Security considerations
