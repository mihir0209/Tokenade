# Tokenade User Guide

Browser session portability — extract, transfer, and inject logged-in states across machines and browsers.

## Installation

```bash
pip install tokenade
```

Verify:

```bash
tokenade --version
# tokenade 1.1.77
```

This guide was verified against the published PyPI package `tokenade==1.1.77`, not an editable source checkout.

## Quick Start

```bash
# 1. Export from Firefox
tokenade export --browser-name firefox --domains "google.com,accounts.google.com" -o google.tokenade

# 2. Transfer the .tokenade file to another machine
scp google.tokenade user@newmachine:~/

# 3. Load into a stealth browser on the new machine
tokenade load --file google.tokenade
```

## Commands

### `tokenade export`

Extract cookies (and optionally localStorage) from a browser into a `.tokenade` file.

```bash
# Basic export — cookie-only sites
tokenade export --browser-name firefox --domains "github.com" -o github.tokenade

# Export with plugin (required for hard sites like Discord, Telegram)
tokenade export --browser-name firefox --plugin discord-handler -o discord.tokenade

# List available handlers
tokenade export --list-handlers

# List browser profiles found on your system
tokenade export --list-profiles
```

**`--list-handlers` output:**

```
🔌 Available site handlers (12):

   discord v1.2.0 — Site handler for Discord (discord.com, discordapp.com)
   generic v2.0.0 — Multi-site handler: cookie-simple sites via sites/*.json
   google-flow v1.0.3 — OAuth automation for labs.google/fx/tools/flow
   generic_oauth v1.0.0 — Generic OAuth2 authorization code flow with PKCE
   telegram v1.1.0 — Site handler for Telegram Web (auth in localStorage)
   ...
```

**`--list-profiles` output:**

```
📁 Found 5 profile(s):

   Browser: firefox
   Profile: default
   Path: /home/user/snap/firefox/common/.mozilla/firefox/xxxx.default

   Browser: brave
   Profile: Default
   Path: /home/user/.config/BraveSoftware/Brave-Browser/Default
```

### `tokenade load`

Load a `.tokenade` session file into a browser (CloakBrowser by default).

```bash
# Headless (default)
tokenade load --file session.tokenade

# Visible window
tokenade load --file session.tokenade --visible

# With validation after injection
tokenade load --file session.tokenade --validate

# With specific stealth level
tokenade load --file session.tokenade --stealth-level maximum
```

### `tokenade validate`

Validate session files in a directory.

```bash
tokenade validate -d ~/sessions/
```

**Output:**

```
================================================================================
TOKENADE - Session Validation
================================================================================

📁 Checking: chatgpt.tokenade
   ✅ 33 cookies
   ✅ Status: logged_in

📁 Checking: discord.tokenade
   ✅ 9 cookies
   ✅ Status: logged_in

📁 Checking: github.tokenade
   ✅ 9 cookies
   ✅ Status: logged_in

📁 Checking: google.tokenade
   ✅ 177 cookies
   ✅ Status: logged_in

📁 Checking: telegram.tokenade
   ⚠️  No cookies
   ⚠️  Status: logged_out

📊 Summary: 6 valid, 1 invalid
```

### `tokenade health`

Check session health with scoring.

```bash
# Single session
tokenade health -s session.tokenade

# All sessions in a directory
tokenade health -d ~/sessions/
```

**Output:**

```
================================================================================
TOKENADE - Session Health Check
================================================================================

📁 Checking: discord-fixed.tokenade
Status: ✅ HEALTHY
Health Score: 100.0%

📁 Checking: discord.tokenade
Status: ❌ UNHEALTHY
Health Score: 88.9%
Issues:
  • 1 expired cookies
Recommendations:
  • Re-export session from browser

📁 Checking: github.tokenade
Status: ✅ HEALTHY
Health Score: 100.0%

📁 Checking: google.tokenade
Status: ❌ UNHEALTHY
Health Score: 99.4%
Issues:
  • 1 expired cookies

================================================================================
SUMMARY: 2 healthy, 5 unhealthy
```

### `tokenade encrypt` / `tokenade decrypt`

Encrypt a session file for safe transport.

```bash
# Encrypt
tokenade encrypt -i session.tokenade -o session.tokenade.enc -p "my-secret"

# Decrypt
tokenade decrypt -i session.tokenade.enc -o session.tokenade -p "my-secret"
```

**Output:**

```
✅ Encrypted successfully
   Output: session.tokenade.enc
   Size: 55216 -> 55282 bytes

✅ Decrypted successfully
   Output: session.tokenade
   Size: 55282 -> 55216 bytes
```

### `tokenade sessions`

Manage multiple sessions.

```bash
# List all sessions in a directory
tokenade sessions list -d ~/sessions/
```

**Output:**

```
======================================================================
Site                 Cookies    Browser      Size       Path
======================================================================
discord              7          firefox      3.0K       discord-fixed.tokenade
discord              9          firefox      53.9K      discord.tokenade
github               9          firefox      2.9K       github.tokenade
google               177        firefox      62.5K      google.tokenade
openai               33         firefox      18.1K      chatgpt.tokenade
unknown              2          firefox      22.6K      telegram_web.tokenade
unknown              0          firefox      22.1K      telegram.tokenade

======================================================================
Total: 7 sessions
======================================================================
```

### `tokenade recommend`

Get recommendations for which plugin, browser, and site to use.

```bash
# By URL
tokenade recommend --url https://discord.com

# By session file
tokenade recommend --session discord.tokenade
```

**Output:**

```
  site:     discord
  plugin:   discord-handler
  browser:  cloak
  confidence: 0.80

  reasons:
    - site matched from URL host: 'https://discord.com'
    - plugin = 'discord-handler' (site_config.preferred_plugin)
    - browser = 'cloak'
    - per-site override (discord -> cloak)
```

### `tokenade diff`

Compare two session files.

```bash
tokenade diff session_a.tokenade session_b.tokenade
```

**Output:**

```
======================================================================
SESSION COMPARISON
======================================================================

  A: /path/to/discord.tokenade
  B: /path/to/discord-fixed.tokenade

  ──────────────────────────────────────────────────
  Cookies only in A: 1
  Cookies modified: 3
  Metadata differences: ['created_at']
```

### `tokenade plugin`

Manage site handler plugins.

```bash
# List installed plugins
tokenade plugin list

# Test a plugin's contract
tokenade plugin test discord-handler

# Install a plugin
tokenade plugin install discord-handler

# Install all official plugins
tokenade plugin sync

# Search marketplace
tokenade plugin search telegram
```

Recommended first-time setup:

```bash
rm -rf ~/.tokenade/plugins
tokenade plugin sync
tokenade plugin list
```

If GitHub's `main` raw-content cache is stale immediately after a marketplace update, add a pinned GitHub registry for the current commit and install from it:

```bash
tokenade plugin registry add github-current \
  https://raw.githubusercontent.com/mihir0209/tokenade-plugins/<commit-sha>

tokenade plugin install discord-handler --registry github-current
```

**`plugin list` output:**

```
📦 Installed plugins:
   • auto-refresh v1.2.0 (session_refresh) — CloakBrowser live session revalidation
   • bulk-export v1.0.0 (export_format) — Export all sessions from all browsers
   • cookie-export v1.1.0 (export_format) — Multi-format cookie export
   • discord-handler v1.2.0 (handler) — Site handler for Discord
   • generic-handler v2.0.0 (handler) — Multi-site handler: chatgpt, github, google, reddit
   • google-flow-handler v1.0.3 (handler) — OAuth automation for labs.google
   • oauth-flow-handler v1.0.0 (handler) — Generic OAuth2 with PKCE
   • oauth2 v1.2.0 (session_refresh) — OAuth2 token refresh
   • proxy-health v1.0.0 (proxy) — Monitor proxy health
   • proxy-rotate v1.1.0 (proxy) — Rotating proxy support
   • session-backup v1.0.1 (handler) — Auto-backup with rotation
   • session-encrypt v1.2.0 (session_refresh) — AES-256-GCM encryption
   • session-expiry-alert v1.0.0 (notification) — Expiry alerts
   • session-merge v1.0.0 (handler) — Merge duplicate sessions
   • session-share v1.1.0 (session_refresh) — Encrypted URL/QR sharing
   • telegram-handler v1.1.0 (handler) — Site handler for Telegram Web
   • webhook-notify v1.2.0 (notification) — Webhook notifications

📦 Loaded 17/17 plugins
```

**`plugin test` output:**

```
Results: 10 passed, 0 failed
```

### `tokenade cloak`

CloakBrowser stealth browser management.

```bash
# Show CloakBrowser status
tokenade cloak info

# Install/update CloakBrowser binary
tokenade cloak install
```

**`cloak info` output:**

```
============================================================
CLOAKBROWSER STATUS
============================================================
  Package installed: Yes
  Binary installed:  Yes
  Binary version:    146.0.7680.177.5
  Platform:          linux-x64
  License tier:      free
  Binary path:       /home/user/.cloakbrowser/chromium-146.0.7680.177.5/chrome
============================================================
```

### `tokenade dashboard`

Start a web-based monitoring dashboard for sessions.

```bash
# Start dashboard server
tokenade dashboard start --port 8080

# Start with authentication
tokenade dashboard start --port 8080 --require-auth --username admin --password secret

# Start with HTTPS
tokenade dashboard start --port 8443 --ssl-certfile cert.pem --ssl-keyfile key.pem

# Check dashboard status
tokenade dashboard status

# List sessions via API
tokenade dashboard sessions
```

The dashboard provides:
- Real-time session health monitoring
- Session management (view, validate, delete)
- Auto-refresh UI
- REST API for integration
- Authentication and HTTPS support

### `tokenade vault`

Secure encrypted storage for sessions with key rotation.

```bash
# Store a session
tokenade vault store /path/to/session.tokenade --name "twitter-fresh"

# Retrieve a session
tokenade vault retrieve "twitter-fresh" --output retrieved.tokenade

# List stored sessions
tokenade vault list

# Delete a session
tokenade vault delete "twitter-fresh"

# Rotate encryption key
tokenade vault rotate-key

# Backup vault
tokenade vault backup --output vault-backup.tar.gz

# Restore vault
tokenade vault restore --input vault-backup.tar.gz
```

Sessions are encrypted with AES-256-GCM. The vault supports key rotation without data loss.

### `tokenade sync-remote`

Sync sessions to/from a remote machine via SSH/SCP.

```bash
# Check sync status
tokenade sync-remote status --remote-host user@remote --remote-path ~/.tokenade/sessions

# Push sessions to remote
tokenade sync-remote push --remote-host user@remote --remote-path ~/.tokenade/sessions

# Pull sessions from remote
tokenade sync-remote pull --remote-host user@remote --remote-path ~/.tokenade/sessions

# Bidirectional sync
tokenade sync-remote bidirectional --remote-host user@remote --remote-path ~/.tokenade/sessions

# With conflict resolution
tokenade sync-remote push --remote-host user@remote --remote-path ~/.tokenade/sessions --conflict remote-wins
```

Conflict resolution strategies:
- `local-wins`: Local version takes precedence
- `remote-wins`: Remote version takes precedence
- `newer-wins`: Most recently modified version wins
- `manual`: Skip conflicts for manual resolution

### `tokenade share-url` (canonical)

Create password-protected share links for sessions. The password never leaves
the machine. Ciphertext may be stored on the public Supabase project (or your
own) so peers can retrieve by short id. Small sessions also get a full
`tokenade://share/<id>?data=…` URL for offline peer share; large sessions
skip the embed (remote short-id only, or fail if remote is off / over size).
`tokenade://` is CLI/TUI-only (not a browser protocol).

```bash
# Create (public remote by default when available)
tokenade share-url create /path/to/session.tokenade --password "MySecurePassword123!"

# Create with expiry / max uses (--expiry is hours; not --expiry-hours)
tokenade share-url create /path/to/session.tokenade --password "MySecurePassword123!" --expiry 24 --max-uses 5

# Status of remote (limits, public vs private)
tokenade share-url status

# Offline-only create (no Supabase; needs small enough payload to embed)
tokenade share-url create session.tokenade --password "..." --no-remote

# Private project override
tokenade share-url create session.tokenade --password "..." \
  --supabase-url https://xxxx.supabase.co --supabase-key sb_publishable_...

# Retrieve (short id or full URL)
tokenade share-url retrieve <share_id> --password "MySecurePassword123!" -o session.tokenade

# List / revoke / cleanup (local share index; cleanup also strips oversized embeds)
tokenade share-url list
tokenade share-url revoke <share_id>
tokenade share-url cleanup
```

**Public remote limits (server-side):** max ciphertext ~2M chars; 30 creates/IP/hour;
expiry capped at 7 days; `max_uses` 1–50 (`0` becomes `10` on public store).
Prefer site-scoped exports (`--domains`) over full-profile dumps for sharing.

Private Supabase setup (OSS): copy `.env.example` → `.env`, set `DATABASE_URL`,
then `python3 scripts/apply_supabase_schema.py` and optionally `--verify`.
TUI Share tab: remote status, offline toggle, list/revoke/cleanup.

Features:
- Password-protected encrypted sharing (PBKDF2 + Fernet)
- Short-id via Supabase RPCs (public default or private project)
- Full URL offline embed (`?data=`) when payload is small enough
- Automatic expiration, use limits, and local store compaction

### Enterprise Features

Tokenade includes enterprise-grade security and compliance features.

#### RBAC (Role-Based Access Control)

```python
from tokenade.core.enterprise.auth import RBACManager, Role

# Create roles
rbac = RBACManager()
rbac.create_role("admin", permissions=["read", "write", "delete", "manage_users"])
rbac.create_role("user", permissions=["read", "write"])
rbac.create_role("viewer", permissions=["read"])

# Assign roles
rbac.assign_role("alice", "admin")
rbac.assign_role("bob", "user")
```

#### Encrypted Audit Logging

```python
from tokenade.core.enterprise.encrypted_audit import EncryptedAuditLogger

audit = EncryptedAuditLogger()

# Log an event
audit.log(
    user_id="alice",
    action="export",
    resource="session",
    resource_id="twitter-fresh",
    details={"browser": "firefox", "cookies": 113},
    success=True,
)

# Query logs
entries = audit.query(user_id="alice", action="export")
for entry in entries:
    print(f"  {entry['timestamp']}: {entry['action']} on {entry['resource']}")

# Rotate encryption key
audit.rotate_key()
```

Audit logs are encrypted with AES-256-GCM and support key rotation.

### `tokenade launch`

Launch a browser with session injection.

```bash
# Launch CloakBrowser (default)
tokenade launch

# Launch with session injection
tokenade launch --session session.tokenade

# Launch visible with a specific URL
tokenade launch --visible --url https://discord.com
```

### `tokenade test`

Run portability tests against a session file.

```bash
tokenade test -s session.tokenade
```

`tokenade test` uses saved browser fingerprints. If no default fingerprint exists yet, the command resolves the handler correctly but reports the missing fingerprint:

```
⚠️  Using legacy handler DiscordSiteHandlerLegacyHandler (prefer site plugins + site_config.json for new work)
PORTABILITY TEST REPORT
Total Tests: 1
   Error: Target fingerprint not found: default
```

Create or collect a fingerprint first:

```bash
tokenade fingerprint collect --name default --profile-dir <browser-profile-dir>
tokenade test -s session.tokenade --target-fp default
```

### Other Commands

| Command | Description |
|---------|-------------|
| `tokenade inject-profile` | Inject cookies directly into browser profile |
| `tokenade refresh` | Refresh session from source browser |
| `tokenade batch-export` | Export multiple sites at once |
| `tokenade batch-load` | Load multiple sessions |
| `tokenade share-url` | **Canonical** password share (create/retrieve/revoke/list/cleanup/status) |
| `tokenade share` | Legacy share link / QR (prefer `share-url`) |
| `tokenade unshare` | Legacy revoke (prefer `share-url revoke`) |
| `tokenade import` | Legacy import from URL (prefer `share-url retrieve`) |
| `tokenade proxy` | Start CDP proxy with donor session |
| `tokenade monitor` | Monitor session health in real-time |
| `tokenade analytics` | Session usage analytics |
| `tokenade completion` | Generate shell completion scripts |
| `tokenade refresh-oauth` | Refresh OAuth tokens |
| `tokenade daemon` | Auto-refresh daemon (background) |
| `tokenade versions` | Session versioning |
| `tokenade rollback` | Rollback session to a version |
| `tokenade logs` | View structured logs |
| `tokenade serve` | Start API server |

## Plugin Types

| Type | Description | Example |
|------|-------------|---------|
| `handler` | Site-specific extraction/injection | discord-handler, telegram-handler |
| `session_refresh` | Token refresh logic | auto-refresh, oauth2, session-encrypt |
| `notification` | Expiry alerts, webhooks | session-expiry-alert, webhook-notify |
| `proxy` | Proxy rotation, health | proxy-health, proxy-rotate |
| `export_format` | Custom export formats | bulk-export, cookie-export |

## Configuration

Config file: `~/.tokenade/config.json`

```json
{
  "automation_browser": "cloak",
  "default_browser": "firefox",
  "plugin_dir": "~/.tokenade/plugins",
  "supabase_use_default": true,
  "supabase_url": "",
  "supabase_anon_key": ""
}
```

## Supported Sites

### Cookie-Simple (via `generic-handler`)

- ChatGPT / OpenAI
- GitHub
- Google (basic export)
- Reddit

### Hard Sites (dedicated handlers)

- **Discord** (`discord-handler` v1.2.0) — uses localStorage token
- **Telegram** (`telegram-handler` v1.1.0) — uses localStorage auth keys

### OAuth Sites

- Google OAuth (`google-flow-handler` v1.0.3)
- Generic OAuth2 (`oauth-flow-handler` v1.0.0)

## Troubleshooting

### Common Errors

**"Browser is running" error during export:**
```bash
# Close the browser first, then export
tokenade export --browser-name firefox --domains "google.com" -o gmail.tokenade
```

**Plugin not found:**
```bash
tokenade plugin install <plugin-name>
# Or install all official plugins
tokenade plugin sync
```

**Session marked unhealthy:**
Re-export from the browser. Expired cookies reduce health score.

**Handler not found for site:**
```bash
tokenade recommend --url https://yoursite.com
```
This tells you which plugin to install.

**Textual not installed (TUI):**
```bash
pip install 'tokenade[tui]'
```

**CloakBrowser not found:**
```bash
tokenade cloak install
```

**pymobiledevice3 not available (iOS):**
```bash
pip install pymobiledevice3
# Requires macOS with device connected
```

**SSH connection refused during sync-remote:**
```bash
# Ensure SSH server is running on remote
sudo systemctl status sshd
# Test connection manually
ssh user@remote-host echo "connected"
```

**Vault key rotation fails:**
```bash
# Ensure you have write permission to vault directory
ls -la ~/.tokenade/vault/
# Check vault integrity
tokenade vault list
```

**Dashboard won't start:**
```bash
# Check if port is in use
lsof -i :8080
# Use a different port
tokenade dashboard start --port 9090
```

**Share-url password too short:**
```bash
# Default minimum is 8 characters
tokenade share-url create session.tokenade --password "long-password-here"
```

**Share payload too large / short id won't retrieve:**
```bash
# Prefer site-scoped export, then share
tokenade export --browser-name firefox --domains "example.com" -o site.tokenade
tokenade share-url create site.tokenade --password "long-password-here"
tokenade share-url status   # check remote + limits
```

### Debug Mode

Enable verbose logging:
```bash
tokenade -v export --browser-name firefox --domains "google.com" -o gmail.tokenade
```

### Log Files

Check logs for detailed error information:
```bash
# View recent logs
ls ~/.tokenade/logs/
# Or use the logs command
tokenade logs --tail 50
```

## Python API

### Basic Usage

```python
from tokenade.core.recommend import recommend_site, recommend_plugin, recommend_browser

# Get recommendation
result = recommend_site(url="https://discord.com")
print(result.site)       # "discord"
print(result.plugin)     # "discord-handler"
print(result.browser)    # "cloak"
```

### Vault Operations

```python
from tokenade.core.vault.vault import SessionVault

vault = SessionVault()

# Store a session
vault.store("twitter.tokenade", name="twitter-fresh")

# Retrieve a session
vault.retrieve("twitter-fresh", output_path="retrieved.tokenade")

# List stored sessions
sessions = vault.list_sessions()

# Rotate encryption key
vault.rotate_key()
```

### Session Analytics

```python
from tokenade.core.analytics.engine import AnalyticsEngine

engine = AnalyticsEngine()

# Record events
engine.record_event("export", {"site": "twitter", "cookies": 113})
engine.record_event("load", {"site": "twitter"})

# Generate report
report = engine.generate_report()
print(f"Total events: {report.total_events}")
print(f"Success rate: {report.success_rate:.1%}")

# Export to CSV
engine.export_csv("analytics.csv")
```

### Session Sharing

```python
from tokenade.core.sharing.url_shortener import SessionURLShortener, URLShortenerConfig

config = URLShortenerConfig(require_password=True)
shortener = SessionURLShortener(config)

# Create share
result = shortener.create_share(
    session_file="twitter.tokenade",
    password="MySecurePassword123!",
    expiry_hours=24,
)
print(f"Share URL: {result['short_url']}")

# Retrieve session
shortener.retrieve_session(
    short_url=result['short_url'],
    password="MySecurePassword123!",
    output_path="retrieved.tokenade",
)
```

### Session Sync

```python
from tokenade.core.sync.syncer import SessionSyncer, SyncConfig

config = SyncConfig(
    remote_host="user@remote-host",
    remote_path="~/.tokenade/sessions",
    local_path="~/.tokenade/sessions",
)

syncer = SessionSyncer(config)

# Push sessions
result = syncer.push()

# Pull sessions
result = syncer.pull()

# Bidirectional sync
result = syncer.sync("bidirectional")
```

### Mobile Import

```python
from tokenade.core.importer.mobile_import import MobileImportManager

manager = MobileImportManager()

# List connected devices
devices = manager.list_devices()
for device in devices:
    print(f"{device.platform}: {device.model} ({device.os_version})")

# Extract from device
result = manager.extract(device, browser="chrome", domains=["google.com"])

# Extract from iTunes backup (no device needed)
result = manager.extract_from_itunes_backup(browser="safari")

# List iTunes backups
backups = manager.list_itunes_backups()
```

### Enterprise Features

```python
from tokenade.core.enterprise.auth import RBACManager
from tokenade.core.enterprise.encrypted_audit import EncryptedAuditLogger

# RBAC
rbac = RBACManager()
rbac.create_role("admin", permissions=["read", "write", "delete"])
rbac.assign_role("alice", "admin")

# Audit logging
audit = EncryptedAuditLogger()
audit.log(user_id="alice", action="export", resource="session", success=True)
entries = audit.query(user_id="alice")
```

### Docker Deployment

```bash
# Build image
docker build -t tokenade:latest .

# Run API server
docker run -p 9224:9224 tokenade:latest

# Run with docker-compose
docker-compose up -d
```

### Kubernetes Deployment

```bash
# Apply all manifests
kubectl apply -f deploy/k8s/

# Check pods
kubectl -n tokenade get pods

# View logs
kubectl -n tokenade logs -f deployment/tokenade
```

## License

MIT License
